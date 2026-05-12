"""Observe node: Observe results and decide next steps."""

from ._shared import (
    AgentState,
    StopReason,
    HumanMessage,
    AIMessage,
    get_max_iterations,
    detect_project_type,
    check_project_completion,
    check_web_project_completion,
    check_backend_project_completion,
    settings,
    trace_agent_node,
    logger,
)


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

        # 检查是否有工具错误（排除需要确认的安全提示）
        # "requires confirmation" 是安全提示，不是真正的错误
        recent_errors = [
            msg.content
            for msg in messages[-5:]
            if isinstance(msg, HumanMessage)
            and hasattr(msg, "name")
            and "error:" in msg.content.lower()
            and "requires confirmation" not in msg.content.lower()  # 排除安全确认提示
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
            isinstance(msg, HumanMessage)
            and hasattr(msg, "name")
            and "requires confirmation" in msg.content.lower()
            for msg in messages[-3:]
        )
        if has_confirmation_prompt:
            logger.debug("observe_node: found confirmation prompt, treating as normal result")
            # 不设置 ERROR，让 LLM 处理

        # 检查是否有工具结果
        has_tool_result = any(
            isinstance(msg, HumanMessage) and hasattr(msg, "name") and msg.name
            for msg in messages[-3:]
        )

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

            # 子代理模式：写入操作后停止
            if state.get("is_subagent", False):
                for msg in reversed(messages):
                    if isinstance(msg, HumanMessage) and hasattr(msg, "name") and msg.name:
                        if msg.name in ["write_file", "edit_file"]:
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
