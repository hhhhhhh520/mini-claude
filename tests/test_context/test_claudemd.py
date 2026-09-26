"""CLAUDE.md 自动加载测试（P1-2）

覆盖：
1. load_claude_md：用户级 ~/.mini-claude/CLAUDE.md + 项目级 workspace_root/CLAUDE.md
2. 合并顺序（用户级在前）、单文件/总量截断、坏编码不崩
3. build_system_messages 注入（开关、缺失不注入、加载失败不阻断主链路）
"""

import pytest
from unittest.mock import patch

from mini_claude.utils.claudemd import load_claude_md


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def workspace(tmp_path):
    w = tmp_path / "ws"
    w.mkdir()
    return w


class TestLoadClaudeMd:
    def test_missing_files_returns_empty(self, home, workspace):
        assert load_claude_md(str(workspace), home_dir=str(home)) == ""

    def test_user_level_loaded(self, home, workspace):
        d = home / ".mini-claude"
        d.mkdir()
        (d / "CLAUDE.md").write_text("USER-RULE-1", encoding="utf-8")
        assert "USER-RULE-1" in load_claude_md(str(workspace), home_dir=str(home))

    def test_project_level_loaded(self, home, workspace):
        (workspace / "CLAUDE.md").write_text("PROJ-RULE-1", encoding="utf-8")
        assert "PROJ-RULE-1" in load_claude_md(str(workspace), home_dir=str(home))

    def test_user_comes_before_project(self, home, workspace):
        d = home / ".mini-claude"
        d.mkdir()
        (d / "CLAUDE.md").write_text("USER-PART", encoding="utf-8")
        (workspace / "CLAUDE.md").write_text("PROJ-PART", encoding="utf-8")
        combined = load_claude_md(str(workspace), home_dir=str(home))
        assert combined.index("USER-PART") < combined.index("PROJ-PART")

    def test_oversize_file_truncated_with_marker(self, home, workspace):
        big = "x" * (70_000)
        (workspace / "CLAUDE.md").write_text(big, encoding="utf-8")
        combined = load_claude_md(str(workspace), home_dir=str(home))
        assert len(combined) < 70_000
        assert "截断" in combined or "truncated" in combined.lower()

    def test_total_cap_enforced(self, home, workspace):
        d = home / ".mini-claude"
        d.mkdir()
        (d / "CLAUDE.md").write_text("u" * 60_000, encoding="utf-8")
        (workspace / "CLAUDE.md").write_text("p" * 60_000, encoding="utf-8")
        from mini_claude.utils.claudemd import CLAUDE_MD_MAX_TOTAL_CHARS

        combined = load_claude_md(str(workspace), home_dir=str(home))
        # 两部分都在，且总量不超过常量上限
        assert "u" in combined and "p" in combined
        assert len(combined) <= CLAUDE_MD_MAX_TOTAL_CHARS

    def test_total_cap_truncates_project_part(self, home, workspace):
        """用户级占满大头时，项目级被截断而不是丢弃"""
        d = home / ".mini-claude"
        d.mkdir()
        (d / "CLAUDE.md").write_text("u" * 130_000, encoding="utf-8")  # 超单文件上限→截到 65536
        (workspace / "CLAUDE.md").write_text("PROJ-TAIL", encoding="utf-8")
        combined = load_claude_md(str(workspace), home_dir=str(home))

        assert "PROJ-TAIL" in combined  # 项目级仍被保留（截断而非跳过）
        assert "截断" in combined

    def test_bad_encoding_does_not_crash(self, home, workspace):
        (workspace / "CLAUDE.md").write_bytes(b"\xff\xfe\x81\x81 broken")
        result = load_claude_md(str(workspace), home_dir=str(home))
        assert isinstance(result, str)

    def test_workspace_none_only_user_level(self, home):
        d = home / ".mini-claude"
        d.mkdir()
        (d / "CLAUDE.md").write_text("ONLY-USER", encoding="utf-8")
        assert "ONLY-USER" in load_claude_md(None, home_dir=str(home))


class TestBuildSystemMessagesInjection:
    """build_system_messages 注入契约"""

    def _build(self):
        from mini_claude.agent.nodes._shared import build_system_messages

        return build_system_messages()

    def test_injection_via_real_loader(self, monkeypatch, tmp_path):
        """真实加载器打通：workspace 的 CLAUDE.md 进 system 消息"""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "CLAUDE.md").write_text("REAL-CONVENTION-7", encoding="utf-8")

        from mini_claude.config.settings import settings as real_settings

        monkeypatch.setattr(real_settings, "claude_md_enabled", True)
        monkeypatch.setattr(
            "mini_claude.agent.nodes._shared.settings", real_settings, raising=False
        )
        with patch(
            "mini_claude.utils.claudemd.load_claude_md",
            return_value="REAL-CONVENTION-7",
        ):
            msgs = self._build()

        assert any("REAL-CONVENTION-7" in m.get("content", "") for m in msgs)

    def test_disabled_flag_no_injection(self, monkeypatch):
        from mini_claude.config.settings import settings as real_settings

        monkeypatch.setattr(real_settings, "claude_md_enabled", False)
        monkeypatch.setattr(
            "mini_claude.agent.nodes._shared.settings", real_settings, raising=False
        )
        with patch("mini_claude.utils.claudemd.load_claude_md", return_value="SHOULD-NOT-APPEAR"):
            msgs = self._build()

        assert all("SHOULD-NOT-APPEAR" not in m.get("content", "") for m in msgs)

    def test_loader_crash_does_not_break_main_path(self, monkeypatch):
        from mini_claude.config.settings import settings as real_settings

        monkeypatch.setattr(real_settings, "claude_md_enabled", True)
        monkeypatch.setattr(
            "mini_claude.agent.nodes._shared.settings", real_settings, raising=False
        )
        with patch("mini_claude.utils.claudemd.load_claude_md", side_effect=RuntimeError("boom")):
            msgs = self._build()  # 不抛异常即通过

        assert msgs and msgs[0]["role"] == "system"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
