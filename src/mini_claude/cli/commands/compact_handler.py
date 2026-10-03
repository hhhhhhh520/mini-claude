"""/compact 命令：手动压缩当前会话历史（对标 Claude Code /compact）。

架构要点——为什么播种新线程而不是 aupdate_state 原线程：
messages 挂的是裸 operator.add reducer（见 agent/state.py 红线注释），
aupdate_state 走同一 reducer 只能**拼接**，永远无法缩减持久化历史。
因此压缩结果写入一个全新 thread_id：空线程当前状态为空，add([]) 即
纯替换。旧线程的 checkpoint 链原样留在 SQLite（可追溯），会话切换到
新线程后照常 /rewind（分叉点从播种快照起算）。

压缩引擎复用 act 自动压缩的 summarize_messages（utils/token_manager），
`/compact <自定义指令>` 透传为摘要提示词的额外要求。

协议红线（ISSUE-026）：摘要引擎的 keep_last 可能切在 assistant(tool_calls)
与 tool 结果中间，持久化前必须修剪孤儿 tool 结果，否则下轮 LLM 调用
线格式残缺，Qwen 类网关会从函数调用模式退化。
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .base import CommandHandler, CommandResult

# 历史不足 keep_first+keep_last（1+4=5）时摘要引擎原样返回，6 条起才有压缩空间
_MIN_MESSAGES_TO_COMPACT = 6


def _get_session_graph():
    """取当前 REPL 的图（延迟导入：须在运行中的事件循环里调用）。"""
    from ...agent.graph import get_agent_graph

    return get_agent_graph()


def _drop_orphan_tool_results(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """修剪没有对应 assistant tool_calls 的孤儿 tool 结果。

    摘要引擎保留的近端尾部可能从 tool 消息开头（调用它的 assistant 已被
    摘要吃掉）——这种残缺尾巴持久化后会让下轮 LLM 调用的线格式违反
    函数调用协议。
    """
    known_ids = set()
    for m in msgs:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_id = tc.get("id") if isinstance(tc, dict) else None
                if tc_id:
                    known_ids.add(tc_id)
    return [
        m for m in msgs if not (m.get("role") == "tool" and m.get("tool_call_id") not in known_ids)
    ]


def _litellm_to_langchain(m: Dict[str, Any]):
    """压缩后的 LiteLLM 消息 → LangChain 消息（播种用）。

    形状与 act.parse_tool_calls 的 AIMessage.tool_calls 约定一致：
    [{"id", "name", "args"}]。
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    role = m.get("role")
    content = m.get("content", "")
    if role == "assistant":
        tool_calls = []
        for tc in m.get("tool_calls") or []:
            try:
                args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "args": args,
                }
            )
        return AIMessage(content=content or "", tool_calls=tool_calls)
    if role == "tool":
        return ToolMessage(content=str(content), tool_call_id=m.get("tool_call_id", ""))
    return HumanMessage(content=str(content))


async def compact_session(
    graph,
    thread_id: str,
    custom_instructions: str = "",
    trigger: str = "manual",
) -> Tuple[Optional[str], str]:
    """压缩核心（/compact 与 auto-compact 共用，收敛批次②提取）。

    做 graph 级的事：PreCompact hook → LLM 摘要 → 修剪孤儿 tool 结果 →
    播种新线程（messages + 非空 tasks/todos 随迁）。

    Returns:
        (new_thread_id, 报告文本)；new_thread_id=None 表示未压缩
        （报告说明原因）。调用方负责把会话切到新线程。
    """
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(cfg)
    messages = list(snap.values.get("messages") or [])
    if len(messages) < _MIN_MESSAGES_TO_COMPACT:
        return None, f"当前会话历史 {len(messages)} 条消息，无需压缩。"

    # PreCompact hook：压缩前触发，只通知不判断
    try:
        from ...hooks.dispatcher import get_hook_dispatcher

        await get_hook_dispatcher().dispatch_pre_compact(
            trigger=trigger, custom_instructions=custom_instructions, thread_id=thread_id
        )
    except Exception:
        pass

    from ...agent.nodes._act_helpers import convert_message, setup_token_counter
    from ...agent.nodes._shared import get_llm_provider

    token_counter = setup_token_counter()
    litellm_messages = [convert_message(m) for m in messages]
    before_tokens = token_counter.count_messages_tokens(litellm_messages)

    async def llm_chat_for_summary(messages: List[Dict], **kwargs) -> Dict:
        return await get_llm_provider().chat(messages=messages, **kwargs)

    try:
        summarized, _summary_text = await token_counter.summarize_messages(
            litellm_messages,
            llm_chat_func=llm_chat_for_summary,
            custom_instructions=custom_instructions,
        )
    except Exception as e:
        raise RuntimeError(f"压缩失败：{e}") from e

    if summarized == litellm_messages:
        return None, "历史不足以压缩（摘要引擎未缩短），保持原样。"

    summarized = _drop_orphan_tool_results(summarized)
    compressed = [_litellm_to_langchain(m) for m in summarized]
    after_tokens = token_counter.count_messages_tokens(summarized)

    # 播种新线程：空线程首次 update 即纯替换（add-reducer 对空列表）。
    # tasks/todos 是 state 里的跨回合字段，必须随迁——只写 messages 会让
    # 压缩后清单静默清空（实际测试抓到的缺陷，有回归测试锁定）。
    new_tid = f"{thread_id}_c{uuid.uuid4().hex[:8]}"
    seed = {"messages": compressed}
    for field in ("tasks", "todos"):
        value = snap.values.get(field)
        if value:
            seed[field] = value
    await graph.aupdate_state({"configurable": {"thread_id": new_tid}}, seed)

    return (
        new_tid,
        f"已压缩：{len(messages)} 条消息 → {len(compressed)} 条，"
        f"tokens 约 {before_tokens} → {after_tokens}。",
    )


class CompactHandler(CommandHandler):
    """手动压缩会话历史命令。"""

    commands: List[str] = ["/compact"]

    async def handle(self, ctx) -> CommandResult:
        graph = _get_session_graph()
        tid = ctx.thread_id
        custom_instructions = (ctx.args or "").strip()

        try:
            new_tid, report = await compact_session(
                graph, tid, custom_instructions=custom_instructions, trigger="manual"
            )
        except Exception as e:
            return CommandResult(handled=True, error=str(e))

        if new_tid is None:
            return CommandResult(handled=True, message=report)

        # 会话切到新线程；旧线程的 rewind 游标跨线程无效，必须作废
        ctx.session.thread_id = new_tid
        ctx.session._rewind_configurable = None
        try:
            snap = await graph.aget_state({"configurable": {"thread_id": new_tid}})
            ctx.session.messages = [
                {
                    "role": "assistant" if getattr(m, "type", "") == "ai" else "user",
                    "content": str(getattr(m, "content", "")),
                }
                for m in (snap.values.get("messages") or [])
            ]
        except Exception:
            pass

        return CommandResult(
            handled=True,
            message=(
                f"{report}\n"
                f"会话已切换到新线程 {new_tid}（旧线程历史保留在 checkpoint 链中）。"
                + (f"\n压缩指令已生效：{custom_instructions}" if custom_instructions else "")
            ),
        )
