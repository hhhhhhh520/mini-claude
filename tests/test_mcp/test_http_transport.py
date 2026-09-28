"""MCP HTTP transport 连接路由测试（无 SDK 依赖——sys.modules 注入假模块）。

锁定 _open_connection 的 http 分支契约：
- 走 streamablehttp_client(url, headers=...)，session 完成 initialize + list_tools
- headers 透传；url 来自配置
- 连接后工具照常注册进 tool_registry（与 stdio 同桥接路径）
"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mini_claude.mcp.config import McpServerConfig
from mini_claude.mcp.manager import McpManager, reset_mcp_manager
from mini_claude.tools import list_tools, tool_registry


class _FakeAsyncCtx:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self):
        self.initialize = AsyncMock()
        self.list_tools = AsyncMock(
            return_value=SimpleNamespace(
                tools=[SimpleNamespace(name="ping", description="pong", inputSchema={})]
            )
        )
        self.call_tool = AsyncMock(return_value=SimpleNamespace(content=[], isError=False))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fake_http_sdk(monkeypatch):
    """注入假 mcp / mcp.client.streamable_http 模块，记录 client 调用参数。"""
    calls = []
    holder = {}

    def fake_client(url, headers=None, **kwargs):
        calls.append({"url": url, "headers": headers})
        return _FakeAsyncCtx((object(), object(), lambda: None))

    def fake_session_class(read, write):
        sess = _FakeSession()
        holder["session"] = sess
        return _FakeAsyncCtx(sess)

    fake_root = type(sys)("mcp")
    fake_root.ClientSession = fake_session_class
    fake_root.StdioServerParameters = lambda **kw: SimpleNamespace(**kw)
    fake_http_mod = type(sys)("mcp.client.streamable_http")
    fake_http_mod.streamablehttp_client = fake_client
    fake_stdio_mod = type(sys)("mcp.client.stdio")
    fake_stdio_mod.stdio_client = lambda params, **kw: _FakeAsyncCtx((object(), object()))

    monkeypatch.setitem(sys.modules, "mcp", fake_root)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", fake_http_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", fake_stdio_mod)
    return calls, holder


def _http_cfg(**over):
    base = {
        "name": "remote",
        "command": "",
        "transport": "http",
        "url": "https://mcp.example.com/mcp",
    }
    base.update(over)
    return McpServerConfig(**base)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    reset_mcp_manager()
    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp__"):
            tool_registry.unregister(name)


@pytest.mark.asyncio
async def test_http_branch_routes_to_streamable_client(fake_http_sdk):
    calls, _ = fake_http_sdk
    mgr = McpManager()
    mgr._configs = {"remote": _http_cfg()}
    mgr._config_loaded = True

    await mgr.connect_server("remote")

    assert calls and calls[0]["url"] == "https://mcp.example.com/mcp"
    assert calls[0]["headers"] is None


@pytest.mark.asyncio
async def test_http_headers_passthrough(fake_http_sdk):
    calls, _ = fake_http_sdk
    mgr = McpManager()
    mgr._configs = {"remote": _http_cfg(headers={"Authorization": "Bearer t1"})}
    mgr._config_loaded = True

    await mgr.connect_server("remote")
    assert calls[0]["headers"] == {"Authorization": "Bearer t1"}


@pytest.mark.asyncio
async def test_http_tools_registered_via_bridge(fake_http_sdk):
    mgr = McpManager()
    mgr._configs = {"remote": _http_cfg(trusted=True)}
    mgr._config_loaded = True

    await mgr.connect_server("remote")

    assert "mcp__remote__ping" in list_tools()
    assert mgr.is_tool_approved("remote", "ping"), "trusted server 自动放行"


@pytest.mark.asyncio
async def test_stdio_config_does_not_touch_http_client(fake_http_sdk):
    calls, _ = fake_http_sdk

    mgr = McpManager()
    mgr._configs = {"local": McpServerConfig(name="local", command="echo", transport="stdio")}
    mgr._config_loaded = True

    await mgr.connect_server("local")
    assert calls == [], "stdio 配置不得触碰 streamable http client"
