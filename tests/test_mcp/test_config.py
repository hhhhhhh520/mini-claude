"""MCP 配置加载测试（P2）

配置形态对齐 Claude Code：{"mcpServers": {name: {command, args, env, trusted}}}
搜索顺序：用户级 ~/.mini-claude/mcp.json → 项目级 <workspace_root>/.mini-claude/mcp.json
（同名时项目级覆盖）。不依赖 mcp SDK。
"""

import json

from mini_claude.mcp.config import load_mcp_config


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp_path, user=None, project=None):
    """写好用户级/项目级配置，返回 (home, workspace) 路径"""
    home = tmp_path / "h"
    ws = tmp_path / "w"
    if user is not None:
        _write(home / ".mini-claude" / "mcp.json", user)
    if project is not None:
        _write(ws / ".mini-claude" / "mcp.json", project)
    for d in (home, ws):
        d.mkdir(exist_ok=True)
    return str(home), str(ws)


class TestLoadMcpConfig:
    def test_no_files_returns_empty(self, tmp_path):
        home, ws = _setup(tmp_path)
        configs, warnings = load_mcp_config(ws, home_dir=home)
        assert configs == {}
        assert warnings == []

    def test_user_level_loaded(self, tmp_path):
        home, ws = _setup(
            tmp_path, user={"mcpServers": {"fs": {"command": "uvx", "args": ["mcp-server-fs"]}}}
        )
        configs, warnings = load_mcp_config(ws, home_dir=home)
        assert warnings == []
        assert configs["fs"].command == "uvx"
        assert configs["fs"].args == ["mcp-server-fs"]

    def test_project_level_loaded(self, tmp_path):
        home, ws = _setup(tmp_path, project={"mcpServers": {"db": {"command": "db-cmd"}}})
        configs, _ = load_mcp_config(ws, home_dir=home)
        assert configs["db"].command == "db-cmd"

    def test_project_overrides_user(self, tmp_path):
        home, ws = _setup(
            tmp_path,
            user={"mcpServers": {"fs": {"command": "user-cmd"}}},
            project={"mcpServers": {"fs": {"command": "project-cmd"}}},
        )
        configs, _ = load_mcp_config(ws, home_dir=home)
        assert configs["fs"].command == "project-cmd"

    def test_flat_format_accepted(self, tmp_path):
        home, ws = _setup(tmp_path, user={"db": {"command": "db-server"}})
        configs, _ = load_mcp_config(ws, home_dir=home)
        assert configs["db"].command == "db-server"

    def test_entry_missing_command_rejected_with_warning(self, tmp_path):
        home, ws = _setup(
            tmp_path, user={"mcpServers": {"bad": {"args": ["x"]}, "good": {"command": "ok"}}}
        )
        configs, warnings = load_mcp_config(ws, home_dir=home)
        assert "bad" not in configs
        assert configs["good"].command == "ok"
        assert any("bad" in w for w in warnings)

    def test_invalid_name_rejected_with_warning(self, tmp_path):
        """名字会进工具名 mcp__<server>__<tool>，只允许 [a-zA-Z0-9_-]"""
        home, ws = _setup(tmp_path, user={"mcpServers": {"my server": {"command": "x"}}})
        configs, warnings = load_mcp_config(ws, home_dir=home)
        assert "my server" not in configs
        assert any("my server" in w for w in warnings)

    def test_invalid_json_yields_warning_not_crash(self, tmp_path):
        home, ws = _setup(tmp_path)
        bad = tmp_path / "h" / ".mini-claude" / "mcp.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")
        configs, warnings = load_mcp_config(ws, home_dir=home)
        assert configs == {}
        assert len(warnings) == 1

    def test_trusted_flag_passthrough(self, tmp_path):
        home, ws = _setup(tmp_path, user={"mcpServers": {"t": {"command": "c", "trusted": True}}})
        configs, _ = load_mcp_config(ws, home_dir=home)
        assert configs["t"].trusted is True

    def test_env_passthrough(self, tmp_path):
        home, ws = _setup(tmp_path, user={"mcpServers": {"e": {"command": "c", "env": {"K": "V"}}}})
        configs, _ = load_mcp_config(ws, home_dir=home)
        assert configs["e"].env == {"K": "V"}

    def test_workspace_none_only_user_level(self, tmp_path):
        home, _ = _setup(tmp_path, user={"mcpServers": {"only": {"command": "c"}}})
        configs, _ = load_mcp_config(None, home_dir=home)
        assert "only" in configs


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
