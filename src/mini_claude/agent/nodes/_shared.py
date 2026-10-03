"""Shared imports and utilities for nodes."""

from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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

# LLM provider 单例——懒加载（2026-10-03 拔除导入期副作用）：
# 此前模块导入期即 `LLMProvider()`，ask 在测试把 LLMProvider 打补丁的窗口内
# 首次导入 _shared 时会把假 provider 铸进全局，污染同进程后续图测试
# （实测 20 errors，单跑全过——导入序敏感）。导入期零构造，首次取用才创建。
llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """取当前 LLM provider 实例（P4-4；懒加载）。

    act 等模块不得在 import 期按名绑定 llm_provider——/model 热切换会重建
    单例，按名绑定会失联（ISSUE-024 同款教训）；懒加载后按名绑定更会拿到
    None。统一经本访问器取。
    """
    global llm_provider
    if llm_provider is None:
        llm_provider = LLMProvider()
    return llm_provider


def rebuild_llm_provider(model: Optional[str] = None):
    """重建 provider 单例（/model 热切换）；返回新实例。"""
    global llm_provider
    llm_provider = LLMProvider(model=model)
    logger.info("llm provider rebuilt", model=llm_provider.model)
    return llm_provider


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


def build_system_messages(hook_context: str = "") -> list:
    """构造前置给 LLM 的系统消息——实现在 llm/prompts.py，此处仅兼容转发。

    历史教训（2026-10-02）：ask 模式在本函数被引入后首次触发 `_shared`
    导入，恰逢测试把 LLMProvider 打补丁的窗口，模块导入期的
    `llm_provider = LLMProvider()` 单例初始化把假 provider 铸进了全局，
    污染后续所有图测试。提示词装配不依赖 LLM 机制，因此整体迁往
    llm/prompts.py——ask 只依赖 llm 层，_shared 保留转发兼容图路径调用方。
    """
    from ...llm.prompts import build_system_messages as _build

    return _build(hook_context)


__all__ = [
    # Types
    "AgentState",
    "StopReason",
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "ToolMessage",
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
    "build_system_messages",
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
