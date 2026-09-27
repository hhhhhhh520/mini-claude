"""/permissions 与 /hooks 命令测试（P3）"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mini_claude.cli.commands.permission_handler import PermissionCommandHandler
from mini_claude.cli.commands.base import CommandContext, get_command_registry
from mini_claude.cli.display import display
from mini_claude.permissions.manager import PermissionManager
from mini_claude.permissions.mode import PermissionMode


def _ctx(args="", command="/permissions"):
    session = SimpleNamespace(thread_id="t1", messages=[])
    return CommandContext(session=session, command=command, args=args, display=display)


class TestPermissionsCommand:
    @pytest.mark.asyncio
    async def test_show_mode_and_rules(self, monkeypatch):
        perm = PermissionManager(
            allow_rules=[],
            deny_rules=[],
            ask_rules=[],
            mode=PermissionMode.PLAN,
        )
        monkeypatch.setattr("mini_claude.permissions.manager.get_permission_manager", lambda: perm)
        result = await PermissionCommandHandler().handle(_ctx())
        assert "plan" in result.message

    @pytest.mark.asyncio
    async def test_set_mode(self, monkeypatch):
        perm = PermissionManager()
        monkeypatch.setattr("mini_claude.permissions.manager.get_permission_manager", lambda: perm)
        await PermissionCommandHandler().handle(_ctx("accept_edits"))
        assert perm.mode == PermissionMode.ACCEPT_EDITS

    @pytest.mark.asyncio
    async def test_set_invalid_mode_errors(self, monkeypatch):
        perm = PermissionManager()
        monkeypatch.setattr("mini_claude.permissions.manager.get_permission_manager", lambda: perm)
        result = await PermissionCommandHandler().handle(_ctx("yolo_mode"))
        assert result.error is not None
        assert perm.mode == PermissionMode.DEFAULT


class TestHooksCommand:
    @pytest.mark.asyncio
    async def test_hooks_listing(self, monkeypatch):
        from mini_claude.hooks.config import HookConfig

        dispatcher = MagicMock()
        dispatcher.config = HookConfig(
            entries={
                "PreToolUse": [
                    SimpleNamespace(
                        matcher="run_command",
                        hooks=[SimpleNamespace(command="check.bat", timeout=10)],
                    )
                ],
            }
        )
        monkeypatch.setattr("mini_claude.hooks.dispatcher.get_hook_dispatcher", lambda: dispatcher)
        result = await PermissionCommandHandler().handle(_ctx(command="/hooks"))
        assert "PreToolUse" in result.message
        assert "run_command" in result.message
        assert "check.bat" in result.message

    @pytest.mark.asyncio
    async def test_hooks_empty(self, monkeypatch):
        from mini_claude.hooks.config import HookConfig

        dispatcher = MagicMock()
        dispatcher.config = HookConfig(entries={})
        monkeypatch.setattr("mini_claude.hooks.dispatcher.get_hook_dispatcher", lambda: dispatcher)
        result = await PermissionCommandHandler().handle(_ctx(command="/hooks"))
        assert "hooks.json" in result.message

    def test_both_commands_registered(self):
        registry = get_command_registry()
        assert registry.get_handler("/permissions") is not None
        assert registry.get_handler("/hooks") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
