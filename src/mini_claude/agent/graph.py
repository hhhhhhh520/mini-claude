"""LangGraph agent graph definition - Refactored version."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes import (
    think_node,
    plan_node,
    act_node,
    observe_node,
    check_completion_node,
    handle_error_node,
    retry_node,
)
from .routers import (
    route_after_observe,
    route_completion_check,
    route_on_error,
)


def build_agent_graph(checkpointer_path: str = "checkpoints.db"):
    """Build the main agent graph - 改进版架构

    Graph structure (7 nodes):
        THINK → PLAN → ACT → OBSERVE → CHECK_COMPLETION → (循环/END)
                                          ↓
                                    HANDLE_ERROR → RETRY → ACT

    新增功能：
    - 错误恢复机制（handle_error + retry）
    - 任务完成检查（check_completion）
    - 统一的路由函数
    """
    # Create the graph
    graph = StateGraph(AgentState)

    # 核心节点
    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)

    # 新增节点
    graph.add_node("check_completion", check_completion_node)
    graph.add_node("handle_error", handle_error_node)
    graph.add_node("retry", retry_node)

    # Set entry point
    graph.set_entry_point("think")

    # 主流程边
    graph.add_edge("think", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "observe")

    # 条件路由：observe 后
    graph.add_conditional_edges(
        "observe",
        route_after_observe,
        {
            "continue": "check_completion",  # 继续检查完成度
            "error": "handle_error",         # 错误处理
            "complete": END,                 # 任务完成
        }
    )

    # 条件路由：check_completion 后
    graph.add_conditional_edges(
        "check_completion",
        route_completion_check,
        {
            "complete": END,        # 任务完成
            "incomplete": "think",  # 继续循环
            "retry": "retry",       # 重试
        }
    )

    # 条件路由：handle_error 后
    graph.add_conditional_edges(
        "handle_error",
        route_on_error,
        {
            "retry": "retry",   # 重试
            "abort": END,       # 终止
        }
    )

    # 重试后回到 act
    graph.add_edge("retry", "act")

    # Enable checkpointer for state persistence
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def build_agent_graph_simple():
    """Build simplified agent graph (4 nodes, for testing).

    简化版图结构（用于测试）：
        THINK → PLAN → ACT → OBSERVE → (循环/END)
    """
    from .nodes import should_continue_router

    graph = StateGraph(AgentState)

    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)

    graph.set_entry_point("think")
    graph.add_edge("think", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "observe")
    graph.add_conditional_edges(
        "observe",
        should_continue_router,
        {True: "think", False: END}
    )

    return graph.compile()


def build_agent_graph_no_checkpoint():
    """Build agent graph without checkpointer (for testing)."""
    graph = StateGraph(AgentState)

    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)
    graph.add_node("check_completion", check_completion_node)
    graph.add_node("handle_error", handle_error_node)
    graph.add_node("retry", retry_node)

    graph.set_entry_point("think")
    graph.add_edge("think", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "observe")

    graph.add_conditional_edges(
        "observe",
        route_after_observe,
        {"continue": "check_completion", "error": "handle_error", "complete": END}
    )
    graph.add_conditional_edges(
        "check_completion",
        route_completion_check,
        {"complete": END, "incomplete": "think", "retry": "retry"}
    )
    graph.add_conditional_edges(
        "handle_error",
        route_on_error,
        {"retry": "retry", "abort": END}
    )
    graph.add_edge("retry", "act")

    return graph.compile()


# Default recursion limit for graph execution
DEFAULT_RECURSION_LIMIT = 50


# Default graph instance
_agent_graph = None


def get_agent_graph():
    """Get or create the default agent graph."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
