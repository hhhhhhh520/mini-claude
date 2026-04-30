"""Agent graph nodes: Think, Plan, Act, Observe - Refactored version."""

import asyncio
import sys
import os
import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from .state import AgentState, StopReason, get_max_iterations
from .subagent import subagent_manager, AgentStatus
from .completion_config import (
    detect_project_type,
    check_project_completion,
    check_web_project_completion,
    check_backend_project_completion,
)
from ..llm.provider import LLMProvider, convert_tools_to_litellm
from ..llm.prompts import get_system_prompt, get_planning_prompt
from ..tools import get_all_tools
from mini_claude.config.settings import settings, ModelProvider
from ..utils.safety import PathConfirmationRequired, approve_path, is_path_approved


# Fix Windows console encoding for debug output
def safe_print(msg: str):
    """Print safely handling encoding issues on Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# Initialize LLM provider
llm_provider = LLMProvider()


# =============================================================================
# THINK NODE
# =============================================================================

async def think_node(state: AgentState) -> dict:
    """Think 节点：检查迭代限制，添加系统提示

    职责：
    1. 检查是否达到迭代上限
    2. 首次迭代时添加系统提示
    3. 首次迭代时重置错误状态（解决 checkpointer 状态累积问题）

    Returns:
        部分状态更新（LangGraph 自动合并）
    """
    messages = list(state["messages"])
    iteration = state["iteration"]

    # 检查迭代限制
    max_iter = get_max_iterations(state)
    if iteration >= max_iter:
        safe_print(f"[DEBUG] think_node: max iterations reached ({iteration}/{max_iter})")
        return {
            "stop_reason": StopReason.MAX_ITERATIONS,
            "messages": [AIMessage(content="达到最大迭代次数，任务终止。")],
        }

    # 首次迭代：添加系统提示 + 重置错误状态
    if iteration == 0:
        provider = settings.get_model_provider()
        system_prompt = get_system_prompt(provider)
        messages = [SystemMessage(content=system_prompt)] + messages

        safe_print(f"[DEBUG] think_node: iteration 0, resetting error state")
        return {
            "messages": messages,
            "iteration": 1,
            "stop_reason": StopReason.CONTINUE,
            "errors": [],        # 重置错误列表
            "retry_count": 0,    # 重置重试计数
        }

    safe_print(f"[DEBUG] think_node: iteration {iteration + 1}/{max_iter}")

    # 返回部分更新
    return {
        "iteration": iteration + 1,
        "stop_reason": StopReason.CONTINUE,
    }


# =============================================================================
# PLAN NODE
# =============================================================================

async def plan_node(state: AgentState) -> dict:
    """Plan 节点：生成执行计划

    职责：
    1. 保留核心关键词快速路径
    2. 复杂场景用 LLM 判断是否需要工具

    Returns:
        部分状态更新
    """
    messages = list(state["messages"])
    current_task = state["current_task"]
    iteration = state["iteration"]

    safe_print(f"[DEBUG] plan_node: iteration={iteration}, task={current_task[:50]}...")

    # 首次迭代：检查是否为简单对话
    if iteration == 1:
        simple_indicators = ["你好", "hello", "hi", "介绍", "什么", "如何", "怎么", "为什么"]
        if any(ind in current_task.lower() for ind in simple_indicators) and len(current_task) < 100:
            safe_print(f"[DEBUG] plan_node: simple query, skip detailed planning")
            return {
                "messages": [AIMessage(content="直接回复用户问题")],
            }

    # 核心关键词快速路径（保留，避免不必要的 LLM 调用）
    task_lower = current_task.lower()
    tool_keywords = {
        "创建": "write_file",
        "开发": "write_file",
        "写": "write_file",
        "生成": "write_file",
        "读取": "read_file",
        "查看": "read_file",
        "修改": "edit_file",
        "编辑": "edit_file",
        "删除": "run_command",
        "执行": "run_command",
        "搜索": "search_files",
        "查找": "search_content",
        "目录": "list_dir",
        "网站": "write_file",
        "网页": "write_file",
        "html": "write_file",
        "前端": "write_file",
        "后端": "write_file",
        "api": "write_file",
        "fastapi": "write_file",
        "flask": "write_file",
    }

    detected_tools = []
    for keyword, tool_name in tool_keywords.items():
        if keyword in task_lower:
            if tool_name not in detected_tools:
                detected_tools.append(tool_name)

    if detected_tools:
        plan_msg = f"执行计划：使用 {', '.join(detected_tools)} 工具完成任务"
        safe_print(f"[DEBUG] plan_node: detected tools: {detected_tools}")
        return {
            "messages": [AIMessage(content=plan_msg)],
        }

    # 无明显工具需求，让 LLM 自己判断
    safe_print(f"[DEBUG] plan_node: no obvious tools, LLM will decide")
    return {
        "messages": [],
    }


# =============================================================================
# ACT NODE
# =============================================================================

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
    messages = list(state["messages"])
    safe_print(f"[DEBUG] act_node: messages count = {len(messages)}")

    # 获取可用工具
    tools = get_all_tools()
    allowed_tools = state.get("allowed_tools")
    if allowed_tools:
        tools = [t for t in tools if t.get("name") in allowed_tools]
    litellm_tools = convert_tools_to_litellm(tools)

    # 转换消息格式
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
        # 使用流式输出（非子代理模式）
        use_streaming = settings.streaming_enabled and not state.get("is_subagent", False)

        if use_streaming:
            from ..cli.display import display

            def stream_callback(token: str):
                display.stream_token(token)

            def tool_stream_callback(event_type: str, data: str):
                if event_type == "name":
                    display.show_tool_call_start(data)
                elif event_type == "args":
                    display.stream_tool_args(data)

            result = await llm_provider.chat_stream_with_tools(
                messages=litellm_messages,
                tools=litellm_tools if litellm_tools else None,
                tool_choice="auto",
                stream_callback=stream_callback,
                tool_stream_callback=tool_stream_callback,
            )

            content = result.get("content", "")
            raw_tool_calls = result.get("tool_calls")
            display.end_stream()
        else:
            response = await llm_provider.chat(
                messages=litellm_messages,
                tools=litellm_tools if litellm_tools else None,
                tool_choice="auto",
            )
            message = response.choices[0].message
            content = message.content or ""
            raw_tool_calls = message.tool_calls if hasattr(message, 'tool_calls') else None

        # 解析工具调用
        tool_calls = []
        if raw_tool_calls:
            for tc in raw_tool_calls:
                args = tc.get("arguments", "{}") if isinstance(tc, dict) else tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                name = tc.get("name", "") if isinstance(tc, dict) else tc.function.name
                if not name:
                    continue

                tool_calls.append({
                    "id": tc.get("id", "") if isinstance(tc, dict) else tc.id,
                    "name": name,
                    "args": args,
                })

        safe_print(f"[DEBUG] act_node: tool_calls={tool_calls}")

        # 构建 AI 消息
        ai_message = AIMessage(content=content or "", tool_calls=tool_calls)
        new_messages = [ai_message]

        # 执行工具
        if tool_calls:
            from ..tools import execute_tool

            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                # 验证必需参数
                if tool_name in ["write_file", "edit_file"]:
                    if not tool_args.get("path"):
                        error_msg = f"Error: Tool {tool_name} requires 'path' argument"
                        safe_print(f"[DEBUG] {error_msg}")
                        new_messages.append(HumanMessage(content=error_msg, name=tool_name))
                        continue
                    if tool_name == "write_file" and not tool_args.get("content"):
                        error_msg = f"Error: Tool write_file requires 'content' argument"
                        safe_print(f"[DEBUG] {error_msg}")
                        new_messages.append(HumanMessage(content=error_msg, name=tool_name))
                        continue

                try:
                    safe_print(f"[DEBUG] Executing tool [{i+1}/{len(tool_calls)}]: {tool_name}")
                    result = await execute_tool(tool_name, tool_args)
                    safe_print(f"[DEBUG] Tool result: {result[:200] if result else 'None'}...")
                    new_messages.append(HumanMessage(
                        content=f"Tool {tool_name} result: {result}",
                        name=tool_name,
                    ))
                except PathConfirmationRequired as e:
                    # Path requires user confirmation - 停止执行，等待用户确认
                    safe_print(f"[DEBUG] Path confirmation required: {e.path}")
                    new_messages.append(HumanMessage(
                        content=f"⚠️ 路径确认请求：{e.path}\n\n原因：{e.reason}\n\n请回复 'yes' 或 'y' 确认访问此路径，或提供其他路径。",
                        name=tool_name,
                    ))
                    # 设置特殊状态，让图停止并等待用户输入
                    return {
                        "messages": new_messages,
                        "stop_reason": StopReason.WAITING_CONFIRMATION,
                        "pending_confirmation_path": e.path,  # 记录待确认的路径
                    }
                except Exception as e:
                    import traceback
                    safe_print(f"[DEBUG] Tool error: {e}")
                    safe_print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    new_messages.append(HumanMessage(
                        content=f"Tool {tool_name} error: {e}",
                        name=tool_name,
                    ))

        safe_print(f"[DEBUG] act_node: returning {len(new_messages)} messages")

        return {
            "messages": new_messages,
        }

    except Exception as e:
        import traceback
        safe_print(f"[DEBUG] act_node EXCEPTION: {e}")
        safe_print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return {
            "messages": [AIMessage(content=f"执行出错：{e}")],
            "errors": [f"Act error: {e}"],
            "stop_reason": StopReason.ERROR,
        }


# =============================================================================
# OBSERVE NODE
# =============================================================================

async def observe_node(state: AgentState) -> dict:
    """Observe 节点：观察结果，判断下一步

    职责：
    1. 检查是否有工具结果
    2. 检查项目完成度（针对多文件任务）
    3. 检测空转循环
    4. 设置 stop_reason

    Returns:
        部分状态更新
    """
    messages = list(state["messages"])
    iteration = state["iteration"]
    current_task = state["current_task"]

    safe_print(f"[DEBUG] observe_node: iteration={iteration}")

    # 首先检查是否已经在等待确认状态（act_node 设置的）
    current_stop_reason = state.get("stop_reason", StopReason.CONTINUE)
    if current_stop_reason == StopReason.WAITING_CONFIRMATION:
        safe_print(f"[DEBUG] observe_node: preserving WAITING_CONFIRMATION state")
        return {}  # 不修改任何状态，保留 WAITING_CONFIRMATION

    # 检查迭代限制
    max_iter = get_max_iterations(state)
    if iteration >= max_iter:
        safe_print(f"[DEBUG] observe_node: max iterations reached")
        return {"stop_reason": StopReason.MAX_ITERATIONS}

    # 检查是否有工具错误（排除需要确认的安全提示）
    # "requires confirmation" 是安全提示，不是真正的错误
    recent_errors = [
        msg.content for msg in messages[-5:]
        if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and "error:" in msg.content.lower()
        and "requires confirmation" not in msg.content.lower()  # 排除安全确认提示
    ]
    if recent_errors:
        safe_print(f"[DEBUG] observe_node: found tool errors: {recent_errors}")
        return {
            "errors": recent_errors,  # 不累积，只记录当前错误
            "stop_reason": StopReason.ERROR,
        }

    # 检查是否有需要确认的安全提示（当作普通结果处理）
    has_confirmation_prompt = any(
        isinstance(msg, HumanMessage) and hasattr(msg, 'name') and "requires confirmation" in msg.content.lower()
        for msg in messages[-3:]
    )
    if has_confirmation_prompt:
        safe_print(f"[DEBUG] observe_node: found confirmation prompt, treating as normal result")
        # 不设置 ERROR，让 LLM 处理

    # 检查是否有工具结果
    has_tool_result = any(
        isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name
        for msg in messages[-3:]
    )

    # 检查是否为多文件任务
    task_lower = current_task.lower()
    multi_file_keywords = ["开发", "创建", "生成", "网站", "前端", "项目", "web", "backend", "fastapi", "flask", "api"]
    is_multi_file_task = any(kw in task_lower for kw in multi_file_keywords)

    if is_multi_file_task:
        workspace = settings.workspace_root

        # 检测项目类型并检查完成度
        project_type = detect_project_type(current_task)

        if project_type:
            completion = check_project_completion(workspace, project_type)
            safe_print(f"[DEBUG] observe_node: project_type={project_type}, complete={completion['complete']}")

            if completion["complete"]:
                safe_print(f"[DEBUG] observe_node: project complete")
                return {"stop_reason": StopReason.TASK_COMPLETE}
            elif completion["missing"]:
                # 项目未完成，添加提醒
                missing = completion["missing"]
                reminder = f"项目文件不完整，缺少: {', '.join(missing)}。请使用 write_file 工具创建这些文件。"
                safe_print(f"[DEBUG] observe_node: project incomplete, missing: {missing}")
                return {
                    "messages": [HumanMessage(content=reminder)],
                    "stop_reason": StopReason.CONTINUE,
                }
        else:
            # 未知项目类型，使用通用检查
            web_completion = check_web_project_completion(workspace)
            backend_completion = check_backend_project_completion(workspace)

            if web_completion["complete"] or backend_completion["complete"]:
                safe_print(f"[DEBUG] observe_node: project complete (generic check)")
                return {"stop_reason": StopReason.TASK_COMPLETE}

    # 检查是否有工具结果
    if has_tool_result:
        safe_print(f"[DEBUG] observe_node: has tool results, continuing")

        # 子代理模式：写入操作后停止
        if state.get("is_subagent", False):
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                    if msg.name in ['write_file', 'edit_file']:
                        safe_print(f"[DEBUG] observe_node: subagent completed write operation")
                        return {"stop_reason": StopReason.TASK_COMPLETE}
                    break

        return {"stop_reason": StopReason.CONTINUE}

    # 无工具结果 - 可能是空转
    safe_print(f"[DEBUG] observe_node: no tool results, idle loop")
    return {"stop_reason": StopReason.IDLE_LOOP}


# =============================================================================
# CHECK COMPLETION NODE
# =============================================================================

async def check_completion_node(state: AgentState) -> dict:
    """检查任务完成度节点

    职责：
    使用 LLM 判断任务是否真正完成

    注意：只在检测到可能完成时调用，避免额外 LLM 开销
    """
    current_task = state["current_task"]
    messages = state["messages"]

    # 构建检查提示 - 更明确的判断标准
    recent_messages = messages[-10:]
    messages_text = "\n".join([
        f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content[:300]}..."
        for m in recent_messages if m.content
    ])

    completion_prompt = f"""判断以下任务是否已完成。

