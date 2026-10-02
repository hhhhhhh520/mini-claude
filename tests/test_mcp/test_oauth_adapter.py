"""MCP OAuth 适配器测试（mcp SDK 用 sys.modules 假身，回调 server 用真回环 HTTP）。

覆盖：
- parse_callback_url：正常 / OOB urn 形态 / 缺 code / 缺 state / IdP 错误回跳 / 垃圾输入
- McpCallbackServer：真端口绑定、真 HTTP 请求取 code、无关路径 404、超时、关闭幂等
- build_oauth_provider：local/paste 模式路由、构造参数锁定、绑定失败回退、aclose
"""

import asyncio
import sys

import httpx
import pytest

from mini_claude.mcp.config import McpAuthConfig, McpServerConfig
from mini_claude.mcp.oauth import (
    McpCallbackServer,
    McpOAuthError,
    OOB_REDIRECT_URI,
    build_oauth_provider,
    parse_callback_url,
)


class _FakeModel:
    """pydantic 最小假身：__init__ kwargs + model_validate + model_dump。"""

    def __init__(self, **data):
        self._data = dict(data)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

    def model_dump(self, mode="json"):
        return dict(self._data)


class _FakeClientProvider:
    instances = []

    def __init__(
        self,
        server_url,
        client_metadata,
        storage,
        redirect_handler=None,
        callback_handler=None,
        timeout=300.0,
        client_metadata_url=None,
    ):
        self.server_url = server_url
        self.client_metadata = client_metadata
        self.storage = storage
        self.redirect_handler = redirect_handler
        self.callback_handler = callback_handler
        _FakeClientProvider.instances.append(self)


@pytest.fixture
def fake_oauth_sdk(monkeypatch):
    """注入假 mcp.client.auth / mcp.shared.auth，收集 OAuthClientProvider 构造。"""
    _FakeClientProvider.instances = []
    root = type(sys)("mcp")
    client_auth = type(sys)("mcp.client.auth")
    client_auth.OAuthClientProvider = _FakeClientProvider
    shared = type(sys)("mcp.shared.auth")
    shared.OAuthClientMetadata = type("OAuthClientMetadata", (_FakeModel,), {})
    shared.OAuthToken = type("OAuthToken", (_FakeModel,), {})
    shared.OAuthClientInformationFull = type("OAuthClientInformationFull", (_FakeModel,), {})
    monkeypatch.setitem(sys.modules, "mcp", root)
    monkeypatch.setitem(sys.modules, "mcp.client.auth", client_auth)
    monkeypatch.setitem(sys.modules, "mcp.shared.auth", shared)
    return _FakeClientProvider.instances


def _cfg(**auth_over):
    auth = {"mode": "oauth"}
    auth.update(auth_over)
    return McpServerConfig(
        name="remote",
        transport="http",
        url="https://mcp.example.com/mcp",
        auth=McpAuthConfig(**auth),
    )


# ---------- parse_callback_url ----------


def test_parse_normal_https_url():
    code, state = parse_callback_url("http://127.0.0.1:8765/callback?code=C1&state=S1&scope=read")
    assert (code, state) == ("C1", "S1")


def test_parse_oob_urn_form():
    code, state = parse_callback_url("urn:ietf:wg:oauth:2.0:oob?code=C2&state=S2")
    assert (code, state) == ("C2", "S2")


def test_parse_missing_code_rejected():
    with pytest.raises(McpOAuthError, match="code"):
        parse_callback_url("http://127.0.0.1:1/callback?state=S1")


def test_parse_missing_state_rejected():
    with pytest.raises(McpOAuthError, match="state"):
        parse_callback_url("http://127.0.0.1:1/callback?code=C1")


def test_parse_error_redirect_surfaces_reason():
    with pytest.raises(McpOAuthError, match="access_denied"):
        parse_callback_url(
            "http://127.0.0.1:1/callback?error=access_denied"
            "&error_description=%E7%94%A8%E6%88%B7%E6%8B%92%E7%BB%9D&state=S1"
        )


