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

# Initialize LLM provider
llm_provider = LLMProvider()


def get_llm_provider():
    """取当前 LLM provider 实例（P4-4）。

    act 等模块不得在 import 期按名绑定 llm_provider——/model 热切换会重建
    单例，按名绑定会失联（ISSUE-024 同款教训）。统一经本访问器取。
    """
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


def build_system_messages() -> list:
    """构造前置给 LLM 的系统消息（LiteLLM 格式）：系统提示 + 可用 skills.

    刻意**不写入** state["messages"]：messages 字段是 `Annotated[List, add]`
    累加语义，把系统提示塞进去再由 think 返回全量列表，会导致用户消息被复制、
    SystemMessage 落到 HumanMessage 之后（见 ISSUE：reducer 消息重复）。
    系统提示应在每次 LLM 调用时前置，永远完整、永远在最前、不进持久化历史。
    """
    provider = settings.get_model_provider()
    system_msgs = [{"role": "system", "content": get_system_prompt(provider)}]

    # Inject CLAUDE.md project/user memory (P1-2)——与 skills 同一通道：
    # 每次调用前置、不进持久化历史、失效不阻断主链路。
    if getattr(settings, "claude_md_enabled", False):
        try:
            from mini_claude.utils.claudemd import load_claude_md

            claude_md = load_claude_md(settings.workspace_root)
            if claude_md:
                system_msgs.append(
                    {
                        "role": "system",
                        "content": (
                            "以下约定来自 CLAUDE.md（用户级与项目级记忆），"
                            "在本会话中必须始终遵守：\n\n" + claude_md
                        ),
                    }
                )
        except Exception as e:
            logger.debug("claudemd injection failed", error=str(e))

    # Inject skills as a dedicated system message（小模型更关注近期上下文，
    # 但系统消息本就整体前置，这里保持与旧行为一致的完整 skill 说明）。
    try:
        from mini_claude.skills.registry import get_skill_registry

        registry = get_skill_registry()
        skills = [s for s in registry.list_skills() if s.model_invocable]
        if skills:
            parts = [
                "IMPORTANT: You have the following skills available. "
                "A skill is a set of specialized instructions you should follow "
                "when the user's request matches. DO NOT search for skills on disk — "
                "they are already loaded here:\n"
            ]
            for skill in skills:
                parts.append(f"--- Skill: {skill.name} ---")
                if skill.description:
                    parts.append(f"Trigger: {skill.description}")
                if skill.body:
                    parts.append(skill.body)
                parts.append("")
            parts.append(
                "To use a skill, tell the user you are following it and apply its instructions. "
                "You can also suggest the user type /skill <name> to explicitly activate one."
            )
            system_msgs.append({"role": "system", "content": "\n".join(parts)})
    except Exception as e:  # skills 失效不应阻断主链路，但必须可见
        logger.debug("skills injection failed", error=str(e))

    return system_msgs


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
