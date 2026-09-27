"""权限 ask 确认通道测试（P3-2）：PermissionAskRequired → WAITING_CONFIRMATION。

复用路径确认/MCP 确认的同一状态机：pending_confirmation_path="perm:<tool>:<arg>"。
"""

from unittest.mock import MagicMock

import pytest

from mini_claude.agent.nodes._act_helpers import execute_single_tool
from mini_claude.permissions.manager import PermissionManager
from mini_claude.permissions.rules import parse_rules
from mini_claude.tools import tool_registry
from mini_claude.tools.base import BaseTool


class AskProbeTool(BaseTool):
    @property
    def name(self):
        return "perm_ask_probe"

    @property
    def description(self):
        return "probe"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def execute(self, **kwargs):
        return "should-not-reach"


@pytest.fixture(autouse=True)
def _probe():
    tool_registry.register(AskProbeTool())
    yield
    tool_registry.unregister("perm_ask_probe")


def _deps():
    degr = MagicMock()
    degr.tool.should_skip.return_value = False
    return degr, MagicMock(), lambda n, a: MagicMock()


class TestPermissionAskChannel:
    @pytest.mark.asyncio
    async def test_ask_becomes_waiting_confirmation(self, monkeypatch):
        import mini_claude.tools.base as base_mod

        # probe 工具不在主参数映射里 → ask 键带空 arg（设计如此：arg 级粒度只对映射工具生效）
        perm = PermissionManager(ask_rules=parse_rules(["perm_ask_probe"]))
        monkeypatch.setattr(base_mod, "_gate_permission_manager", lambda: perm)
        monkeypatch.setattr(base_mod, "_gate_hook_dispatcher", lambda: None)
        new_messages = []

        msgs, state_update = await execute_single_tool(
            "perm_ask_probe", {"command": "danger"}, *_deps(), new_messages
        )

        assert state_update is not None
        assert state_update["stop_reason"].value == "waiting_confirmation"
        assert state_update["pending_confirmation_path"] == "perm:perm_ask_probe:"
        assert "确认" in msgs[-1].content and "perm_ask_probe" in msgs[-1].content

    @pytest.mark.asyncio
    async def test_session_approved_then_executes(self, monkeypatch):
        import mini_claude.tools.base as base_mod

        perm = PermissionManager(ask_rules=parse_rules(["perm_ask_probe"]))
        perm.approve_session("perm_ask_probe", "")
        monkeypatch.setattr(base_mod, "_gate_permission_manager", lambda: perm)
        monkeypatch.setattr(base_mod, "_gate_hook_dispatcher", lambda: None)
        new_messages = []

        msgs, state_update = await execute_single_tool(
            "perm_ask_probe", {"command": "danger"}, *_deps(), new_messages
        )

        assert state_update is None
        assert "should-not-reach" in msgs[-1].content


class TestConfirmationRouter:
    def test_router_handles_perm_and_mcp_keys(self):
        from mini_claude.utils.confirmations import route_confirmation_key

        # perm: 键路由到权限管理器（ask 规则带 arg，放行后同参数不再问）
        perm = PermissionManager(ask_rules=parse_rules(["write_file:/a.txt"]))
        from mini_claude.permissions import manager as perm_mod

        old = perm_mod.get_permission_manager
        perm_mod.get_permission_manager = lambda: perm
        try:
            assert perm.decide("write_file", {"path": "/a.txt"}).action == "ask"
            assert route_confirmation_key("perm:write_file:/a.txt") is True
            assert perm.decide("write_file", {"path": "/a.txt"}).action == "allow"
        finally:
            perm_mod.get_permission_manager = old

        # mcp: 键路由到 mcp 管理器
        assert route_confirmation_key("mcp:fs:read") is True

        # 普通路径键返回 False（走 approve_path）
        assert route_confirmation_key("/some/path") is False

    def test_malformed_perm_key_is_swallowed(self):
        from mini_claude.utils.confirmations import route_confirmation_key

        assert route_confirmation_key("perm:nocolon") is True  # 吞掉不落 approve_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
