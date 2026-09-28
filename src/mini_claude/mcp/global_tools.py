"""MCP resources/prompts 全局工具（B2）。

对标 Claude Code 的 ListMcpResources / ReadMcpResource（prompts 同理）：
- 四个只读工具（mcp_list_resources / mcp_read_resource / mcp_list_prompts /
  mcp_get_prompt），经 manager 的已连接集合聚合查询
- 只读操作不走确认通道（资源/prompt 内容显式请求才进上下文，与 web_fetch
  同级；server 本身是用户配置的信任对象）
- ensure_global_tools_registered() 幂等；在 MCP 连接路径上调用——
  MCP_ENABLED=false 或从未连接时这些工具不占工具列表
"""

from typing import Any, Dict

from ..tools.base import BaseTool, tool_registry
from ..utils.logger import get_logger

logger = get_logger("mini_claude.mcp.global_tools")

_GLOBAL_TOOL_NAMES = (
    "mcp_list_resources",
    "mcp_read_resource",
    "mcp_list_prompts",
    "mcp_get_prompt",
)


def _no_connection_error() -> str:
    return "Error: 当前没有已连接的 MCP server（用 /mcp connect <name> 或配置 mcp.json 自动连接）"


class McpListResourcesTool(BaseTool):
    """列出全部已连接 server 的资源。"""

    @property
    def name(self) -> str:
        return "mcp_list_resources"

    @property
    def description(self) -> str:
        return (
            "List resources exposed by connected MCP servers "
            "(server, uri, name, description). Use mcp_read_resource to read one."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self) -> str:
        from .manager import get_mcp_manager

        mgr = get_mcp_manager()
        if not mgr._connections:
            return _no_connection_error()
        resources = await mgr.list_resources()
        if not resources:
            return "已连接的 MCP server 没有暴露任何资源。"
        lines = [f"MCP resources ({len(resources)}):"]
        for r in resources:
            desc = f" — {r['description']}" if r["description"] else ""
            lines.append(f"  [{r['server']}] {r['uri']} ({r['name']}){desc}")
        return "\n".join(lines)


class McpReadResourceTool(BaseTool):
    """按 server + uri 读取一个资源。"""

    @property
    def name(self) -> str:
        return "mcp_read_resource"

    @property
    def description(self) -> str:
        return "Read one resource from a connected MCP server by server name and uri."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name"},
                "uri": {"type": "string", "description": "Resource uri (see mcp_list_resources)"},
            },
            "required": ["server", "uri"],
        }

    async def execute(self, server: str = "", uri: str = "") -> str:
        from .manager import get_mcp_manager

        if not server or not uri:
            return "Error: mcp_read_resource 需要 server 与 uri 参数"
        try:
            return await get_mcp_manager().read_resource(server, uri)
        except KeyError as e:
            return f"Error: {e.args[0]}"
        except Exception as e:
            return f"Error: 读取资源失败：{type(e).__name__}: {e}"


class McpListPromptsTool(BaseTool):
    """列出全部已连接 server 的 prompts。"""

    @property
    def name(self) -> str:
        return "mcp_list_prompts"

    @property
    def description(self) -> str:
        return (
            "List prompts exposed by connected MCP servers "
            "(server, name, description). Use mcp_get_prompt to expand one."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self) -> str:
        from .manager import get_mcp_manager

        mgr = get_mcp_manager()
        if not mgr._connections:
            return _no_connection_error()
        prompts = await mgr.list_prompts()
        if not prompts:
            return "已连接的 MCP server 没有暴露任何 prompt。"
        lines = [f"MCP prompts ({len(prompts)}):"]
        for p in prompts:
            desc = f" — {p['description']}" if p["description"] else ""
            lines.append(f"  [{p['server']}] {p['name']}{desc}")
        return "\n".join(lines)


class McpGetPromptTool(BaseTool):
    """展开一个 prompt 为对话文本。"""

    @property
    def name(self) -> str:
        return "mcp_get_prompt"

    @property
    def description(self) -> str:
        return "Expand one MCP prompt into message text by server name and prompt name."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name"},
                "name": {"type": "string", "description": "Prompt name (see mcp_list_prompts)"},
                "arguments": {
                    "type": "object",
                    "description": "Prompt template arguments",
                },
            },
            "required": ["server", "name"],
        }

    async def execute(self, server: str = "", name: str = "", arguments: dict = None) -> str:
        from .manager import get_mcp_manager

        if not server or not name:
            return "Error: mcp_get_prompt 需要 server 与 name 参数"
        try:
            return await get_mcp_manager().get_prompt(server, name, arguments or {})
        except KeyError as e:
            return f"Error: {e.args[0]}"
        except Exception as e:
            return f"Error: 获取 prompt 失败：{type(e).__name__}: {e}"


def ensure_global_tools_registered() -> None:
    """幂等注册四个全局工具（MCP 连接路径上调用）。"""
    registered = False
    for cls in (McpListResourcesTool, McpReadResourceTool, McpListPromptsTool, McpGetPromptTool):
        tool = cls()
        if tool.name not in tool_registry.list_tools():
            tool_registry.register(tool)
            registered = True
    if registered:
        logger.debug("MCP global tools registered", tools=list(_GLOBAL_TOOL_NAMES))
