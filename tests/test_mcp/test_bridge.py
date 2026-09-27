"""MCP 桥接工具测试（P2）

bridge 不依赖 mcp SDK（session 用鸭子类型 mock），确保缺 SDK 时模块可导入。
覆盖：命名规范、schema 透传、确认门槛、结果格式化、注册/注销。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mini_claude.mcp.bridge import (
    McpConfirmationRequired,
    McpToolBridge,
    make_bridge_tool_name,
    register_server_tools,
    unregister_server_tools,
)
from mini_claude.tools import list_tools, tool_registry


def _text_result(text, is_error=False):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=is_error)


def _tool_def(name="echo", desc="Echo a text", schema=None):
    return SimpleNamespace(
        name=name,
        description=desc,
        inputSchema=schema
        or {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )


def _manager(approved=False):
    m = MagicMock()
    m.is_tool_approved.return_value = approved
    return m


class TestNaming:
    def test_bridge_tool_name(self):
        assert make_bridge_tool_name("fs", "read_file") == "mcp__fs__read_file"


class TestMcpToolBridge:
    def test_metadata_passthrough(self):
        tool = McpToolBridge(_manager(), "fs", _tool_def())
        assert tool.name == "mcp__fs__echo"
        assert tool.description.startswith("[mcp:fs]")
        assert "Echo a text" in tool.description
        assert tool.parameters["type"] == "object"

    @pytest.mark.asyncio
    async def test_execute_without_approval_raises_confirmation(self):
        tool = McpToolBridge(_manager(approved=False), "fs", _tool_def())
        with pytest.raises(McpConfirmationRequired) as exc_info:
            await tool.execute(text="hi")
        assert exc_info.value.server == "fs"
        assert exc_info.value.tool == "echo"

    @pytest.mark.asyncio
    async def test_execute_with_approval_calls_session(self):
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result("hello back"))
        tool = McpToolBridge(_manager(approved=True), "fs", _tool_def())
        tool.bind_session(session)

        result = await tool.execute(text="hi")
        assert result == "hello back"
        session.call_tool.assert_awaited_once_with("echo", {"text": "hi"})

    @pytest.mark.asyncio
    async def test_execute_error_flag_prefixed(self):
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result("boom", is_error=True))
        tool = McpToolBridge(_manager(approved=True), "fs", _tool_def())
        tool.bind_session(session)

        result = await tool.execute(text="hi")
        assert result.startswith("Error:")

    @pytest.mark.asyncio
    async def test_execute_non_text_content_placeholder(self):
        session = MagicMock()
        session.call_tool = AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(type="image", data="...")], isError=False
            )
        )
        tool = McpToolBridge(_manager(approved=True), "fs", _tool_def())
        tool.bind_session(session)

        result = await tool.execute(text="hi")
        assert "image" in result

    @pytest.mark.asyncio
    async def test_execute_session_gone_returns_error_not_crash(self):
        tool = McpToolBridge(_manager(approved=True), "fs", _tool_def())
        result = await tool.execute(text="hi")  # 未 bind_session
        assert result.startswith("Error:")


class TestRegistryIntegration:
    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        unregister_server_tools("regsrv")

    def test_register_and_unregister(self):
        manager = _manager()
        session = MagicMock()
        conn = SimpleNamespace(
            server="regsrv", session=session, tools=[_tool_def("echo"), _tool_def("ping")]
        )
        names = register_server_tools(manager, conn)

        assert names == ["mcp__regsrv__echo", "mcp__regsrv__ping"]
        assert all(n in list_tools() for n in names)

        unregister_server_tools("regsrv")
        assert not any(n in list_tools() for n in names)

    def test_reregister_replaces_not_duplicates(self):
        manager = _manager()
        session = MagicMock()
        conn = SimpleNamespace(server="regsrv", session=session, tools=[_tool_def("echo")])
        register_server_tools(manager, conn)
        register_server_tools(manager, conn)

        assert list_tools().count("mcp__regsrv__echo") == 1
        unregister_server_tools("regsrv")

    def test_registered_tool_name_in_registry_object(self):
        manager = _manager()
        conn = SimpleNamespace(server="regsrv", session=MagicMock(), tools=[_tool_def("echo")])
        register_server_tools(manager, conn)

        obj = tool_registry.get("mcp__regsrv__echo")
        assert obj is not None
        unregister_server_tools("regsrv")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
