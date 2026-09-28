"""MCP resources/prompts 全局工具测试。

对标 Claude Code 的 ListMcpResources / ReadMcpResource（prompts 同理）：
- 全局工具 mcp_list_resources / mcp_read_resource / mcp_list_prompts /
  mcp_get_prompt 在任一 server 连接时注册（MCP 关闭时不注册）
- 经 manager 的连接迭代聚合；只读操作不走确认通道
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mini_claude.mcp.manager import get_mcp_manager, reset_mcp_manager
from mini_claude.tools import execute_tool, list_tools, tool_registry


def _conn(name, resources=None, prompts=None):
    session = SimpleNamespace(
        list_resources=AsyncMock(
            return_value=SimpleNamespace(
                resources=[
                    SimpleNamespace(
                        uri="echo://greeting",
                        name="greeting",
                        description="一句问候",
                        mimeType="text/plain",
                    )
                ]
                if resources is None
                else resources
            )
        ),
        read_resource=AsyncMock(
            return_value=SimpleNamespace(
                contents=[SimpleNamespace(text="你好，世界", type="text", uri="echo://greeting")],
            )
        ),
        list_prompts=AsyncMock(
            return_value=SimpleNamespace(
                prompts=[SimpleNamespace(name="review", description="代码审查提示")]
                if prompts is None
                else prompts
            )
        ),
        get_prompt=AsyncMock(
            return_value=SimpleNamespace(
                messages=[
                    SimpleNamespace(
                        role="user", content=SimpleNamespace(type="text", text="审查这段代码")
                    )
                ]
            )
        ),
    )
    return SimpleNamespace(server=name, session=session, tools=[], stack=None)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    reset_mcp_manager()
    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp_") and not name.startswith("mcp__"):
            tool_registry.unregister(name)
    yield
    reset_mcp_manager()
    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp_") and not name.startswith("mcp__"):
            tool_registry.unregister(name)


def _with_connections(monkeypatch, conns):
    from mini_claude.mcp.global_tools import ensure_global_tools_registered

    mgr = get_mcp_manager()
    mgr._connections = {c.server: c for c in conns}
    mgr._config_loaded = True
    mgr._configs = {
        c.server: SimpleNamespace(trusted=True, command="x", transport="stdio", url="")
        for c in conns
    }
    # 生产路径里全局工具在 connect_server 注册；注入连接的测试同流程补注册
    ensure_global_tools_registered()
    return mgr


@pytest.mark.asyncio
async def test_global_tools_registered_on_connect(monkeypatch):
    from mini_claude.mcp.global_tools import ensure_global_tools_registered

    ensure_global_tools_registered()
    names = set(list_tools())
    assert {
        "mcp_list_resources",
        "mcp_read_resource",
        "mcp_list_prompts",
        "mcp_get_prompt",
    } <= names


@pytest.mark.asyncio
async def test_list_resources_aggregates_servers(monkeypatch):
    _with_connections(monkeypatch, [_conn("a"), _conn("b")])
    out = await execute_tool("mcp_list_resources", {})
    assert "a" in out and "b" in out
    assert "echo://greeting" in out


@pytest.mark.asyncio
async def test_read_resource_by_server_and_uri(monkeypatch):
    _with_connections(monkeypatch, [_conn("a")])
    out = await execute_tool("mcp_read_resource", {"server": "a", "uri": "echo://greeting"})
    assert "你好，世界" in out


@pytest.mark.asyncio
async def test_read_resource_unknown_server_errors(monkeypatch):
    _with_connections(monkeypatch, [_conn("a")])
    out = await execute_tool("mcp_read_resource", {"server": "zzz", "uri": "echo://greeting"})
    assert out.startswith("Error") and "zzz" in out


@pytest.mark.asyncio
async def test_no_connections_friendly_error(monkeypatch):
    _with_connections(monkeypatch, [])
    out = await execute_tool("mcp_list_resources", {})
    assert out.startswith("Error") or "未连接" in out


@pytest.mark.asyncio
async def test_prompts_list_and_get(monkeypatch):
    _with_connections(monkeypatch, [_conn("a")])
    out = await execute_tool("mcp_list_prompts", {})
    assert "review" in out and "代码审查提示" in out

    out = await execute_tool("mcp_get_prompt", {"server": "a", "name": "review"})
    assert "审查这段代码" in out


@pytest.mark.asyncio
async def test_registered_once_idempotent(monkeypatch):
    from mini_claude.mcp.global_tools import ensure_global_tools_registered

    ensure_global_tools_registered()
    ensure_global_tools_registered()
    names = [n for n in list_tools() if n.startswith("mcp_") and not n.startswith("mcp__")]
    assert len(names) == len(set(names)), "重复注册不得产生同名工具"
