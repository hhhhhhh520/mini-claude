"""文件修改日志测试（收敛批次③：/rewind 代码回退的数据底座）。"""

import time

import pytest

from mini_claude.utils import file_history as fh


@pytest.fixture(autouse=True)
def _clean():
    fh.reset()
    yield
    fh.reset()


class TestRecordAndRestore:
    def test_records_before_content_once(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("原始内容", encoding="utf-8")
        fh.record_before_write(str(f))
        f.write_text("第一次修改", encoding="utf-8")
        fh.record_before_write(str(f))  # 同路径第二次记录被去重
        f.write_text("第二次修改", encoding="utf-8")

        assert fh.entry_count() == 1
        results = fh.restore_since(0.0)
        assert results == [(str(f), "restored")]
        assert f.read_text(encoding="utf-8") == "原始内容", "回退到最早一次修改前"

    def test_created_file_deleted_on_restore(self, tmp_path):
        f = tmp_path / "new.txt"
        fh.record_before_write(str(f))  # 此前不存在
        f.write_text("新建内容", encoding="utf-8")

        results = fh.restore_since(0.0)
        assert results == [(str(f), "deleted")]
        assert not f.exists()

    def test_restore_since_boundary(self, tmp_path):
        """边界之前的条目不回放（且保留）；之后的回放并消费。"""
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        old.write_text("旧文件内容", encoding="utf-8")
        fh.record_before_write(str(old))
        boundary = time.time() + 0.01
        time.sleep(0.02)
        new.write_text("x", encoding="utf-8")
        fh.record_before_write(str(new))

        results = fh.restore_since(boundary)
        assert results == [(str(new), "restored")]
        assert old.read_text(encoding="utf-8") == "旧文件内容"
        assert fh.entry_count() == 1, "边界前条目保留（仍是对话更早的历史）"

    def test_consumed_entries_dropped(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("orig", encoding="utf-8")
        fh.record_before_write(str(f))
        f.write_text("changed", encoding="utf-8")

        fh.restore_since(0.0)
        assert fh.entry_count() == 0, "回放即消费（单向回退，不做 redo）"

    def test_failed_restore_kept_for_retry(self, tmp_path, monkeypatch):
        f = tmp_path / "a.txt"
        f.write_text("orig", encoding="utf-8")
        fh.record_before_write(str(f))
        f.write_text("changed", encoding="utf-8")

        import builtins

        real_open = builtins.open

        def failing_open(path, *a, **kw):
            if "w" in str(a) and str(path) == str(f):
                raise PermissionError("被锁住")
            return real_open(path, *a, **kw)

        monkeypatch.setattr(builtins, "open", failing_open)
        results = fh.restore_since(0.0)
        assert results[0][1].startswith("failed")
        assert fh.entry_count() == 1, "失败条目保留，下次回退可重试"


class TestAtomicWriteRecording:
    @pytest.mark.asyncio
    async def test_write_file_records_journal(self, tmp_path, monkeypatch):
        """三个写工具的公共汇聚点自动记录（write_file 验证）。"""
        from mini_claude.config.settings import settings

        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
        target = tmp_path / "t.txt"
        target.write_text("v1", encoding="utf-8")

        from mini_claude.tools.file_ops import WriteFileTool

        await WriteFileTool().execute(path="t.txt", content="v2")
        assert target.read_text(encoding="utf-8") == "v2"
        assert fh.entry_count() == 1
        results = fh.restore_since(0.0)
        assert results == [(str(target), "restored")]
        assert target.read_text(encoding="utf-8") == "v1"
