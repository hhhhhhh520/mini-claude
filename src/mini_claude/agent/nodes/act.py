"""Act node: Call LLM and execute tools."""

import asyncio
import json
import time
from typing import Dict, List

from ._shared import (
    AgentState,
    StopReason,
    AIMessage,
    get_rate_limiter,
    get_all_tools,
    convert_tools_to_litellm,
    get_degradation_manager,
    get_metrics_collector,
    settings,
    trace_agent_node,
    trace_tool_call,
    trace_llm_call,
    logger,
    llm_provider,
    LLMProvider,
)
from ._act_helpers import (
    convert_message,
    handle_token_budget,
    parse_tool_calls,
    execute_single_tool,
    setup_token_counter,
)


def _update_plan_step_status(execution_plan: Dict, step_index: int, status: str) -> Dict:
    """Update execution plan step status.

    Args:
        execution_plan: Serialized execution plan
        step_index: Step index to update
        status: New status (pending/running/completed/failed)

    Returns:
        Updated execution plan
    """
    if not execution_plan or step_index >= len(execution_plan.get("steps", [])):
        return execution_plan

    updated_plan = dict(execution_plan)
    updated_steps = list(updated_plan.get("steps", []))

    if step_index < len(updated_steps):
        updated_steps[step_index] = dict(updated_steps[step_index])
        updated_steps[step_index]["status"] = status

    updated_plan["steps"] = updated_steps
    return updated_plan


def _get_plan_progress_message(execution_plan: Dict, step_index: int) -> str:
    """Get progress message for current step."""
    if not execution_plan:
        return ""

    steps = execution_plan.get("steps", [])
    if step_index < len(steps):
        step = steps[step_index]
        return f"[步骤 {step_index + 1}/{len(steps)}] {step.get('description', '执行中')}"
    return ""


