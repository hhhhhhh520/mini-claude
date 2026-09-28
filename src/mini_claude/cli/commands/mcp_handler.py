"""/mcp 命令：查看 MCP server 状态、手动连接/断连、重载配置。"""

from typing import TYPE_CHECKING, List

from .base import CommandHandler, CommandResult

if TYPE_CHECKING:
    pass


class McpCommandHandler(CommandHandler):
    """MCP server 管理命令。

    /mcp                     状态总览
    /mcp connect <name>      连接指定 server
    /mcp disconnect <name>   断开指定 server
    /mcp reload              重载 mcp.json（新增/修改的 server 生效）
    """

    commands: List[str] = ["/mcp"]

    async def handle(self, ctx) -> CommandResult:
        from ...mcp.manager import get_mcp_manager

        manager = get_mcp_manager()
        args = (ctx.args or "").strip()
        parts = args.split()

        try:
            if not parts:
                return CommandResult(handled=True, message=self._format_status(manager))

            sub = parts[0].lower()
            if sub == "connect" and len(parts) == 2:
                await manager.connect_server(parts[1])
                return CommandResult(handled=True, message=f"已连接 MCP server: {parts[1]}")
            if sub == "disconnect" and len(parts) == 2:
                await manager.disconnect_server(parts[1])
                return CommandResult(handled=True, message=f"已断开 MCP server: {parts[1]}")
            if sub == "reload":
                warnings = manager.reload_config()
                msgs = ["已重载 mcp.json 配置"] + [f"- {w}" for w in warnings]
                return CommandResult(handled=True, message="\n".join(msgs))

            return CommandResult(
                handled=True,
                message="用法: /mcp [connect <name> | disconnect <name> | reload]",
            )
        except KeyError as e:
            return CommandResult(handled=True, error=str(e).strip("'\""))
        except Exception as e:
            # 含 McpSDKMissingError：中文指引已在消息里，直接透传
            return CommandResult(handled=True, error=str(e))

    def _format_status(self, manager) -> str:
        if not manager.has_config():
            return (
                "未找到 MCP 配置。\n"
                "在 ~/.mini-claude/mcp.json 或 <工作区>/.mini-claude/mcp.json 写入：\n"
                '{"mcpServers": {"<name>": {"command": "...", "args": [...]}}}\n'
                '然后用 /mcp reload 重新加载。依赖缺失时先 pip install -e ".[mcp]"。'
            )

        status = manager.status()
        if not status:
            return "MCP 配置为空。"

        lines = ["MCP servers:"]
        for name, info in status.items():
            endpoint = info.get("url") or info.get("command") or ""
            tag = f"[{info.get('transport', 'stdio')}] "
            if info["connected"]:
                lines.append(
                    f"  [ok] {name}: {tag}{info['tools']} 个工具"
                    + ("（trusted）" if info.get("trusted") else "")
                )
            else:
                lines.append(f"  [--] {name}: 未连接（{tag}{endpoint}）")
        lines.append("用 /mcp connect <name> 连接，/mcp reload 重载配置。")
        return "\n".join(lines)
