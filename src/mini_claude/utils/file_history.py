"""会话级文件修改日志（收敛批次③：/rewind 代码回退的数据底座）。

对齐 Claude Code /rewind 的"代码回退"半边：文件工具每次**首次**改动某文件前，
把改动前的内容记进进程内日志；/rewind <n> code 按选中 checkpoint 的时间戳
回放日志，把该时点之后被改的文件恢复原状（期间新建的文件删除）。

边界（诚实声明，写进文档）：
- 进程内日志——**跨会话**的文件修改不在恢复范围（本体有持久化文件历史链）
- 只覆盖走 file_ops._atomic_write 的三个工具（write/edit/force_write）；
  run_command 等侧门修改不记录
- 日志按路径去重，保留最早一次的"改动前"状态（多次修改一次回退）
- 回放即消费：恢复后移除已回放条目（本仓库回退是单向的，不做 redo）
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FileJournalEntry:
    """一次文件改动前的状态快照。"""

    ts: float  # 改动发生时刻（epoch 秒，对齐 checkpoint 时间轴）
    path: str  # 绝对路径（normpath 归一）
    before_content: Optional[str]  # None = 文件此前不存在（回退=删除）


_journal: List[FileJournalEntry] = []
_lock = threading.Lock()


def record_before_write(path: str) -> None:
    """文件写入前调用：记录改动前状态（同路径只记最早一次）。

    任何读取失败都静默跳过（日志是旁路设施，不能弄断写入主链路）。
    """
    try:
        abs_path = os.path.normpath(os.path.abspath(path))
        with _lock:
            if any(e.path == abs_path for e in _journal):
                return  # 已有更早的快照，保留它
            if os.path.isfile(abs_path):
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    before = f.read()
            else:
                before = None
            _journal.append(FileJournalEntry(ts=time.time(), path=abs_path, before_content=before))
    except Exception as e:
        logger.debug("file history record failed: %s: %s", type(e).__name__, e)


def restore_since(ts_epoch: float) -> List[Tuple[str, str]]:
    """回放 ts_epoch 之后的日志，把文件恢复到改动前。

    每个路径取**最早**的快照（多次修改一次回退到最初状态）；
    回放即消费——已恢复的条目从日志移除，更早的条目保留。

    Returns:
        [(path, action)]，action ∈ {"restored", "deleted"}
    """
    with _lock:
        to_replay = [e for e in _journal if e.ts > ts_epoch]
        if not to_replay:
            return []

        earliest: Dict[str, FileJournalEntry] = {}
        for e in to_replay:
            if e.path not in earliest or e.ts < earliest[e.path].ts:
                earliest[e.path] = e

        results: List[Tuple[str, str]] = []
        consumed = set()
        for path in earliest:
            entry = earliest[path]
            try:
                if entry.before_content is None:
                    if os.path.isfile(path):
                        os.remove(path)
                    results.append((path, "deleted"))
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(entry.before_content)
                    results.append((path, "restored"))
                consumed.add(path)
            except Exception as e:
                # 失败条目保留在日志里，之后的回退可以重试
                logger.warning("file history restore failed: %s: %s", path, e)
                results.append((path, f"failed: {type(e).__name__}"))

        # 消费已恢复条目；边界之前的条目保留（仍是对话更早时点的历史）
        _journal[:] = [e for e in _journal if e.ts <= ts_epoch or e.path not in consumed]
        return results


def entry_count() -> int:
    with _lock:
        return len(_journal)


def reset() -> None:
    with _lock:
        _journal.clear()
