"""hooks.json 配置加载测试（P3-1）

形态对齐 Claude Code：
{
  "hooks": {
    "PreToolUse": [{"matcher": "run_command|write_file",
                    "hooks": [{"type": "command", "command": "...", "timeout": 10}]}]
  }
}
搜索顺序：用户级 ~/.mini-claude/hooks.json → 项目级 <workspace_root>/.mini-claude/hooks.json
（同类事件条目拼接，不去重）。
"""

import json

from mini_claude.hooks.config import load_hooks_config


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp_path, user=None, project=None):
    home = tmp_path / "h"
    ws = tmp_path / "w"
    if user is not None:
        _write(home / ".mini-claude" / "hooks.json", user)
    if project is not None:
        _write(ws / ".mini-claude" / "hooks.json", project)
    for d in (home, ws):
        d.mkdir(exist_ok=True)
    return str(home), str(ws)


class TestLoadHooksConfig:
    def test_no_files_returns_empty(self, tmp_path):
        home, ws = _setup(tmp_path)
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert config.entries == {}
        assert warnings == []

    def test_user_level_loaded(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "run_command",
                            "hooks": [{"type": "command", "command": "check.bat", "timeout": 5}],
                        }
                    ]
                }
            },
        )
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert warnings == []
        rules = config.entries["PreToolUse"]
        assert len(rules) == 1
        assert rules[0].matcher == "run_command"
        assert rules[0].hooks[0].command == "check.bat"
        assert rules[0].hooks[0].timeout == 5

    def test_user_and_project_merged_not_replaced(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "a"}]}]}},
            project={
                "hooks": {
                    "PreToolUse": [{"hooks": [{"type": "command", "command": "b"}]}],
                    "Stop": [{"hooks": [{"type": "command", "command": "c"}]}],
                }
            },
        )
        config, _ = load_hooks_config(ws, home_dir=home)
        assert len(config.entries["PreToolUse"]) == 2
        assert len(config.entries["Stop"]) == 1

    def test_unknown_event_warned_and_skipped(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={"hooks": {"BadEvent": [{"hooks": [{"type": "command", "command": "x"}]}]}},
        )
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert "BadEvent" not in config.entries
        assert any("BadEvent" in w for w in warnings)

    def test_entry_without_command_rejected_with_warning(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "", "hooks": [{"type": "command", "command": "ok"}]},
                        {"matcher": "", "hooks": [{"type": "command"}]},  # 缺 command
                    ]
                }
            },
        )
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert len(config.entries["PreToolUse"]) == 1  # 只有合法条目
        assert len(warnings) == 1

    def test_non_command_type_rejected(self, tmp_path):
        """v1 只支持 type=command"""
        home, ws = _setup(
            tmp_path,
            user={
                "hooks": {
                    "PreToolUse": [
                        {"hooks": [{"type": "prompt", "prompt": "think"}]},
                    ]
                }
            },
        )
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert config.entries == {}
        assert len(warnings) == 1

    def test_invalid_json_warns_not_crash(self, tmp_path):
        home, ws = _setup(tmp_path)
        bad = tmp_path / "h" / ".mini-claude" / "hooks.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{broken", encoding="utf-8")
        config, warnings = load_hooks_config(ws, home_dir=home)
        assert config.entries == {}
        assert len(warnings) == 1

    def test_matcher_default_empty_matches_all(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "log"}]}]}},
        )
        config, _ = load_hooks_config(ws, home_dir=home)
        assert config.entries["PostToolUse"][0].matcher == ""


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
