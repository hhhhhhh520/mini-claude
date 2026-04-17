"""Agent graph nodes: Think, Plan, Act, Observe."""

import asyncio
import sys
import io
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from .state import AgentState
from .subagent import subagent_manager, AgentStatus
from ..llm.provider import LLMProvider, convert_tools_to_litellm
from ..llm.prompts import get_system_prompt, get_planning_prompt
from ..tools import get_all_tools
from mini_claude.config.settings import settings, ModelProvider


# Fix Windows console encoding for debug output
def safe_print(msg: str):
    """Print safely handling encoding issues on Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: encode to ASCII with replacement
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# Initialize LLM provider
llm_provider = LLMProvider()


async def think_node(state: AgentState) -> AgentState:
    """Think node: Analyze the request and prepare for planning."""
    messages = list(state["messages"])
    iteration = state["iteration"]

    # Check iteration limit (use subagent limit if is_subagent)
    max_iter = settings.max_subagent_iterations if state.get("is_subagent") else settings.max_iterations
    if iteration >= max_iter:
        messages.append(AIMessage(content="Maximum iterations reached."))
        return AgentState(
            messages=messages,
            current_task=state["current_task"],
            plan=state.get("plan"),
            tool_results=state.get("tool_results", []),
            pending_tool_calls=state.get("pending_tool_calls"),
            sub_agents=state.get("sub_agents", {}),
            sub_agent_results=state.get("sub_agent_results", {}),
            iteration=iteration,
            should_continue=False,
            thread_id=state["thread_id"],
            errors=state.get("errors"),
            is_subagent=state.get("is_subagent", False),
            allowed_tools=state.get("allowed_tools"),
            incomplete_check_count=state.get("incomplete_check_count", 0),
            last_missing_files=state.get("last_missing_files"),
            consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
            last_tool_names=state.get("last_tool_names"),
            no_tool_call_count=state.get("no_tool_call_count", 0),
        )

    # Add system message if not present
    if not any(isinstance(m, SystemMessage) for m in messages):
        provider = settings.get_model_provider()
        system_prompt = get_system_prompt(provider)
        messages = [SystemMessage(content=system_prompt)] + messages

    return AgentState(
        messages=messages,
        current_task=state["current_task"],
        plan=state.get("plan"),
        tool_results=state.get("tool_results", []),
        pending_tool_calls=state.get("pending_tool_calls"),
        sub_agents=state.get("sub_agents", {}),
        sub_agent_results=state.get("sub_agent_results", {}),
        iteration=iteration + 1,
        should_continue=True,
        thread_id=state["thread_id"],
        errors=state.get("errors"),
        is_subagent=state.get("is_subagent", False),
        allowed_tools=state.get("allowed_tools"),
        incomplete_check_count=state.get("incomplete_check_count", 0),
        last_missing_files=state.get("last_missing_files"),
        consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
        last_tool_names=state.get("last_tool_names"),
        no_tool_call_count=state.get("no_tool_call_count", 0),
    )


async def plan_node(state: AgentState) -> AgentState:
    """Plan node: Create execution plan."""
    messages = list(state["messages"])
    current_task = state["current_task"]
    iteration = state["iteration"]
    safe_print(f"[DEBUG] plan_node received: messages count = {len(messages)}")

    # Skip detailed planning for simple conversational messages
    if iteration == 1:
        simple_indicators = ["你好", "hello", "hi", "介绍", "什么", "如何", "怎么", "为什么"]
        if any(ind in current_task.lower() for ind in simple_indicators) and len(current_task) < 100:
            safe_print(f"[DEBUG] plan_node: simple query, skip detailed planning")
            # Return state with a simple plan
            return AgentState(
                messages=messages,
                current_task=current_task,
                plan="直接回复用户问题",
                tool_results=state.get("tool_results", []),
                pending_tool_calls=state.get("pending_tool_calls"),
                sub_agents=state.get("sub_agents", {}),
                sub_agent_results=state.get("sub_agent_results", {}),
                iteration=iteration,
                should_continue=True,
                thread_id=state["thread_id"],
                errors=state.get("errors"),
                is_subagent=state.get("is_subagent", False),
                allowed_tools=state.get("allowed_tools"),
                incomplete_check_count=state.get("incomplete_check_count", 0),
                last_missing_files=state.get("last_missing_files"),
                consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
                last_tool_names=state.get("last_tool_names"),
                no_tool_call_count=state.get("no_tool_call_count", 0),
            )

    # Analyze the task and create a plan
    plan = None

    # Always use the original current_task for planning (not last message)
    task_text = current_task.lower() if current_task else ""

    tool_keywords = {
        "创建": "需要使用 write_file 工具",
        "开发": "需要使用 write_file 工具",
        "写": "需要使用 write_file 工具",
        "生成": "需要使用 write_file 工具",
        "文件": "可能需要使用文件读写工具",
        "读取": "需要使用 read_file 工具",
        "写入": "需要使用 write_file 工具",
        "执行": "可能需要使用 Bash 工具",
        "搜索": "可能需要使用 Grep 或 Glob 工具",
        "目录": "可能需要使用 Glob 或 Bash ls 工具",
        "代码": "可能需要读取或编辑代码文件",
        "查找": "需要使用搜索工具",
        "修改": "需要使用 edit_file 工具",
        "删除": "可能需要使用 Bash 工具",
        "网站": "需要使用 write_file 工具创建文件",
        "网页": "需要使用 write_file 工具创建文件",
        "html": "需要使用 write_file 工具创建文件",
        "前端": "需要使用 write_file 工具创建文件",
    }

    detected_actions = []
    needs_tools = False
    for keyword, action in tool_keywords.items():
        if keyword in task_text:
            detected_actions.append(action)
            needs_tools = True

    # For multi-file projects, ALWAYS check if task is complete (not just iteration > 1)
    if needs_tools:
        # Check actual files on disk
        import os
        workspace = settings.workspace_root

        # Check for web project completion
        if any(kw in task_text for kw in ["网站", "前端", "web", "网页"]):
            html_path = os.path.join(workspace, "index.html")
            css_exists = os.path.exists(os.path.join(workspace, "style.css")) or \
                         os.path.exists(os.path.join(workspace, "css", "style.css"))
            js_exists = os.path.exists(os.path.join(workspace, "script.js")) or \
                        os.path.exists(os.path.join(workspace, "js", "main.js"))

            has_html = os.path.exists(html_path)
            has_css = css_exists
            has_js = js_exists

            safe_print(f"[DEBUG] plan_node: checking files on disk: has_html={has_html}, has_css={has_css}, has_js={has_js}")

            if has_html and has_css and has_js:
                safe_print(f"[DEBUG] plan_node: web project complete, no more tools needed")
                needs_tools = False
                detected_actions = []
            elif has_html and not has_css:
                # Override plan to focus on missing files
                plan = "执行计划:\n- 使用 write_file 工具创建 style.css 样式文件\n- 使用 write_file 工具创建 script.js 脚本文件"
                safe_print(f"[DEBUG] plan_node: CSS/JS missing, need to create them")
                # Return early with specific plan
                return AgentState(
                    messages=messages,
                    current_task=current_task,
                    plan=plan,
                    tool_results=state.get("tool_results", []),
                    pending_tool_calls=state.get("pending_tool_calls"),
                    sub_agents=state.get("sub_agents", {}),
                    sub_agent_results=state.get("sub_agent_results", {}),
                    iteration=iteration,
                    should_continue=True,
                    thread_id=state["thread_id"],
                    errors=state.get("errors"),
                    is_subagent=state.get("is_subagent", False),
                    allowed_tools=state.get("allowed_tools"),
                    incomplete_check_count=state.get("incomplete_check_count", 0),
                    last_missing_files=state.get("last_missing_files"),
                    consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
                    last_tool_names=state.get("last_tool_names"),
                    no_tool_call_count=state.get("no_tool_call_count", 0),
                )

    if detected_actions:
        plan = f"执行计划:\n" + "\n".join(f"- {action}" for action in detected_actions)
        safe_print(f"[DEBUG] plan_node: created plan: {plan}")
    else:
        plan = "分析用户请求并直接响应"
        safe_print(f"[DEBUG] plan_node: no tools needed, direct response")

    return AgentState(
        messages=messages,
        current_task=current_task,
        plan=plan,
        tool_results=state.get("tool_results", []),
        pending_tool_calls=state.get("pending_tool_calls"),
        sub_agents=state.get("sub_agents", {}),
        sub_agent_results=state.get("sub_agent_results", {}),
        iteration=iteration,
        should_continue=True,
        thread_id=state["thread_id"],
        errors=state.get("errors"),
        is_subagent=state.get("is_subagent", False),
        allowed_tools=state.get("allowed_tools"),
        incomplete_check_count=state.get("incomplete_check_count", 0),
        last_missing_files=state.get("last_missing_files"),
        consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
        last_tool_names=state.get("last_tool_names"),
        no_tool_call_count=state.get("no_tool_call_count", 0),
    )


async def act_node(state: AgentState) -> AgentState:
    """Act node: Execute tools based on plan."""
    import json
    messages = list(state["messages"])
    safe_print(f"[DEBUG] act_node received: messages count = {len(messages)}")

    # Get available tools (filter by allowed_tools if specified)
    tools = get_all_tools()
    allowed_tools = state.get("allowed_tools")
    if allowed_tools:
        tools = [t for t in tools if t.get("name") in allowed_tools]
    litellm_tools = convert_tools_to_litellm(tools)

    # Convert messages to LiteLLM format
    def convert_message(msg):
        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": msg.content}
        elif isinstance(msg, AIMessage):
            return {"role": "assistant", "content": msg.content or ""}
        elif isinstance(msg, SystemMessage):
            return {"role": "system", "content": msg.content}
        else:
            return {"role": "user", "content": str(msg.content)}

    litellm_messages = [convert_message(m) for m in messages]

    try:
        # Call LLM with tools
        # Only force tool calling for write operations, not read operations
        # Read operations (read_file, list_dir) should allow model to output text after getting results
        plan = state.get("plan", "")

        # Check if this is a read-only task (reading/summarizing, not creating)
        read_only_keywords = ["读取", "总结", "告诉我", "查看", "列出", "搜索"]
        is_read_only_task = any(kw in state.get("current_task", "") for kw in read_only_keywords)

        # Only force tools for write operations, not for read operations
        force_tools = plan and ("write_file" in plan or "创建" in plan or "edit_file" in plan)
        force_tools = force_tools and not is_read_only_task

        effective_tool_choice = "required" if force_tools and litellm_tools else "auto"

        # Use streaming if enabled and not in subagent mode
        use_streaming = settings.streaming_enabled and not state.get("is_subagent", False)

        if use_streaming:
            # Stream output with tool support
            from ..cli.display import display

            def stream_callback(token: str):
                display.stream_token(token)

            def tool_stream_callback(event_type: str, data: str):
                """Handle tool call streaming events."""
                if event_type == "name":
                    # New tool call - show tool name
                    display.show_tool_call_start(data)
                elif event_type == "args":
                    # Stream arguments (code content)
                    display.stream_tool_args(data)

            result = await llm_provider.chat_stream_with_tools(
                messages=litellm_messages,
                tools=litellm_tools if litellm_tools else None,
                tool_choice=effective_tool_choice if litellm_tools else None,
                stream_callback=stream_callback,
                tool_stream_callback=tool_stream_callback,
            )

            content = result.get("content", "")
            raw_tool_calls = result.get("tool_calls")

            # End streaming display
            display.end_stream()

            # Build tool_calls list
            tool_calls = []
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    args = tc.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    # Skip tool calls with empty name (parsing error)
                    if not tc.get("name"):
                        safe_print(f"[DEBUG] act_node: skipping tool call with empty name: {tc}")
                        continue

                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": args,
                    })
        else:
            # Non-streaming mode
            response = await llm_provider.chat(
                messages=litellm_messages,
                tools=litellm_tools if litellm_tools else None,
                tool_choice=effective_tool_choice if litellm_tools else None,
            )

            message = response.choices[0].message
            content = message.content or ""

            # Check if we have tool calls
            tool_calls = []
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    # Parse args if it's a string (LiteLLM returns string)
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": args,
                    })

        # Debug output
        safe_print(f"[DEBUG] act_node: tool_calls={tool_calls}")

        # Add AI message to history
        ai_message = AIMessage(
            content=content or "",
            tool_calls=tool_calls,
        )
        messages = messages + [ai_message]

        # Execute tools immediately if there are tool calls
        if tool_calls:
            from ..tools import execute_tool

            safe_print(f"[DEBUG] act_node: executing {len(tool_calls)} tool calls")
            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Parse args if it's a string
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        safe_print(f"[DEBUG] Failed to parse tool args as JSON: {tool_args}")
                        tool_args = {}

                # Validate required args for critical tools
                if tool_name in ["write_file", "edit_file"]:
                    if not tool_args.get("path"):
                        error_msg = f"Error: Tool {tool_name} requires 'path' argument but got: {tool_args}"
                        safe_print(f"[DEBUG] {error_msg}")
                        messages.append(HumanMessage(
                            content=error_msg,
                            name=tool_name,
                        ))
                        continue
                    if tool_name == "write_file" and not tool_args.get("content"):
                        error_msg = f"Error: Tool write_file requires 'content' argument but got: {tool_args}"
                        safe_print(f"[DEBUG] {error_msg}")
                        messages.append(HumanMessage(
                            content=error_msg,
                            name=tool_name,
                        ))
                        continue

                try:
                    safe_print(f"[DEBUG] Executing tool [{i+1}/{len(tool_calls)}]: {tool_name} with args: {tool_args}")
                    result = await execute_tool(tool_name, tool_args)
                    safe_print(f"[DEBUG] Tool result: {result[:200] if result else 'None'}...")

                    # Add tool result message
                    messages.append(HumanMessage(
                        content=f"Tool {tool_name} result: {result}",
                        name=tool_name,
                    ))

                except Exception as e:
                    import traceback
                    safe_print(f"[DEBUG] Tool error: {e}")
                    safe_print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    messages.append(HumanMessage(
                        content=f"Tool {tool_name} error: {e}",
                        name=tool_name,
                    ))

        safe_print(f"[DEBUG] act_node returning: messages count = {len(messages)}, had tool_calls = {bool(tool_calls)}")

        # Determine if we should continue based on tool calls and iteration limit
        # Use consistent logic with think_node: iteration >= max_iter means stop
        max_iter = settings.max_subagent_iterations if state.get("is_subagent") else settings.max_iterations
        iteration = state["iteration"]

        if iteration >= max_iter:
            # Reached limit, stop regardless of tool calls
            should_continue = False
            safe_print(f"[DEBUG] act_node: iteration {iteration} >= max_iter {max_iter}, stopping")
        elif tool_calls:
            # Had tool calls, need to process results
            should_continue = True
        else:
            # No tool calls - check if multi-file task is incomplete
            original_task = state.get("current_task", "").lower()
            multi_file_keywords = ["开发", "创建", "生成", "网站", "前端", "项目", "web", "backend", "fastapi", "flask", "api"]
            is_multi_file_task = any(kw in original_task for kw in multi_file_keywords)

            if is_multi_file_task:
                import os
                workspace = settings.workspace_root

                html_path = os.path.join(workspace, "index.html")
                css_exists = os.path.exists(os.path.join(workspace, "style.css")) or \
                             os.path.exists(os.path.join(workspace, "css", "style.css"))
                js_exists = os.path.exists(os.path.join(workspace, "script.js")) or \
                            os.path.exists(os.path.join(workspace, "js", "main.js"))

                has_html = os.path.exists(html_path)
                has_css = css_exists
                has_js = js_exists

                safe_print(f"[DEBUG] act_node: no tool_calls, checking disk: has_html={has_html}, has_css={has_css}, has_js={has_js}")

                if has_html and not (has_css and has_js):
                    # Task incomplete, add reminder and continue
                    missing = []
                    if not has_css:
                        missing.append("style.css")
                    if not has_js:
                        missing.append("script.js")
                    reminder = f"任务未完成。请使用 write_file 工具创建缺失的文件: {', '.join(missing)}。"
                    messages.append(HumanMessage(content=reminder))
                    should_continue = True
                    safe_print(f"[DEBUG] act_node: task incomplete, added reminder")
                else:
                    should_continue = False
            else:
                should_continue = False

        # Clear pending_tool_calls after execution to prevent infinite loop
        # We only keep them if we couldn't execute them (which shouldn't happen)

        # Return complete new state
        return AgentState(
            messages=messages,
            current_task=state["current_task"],
            plan=state.get("plan"),
            tool_results=state.get("tool_results", []),
            pending_tool_calls=None,  # Clear after execution
            sub_agents=state.get("sub_agents", {}),
            sub_agent_results=state.get("sub_agent_results", {}),
            iteration=state["iteration"],
            should_continue=should_continue,
            thread_id=state["thread_id"],
            errors=state.get("errors"),
            is_subagent=state.get("is_subagent", False),
            allowed_tools=state.get("allowed_tools"),
            incomplete_check_count=state.get("incomplete_check_count", 0),
            last_missing_files=state.get("last_missing_files"),
            consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
            last_tool_names=state.get("last_tool_names"),
            no_tool_call_count=state.get("no_tool_call_count", 0),
        )

    except Exception as e:
        import traceback
        safe_print(f"[DEBUG] act_node EXCEPTION: {e}")
        safe_print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return AgentState(
            messages=messages,
            current_task=state["current_task"],
            plan=state.get("plan"),
            tool_results=state.get("tool_results", []),
            pending_tool_calls=None,
            sub_agents=state.get("sub_agents", {}),
            sub_agent_results=state.get("sub_agent_results", {}),
            iteration=state["iteration"],
            should_continue=False,
            thread_id=state["thread_id"],
            errors=(state.get("errors") or []) + [f"Act error: {e}"],
            is_subagent=state.get("is_subagent", False),
            allowed_tools=state.get("allowed_tools"),
            incomplete_check_count=state.get("incomplete_check_count", 0),
            last_missing_files=state.get("last_missing_files"),
            consecutive_read_only_count=state.get("consecutive_read_only_count", 0),
            last_tool_names=state.get("last_tool_names"),
            no_tool_call_count=state.get("no_tool_call_count", 0),
        )


async def observe_node(state: AgentState) -> AgentState:
    """Observe node: Process tool results and decide next steps."""
    messages = list(state["messages"])
    iteration = state["iteration"]

    safe_print(f"[DEBUG] observe_node: iteration={iteration}, messages count = {len(messages)}")

    # Initialize defaults
    should_continue = False
    incomplete_count = state.get("incomplete_check_count", 0)
    missing = state.get("last_missing_files", [])

    # Track consecutive iterations without tool calls (idle detection)
    no_tool_call_count = state.get("no_tool_call_count", 0)

    # Check iteration limit first (use subagent limit if is_subagent)
    max_iter = settings.max_subagent_iterations if state.get("is_subagent") else settings.max_iterations
    if iteration >= max_iter:
        safe_print(f"[DEBUG] observe_node: max iterations reached")
        should_continue = False
    else:
        # FIRST: Check if multi-file task is complete (regardless of tool results)
        original_task = state.get("current_task", "").lower()
        multi_file_keywords = ["开发", "创建", "生成", "网站", "前端", "项目", "web"]
        is_multi_file_task = any(kw in original_task for kw in multi_file_keywords)

        if is_multi_file_task:
            # Check actual files on disk
            import os
            workspace = settings.workspace_root

            html_path = os.path.join(workspace, "index.html")
            css_exists = os.path.exists(os.path.join(workspace, "style.css")) or \
                         os.path.exists(os.path.join(workspace, "css", "style.css"))
            js_exists = os.path.exists(os.path.join(workspace, "script.js")) or \
                        os.path.exists(os.path.join(workspace, "js", "main.js"))

            has_html = os.path.exists(html_path)
            has_css = css_exists
            has_js = js_exists

            safe_print(f"[DEBUG] observe_node: checking disk FIRST: has_html={has_html}, has_css={has_css}, has_js={has_js}")

            # If project is complete, STOP regardless of tool results
            if has_html and has_css and has_js:
                safe_print(f"[DEBUG] observe_node: web project complete, STOPPING")
                should_continue = False
                incomplete_count = 0
                missing = []
                # Return immediately to prevent further processing
                return AgentState(
                    messages=messages,
                    current_task=state["current_task"],
                    plan=state.get("plan"),
                    tool_results=state.get("tool_results", []),
                    pending_tool_calls=None,
                    sub_agents=state.get("sub_agents", {}),
                    sub_agent_results=state.get("sub_agent_results", {}),
                    iteration=iteration,
                    should_continue=False,
                    thread_id=state["thread_id"],
                    errors=state.get("errors"),
                    is_subagent=state.get("is_subagent", False),
                    allowed_tools=state.get("allowed_tools"),
                    incomplete_check_count=0,
                    last_missing_files=[],
                    consecutive_read_only_count=0,
                    last_tool_names=[],
                    no_tool_call_count=0,
                )

        # SECOND: Check if we just executed tools - if so, continue to let LLM process results
        # Look for tool results (HumanMessage with name attribute) after the last AIMessage
        has_tool_result = False
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                has_tool_result = True
                break
            if isinstance(msg, AIMessage):
                break

        if has_tool_result:
            # Continue to let LLM process results and create more files
            safe_print(f"[DEBUG] observe_node: tool results found, continuing to process")
            should_continue = True
            incomplete_count = state.get("incomplete_check_count", 0)
            missing = state.get("last_missing_files", [])
            no_tool_call_count = 0  # Reset idle counter when we have tool results

            # For subagents: check if we just wrote a file - if so, we're done
            if state.get("is_subagent", False):
                # Check if last tool was a write operation
                for msg in reversed(messages):
                    if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                        if msg.name in ['write_file', 'edit_file']:
                            safe_print(f"[DEBUG] observe_node: subagent completed write operation, stopping")
                            should_continue = False
                            break
                        break

            # Check if we just completed execute_parallel - if so, stop
            # Only stop after execute_parallel, NOT after plan_parallel (need to continue to execute)
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                    if msg.name == 'execute_parallel':
                        # Check if result indicates success/completion
                        result_content = str(msg.content) if msg.content else ""
                        completion_indicators = ['Completed:', 'Execution complete', '✓']
                        if any(ind in result_content for ind in completion_indicators):
                            safe_print(f"[DEBUG] observe_node: execute_parallel completed successfully, stopping")
                            should_continue = False
                            break
                    break
        else:
            # No tool results - increment idle counter
            no_tool_call_count = state.get("no_tool_call_count", 0) + 1
            safe_print(f"[DEBUG] observe_node: no tool results, idle count = {no_tool_call_count}")

            # Check for idle loop - if 3+ consecutive iterations without tool calls, stop
            if no_tool_call_count >= 3:
                safe_print(f"[DEBUG] observe_node: idle loop detected ({no_tool_call_count} iterations without tools), stopping")
                should_continue = False
            else:
                # Check if the original task is a multi-file project that's incomplete
                original_task = state.get("current_task", "").lower()
                multi_file_keywords = ["开发", "创建", "生成", "网站", "前端", "项目", "web", "backend", "fastapi", "flask", "api"]

                is_multi_file_task = any(kw in original_task for kw in multi_file_keywords)

                if is_multi_file_task:
                    # Check actual files on disk
                    import os
                    workspace = settings.workspace_root

                    # Check for web project (HTML/CSS/JS)
                    html_path = os.path.join(workspace, "index.html")
                    css_exists = os.path.exists(os.path.join(workspace, "style.css")) or \
                                 os.path.exists(os.path.join(workspace, "css", "style.css"))
                    js_exists = os.path.exists(os.path.join(workspace, "script.js")) or \
                                os.path.exists(os.path.join(workspace, "js", "main.js"))

                    has_html = os.path.exists(html_path)
                    has_css = css_exists
                    has_js = js_exists

                    safe_print(f"[DEBUG] observe_node: checking disk: has_html={has_html}, has_css={has_css}, has_js={has_js}")

                    # If HTML was created but CSS/JS are missing, continue
                    if has_html and not (has_css and has_js):
                        # Check for infinite loop - if same missing files detected multiple times
                        missing = []
                        if not has_css:
                            missing.append("style.css")
                        if not has_js:
                            missing.append("script.js")

                        last_missing = state.get("last_missing_files", [])
                        incomplete_count = state.get("incomplete_check_count", 0)

                        if missing == last_missing:
                            incomplete_count += 1
                        else:
                            incomplete_count = 1

                        # Max 3 consecutive checks with same missing files
                        if incomplete_count >= 3:
                            safe_print(f"[DEBUG] observe_node: same missing files detected {incomplete_count} times, stopping")
                            error_msg = f"无法自动创建缺失文件: {', '.join(missing)}。请手动处理或重新描述任务。"
                            messages = messages + [AIMessage(content=error_msg)]
                            should_continue = False
                        else:
                            safe_print(f"[DEBUG] observe_node: web project incomplete (missing CSS/JS), continuing (attempt {incomplete_count})")
                            reminder = f"""重要提醒：项目文件不完整，缺少: {', '.join(missing)}

