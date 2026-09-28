"""Observe node: Observe results and decide next steps."""

from ._shared import (
    AgentState,
    StopReason,
    HumanMessage,
    AIMessage,
    ToolMessage,
    get_max_iterations,
    detect_project_type,
    check_project_completion,
    check_web_project_completion,
    check_backend_project_completion,
    settings,
    trace_agent_node,
    logger,
)

# 执行层捕获异常时使用的固定中文前缀（见 _act_helpers.py 的 except 分支）。
# 它们是本项目代码自己产生的，不是工具输出正文，因此可安全地作为错误信号。
_TOOL_EXCEPTION_MARKERS = (
    "文件系统错误",
    "参数错误",
    "执行超时",
    "执行失败",
    "被跳过",
)


def _is_tool_result_message(msg) -> bool:
    """判断一条消息是否是工具结果。

    ISSUE-026 起新协议下工具结果是 ``ToolMessage``；旧 checkpoint 里是
    带 name 的 ``HumanMessage``（兼容 /resume 恢复的历史会话）。
    """
    if isinstance(msg, ToolMessage):
        return True
    return isinstance(msg, HumanMessage) and getattr(msg, "name", None) and bool(msg.name)


def _is_tool_error_message(msg) -> bool:
    """结构化判断一条工具消息是否代表真正的工具错误.

    刻意不做「正文含某关键词」式的嗅探：
      a) ToolMessage.status == "error"：执行层统一标错（ISSUE-026 起的结构化信号）；
      b) 工具返回值本身以 Error 开头（工具层以字符串报告失败的约定）；
      c) 旧格式 "Tool {name} result: Error..."：只看包裹边界之后的起始，
         兼容 /resume 恢复的旧 checkpoint；
      d) 执行层捕获的异常：固定中文前缀出现在消息开头附近。
    """
    if isinstance(msg, ToolMessage):
        if msg.status == "error":
            return True
        content = str(msg.content)
        if content.lower().startswith("error"):
            return True
        return any(marker in content[:40] for marker in _TOOL_EXCEPTION_MARKERS)

    if not (isinstance(msg, HumanMessage) and getattr(msg, "name", None)):
        return False
    content = msg.content
    if content.startswith("Error"):
        return True
    result_prefix = f"Tool {msg.name} result: "
    if content.startswith(result_prefix):
        return content[len(result_prefix) :].lstrip().lower().startswith("error")
    head = content[:40]
    return any(marker in head for marker in _TOOL_EXCEPTION_MARKERS)


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
    with trace_agent_node("observe", state["iteration"]) as span:
        messages = list(state["messages"])
        iteration = state["iteration"]
        current_task = state["current_task"]

        logger.debug("observe_node: starting", iteration=iteration)

        if span:
            span.set_attribute("iteration", iteration)

        # 首先检查是否已经在等待确认状态（act_node 设置的）
        current_stop_reason = state.get("stop_reason", StopReason.CONTINUE)
        if current_stop_reason == StopReason.WAITING_CONFIRMATION:
            logger.debug("observe_node: preserving WAITING_CONFIRMATION state")
            if span:
                span.set_attribute("waiting_confirmation", True)
            return {}  # 不修改任何状态，保留 WAITING_CONFIRMATION

        # 检查迭代限制
        max_iter = get_max_iterations(state)
        if iteration >= max_iter:
            logger.debug("observe_node: max iterations reached")
            if span:
                span.set_attribute("stop_reason", "max_iterations")
            return {"stop_reason": StopReason.MAX_ITERATIONS}

        # 检查是否有工具错误。
        # 只信任结构化信号，绝不对正文做自然语言关键词匹配——否则含「失败/超时」
        # 字样的正常中文输出会被误判为 Agent 级错误，攻击者控制的文本也会被当成
        # 错误并在 handle_error 里被抬升为指令。三类结构化信号见 _is_tool_error_message。
        recent_errors = [
            msg.content
            for msg in messages[-5:]
            if _is_tool_result_message(msg) and _is_tool_error_message(msg)
        ]
        if recent_errors:
            logger.debug("observe_node: found tool errors", errors=recent_errors)
            if span:
                span.set_attribute("has_errors", True)
                span.set_attribute("error_count", len(recent_errors))
            return {
                "errors": recent_errors,  # 不累积，只记录当前错误
                "stop_reason": StopReason.ERROR,
            }

        # 检查是否有需要确认的安全提示（当作普通结果处理）
        has_confirmation_prompt = any(
            _is_tool_result_message(msg) and "requires confirmation" in msg.content.lower()
            for msg in messages[-3:]
        )
        if has_confirmation_prompt:
            logger.debug("observe_node: found confirmation prompt, treating as normal result")
            # 不设置 ERROR，让 LLM 处理

        # 检查是否有工具结果
        has_tool_result = any(_is_tool_result_message(msg) for msg in messages[-3:])

        if span:
            span.set_attribute("has_tool_result", has_tool_result)

        # 检查是否为多文件任务
        task_lower = current_task.lower()
        multi_file_keywords = [
            "开发",
            "创建",
            "生成",
            "网站",
            "前端",
            "项目",
            "web",
            "backend",
            "fastapi",
            "flask",
            "api",
        ]
        is_multi_file_task = any(kw in task_lower for kw in multi_file_keywords)

        if is_multi_file_task:
            workspace = settings.workspace_root

            # 检测项目类型并检查完成度
            project_type = detect_project_type(current_task)

            if project_type:
                completion = check_project_completion(workspace, project_type)
                logger.debug(
                    "observe_node: project completion check",
                    project_type=project_type,
                    complete=completion["complete"],
                )

                if span:
                    span.set_attribute("project_type", project_type)
                    span.set_attribute("project_complete", completion["complete"])

                if completion["complete"]:
                    logger.debug("observe_node: project complete")
                    if span:
                        span.set_attribute("stop_reason", "task_complete")
                    return {"stop_reason": StopReason.TASK_COMPLETE}
                elif completion["missing"]:
                    # 项目未完成，添加提醒
                    missing = completion["missing"]
                    reminder = f"项目文件不完整，缺少: {', '.join(missing)}。请使用 write_file 工具创建这些文件。"
                    logger.debug("observe_node: project incomplete", missing=missing)
                    return {
                        "messages": [HumanMessage(content=reminder)],
                        "stop_reason": StopReason.CONTINUE,
                    }
            else:
                # 未知项目类型，使用通用检查
                web_completion = check_web_project_completion(workspace)
                backend_completion = check_backend_project_completion(workspace)

                if web_completion["complete"] or backend_completion["complete"]:
                    logger.debug("observe_node: project complete (generic check)")
                    if span:
                        span.set_attribute("stop_reason", "task_complete")
                    return {"stop_reason": StopReason.TASK_COMPLETE}

        # 检查是否有工具结果
        if has_tool_result:
            logger.debug("observe_node: has tool results, continuing")

            if span:
                span.set_attribute("stop_reason", "continue")

            # 子代理模式：写入操作后停止（SubagentStop hook 可阻断收工，P5 对齐）
            if state.get("is_subagent", False):
                for msg in reversed(messages):
                    if _is_tool_result_message(msg):
                        if msg.name in ["write_file", "edit_file"]:
                            # SubagentStop hook：exit 2 / decision=block → 不收工，
                            # 原因作为消息喂回让子代理继续（受 max_iterations 兜底；
                            # hook 自身异常不阻断收工——和 Notification 同级纪律）
                            try:
                                from ...hooks.dispatcher import get_hook_dispatcher

                                (
                                    blocked,
                                    reason,
                                ) = await get_hook_dispatcher().dispatch_subagent_stop(
                                    agent_id=state.get("thread_id", ""),
                                    agent_task=state.get("current_task", ""),
                                    result_summary=str(msg.content)[:500],
                                    thread_id=state.get("thread_id", ""),
                                )
                            except Exception as hook_err:
                                logger.debug("subagent stop hook failed", error=str(hook_err))
                                blocked, reason = False, ""
                            if blocked:
                                logger.debug(
                                    "observe_node: subagent stop blocked by hook", reason=reason
                                )
                                if span:
                                    span.set_attribute("subagent_stop_blocked", True)
                                return {
                                    "messages": [
                                        HumanMessage(
                                            content=(
                                                f"SubagentStop hook 阻断收工，请继续完成任务：{reason}"
                                            ),
                                            name="subagent_stop_hook",
                                        )
                                    ],
                                    "stop_reason": StopReason.CONTINUE,
                                }
                            logger.debug("observe_node: subagent completed write operation")
                            if span:
                                span.set_attribute("stop_reason", "subagent_complete")
                            return {"stop_reason": StopReason.TASK_COMPLETE}
                        break

            return {"stop_reason": StopReason.CONTINUE}

        # 无工具结果 - 检查是否有 AI 文本回复
        has_ai_reply = any(
            isinstance(msg, AIMessage) and msg.content and len(msg.content.strip()) > 10
            for msg in messages[-3:]
        )

        if has_ai_reply:
            # AI 有实质性回复，可能是正在解释或规划，继续执行
            logger.debug("observe_node: AI has text reply, continuing")
            if span:
                span.set_attribute("stop_reason", "continue")
            return {"stop_reason": StopReason.CONTINUE}

        # 真正的空转 - 无工具结果且无 AI 回复
        logger.debug("observe_node: no tool results and no AI reply, idle loop")
        if span:
            span.set_attribute("stop_reason", "idle_loop")
        return {"stop_reason": StopReason.IDLE_LOOP}
