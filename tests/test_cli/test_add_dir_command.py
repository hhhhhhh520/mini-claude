"""/add-dir 命令测试：注册额外工作目录、无参列出。"""

from types import SimpleNamespace

import pytest

from mini_claude.cli.commands.base import CommandContext, get_command_registry
from mini_claude.cli.commands.add_dir_handler import AddDirHandler
from mini_claude.cli.display import display
from mini_claude.utils import safety
from mini_claude.utils.safety import reset_workspace_roots


@pytest.fixture(autouse=True)
def _clean_roots():
    reset_workspace_roots()
    yield
    reset_workspace_roots()


def _ctx(session, args=""):
    return CommandContext(session=session, command="/add-dir", args=args, display=display)


class TestAddDirCommand:
    def test_registered(self):
        assert get_command_registry().get_handler("/add-dir") is not None

    @pytest.mark.asyncio
    async def test_add_registers_root(self, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        result = await AddDirHandler().handle(_ctx(SimpleNamespace(), str(extra)))
        assert result.error is None
        assert str(extra.resolve()) in safety.get_workspace_roots()

    @pytest.mark.asyncio
    async def test_no_args_lists_roots(self, tmp_path, monkeypatch):
        monkeypatch.setattr(safety.settings, "workspace_root", str(tmp_path))
        result = await AddDirHandler().handle(_ctx(SimpleNamespace(), ""))
        assert result.error is None
        assert str(tmp_path) in result.message
        assert "add-dir" in result.message  # 用法提示

    @pytest.mark.asyncio
    async def test_nonexistent_path_reports_error(self, tmp_path):
        result = await AddDirHandler().handle(_ctx(SimpleNamespace(), str(tmp_path / "nope")))
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_tilde_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        result = await AddDirHandler().handle(_ctx(SimpleNamespace(), "~/"))
        assert result.error is None
        assert str(tmp_path.resolve()) in safety.get_workspace_roots()

    @pytest.mark.asyncio
    async def test_duplicate_add_reports_already(self, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        await AddDirHandler().handle(_ctx(SimpleNamespace(), str(extra)))
        result = await AddDirHandler().handle(_ctx(SimpleNamespace(), str(extra)))
        assert result.error is None
        assert "已注册" in result.message or "already" in result.message.lower()
