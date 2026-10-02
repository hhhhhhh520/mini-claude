"""MCP 连接管理器（P2）。

职责：
- 读取配置、按 server 建 stdio 连接（官方 mcp SDK），发现工具并注册进 ToolRegistry
- 连接生命周期：AsyncExitStack 托管 stdio_client + ClientSession，
  close_all() 统一关闭（REPL finally 与路径确认同级别的退出纪律）
- 确认通道：默认每个工具调用前需要用户放行；trusted server 自动放行；
  放行记录在会话内存（不持久化——每次启动重新确认，安全默认值）
- SDK 缺失时给中文指引（McpSDKMissingError），绝不静默

SDK 版本纪律：pin 在 1.x（mcp>=1.30.0,<2.0.0）。2.x 改了公开 API
（FastMCP→MCPServer 等），未验证前不跟。
"""

import asyncio
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple


from ..config.settings import settings
from ..utils.logger import get_logger
from .bridge import register_server_tools, unregister_server_tools
from .config import McpServerConfig, load_mcp_config
from .token_store import FileTokenStorage

logger = get_logger("mini_claude.mcp.manager")

MCP_CONFIRM_PREFIX = "mcp:"

_HTTP_CONNECT_TIMEOUT_SECONDS = 30.0  # 无交互流 http 连接的 initialize 上限（见 _open_connection）


class McpSDKMissingError(RuntimeError):
    """mcp SDK 未安装。"""


class McpConnectError(RuntimeError):
    """MCP server 连接失败（含 OAuth 授权失败）。"""


def _extract_connect_failure(e: BaseException) -> Optional[BaseException]:
    """从连接失败的异常组中提取真实原因。

    授权流/初始化在 SDK 的 anyio 任务组内失败时，原始异常会被取消风暴
    顶掉并以异常组（含 CancelledError 成员）呈现（实测：401 场景到达
    调用方的是 WouldBlock→"Cancelled via cancel scope" 链，或含取消成员
    的异常组）——提取非取消叶子异常作为真实原因；全是取消成员时返回
    None，由调用方把取消伪装按连接失败呈现（连接阶段无自然取消源，
    REPL 收口不走本路径）。

    异常组用 exceptions 属性鸭子特征识别（3.11 内建 / 3.10 是
    exceptiongroup backport，项目要同时支持，不能按名字 import）。
    """
    pending: List[BaseException] = [e]
    while pending:
        x = pending.pop()
        sub_excs = getattr(x, "exceptions", None)
        if isinstance(sub_excs, tuple):
            pending.extend(sub_excs)
            continue
        if isinstance(x, (asyncio.CancelledError, GeneratorExit)):
            continue
        return x
    return None


def _approve_key(server: str, tool: str) -> str:
    return f"{server}:{tool}"


def approve_confirmation_key(key: str) -> bool:
    """处理 pending_confirmation_path 中的 MCP 确认键。

    REPL 的 'yes' 分支先调它：是 mcp:<server>:<tool> 则放行对应工具并返回 True；
    其他 key 返回 False，走原有 approve_path 逻辑。
    """
    if not key.startswith(MCP_CONFIRM_PREFIX):
        return False
    parts = key[len(MCP_CONFIRM_PREFIX) :].split(":", 1)
    if len(parts) != 2:
        logger.warning("malformed mcp confirmation key", key=key)
        return True
    get_mcp_manager().approve_tool(parts[0], parts[1])
    return True


