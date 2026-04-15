"""Agent graph nodes: Think, Plan, Act, Observe."""

import asyncio
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from .state import AgentState
from .subagent import subagent_manager, AgentStatus
from ..llm.provider import LLMProvider, convert_tools_to_litellm
from ..llm.prompts import get_system_prompt, get_planning_prompt
from ..tools import get_all_tools
from mini_claude.config.settings import settings, ModelProvider


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
    )


async def plan_node(state: AgentState) -> AgentState:
    """Plan node: Create execution plan."""
    messages = list(state["messages"])
    current_task = state["current_task"]
    iteration = state["iteration"]
    print(f"[DEBUG] plan_node received: messages count = {len(messages)}")

    # Skip detailed planning for simple conversational messages
    if iteration == 1:
        simple_indicators = ["你好", "hello", "hi", "介绍", "什么", "如何", "怎么", "为什么"]
        if any(ind in current_task.lower() for ind in simple_indicators) and len(current_task) < 100:
            print(f"[DEBUG] plan_node: simple query, skip detailed planning")
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
            )

    # Analyze the task and create a plan
    plan = None

    # Detect if task might need tools
    tool_keywords = {
        "文件": "可能需要使用文件读写工具",
        "读取": "需要使用 Read 工具",
        "写入": "需要使用 Write 工具",
        "执行": "可能需要使用 Bash 工具",
        "搜索": "可能需要使用 Grep 或 Glob 工具",
        "目录": "可能需要使用 Glob 或 Bash ls 工具",
        "代码": "可能需要读取或编辑代码文件",
        "查找": "需要使用搜索工具",
        "修改": "需要使用 Edit 工具",
        "创建": "可能需要使用 Write 工具",
        "删除": "可能需要使用 Bash 工具",
    }

    detected_actions = []
    for keyword, action in tool_keywords.items():
        if keyword in current_task:
            detected_actions.append(action)

    if detected_actions:
        plan = f"执行计划:\n" + "\n".join(f"- {action}" for action in detected_actions)
        print(f"[DEBUG] plan_node: created plan: {plan}")
    else:
        plan = "分析用户请求并直接响应"
        print(f"[DEBUG] plan_node: no tools needed, direct response")

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
    )


async def act_node(state: AgentState) -> AgentState:
    """Act node: Execute tools based on plan."""
    import json
    messages = list(state["messages"])
    print(f"[DEBUG] act_node received: messages count = {len(messages)}")

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
        response = await llm_provider.chat(
            messages=litellm_messages,
            tools=litellm_tools if litellm_tools else None,
            tool_choice="auto" if litellm_tools else None,
        )

        message = response.choices[0].message

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
        print(f"[DEBUG] act_node: tool_calls={tool_calls}")

        # Add AI message to history
        ai_message = AIMessage(
            content=message.content or "",
            tool_calls=tool_calls,
        )
        messages = messages + [ai_message]

        # Execute tools immediately if there are tool calls
        if tool_calls:
            from ..tools import execute_tool

            print(f"[DEBUG] act_node: executing {len(tool_calls)} tool calls")
            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Parse args if it's a string
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                try:
                    print(f"[DEBUG] Executing tool [{i+1}/{len(tool_calls)}]: {tool_name} with args: {tool_args}")
                    result = await execute_tool(tool_name, tool_args)
                    print(f"[DEBUG] Tool result: {result[:200] if result else 'None'}...")

                    # Add tool result message
                    messages.append(HumanMessage(
                        content=f"Tool {tool_name} result: {result}",
                        name=tool_name,
                    ))

                except Exception as e:
                    import traceback
                    print(f"[DEBUG] Tool error: {e}")
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    messages.append(HumanMessage(
                        content=f"Tool {tool_name} error: {e}",
                        name=tool_name,
                    ))

        print(f"[DEBUG] act_node returning: messages count = {len(messages)}, had tool_calls = {bool(tool_calls)}")

        # Determine if we should continue based on tool calls and iteration limit
        # If we had tool calls, we need to continue to let the LLM process results
        max_iter = settings.max_subagent_iterations if state.get("is_subagent") else settings.max_iterations
        should_continue = bool(tool_calls) and state["iteration"] < max_iter

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
        )

    except Exception as e:
        import traceback
        print(f"[DEBUG] act_node EXCEPTION: {e}")
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
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
        )


async def observe_node(state: AgentState) -> AgentState:
    """Observe node: Process tool results and decide next steps."""
    messages = list(state["messages"])
    iteration = state["iteration"]

    print(f"[DEBUG] observe_node: iteration={iteration}, messages count = {len(messages)}")

    # Check iteration limit first (use subagent limit if is_subagent)
    max_iter = settings.max_subagent_iterations if state.get("is_subagent") else settings.max_iterations
    if iteration >= max_iter:
        print(f"[DEBUG] observe_node: max iterations reached")
        should_continue = False
    else:
        # Check if we just executed tools - if so, continue to let LLM process results
        # Look for tool results (HumanMessage with name attribute) after the last AIMessage
        has_tool_result = False
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                has_tool_result = True
                break
            if isinstance(msg, AIMessage):
                break

        if has_tool_result:
            # We have tool results, need to continue so LLM can process them
            print(f"[DEBUG] observe_node: tool results found, continuing to process")
            should_continue = True
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
                            print(f"[DEBUG] observe_node: found unexecuted tool_calls")
                            should_continue = True
                    break

    print(f"[DEBUG] observe_node: should_continue = {should_continue}")

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
    )


def should_continue_router(state: AgentState) -> bool:
    """Router function to determine if we should continue."""
    return state.get("should_continue", False)
