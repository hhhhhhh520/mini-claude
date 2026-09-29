"""Task 清单跨会话落盘测试（收敛批次②D）。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from mini_claude.agent.state import create_initial_state, create_turn_increment
from mini_claude.cli.repl import REPLSession


@pytest.fixture
def task_workspace(tmp_path, monkeypatch):
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    return tmp_path


class TestPersistRoundtrip:
    def test_persist_and_load(self, task_workspace):
        from mini_claude.tools.tasks import load_persisted_tasks, persist_tasks

        tasks = [
            {
                "id": "1",
                "subject": "跨会话任务",
                "description": "d",
                "status": "pending",
                "blocks": [],
                "blocked_by": [],
            }
        ]
        persist_tasks(tasks)
        assert load_persisted_tasks() == tasks

    def test_load_missing_returns_empty(self, task_workspace):
        from mini_claude.tools.tasks import load_persisted_tasks

        assert load_persisted_tasks() == []

    def test_load_corrupted_returns_empty(self, task_workspace):
        from pathlib import Path

        from mini_claude.tools.tasks import load_persisted_tasks

        p = Path(task_workspace) / ".mini-claude" / "tasks.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{broken", encoding="utf-8")
        assert load_persisted_tasks() == []


@pytest.mark.asyncio
async def test_act_node_task_create_persists_to_disk(task_workspace):
    """act 链任务变更写透到 tasks.json（收敛批次②D 通道）。"""
    from mini_claude.agent.nodes import act as act_mod
    from mini_claude.tools.tasks import load_persisted_tasks

    call = [
        {
            "id": "call_1",
            "name": "task_create",
            "arguments": json.dumps({"subject": "落盘验证", "description": "d"}),
        }
    ]
    with patch.object(act_mod, "_call_llm_with_retry", new=AsyncMock(return_value=("", call))):
        result = await act_mod.act_node(create_initial_state("建任务"))

    subject = result["tasks"][0]["subject"]
    persisted = load_persisted_tasks()
    assert persisted, "任务变更必须写透到磁盘"
    assert persisted[0]["subject"] == subject


class TestTaskSeed:
    def _session(self, seed):
        s = REPLSession()
        s._pending_task_seed = seed
        return s

    def test_seed_merged_into_turn_increment(self):
        seed = [{"id": "1", "subject": "s", "status": "pending"}]
        s = self._session(seed)
        turn = s._apply_task_seed(create_turn_increment("下一轮"))
        assert turn["tasks"] == seed, "播种清单必须随首个回合增量进 state"
        assert s._pending_task_seed is None, "用后即清"

    def test_no_seed_returns_same(self):
        s = self._session(None)
        turn = create_turn_increment("下一轮")
        assert s._apply_task_seed(turn) is turn

    def test_no_seed_omits_tasks_key(self):
        """resume 不播种（checkpoint 为准）：_pending_task_seed 保持 None。"""
        s = self._session(None)
        turn = s._apply_task_seed(create_turn_increment("x"))
        assert "tasks" not in turn
