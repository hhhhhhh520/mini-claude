"""Base tool definitions."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
import json


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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions."""
        return [tool.to_dict() for tool in self._tools.values()]

    async def execute(self, name: str, params: Dict[str, Any]) -> str:
        """Execute a tool by name."""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return await tool.execute(**params)


# Global tool registry
tool_registry = ToolRegistry()


def register_tool(tool: BaseTool):
    """Decorator/function to register a tool."""
    tool_registry.register(tool)
    return tool
