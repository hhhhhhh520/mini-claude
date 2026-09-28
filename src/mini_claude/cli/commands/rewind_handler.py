"""/rewind 命令（P4-1；收敛批次③扩展代码回退）：列出回合边界 checkpoint，
选择后从该点分叉重跑。

底层是 LangGraph 时间旅行：get_state_history 列快照，/rewind <n> 把快照的
configurable（含 checkpoint_id）暂存到 session._rewind_configurable，
下一轮用户输入由 REPL 带该 configurable 做增量 fork——分叉后旧分支仍在
SQLite 里（checkpoint 链），可再次 /rewind。

scope 参数（对齐 Claude Code 的 对话/代码/两者 三选）：
- `/rewind <n>`        仅回退对话（默认，行为与历史版本一致）
- `/rewind <n> code`   仅恢复文件（utils/file_history 日志回放）
- `/rewind <n> both`   对话 + 文件都回退
代码回退只覆盖会话内经 write/edit/force_write 的修改（进程内日志，
跨会话修改与 run_command 侧门修改不在恢复范围——诚实边界，见
utils/file_history.py 模块注释）。
"""

import time as _time
from datetime import datetime
from typing import TYPE_CHECKING, List

from .base import CommandHandler, CommandResult

if TYPE_CHECKING:
    pass

# 回合边界：即将进入 think（回合开始）或已到 END（回合完成）
_BOUNDARY_NEXT = {("think",), ()}

_SCOPES = {
    "chat": "chat",
    "code": "code",
    "both": "both",
    "对话": "chat",
    "代码": "code",
    "两者": "both",
}


def _get_session_graph():
    """取当前 REPL 的图（延迟导入：须在运行中的事件循环里调用）。"""
    from ...agent.graph import get_agent_graph

    return get_agent_graph()


def _preview(messages, limit: int = 40) -> str:
    for m in reversed(messages or []):
        text = str(getattr(m, "content", "") or "").strip().replace("\n", " ")
        if text:
            return text[:limit] + ("…" if len(text) > limit else "")
    return "(无消息)"


def _snapshot_epoch(snapshot) -> float:
    """checkpoint 时间转 epoch（StateSnapshot.created_at，ISO 串）。

    metadata 里没有可靠的时间戳——created_at 是文档化字段；两者都缺时
    回退当前时间（等于"不恢复任何文件"，安全侧）。
    """
    for candidate in (getattr(snapshot, "created_at", None), snapshot.metadata.get("ts")):
        if candidate:
            try:
                return datetime.fromisoformat(str(candidate)).timestamp()
            except (ValueError, TypeError):
                continue
    return _time.time()


class RewindHandler(CommandHandler):
    """会话回退命令。"""

    commands: List[str] = ["/rewind"]

    async def handle(self, ctx) -> CommandResult:
        graph = _get_session_graph()
        thread_id = ctx.thread_id
        cfg = {"configurable": {"thread_id": thread_id}}

        try:
            snapshots = [s async for s in graph.aget_state_history(cfg)]
        except Exception as e:
            return CommandResult(handled=True, error=f"读取 checkpoint 历史失败：{e}")

        boundaries = [s for s in snapshots if s.next in _BOUNDARY_NEXT]
        if not boundaries:
            return CommandResult(
                handled=True,
                message="当前会话没有可回退的 checkpoint（先聊出一点历史再 /rewind）。",
            )

        args = (ctx.args or "").strip()
        parts = args.split()
        scope = "chat"
        if len(parts) >= 2:
            scope = _SCOPES.get(parts[1].lower())
            if scope is None:
                return CommandResult(
                    handled=True,
                    error=f"无效范围 {parts[1]!r}——用 /rewind <n> [chat|code|both]",
                )
        if not parts:
            return CommandResult(handled=True, message=self._format_list(boundaries))

        if not parts[0].isdigit():
            return CommandResult(
                handled=True,
                error=f"无效编号 {parts[0]!r}——用法：/rewind 查看列表，/rewind <编号> [chat|code|both] 回退",
            )

        idx = int(parts[0])
        if idx < 1 or idx > len(boundaries):
            return CommandResult(
                handled=True, error=f"编号超出范围（1-{len(boundaries)}），用 /rewind 查看列表"
            )

        pick = boundaries[idx - 1]

        # 代码回退（收敛批次③）：按所选 checkpoint 的时间戳回放文件日志
        file_report = ""
        if scope in ("code", "both"):
            from ...utils.file_history import restore_since

            boundary = _snapshot_epoch(pick)
            restored = restore_since(boundary)
            if restored:
                lines = ["文件恢复："]
                for path, action in restored:
                    short = (
                        "已删除（当时新建）"
                        if action == "deleted"
                        else (
                            f"已恢复（{action}）"
                            if not action.startswith("failed")
                            else f"恢复失败（{action}）"
                        )
                    )
                    lines.append(f"  {path}: {short}")
                file_report = "\n" + "\n".join(lines)
            else:
                file_report = (
                    "\n该时点之后没有可恢复的文件修改（或仅 run_command 侧门修改，不在记录范围）。"
                )

        # 存整个 configurable（含 checkpoint_id / checkpoint_ns 等），fork 语义由
        # LangGraph 保证；下轮用户输入带上它做增量分叉，用后即清。
        if scope in ("chat", "both"):
            ctx.session._rewind_configurable = dict(pick.config.get("configurable", {}))
            ctx.session.messages = [
                {"role": "user" if m.type == "human" else "assistant", "content": str(m.content)}
                for m in (pick.values.get("messages") or [])
            ]

        scope_note = {
            "chat": "下一条输入将从该点分叉重跑；再次 /rewind 可回到更早的位置。",
            "code": "仅恢复文件，对话未回退。",
            "both": "下一条输入将从该点分叉重跑；再次 /rewind 可回到更早的位置。",
        }[scope]

        return CommandResult(
            handled=True,
            message=(
                f"已回退到 #{idx}（step={pick.metadata.get('step')}，"
                f"历史 {len(ctx.session.messages) if scope != 'code' else '未变更'} 条消息）。"
                + file_report
                + "\n"
                + scope_note
            ),
        )

    def _format_list(self, boundaries: list) -> str:
        lines = ["可回退的回合边界（新 → 旧）："]
        for i, snap in enumerate(boundaries, 1):
            step = snap.metadata.get("step")
            at_end = "（回合结束）" if snap.next == () else "（回合开始）"
            lines.append(f"  #{i}  step={step}  {at_end}  {_preview(snap.values.get('messages'))}")
        lines.append("用 /rewind <编号> [chat|code|both] 回退（默认 chat；code 恢复文件）。")
        return "\n".join(lines)
