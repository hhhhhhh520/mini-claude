"""/rewind 代码回退集成测试（收敛批次③）：scope 三选 + 文件恢复。"""

from types import SimpleNamespace

import pytest

from mini_claude.cli.commands.base import CommandContext
from mini_claude.cli.commands.rewind_handler import RewindHandler
from mini_claude.cli.display import display
from mini_claude.utils import file_history as fh


def _ctx(session, args=""):
    return CommandContext(session=session, command="/rewind", args=args, display=display)


@pytest.fixture
async def session_with_graph(tmp_path, monkeypatch):
    """三轮真实图 + 两个被日志跟踪的文件（一个改写、一个新建）。"""
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

    graph = build_agent_graph(checkpointer_path=str(tmp_path / "ckpt.db"))
    tid = "t-rewind-code"
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}
    for text in ("第一轮", "第二轮", "第三轮"):
        await graph.ainvoke(create_turn_increment(text, tid), cfg)

    # 图跑完后模拟"回合期间的文件修改"：先记录改动前状态，再改动
    # （ts 必然晚于所有回合边界的 created_at）
    fh.reset()
    original = tmp_path / "original.txt"
    original.write_text("原始版本", encoding="utf-8")
    fh.record_before_write(str(original))
    original.write_text("被改掉", encoding="utf-8")
    created = tmp_path / "created.txt"
    fh.record_before_write(str(created))  # 记录时不存在 → 回退=删除
    created.write_text("新建", encoding="utf-8")

    session = SimpleNamespace(thread_id=tid, messages=[], _rewind_configurable=None)
    monkeypatch.setattr("mini_claude.cli.commands.rewind_handler._get_session_graph", lambda: graph)
    yield session, graph, original, created

    fh.reset()
    await close_checkpoint_connections()


class TestRewindCodeScope:
    @pytest.mark.asyncio
    async def test_code_scope_restores_files(self, session_with_graph):
        session, graph, original, created = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "1 code"))
        assert result.error is None, result.error
        assert original.read_text(encoding="utf-8") == "原始版本", "改写文件必须恢复"
        assert not created.exists(), "期间新建的文件必须删除"
        assert "文件恢复" in result.message
        # code scope 不回退对话
        assert session._rewind_configurable is None

    @pytest.mark.asyncio
    async def test_default_scope_is_chat_only(self, session_with_graph):
        session, graph, original, created = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "1"))
        assert result.error is None
        assert original.read_text(encoding="utf-8") == "被改掉", "默认不动文件"
        assert created.exists()
        assert session._rewind_configurable is not None

    @pytest.mark.asyncio
    async def test_both_scope_restores_and_forks(self, session_with_graph):
        session, graph, original, created = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "1 both"))
        assert result.error is None
        assert original.read_text(encoding="utf-8") == "原始版本"
        assert not created.exists()
        assert session._rewind_configurable is not None, "both 也要分叉对话"

    @pytest.mark.asyncio
    async def test_invalid_scope_rejected(self, session_with_graph):
        session, graph, original, created = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "1 wat"))
        assert result.error is not None and "chat|code|both" in result.error

    @pytest.mark.asyncio
    async def test_list_shows_scope_hint(self, session_with_graph):
        session, graph, original, created = session_with_graph
        result = await RewindHandler().handle(_ctx(session, ""))
        assert result.error is None
        assert "chat|code|both" in result.message
