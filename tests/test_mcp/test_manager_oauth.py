"""MCP manager 的 OAuth 接线测试（sys.modules 假 SDK）。

锁定契约：
- http + auth 配置 → build_oauth_provider 产物作为 auth= 传给 streamablehttp_client
- http 无 auth / stdio → auth=None，不触碰 OAuth 装配
- 授权失败异常被 connect_all 隔离成 errors dict（不阻断其他 server）
- status() 报告 auth 模式与 token 落盘摘要；token_home 可注入（测试不碰真 home）
- /mcp 状态文本展示 auth 标签
"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mini_claude.mcp.config import McpServerConfig
from mini_claude.mcp.manager import McpManager, reset_mcp_manager
from mini_claude.mcp.token_store import FileTokenStorage
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


class _FakeModel:
    def __init__(self, **data):
        self._data = dict(data)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

    def model_dump(self, mode="json"):
        return dict(self._data)


class _FakeOAuthProvider:
    instances = []


@pytest.fixture
def fake_sdk(monkeypatch):
    """假 mcp 全家桶：client/streamable_http 捕获调用参数，client.auth 提供 OAuth 假身。"""
    calls = []
    _FakeOAuthProvider.instances = []

    def fake_client(url, headers=None, auth=None, **kwargs):
        calls.append({"url": url, "headers": headers, "auth": auth})
        return _FakeAsyncCtx((object(), object(), lambda: None))

    def fake_session_class(read, write):
        return _FakeAsyncCtx(_FakeSession())

    root = type(sys)("mcp")
    root.ClientSession = fake_session_class
    root.StdioServerParameters = lambda **kw: SimpleNamespace(**kw)

    http_mod = type(sys)("mcp.client.streamable_http")
    http_mod.streamablehttp_client = fake_client
    stdio_mod = type(sys)("mcp.client.stdio")
    stdio_mod.stdio_client = lambda params, **kw: _FakeAsyncCtx((object(), object()))

    client_auth = type(sys)("mcp.client.auth")

    class FakeOAuthClientProvider:
        def __init__(self, server_url, client_metadata, storage, **kwargs):
            self.server_url = server_url
            self.client_metadata = client_metadata
            self.storage = storage
            self.kwargs = kwargs
            _FakeOAuthProvider.instances.append(self)

    client_auth.OAuthClientProvider = FakeOAuthClientProvider

    shared = type(sys)("mcp.shared.auth")
    shared.OAuthClientMetadata = type("OAuthClientMetadata", (_FakeModel,), {})
    shared.OAuthToken = type("OAuthToken", (_FakeModel,), {})
    shared.OAuthClientInformationFull = type("OAuthClientInformationFull", (_FakeModel,), {})

    monkeypatch.setitem(sys.modules, "mcp", root)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", http_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", stdio_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.auth", client_auth)
    monkeypatch.setitem(sys.modules, "mcp.shared.auth", shared)
    return calls


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    reset_mcp_manager()
    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp__"):
            tool_registry.unregister(name)


def _http_cfg(**over):
    base = {"name": "remote", "command": "", "transport": "http", "url": "https://x.example/mcp"}
    base.update(over)
    return McpServerConfig(**base)


def _mgr(tmp_path, cfg):
    mgr = McpManager(token_home=tmp_path)
    mgr._configs = {cfg.name: cfg}
    mgr._config_loaded = True
    return mgr


@pytest.mark.asyncio
async def test_http_auth_passes_provider_to_client(fake_sdk, tmp_path):
    mgr = _mgr(
        tmp_path,
        _http_cfg(
            auth=SimpleNamespace(
                mode="oauth", scope="", callback="local", client_name="mini-claude"
            )
        ),
    )

    await mgr.connect_server("remote")

    assert fake_sdk[0]["auth"] is _FakeOAuthProvider.instances[-1], (
        "auth 配置必须装配 provider 并透传"
    )


@pytest.mark.asyncio
async def test_http_without_auth_passes_none(fake_sdk, tmp_path):
    mgr = _mgr(tmp_path, _http_cfg())
    await mgr.connect_server("remote")
    assert fake_sdk[0]["auth"] is None


@pytest.mark.asyncio
async def test_stdio_never_builds_oauth_provider(fake_sdk, tmp_path):
    mgr = _mgr(
        tmp_path,
        McpServerConfig(name="local", command="echo", transport="stdio"),
    )
    await mgr.connect_server("local")
    assert fake_sdk == [], "stdio 不得触碰 http client"
    assert _FakeOAuthProvider.instances == []


@pytest.mark.asyncio
async def test_oauth_failure_isolated_in_connect_all(fake_sdk, tmp_path, monkeypatch):
    """授权失败（如用户拒绝）只进 errors dict，不炸其他 server。"""
    from mini_claude.mcp import oauth as oauth_mod

    async def boom(cfg, **kwargs):
        raise RuntimeError("授权失败：access_denied")

    monkeypatch.setattr(oauth_mod, "build_oauth_provider", boom)

    good = McpServerConfig(name="good", transport="http", url="https://g.example/mcp")
    bad = _http_cfg(
        auth=SimpleNamespace(mode="oauth", scope="", callback="local", client_name="mini-claude")
    )
    mgr = McpManager(token_home=tmp_path)
    mgr._configs = {good.name: good, bad.name: bad}
    mgr._config_loaded = True

    connected, errors = await mgr.connect_all()
    assert connected == ["good"]
    assert "remote" in errors and "授权失败" in errors["remote"]


@pytest.mark.asyncio
async def test_status_reports_auth_with_token_summary(fake_sdk, tmp_path):
    store = FileTokenStorage("remote", home_dir=tmp_path)
    await store.set_tokens({"access_token": "t", "expires_in": 3600})

    mgr = _mgr(
        tmp_path,
        _http_cfg(
            auth=SimpleNamespace(
                mode="oauth", scope="", callback="local", client_name="mini-claude"
            )
        ),
    )
    info = mgr.status()["remote"]
    assert info["auth"] == "oauth"
    assert info["auth_token"]["has_tokens"] is True
    assert info["auth_token"]["expires_at"] is not None


@pytest.mark.asyncio
async def test_status_reports_auth_without_tokens(fake_sdk, tmp_path):
    mgr = _mgr(
        tmp_path,
        _http_cfg(
            auth=SimpleNamespace(
                mode="oauth", scope="", callback="local", client_name="mini-claude"
            )
        ),
    )
    info = mgr.status()["remote"]
    assert info["auth"] == "oauth"
    assert info["auth_token"] is None


@pytest.mark.asyncio
async def test_status_auth_none_when_unconfigured(fake_sdk, tmp_path):
    mgr = _mgr(tmp_path, _http_cfg())
    info = mgr.status()["remote"]
    assert info["auth"] is None
    assert info["auth_token"] is None


def test_mcp_handler_status_shows_oauth_tag(tmp_path):
    from mini_claude.cli.commands.mcp_handler import McpCommandHandler

    manager = SimpleNamespace(
        has_config=lambda: True,
        status=lambda: {
            "remote": {
                "connected": True,
                "tools": 3,
                "trusted": False,
                "transport": "http",
                "command": "",
                "url": "https://x.example/mcp",
                "error": None,
                "auth": "oauth",
                "auth_token": {
                    "has_tokens": True,
                    "has_client_info": True,
                    "obtained_at": 1.0,
                    "expires_at": 3601.0,
                },
            },
            "plain": {
                "connected": False,
                "tools": 0,
                "trusted": False,
                "transport": "http",
                "command": "",
                "url": "https://y.example/mcp",
                "error": None,
                "auth": None,
                "auth_token": None,
            },
        },
    )
    text = McpCommandHandler()._format_status(manager)
    assert "oauth" in text
    assert "token" in text
    assert "plain" in text and "oauth" not in text.split("plain")[1].splitlines()[0]


def test_mcp_handler_status_oauth_no_token_hint(tmp_path):
    from mini_claude.cli.commands.mcp_handler import McpCommandHandler

    manager = SimpleNamespace(
        has_config=lambda: True,
        status=lambda: {
            "remote": {
                "connected": False,
                "tools": 0,
                "trusted": False,
                "transport": "http",
                "command": "",
                "url": "https://x.example/mcp",
                "error": None,
                "auth": "oauth",
                "auth_token": None,
            },
        },
    )
    text = McpCommandHandler()._format_status(manager)
    assert "oauth" in text and "未授权" in text


def test_list_tools_unaffected_by_oauth(monkeypatch):
    """OAuth 只影响连接层，工具命名 mcp__<server>__<tool> 不变。"""
    from mini_claude.mcp.bridge import register_server_tools

    assert "mcp__remote__ping" not in list_tools()
    conn = SimpleNamespace(
        server="remote",
        session=object(),
        tools=[SimpleNamespace(name="ping", description="p", inputSchema={})],
    )
    register_server_tools(SimpleNamespace(), conn)
    try:
        assert "mcp__remote__ping" in list_tools()
    finally:
        tool_registry.unregister("mcp__remote__ping")
