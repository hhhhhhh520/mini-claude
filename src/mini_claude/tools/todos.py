"""todo_write tool - session-level task checklist (P1-1).

清单本身存放在 AgentState.todos（全量替换语义，不挂 add reducer）。
工具只做校验与确认输出；state 的写入由 act 执行链在参数校验通过后完成
（工具拿不到 state，这是既有架构：工具无状态、状态更新走 act）。
"""

from typing import Any, Dict, List

from .base import BaseTool, register_tool

VALID_STATUSES = ("pending", "in_progress", "completed")


def validate_todos(todos: Any) -> List[str]:
    """校验 todo 清单，返回错误列表（空列表 = 校验通过）。

    规则（对齐 Claude Code TodoWrite 语义）：
    - 必须是 list（空 list 合法，表示清空清单）
    - 每项是 dict，content 非空字符串，status 属于 VALID_STATUSES
    - 非空清单时恰好一个 in_progress（0 个或多个都拒绝）
    - content 不得重复
    """
    errors: List[str] = []

    if not isinstance(todos, list):
        return [f"todos 必须是数组，收到 {type(todos).__name__}"]

    in_progress_count = 0
    seen_contents = set()
    for i, item in enumerate(todos):
        if not isinstance(item, dict):
            errors.append(f"todos[{i}] 必须是对象")
            continue

        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"todos[{i}].content 不能为空")
        elif content in seen_contents:
            errors.append(f"todos[{i}].content 与其他项重复: {content!r}")
        else:
            seen_contents.add(content)

        status = item.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"todos[{i}].status 非法: {status!r}（必须是 {'/'.join(VALID_STATUSES)}）"
            )
        elif status == "in_progress":
            in_progress_count += 1

    if todos and in_progress_count != 1:
        errors.append(f"非空清单必须恰好一个 in_progress，当前 {in_progress_count} 个")

    return errors


def _summarize(todos: List[Dict[str, Any]]) -> str:
    counts = {s: 0 for s in VALID_STATUSES}
    for t in todos:
        counts[t["status"]] += 1
    if not todos:
        return "Todos cleared."
    in_progress = next((t for t in todos if t["status"] == "in_progress"), None)
    parts = [
        f"Todos updated: {counts['completed']} completed, "
        f"{counts['in_progress']} in progress, {counts['pending']} pending."
    ]
    if in_progress:
        label = in_progress.get("active_form") or in_progress["content"]
        parts.append(f"Current: {label}")
    return "\n".join(parts)


class TodoWriteTool(BaseTool):
    """提交会话级 todo 清单（全量替换）。

    每次调用必须携带完整清单（新增/更新/删除都在同一次提交里），
    而不是增量操作——这与 act 执行链的全量替换写入语义一一对应。
    """

    @property
    def name(self) -> str:
        return "todo_write"

    @property
    def description(self) -> str:
        return (
            "Write the session task checklist. Pass the COMPLETE list every time. "
            "Each item: {content, status: pending|in_progress|completed, active_form?}. "
            "Exactly one item must be in_progress while working. "
            "Use it for multi-step tasks (3+ steps) so the user can see progress; "
            "skip it for trivial single-step requests. "
            "Pass an empty list to clear the checklist."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "The complete todo list (full replacement)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Task description (imperative form)",
                            },
                            "status": {
                                "type": "string",
                                "enum": list(VALID_STATUSES),
                                "description": "Task state",
                            },
                            "active_form": {
                                "type": "string",
                                "description": "Present-continuous label shown while in progress",
                            },
                        },
                        "required": ["content", "status"],
                    },
                }
            },
            "required": ["todos"],
        }

    async def execute(self, todos: List[Dict[str, Any]]) -> str:
        errors = validate_todos(todos)
        if errors:
            return "Error: todo list 校验失败：\n- " + "\n- ".join(errors)
        return _summarize(todos)


register_tool(TodoWriteTool())
