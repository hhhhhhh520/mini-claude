"""/rewind 命令测试（P4-1）。

真实 checkpointer + fake LLM 建图，monkeypatch rewind handler 的取图函数。
"""

from types import SimpleNamespace

import pytest

from mini_claude.cli.commands.base import CommandContext, get_command_registry
from mini_claude.cli.commands.rewind_handler import RewindHandler
from mini_claude.cli.display import display


def _ctx(session, args=""):
    return CommandContext(session=session, command="/rewind", args=args, display=display)


@pytest.fixture
async def session_with_graph(tmp_path, monkeypatch):
    """跑两轮真实图；返回 (session, graph)。连接与图随测试事件循环收口。"""
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
    tid = "t-cmd-rewind"
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}
    await graph.ainvoke(create_turn_increment("第一轮", tid), cfg)
    await graph.ainvoke(create_turn_increment("第二轮", tid), cfg)

    session = SimpleNamespace(thread_id=tid, messages=[], _rewind_configurable=None)
    monkeypatch.setattr("mini_claude.cli.commands.rewind_handler._get_session_graph", lambda: graph)
    yield session, graph

    await close_checkpoint_connections()


class TestRewindCommand:
    @pytest.mark.asyncio
    async def test_list_shows_turn_boundaries(self, session_with_graph):
        session, graph = session_with_graph
        result = await RewindHandler().handle(_ctx(session))
        assert result.error is None
        assert "第一轮" in result.message and "第二轮" in result.message

    @pytest.mark.asyncio
    async def test_pick_sets_rewind_configurable(self, session_with_graph):
        session, graph = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "1"))
        assert result.error is None
        assert session._rewind_configurable is not None
        assert "checkpoint_id" in session._rewind_configurable
        contents = [
            m.get("content", "") if isinstance(m, dict) else str(getattr(m, "content", ""))
            for m in session.messages
        ]
        assert any("第一轮" in c for c in contents)

    @pytest.mark.asyncio
    async def test_invalid_index_errors(self, session_with_graph):
        session, graph = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "99"))
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_non_numeric_args_shows_usage(self, session_with_graph):
        session, graph = session_with_graph
        result = await RewindHandler().handle(_ctx(session, "abc"))
        assert result.error is not None or "编号" in result.message

    @pytest.mark.asyncio
    async def test_no_checkpoints_friendly(self, tmp_path, monkeypatch):
        from mini_claude.agent.graph import build_agent_graph

        graph = build_agent_graph(checkpointer_path=str(tmp_path / "empty.db"))
        monkeypatch.setattr(
            "mini_claude.cli.commands.rewind_handler._get_session_graph", lambda: graph
        )
        session = SimpleNamespace(thread_id="never-ran", messages=[], _rewind_configurable=None)
        result = await RewindHandler().handle(_ctx(session))
        assert result.error is None
        assert "没有" in result.message or "无" in result.message

    def test_registered(self):
        assert get_command_registry().get_handler("/rewind") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
