"""plan 模式审批流测试（收敛批次③C）：exit_plan_mode 三态 + 确认路由。"""

import pytest

from mini_claude.permissions.manager import (
    PlanApprovalRequired,
    get_permission_manager,
    reset_permission_manager,
)
from mini_claude.permissions.mode import PermissionMode


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_permission_manager()
    yield
    reset_permission_manager()


class TestExitPlanModeTool:
    @pytest.mark.asyncio
    async def test_plan_mode_raises_approval(self):
        from mini_claude.tools.plan_mode import ExitPlanModeTool

        get_permission_manager().set_mode(PermissionMode.PLAN)
        with pytest.raises(PlanApprovalRequired) as exc_info:
            await ExitPlanModeTool().execute(plan="1. 先写测试\n2. 再实现")
        assert "先写测试" in exc_info.value.plan

    @pytest.mark.asyncio
    async def test_non_plan_mode_errors(self):
        from mini_claude.tools.plan_mode import ExitPlanModeTool

        get_permission_manager().set_mode(PermissionMode.DEFAULT)
        out = await ExitPlanModeTool().execute(plan="计划")
        assert out.startswith("Error") and "plan" in out

    @pytest.mark.asyncio
    async def test_empty_plan_rejected(self):
        from mini_claude.tools.plan_mode import ExitPlanModeTool

        get_permission_manager().set_mode(PermissionMode.PLAN)
        out = await ExitPlanModeTool().execute(plan="  ")
        assert out.startswith("Error")

    @pytest.mark.asyncio
    async def test_registered(self):
        from mini_claude.tools import list_tools

        assert "exit_plan_mode" in list_tools()


class TestActChainBridge:
    @pytest.mark.asyncio
    async def test_act_converts_to_waiting_confirmation(self, monkeypatch):
        """act 链捕获审批异常 → WAITING_CONFIRMATION + pending 键 "plan"。"""
        from mini_claude.agent.nodes._act_helpers import execute_single_tool

        async def fake_execute_tool(name, params):
            raise PlanApprovalRequired("分步计划")

        import mini_claude.tools as tools_pkg

        monkeypatch.setattr(tools_pkg, "execute_tool", fake_execute_tool)

        from types import SimpleNamespace

        degr = SimpleNamespace(
            tool=SimpleNamespace(
                should_skip=lambda n: False,
                get_replacement=lambda n: None,
                record_success=lambda n: None,
                record_failure=lambda *a, **k: None,
            )
        )
        metrics = SimpleNamespace(record_tool_call=lambda *a, **k: None)
        import contextlib

        messages = []
        _, state_update = await execute_single_tool(
            "exit_plan_mode",
            {"plan": "分步计划"},
            degr,
            metrics,
            lambda *a, **k: contextlib.nullcontext(),
            messages,
            tool_call_id="c1",
        )
        assert state_update["stop_reason"].value == "waiting_confirmation"
        assert state_update["pending_confirmation_path"] == "plan"
        assert "等待用户审批" in messages[0].content
        assert messages[0].status == "success"


class TestApprovalRouting:
    def test_yes_routes_to_accept_edits(self):
        """route_confirmation_key("plan")：批准即切出 plan 模式。"""
        from mini_claude.utils.confirmations import route_confirmation_key

        get_permission_manager().set_mode(PermissionMode.PLAN)
        assert route_confirmation_key("plan") is True
        assert get_permission_manager().mode == PermissionMode.ACCEPT_EDITS

    def test_plan_mode_allows_exit_tool_despite_readonly(self):
        """plan 模式只读闸不拦 exit_plan_mode（decide 允许）。"""

        manager = get_permission_manager()
        manager.set_mode(PermissionMode.PLAN)
        decision = manager.decide("exit_plan_mode", {"plan": "x"})
        assert decision.action == "allow"

    def test_not_confused_with_other_keys(self):
        from mini_claude.utils.confirmations import route_confirmation_key

        assert route_confirmation_key("plan2") is False
        assert route_confirmation_key("/plan") is False
