"""Task 系统 v2（对标 Claude Code TaskCreate/Update/List/Get）。

与 todo_write（P1-1）的关系：todo_write 是"全量提交的单清单"，Task v2 是
"增量操作的多任务 + 依赖边 + 委派"——两者并存，Task 面向多代理协作。

架构契约（红线，见 CLAUDE.md）：
- **state.tasks 是唯一事实源**（AgentState.tasks 全量替换语义，与 todos 同纪律：
  不挂 add reducer、不进 create_turn_increment——跨回合由 checkpoint 携带）。
- 工具无状态拿不到 graph state，所以 act 链在派发前把 state.tasks 传入
  execute_single_tool，任务变更经 state_extras["tasks"] 全量替换回 state。
- 模块级 session store **只服务 ask 模式**（无 checkpoint、单回合、无 rewind）；
  act 每轮派发前用 state.tasks 覆盖 store，分叉后 store 从新状态重新同步，
  不会发散。纯函数绝不隐式写 store。

Task 形状（free-code 规格参考，未搬代码）：
    {id, subject, description, active_form?, status, owner?, blocks[], blocked_by[]}
- status ∈ pending/in_progress/completed；update 的 status='deleted' 表示删除
- 依赖边双向同步（A blocked_by B ⇔ B blocks A）；禁自引用、禁重复边、禁成环
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger
from .base import BaseTool, register_tool

_logger = get_logger("mini_claude.tools.tasks")

VALID_TASK_STATUSES = ("pending", "in_progress", "completed")
_DELETE = "deleted"


# ---- 模块级 session store（仅 ask 模式；act 路径每轮从 state 覆盖） ----
_store_lock = threading.Lock()
_session_tasks: List[Dict[str, Any]] = []
# 编号高水位（进程级只增）：硬删除后新建任务不得复用已回收编号——
# 对话历史里对旧编号的引用会造成歧义。这不是业务状态，是 id 分配器记忆。
_id_high_water = 0


def get_session_tasks() -> List[Dict[str, Any]]:
    """ask 模式的任务清单（REPL 路径请以 state.tasks 为准）。"""
    return _session_tasks


def set_session_tasks(tasks: List[Dict[str, Any]]) -> None:
    """act 链每轮派发前同步 state.tasks → store（分叉安全的关键）。"""
    with _store_lock:
        _session_tasks.clear()
        _session_tasks.extend(tasks)


def reset_session_tasks() -> None:
    global _id_high_water
    with _store_lock:
        _session_tasks.clear()
        _id_high_water = 0


# ---- 纯函数层（act 路径与工具路径共用） ----


def _next_id(tasks: List[Dict[str, Any]]) -> str:
    """编号只增不复用：取高水位与现清单 max 的较大者 +1（删除后不复用）。"""
    global _id_high_water
    max_id = _id_high_water
    for t in tasks:
        try:
            max_id = max(max_id, int(t.get("id", 0)))
        except (TypeError, ValueError):
            continue
    issued = max_id + 1
    _id_high_water = max(_id_high_water, issued)
    return str(issued)


def _find(tasks: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def _would_cycle(tasks: List[Dict[str, Any]], from_id: str, to_id: str) -> bool:
    """加边 from←to（from blocked_by to）后是否成环：从 to 沿 blocked_by
    走，若能回到 from 则成环。"""
    stack = [to_id]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur == from_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        node = _find(tasks, cur)
        if node:
            stack.extend(node.get("blocked_by", []))
    return False


def apply_task_create(
    tasks: List[Dict[str, Any]], args: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """创建任务。返回 (新清单, 输出文本, 错误)；错误非空时新清单与输入相同。"""
    subject = args.get("subject")
    description = args.get("description")
    if not isinstance(subject, str) or not subject.strip():
        return tasks, "", "Error: task_create 需要 subject（非空字符串）"
    if not isinstance(description, str) or not description.strip():
        return tasks, "", "Error: task_create 需要 description（非空字符串）"

    task = {
        "id": _next_id(tasks),
        "subject": subject.strip(),
        "description": description.strip(),
        "status": "pending",
        "blocks": [],
        "blocked_by": [],
    }
    active_form = args.get("active_form")
    if isinstance(active_form, str) and active_form.strip():
        task["active_form"] = active_form.strip()
    owner = args.get("owner")
    if isinstance(owner, str) and owner.strip():
        task["owner"] = owner.strip()

    new_tasks = tasks + [task]
    return new_tasks, f"Task #{task['id']} created: {task['subject']}", None


def apply_task_update(
    tasks: List[Dict[str, Any]], args: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """更新任务（字段赋值 / 依赖边 / 删除）。返回 (新清单, 输出文本, 错误)。"""
    task_id = args.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return tasks, "", "Error: task_update 需要 task_id"
    task_id = task_id.strip()

    target = _find(tasks, task_id)
    if target is None:
        known = ", ".join(t["id"] for t in tasks) or "（空）"
        return tasks, "", f"Error: 任务 #{task_id} 不存在（现有：{known}）"

    status = args.get("status")
    if status is not None and status != _DELETE and status not in VALID_TASK_STATUSES:
        return (
            tasks,
            "",
            (
                f"Error: status 非法：{status!r}（必须是 {'/'.join(VALID_TASK_STATUSES)}"
                f"或 '{_DELETE}'）"
            ),
        )

    add_blocks = args.get("add_blocks") or []
    add_blocked_by = args.get("add_blocked_by") or []
    for edge_type, targets in (("add_blocks", add_blocks), ("add_blocked_by", add_blocked_by)):
        for tid in targets:
            if tid == task_id:
                return tasks, "", f"Error: 任务 #{task_id} 不能依赖自己"
            if _find(tasks, str(tid)) is None:
                return tasks, "", f"Error: {edge_type} 引用了不存在的任务 #{tid}"
            _from, _to = (
                (task_id, str(tid)) if edge_type == "add_blocked_by" else (str(tid), task_id)
            )
            existing = _find(tasks, _from)
            if _to in existing.get("blocked_by", []):
                return tasks, "", f"Error: 依赖边 #{_from}←#{_to} 重复"
            if _would_cycle(tasks, _from, _to):
                return tasks, "", f"Error: 依赖边 #{_from}←#{_to} 会构成环，已拒绝"

    if status == _DELETE:
        # dict(t) 拷贝：清理悬空边时不得变异调用方的原清单（纯函数契约）
        new_tasks = [dict(t) for t in tasks if t["id"] != task_id]
        for t in new_tasks:
            t["blocks"] = [x for x in t.get("blocks", []) if x != task_id]
            t["blocked_by"] = [x for x in t.get("blocked_by", []) if x != task_id]
        return new_tasks, f"Task #{task_id} deleted", None

    updated = dict(target)
    changed = []
    for field in ("subject", "description", "active_form", "owner"):
        if field in args and args[field] is not None:
            value = str(args[field]).strip()
            if not value:
                return tasks, "", f"Error: {field} 不能为空字符串"
            updated[field] = value
            changed.append(field)
    if status is not None:
        updated["status"] = status
        changed.append("status")
    if add_blocked_by:
        updated["blocked_by"] = updated.get("blocked_by", []) + [str(x) for x in add_blocked_by]
        changed.append("blocked_by")
    if add_blocks:
        updated["blocks"] = updated.get("blocks", []) + [str(x) for x in add_blocks]
        changed.append("blocks")

    new_tasks = [updated if t["id"] == task_id else dict(t) for t in tasks]
    # 反向边同步：加 blocked_by 时给对方加 blocks，反之亦然
    for tid in updated["blocked_by"]:
        for t in new_tasks:
            if t["id"] == tid and task_id not in t.get("blocks", []):
                t["blocks"] = t.get("blocks", []) + [task_id]
    for tid in updated["blocks"]:
        for t in new_tasks:
            if t["id"] == tid and task_id not in t.get("blocked_by", []):
                t["blocked_by"] = t.get("blocked_by", []) + [task_id]

    detail = ", ".join(changed) if changed else "no-op"
    return new_tasks, f"Task #{task_id} updated ({detail})", None


def apply_task_list(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return "No tasks. 用 task_create 创建任务。"
    lines = [f"Tasks ({len(tasks)}):"]
    for t in tasks:
        status = t.get("status", "pending")
        mark = {"pending": "○", "in_progress": "→", "completed": "✓"}.get(status, "○")
        owner = f" [owner: {t['owner']}]" if t.get("owner") else ""
        blocked = f" [blocked_by: {','.join(t['blocked_by'])}]" if t.get("blocked_by") else ""
        lines.append(f"  #{t['id']} {mark} [{status}] {t['subject']}{owner}{blocked}")
    return "\n".join(lines)


def apply_task_get(tasks: List[Dict[str, Any]], task_id: str) -> Tuple[str, Optional[str]]:
    target = _find(tasks, str(task_id))
    if target is None:
        return "", f"Error: 任务 #{task_id} 不存在"
    lines = [f"Task #{target['id']}: {target['subject']}", f"  status: {target['status']}"]
    lines.append(f"  description: {target.get('description', '')}")
    if target.get("active_form"):
        lines.append(f"  active_form: {target['active_form']}")
    if target.get("owner"):
        lines.append(f"  owner: {target['owner']}")
    if target.get("blocked_by"):
        lines.append(f"  blocked_by: {', '.join(target['blocked_by'])}")
    if target.get("blocks"):
        lines.append(f"  blocks: {', '.join(target['blocks'])}")
    return "\n".join(lines), None


# ---- 工具类（ask 模式经 execute_tool 走 store；REPL 走 act 特化分支） ----


class TaskCreateTool(BaseTool):
    @property
    def name(self) -> str:
        return "task_create"

    @property
    def description(self) -> str:
        return (
            "Create a task in the session task list (v2 task system with dependencies "
            "and delegation). Returns the task id. Use task_update to assign an owner "
            "(a spawned agent id) to delegate, and to track status transitions."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "A brief title for the task"},
                "description": {"type": "string", "description": "What needs to be done"},
                "active_form": {
                    "type": "string",
                    "description": "Present-continuous label shown while in_progress",
                },
                "owner": {
                    "type": "string",
                    "description": "Agent id assigned to this task (delegation)",
                },
            },
            "required": ["subject", "description"],
        }

    async def execute(self, subject: str = "", description: str = "", **kwargs) -> str:
        new_tasks, out, err = apply_task_create(
            get_session_tasks(), {"subject": subject, "description": description, **kwargs}
        )
        if err:
            return err
        set_session_tasks(new_tasks)
        return out


class TaskUpdateTool(BaseTool):
    @property
    def name(self) -> str:
        return "task_update"

    @property
    def description(self) -> str:
        return (
            "Update a task: subject/description/active_form/owner fields, status "
            "(pending|in_progress|completed, or 'deleted' to remove), dependency edges "
            "(add_blocks/add_blocked_by, cycle-safe). Assign owner=<agent id> to "
            "delegate a task to a spawned agent."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The id of the task to update"},
                "subject": {"type": "string", "description": "New subject"},
                "description": {"type": "string", "description": "New description"},
                "active_form": {"type": "string", "description": "New present-continuous label"},
                "status": {
                    "type": "string",
                    "enum": [*VALID_TASK_STATUSES, _DELETE],
                    "description": "New status ('deleted' removes the task)",
                },
                "owner": {"type": "string", "description": "New owner (agent id)"},
                "add_blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task ids this task blocks",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task ids that block this task",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str = "", **kwargs) -> str:
        new_tasks, out, err = apply_task_update(get_session_tasks(), {"task_id": task_id, **kwargs})
        if err:
            return err
        set_session_tasks(new_tasks)
        return out


class TaskListTool(BaseTool):
    @property
    def name(self) -> str:
        return "task_list"

    @property
    def description(self) -> str:
        return "List all tasks in the session task list with status, owner and dependencies."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self) -> str:
        return apply_task_list(get_session_tasks())


class TaskGetTool(BaseTool):
    @property
    def name(self) -> str:
        return "task_get"

    @property
    def description(self) -> str:
        return "Get full details of one task by id (description, owner, dependencies)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task id"}},
            "required": ["task_id"],
        }

    async def execute(self, task_id: str = "") -> str:
        out, err = apply_task_get(get_session_tasks(), task_id)
        return err or out


register_tool(TaskCreateTool())
register_tool(TaskUpdateTool())
register_tool(TaskListTool())
register_tool(TaskGetTool())


# ---- 跨会话落盘（收敛批次②D：Task 清单随会话存活，重启可接续） ----
# 策略：act 链每次任务变更写透到 <workspace>/.mini-claude/tasks.json；
# REPL **新会话**（非 resume）启动时装载并随首个回合增量播种进 state——
# resume 以 checkpoint 为准（不回退）。崩溃窗口只丢最后一次变更。


def _tasks_file_path() -> Path:
    from ..config.settings import settings

    return Path(settings.workspace_root) / ".mini-claude" / "tasks.json"


def persist_tasks(tasks: List[Dict[str, Any]]) -> None:
    """写透任务清单（旁路设施：失败只记日志，不弄断工具执行链）。"""
    try:
        path = _tasks_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _logger.warning("task list persist failed", error=f"{type(e).__name__}: {e}")


def load_persisted_tasks() -> List[Dict[str, Any]]:
    """读取落盘的任务清单；缺失/损坏返回空表（不抛）。"""
    try:
        path = _tasks_file_path()
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        _logger.warning("task list load failed", error=f"{type(e).__name__}: {e}")
        return []
