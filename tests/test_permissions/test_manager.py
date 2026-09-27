"""PermissionManager 裁决测试（P3-2）

裁决顺序：deny > ask > allow > 模式默认。
模式：default / accept_edits / plan / bypass（shift+tab 循环）。
"""

import pytest

from mini_claude.permissions.manager import PermissionManager
from mini_claude.permissions.rules import parse_rules
from mini_claude.permissions.mode import PermissionMode, next_mode


def _mgr(allow=(), deny=(), ask=(), mode=PermissionMode.DEFAULT, enabled=True):
    return PermissionManager(
        allow_rules=parse_rules(list(allow)),
        deny_rules=parse_rules(list(deny)),
        ask_rules=parse_rules(list(ask)),
        mode=mode,
        enabled=enabled,
    )


class TestDecisionOrder:
    def test_no_rules_default_mode_allows(self):
        assert _mgr().decide("read_file", {}).action == "allow"

    def test_deny_wins_over_everything(self):
        mgr = _mgr(allow=["run_command"], deny=["run_command:rm *"], ask=["run_command"])
        d = mgr.decide("run_command", {"command": "rm -rf /"})
        assert d.action == "deny"
        assert "deny" in d.reason or "拒绝" in d.reason

    def test_ask_wins_over_allow(self):
        mgr = _mgr(allow=["write_file"], ask=["write_file:*"])
        d = mgr.decide("write_file", {"path": "a.py"})
        assert d.action == "ask"

    def test_allow_short_circuits_mode_defaults(self):
        mgr = _mgr(allow=["run_command:git *"])
        assert mgr.decide("run_command", {"command": "git push"}).action == "allow"

    def test_unmatched_rule_no_effect(self):
        mgr = _mgr(deny=["run_command:rm *"])
        assert mgr.decide("run_command", {"command": "git status"}).action == "allow"
        assert mgr.decide("read_file", {}).action == "allow"


class TestSessionApproval:
    def test_ask_then_approved_then_allowed(self):
        mgr = _mgr(ask=["write_file:*"])
        assert mgr.decide("write_file", {"path": "a.py"}).action == "ask"
        mgr.approve_session("write_file", "a.py")
        assert mgr.decide("write_file", {"path": "a.py"}).action == "allow"

    def test_approval_is_per_primary_arg(self):
        mgr = _mgr(ask=["write_file:*"])
        mgr.approve_session("write_file", "a.py")
        assert mgr.decide("write_file", {"path": "b.py"}).action == "ask"

    def test_approval_cannot_override_deny(self):
        mgr = _mgr(deny=["run_command:rm *"])
        mgr.approve_session("run_command", "rm -rf /")
        assert mgr.decide("run_command", {"command": "rm -rf /"}).action == "deny"


class TestModes:
    def test_plan_mode_denies_mutating_tools(self):
        mgr = _mgr(mode=PermissionMode.PLAN)
        for tool in ("write_file", "edit_file", "force_write", "run_command", "run_background"):
            d = mgr.decide(tool, {"command": "x", "path": "y"})
            assert d.action == "deny", tool
            assert "plan" in d.reason

    def test_plan_mode_allows_read_tools(self):
        mgr = _mgr(mode=PermissionMode.PLAN)
        assert mgr.decide("read_file", {}).action == "allow"
        assert mgr.decide("list_dir", {}).action == "allow"
        assert mgr.decide("search_content", {}).action == "allow"

    def test_plan_mode_denies_mcp_tools(self):
        mgr = _mgr(mode=PermissionMode.PLAN)
        assert mgr.decide("mcp__fs__write", {}).action == "deny"

    def test_explicit_allow_beats_plan_mode(self):
        mgr = _mgr(allow=["run_command:npm test"], mode=PermissionMode.PLAN)
        assert mgr.decide("run_command", {"command": "npm test"}).action == "allow"

    def test_accept_edits_suppresses_ask_on_edit_tools(self):
        mgr = _mgr(ask=["write_file:*"], mode=PermissionMode.ACCEPT_EDITS)
        assert mgr.decide("write_file", {"path": "a.py"}).action == "allow"
        # 非 edit 工具的 ask 不受影响
        mgr2 = _mgr(ask=["run_command:*"], mode=PermissionMode.ACCEPT_EDITS)
        assert mgr2.decide("run_command", {"command": "x"}).action == "ask"

    def test_accept_edits_still_respects_deny(self):
        mgr = _mgr(deny=["write_file:/etc/*"], mode=PermissionMode.ACCEPT_EDITS)
        assert mgr.decide("write_file", {"path": "/etc/passwd"}).action == "deny"

    def test_bypass_skips_ask_but_not_deny(self):
        mgr = _mgr(deny=["run_command:rm *"], ask=["write_file:*"], mode=PermissionMode.BYPASS)
        assert mgr.decide("write_file", {"path": "a.py"}).action == "allow"
        assert mgr.decide("run_command", {"command": "rm -rf /"}).action == "deny"

    def test_disabled_manager_allows_all(self):
        mgr = _mgr(deny=["*"], enabled=False)
        assert mgr.decide("run_command", {"command": "rm"}).action == "allow"


class TestModeCycle:
    def test_next_mode_cycle_order(self):
        order = [
            PermissionMode.DEFAULT,
            PermissionMode.ACCEPT_EDITS,
            PermissionMode.PLAN,
            PermissionMode.BYPASS,
        ]
        for cur, nxt in zip(order, order[1:] + order[:1]):
            assert next_mode(cur) == nxt

    def test_manager_set_mode(self):
        mgr = _mgr()
        mgr.set_mode(PermissionMode.PLAN)
        assert mgr.mode == PermissionMode.PLAN


class TestConfigLoad:
    def test_load_from_settings_json(self, tmp_path):
        import json

        ws = tmp_path / "w"
        (ws / ".mini-claude").mkdir(parents=True)
        (ws / ".mini-claude" / "settings.json").write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["read_file"],
                        "deny": ["run_command:rm *"],
                        "ask": ["write_file:*"],
                    }
                }
            ),
            encoding="utf-8",
        )
        home = tmp_path / "h"
        home.mkdir()

        mgr = PermissionManager.load(str(ws), home_dir=str(home))
        assert mgr.decide("read_file", {}).action == "allow"
        assert mgr.decide("run_command", {"command": "rm -rf /"}).action == "deny"
        assert mgr.decide("write_file", {"path": "x"}).action == "ask"

    def test_user_and_project_union(self, tmp_path):
        import json

        home = tmp_path / "h"
        (home / ".mini-claude").mkdir(parents=True)
        (home / ".mini-claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["list_dir"]}}), encoding="utf-8"
        )
        ws = tmp_path / "w"
        (ws / ".mini-claude").mkdir(parents=True)
        (ws / ".mini-claude" / "settings.json").write_text(
            json.dumps({"permissions": {"deny": ["run_command:rm *"]}}), encoding="utf-8"
        )

        mgr = PermissionManager.load(str(ws), home_dir=str(home))
        assert mgr.decide("list_dir", {}).action == "allow"
        assert mgr.decide("run_command", {"command": "rm -rf /"}).action == "deny"

    def test_missing_file_ok(self, tmp_path):
        home = tmp_path / "h"
        home.mkdir()
        mgr = PermissionManager.load(str(tmp_path / "w"), home_dir=str(home))
        assert mgr.decide("read_file", {}).action == "allow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
