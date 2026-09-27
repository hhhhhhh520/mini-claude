"""MCP stdio 真子进程 E2E（P2）。

真实连接仓库内的 echo_server.py（官方 SDK FastMCP）：
连接 → 工具发现 → 注册进 tool_registry → 放行 → 调用 → 注销。
Windows 子进程编码/关闭差异主要靠这条测试兜底。
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mini_claude.mcp.config import McpServerConfig  # noqa: E402
from mini_claude.mcp.manager import McpManager, reset_mcp_manager  # noqa: E402
from mini_claude.tools import list_tools, tool_registry  # noqa: E402

SERVER_SCRIPT = Path(__file__).parent.parent / "test_mcp" / "echo_server.py"


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    reset_mcp_manager()
    for name in list(list_tools()):
        if name.startswith("mcp__e2e__"):
            tool_registry.unregister(name)


@pytest.mark.asyncio
async def test_real_stdio_connect_discover_call():
    mgr = McpManager()
    mgr._configs = {
        "e2e": McpServerConfig(name="e2e", command=sys.executable, args=[str(SERVER_SCRIPT)])
    }
    mgr._config_loaded = True  # 冻结：E2E 配置不经磁盘加载

    connected, errors = await mgr.connect_all()
    assert errors == {}, f"连接失败: {errors}"
    assert connected == ["e2e"]

    # 工具发现并注册进全局 registry
    assert "mcp__e2e__echo" in list_tools()
    assert "mcp__e2e__add" in list_tools()

    # 未放行时走确认通道（execute 抛确认异常）
    from mini_claude.mcp.bridge import McpConfirmationRequired

    echo_tool = tool_registry.get("mcp__e2e__echo")
    with pytest.raises(McpConfirmationRequired):
        await echo_tool.execute(text="hello-mcp")

    # 放行后真调用
    mgr.approve_tool("e2e", "echo")
    assert await echo_tool.execute(text="hello-mcp") == "hello-mcp"

    # int 参数往返
    mgr.approve_tool("e2e", "add")
    add_tool = tool_registry.get("mcp__e2e__add")
    assert await add_tool.execute(a=2, b=3) == "5"

    # 干净退出
    await mgr.close_all()
    assert "mcp__e2e__echo" not in list_tools()
    assert "mcp__e2e__add" not in list_tools()


@pytest.mark.asyncio
async def test_real_stdio_reconnect_after_close():
    """close 后可重新连接同一 server（/mcp reconnect 场景）"""
    mgr = McpManager()
    mgr._configs = {
        "e2e": McpServerConfig(name="e2e", command=sys.executable, args=[str(SERVER_SCRIPT)])
    }
    mgr._config_loaded = True

    await mgr.connect_server("e2e")
    await mgr.close_all()
    assert "mcp__e2e__echo" not in list_tools()

    await mgr.connect_server("e2e")
    assert "mcp__e2e__echo" in list_tools()
    await mgr.close_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
