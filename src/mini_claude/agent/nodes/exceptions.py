"""Node-level exceptions for tool execution."""

from typing import Optional


class ToolExecutionError(Exception):
    """Tool execution error."""

    def __init__(self, message: str, tool_name: Optional[str] = None):
        self.tool_name = tool_name
        super().__init__(message)


class ToolTimeoutError(Exception):
    """Tool timeout error."""

    def __init__(self, tool_name: str, timeout_seconds: float):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Tool {tool_name} timed out after {timeout_seconds}s")


class ToolParameterError(Exception):
    """Tool parameter error."""

    def __init__(self, tool_name: str, parameter: str, reason: str):
        self.tool_name = tool_name
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"Tool {tool_name} parameter '{parameter}' error: {reason}")
