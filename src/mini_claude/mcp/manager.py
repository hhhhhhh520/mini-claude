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

from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from ..config.settings import settings
from ..utils.logger import get_logger
from .bridge import register_server_tools, unregister_server_tools
from .config import McpServerConfig, load_mcp_config

logger = get_logger("mini_claude.mcp.manager")

MCP_CONFIRM_PREFIX = "mcp:"


class McpSDKMissingError(RuntimeError):
    """mcp SDK 未安装。"""


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

    def __init__(self):
        self._configs: Dict[str, McpServerConfig] = {}
        self._connections: Dict[str, object] = {}
        self._approved: set = set()
        self._config_loaded = False

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
        """建立 stdio 连接并完成 initialize + 工具发现。

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

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        stack = AsyncExitStack()
        try:
            params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env or None)
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools_result = await session.list_tools()
            return SimpleNamespace(
                server=cfg.name, session=session, tools=list(tools_result.tools), stack=stack
            )
        except Exception:
            await stack.aclose()
            raise

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
        conn = self._connections.pop(name, None)
        if conn is None:
            return
        unregister_server_tools(name)
        await conn.stack.aclose()
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
            out[name] = {
                "connected": conn is not None,
                "tools": len(conn.tools) if conn else 0,
                "trusted": cfg.trusted,
                "command": cfg.command,
                "error": None,
            }
        return out

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
