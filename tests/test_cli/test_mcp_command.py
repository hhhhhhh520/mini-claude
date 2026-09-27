"""/mcp REPL 命令测试（P2）"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mini_claude.cli.commands.mcp_handler import McpCommandHandler
from mini_claude.cli.commands.base import CommandContext
from mini_claude.cli.display import display


def _ctx(args=""):
    session = SimpleNamespace(thread_id="t1", messages=[])
    return CommandContext(session=session, command="/mcp", args=args, display=display)


class TestMcpCommand:
    @pytest.mark.asyncio
    async def test_status_empty_config(self, monkeypatch):
        manager = MagicMock()
        manager.status.return_value = {}
        manager.has_config.return_value = False
        monkeypatch.setattr("mini_claude.mcp.manager.get_mcp_manager", lambda: manager)

        result = await McpCommandHandler().handle(_ctx())
        assert result.handled
        assert "mcp.json" in result.message

    @pytest.mark.asyncio
    async def test_status_lists_servers(self, monkeypatch):
        manager = MagicMock()
        manager.status.return_value = {
            "fs": {"connected": True, "tools": 3, "trusted": False, "command": "x", "error": None},
            "db": {
                "connected": False,
                "tools": 0,
                "trusted": False,
                "command": "y",
                "error": "spawn failed",
            },
        }
        manager.has_config.return_value = True
        monkeypatch.setattr("mini_claude.mcp.manager.get_mcp_manager", lambda: manager)

        result = await McpCommandHandler().handle(_ctx())
        assert "fs" in result.message and "db" in result.message
        assert "3" in result.message

    @pytest.mark.asyncio
    async def test_connect_subcommand(self, monkeypatch):
        manager = MagicMock()
        manager.connect_server = AsyncMock()
        manager.status.return_value = {}
        manager.has_config.return_value = True
        monkeypatch.setattr("mini_claude.mcp.manager.get_mcp_manager", lambda: manager)

        await McpCommandHandler().handle(_ctx("connect fs"))
        manager.connect_server.assert_awaited_once_with("fs")

    @pytest.mark.asyncio
    async def test_disconnect_subcommand(self, monkeypatch):
        manager = MagicMock()
        manager.disconnect_server = AsyncMock()
        manager.status.return_value = {}
        manager.has_config.return_value = True
        monkeypatch.setattr("mini_claude.mcp.manager.get_mcp_manager", lambda: manager)

        await McpCommandHandler().handle(_ctx("disconnect fs"))
        manager.disconnect_server.assert_awaited_once_with("fs")

    @pytest.mark.asyncio
    async def test_sdk_missing_shows_guidance(self, monkeypatch):
        manager = MagicMock()
        manager.connect_server = AsyncMock(
            side_effect=RuntimeError('MCP 支持未安装。请运行: pip install -e ".[mcp]"')
        )
        manager.status.return_value = {}
        manager.has_config.return_value = True
        monkeypatch.setattr("mini_claude.mcp.manager.get_mcp_manager", lambda: manager)

        result = await McpCommandHandler().handle(_ctx("connect fs"))
        assert result.error is not None
        assert "mcp" in result.error

    def test_registered_in_dispatch(self):
        """注册进命令分发器，/mcp 能被路由"""
        from mini_claude.cli.commands.base import get_command_registry

        assert get_command_registry().get_handler("/mcp") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
