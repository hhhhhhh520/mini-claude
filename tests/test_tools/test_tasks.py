"""Task 系统 v2 纯函数层测试（对标 Claude Code TaskCreate/Update/List/Get）。

规格（free-code 只读参考，未搬代码）：
- Task 形状 {id, subject, description, active_form?, status, owner?, blocks[], blockedBy[]}
- status ∈ pending/in_progress/completed；update 支持 'deleted' 特殊动作
- 依赖边：blocks/blocked_by 指向存在的任务、禁自引用、禁成环
架构约束：state 是唯一事实源；模块级 store 仅服务 ask 无 checkpoint 场景，
act 每轮用 state.tasks 覆盖 store（rewind 分叉安全）。
"""

import pytest

from mini_claude.tools.tasks import (
    apply_task_create,
    apply_task_get,
    apply_task_list,
    apply_task_update,
    get_session_tasks,
    reset_session_tasks,
)


@pytest.fixture(autouse=True)
def _clean_store():
    reset_session_tasks()
    yield
    reset_session_tasks()


class TestTaskCreate:
    def test_creates_pending_task_with_sequential_id(self):
        tasks, out, err = apply_task_create(
            [], {"subject": "写模块", "description": "实现核心逻辑"}
        )
        assert err is None
        assert len(tasks) == 1
        assert tasks[0]["id"] == "1"
        assert tasks[0]["status"] == "pending"
        assert tasks[0]["subject"] == "写模块"
        assert tasks[0]["description"] == "实现核心逻辑"
        assert tasks[0]["blocks"] == [] and tasks[0]["blocked_by"] == []
        assert "#1" in out and "写模块" in out

    def test_id_increments_across_creates(self):
        t1, _, _ = apply_task_create([], {"subject": "a", "description": "a"})
        t2, _, _ = apply_task_create(t1, {"subject": "b", "description": "b"})
        assert [t["id"] for t in t2] == ["1", "2"]

    def test_id_not_reused_after_delete(self):
        t1, _, _ = apply_task_create([], {"subject": "a", "description": "a"})
        t2, _, _ = apply_task_update(t1, {"task_id": "1", "status": "deleted"})
        t3, _, _ = apply_task_create(t2, {"subject": "b", "description": "b"})
        assert t3[0]["id"] == "2", "删除后新任务不得复用已回收的编号"

    def test_optional_fields(self):
        tasks, _, _ = apply_task_create(
            [],
            {
                "subject": "跑测试",
                "description": "回归",
                "active_form": "正在跑测试",
                "owner": "subagent_001",
            },
        )
        assert tasks[0]["active_form"] == "正在跑测试"
        assert tasks[0]["owner"] == "subagent_001"

    def test_empty_subject_rejected(self):
        _, _, err = apply_task_create([], {"subject": "  ", "description": "x"})
        assert err is not None and "subject" in err

    def test_missing_description_rejected(self):
        _, _, err = apply_task_create([], {"subject": "只有标题"})
        assert err is not None and "description" in err

    def test_output_text_reaches_session_store_on_tool_path(self):
        """工具 execute() 走 store（ask 场景）——store 路径在 act 级测试覆盖，
        这里锁纯函数不偷写 store。"""
        apply_task_create([], {"subject": "a", "description": "a"})
        assert get_session_tasks() == [], "纯函数不得隐式写 store（写入由调用方负责）"


class TestTaskUpdate:
    def _seed(self, n=2):
        tasks = []
        for i in range(n):
            tasks, _, _ = apply_task_create(
                tasks, {"subject": f"任务{i + 1}", "description": f"d{i + 1}"}
            )
        return tasks

    def test_status_change_and_updated_fields(self):
        tasks = self._seed()
        new_tasks, out, err = apply_task_update(tasks, {"task_id": "1", "status": "in_progress"})
        assert err is None
        assert new_tasks[0]["status"] == "in_progress"
        assert "status" in out

    def test_owner_assignment_delegates(self):
        tasks = self._seed()
        new_tasks, _, err = apply_task_update(tasks, {"task_id": "1", "owner": "subagent_001"})
        assert err is None
        assert new_tasks[0]["owner"] == "subagent_001"

    def test_subject_and_active_form_update(self):
        tasks = self._seed()
        new_tasks, _, err = apply_task_update(
            tasks, {"task_id": "2", "subject": "改名", "active_form": "正在改名"}
        )
        assert err is None
        assert new_tasks[1]["subject"] == "改名"
        assert new_tasks[1]["active_form"] == "正在改名"

    def test_deleted_removes_task(self):
        tasks = self._seed()
        new_tasks, _, err = apply_task_update(tasks, {"task_id": "1", "status": "deleted"})
        assert err is None
        assert [t["id"] for t in new_tasks] == ["2"]

    def test_unknown_task_id_rejected(self):
        tasks = self._seed()
        _, _, err = apply_task_update(tasks, {"task_id": "99", "status": "completed"})
        assert err is not None and "99" in err

    def test_invalid_status_rejected(self):
        tasks = self._seed()
        _, _, err = apply_task_update(tasks, {"task_id": "1", "status": "done"})
        assert err is not None and "status" in err

    def test_missing_task_id_rejected(self):
        _, _, err = apply_task_update([], {"status": "completed"})
        assert err is not None and "task_id" in err

    def test_no_op_update_returns_same_list(self):
        tasks = self._seed()
        new_tasks, _, err = apply_task_update(tasks, {"task_id": "1"})
        assert err is None
        assert new_tasks == tasks


