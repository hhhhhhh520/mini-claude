"""Helper functions for act_node."""

import asyncio
import json
from typing import Dict, List, Tuple, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ._shared import (
    get_token_counter,
    TokenLimitStrategy,
    get_degradation_manager,
    get_metrics_collector,
    PathConfirmationRequired,
    settings,
    logger,
    llm_provider,
    LLMProvider,
)


def convert_message(msg) -> Dict[str, str]:
    """Convert LangChain message to LiteLLM format.

    Args:
        msg: LangChain message (HumanMessage, AIMessage, SystemMessage)

    Returns:
        Dict with 'role' and 'content' keys
    """
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "assistant", "content": msg.content or ""}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    else:
        return {"role": "user", "content": str(msg.content)}


async def handle_token_budget(
    messages: List,
    litellm_messages: List[Dict],
    token_counter,
) -> Tuple[List, List[Dict]]:
    """Handle token budget check and apply strategy if needed.

    Args:
        messages: LangChain messages
        litellm_messages: LiteLLM format messages
        token_counter: TokenCounter instance

    Returns:
        Tuple of (updated_messages, updated_litellm_messages)
    """
    budget_check = token_counter.check_budget(
        litellm_messages,
        reserved_output=settings.token_reserved_output,
    )

    if not budget_check["ok"]:
        # Over budget
        if token_counter.strategy == TokenLimitStrategy.SUMMARIZE:
            logger.debug("act_node: token budget exceeded, summarizing messages")
            # Summarize messages using LLM
            async def llm_chat_for_summary(msgs: List[Dict], **kwargs) -> Dict:
                return await llm_provider.chat(messages=msgs, **kwargs)

            summarized, summary_text = await token_counter.summarize_messages(
                litellm_messages,
                llm_chat_func=llm_chat_for_summary,
            )
            litellm_messages = summarized
            # Sync LangChain messages with summarized messages
            if len(litellm_messages) < len(messages):
                # Find the summary message position
                summary_idx = None
                for i, msg in enumerate(litellm_messages):
                    if msg.get("role") == "assistant" and "[历史对话摘要]" in msg.get("content", ""):
                        summary_idx = i
                        break

                if summary_idx is not None:
                    # Rebuild messages: system + summary + last few
                    new_messages = []
                    # System message
                    if messages and isinstance(messages[0], SystemMessage):
                        new_messages.append(messages[0])
                    # Summary as AI message
                    new_messages.append(AIMessage(content=litellm_messages[summary_idx]["content"]))
                    # Last few messages
                    keep_last = len(litellm_messages) - summary_idx - 1
                    if keep_last > 0 and len(messages) > keep_last:
                        new_messages.extend(messages[-keep_last:])
                    messages = new_messages
                else:
                    # Fallback to truncate
                    keep_first = 1
                    keep_last = 4
                    if len(messages) > keep_first + keep_last:
                        messages = messages[:keep_first] + messages[-keep_last:]

        elif token_counter.strategy == TokenLimitStrategy.TRUNCATE:
            logger.debug("act_node: token budget exceeded, truncating messages")
            # Truncate messages
            truncated = token_counter.truncate_messages(litellm_messages)
            litellm_messages = truncated
            # Also truncate LangChain messages
            keep_first = 1  # System message
            keep_last = 4   # Recent context
            if len(messages) > keep_first + keep_last:
                messages = messages[:keep_first] + messages[-keep_last:]
        else:
            # Warn strategy - log warning but continue
            logger.warning(budget_check['reason'])
    elif budget_check.get("action") == "warn":
        logger.warning(budget_check['reason'])

    return messages, litellm_messages


def parse_tool_calls(raw_tool_calls) -> List[Dict]:
    """Parse raw tool calls from LLM response.

    Args:
        raw_tool_calls: Raw tool calls from LLM response

    Returns:
        List of parsed tool calls with 'id', 'name', 'args' keys
    """
    tool_calls = []
    if not raw_tool_calls:
        return tool_calls

    for tc in raw_tool_calls:
        args = tc.get("arguments", "{}") if isinstance(tc, dict) else tc.function.arguments
        args_str = args if isinstance(args, str) else "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as e:
                # JSON 解析失败，记录错误并返回原始字符串让 LLM 修正
                logger.warning("Failed to parse tool arguments JSON", error=str(e), args_preview=args_str[:200])
                args = {"_parse_error": f"JSON 解析失败: {str(e)}", "_raw_args": args_str[:500]}

        name = tc.get("name", "") if isinstance(tc, dict) else tc.function.name
        if not name:
            continue

        tool_calls.append({
            "id": tc.get("id", "") if isinstance(tc, dict) else tc.id,
            "name": name,
            "args": args,
        })

    return tool_calls