async def act_node(state: AgentState) -> dict:
    """Act 节点：调用 LLM 并执行工具

    职责：
    1. 调用 LLM 获取响应
    2. 执行工具调用
    3. 收集结果

    注意：不在这里决定是否继续，交给 observe_node

    Returns:
        部分状态更新
    """
    with trace_agent_node("act", state["iteration"]) as span:
        messages = list(state["messages"])
        logger.debug("act_node: messages count", count=len(messages))

        if span:
            span.set_attribute("messages_count", len(messages))

        # Rate limit check
        rate_limiter = get_rate_limiter()
        session_id = state.get("session_id", "default")
        if not rate_limiter.check_limit(session_id):
            retry_after = rate_limiter.get_retry_after(session_id)
            remaining = rate_limiter.get_remaining(session_id)
            logger.warning(
                "act_node: rate limit exceeded",
                session_id=session_id,
                retry_after=retry_after,
                remaining=remaining,
            )
            if span:
                span.set_attribute("rate_limit_exceeded", True)
            return {
                "messages": [
                    AIMessage(
                        content=f"请求频率超限，请等待 {int(retry_after)} 秒后再试。\n"
                        f"当前限制：每分钟 {settings.rate_limit_requests_per_minute} 次请求。\n"
                        f"剩余配额：{remaining} 次。"
                    )
                ],
                "stop_reason": StopReason.ERROR,
            }

        # Get available tools
        tools = get_all_tools()
        allowed_tools = state.get("allowed_tools")
        if allowed_tools:
            tools = [t for t in tools if t.get("name") in allowed_tools]
        litellm_tools = convert_tools_to_litellm(tools)

        # Convert messages
        litellm_messages = [convert_message(m) for m in messages]

        # Token budget check
        token_counter = setup_token_counter()
        messages, litellm_messages = await handle_token_budget(
            messages, litellm_messages, token_counter
        )

        try:
            degr_manager = get_degradation_manager()
            metrics_collector = get_metrics_collector()
            request_start_time = metrics_collector.record_request_start()
            backoff = degr_manager.backoff
            max_retries = backoff.max_retries

            # LLM call with retry
            content, raw_tool_calls = await _call_llm_with_retry(
                state,
                litellm_messages,
                litellm_tools,
                degr_manager,
                metrics_collector,
                span,
                max_retries,
                backoff,
            )

            # Parse tool calls
            tool_calls = parse_tool_calls(raw_tool_calls)
            logger.debug("act_node: tool_calls", tool_calls=tool_calls)

            if span:
                span.set_attribute("tool_calls_count", len(tool_calls))

            # Build AI message
            ai_message = AIMessage(content=content or "", tool_calls=tool_calls)
            new_messages = [ai_message]

            # Get execution plan state
            execution_plan = state.get("execution_plan")
            current_step_index = state.get("current_step_index", 0)

            # Execute tools with plan progress tracking
            if tool_calls:
                # Update plan step to RUNNING if we have a plan
                updated_plan = None
                if execution_plan:
                    updated_plan = _update_plan_step_status(
                        execution_plan, current_step_index, "running"
                    )
                    progress_msg = _get_plan_progress_message(updated_plan, current_step_index)
                    if progress_msg:
                        logger.info("act_node: plan progress", progress=progress_msg)

                new_messages, early_return, step_success = await _execute_tools(
                    tool_calls,
                    degr_manager,
                    metrics_collector,
                    new_messages,
                    span,
                    execution_plan=updated_plan or execution_plan,
                    step_index=current_step_index,
                )

                # Update plan step status based on result
                if updated_plan:
                    new_status = "completed" if step_success else "failed"
                    updated_plan = _update_plan_step_status(
                        updated_plan, current_step_index, new_status
                    )
                    # Advance to next step
                    next_step_index = current_step_index + 1

                # Build result with messages and plan updates
                result = {"messages": new_messages}
                if updated_plan:
                    result["execution_plan"] = updated_plan
                    result["current_step_index"] = next_step_index

                # Merge early_return fields if present
                if early_return:
                    result.update(early_return)

                return result

            logger.debug("act_node: returning messages", count=len(new_messages))

            request_duration = time.time() - request_start_time
            metrics_collector.record_request_end(success=True, duration=request_duration)

            if span:
                span.set_attribute("request_duration_ms", request_duration * 1000)

            return {"messages": new_messages}

        except Exception as e:
            logger.error("act_node EXCEPTION", exc_info=True, error=str(e))
            request_duration = time.time() - request_start_time
            metrics_collector.record_request_end(
                success=False,
                duration=request_duration,
                error_type=type(e).__name__,
            )
            if span:
                span.set_attribute("error", str(e))
            return {
                "messages": [AIMessage(content="执行过程中发生错误，请检查任务描述或重试")],
                "errors": [f"Act error: {type(e).__name__}"],
                "stop_reason": StopReason.ERROR,
            }


