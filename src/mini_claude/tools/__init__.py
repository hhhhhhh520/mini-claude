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
)
from .bash import RunCommandTool, RunBackgroundTool
from .agent_spawn import (
    SpawnAgentTool,
    ListAgentsTool,
    GetResultTool,
    SpawnParallelTool,
)
from .web_search import WebSearchTool


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
    # Bash tools
    "RunCommandTool",
    "RunBackgroundTool",
    # Agent tools
    "SpawnAgentTool",
    "ListAgentsTool",
    "GetResultTool",
    "SpawnParallelTool",
    # Web tools
    "WebSearchTool",
    # Helper functions
    "get_all_tools",
    "get_tool",
    "execute_tool",
    "list_tools",
]
