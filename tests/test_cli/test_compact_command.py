"""/compact 命令测试：手动压缩 + 新线程播种 + PreCompact hook。

架构要点（为什么播种新线程）：messages 是裸 add-reducer，aupdate_state 只能
拼接不能替换——压缩结果写入**全新 thread_id**（空线程首写即纯替换），
旧线程 checkpoint 链原样保留在 SQLite 里。
"""

from types import SimpleNamespace

import pytest

from mini_claude.cli.commands.base import CommandContext, get_command_registry
from mini_claude.cli.commands.compact_handler import (
    CompactHandler,
    _drop_orphan_tool_results,
    _litellm_to_langchain,
)
from mini_claude.cli.display import display


def _ctx(session, args=""):
    return CommandContext(session=session, command="/compact", args=args, display=display)


def _fake_llm_response(content="摘要内容"):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


@pytest.fixture
async def session_with_graph(tmp_path, monkeypatch):
    """跑三轮真实图（6 条消息，达到压缩下限）；连接与图随测试事件循环收口。"""
    from mini_claude.agent.graph import build_agent_graph, close_checkpoint_connections
    from mini_claude.agent.nodes import _shared
    from mini_claude.agent.state import create_turn_increment
    from mini_claude.config.settings import settings

    provider = _shared.llm_provider

    async def fake_chat(*a, **k):
        return _fake_llm_response("好")

    async def fake_stream(*a, **k):
        return {"content": "好", "tool_calls": None}

    monkeypatch.setattr(provider, "chat", fake_chat)
    monkeypatch.setattr(provider, "chat_stream_with_tools", fake_stream)
    monkeypatch.setattr(settings, "streaming_enabled", False)

    graph = build_agent_graph(checkpointer_path=str(tmp_path / "ckpt.db"))
    tid = "t-cmd-compact"
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}
    for text in ("第一轮", "第二轮", "第三轮"):
        await graph.ainvoke(create_turn_increment(text, tid), cfg)

    session = SimpleNamespace(
        thread_id=tid, messages=[], _rewind_configurable=None, _session_hook_context=""
    )
    monkeypatch.setattr(
        "mini_claude.cli.commands.compact_handler._get_session_graph", lambda: graph
    )
    yield session, graph

    await close_checkpoint_connections()