class TestDependencyEdges:
    def _seed(self, n=3):
        tasks = []
        for i in range(n):
            tasks, _, _ = apply_task_create(tasks, {"subject": f"任务{i + 1}", "description": "d"})
        return tasks

    def test_add_blocked_by_records_edge(self):
        tasks = self._seed()
        new_tasks, _, err = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["2"]})
        assert err is None
        assert new_tasks[0]["blocked_by"] == ["2"]
        assert new_tasks[1]["blocks"] == ["1"], "反向边必须同步维护"

    def test_self_reference_rejected(self):
        tasks = self._seed()
        _, _, err = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["1"]})
        assert err is not None

    def test_unknown_edge_target_rejected(self):
        tasks = self._seed()
        _, _, err = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["99"]})
        assert err is not None

    def test_duplicate_edge_rejected(self):
        tasks = self._seed()
        t1, _, _ = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["2"]})
        _, _, err = apply_task_update(t1, {"task_id": "1", "add_blocked_by": ["2"]})
        assert err is not None and "重复" in err

    def test_cycle_rejected(self):
        """1 被 2 阻塞后再让 2 被 1 阻塞 = 环，必须拒绝。"""
        tasks = self._seed()
        t1, _, _ = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["2"]})
        _, _, err = apply_task_update(t1, {"task_id": "2", "add_blocked_by": ["1"]})
        assert err is not None and "环" in err

    def test_longer_cycle_rejected(self):
        """三节点环：1←2←3←1。"""
        tasks = self._seed()
        t1, _, _ = apply_task_update(tasks, {"task_id": "1", "add_blocked_by": ["2"]})
        t2, _, _ = apply_task_update(t1, {"task_id": "2", "add_blocked_by": ["3"]})
        _, _, err = apply_task_update(t2, {"task_id": "3", "add_blocked_by": ["1"]})
        assert err is not None and "环" in err

    def test_diamond_dependency_allowed(self):
        """菱形依赖（无环）必须放行：3 被 1、2 阻塞。"""
        tasks = self._seed()
        t1, _, _ = apply_task_update(tasks, {"task_id": "3", "add_blocked_by": ["1"]})
        t2, _, err = apply_task_update(t1, {"task_id": "3", "add_blocked_by": ["2"]})
        assert err is None
        assert t2[2]["blocked_by"] == ["1", "2"]


class TestRender:
    def _seed_with_state(self):
        tasks, _, _ = apply_task_create([], {"subject": "写模块", "description": "d"})
        tasks, _, _ = apply_task_update(tasks, {"task_id": "1", "status": "in_progress"})
        tasks, _, _ = apply_task_create(tasks, {"subject": "跑测试", "description": "d"})
        tasks, _, _ = apply_task_update(tasks, {"task_id": "1", "owner": "subagent_001"})
        return tasks

    def test_list_shows_status_owner(self):
        out = apply_task_list(self._seed_with_state())
        assert "#1" in out and "写模块" in out
        assert "in_progress" in out
        assert "subagent_001" in out
        assert "pending" in out

    def test_list_empty(self):
        out = apply_task_list([])
        assert "0" in out or "空" in out or "no tasks" in out.lower()

    def test_get_found_and_missing(self):
        tasks = self._seed_with_state()
        out, err = apply_task_get(tasks, "1")
        assert err is None and "写模块" in out and "d" in out
        out, err = apply_task_get(tasks, "42")
        assert err is not None and "42" in err
