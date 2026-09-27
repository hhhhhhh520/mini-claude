"""MCP client support (P2) - 对接 Model Context Protocol 服务器。

公开入口：
- get_mcp_manager / reset_mcp_manager / close_mcp_connections / auto_connect_on_startup
- approve_confirmation_key（REPL 'yes' 分支的 MCP 键处理）
- McpConfirmationRequired / McpSDKMissingError
- load_mcp_config / McpServerConfig

SDK pin 纪律：mcp>=1.30.0,<2.0.0（2.x 改公开 API，未验证不跟）。
"""

from .bridge import (
    McpConfirmationRequired,
    McpToolBridge,
    make_bridge_tool_name,
    register_server_tools,
    unregister_server_tools,
)
from .config import McpServerConfig, load_mcp_config
from .manager import (
    McpSDKMissingError,
    McpManager,
    approve_confirmation_key,
    auto_connect_on_startup,
    close_mcp_connections,
    get_mcp_manager,
    reset_mcp_manager,
)

__all__ = [
    "McpConfirmationRequired",
    "McpToolBridge",
    "make_bridge_tool_name",
    "register_server_tools",
    "unregister_server_tools",
    "McpServerConfig",
    "load_mcp_config",
    "McpSDKMissingError",
    "McpManager",
    "approve_confirmation_key",
    "auto_connect_on_startup",
    "close_mcp_connections",
    "get_mcp_manager",
    "reset_mcp_manager",
]