class TestCompactCommand:
    @pytest.mark.asyncio
    async def test_short_history_noop(self, session_with_graph):
        """空/过短历史直接友好提示，不换线程。"""
        session, graph = session_with_graph
        session.thread_id = "t-never-ran"
        old_tid = session.thread_id
        result = await CompactHandler().handle(_ctx(session))
        assert result.error is None
        assert "无需压缩" in result.message or "太短" in result.message
        assert session.thread_id == old_tid

    @pytest.mark.asyncio
    async def test_compact_seeds_new_thread(self, session_with_graph):
        """压缩结果播种到新线程：新线程可读、含摘要、旧线程保留。"""
        session, graph = session_with_graph
        old_tid = session.thread_id
        session._rewind_configurable = {"checkpoint_id": "fake-from-old-thread"}
        result = await CompactHandler().handle(_ctx(session))
        assert result.error is None, f"压缩失败：{result.error}"
        new_tid = session.thread_id
        assert new_tid != old_tid, "压缩后必须切换到新线程"
        assert session._rewind_configurable is None, "旧线程的 rewind 游标必须作废"

        snap = await graph.aget_state({"configurable": {"thread_id": new_tid}})
        msgs = snap.values.get("messages") or []
        assert msgs, "新线程应播种压缩后的历史"
        assert any("历史对话摘要" in str(getattr(m, "content", "")) for m in msgs)

        old_snap = await graph.aget_state({"configurable": {"thread_id": old_tid}})
        old_len = len(old_snap.values.get("messages") or [])
        assert old_len >= 6, "旧线程历史必须原样保留"

    @pytest.mark.asyncio
    async def test_custom_instructions_reach_engine(self, session_with_graph, monkeypatch):
        """`/compact 保留XXX` 的自定义指令必须传给摘要引擎。"""
        from mini_claude.utils.token_manager import TokenCounter

        captured = {}

        async def fake_summarize(self, messages, llm_chat_func, **kwargs):
            captured["custom_instructions"] = kwargs.get("custom_instructions", "")
            summary = {"role": "assistant", "content": "[历史对话摘要]\n摘要"}
            return messages[:1] + [summary] + messages[-2:], "摘要"

        monkeypatch.setattr(TokenCounter, "summarize_messages", fake_summarize)
        session, _ = session_with_graph
        result = await CompactHandler().handle(_ctx(session, "保留 API 设计决策"))
        assert result.error is None
        assert captured["custom_instructions"] == "保留 API 设计决策"

    @pytest.mark.asyncio
    async def test_pre_compact_hook_fired_manual(self, session_with_graph, monkeypatch):
        calls = []

        class _FakeDispatcher:
            async def dispatch_pre_compact(self, trigger, custom_instructions="", thread_id=""):
                calls.append({"trigger": trigger, "custom_instructions": custom_instructions})

        import mini_claude.hooks.dispatcher as dispatcher_mod

        monkeypatch.setattr(dispatcher_mod, "get_hook_dispatcher", lambda: _FakeDispatcher())
        session, _ = session_with_graph
        result = await CompactHandler().handle(_ctx(session, "保留决策"))
        assert result.error is None
        assert calls and calls[0]["trigger"] == "manual"
        assert calls[0]["custom_instructions"] == "保留决策"

    @pytest.mark.asyncio
    async def test_engine_unchanged_result_noop(self, session_with_graph, monkeypatch):
        """摘要引擎原样返回（历史不足）时不播种、不换线程。"""
        from mini_claude.utils.token_manager import TokenCounter

        async def fake_summarize(self, messages, llm_chat_func, **kwargs):
            return messages, None

        monkeypatch.setattr(TokenCounter, "summarize_messages", fake_summarize)
        session, _ = session_with_graph
        old_tid = session.thread_id
        result = await CompactHandler().handle(_ctx(session))
        assert result.error is None
        assert "无法压缩" in result.message or "保持原样" in result.message
        assert session.thread_id == old_tid

    def test_registered(self):
        assert get_command_registry().get_handler("/compact") is not None


class TestProtocolHelpers:
    """ISSUE-026 红线：压缩结果不得携带孤儿 tool 结果。"""

    def test_orphan_tool_results_dropped(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "[历史对话摘要]\n摘要"},
            {"role": "tool", "tool_call_id": "orphan-1", "content": "无主结果"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "keep-1",
                        "type": "function",
                        "function": {"name": "ls", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "keep-1", "content": "有主结果"},
        ]
        out = _drop_orphan_tool_results(msgs)
        ids = [m.get("tool_call_id") for m in out if m.get("role") == "tool"]
        assert ids == ["keep-1"], "无主的 tool 结果必须被修剪"

    def test_paired_results_kept(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "ls", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "r1"},
        ]
        assert _drop_orphan_tool_results(msgs) == msgs

    def test_litellm_to_langchain_tool_roundtrip(self):
        from langchain_core.messages import ToolMessage

        m = {"role": "tool", "tool_call_id": "abc", "content": "结果"}
        converted = _litellm_to_langchain(m)
        assert isinstance(converted, ToolMessage)
        assert converted.tool_call_id == "abc" and converted.content == "结果"

    def test_litellm_to_langchain_assistant_tool_calls(self):
        from langchain_core.messages import AIMessage

        m = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                }
            ],
        }
        converted = _litellm_to_langchain(m)
        assert isinstance(converted, AIMessage)
        assert converted.tool_calls[0]["name"] == "read_file"
        assert converted.tool_calls[0]["args"] == {"path": "a.py"}
        assert converted.tool_calls[0]["id"] == "t1"

    def test_litellm_to_langchain_user(self):
        from langchain_core.messages import HumanMessage

        converted = _litellm_to_langchain({"role": "user", "content": "问题"})
        assert isinstance(converted, HumanMessage) and converted.content == "问题"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
