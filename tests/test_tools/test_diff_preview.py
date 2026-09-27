"""P4-3 确认流程 unified diff 预览测试。

write_file/edit_file/force_write 在触发路径确认时，reason 里带变更预览：
- write_file：现有内容 → 新内容的 unified diff
- edit_file：old_text 替换后的 diff
- 首次创建（无旧内容）：标注"新建文件"
"""

import pytest

from mini_claude.tools.file_ops import (
    EditFileTool,
    ForceWriteTool,
    WriteFileTool,
)
from mini_claude.utils.safety import (
    PathConfirmationRequired,
    clear_approved_paths,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """工作区 = tmp/ws，确认目标放在工作区外 tmp/outside"""
    from mini_claude.config.settings import settings

    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    monkeypatch.setattr(settings, "workspace_root", str(ws))
    clear_approved_paths()
    try:
        yield ws, outside
    finally:
        clear_approved_paths()


class TestWriteFileDiffPreview:
    @pytest.mark.asyncio
    async def test_overwrite_existing_shows_diff(self, sandbox):
        ws, outside = sandbox
        target = outside / "conf.txt"
        target.write_text("old line\n", encoding="utf-8")

        with pytest.raises(PathConfirmationRequired) as exc_info:
            await WriteFileTool().execute(path=str(target), content="new line\n")

        reason = exc_info.value.reason
        assert "-old line" in reason, f"diff 应含删除行，实际：{reason}"
        assert "+new line" in reason, f"diff 应含新增行，实际：{reason}"

    @pytest.mark.asyncio
    async def test_new_file_marked(self, sandbox):
        ws, outside = sandbox
        target = outside / "brand-new.txt"

        with pytest.raises(PathConfirmationRequired) as exc_info:
            await WriteFileTool().execute(path=str(target), content="hello\n")

        assert "新建文件" in exc_info.value.reason


class TestEditFileDiffPreview:
    @pytest.mark.asyncio
    async def test_edit_shows_replacement_diff(self, sandbox):
        ws, outside = sandbox
        target = outside / "code.py"
        target.write_text("x = 1\n", encoding="utf-8")

        with pytest.raises(PathConfirmationRequired) as exc_info:
            await EditFileTool().execute(path=str(target), old_text="x = 1", new_text="x = 2")

        reason = exc_info.value.reason
        assert "-x = 1" in reason
        assert "+x = 2" in reason


class TestForceWriteDiffPreview:
    @pytest.mark.asyncio
    async def test_force_write_shows_diff(self, sandbox):
        ws, outside = sandbox
        target = outside / "fw.txt"
        target.write_text("a\n", encoding="utf-8")

        with pytest.raises(PathConfirmationRequired) as exc_info:
            await ForceWriteTool().execute(path=str(target), content="b\n")

        assert "-a" in exc_info.value.reason and "+b" in exc_info.value.reason


class TestDiffCapped:
    @pytest.mark.asyncio
    async def test_large_diff_truncated(self, sandbox):
        ws, outside = sandbox
        target = outside / "big.txt"
        target.write_text("\n".join(f"line{i}" for i in range(500)), encoding="utf-8")
        new_content = "\n".join(f"LINE{i}" for i in range(500))

        with pytest.raises(PathConfirmationRequired) as exc_info:
            await WriteFileTool().execute(path=str(target), content=new_content)

        reason = exc_info.value.reason
        assert len(reason) < 8000, "diff 预览应有上限，不能把确认消息撑爆"
        assert "截断" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
