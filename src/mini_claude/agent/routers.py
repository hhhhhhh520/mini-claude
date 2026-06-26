"""Router functions for agent graph - 路由函数模块."""

from .state import AgentState, StopReason
from ..utils.logger import get_logger

logger = get_logger("mini_claude.agent.routers")


def route_after_observe(state: AgentState) -> str:
    """Observe 节点后的路由

    Returns:
        "reflect": 进入反思节点（复杂任务）
        "continue": 继续执行 check_completion
        "error": 进入错误处理
        "complete": 任务完成，结束
    """
    stop_reason = state.get("stop_reason", StopReason.CONTINUE)

    logger.debug("route_after_observe", stop_reason=str(stop_reason))

    if stop_reason == StopReason.ERROR:
        return "error"
    elif stop_reason == StopReason.IDLE_LOOP:
        # 空转视为完成（LLM 直接回复了，没有调用工具）
        return "complete"
    elif stop_reason == StopReason.TASK_COMPLETE:
        return "complete"
    elif stop_reason == StopReason.MAX_ITERATIONS:
        return "complete"
    elif stop_reason == StopReason.WAITING_CONFIRMATION:
        # 等待用户确认，停止执行
        return "complete"
    else:
        # 对于复杂任务，先进行反思（结果缓存到 state 避免重复分析）
        from .complexity import TaskComplexityAnalyzer, ComplexityLevel

        complexity_level = state.get("_complexity_level")
        if complexity_level is None:
            current_task = state.get("current_task", "")
            analyzer = TaskComplexityAnalyzer()
            complexity = analyzer.analyze(current_task)
            complexity_level = complexity.level
            # 缓存到 state（TypedDict 运行时不阻止额外 key）
            state["_complexity_level"] = complexity_level  # type: ignore[misc]
        if complexity_level == ComplexityLevel.COMPLEX:
            return "reflect"
        return "continue"


def route_after_reflect(state: AgentState) -> str:
    """Reflect 节点后的路由

    Returns:
        "continue": 继续执行 check_completion
    """
    logger.debug("route_after_reflect: proceeding to check_completion")
    return "continue"


def route_completion_check(state: AgentState) -> str:
    """完成检查后的路由

    Returns:
        "complete": 任务完成，结束
        "incomplete": 任务未完成，继续循环
        "retry": 需要重试
    """
    stop_reason = state.get("stop_reason", StopReason.CONTINUE)
    retry_count = state.get("retry_count", 0)

    logger.debug("route_completion_check", stop_reason=str(stop_reason), retry_count=retry_count)

    if stop_reason == StopReason.TASK_COMPLETE:
        return "complete"
    elif stop_reason == StopReason.MAX_ITERATIONS:
        return "complete"
    elif stop_reason == StopReason.ERROR and retry_count < 3:
        return "retry"
    elif stop_reason == StopReason.CONTINUE:
        return "incomplete"
    else:
        # 其他情况（如 IDLE_LOOP），视为完成
        return "complete"


def route_on_error(state: AgentState) -> str:
    """错误处理后的路由

    Returns:
        "retry": 重试执行
        "abort": 超过重试上限，终止
    """
    retry_count = state.get("retry_count", 0)

    logger.debug("route_on_error", retry_count=retry_count)

    if retry_count >= 3:
        return "abort"
    else:
        return "retry"