async def execute_single_tool(
    tool_name: str,
    tool_args: Dict,
    degr_manager,
    metrics_collector,
    trace_tool_call,
    new_messages: List,
) -> Tuple[List, Dict]:
    """Execute a single tool call.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments for the tool
        degr_manager: DegradationManager instance
        metrics_collector: MetricsCollector instance
        trace_tool_call: Trace function for tool calls
        new_messages: List to append result messages to

    Returns:
        Tuple of (updated_new_messages, state_update or None if should continue)
    """
    from ...tools import execute_tool

    # Check if tool should be skipped (degradation)
    if degr_manager.tool.should_skip(tool_name):
        replacement = degr_manager.tool.get_replacement(tool_name)
        if replacement:
            logger.info("Tool degraded, using replacement", from_tool=tool_name, to_tool=replacement)
            tool_name = replacement
        else:
            logger.warning("Tool skipped due to failures", tool=tool_name)
            new_messages.append(HumanMessage(
                content=f"Tool {tool_name} 被跳过（之前多次失败）",
                name=tool_name,
            ))
            return new_messages, None

    # Validate required parameters
    if tool_name in ["write_file", "edit_file"]:
        # Check for parse error first
        if tool_args.get("_parse_error"):
            error_msg = f"Error: 工具参数解析失败 - {tool_args['_parse_error']}"
            logger.warning(error_msg)
            new_messages.append(HumanMessage(content=error_msg, name=tool_name))
            return new_messages, None

        if not tool_args.get("path"):
            error_msg = f"Error: Tool {tool_name} requires 'path' argument"
            logger.debug(error_msg)
            new_messages.append(HumanMessage(content=error_msg, name=tool_name))
            return new_messages, None
        if tool_name == "write_file" and not tool_args.get("content"):
            error_msg = "Error: Tool write_file requires 'content' argument"
            logger.debug(error_msg)
            new_messages.append(HumanMessage(content=error_msg, name=tool_name))
            return new_messages, None

    try:
        # Trace tool execution
        with trace_tool_call(tool_name, tool_args):
            result = await execute_tool(tool_name, tool_args)

        logger.debug("Tool result", tool_name=tool_name, result_preview=result[:200] if result else 'None')

        # Record tool success
        degr_manager.tool.record_success(tool_name)
        metrics_collector.record_tool_call(tool_name, success=True)

        new_messages.append(HumanMessage(
            content=f"Tool {tool_name} result: {result}",
            name=tool_name,
        ))
        return new_messages, None

    except PathConfirmationRequired as e:
        # Path requires user confirmation
        from ._shared import StopReason
        logger.debug("Path confirmation required", path=e.path)
        new_messages.append(HumanMessage(
            content=f"路径确认请求：{e.path}\n\n原因：{e.reason}\n\n请回复 'yes' 或 'y' 确认访问此路径，或提供其他路径。",
            name=tool_name,
        ))
        return new_messages, {
            "stop_reason": StopReason.WAITING_CONFIRMATION,
            "pending_confirmation_path": e.path,
        }

    except (FileNotFoundError, PermissionError, OSError) as e:
        # File system errors
        logger.debug("File system error", tool_name=tool_name, error=str(e))
        degr_manager.tool.record_failure(tool_name, f"File system error: {e}")
        metrics_collector.record_tool_call(tool_name, success=False)
        new_messages.append(HumanMessage(
            content=f"Tool {tool_name} 文件系统错误: {e}",
            name=tool_name,
        ))
        return new_messages, None

    except (ValueError, TypeError, KeyError) as e:
        # Parameter errors
        logger.debug("Parameter error", tool_name=tool_name, error=str(e))
        degr_manager.tool.record_failure(tool_name, f"Parameter error: {e}")
        metrics_collector.record_tool_call(tool_name, success=False)
        new_messages.append(HumanMessage(
            content=f"Tool {tool_name} 参数错误: {e}",
            name=tool_name,
        ))
        return new_messages, None

    except asyncio.TimeoutError:
        # Timeout errors
        logger.debug("Tool timeout", tool_name=tool_name)
        degr_manager.tool.record_failure(tool_name, "Timeout")
        metrics_collector.record_tool_call(tool_name, success=False)
        new_messages.append(HumanMessage(
            content=f"Tool {tool_name} 执行超时",
            name=tool_name,
        ))
        return new_messages, None

    except Exception as e:
        # Other unknown errors
        logger.error("Unexpected tool error", exc_info=True, tool_name=tool_name, error=str(e))
        degr_manager.tool.record_failure(tool_name, f"Unexpected error: {type(e).__name__}")
        metrics_collector.record_tool_call(tool_name, success=False)
        new_messages.append(HumanMessage(
            content=f"Tool {tool_name} 执行失败，请检查参数或重试",
            name=tool_name,
        ))
        return new_messages, None


def setup_token_counter():
    """Set up token counter with settings.

    Returns:
        Configured TokenCounter instance
    """
    token_counter = get_token_counter(settings.default_model)
    token_counter.budget_ratio = settings.token_budget_ratio
    token_counter.warn_ratio = settings.token_warn_ratio
    if settings.token_strategy == "truncate":
        token_counter.strategy = TokenLimitStrategy.TRUNCATE
    elif settings.token_strategy == "summarize":
        token_counter.strategy = TokenLimitStrategy.SUMMARIZE
    else:
        token_counter.strategy = TokenLimitStrategy.WARN
    return token_counter
