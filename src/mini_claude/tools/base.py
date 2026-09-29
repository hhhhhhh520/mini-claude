"""Base tool definitions."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
import time

if TYPE_CHECKING:
    from .health_check import ToolHealthResult


@dataclass
class ToolDefinition:
    """Definition of a tool."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


class BaseTool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema for parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool."""
        pass

    @property
    def examples(self) -> List[Dict[str, Any]]:
        """Few-shot examples for tool usage.

        Each example should contain:
        - description: Brief description of the example
        - input: Dictionary of input parameters
        - expected_output: Expected output string

        Returns:
            List of example dictionaries. Default is empty list.
        """
        return []

    @property
    def dependencies(self) -> List[str]:
        """List of tool names this tool depends on.

        Returns:
            List of tool names that must be available for this tool to work.
            Default is empty list (no dependencies).
        """
        return []

    def get_dependency_info(self) -> Dict[str, Any]:
        """Get detailed dependency information.

        Returns:
            Dictionary with dependency details from the global dependency graph.
        """
        from .dependencies import get_dependency_graph

        graph = get_dependency_graph()
        deps = graph.get_dependencies(self.name)

        return {
            "tool_name": self.name,
            "direct_dependencies": deps,
            "all_dependencies": list(graph.get_all_dependencies(self.name)),
            "dependents": graph.get_dependents(self.name),
        }

    async def health_check(self) -> "ToolHealthResult":
        """Check tool health status.

        Returns:
            ToolHealthResult with status details.
            Default implementation delegates to health check module.
        """
        from .health_check import check_tool_health

        return await check_tool_health(self.name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "examples": self.examples,
        }


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._dependency_graph = None

    def _get_dependency_graph(self):
        """Get or initialize dependency graph."""
        if self._dependency_graph is None:
            from .dependencies import get_dependency_graph

            self._dependency_graph = get_dependency_graph()
        return self._dependency_graph

    def register(self, tool: BaseTool):
        """Register a tool."""
        self._tools[tool.name] = tool
        # Register in dependency graph
        graph = self._get_dependency_graph()
        graph.register_tool(tool.name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            graph = self._get_dependency_graph()
            graph.unregister_tool(name)
            return True
        return False

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions."""
        return [tool.to_dict() for tool in self._tools.values()]

    def get_dependency_info(self, name: str = None) -> Dict[str, Any]:
        """Get dependency information for a tool or all tools.

        Args:
            name: Specific tool name, or None for all tools

        Returns:
            Dictionary with dependency information
        """
        graph = self._get_dependency_graph()

        if name:
            if name not in self._tools:
                raise ValueError(f"Unknown tool: {name}")
            return {
                "tool_name": name,
                "dependencies": graph.get_dependencies(name),
                "all_dependencies": list(graph.get_all_dependencies(name)),
                "dependents": graph.get_dependents(name),
                "available": graph.check_availability(name, set(self._tools.keys())),
            }

        # Return info for all tools
        return {
            "tools": {
                tool_name: {
                    "dependencies": graph.get_dependencies(tool_name),
                    "dependents": graph.get_dependents(tool_name),
                }
                for tool_name in self._tools.keys()
            },
            "registered": list(self._tools.keys()),
            "dependency_count": len(graph._dependencies),
        }

    async def execute(self, name: str, params: Dict[str, Any]) -> str:
        """Execute a tool by name with audit logging, caching, dependency checking, and tracing.

        P3 单一裁决点 + 收敛批次①：PreToolUse hook（可 deny/allow/updatedInput）
        → 权限门（deny/ask；hook allow 跳过 ask）→ 执行 → PostToolUse hook。
        hook 的 updatedInput 先行改写入参，喂给权限匹配与执行。
        子代理跳过双门（子代理有自己的工具白名单体系，且不在子代理中执行用户 hook）。
        """
        from ..utils.logger import get_logger, get_audit_logger
        from ..config.settings import settings
        from ..monitoring.tracing import trace_tool_call
        from ..agent.nodes._shared import get_degradation_manager

        logger = get_logger("mini_claude.tools.registry")
        audit = get_audit_logger()

        from .file_ops import is_subagent_mode

        subagent = is_subagent_mode()

        # --- PreToolUse hook（先于权限门：allow 免确认 / ask 强制确认 / updatedInput 改写入参）---
        hook_allow = False
        if not subagent:
            hooks = _gate_hook_dispatcher()
            if hooks is not None:
                verdict = await hooks.dispatch_pre_tool_use(name, params)
                if verdict.blocked:
                    logger.info("tool blocked by PreToolUse hook", tool_name=name)
                    return f"Error: 被 PreToolUse hook 阻断：{verdict.blocked}"
                if verdict.updated_input is not None:
                    logger.info(
                        "tool input rewritten by PreToolUse hook",
                        tool_name=name,
                    )
                    params = verdict.updated_input
                hook_allow = verdict.allow
                if verdict.force_ask:
                    from ..permissions.manager import PermissionAskRequired
                    from ..permissions.rules import primary_arg

                    logger.info("tool forced to ask by PreToolUse hook", tool_name=name)
                    raise PermissionAskRequired(name, primary_arg(name, params))

        # --- 权限门（P3-2）：deny 拦下 / ask 抛确认异常；hook allow 免确认 ---
        if not subagent and not hook_allow:
            perm = _gate_permission_manager()
            if perm is not None:
                decision = perm.decide(name, params)
                if decision.action == "deny":
                    logger.info("tool denied by permission", tool_name=name, reason=decision.reason)
                    return f"Error: 权限拒绝（{decision.reason}）。如需执行请让用户调整权限规则或退出 plan 模式。"
                if decision.action == "ask":
                    from ..permissions.manager import PermissionAskRequired
                    from ..permissions.rules import primary_arg

                    raise PermissionAskRequired(name, primary_arg(name, params))

        # Degradation check: skip tool if it has too many recent failures
        degr_manager = get_degradation_manager()
        if degr_manager.tool.should_skip(name):
            replacement = degr_manager.tool.get_replacement(name)
            if replacement:
                return f"Error: Tool '{name}' is temporarily disabled. Try '{replacement}' instead."
            return f"Error: Tool '{name}' is temporarily disabled due to repeated failures."

        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        # Check dependencies before execution
        graph = self._get_dependency_graph()
        available, missing_required, missing_optional = graph.check_availability(
            name, set(self._tools.keys())
        )

        if not available:
            logger.warning(
                "Tool dependency check failed",
                tool_name=name,
                missing_required=missing_required,
            )
            # Return error message instead of raising - let LLM handle it
            return f"Error: Tool '{name}' requires unavailable tools: {missing_required}"

        if missing_optional:
            logger.debug(
                "Optional dependencies missing",
                tool_name=name,
                missing_optional=missing_optional,
            )

        # Check cache first if enabled
        if settings.tool_cache_enabled:
            from .cache import get_tool_cache

            cache = get_tool_cache()
            cached_result, hit = cache.get(name, params)
            if hit:
                logger.debug("Tool cache hit", tool_name=name)
                return cached_result

        start_time = time.time()

        # Execute with tracing
        with trace_tool_call(name, params) as span:
            try:
                result = await tool.execute(**params)
                duration_ms = (time.time() - start_time) * 1000

                # Record success for degradation tracking
                degr_manager.tool.record_success(name)

                if span:
                    span.set_attribute("tool.duration_ms", duration_ms)
                    span.set_attribute("tool.success", True)
                    span.set_attribute("tool.result_length", len(result) if result else 0)

                # Cache successful result if cacheable
                if settings.tool_cache_enabled and not result.startswith("Error"):
                    from .cache import get_tool_cache

                    cache = get_tool_cache()
                    cache.set(name, params, result)

                # Log to audit if available
                if audit:
                    audit.log_tool_call(
                        tool_name=name,
                        arguments=params,
                        result=result,
                        success=True,
                        duration_ms=duration_ms,
                    )

                # --- PostToolUse hook（P3-1）：可替换输出 ---
                if not subagent:
                    hooks = _gate_hook_dispatcher()
                    if hooks is not None:
                        replacement = await hooks.dispatch_post_tool_use(name, params, result)
                        if replacement is not None:
                            logger.info("tool output replaced by PostToolUse hook", tool_name=name)
                            result = replacement
                            if span:
                                span.set_attribute("tool.result_replaced", True)

                logger.debug("Tool executed", tool_name=name, duration_ms=round(duration_ms, 2))
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # Record failure for degradation tracking
                degr_manager.tool.record_failure(name, str(e))

                if span:
                    span.set_attribute("tool.duration_ms", duration_ms)
                    span.set_attribute("tool.success", False)
                    span.set_attribute("tool.error", str(e))

                # Log failure to audit
                if audit:
                    audit.log_tool_call(
                        tool_name=name,
                        arguments=params,
                        result=str(e),
                        success=False,
                        duration_ms=duration_ms,
                    )

                logger.error("Tool execution failed", tool_name=name, error=str(e))
                raise


# Global tool registry
tool_registry = ToolRegistry()


def register_tool(tool: BaseTool):
    """Decorator/function to register a tool."""
    tool_registry.register(tool)
    return tool


def _gate_permission_manager():
    """延迟解析权限管理器（P3-2）。

    函数内 import 避免循环依赖；独立函数便于测试注入（monkeypatch 本函数）。
    """
    from ..permissions.manager import get_permission_manager

    return get_permission_manager()


def _gate_hook_dispatcher():
    """延迟解析 hook 分发器（P3-1），同上。"""
    from ..hooks.dispatcher import get_hook_dispatcher

    return get_hook_dispatcher()
