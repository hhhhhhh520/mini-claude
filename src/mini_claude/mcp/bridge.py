"""MCP 工具桥接（P2）。

把远端 MCP server 的工具适配成本仓库的 BaseTool 注册进全局 ToolRegistry：
- 命名 mcp__<server>__<tool>（与 Claude Code 的 mcp__ 前缀约定一致）
- 描述加 [mcp:<server>] 前缀，LLM 能分辨来源
- 默认走确认通道：未放行时抛 McpConfirmationRequired，由 act 执行链转
  WAITING_CONFIRMATION（复用路径确认的状态机通道）
- 本模块不 import mcp SDK（session 鸭子类型），缺 SDK 也能导入
"""

from typing import Any, Dict, List

from ..tools.base import BaseTool
from ..tools.base import tool_registry
from ..utils.logger import get_logger

logger = get_logger("mini_claude.mcp.bridge")


class McpConfirmationRequired(Exception):
    """MCP 工具未放行，需要用户确认。

    Attributes:
        server: server 名
        tool: 工具名
    """

    def __init__(self, server: str, tool: str):
        self.server = server
        self.tool = tool
        super().__init__(f"MCP tool requires confirmation: {server}/{tool}")


def make_bridge_tool_name(server: str, tool: str) -> str:
    """MCP 工具在本仓库的全局名：mcp__<server>__<tool>。"""
    return f"mcp__{server}__{tool}"


def _format_content(content: List[Any]) -> str:
    """把 MCP CallToolResult.content 拼成文本；非文本部分给占位标记。"""
    parts: List[str] = []
    for item in content or []:
        kind = getattr(item, "type", None)
        if kind == "text":
            parts.append(getattr(item, "text", ""))
        else:
            parts.append(f"[{kind or 'unknown'} content]")
    return "\n".join(p for p in parts if p)


class McpToolBridge(BaseTool):
    """远端 MCP 工具的本地适配器。"""

    def __init__(self, manager, server: str, tool_def: Any):
        self._manager = manager
        self._server = server
        self._tool_name = tool_def.name
        self._description = tool_def.description or ""
        self._input_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._session = None

    def bind_session(self, session) -> None:
        """绑定已初始化的 ClientSession（由 manager 在连接时调用）。"""
        self._session = session

    @property
    def name(self) -> str:
        return make_bridge_tool_name(self._server, self._tool_name)

    @property
    def description(self) -> str:
        return f"[mcp:{self._server}] {self._description}".strip()

    @property
    def parameters(self) -> Dict[str, Any]:
        schema = dict(self._input_schema)
        schema.setdefault("type", "object")
        return schema

    async def execute(self, **kwargs) -> str:
        if not self._manager.is_tool_approved(self._server, self._tool_name):
            raise McpConfirmationRequired(self._server, self._tool_name)

        if self._session is None:
            return f"Error: MCP server '{self._server}' 未连接，无法调用 {self._tool_name}"

        try:
            result = await self._session.call_tool(self._tool_name, kwargs)
        except Exception as e:
            return f"Error: MCP 工具 {self._tool_name} 调用失败：{type(e).__name__}: {e}"

        text = _format_content(getattr(result, "content", []))
        if getattr(result, "isError", False):
            return f"Error: {text or 'MCP 工具返回错误（无内容）'}"
        return text or "(MCP 工具返回空内容)"


def register_server_tools(manager, connection) -> List[str]:
    """把一个已连接 server 的全部工具注册进全局 registry。

    重复注册（重连场景）会先注销旧条目，保证同名工具只有一个。
    """
    unregister_server_tools(connection.server)

    registered: List[str] = []
    for tool_def in connection.tools:
        bridge = McpToolBridge(manager, connection.server, tool_def)
        bridge.bind_session(connection.session)
        tool_registry.register(bridge)
        registered.append(bridge.name)

    logger.info("MCP tools registered", server=connection.server, count=len(registered))
    return registered


def unregister_server_tools(server: str) -> None:
    """注销某 server 注册的全部桥接工具（断连/重连时调用）。"""
    prefix = f"mcp__{server}__"
    for name in list(tool_registry.list_tools()):
        if name.startswith(prefix):
            tool_registry.unregister(name)
