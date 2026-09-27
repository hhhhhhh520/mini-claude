"""/rewind 命令（P4-1）：列出回合边界 checkpoint，选择后从该点分叉重跑。

底层是 LangGraph 时间旅行：get_state_history 列快照，/rewind <n> 把快照的
configurable（含 checkpoint_id）暂存到 session._rewind_configurable，
下一轮用户输入由 REPL 带该 configurable 做增量 fork——分叉后旧分支仍在
SQLite 里（checkpoint 链），可再次 /rewind。
"""

from typing import TYPE_CHECKING, List

from .base import CommandHandler, CommandResult

if TYPE_CHECKING:
    pass

# 回合边界：即将进入 think（回合开始）或已到 END（回合完成）
_BOUNDARY_NEXT = {("think",), ()}


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
        if not args:
            return CommandResult(handled=True, message=self._format_list(boundaries))

        if not args.isdigit():
            return CommandResult(
                handled=True,
                error=f"无效编号 {args!r}——用法：/rewind 查看列表，/rewind <编号> 回退",
            )

        idx = int(args)
        if idx < 1 or idx > len(boundaries):
            return CommandResult(
                handled=True, error=f"编号超出范围（1-{len(boundaries)}），用 /rewind 查看列表"
            )

        pick = boundaries[idx - 1]
        # 存整个 configurable（含 checkpoint_id / checkpoint_ns 等），fork 语义由
        # LangGraph 保证；下轮用户输入带上它做增量分叉，用后即清。
        ctx.session._rewind_configurable = dict(pick.config.get("configurable", {}))
        ctx.session.messages = [
            {"role": "user" if m.type == "human" else "assistant", "content": str(m.content)}
            for m in (pick.values.get("messages") or [])
        ]

        return CommandResult(
            handled=True,
            message=(
                f"已回退到 #{idx}（step={pick.metadata.get('step')}，"
                f"历史 {len(ctx.session.messages)} 条消息）。\n"
                "下一条输入将从该点分叉重跑；再次 /rewind 可回到更早的位置。"
            ),
        )

    def _format_list(self, boundaries: list) -> str:
        lines = ["可回退的回合边界（新 → 旧）："]
        for i, snap in enumerate(boundaries, 1):
            step = snap.metadata.get("step")
            at_end = "（回合结束）" if snap.next == () else "（回合开始）"
            lines.append(f"  #{i}  step={step}  {at_end}  {_preview(snap.values.get('messages'))}")
        lines.append("用 /rewind <编号> 回退；分叉后旧对话仍保留在 checkpoint 链中。")
        return "\n".join(lines)