请立即使用 write_file 工具创建这些文件：
- write_file(path="script.js", content="...")

禁止使用 read_file 或 list_dir，必须使用 write_file 创建新文件！"""
                            messages = messages + [HumanMessage(content=reminder)]
                            should_continue = True
                    else:
                        # Check for backend project (Python files)
                        main_py = os.path.join(workspace, "main.py")
                        models_py = os.path.join(workspace, "models.py")
                        has_main = os.path.exists(main_py)
                        has_models = os.path.exists(models_py)

                        # If task mentions backend files but they're missing
                        backend_keywords = ["fastapi", "flask", "backend", "api", "main.py", "models.py"]
                        is_backend_task = any(kw in original_task for kw in backend_keywords)

                        if is_backend_task and not (has_main and has_models):
                            missing = []
                            if not has_main:
                                missing.append("main.py")
                            if not has_models:
                                missing.append("models.py")

                            if missing:
                                safe_print(f"[DEBUG] observe_node: backend project incomplete, missing: {missing}")
                                reminder = f"""重要提醒：后端项目文件不完整，缺少: {', '.join(missing)}

请立即使用 write_file 工具创建这些文件。"""
                                messages = messages + [HumanMessage(content=reminder)]
                                should_continue = True
                            else:
                                incomplete_count = 0
                                missing = []
                        else:
                            incomplete_count = 0
                            missing = []
                else:
                    # No tool results, check for unexecuted tool calls
                    should_continue = False
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage):
                            tc = getattr(msg, 'tool_calls', None)
                            if tc and len(tc) > 0:
                                # Check if these tool calls have already been executed
                                msg_idx = messages.index(msg)
                                has_result = False
                                for j in range(msg_idx + 1, len(messages)):
                                    if isinstance(messages[j], HumanMessage) and hasattr(messages[j], 'name'):
                                        has_result = True
                                        break
                                if not has_result:
                                    safe_print(f"[DEBUG] observe_node: found unexecuted tool_calls")
                                    should_continue = True
                            break

    # Detect read-only tool loop (auto-stop for non-web tasks)
    # Read-only tools: read_file, list_dir, search_files, search_content, web_search
    # Write tools: write_file, edit_file, run_command
    READ_ONLY_TOOLS = {'read_file', 'list_dir', 'search_files', 'search_content', 'web_search'}
    WRITE_TOOLS = {'write_file', 'edit_file', 'run_command'}

    # Get last executed tool names from recent tool results
    recent_tool_names = []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
            recent_tool_names.append(msg.name)
        if len(recent_tool_names) >= 3:  # Check last 3 tools
            break

    # Check if all recent tools are read-only
    all_read_only = all(name in READ_ONLY_TOOLS for name in recent_tool_names) if recent_tool_names else False
    has_write_tool = any(name in WRITE_TOOLS for name in recent_tool_names)

    # Update consecutive read-only count
    prev_read_only_count = state.get("consecutive_read_only_count", 0)
    if all_read_only and not has_write_tool:
        consecutive_read_only_count = prev_read_only_count + len(recent_tool_names)
    else:
        consecutive_read_only_count = 0

    # If 2+ consecutive read-only tools, add reminder and stop after this iteration
    if consecutive_read_only_count >= 2 and should_continue:
        safe_print(f"[DEBUG] observe_node: detected read-only loop ({consecutive_read_only_count} consecutive)")
        # Add a reminder to help LLM understand it should output result
        reminder = """你已经成功获取了所需信息。现在请直接输出结果回答用户的问题，不要再调用工具。

