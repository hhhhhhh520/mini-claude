"""agent 侧 hooks 接线测试：hook_context 注入 + SubagentStop 阻断。

- `hook_context` 是回合级 state 字段：UserPromptSubmit hook 注入的上下文，
  经 build_system_messages() 前置给 LLM（不进持久化历史——架构红线），
  当回合结束、下一轮增量不带它即自然失效。
- SubagentStop hook 阻断子代理收工：原因作为消息喂回，子代理继续
  （受 max_iterations 兜底，对齐 Claude Code 语义）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

from mini_claude.agent.nodes import _shared
from mini_claude.agent.nodes.act import act_node
from mini_claude.agent.nodes.observe import observe_node
from mini_claude.agent.state import StopReason, create_initial_state, create_turn_increment


class TestTurnIncrementCarriesHookContext:
    def test_increment_includes_hook_context(self):
        inc = create_turn_increment("问题", thread_id="t", hook_context="hook 给的上下文")
        assert inc["hook_context"] == "hook 给的上下文"

    def test_increment_defaults_empty(self):
        inc = create_turn_increment("问题", thread_id="t")
        assert inc["hook_context"] == ""


class TestHookContextReachesSystemMessages:
    def test_build_system_messages_accepts_hook_context(self):
        from mini_claude.agent.nodes._shared import build_system_messages

        msgs = build_system_messages(hook_context="回合级注入")
        joined = "\n".join(str(m.get("content", m)) for m in msgs)
        assert "回合级注入" in joined

    def test_build_system_messages_empty_context_no_extra(self):
        from mini_claude.agent.nodes._shared import build_system_messages

        baseline = build_system_messages()
        msgs = build_system_messages(hook_context="")
        assert len(msgs) == len(baseline)

    @pytest.mark.asyncio
    async def test_act_node_sends_hook_context_to_llm(self, _isolated_llm):
        """fake provider 捕获的消息里必须含 hook 注入的 system 内容"""
        captured = []

        async def fake_stream(messages=None, tools=None, **kwargs):
            captured.append(list(messages or []))
            return {"content": "好的", "tool_calls": None}

        with (
            patch.object(_shared.llm_provider, "chat_stream_with_tools", side_effect=fake_stream),
            patch.object(_shared.llm_provider, "chat", side_effect=fake_stream),
        ):
            state = create_initial_state("随便说句话")
            state["hook_context"] = "本回合特殊约定：回答必须以 HOOK-OK 结尾"
            await act_node(state)

        assert captured, "应有一次 LLM 调用"
        system_texts = [m.get("content", "") for m in captured[0] if m.get("role") == "system"]
        assert any("HOOK-OK" in t for t in system_texts), (
            f"hook_context 未进 system 消息：{system_texts}"
        )

    @pytest.fixture
    def _isolated_llm(self, monkeypatch):
        from mini_claude.config.settings import settings
        from mini_claude.utils.safety import get_rate_limiter

        monkeypatch.setattr(get_rate_limiter(), "check_limit", lambda *a, **k: True)
        degr = MagicMock()
        degr.model.get_current_model.return_value = settings.default_model
        degr.backoff = SimpleNamespace(max_retries=0, reset=lambda: None, wait=AsyncMock())
        degr.tool.should_skip.return_value = False
        degr.tool.get_replacement.return_value = None
        import mini_claude.agent.nodes.act as act_mod

        monkeypatch.setattr(act_mod, "get_degradation_manager", lambda: degr)


class TestSubagentStopHook:
    def _subagent_state(self):
        state = create_initial_state("写模块", thread_id="t")
        state["is_subagent"] = True
        state["messages"].append(
            ToolMessage(
                content="文件已写入", name="write_file", tool_call_id="call_1", status="success"
            )
        )
        return state

    def _dispatcher(self, blocked: bool, reason: str = ""):
        d = MagicMock()
        d.dispatch_subagent_stop = AsyncMock(return_value=(blocked, reason))
        return d

    @pytest.mark.asyncio
    async def test_block_forces_subagent_continue(self, monkeypatch):
        d = self._dispatcher(True, "还要补上单元测试")
        monkeypatch.setattr(
            "mini_claude.hooks.dispatcher.get_hook_dispatcher", lambda: d, raising=False
        )
        result = await observe_node(self._subagent_state())

        assert result["stop_reason"] == StopReason.CONTINUE, (
            f"SubagentStop 阻断时应继续，实际 {result.get('stop_reason')}"
        )
        assert result["messages"][-1].content.find("还要补上单元测试") >= 0
        d.dispatch_subagent_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_block_completes(self, monkeypatch):
        d = self._dispatcher(False)
        monkeypatch.setattr(
            "mini_claude.hooks.dispatcher.get_hook_dispatcher", lambda: d, raising=False
        )
        result = await observe_node(self._subagent_state())
        assert result["stop_reason"] == StopReason.TASK_COMPLETE

    @pytest.mark.asyncio
    async def test_hook_failure_does_not_block_completion(self, monkeypatch):
        d = MagicMock()
        d.dispatch_subagent_stop = AsyncMock(side_effect=RuntimeError("hook down"))
        monkeypatch.setattr(
            "mini_claude.hooks.dispatcher.get_hook_dispatcher", lambda: d, raising=False
        )
        result = await observe_node(self._subagent_state())
        assert result["stop_reason"] == StopReason.TASK_COMPLETE, "hook 异常不得卡死子代理"