原始任务：{current_task}

最近的对话和工具结果：
{messages_text}

判断标准：
1. 如果任务要求"运行"或"执行"文件，必须看到实际运行结果（不仅仅是读取文件）
2. 如果任务要求"创建"或"生成"文件，必须看到文件创建成功的确认
3. 如果任务要求"修改"或"编辑"文件，必须看到修改成功的确认
4. 如果任务是"查看文件夹内容"或"列出目录"，必须明确告知用户文件夹内容（包括是否为空）
5. 如果任务是对话类问题（如"介绍"、"解释"），有回答就算完成

重要：
- 如果任务是查看文件夹，必须报告文件夹是否为空，不能只说"执行成功"
- 空文件夹也是有效结果，但必须明确告知用户"这是一个空文件夹"

请回答以下之一：
- COMPLETE: 任务已完成（满足上述标准，且结果已明确告知用户）
- INCOMPLETE: 任务未完成（还需要继续执行或需要向用户报告结果）

只回答 COMPLETE 或 INCOMPLETE，不要解释。"""

    try:
        response = await llm_provider.chat(
            messages=[{"role": "user", "content": completion_prompt}],
            temperature=0,
        )
        answer = response.choices[0].message.content.strip().upper()

        safe_print(f"[DEBUG] check_completion_node: LLM answer = {answer}")

        # 注意：必须先检查 INCOMPLETE，因为 "COMPLETE" in "INCOMPLETE" 为 True
        if answer == "INCOMPLETE" or answer.startswith("INCOMPLETE"):
            return {"stop_reason": StopReason.CONTINUE}
        elif "COMPLETE" in answer:
            return {"stop_reason": StopReason.TASK_COMPLETE}
        else:
            return {"stop_reason": StopReason.CONTINUE}

    except Exception as e:
        safe_print(f"[DEBUG] check_completion_node error: {e}")
        # 出错时默认继续
        return {"stop_reason": StopReason.CONTINUE}


# =============================================================================
# HANDLE ERROR NODE
# =============================================================================

async def handle_error_node(state: AgentState) -> dict:
    """错误处理节点

    职责：
    1. 检查重试次数
    2. 生成修复建议
    """
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)

    safe_print(f"[DEBUG] handle_error_node: retry_count={retry_count}, errors={len(errors)}")

    if retry_count >= 3:
        error_msg = errors[-1] if errors else "多次重试失败"
        return {
            "messages": [AIMessage(content=f"多次重试失败，错误：{error_msg}")],
            "stop_reason": StopReason.ERROR,
        }

    # 生成修复建议
    error_msg = errors[-1] if errors else "未知错误"
    return {
        "messages": [HumanMessage(content=f"上一步出错：{error_msg}\n\n请尝试修复或使用其他方法完成任务。")],
        "retry_count": retry_count + 1,
    }


# =============================================================================
# RETRY NODE
# =============================================================================

async def retry_node(state: AgentState) -> dict:
    """重试节点

    职责：
    准备重新执行
    """
    safe_print(f"[DEBUG] retry_node: preparing for retry")

    return {
        "messages": [HumanMessage(content="请重新尝试执行任务。")],
    }


# =============================================================================
# ROUTER FUNCTION (保留兼容)
# =============================================================================

def should_continue_router(state: AgentState) -> bool:
    """路由函数：判断是否继续（保留兼容旧代码）"""
    stop_reason = state.get("stop_reason", StopReason.CONTINUE)
    return stop_reason == StopReason.CONTINUE
