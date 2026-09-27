"""ToolRegistry 双门测试（P3）：权限门 + hook 门 + 子代理跳过 + 裁决顺序。

单一裁决点：ToolRegistry.execute（降级管理器同位置）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mini_claude.permissions.manager import PermissionManager
from mini_claude.permissions.rules import parse_rules
from mini_claude.tools.base import BaseTool, tool_registry
from mini_claude.tools.file_ops import set_subagent_mode


class DummyTool(BaseTool):
    """可探测是否真执行的工具"""

    executed = False

    @property
    def name(self):
        return "gate_probe"

    @property
    def description(self):
        return "probe"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def execute(self, **kwargs):
        DummyTool.executed = True
        return "probe-ok"


@pytest.fixture
def probe():
    DummyTool.executed = False
    tool = DummyTool()
    tool_registry.register(tool)
    yield tool
    tool_registry.unregister("gate_probe")
    set_subagent_mode(False)


def _patch_managers(monkeypatch, permission=None, hooks=None):
    """patch tools/base.py 的延迟解析函数（单一裁决点的注入缝）"""
    import mini_claude.tools.base as base_mod

    monkeypatch.setattr(base_mod, "_gate_permission_manager", lambda: permission)
    monkeypatch.setattr(base_mod, "_gate_hook_dispatcher", lambda: hooks)


class TestPermissionGate:
    @pytest.mark.asyncio
    async def test_deny_returns_error_without_executing(self, probe, monkeypatch):
        perm = PermissionManager(deny_rules=parse_rules(["gate_probe"]), enabled=True)
        _patch_managers(monkeypatch, permission=perm, hooks=None)

        result = await tool_registry.execute("gate_probe", {})
        assert result.startswith("Error")
        assert DummyTool.executed is False

    @pytest.mark.asyncio
    async def test_ask_raises_permission_ask_required(self, probe, monkeypatch):
        from mini_claude.permissions.manager import PermissionAskRequired

        perm = PermissionManager(ask_rules=parse_rules(["gate_probe:*"]), enabled=True)
        _patch_managers(monkeypatch, permission=perm, hooks=None)

        with pytest.raises(PermissionAskRequired):
            await tool_registry.execute("gate_probe", {"command": "x"})

    @pytest.mark.asyncio
    async def test_allow_executes_normally(self, probe, monkeypatch):
        perm = PermissionManager(enabled=True)
        _patch_managers(monkeypatch, permission=perm, hooks=None)

        result = await tool_registry.execute("gate_probe", {"command": "x"})
        assert result == "probe-ok"
        assert DummyTool.executed is True


class TestHookGate:
    @pytest.mark.asyncio
    async def test_pre_hook_block_returns_error_without_executing(self, probe, monkeypatch):
        hooks = SimpleNamespace(
            dispatch_pre_tool_use=AsyncMock(return_value="no probes allowed"),
            dispatch_post_tool_use=AsyncMock(return_value=None),
        )
        _patch_managers(monkeypatch, permission=None, hooks=hooks)

        result = await tool_registry.execute("gate_probe", {})
        assert result.startswith("Error") and "no probes allowed" in result
        assert DummyTool.executed is False

    @pytest.mark.asyncio
    async def test_post_hook_replacement(self, probe, monkeypatch):
        hooks = SimpleNamespace(
            dispatch_pre_tool_use=AsyncMock(return_value=None),
            dispatch_post_tool_use=AsyncMock(return_value="replaced-by-hook"),
        )
        _patch_managers(monkeypatch, permission=None, hooks=hooks)

        result = await tool_registry.execute("gate_probe", {})
        assert result == "replaced-by-hook"

    @pytest.mark.asyncio
    async def test_deny_beats_pre_hook_order(self, probe, monkeypatch):
        """deny 先于 hook：权限拒绝时 hook 不应执行"""
        hooks = SimpleNamespace(
            dispatch_pre_tool_use=AsyncMock(return_value=None),
            dispatch_post_tool_use=AsyncMock(return_value=None),
        )
        perm = PermissionManager(deny_rules=parse_rules(["gate_probe"]))
        _patch_managers(monkeypatch, permission=perm, hooks=hooks)

        await tool_registry.execute("gate_probe", {})
        hooks.dispatch_pre_tool_use.assert_not_awaited()


class TestSubagentBypass:
    @pytest.mark.asyncio
    async def test_subagent_skips_both_gates(self, probe, monkeypatch):
        """子代理有自己的白名单体系，权限/hook 门不适用"""
        hooks = SimpleNamespace(
            dispatch_pre_tool_use=AsyncMock(return_value="should-not-fire"),
            dispatch_post_tool_use=AsyncMock(return_value="should-not-replace"),
        )
        perm = PermissionManager(deny_rules=parse_rules(["gate_probe"]))
        _patch_managers(monkeypatch, permission=perm, hooks=hooks)

        set_subagent_mode(True)
        result = await tool_registry.execute("gate_probe", {})
        assert result == "probe-ok"
        hooks.dispatch_pre_tool_use.assert_not_awaited()


class TestOrderWithRealChain:
    @pytest.mark.asyncio
    async def test_full_chain_allow_through(self, probe, monkeypatch):
        hooks = SimpleNamespace(
            dispatch_pre_tool_use=AsyncMock(return_value=None),
            dispatch_post_tool_use=AsyncMock(return_value=None),
        )
        perm = PermissionManager(allow_rules=parse_rules(["gate_probe"]))
        _patch_managers(monkeypatch, permission=perm, hooks=hooks)

        result = await tool_registry.execute("gate_probe", {})
        assert result == "probe-ok"
        hooks.dispatch_pre_tool_use.assert_awaited_once()
        hooks.dispatch_post_tool_use.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
