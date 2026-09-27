"""P4-1 /rewind 契约测试：真实 checkpointer + fake LLM。

三个契约：
1. 多轮增量传参：REPL 式多轮对话下用户消息不复制（当前全量传参有翻倍 bug 的回归守卫）
2. fork：从回合边界快照带 checkpoint_id + 增量输入重跑，历史 = 快照历史 + 新消息，无重复
3. 分叉后的回合继续写 checkpoint（/resume 语义不断）
连接生命周期由 _drain fixture 收口。
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage


@pytest.fixture(autouse=True)
async def _drain_checkpoint_conns():
    from mini_claude.agent.graph import close_checkpoint_connections

    yield
    await close_checkpoint_connections()


@pytest.fixture
def fake_provider(monkeypatch):
    from mini_claude.agent.nodes import _shared

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

    from unittest.mock import MagicMock

    from mini_claude.config.settings import settings as _settings

    degr = MagicMock()
    degr.model.get_current_model.return_value = _settings.default_model
    import mini_claude.agent.nodes.act as act_mod

    monkeypatch.setattr(act_mod, "get_degradation_manager", lambda: degr)
    return provider


def _turn_increment(user_input, thread_id):
    """REPL 将采用的每轮增量构造（create_turn_increment 的预期形态）"""
    from mini_claude.agent.state import create_turn_increment

    return create_turn_increment(user_input, thread_id=thread_id)


async def _list_boundary_snapshots(graph, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    snaps = [s async for s in graph.aget_state_history(cfg)]
    return [s for s in snaps if s.next in (("think",), ())]


@pytest.mark.parametrize("streaming", [False], ids=["non-stream"])
async def test_multi_turn_increment_no_duplication(tmp_path, fake_provider, streaming, monkeypatch):
    """多轮会话用增量传参：checkpoint 里历史不复制（旧全量传参会把'第一轮'存两份）"""
    from mini_claude.agent.graph import build_agent_graph
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", streaming)
    db = str(tmp_path.resolve() / "ckpt.db")
    tid = "t-multi-inc"
    graph = build_agent_graph(checkpointer_path=db)
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}

    await graph.ainvoke(_turn_increment("第一轮", tid), cfg)
    result2 = await graph.ainvoke(_turn_increment("第二轮", tid), cfg)

    humans = [str(m.content) for m in result2["messages"] if isinstance(m, HumanMessage)]
    assert humans == ["第一轮", "第二轮"], f"多轮增量不得复制历史，实际 {humans}"


@pytest.mark.parametrize("streaming", [False], ids=["non-stream"])
async def test_rewind_fork_from_boundary(tmp_path, fake_provider, streaming, monkeypatch):
    """rewind = 取回合边界快照 + checkpoint_id + 增量输入 → 分叉重跑无重复"""
    from mini_claude.agent.graph import build_agent_graph
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", streaming)
    db = str(tmp_path.resolve() / "ckpt.db")
    tid = "t-rewind"
    graph = build_agent_graph(checkpointer_path=db)
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}

    await graph.ainvoke(_turn_increment("第一轮", tid), cfg)
    await graph.ainvoke(_turn_increment("第二轮", tid), cfg)

    boundaries = await _list_boundary_snapshots(graph, tid)
    assert len(boundaries) >= 2, f"至少有两个回合边界快照，实际 {len(boundaries)}"

    # 选取"含第一轮、不含第二轮"的回合边界 = 第一轮结束
    def _has(msgs, text):
        return any(text in str(getattr(m, "content", "")) for m in msgs)

    candidates = [
        s
        for s in boundaries
        if _has(s.values.get("messages"), "第一轮") and not _has(s.values.get("messages"), "第二轮")
    ]
    assert candidates, "找不到第一轮结束的边界快照"
    pick = candidates[0]
    fork_cfg = {
        "configurable": {
            "thread_id": tid,
            "checkpoint_id": pick.config["configurable"]["checkpoint_id"],
        },
        "recursion_limit": 50,
    }
    result = await graph.ainvoke(_turn_increment("分叉新输入", tid), fork_cfg)

    humans = [str(m.content) for m in result["messages"] if isinstance(m, HumanMessage)]
    assert humans == ["第一轮", "分叉新输入"], (
        f"分叉后应只有第一轮+新输入，实际 {humans}（第二轮应被丢弃）"
    )


@pytest.mark.asyncio
async def test_rewind_fork_persists_new_checkpoints(tmp_path, fake_provider, monkeypatch):
    """分叉回合继续写 checkpoint，且最新状态=分叉结果（/resume 语义不断）"""
    from mini_claude.agent.graph import build_agent_graph
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", False)
    db = str(tmp_path.resolve() / "ckpt.db")
    tid = "t-rewind-persist"
    graph = build_agent_graph(checkpointer_path=db)
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}

    await graph.ainvoke(_turn_increment("第一轮", tid), cfg)
    await graph.ainvoke(_turn_increment("第二轮", tid), cfg)
    boundaries = await _list_boundary_snapshots(graph, tid)

    def _has(msgs, text):
        return any(text in str(getattr(m, "content", "")) for m in msgs)

    candidates = [
        s
        for s in boundaries
        if _has(s.values.get("messages"), "第一轮") and not _has(s.values.get("messages"), "第二轮")
    ]
    assert candidates, "找不到第一轮结束的边界快照"
    pick = candidates[0]
    fork_cfg = {
        "configurable": {
            "thread_id": tid,
            "checkpoint_id": pick.config["configurable"]["checkpoint_id"],
        },
        "recursion_limit": 50,
    }
    await graph.ainvoke(_turn_increment("分叉新输入", tid), fork_cfg)

    latest = await graph.aget_state({"configurable": {"thread_id": tid}})
    contents = [str(getattr(m, "content", "")) for m in latest.values["messages"]]
    assert any("分叉新输入" in c for c in contents), "分叉回合未写入最新 checkpoint"
    assert not any("第二轮" in c for c in contents), "分叉后旧'第二轮'不应残留在最新状态"


async def test_create_turn_increment_shape():
    """增量必须带全部必需字段，但不得携带 todos（跨回合保留）与旧历史"""
    from mini_claude.agent.state import create_turn_increment

    inc = create_turn_increment("新任务", thread_id="t1")
    assert len(inc["messages"]) == 1
    assert isinstance(inc["messages"][0], HumanMessage)
    assert inc["messages"][0].content == "新任务"
    assert inc["current_task"] == "新任务"
    assert inc["iteration"] == 0
    assert inc["thread_id"] == "t1"
    assert "todos" not in inc, "todos 是跨回合状态，增量里带空列表会把回合间进度清掉"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
