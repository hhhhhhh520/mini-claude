"""MCP OAuth 真 E2E（本机回环，真 mcp SDK + 真 FastMCP + 进程内假 IdP）。

服务端：FastMCP(auth=AuthSettings, auth_server_provider=FakeIdpProvider) ——
SDK 原生挂 /.well-known/oauth-protected-resource、/.well-known/oauth-authorization-server、
/register、/authorize、/token，/mcp 由 Bearer 中间件把守。

客户端：走 mini_claude 真连接链路（config → manager → oauth 适配器 → SDK
OAuthClientProvider），浏览器由测试模拟（notify 捕获授权 URL 后真 GET）。

mcp/uvicorn 在 [dev] extra 里，CI 全矩阵真跑本文件（每矩阵约 30s）；
importorskip 仅作无 SDK 环境的兜底。
"""

import asyncio
import json
import secrets
import socket
import time
from urllib.parse import urlparse

import httpx
import pytest

pytest.importorskip("mcp")
pytest.importorskip("uvicorn")

from mcp.server.auth.provider import (  # noqa: E402
    AccessToken,
    AuthorizationCode,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken  # noqa: E402

from mini_claude.mcp import oauth as oauth_mod  # noqa: E402
from mini_claude.mcp.config import load_mcp_config  # noqa: E402
from mini_claude.mcp.manager import get_mcp_manager, reset_mcp_manager  # noqa: E402
from mini_claude.mcp.token_store import FileTokenStorage  # noqa: E402
from mini_claude.tools import execute_tool, list_tools  # noqa: E402


class FakeIdpProvider:
    """测试双 IdP：实现 OAuthAuthorizationServerProvider 协议。

    auto_approve=True 时 /authorize 直接发 code 302 回跳（无人工同意页）；
    False 时回 error=access_denied（模拟用户拒绝）。expires_in 控制 token 寿命。
    """

    def __init__(self, expires_in: int = 3600, auto_approve: bool = True):
        self.clients: dict = {}
        self.codes: dict = {}
        self.access_tokens: dict = {}
        self.refresh_tokens: dict = {}
        self.expires_in = expires_in
        self.auto_approve = auto_approve
        self.calls: dict = {}

    def _tick(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._tick("register_client")
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client, params) -> str:
        self._tick("authorize")
        if not self.auto_approve:
            raise AuthorizeError(error="access_denied", error_description="用户拒绝授权")
        code = secrets.token_urlsafe(24)
        self.codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client, authorization_code: str):
        return self.codes.get(authorization_code)

    def _issue_tokens(self, client, scopes, resource) -> OAuthToken:
        access = secrets.token_urlsafe(24)
        refresh = secrets.token_urlsafe(24)
        now = int(time.time())
        self.access_tokens[access] = AccessToken(
            token=access,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=now + self.expires_in,
            resource=resource,
        )
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=now + 86400,
            resource=resource,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self.expires_in,
            refresh_token=refresh,
        )

    async def exchange_authorization_code(self, client, authorization_code) -> OAuthToken:
        self._tick("exchange_authorization_code")
        return self._issue_tokens(client, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client, refresh_token: str):
        return self.refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(self, client, refresh_token, scopes) -> OAuthToken:
        self._tick("exchange_refresh_token")
        self.refresh_tokens.pop(refresh_token.token, None)  # 轮换：旧的作废
        return self._issue_tokens(client, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self.access_tokens.get(token)
        if at is None:
            return None
        if at.expires_at is not None and at.expires_at < time.time():
            return None
        return at

    async def revoke_token(self, token) -> None:
        self.access_tokens.pop(getattr(token, "token", ""), None)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _start_oauth_server(expires_in: int = 3600, auto_approve: bool = True):
    """进程内起带 OAuth 的 FastMCP，返回 (base_url, provider, server, task)。"""
    import uvicorn

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    provider = FakeIdpProvider(expires_in=expires_in, auto_approve=auto_approve)
    mcp = FastMCP(
        "oauth-e2e",
        host="127.0.0.1",
        port=port,
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=base,
            validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        ),
        auth_server_provider=provider,
    )

    @mcp.tool()
    def echo(text: str) -> str:
        """原样返回输入文本"""
        return text

    app = mcp.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.get_running_loop().create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started, "uvicorn 未能在 5s 内启动"
    return base, provider, server, task


async def _stop_server(server, task) -> None:
    server.should_exit = True
    await task


def _write_config(tmp_path, url, auth) -> None:
    cfg_dir = tmp_path / ".mini-claude"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"remote": {"type": "http", "url": url, "auth": auth}}}),
        encoding="utf-8",
    )


