"""MCP streamable HTTP 的 OAuth 适配层（对齐 Claude Code 的 401 自动授权流）。

职责边界：
- PKCE、动态客户端注册（RFC 7591）、受保护资源发现（RFC 9728）、token 交换与
  过期刷新全部复用 SDK 的 OAuthClientProvider（httpx.Auth——401 时自动触发全流程）
- 本模块只做三件事：回调交互（本地回环 server + 手动粘贴兜底）、TokenStorage
  文件落盘的 pydantic 适配、按配置装配 provider

mcp SDK 只在函数内 import——本模块在无 SDK 环境（CI unit 层）必须可导入可测。

交互形态：
- callback=local（默认）：绑定 127.0.0.1 临时端口作 redirect_uri，打印授权 URL；
  浏览器回跳被 server 接住。超时未回跳 → 转手动粘贴（浏览器地址栏完整 URL，
  含 code 与 state——裸 code 过不了 SDK 的 state 校验）
- callback=paste：不起 server，redirect_uri 用 OOB（urn:ietf:wg:oauth:2.0:oob），
  全程手动粘贴。SSH/无浏览器环境的兜底路径
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..utils.logger import get_logger
from .config import McpAuthConfig, McpServerConfig
from .token_store import FileTokenStorage

logger = get_logger("mini_claude.mcp.oauth")

OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
CALLBACK_WAIT_TIMEOUT = 300.0  # 本地回跳等待上限（SDK 的 timeout 参数并不生效——实测 1.30 只存不用）
_CALLBACK_PORT = 0  # 临时端口，由 OS 分配

_SUCCESS_PAGE = (
    "<html><body><h2>授权完成</h2>"
    "<p>已收到授权响应，请返回 mini-claude 继续使用。</p></body></html>"
)
_DENIED_PAGE = (
    "<html><body><h2>授权未完成</h2>"
    "<p>授权被拒绝或失败，请返回 mini-claude 查看原因并重试。</p></body></html>"
)
_MISS_PAGE = "<html><body><h2>404</h2><p>这不是 mini-claude 的 OAuth 回调地址。</p></body></html>"


class McpOAuthError(RuntimeError):
    """OAuth 交互失败（用户拒绝、缺 code/state、粘贴内容非法等）。"""


def parse_callback_url(url: str) -> Tuple[str, str]:
    """从回调 URL 提取 (code, state)；二者缺一不可。

    兼容 http(s) 本地回跳与 OOB（urn:...?code=...&state=...）两种形态；
    IdP 错误回跳（error=access_denied 等）转成带原因的 McpOAuthError。
    """
    text = (url or "").strip().strip("'\"")
    if not text:
        raise McpOAuthError("回调内容为空——请粘贴浏览器地址栏的完整 URL")
    query = parse_qs(urlparse(text).query)
    if "error" in query:
        reason = query["error"][0] if query["error"] else "unknown_error"
        desc = (query.get("error_description") or [""])[0]
        raise McpOAuthError(f"授权失败：{reason}" + (f"（{desc}）" if desc else ""))
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    if not code:
        raise McpOAuthError("回调 URL 中没有 authorization code——请粘贴完整 URL")
    if not state:
        raise McpOAuthError("回调 URL 中缺少 state（裸 code 无法通过校验）——请粘贴完整 URL")
    return code, state


class McpCallbackServer:
    """本地回环回调 server：接住 IdP 的 302 回跳，取出 code + state。

    future 在 start() 时创建（而非等待时）——浏览器回跳可能早于
    callback_handler 被等待，晚创建会丢结果并挂死整个授权流。
    """

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self.port = 0
        self._server: Optional[asyncio.AbstractServer] = None
        self._future: Optional[asyncio.Future] = None

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.host}:{self.port}/callback"

    async def start(self) -> None:
        self._future = asyncio.get_running_loop().create_future()
        self._server = await asyncio.start_server(self._handle, self.host, _CALLBACK_PORT)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            parts = request_line.decode("latin-1").split(" ")
            path = parts[1] if len(parts) > 1 else "/"
            while True:  # 排掉请求头，浏览器才不会重试
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in (b"\r\n", b"\n", b""):
                    break
            query = parse_qs(urlparse(path).query)
            code = (query.get("code") or [""])[0]
            state = (query.get("state") or [""])[0]
            if "error" in query and self._future and not self._future.done():
                # IdP 错误回跳（用户拒绝等）：立刻失败，不等超时
                reason = query["error"][0] if query["error"] else "unknown_error"
                desc = (query.get("error_description") or [""])[0]
                self._future.set_exception(
                    McpOAuthError(f"授权失败：{reason}" + (f"（{desc}）" if desc else ""))
                )
                self._respond(writer, 200, _DENIED_PAGE)
            elif code and state and self._future and not self._future.done():
                self._future.set_result((code, state))
                self._respond(writer, 200, _SUCCESS_PAGE)
            else:
                self._respond(writer, 404, _MISS_PAGE)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("OAuth 回调请求处理失败", error=str(e))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - 连接收口失败不影响流程
                pass

    @staticmethod
    def _respond(writer: asyncio.StreamWriter, status: int, body: str) -> None:
        reason = "OK" if status == 200 else "Not Found"
        payload = body.encode("utf-8")
        head = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(head.encode("latin-1") + payload)

    async def wait_code(self, timeout: float) -> Tuple[str, str]:
        assert self._future is not None, "wait_code 必须在 start() 之后调用"
        return await asyncio.wait_for(self._future, timeout)

    async def aclose(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


def _default_notify(message: str) -> None:
    print(message)


async def _read_pasted_line(
    notify: Callable[[str], None],
    paste_reader: Optional[Callable[[], Awaitable[str]]],
) -> str:
    """读用户粘贴的回调 URL（可注入 reader；默认阻塞读 stdin 放线程池）。"""
    notify("把浏览器最终停留页面的完整 URL（含 code 与 state）粘贴进来后回车：")
    if paste_reader is not None:
        line = await paste_reader()
    else:
        line = await asyncio.to_thread(input)
    return (line or "").strip()


class _SdkTokenStorage:
    """FileTokenStorage 的 SDK 适配层：OAuthToken/OAuthClientInformationFull ↔ dict。"""

    def __init__(self, inner: FileTokenStorage):
        self._inner = inner

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        raw = await self._inner.get_tokens()
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens) -> None:
        await self._inner.set_tokens(tokens)  # pydantic 模型由 _to_plain 收

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        raw = await self._inner.get_client_info()
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info) -> None:
        await self._inner.set_client_info(client_info)


@dataclass
class OAuthSetup:
    """build_oauth_provider 的产物：provider 进连接，aclose 进连接的收口栈。

    last_error 是授权流里记录的真实失败原因——授权流异常穿过 SDK 的
    anyio 任务组后常被取消风暴顶掉（实测），manager 收口时用它还原。
    """

    provider: Any  # mcp.client.auth.OAuthClientProvider（httpx.Auth）
    callback_server: Optional[McpCallbackServer]
    aclose: Callable[[], Awaitable[None]]
    _flow_error: List[Exception] = field(default_factory=list)

    @property
    def last_error(self) -> Optional[Exception]:
        return self._flow_error[-1] if self._flow_error else None


async def build_oauth_provider(
    cfg: McpServerConfig,
    *,
    home_dir: Optional[Any] = None,
    notify: Optional[Callable[[str], None]] = None,
    paste_reader: Optional[Callable[[], Awaitable[str]]] = None,
) -> OAuthSetup:
    """按配置装配 OAuthClientProvider。

    local 模式起本地回调 server（失败回退 paste）；OOB/粘贴路径在
    SSH/无浏览器环境可用。授权 URL 经 notify 展示给用户。
    """
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    notify = notify or _default_notify
    auth = cfg.auth or McpAuthConfig()

    server: Optional[McpCallbackServer] = None
    mode = auth.callback
    if mode == "local":
        server = McpCallbackServer()
        try:
            await server.start()
        except OSError as e:
            logger.warning(
                "OAuth 本地回调绑定失败，回退手动粘贴模式", server=cfg.name, error=str(e)
            )
            server = None
            mode = "paste"

    redirect_uri = server.redirect_uri if server else OOB_REDIRECT_URI
    flow_error: List[Exception] = []

    async def redirect_handler(url: str) -> None:
        notify("请在浏览器中打开以下 URL 完成 MCP server 授权：")
        notify(url)
        if server is None:
            notify(f"（redirect_uri 为 {OOB_REDIRECT_URI}：授权完成后粘贴回跳 URL）")

    async def callback_handler() -> Tuple[str, str]:
        try:
            if server is not None:
                try:
                    return await server.wait_code(timeout=CALLBACK_WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    notify("本地回调等待超时，转入手动粘贴模式……")
            line = await _read_pasted_line(notify, paste_reader)
            return parse_callback_url(line)
        except McpOAuthError as e:
            flow_error.append(e)  # 真实原因留给 manager 在取消风暴后还原
            raise

    async def aclose() -> None:
        if server is not None:
            await server.aclose()

    metadata = OAuthClientMetadata(
        client_name=auth.client_name,
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=auth.scope or None,
    )
    provider = OAuthClientProvider(
        server_url=cfg.url,
        client_metadata=metadata,
        storage=_SdkTokenStorage(FileTokenStorage(cfg.name, home_dir)),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
    return OAuthSetup(
        provider=provider, callback_server=server, aclose=aclose, _flow_error=flow_error
    )