async def _call_llm_with_retry(
    state,
    litellm_messages: List[Dict],
    litellm_tools: List,
    degr_manager,
    metrics_collector,
    span,
    max_retries: int,
    backoff,
) -> tuple:
    """Call LLM with retry logic.

    Returns:
        Tuple of (content, raw_tool_calls)
    """
    content = ""
    raw_tool_calls = None
    response = None

    for attempt in range(max_retries + 1):
        try:
            current_model = degr_manager.model.get_current_model()
            if current_model != settings.default_model:
                local_provider = LLMProvider(model=current_model)
                logger.info("Using degraded model", model=current_model, attempt=attempt)
                if span:
                    span.set_attribute("degraded_model", current_model)
            else:
                local_provider = llm_provider

            if span:
                span.set_attribute("model", current_model)

            with trace_llm_call(current_model, len(litellm_messages)) as llm_span:
                use_streaming = settings.streaming_enabled and not state.get("is_subagent", False)

                if use_streaming:
                    result = await _streaming_llm_call(
                        local_provider,
                        litellm_messages,
                        litellm_tools,
                        max_tokens=settings.llm_max_tokens,
                    )
                    content = result.get("content", "")
                    raw_tool_calls = result.get("tool_calls")
                else:
                    response = await local_provider.chat(
                        messages=litellm_messages,
                        tools=litellm_tools if litellm_tools else None,
                        tool_choice="auto",
                        max_tokens=settings.llm_max_tokens,
                    )
                    message = response.choices[0].message
                    content = message.content or ""
                    raw_tool_calls = message.tool_calls if hasattr(message, "tool_calls") else None

                if llm_span and hasattr(response, "usage") and response.usage:
                    llm_span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
                    llm_span.set_attribute(
                        "llm.completion_tokens", response.usage.completion_tokens
                    )
                    metrics_collector.record_token_usage(response.usage.prompt_tokens, "input")
                    metrics_collector.record_token_usage(response.usage.completion_tokens, "output")

            degr_manager.model.record_success(current_model)
            backoff.reset()
            break

        except (ConnectionError, TimeoutError, asyncio.TimeoutError) as e:
            logger.warning("LLM call failed, attempting retry", error=str(e), attempt=attempt)
            if attempt < max_retries:
                degr_manager.model.record_failure(current_model, str(e))
                await backoff.wait()
                continue
            else:
                logger.error("All LLM retries failed", error=str(e))
                if span:
                    span.set_attribute("llm_error", str(e))
                raise RuntimeError(f"LLM 调用失败，已尝试 {max_retries} 次重试：{e}")

        except Exception as e:
            logger.error("LLM call unexpected error", error=str(e))
            raise

    return content, raw_tool_calls


async def _streaming_llm_call(
    local_provider,
    litellm_messages: List[Dict],
    litellm_tools: List,
    max_tokens: int = 8192,
) -> Dict:
    """Make streaming LLM call.

    Returns:
        Dict with 'content' and 'tool_calls' keys
    """
    from ...cli.display import display

    def stream_callback(token: str):
        display.stream_token(token)

    def tool_stream_callback(event_type: str, data: str):
        if event_type == "name":
            display.show_tool_call_start(data)
        elif event_type == "args":
            display.stream_tool_args(data)

    result = await local_provider.chat_stream_with_tools(
        messages=litellm_messages,
        tools=litellm_tools if litellm_tools else None,
        tool_choice="auto",
        max_tokens=max_tokens,
        stream_callback=stream_callback,
        tool_stream_callback=tool_stream_callback,
    )
    display.end_stream()
    return result


async def _execute_tools(
    tool_calls: List[Dict],
    degr_manager,
    metrics_collector,
    new_messages: List,
    span,
    execution_plan: Dict = None,
    step_index: int = 0,
) -> tuple:
    """Execute tool calls.

    Args:
        tool_calls: List of tool calls to execute
        degr_manager: Degradation manager
        metrics_collector: Metrics collector
        new_messages: List to append result messages to
        span: Tracing span
        execution_plan: Current execution plan (for progress display)
        step_index: Current step index (for progress display)

    Returns:
        Tuple of (updated_messages, early_return_dict or None, step_success)
    """
    step_success = True  # Assume success unless a tool fails

    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse tool args in execute loop", tool_name=tool_name, error=str(e)
                )
                tool_args = {
                    "_parse_error": f"JSON 解析失败: {str(e)}",
                    "_raw_args": tool_args[:500],
                }

        logger.debug("Executing tool", index=i + 1, total=len(tool_calls), tool_name=tool_name)

        # Display plan progress if available
        if execution_plan and i == 0:
            progress_msg = _get_plan_progress_message(execution_plan, step_index)
            if progress_msg:
                from ...cli.display import display

                display.show_info(progress_msg)

        new_messages, state_update = await execute_single_tool(
            tool_name, tool_args, degr_manager, metrics_collector, trace_tool_call, new_messages
        )

        # Check if tool execution failed
        if state_update and state_update.get("stop_reason") == "error":
            step_success = False

        if state_update:
            return new_messages, state_update, step_success

    return new_messages, None, step_success