def _fresh_manager(tmp_path):
    """干净 manager：token 落盘在 tmp（不碰真 home）。"""
    reset_mcp_manager()
    mgr = get_mcp_manager()
    mgr._token_home = tmp_path / "home"
    return mgr


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    reset_mcp_manager()
    from mini_claude.tools import tool_registry

    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp"):
            tool_registry.unregister(name)


@pytest.mark.asyncio
async def test_oauth_full_flow_local_callback(tmp_path, monkeypatch):
    """全流程：401 → PRM/AS 发现 → 动态注册 → PKCE 授权 → 本地回调收 code →
    token 交换 → Bearer 调用 → token 落盘。"""
    base, provider, server, task = await _start_oauth_server()
    try:
        _write_config(tmp_path, f"{base}/mcp", "oauth")
        configs, warnings = load_mcp_config(workspace_root=tmp_path)
        assert not warnings, warnings

        browser_urls = []

        def fake_notify(message):
            if isinstance(message, str) and message.startswith(base):
                browser_urls.append(message)
                asyncio.get_running_loop().create_task(_browse(message))

        async def _browse(url):
            async with httpx.AsyncClient() as client:
                await client.get(url, follow_redirects=True)  # 302 回跳 → 本地回调 server

        monkeypatch.setattr(oauth_mod, "_default_notify", fake_notify)

        mgr = _fresh_manager(tmp_path)
        mgr._configs = configs
        mgr._config_loaded = True

        await mgr.connect_server("remote")
        assert "mcp__remote__echo" in list_tools()

        # IdP 侧看到了完整链路：注册 → 授权 → code 交换
        assert provider.calls.get("register_client") == 1
        assert provider.calls.get("authorize") == 1
        assert provider.calls.get("exchange_authorization_code") == 1
        assert browser_urls, "授权 URL 必须展示给用户"

        # Bearer token 真实生效：工具调用过资源服务器鉴权
        mgr.approve_tool("remote", "echo")
        assert await execute_tool("mcp__remote__echo", {"text": "ping"}) == "ping"

        # token 落盘且是 IdP 签发的那枚
        store = FileTokenStorage("remote", home_dir=tmp_path / "home")
        tokens = await store.get_tokens()
        assert tokens and tokens["access_token"] in provider.access_tokens

        # 状态可见
        info = mgr.status()["remote"]
        assert info["auth"] == "oauth"
        assert info["auth_token"]["has_tokens"] is True

        await mgr.disconnect_server("remote")
    finally:
        await _stop_server(server, task)


async def _browse_final_url(url: str) -> str:
    """最小"浏览器"：GET 后不跟随 302，返回 Location（等价于地址栏最终 URL）。

    httpx 1.x 对 302 的 Location 无条件做 redirect request 构建（follow_redirects=False
    也一样），urn: OOB 形态会炸 InvalidURL——手工 socket 绕开，也更贴近真实浏览器。
    """
    parsed = urlparse(url)
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    writer.write(
        f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\nConnection: close\r\n\r\n".encode()
    )
    await writer.drain()
    raw = await reader.read()
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    head = raw.decode("latin-1", errors="replace")
    status = head.splitlines()[0].split(" ")[1] if head else ""
    if status == "302":
        for line in head.splitlines():
            if line.lower().startswith("location:"):
                return line.split(":", 1)[1].strip()
    return head


@pytest.mark.asyncio
async def test_oauth_paste_mode_with_oob(tmp_path, monkeypatch):
    """粘贴兜底：redirect_uri 用 OOB，"用户"（测试）从 302 Location 取回跳 URL 粘贴。"""
    base, provider, server, task = await _start_oauth_server()
    try:
        _write_config(tmp_path, f"{base}/mcp", {"mode": "oauth", "callback": "paste"})
        configs, warnings = load_mcp_config(workspace_root=tmp_path)
        assert not warnings, warnings

        captured = {}

        def fake_notify(message):
            if isinstance(message, str) and message.startswith(base):
                captured["url"] = message

        async def fake_read_pasted_line(notify, paste_reader):
            assert "url" in captured, "粘贴提示前必须先展示授权 URL"
            return await _browse_final_url(captured["url"])  # 模拟复制地址栏

        monkeypatch.setattr(oauth_mod, "_default_notify", fake_notify)
        monkeypatch.setattr(oauth_mod, "_read_pasted_line", fake_read_pasted_line)

        mgr = _fresh_manager(tmp_path)
        mgr._configs = configs
        mgr._config_loaded = True

        await mgr.connect_server("remote")
        assert provider.calls.get("authorize") == 1
        assert provider.calls.get("exchange_authorization_code") == 1
        tokens = await FileTokenStorage("remote", home_dir=tmp_path / "home").get_tokens()
        assert tokens["access_token"] in provider.access_tokens
        await mgr.disconnect_server("remote")
    finally:
        await _stop_server(server, task)