def test_parse_garbage_rejected():
    with pytest.raises(McpOAuthError):
        parse_callback_url("  ")


def test_parse_strips_quotes_and_whitespace():
    code, state = parse_callback_url('  "http://127.0.0.1:1/cb?code=C&state=S"  ')
    assert (code, state) == ("C", "S")


# ---------- McpCallbackServer（真回环 HTTP） ----------


@pytest.mark.asyncio
async def test_callback_server_binds_and_serves_code():
    server = McpCallbackServer()
    await server.start()
    try:
        assert server.redirect_uri.startswith("http://127.0.0.1:")
        assert server.redirect_uri.endswith("/callback")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server.redirect_uri}?code=C9&state=S9", follow_redirects=True
            )
        assert resp.status_code == 200
        assert "授权完成" in resp.text
        assert await server.wait_code(timeout=2.0) == ("C9", "S9")
    finally:
        await server.aclose()


@pytest.mark.asyncio
async def test_callback_server_unrelated_path_gets_404():
    server = McpCallbackServer()
    await server.start()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:{server.port}/favicon.ico")
        assert resp.status_code == 404
        with pytest.raises(asyncio.TimeoutError):
            await server.wait_code(timeout=0.2)
    finally:
        await server.aclose()


@pytest.mark.asyncio
async def test_callback_server_error_redirect_fails_fast():
    """IdP 拒绝授权（error 回跳）必须立刻失败，而不是等满超时。"""
    server = McpCallbackServer()
    await server.start()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{server.redirect_uri}?error=access_denied&state=S1")
        assert resp.status_code == 200
        with pytest.raises(McpOAuthError, match="access_denied"):
            await server.wait_code(timeout=2.0)
    finally:
        await server.aclose()


@pytest.mark.asyncio
async def test_callback_server_wait_times_out_without_request():
    server = McpCallbackServer()
    await server.start()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await server.wait_code(timeout=0.15)
    finally:
        await server.aclose()


@pytest.mark.asyncio
async def test_callback_server_aclose_idempotent():
    server = McpCallbackServer()
    await server.start()
    await server.aclose()
    await server.aclose()  # 幂等
    assert server._server is None


# ---------- build_oauth_provider ----------


