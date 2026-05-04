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
        """Execute a tool by name with audit logging, caching, dependency checking, and tracing."""
        from ..utils.logger import get_logger, get_audit_logger
        from ..config.settings import settings
        from ..monitoring.tracing import trace_tool_call

        logger = get_logger("mini_claude.tools.registry")
        audit = get_audit_logger()

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

                logger.debug("Tool executed", tool_name=name, duration_ms=round(duration_ms, 2))
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

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
