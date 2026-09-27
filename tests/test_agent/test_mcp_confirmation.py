"""act 执行链对 MCP 确认通道的测试（P2）

MCP 工具未放行时抛 McpConfirmationRequired → execute_single_tool 转
WAITING_CONFIRMATION + pending_confirmation_path="mcp:<server>:<tool>"；
放行后正常执行。复用与路径确认完全相同的状态机通道。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mini_claude.agent.nodes._act_helpers import execute_single_tool
from mini_claude.mcp.bridge import McpToolBridge
from mini_claude.mcp.manager import McpManager
from mini_claude.tools import tool_registry


def _tool_def():
    return SimpleNamespace(
        name="echo",
        description="Echo",
        inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
    )


@pytest.fixture
def mcp_tool():
    """注册一个未放行的 mcp bridge 工具，测完清理"""
    manager = McpManager()
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="echoed")], isError=False
        )
    )
    tool = McpToolBridge(manager, "confsrv", _tool_def())
    tool.bind_session(session)
    tool_registry.register(tool)
    yield manager, tool
    tool_registry.unregister("mcp__confsrv__echo")


def _deps():
    degr = MagicMock()
    degr.tool.should_skip.return_value = False
    return degr, MagicMock(), lambda n, a: MagicMock()


class TestMcpConfirmationChannel:
    @pytest.mark.asyncio
    async def test_unapproved_becomes_waiting_confirmation(self, mcp_tool):
        manager, _ = mcp_tool
        new_messages = []

        msgs, state_update = await execute_single_tool(
            "mcp__confsrv__echo", {"text": "hi"}, *_deps(), new_messages
        )

        assert state_update is not None
        assert state_update["stop_reason"].value == "waiting_confirmation"
        assert state_update["pending_confirmation_path"] == "mcp:confsrv:echo"
        assert "确认" in msgs[-1].content
        assert "confsrv" in msgs[-1].content

    @pytest.mark.asyncio
    async def test_approved_executes_normally(self, mcp_tool):
        manager, _ = mcp_tool
        manager.approve_tool("confsrv", "echo")
        new_messages = []

        msgs, state_update = await execute_single_tool(
            "mcp__confsrv__echo", {"text": "hi"}, *_deps(), new_messages
        )

        assert state_update is None
        assert "echoed" in msgs[-1].content

    @pytest.mark.asyncio
    async def test_trusted_server_executes_without_confirmation(self, mcp_tool):
        """trusted=true 的 server 连接后自动放行，不需要确认"""
        manager, _ = mcp_tool
        manager._configs = {"confsrv": SimpleNamespace(trusted=True)}
        manager.approve_tool("confsrv", "echo")  # connect 时 trusted 会自动 approve
        new_messages = []

        msgs, _ = await execute_single_tool(
            "mcp__confsrv__echo", {"text": "hi"}, *_deps(), new_messages
        )

        assert "echoed" in msgs[-1].content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
