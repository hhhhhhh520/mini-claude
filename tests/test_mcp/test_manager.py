"""MCP 管理器测试（P2）

连接生命周期用注入的 fake `_open_connection` 测试（不真起子进程）；
真 stdio 子进程的 E2E 在 tests/test_integration/test_mcp_stdio_e2e.py。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mini_claude.mcp.config import McpServerConfig
from mini_claude.mcp.manager import (
    McpSDKMissingError,
    McpManager,
    get_mcp_manager,
    reset_mcp_manager,
)
from mini_claude.tools import list_tools


def _fake_open(connection_name="srv"):
    """构造可注入的 _open_connection 替身"""

    async def _open(cfg):
        stack = SimpleNamespace(aclose=AsyncMock())
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=None)
        tools = [
            SimpleNamespace(
                name="echo",
                description="Echo",
                inputSchema={"type": "object", "properties": {}},
            )
        ]
        return SimpleNamespace(server=cfg.name, session=session, tools=tools, stack=stack)

    return _open


@pytest.fixture(autouse=True)
def _clean():
    yield
    reset_mcp_manager()


def _freeze(mgr: McpManager, configs: dict):
    """直接注入配置并冻结（跳过磁盘加载）"""
    mgr._configs = configs
    mgr._config_loaded = True


class TestManagerLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect_registers_tools(self):
        mgr = McpManager()
        _freeze(mgr, {"srv": McpServerConfig(name="srv", command="x")})
        mgr._open_connection = _fake_open()

        await mgr.connect_server("srv")
        assert "mcp__srv__echo" in list_tools()
        assert mgr.status()["srv"]["connected"] is True
        assert mgr.status()["srv"]["tools"] == 1

        await mgr.disconnect_server("srv")
        assert "mcp__srv__echo" not in list_tools()
        assert mgr.status()["srv"]["connected"] is False  # 仍列出但标记未连接

    @pytest.mark.asyncio
    async def test_connect_unknown_server_raises(self):
        mgr = McpManager()
        _freeze(mgr, {})
        with pytest.raises(KeyError):
            await mgr.connect_server("nope")

    @pytest.mark.asyncio
    async def test_connect_twice_is_idempotent(self):
        mgr = McpManager()
        _freeze(mgr, {"srv": McpServerConfig(name="srv", command="x")})
        mgr._open_connection = _fake_open()

        await mgr.connect_server("srv")
        await mgr.connect_server("srv")  # 不应重复注册
        assert list_tools().count("mcp__srv__echo") == 1

    @pytest.mark.asyncio
    async def test_close_all_closes_stacks_and_unregisters(self):
        mgr = McpManager()
        _freeze(mgr, {"srv": McpServerConfig(name="srv", command="x")})
        mgr._open_connection = _fake_open()
        await mgr.connect_server("srv")

        await mgr.close_all()
        assert "mcp__srv__echo" not in list_tools()
        assert mgr.status()["srv"]["connected"] is False

    @pytest.mark.asyncio
    async def test_connect_all_reports_errors_without_abort(self):
        """单server失败不拖垮其他server"""
        mgr = McpManager()
        _freeze(
            mgr,
            {
                "good": McpServerConfig(name="good", command="x"),
                "bad": McpServerConfig(name="bad", command="y"),
            },
        )

        async def _open(cfg):
            if cfg.name == "bad":
                raise RuntimeError("spawn failed")
            return await _fake_open()(cfg)

        mgr._open_connection = _open
        connected, errors = await mgr.connect_all()

        assert connected == ["good"]
        assert "bad" in errors
        assert "mcp__good__echo" in list_tools()
        await mgr.close_all()


class TestSdkMissing:
    @pytest.mark.asyncio
    async def test_missing_sdk_raises_friendly_chinese_error(self):
        mgr = McpManager()
        _freeze(mgr, {"srv": McpServerConfig(name="srv", command="x")})

        def _raise_import():
            raise ImportError("No module named 'mcp'")

        mgr._load_sdk = _raise_import
        with pytest.raises(McpSDKMissingError) as exc_info:
            await mgr.connect_server("srv")
        assert "[mcp]" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)


class TestApproval:
    @pytest.mark.asyncio
    async def test_approve_roundtrip(self):
        mgr = McpManager()
        assert mgr.is_tool_approved("fs", "read") is False
        mgr.approve_tool("fs", "read")
        assert mgr.is_tool_approved("fs", "read") is True

    @pytest.mark.asyncio
    async def test_trusted_server_auto_approved(self):
        mgr = McpManager()
        _freeze(mgr, {"t": McpServerConfig(name="t", command="x", trusted=True)})
        mgr._open_connection = _fake_open()
        await mgr.connect_server("t")

        assert mgr.is_tool_approved("t", "echo") is True
        await mgr.close_all()

    @pytest.mark.asyncio
    async def test_approve_confirmation_key_routes_mcp_keys(self):
        """REPL 'yes' 分支的键路由：mcp: 前缀放行工具，其他走 approve_path"""
        from mini_claude.mcp.manager import approve_confirmation_key

        mgr = get_mcp_manager()
        assert approve_confirmation_key("mcp:fs:read") is True
        assert mgr.is_tool_approved("fs", "read") is True
        assert approve_confirmation_key("/some/path") is False


class TestSingleton:
    def test_get_mcp_manager_singleton(self):
        reset_mcp_manager()
        assert get_mcp_manager() is get_mcp_manager()

    def test_reset_mcp_manager(self):
        reset_mcp_manager()
        a = get_mcp_manager()
        reset_mcp_manager()
        assert get_mcp_manager() is not a


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