例如：
- 如果用户要求"读取并总结"，请直接输出总结内容
- 如果用户要求"告诉我内容"，请直接告诉用户内容
- 不要再次调用 read_file 或其他工具"""

        messages = messages + [HumanMessage(content=reminder)]
        # Continue one more time to let LLM output the result
        should_continue = True
        # Reset counter to prevent infinite loop
        consecutive_read_only_count = 0

    safe_print(f"[DEBUG] observe_node: should_continue = {should_continue}")

    return AgentState(
        messages=messages,
        current_task=state["current_task"],
        plan=state.get("plan"),
        tool_results=state.get("tool_results", []),
        pending_tool_calls=None,
        sub_agents=state.get("sub_agents", {}),
        sub_agent_results=state.get("sub_agent_results", {}),
        iteration=iteration,
        should_continue=should_continue,
        thread_id=state["thread_id"],
        errors=state.get("errors"),
        is_subagent=state.get("is_subagent", False),
        allowed_tools=state.get("allowed_tools"),
        incomplete_check_count=incomplete_count if 'incomplete_count' in dir() else state.get("incomplete_check_count", 0),
        last_missing_files=missing if 'missing' in dir() else state.get("last_missing_files"),
        consecutive_read_only_count=consecutive_read_only_count,
        last_tool_names=recent_tool_names,
        no_tool_call_count=no_tool_call_count if 'no_tool_call_count' in dir() else state.get("no_tool_call_count", 0),
    )


def should_continue_router(state: AgentState) -> bool:
    """Router function to determine if we should continue."""
    return state.get("should_continue", False)
