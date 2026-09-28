"""/add-dir 多工作目录测试：safety 多根注册表 + 命令。

对标 Claude Code /add-dir：会话级追加工作目录，validate_path 对所有已注册
根放行。主 workspace 的既有比较行为保持不变（含 8.3 短路径先例），额外根
用带 os.sep 守卫的前缀比较，防 D:\\proj 误匹配 D:\\projects。
"""

import pytest

from mini_claude.utils import safety
from mini_claude.utils.safety import (
    PathConfirmationRequired,
    add_workspace_root,
    get_workspace_roots,
    reset_workspace_roots,
)


@pytest.fixture(autouse=True)
def _clean_roots():
    reset_workspace_roots()
    yield
    reset_workspace_roots()


@pytest.fixture
def primary_ws(tmp_path, monkeypatch):
    monkeypatch.setattr(safety.settings, "workspace_root", str(tmp_path / "primary"))
    (tmp_path / "primary").mkdir()
    return tmp_path


class TestMultiRootRegistry:
    def test_register_and_list(self, primary_ws):
        extra = primary_ws / "extra"
        extra.mkdir()
        ok, reason = add_workspace_root(str(extra))
        assert ok is True, reason
        roots = get_workspace_roots()
        assert str(primary_ws / "primary") in roots
        assert str(extra) in roots

    def test_duplicate_register_idempotent(self, primary_ws):
        extra = primary_ws / "extra"
        extra.mkdir()
        add_workspace_root(str(extra))
        add_workspace_root(str(extra))
        assert get_workspace_roots().count(str(extra)) == 1

    def test_reject_nonexistent(self, primary_ws):
        ok, reason = add_workspace_root(str(primary_ws / "nope"))
        assert ok is False and "不存在" in reason

    def test_reject_file_not_dir(self, primary_ws):
        f = primary_ws / "file.txt"
        f.write_text("x", encoding="utf-8")
        ok, reason = add_workspace_root(str(f))
        assert ok is False and "目录" in reason

    def test_primary_workspace_always_first(self, primary_ws):
        assert get_workspace_roots()[0] == str(primary_ws / "primary")

    def test_8_3_short_path_resolved(self, primary_ws):
        """8.3 短路径先例：注册与比较都用 resolve() 归一。"""
        extra = primary_ws / "extra dir"
        extra.mkdir()
        ok, _ = add_workspace_root(str(extra))
        assert ok
        # 注册表存的是 resolve 后的真实路径
        assert str(extra.resolve()) in get_workspace_roots()


class TestValidatePathMultiRoot:
    def test_path_under_additional_root_allowed(self, primary_ws):
        extra = primary_ws / "extra"
        (extra / "sub").mkdir(parents=True)
        add_workspace_root(str(extra))
        target = extra / "sub" / "a.py"
        target.write_text("x", encoding="utf-8")
        ok, reason = safety.validate_path(str(target), require_confirmation=False)
        assert ok is True, reason

    def test_path_outside_all_roots_still_denied(self, primary_ws):
        extra = primary_ws / "extra"
        extra.mkdir()
        add_workspace_root(str(extra))
        outside = primary_ws / "elsewhere" / "a.py"
        outside.parent.mkdir()
        outside.write_text("x", encoding="utf-8")
        ok, _ = safety.validate_path(str(outside), require_confirmation=False)
        assert ok is False

    def test_outside_all_roots_still_raises_confirmation(self, primary_ws):
        """加根 ≠ 全放行：未注册区域仍走确认通道。"""
        extra = primary_ws / "extra"
        extra.mkdir()
        add_workspace_root(str(extra))
        outside = primary_ws / "elsewhere" / "a.py"
        outside.parent.mkdir()
        outside.write_text("x", encoding="utf-8")
        with pytest.raises(PathConfirmationRequired):
            safety.validate_path(str(outside))  # require_confirmation 默认 True

    def test_sibling_prefix_not_matched(self, primary_ws):
        """分隔符守卫：根 D:\\proj 不得放行 D:\\projects。"""
        proj = primary_ws / "proj"
        projects = primary_ws / "projects"
        proj.mkdir()
        (projects / "x").mkdir(parents=True)
        add_workspace_root(str(proj))
        target = projects / "x" / "a.py"
        target.write_text("x", encoding="utf-8")
        ok, _ = safety.validate_path(str(target), require_confirmation=False)
        assert ok is False, "兄弟前缀目录必须被拒绝"

    def test_primary_workspace_unchanged(self, primary_ws):
        target = primary_ws / "primary" / "a.py"
        target.write_text("x", encoding="utf-8")
        ok, reason = safety.validate_path(str(target), require_confirmation=False)
        assert ok is True, reason

    def test_inside_root_traversal_still_denied(self, primary_ws):
        """多根不放松穿越检查：.. 模式仍然拒绝。"""
        extra = primary_ws / "extra"
        extra.mkdir()
        add_workspace_root(str(extra))
        ok, _ = safety.validate_path(str(extra / ".." / "secret"), require_confirmation=False)
        assert ok is False