@pytest.mark.asyncio
async def test_oauth_refresh_after_expiry(tmp_path, monkeypatch):
    """过期刷新：把 SDK 本地令牌到期时间拨到过去，下一次请求前自动刷新。

    刻意不用 expires_in=1 + sleep 的真实时钟竞态——CI 慢机上连接阶段本身
    超过 1 秒会强行触发"连接内刷新"，踩进 ISSUE-030 取消风暴高发窗口
    （2026-10-03 定时 CI 实测 flaky：push 绿、schedule 红）。连接阶段用
    长命 token，刷新由确定性拨表触发（provider.context 是 1.30 的公开
    属性，constraints 锁 1.30）。
    """
    base, provider, server, task = await _start_oauth_server()
    try:
        _write_config(tmp_path, f"{base}/mcp", "oauth")
        configs, _ = load_mcp_config(workspace_root=tmp_path)

        async def _browse(url):
            async with httpx.AsyncClient() as client:
                await client.get(url, follow_redirects=True)

        def fake_notify(message):
            if isinstance(message, str) and message.startswith(base):
                asyncio.get_running_loop().create_task(_browse(message))

        monkeypatch.setattr(oauth_mod, "_default_notify", fake_notify)

        mgr = _fresh_manager(tmp_path)
        mgr._configs = configs
        mgr._config_loaded = True
        await mgr.connect_server("remote")
        mgr.approve_tool("remote", "echo")

        store = FileTokenStorage("remote", home_dir=tmp_path / "home")
        first_token = (await store.get_tokens())["access_token"]

        # 拨表：SDK 本地到期时间拨到过去 → is_token_valid()=False 且
        # can_refresh_token()=True → 下一次请求前走刷新路径
        conn = mgr._connections["remote"]
        conn.oauth_setup.provider.context.token_expiry_time = time.time() - 1

        assert await execute_tool("mcp__remote__echo", {"text": "hi"}) == "hi"

        assert provider.calls.get("exchange_refresh_token") == 1, "过期后必须走刷新而非重新授权"
        assert provider.calls.get("authorize") == 1, "刷新路径不得重新发起人工授权"
        second_token = (await store.get_tokens())["access_token"]
        assert second_token != first_token
        await mgr.disconnect_server("remote")
    finally:
        await _stop_server(server, task)


@pytest.mark.asyncio
async def test_oauth_user_denial_fails_fast_without_connection(tmp_path, monkeypatch):
    """用户拒绝：error 回跳立刻失败、连接不残留，错误信息带原因。"""
    base, provider, server, task = await _start_oauth_server(auto_approve=False)
    try:
        _write_config(tmp_path, f"{base}/mcp", "oauth")
        configs, _ = load_mcp_config(workspace_root=tmp_path)

        async def _browse(url):
            async with httpx.AsyncClient() as client:
                await client.get(url, follow_redirects=True)  # 302 error=access_denied

        def fake_notify(message):
            if isinstance(message, str) and message.startswith(base):
                asyncio.get_running_loop().create_task(_browse(message))

        monkeypatch.setattr(oauth_mod, "_default_notify", fake_notify)

        mgr = _fresh_manager(tmp_path)
        mgr._configs = configs
        mgr._config_loaded = True

        with pytest.raises(Exception) as exc_info:
            await mgr.connect_server("remote")
        assert "access_denied" in str(exc_info.value)
        assert "remote" not in mgr._connections, "失败的授权不得留下半死连接"
    finally:
        await _stop_server(server, task)


@pytest.mark.asyncio
async def test_oauth_required_server_without_auth_config_errors_isolated(tmp_path):
    """对 OAuth server 用无 auth 配置 → 401 → 连接失败进 errors dict，不炸进程。"""
    base, provider, server, task = await _start_oauth_server()
    try:
        _write_config(tmp_path, f"{base}/mcp", None)
        # auth: None → 配置层落成无 auth 字段
        configs, _ = load_mcp_config(workspace_root=tmp_path)
        assert configs["remote"].auth is None

        mgr = _fresh_manager(tmp_path)
        mgr._configs = configs
        mgr._config_loaded = True

        connected, errors = await mgr.connect_all()
        assert connected == []
        assert "remote" in errors, "无凭据必须明确失败，不得静默半连"
    finally:
        await _stop_server(server, task)
