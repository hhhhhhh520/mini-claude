"""Think node: Check iteration limits and add system prompt."""

from ._shared import (
    AgentState,
    StopReason,
    AIMessage,
    get_max_iterations,
    settings,
    trace_agent_node,
    logger,
)


async def think_node(state: AgentState) -> dict:
    """Think 节点：检查迭代限制，添加系统提示

    职责：
    1. 检查是否达到迭代上限
    2. 首次迭代时添加系统提示
    3. 首次迭代时重置错误状态（解决 checkpointer 状态累积问题）

    Returns:
        部分状态更新（LangGraph 自动合并）
    """
    with trace_agent_node("think", state["iteration"]) as span:
        iteration = state["iteration"]

        # 检查迭代限制
        max_iter = get_max_iterations(state)
        if iteration >= max_iter:
            logger.debug(
                "think_node: max iterations reached", iteration=iteration, max_iter=max_iter
            )
            if span:
                span.set_attribute("max_iterations_reached", True)
            return {
                "stop_reason": StopReason.MAX_ITERATIONS,
                "messages": [AIMessage(content="达到最大迭代次数，任务终止。")],
            }

        # 首次迭代：重置错误状态。
        # 注意：系统提示与 skills **不在这里写入 messages**——messages 是
        # `Annotated[List, add]` 累加语义，若在此返回「重排后的全量列表」会把
        # 用户消息复制一份、并把 SystemMessage 放到 HumanMessage 之后。
        # 系统提示改由 act 节点在每次 LLM 调用时前置（见 build_system_messages）。
        if iteration == 0:
            provider = settings.get_model_provider()

            if span:
                span.set_attribute("first_iteration", True)
                span.set_attribute("model_provider", provider.value)

            logger.debug("think_node: iteration 0, resetting error state")
            return {
                "messages": [],
                "iteration": 1,
                "stop_reason": StopReason.CONTINUE,
                "errors": [],  # 重置错误列表
                "retry_count": 0,  # 重置重试计数
            }

        if span:
            span.set_attribute("iteration", iteration + 1)
        logger.debug("think_node: iteration", iteration=iteration + 1, max_iter=max_iter)

        # 返回部分更新
        return {
            "iteration": iteration + 1,
            "stop_reason": StopReason.CONTINUE,
        }