@pytest.mark.asyncio
async def test_local_mode_builds_provider_with_callback_redirect_uri(fake_oauth_sdk, tmp_path):
    notify, paste_calls = [], []

    async def paste_reader():
        paste_calls.append(1)
        return ""

    setup = await build_oauth_provider(
        _cfg(), home_dir=tmp_path, notify=notify.append, paste_reader=paste_reader
    )
    try:
        provider = setup.provider
        assert provider.server_url == "https://mcp.example.com/mcp"
        redirect_uris = provider.client_metadata._data["redirect_uris"]
        assert len(redirect_uris) == 1 and redirect_uris[0].startswith("http://127.0.0.1:")
        assert provider.client_metadata._data["token_endpoint_auth_method"] == "none"
        assert set(provider.client_metadata._data["grant_types"]) == {
            "authorization_code",
            "refresh_token",
        }
        assert setup.callback_server is not None
        assert paste_calls == [], "local 模式在未超时前不得询问粘贴"
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_local_mode_scope_passthrough(fake_oauth_sdk, tmp_path):
    setup = await build_oauth_provider(
        _cfg(scope="mcp:read"), home_dir=tmp_path, notify=lambda m: None
    )
    try:
        assert setup.provider.client_metadata._data["scope"] == "mcp:read"
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_local_mode_redirect_handler_notifies_url(fake_oauth_sdk, tmp_path):
    captured = []
    setup = await build_oauth_provider(_cfg(), home_dir=tmp_path, notify=captured.append)
    try:
        await setup.provider.redirect_handler("https://auth.example/authorize?x=1")
        assert any("https://auth.example/authorize?x=1" in m for m in captured)
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_local_mode_callback_handler_returns_browser_result(fake_oauth_sdk, tmp_path):
    setup = await build_oauth_provider(_cfg(), home_dir=tmp_path, notify=lambda m: None)
    try:
        redirect_uri = str(setup.provider.client_metadata._data["redirect_uris"][0])
        async with httpx.AsyncClient() as client:
            await client.get(f"{redirect_uri}?code=CB1&state=ST1")
        code, state = await setup.provider.callback_handler()
        assert (code, state) == ("CB1", "ST1")
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_local_mode_falls_back_to_paste_on_timeout(fake_oauth_sdk, tmp_path, monkeypatch):
    async def fake_wait_code(self, timeout):
        raise asyncio.TimeoutError()

    async def paste_reader():
        return "urn:ietf:wg:oauth:2.0:oob?code=P1&state=PS1"

    monkeypatch.setattr(McpCallbackServer, "wait_code", fake_wait_code)
    captured = []
    setup = await build_oauth_provider(
        _cfg(), home_dir=tmp_path, notify=captured.append, paste_reader=paste_reader
    )
    try:
        code, state = await setup.provider.callback_handler()
        assert (code, state) == ("P1", "PS1")
        assert any("粘贴" in m for m in captured), "超时后必须引导用户粘贴"
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_paste_mode_uses_oob_redirect_uri(fake_oauth_sdk, tmp_path):
    async def paste_reader():
        return "http://127.0.0.1:1/callback?code=PP&state=SS"

    setup = await build_oauth_provider(
        _cfg(callback="paste"), home_dir=tmp_path, notify=lambda m: None, paste_reader=paste_reader
    )
    try:
        assert setup.provider.client_metadata._data["redirect_uris"] == [OOB_REDIRECT_URI]
        assert setup.callback_server is None, "paste 模式不起本地 server"
        code, state = await setup.provider.callback_handler()
        assert (code, state) == ("PP", "SS")
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_bind_failure_falls_back_to_paste(fake_oauth_sdk, tmp_path, monkeypatch):
    async def dead_start(self):
        raise OSError("no sockets in sandbox")

    async def paste_reader():
        return "http://127.0.0.1:1/callback?code=B1&state=BS"

    monkeypatch.setattr(McpCallbackServer, "start", dead_start)
    setup = await build_oauth_provider(
        _cfg(), home_dir=tmp_path, notify=lambda m: None, paste_reader=paste_reader
    )
    try:
        assert setup.provider.client_metadata._data["redirect_uris"] == [OOB_REDIRECT_URI]
    finally:
        await setup.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_callback_server(fake_oauth_sdk, tmp_path):
    setup = await build_oauth_provider(_cfg(), home_dir=tmp_path, notify=lambda m: None)
    assert setup.callback_server is not None
    await setup.aclose()
    assert setup.callback_server._server is None
    await setup.aclose()  # 幂等


@pytest.mark.asyncio
async def test_sdk_missing_raises_import_error(tmp_path, monkeypatch):
    """无 SDK 时直接暴露 ImportError——manager 路径会先转成中文指引。"""
    monkeypatch.setitem(sys.modules, "mcp", None)
    monkeypatch.setitem(sys.modules, "mcp.client.auth", None)
    monkeypatch.setitem(sys.modules, "mcp.shared.auth", None)
    with pytest.raises(ImportError):
        await build_oauth_provider(_cfg(), home_dir=tmp_path, notify=lambda m: None)


@pytest.mark.asyncio
async def test_storage_is_file_backed(fake_oauth_sdk, tmp_path):
    setup = await build_oauth_provider(_cfg(), home_dir=tmp_path, notify=lambda m: None)
    try:
        storage = setup.provider.storage
        await storage.set_tokens(_FakeModel(access_token="tok1", expires_in=60))
        tokens = await storage.get_tokens()
        assert tokens._data["access_token"] == "tok1"
        # 落盘在 home 目录的 mcp-auth 下
        from mini_claude.mcp.token_store import token_file_path

        assert token_file_path("remote", home_dir=tmp_path).exists()
    finally:
        await setup.aclose()
