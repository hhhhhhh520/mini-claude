"""auto-compact 落盘测试（收敛批次②）。

对齐 Claude Code auto-compact：回合前预算检查，超限即压缩并播种新线程
（持久历史真正缩减，区别于 act 内只作用于当次 prompt 的摘要）。
"""

from types import SimpleNamespace

import pytest

from mini_claude.cli.repl import REPLSession


@pytest.fixture
async def session_with_graph(tmp_path, monkeypatch):
    from mini_claude.agent.graph import build_agent_graph, close_checkpoint_connections
    from mini_claude.agent.nodes import _shared
    from mini_claude.agent.state import create_turn_increment
    from mini_claude.config.settings import settings

    provider = _shared.llm_provider
    msg = SimpleNamespace(content="好", tool_calls=None)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )

    async def fake_chat(*a, **k):
        return response

    async def fake_stream(*a, **k):
        return {"content": "好", "tool_calls": None}

    monkeypatch.setattr(provider, "chat", fake_chat)
    monkeypatch.setattr(provider, "chat_stream_with_tools", fake_stream)
    monkeypatch.setattr(settings, "streaming_enabled", False)
    monkeypatch.setattr(settings, "auto_compact_enabled", True)

    graph = build_agent_graph(checkpointer_path=str(tmp_path / "ckpt.db"))
    tid = "t-auto-compact"
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}
    for text in ("第一轮", "第二轮", "第三轮"):
        await graph.ainvoke(create_turn_increment(text, tid), cfg)

    session = REPLSession()
    session.thread_id = tid
    yield session, graph

    await close_checkpoint_connections()


def _force_over_budget(monkeypatch):
    from mini_claude.utils.token_manager import TokenCounter

    def fake_check(self, messages, reserved_output=4096):
        return {"ok": False, "reason": "over", "stats": {}, "action": None}

    monkeypatch.setattr(TokenCounter, "check_budget", fake_check)


def _force_within_budget(monkeypatch):
    from mini_claude.utils.token_manager import TokenCounter

    def fake_check(self, messages, reserved_output=4096):
        return {"ok": True, "reason": "within", "stats": {}, "action": None}

    monkeypatch.setattr(TokenCounter, "check_budget", fake_check)


@pytest.mark.asyncio
async def test_over_budget_compacts_and_switches_thread(session_with_graph, monkeypatch):
    """超预算：压缩落盘、会话切新线程、tasks 随迁、旧线程保留。"""
    from mini_claude.agent.graph import close_checkpoint_connections

    _force_over_budget(monkeypatch)
    session, graph = session_with_graph
    old_tid = session.thread_id
    tasks = [
        {
            "id": "1",
            "subject": "任务",
            "description": "d",
            "status": "pending",
            "blocks": [],
            "blocked_by": [],
        }
    ]
    await graph.aupdate_state({"configurable": {"thread_id": old_tid}}, {"tasks": tasks})

    await session._maybe_auto_compact(graph)

    assert session.thread_id != old_tid, "超预算必须切到压缩后的新线程"
    assert session._rewind_configurable is None
    snap = await graph.aget_state({"configurable": {"thread_id": session.thread_id}})
    assert snap.values.get("tasks") == tasks, "tasks 必须随迁"
    new_msgs = snap.values.get("messages") or []
    old_snap = await graph.aget_state({"configurable": {"thread_id": old_tid}})
    assert len(new_msgs) <= len(old_snap.values.get("messages") or [])
    assert any("历史对话摘要" in str(getattr(m, "content", "")) for m in new_msgs), (
        "压缩必须真实发生（中段历史换成摘要）"
    )
    await close_checkpoint_connections()


@pytest.mark.asyncio
async def test_within_budget_noop(session_with_graph, monkeypatch):
    _force_within_budget(monkeypatch)
    session, graph = session_with_graph
    old_tid = session.thread_id
    await session._maybe_auto_compact(graph)
    assert session.thread_id == old_tid


@pytest.mark.asyncio
async def test_cooldown_prevents_recompact(session_with_graph, monkeypatch):
    """冷静期 60s：刚压缩过就不再压（防止连续空转）。"""
    _force_over_budget(monkeypatch)
    session, graph = session_with_graph
    first_tid = session.thread_id
    await session._maybe_auto_compact(graph)
    second_tid = session.thread_id
    assert second_tid != first_tid

    await session._maybe_auto_compact(graph)
    assert session.thread_id == second_tid, "冷静期内不得再次压缩"


@pytest.mark.asyncio
async def test_disabled_flag_skips(session_with_graph, monkeypatch):
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "auto_compact_enabled", False)
    _force_over_budget(monkeypatch)
    session, graph = session_with_graph
    old_tid = session.thread_id
    await session._maybe_auto_compact(graph)
    assert session.thread_id == old_tid


@pytest.mark.asyncio
async def test_short_history_noop(session_with_graph, monkeypatch):
    _force_over_budget(monkeypatch)
    session, graph = session_with_graph
    # 只有一轮的线程（2 条消息）不压缩
    from mini_claude.agent.graph import close_checkpoint_connections
    from mini_claude.agent.state import create_turn_increment

    tid = "t-short"
    await graph.ainvoke(
        create_turn_increment("唯一一轮", tid), {"configurable": {"thread_id": tid}}
    )
    session.thread_id = tid
    await session._maybe_auto_compact(graph)
    assert session.thread_id == tid
    await close_checkpoint_connections()
