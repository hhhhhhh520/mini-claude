"""Tools module - exports all tools and provides helper functions."""

from typing import Dict, Any, List

from .base import BaseTool, ToolRegistry, tool_registry, register_tool
from .file_ops import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListDirTool,
    SearchFilesTool,
    SearchContentTool,
    set_current_agent,
    set_subagent_mode,
    is_subagent_mode,
    get_current_agent,
)
from .bash import RunCommandTool, RunBackgroundTool
from .agent_spawn import (
    SpawnAgentTool,
    ListAgentsTool,
    GetResultTool,
    SpawnParallelTool,
)
from .web_search import WebSearchTool
from .web_fetch import WebFetchTool
from .weather import WeatherTool
from .parallel import (
    PlanParallelTool,
    ExecuteParallelTool,
    ParallelStatusTool,
    AggregateResultsTool,
)
from .health_check import (
    ToolHealthChecker,
    ToolHealthStatus,
    ToolHealthResult,
    ToolHealthSummary,
    get_tool_health_checker,
    check_tool_health,
    check_all_tools_health,
)
from .cache import (
    ToolCache,
    CacheEntry,
    CacheStats,
    get_tool_cache,
    reset_tool_cache,
)
from .dependencies import (
    ToolDependency,
    DependencyGraph,
    DependencyType,
    CyclicDependencyError,
    get_dependency_graph,
    reset_dependency_graph,
)


def get_all_tools() -> List[Dict[str, Any]]:
    """Get all registered tool definitions."""
    return tool_registry.get_all_definitions()


def get_tool(name: str) -> BaseTool:
    """Get a tool by name."""
    return tool_registry.get(name)


async def execute_tool(name: str, params: Dict[str, Any]) -> str:
    """Execute a tool by name with given parameters."""
    return await tool_registry.execute(name, params)


def list_tools() -> List[str]:
    """List all registered tool names."""
    return tool_registry.list_tools()


__all__ = [
    # Base classes
    "BaseTool",
    "ToolRegistry",
    "tool_registry",
    "register_tool",
    # File tools
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirTool",
    "SearchFilesTool",
    "SearchContentTool",
    # Agent context functions
    "set_current_agent",
    "get_current_agent",
    "set_subagent_mode",
    "is_subagent_mode",
    # Bash tools
    "RunCommandTool",
    "RunBackgroundTool",
    # Agent tools
    "SpawnAgentTool",
    "ListAgentsTool",
    "GetResultTool",
    "SpawnParallelTool",
    # Parallel execution tools
    "PlanParallelTool",
    "ExecuteParallelTool",
    "ParallelStatusTool",
    "AggregateResultsTool",
    # Web tools
    "WebSearchTool",
    "WebFetchTool",
    "WeatherTool",
    # Health check
    "ToolHealthChecker",
    "ToolHealthStatus",
    "ToolHealthResult",
    "ToolHealthSummary",
    "get_tool_health_checker",
    "check_tool_health",
    "check_all_tools_health",
    # Cache
    "ToolCache",
    "CacheEntry",
    "CacheStats",
    "get_tool_cache",
    "reset_tool_cache",
    # Dependencies
    "ToolDependency",
    "DependencyGraph",
    "DependencyType",
    "CyclicDependencyError",
    "get_dependency_graph",
    "reset_dependency_graph",
    # Helper functions
    "get_all_tools",
    "get_tool",
    "execute_tool",
    "list_tools",
]
