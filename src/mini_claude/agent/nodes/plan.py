"""Plan node: Generate execution plan."""

from ._shared import (
    AgentState,
    AIMessage,
    trace_agent_node,
    logger,
)


def _serialize_plan(plan) -> dict:
    """Serialize ExecutionPlan to dict for state storage."""
    return {
        "steps": [
            {
                "id": step.id,
                "description": step.description,
                "status": step.status.value if hasattr(step.status, 'value') else str(step.status),
                "dependencies": step.dependencies,
                "details": step.details,
            }
            for step in plan.steps
        ],
        "total_steps": plan.total_steps,
        "strategy": plan.strategy,
        "estimated_time": plan.estimated_time,
        "complexity_score": plan.complexity_score,
    }


async def plan_node(state: AgentState) -> dict:
    """Plan 节点：生成执行计划

    职责：
    1. 保留核心关键词快速路径
    2. 复杂场景用 LLM 判断是否需要工具
    3. 对复杂任务显示执行计划可视化

    Returns:
        部分状态更新
    """
    with trace_agent_node("plan", state["iteration"]) as span:
        current_task = state["current_task"]
        iteration = state["iteration"]

        logger.debug("plan_node: starting", iteration=iteration, task_preview=current_task[:50])

        if span:
            span.set_attribute("task_length", len(current_task))

        # 首次迭代：检查是否为简单对话
        if iteration == 1:
            simple_indicators = ["你好", "hello", "hi", "介绍", "什么", "如何", "怎么", "为什么"]
            if any(ind in current_task.lower() for ind in simple_indicators) and len(current_task) < 100:
                logger.debug("plan_node: simple query, skip detailed planning")
                if span:
                    span.set_attribute("query_type", "simple")
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
            "看看": "read_file",  # 新增
            "读": "read_file",    # 新增
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

        if span:
            span.set_attribute("detected_tools", ",".join(detected_tools) if detected_tools else "none")

        # 复杂任务可视化（仅首次迭代且启用时）
        # 放宽条件：只要有工具关键词就显示计划
        if iteration == 1 and detected_tools:
            try:
                from ..complexity import TaskComplexityAnalyzer
                from ...cli.plan_display import PlanVisualizer, create_plan_from_analysis

                analyzer = TaskComplexityAnalyzer()
                complexity = analyzer.analyze(current_task, {"file_count": len(detected_tools)})

                # 所有任务都显示可视化（不再限制 score >= 40）
                visualizer = PlanVisualizer()
                plan = create_plan_from_analysis(current_task, complexity)
                visualizer.display_plan(plan, complexity)
                logger.debug("plan_node: plan visualization displayed", complexity=complexity.level.value, score=complexity.score)
                if span:
                    span.set_attribute("complexity_score", complexity.score)
                    span.set_attribute("complexity_level", complexity.level.value)

                # 将执行计划存入状态（关键修改：不只是显示）
                serialized_plan = _serialize_plan(plan)
                logger.debug("plan_node: storing execution plan in state", steps=len(plan.steps))

                plan_msg = f"执行计划：使用 {', '.join(detected_tools)} 工具完成任务"
                return {
                    "messages": [AIMessage(content=plan_msg)],
                    "execution_plan": serialized_plan,
                    "current_step_index": 0,
                }
            except Exception as e:
                logger.warning("plan_node: visualization failed", error=str(e), exc_info=True)

        if detected_tools:
            plan_msg = f"执行计划：使用 {', '.join(detected_tools)} 工具完成任务"
            logger.debug("plan_node: detected tools", tools=detected_tools)
            return {
                "messages": [AIMessage(content=plan_msg)],
            }

        # 无明显工具需求，让 LLM 自己判断
        logger.debug("plan_node: no obvious tools, LLM will decide")
        return {
            "messages": [],
        }
