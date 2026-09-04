"""LangGraph agent graph definition - Refactored version."""

import logging

import aiosqlite
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .state import AgentState
from .nodes import (
    think_node,
    plan_node,
    act_node,
    observe_node,
    reflect_node,
    check_completion_node,
    handle_error_node,
    retry_node,
    should_continue_router,
)
from .routers import (
    route_after_observe,
    route_after_reflect,
    route_completion_check,
    route_on_error,
)

logger = logging.getLogger(__name__)

# build_agent_graph() 建立的 SQLite 连接，退出时由
# close_checkpoint_connections() 统一关闭。
_checkpoint_conns: list = []


def build_agent_graph(checkpointer_path: str = "sessions.db"):
    """Build the main agent graph - 改进版架构

    返回的图持有 SQLite checkpoint 连接。aiosqlite 的 worker 线程**不是 daemon**，
    且本模块的登记表会强引用连接，所以未关闭时解释器退出会挂住（不是只泄漏 fd）：
    调用方退出时必须 await close_checkpoint_connections()。

    必须在运行中的事件循环里调用（见下方 checkpointer 注释）。

    Graph structure (8 nodes):
        THINK → PLAN → ACT → OBSERVE → REFLECT → CHECK_COMPLETION → (循环/END)
                                          ↓
                                    HANDLE_ERROR → RETRY → ACT

    新增功能：
    - 反思机制（reflect_node，仅复杂任务）
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
    graph.add_node("reflect", reflect_node)
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
            "reflect": "reflect",  # 复杂任务：先反思
            "continue": "check_completion",  # 简单任务：直接检查完成度
            "error": "handle_error",  # 错误处理
            "complete": END,  # 任务完成
        },
    )

    # Reflect 后进入 check_completion
    graph.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {
            "continue": "check_completion",
        },
    )

    # 条件路由：check_completion 后
    graph.add_conditional_edges(
        "check_completion",
        route_completion_check,
        {
            "complete": END,  # 任务完成
            "incomplete": "think",  # 继续循环
            "retry": "retry",  # 重试
        },
    )

    # 条件路由：handle_error 后
    graph.add_conditional_edges(
        "handle_error",
        route_on_error,
        {
            "retry": "retry",  # 重试
            "abort": END,  # 终止
        },
    )

    # 重试后回到 act
    graph.add_edge("retry", "act")

    # Enable checkpointer for state persistence (SQLite-backed).
    #
    # 为什么不能用 from_conn_string()：它被 @classmethod @asynccontextmanager
    # 双重装饰，直接调用返回的是 _AsyncGeneratorContextManager 而不是 saver。
    # 实测 langgraph 1.1.9 的 compile() 会当场校验并抛
    #   TypeError: Invalid checkpointer provided ... Received
    #   _AsyncGeneratorContextManager
    # （pyproject 里 langgraph>=0.2.0 无上界，故具体失败形态随版本漂移。）
    #
    # 为什么可以直接构造：AsyncSqliteSaver 的建表 setup() 在 aget_tuple/alist/
    # aput/aput_writes/aget_delta_channel_history 里都会惰性 await，因此不需要
    # 把调用方改造成 async with。
    #
    # 新前提：AsyncSqliteSaver.__init__ 会执行 asyncio.get_running_loop()，
    # 所以 build_agent_graph() **只能在运行中的事件循环里调用**；同步上下文调用
    # 抛 RuntimeError: no running event loop。
    # 连接登记在最后一步——登记前任何构造失败都不会留下孤儿登记。
    conn = aiosqlite.connect(checkpointer_path)
    compiled = graph.compile(checkpointer=AsyncSqliteSaver(conn))
    _checkpoint_conns.append(conn)
    return compiled


def build_agent_graph_simple():
    """Build simplified agent graph (4 nodes, for testing).

    简化版图结构（用于测试）：
        THINK → PLAN → ACT → OBSERVE → (循环/END)
    """
    graph = StateGraph(AgentState)

    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)

    graph.set_entry_point("think")
    graph.add_edge("think", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "observe")
    graph.add_conditional_edges("observe", should_continue_router, {True: "think", False: END})

    return graph.compile()


def build_agent_graph_no_checkpoint():
    """Build agent graph without checkpointer (for testing)."""
    graph = StateGraph(AgentState)

    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)
    graph.add_node("reflect", reflect_node)
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
        {
            "reflect": "reflect",
            "continue": "check_completion",
            "error": "handle_error",
            "complete": END,
        },
    )
    graph.add_conditional_edges("reflect", route_after_reflect, {"continue": "check_completion"})
    graph.add_conditional_edges(
        "check_completion",
        route_completion_check,
        {"complete": END, "incomplete": "think", "retry": "retry"},
    )
    graph.add_conditional_edges("handle_error", route_on_error, {"retry": "retry", "abort": END})
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
        # 必须与 cli/repl.py 的 _check_previous_session() 用同一个库路径，
        # 否则「发现上次未完成的会话」提示读的表和图写的表会分叉。
        from mini_claude.config.settings import settings

        _agent_graph = build_agent_graph(checkpointer_path=settings.session_db_path)
    return _agent_graph


async def close_checkpoint_connections() -> int:
    """关闭所有由 build_agent_graph() 建立的 SQLite 连接，并丢弃图单例。

    Returns:
        实际关闭的连接数。
    """
    global _agent_graph, _checkpoint_conns
    conns, _checkpoint_conns = _checkpoint_conns, []
    _agent_graph = None
    closed = 0
    for conn in conns:
        try:
            await conn.close()
            closed += 1
        except Exception as exc:  # 退出路径上单个连接失败不应中断清理，但必须可见
            logger.warning("checkpoint connection close failed: %s: %s", type(exc).__name__, exc)
    return closed