class McpManager:
    """MCP server 连接与工具注册的管理器（进程内单例）。"""

    def __init__(self, token_home=None):
        self._configs: Dict[str, McpServerConfig] = {}
        self._connections: Dict[str, object] = {}
        self._approved: set = set()
        self._config_loaded = False
        self._token_home = token_home  # OAuth token 落盘根；None → ~/.mini-claude

    # ---------- 配置 ----------

    def _ensure_configs(self) -> Dict[str, McpServerConfig]:
        if not self._config_loaded:
            self._configs, warnings = load_mcp_config(settings.workspace_root)
            for w in warnings:
                logger.warning("mcp config warning", warning=w)
            self._config_loaded = True
        return self._configs

    def reload_config(self) -> List[str]:
        self._config_loaded = False
        _, warnings = self._ensure_configs()
        return warnings

    def has_config(self) -> bool:
        return bool(self._ensure_configs())

    # ---------- SDK ----------

    def _load_sdk(self):
        import mcp  # noqa: F401

        return mcp

    async def _open_connection(self, cfg: McpServerConfig):
        """建立连接（stdio 或 streamable http）并完成 initialize + 工具发现。

        Returns:
            SimpleNamespace(server, session, tools, stack)
        """
        from contextlib import AsyncExitStack

        try:
            self._load_sdk()
        except ImportError as e:
            raise McpSDKMissingError(
                'MCP 支持未安装。请运行: pip install -e ".[mcp]" （或 pip install "mcp>=1.30.0,<2.0.0"）'
            ) from e

        stack = AsyncExitStack()
        oauth_setup = None  # http+auth 时持有 OAuthSetup（异常翻译用）
        try:
            if cfg.transport == "http":
                from mcp import ClientSession
                from mcp.client.streamable_http import streamablehttp_client

                # OAuth：401 触发授权流（SDK httpx.Auth 内建）；失败随连接异常上抛，
                # 由 connect_all/connect_server 的错误隔离兜住，不阻断其他 server
                auth_provider = None
                if cfg.auth is not None:
                    from .oauth import build_oauth_provider

                    oauth_setup = await build_oauth_provider(cfg, home_dir=self._token_home)
                    auth_provider = oauth_setup.provider
                    stack.push_async_callback(oauth_setup.aclose)

                read, write, _get_session_id = await stack.enter_async_context(
                    streamablehttp_client(cfg.url, headers=cfg.headers or None, auth=auth_provider)
                )
            else:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=cfg.env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))

            session = await stack.enter_async_context(ClientSession(read, write))
            if cfg.transport == "http" and oauth_setup is None:
                # 无交互流的 http 连接限时：SDK 任务组偶发僵死会让 initialize
                # 永久挂起（实测，同进程内反复连接后触发）——30s 无进展即失败。
                # 带 OAuth 的连接不限时：首次 401 会进交互式授权（用户开浏览器）。
                try:
                    await asyncio.wait_for(
                        session.initialize(), timeout=_HTTP_CONNECT_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError as e:
                    raise McpConnectError(
                        f"MCP server '{cfg.name}' 连接超时"
                        f"（{_HTTP_CONNECT_TIMEOUT_SECONDS:.0f}s 无进展），请检查服务端可用性"
                    ) from e
            else:
                await session.initialize()
            tools_result = await session.list_tools()
            return SimpleNamespace(
                server=cfg.name, session=session, tools=list(tools_result.tools), stack=stack
            )
        except BaseException as e:  # noqa: BLE001
            # 收口可能因 anyio 生成器/取消风暴抛次生异常（ISSUE-029 同族，
            # OAuth 授权流在 initialize 内失败时实测必现）——吞掉次生异常，
            # 保原始异常为主向外抛
            try:
                await stack.aclose()
            except BaseException as close_err:  # noqa: BLE001
                logger.warning(
                    "MCP 连接收口失败",
                    server=cfg.name,
                    error=f"{type(close_err).__name__}: {close_err}",
                )
            if oauth_setup is not None and oauth_setup.last_error is not None:
                from .oauth import McpOAuthError

                raise McpOAuthError(
                    f"MCP server '{cfg.name}' OAuth 授权失败：{oauth_setup.last_error}"
                ) from e
            if isinstance(e, McpConnectError):
                raise  # 超时路径已翻译，直接透传
            real = _extract_connect_failure(e) or e
            if isinstance(e, GeneratorExit):
                raise  # 解释器收口语义不翻译
            raise McpConnectError(
                f"MCP server '{cfg.name}' 连接失败：{type(real).__name__}: {real}"
            ) from e

    # ---------- 连接 ----------

    async def connect_server(self, name: str) -> object:
        configs = self._ensure_configs()
        if name not in configs:
            raise KeyError(f"未配置的 MCP server: {name}")
        if name in self._connections:
            return self._connections[name]  # 幂等：已连接直接返回

        cfg = configs[name]
        conn = await self._open_connection(cfg)
        self._connections[name] = conn
        register_server_tools(self, conn)
        # resources/prompts 全局工具：首次连接时幂等注册（MCP 关闭时不占列表）
        from .global_tools import ensure_global_tools_registered

        ensure_global_tools_registered()

        if cfg.trusted:
            for t in conn.tools:
                self._approved.add(_approve_key(name, t.name))

        logger.info("MCP server connected", server=name, tools=len(conn.tools))
        return conn

    async def connect_all(self) -> Tuple[List[str], Dict[str, str]]:
        """连接全部已配置 server。单个失败不拖垮其他，错误进返回值。"""
        configs = self._ensure_configs()
        connected: List[str] = []
        errors: Dict[str, str] = {}
        for name in configs:
            try:
                await self.connect_server(name)
                connected.append(name)
            except Exception as e:
                errors[name] = f"{type(e).__name__}: {e}"
                logger.warning("MCP server connect failed", server=name, error=str(e))
        return connected, errors

    async def disconnect_server(self, name: str) -> None:
        """断开并收口一条连接。任何失败只记日志，不中断退出链路。

        约束：aclose **必须在进入连接的同一任务里直接 await**——anyio 的
        cancel scope 跨任务退出会炸 "Attempted to exit cancel scope in a
        different task"（实测踩中）；wait_for/隔离任务都会改变任务归属。
        代 价是超时不可控：若 anyio 内部取消风暴抛 CancelledError
        （BaseException，实测踩中）或子进程僵死拖住，这里选择吞掉/
        等待到底——REPL 退出场景下用户已按 /exit，干净地卡在收口
        好过留下半死的 MCP 子进程。
        """
        conn = self._connections.pop(name, None)
        if conn is None:
            return
        unregister_server_tools(name)
        try:
            await conn.stack.aclose()
        except BaseException as e:  # noqa: BLE001 - 收口路径吞掉一切（含 CancelledError）
            logger.warning(
                "MCP connection close failed",
                server=name,
                error=f"{type(e).__name__}: {e}",
            )
        logger.info("MCP server disconnected", server=name)

    async def close_all(self) -> None:
        for name in list(self._connections):
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.warning("MCP disconnect failed", server=name, error=str(e))

    # ---------- 状态与确认 ----------

    def status(self) -> Dict[str, dict]:
        self._ensure_configs()
        out: Dict[str, dict] = {}
        for name, cfg in self._configs.items():
            conn = self._connections.get(name)
            token_summary = None
            if cfg.auth is not None:
                token_summary = FileTokenStorage(name, home_dir=self._token_home).snapshot()
            out[name] = {
                "connected": conn is not None,
                "tools": len(conn.tools) if conn else 0,
                "trusted": cfg.trusted,
                "transport": cfg.transport,
                "command": cfg.command,
                "url": cfg.url,
                "error": None,
                "auth": cfg.auth.mode if cfg.auth else None,
                "auth_token": token_summary,
            }
        return out

    # ---------- resources / prompts（只读，不走确认通道） ----------

    def _get_connection(self, server: str):
        conn = self._connections.get(server)
        if conn is None:
            raise KeyError(f"MCP server '{server}' 未连接")
        return conn

    async def list_resources(self) -> List[dict]:
        """聚合已连接 server 的资源清单。"""
        out: List[dict] = []
        for name, conn in self._connections.items():
            try:
                result = await conn.session.list_resources()
            except Exception as e:
                logger.warning("list_resources failed", server=name, error=str(e))
                continue
            for r in result.resources:
                out.append(
                    {
                        "server": name,
                        "uri": str(getattr(r, "uri", "")),
                        "name": getattr(r, "name", "") or "",
                        "description": getattr(r, "description", "") or "",
                    }
                )
        return out

    async def read_resource(self, server: str, uri: str) -> str:
        """读一个资源，拼接文本内容；非文本部分给占位标记。"""
        conn = self._get_connection(server)
        result = await conn.session.read_resource(uri)
        parts: List[str] = []
        for c in getattr(result, "contents", []) or []:
            text = getattr(c, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(f"[{getattr(c, 'mimeType', None) or 'binary'} content]")
        return "\n".join(p for p in parts if p) or "(资源内容为空)"

    async def list_prompts(self) -> List[dict]:
        """聚合已连接 server 的 prompt 清单。"""
        out: List[dict] = []
        for name, conn in self._connections.items():
            try:
                result = await conn.session.list_prompts()
            except Exception as e:
                logger.warning("list_prompts failed", server=name, error=str(e))
                continue
            for p in result.prompts:
                out.append(
                    {
                        "server": name,
                        "name": getattr(p, "name", "") or "",
                        "description": getattr(p, "description", "") or "",
                    }
                )
        return out

    async def get_prompt(self, server: str, name: str, arguments: Optional[dict] = None) -> str:
        """取一个 prompt，拼接 messages 为对话文本。"""
        conn = self._get_connection(server)
        result = await conn.session.get_prompt(name, arguments or {})
        lines: List[str] = []
        for m in getattr(result, "messages", []) or []:
            role = getattr(m, "role", "user")
            content = getattr(m, "content", None)
            text = getattr(content, "text", None)
            if text is None:
                text = f"[{getattr(content, 'type', 'unknown')} content]"
            lines.append(f"{role}: {text}")
        return "\n".join(lines) or "(prompt 内容为空)"

    async def get_prompt_expansion(
        self, server: str, name: str, arguments: Optional[dict] = None
    ) -> str:
        """取 prompt 并返回纯文本展开（无 role 前缀）——斜杠命令注入输入流用
        （收敛批次②B，对齐 Claude Code 把 MCP prompt 注册为斜杠命令）。"""
        conn = self._get_connection(server)
        result = await conn.session.get_prompt(name, arguments or {})
        parts: List[str] = []
        for m in getattr(result, "messages", []) or []:
            content = getattr(m, "content", None)
            text = getattr(content, "text", None)
            if text is not None and text.strip():
                parts.append(text)
        return "\n\n".join(parts)

    def approve_tool(self, server: str, tool: str) -> None:
        self._approved.add(_approve_key(server, tool))

    def is_tool_approved(self, server: str, tool: str) -> bool:
        cfg = self._configs.get(server)
        if cfg is not None and cfg.trusted:
            return True
        return _approve_key(server, tool) in self._approved


_manager: Optional[McpManager] = None


def get_mcp_manager() -> McpManager:
    global _manager
    if _manager is None:
        _manager = McpManager()
    return _manager


def reset_mcp_manager() -> None:
    global _manager
    _manager = None


async def auto_connect_on_startup() -> Tuple[List[str], Dict[str, str]]:
    """REPL 启动时按配置自动连接（settings.mcp_enabled 总开关）。"""
    if not getattr(settings, "mcp_enabled", False):
        return [], {}
    manager = get_mcp_manager()
    if not manager.has_config():
        return [], {}
    return await manager.connect_all()


async def close_mcp_connections() -> None:
    """退出清理入口（REPL finally 调用）。"""
    await get_mcp_manager().close_all()
