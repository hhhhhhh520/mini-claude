"""Agent graph nodes module.

This module contains all node functions for the LangGraph agent.

Nodes:
    think_node: Check iteration limits and add system prompt
    plan_node: Generate execution plan
    act_node: Call LLM and execute tools
    observe_node: Observe results and decide next steps
    reflect_node: Analyze execution results and summarize lessons
    check_completion_node: Use LLM to determine if task is complete
    handle_error_node: Check retry count and generate fix suggestions
    retry_node: Prepare for re-execution

Router functions:
    should_continue_router: Legacy router for backward compatibility

Exceptions:
    ToolExecutionError: Tool execution error
    ToolTimeoutError: Tool timeout error
    ToolParameterError: Tool parameter error

Shared utilities:
    llm_provider: LLM provider instance for backward compatibility with tests
"""

from .exceptions import (
    ToolExecutionError,
    ToolTimeoutError,
    ToolParameterError,
)

from .think import think_node
from .plan import plan_node
from .act import act_node
from .observe import observe_node
from .reflect import reflect_node
from .check_completion import check_completion_node
from .error_handling import handle_error_node
from .retry import retry_node

# Re-export llm_provider for backward compatibility with tests
from ._shared import llm_provider


# =============================================================================
# ROUTER FUNCTION (保留兼容)
# =============================================================================

def should_continue_router(state) -> bool:
    """路由函数：判断是否继续（保留兼容旧代码）"""
    from ..state import StopReason
    stop_reason = state.get("stop_reason", StopReason.CONTINUE)
    return stop_reason == StopReason.CONTINUE


__all__ = [
    # Nodes
    "think_node",
    "plan_node",
    "act_node",
    "observe_node",
    "reflect_node",
    "check_completion_node",
    "handle_error_node",
    "retry_node",
    # Router
    "should_continue_router",
    # Exceptions
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolParameterError",
    # Shared utilities (for backward compatibility)
    "llm_provider",
]
