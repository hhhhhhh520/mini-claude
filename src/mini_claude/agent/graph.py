"""LangGraph agent graph definition."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes import (
    think_node,
    plan_node,
    act_node,
    observe_node,
    should_continue_router,
)


def build_agent_graph(checkpointer_path: str = "checkpoints.db"):
    """Build the main agent graph.

    Graph structure:
        THINK → PLAN → ACT → OBSERVE → (loop back to THINK or END)
    """
    # Create the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("think", think_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)

    # Set entry point
    graph.set_entry_point("think")

    # Add edges
    graph.add_edge("think", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "observe")

    # Add conditional edge from observe
    graph.add_conditional_edges(
        "observe",
        should_continue_router,
        {
            True: "think",   # Continue the loop
            False: END,      # End execution
        }
    )

    # Enable checkpointer for state persistence
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def build_agent_graph_no_checkpoint():
    """Build agent graph without checkpointer (for testing)."""
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


# Default graph instance
_agent_graph = None


def get_agent_graph():
    """Get or create the default agent graph."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
