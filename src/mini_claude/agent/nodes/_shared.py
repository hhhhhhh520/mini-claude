"""Shared imports and utilities for nodes."""

from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..state import AgentState, StopReason, get_max_iterations
from ..completion_config import (
    detect_project_type,
    check_project_completion,
    check_web_project_completion,
    check_backend_project_completion,
)
from ...llm.provider import LLMProvider, convert_tools_to_litellm
from ...llm.prompts import get_system_prompt
from ...tools import get_all_tools
from mini_claude.config.settings import settings
from ...utils.safety import PathConfirmationRequired, get_rate_limiter
from ..degradation import DegradationManager
from ...utils.token_manager import get_token_counter, TokenLimitStrategy
from ...utils.logger import get_logger
from ...monitoring.metrics import get_metrics_collector
from ...monitoring.tracing import trace_agent_node, trace_tool_call, trace_llm_call
from .exceptions import ToolExecutionError, ToolTimeoutError, ToolParameterError


# Module logger
logger = get_logger("mini_claude.agent.nodes")

# Initialize LLM provider
llm_provider = LLMProvider()

# Initialize degradation manager (lazy)
_degradation_manager: Optional[DegradationManager] = None


def get_degradation_manager() -> DegradationManager:
    """Get or create degradation manager."""
    global _degradation_manager
    if _degradation_manager is None:
        config = {
            "model": {
                "primary": settings.default_model,
                "fallbacks": [],  # Can be configured via env
            },
            "backoff": {
                "max_retries": 3,
            },
            "tool": {
                "max_failures": 3,
            },
            "strategy": {
                "initial_strategy": "react",
            },
        }
        _degradation_manager = DegradationManager(config)
    return _degradation_manager


__all__ = [
    # Types
    "AgentState",
    "StopReason",
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "Optional",
    # Functions
    "get_max_iterations",
    "detect_project_type",
    "check_project_completion",
    "check_web_project_completion",
    "check_backend_project_completion",
    "LLMProvider",
    "convert_tools_to_litellm",
    "get_system_prompt",
    "get_all_tools",
    "settings",
    "PathConfirmationRequired",
    "get_rate_limiter",
    "DegradationManager",
    "get_degradation_manager",
    "get_token_counter",
    "TokenLimitStrategy",
    "get_logger",
    "get_metrics_collector",
    "trace_agent_node",
    "trace_tool_call",
    "trace_llm_call",
    # Exceptions
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolParameterError",
    # Logger
    "logger",
    "llm_provider",
]
