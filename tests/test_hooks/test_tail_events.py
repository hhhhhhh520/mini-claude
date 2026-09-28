"""尾部四事件 hooks 测试：SessionStart / SessionEnd / PreCompact / SubagentStart。

事件面收尾（6→10，对齐 Claude Code 全事件）：
- SessionStart：非阻断；exit 0 纯 stdout 或 hookSpecificOutput.additionalContext
  注入会话级上下文（经 hook_context 通道每回合前置）
- SessionEnd / PreCompact / SubagentStart：只触发不判断
- PreCompact 另有 auto 触发点：act 的 handle_token_budget 自动摘要压缩前
"""

import json
from types import SimpleNamespace

import pytest

from mini_claude.config.settings import settings
from mini_claude.hooks.config import HookCommand, HookConfig, HookRule, load_hooks_config
from mini_claude.hooks.dispatcher import HookDispatcher


def _cfg(*events) -> HookConfig:
    return HookConfig(
        entries={
            e: [HookRule(matcher="", hooks=[HookCommand(command=f"echo {e}")])] for e in events
        }
    )


def _runner(outputs):
    """假 runner：按序返回 outcome，并记录调用 payload。"""
    calls = []

    async def run(command, payload, timeout=None, cwd=None):
        calls.append(payload)
        return (
            outputs.pop(0)
            if outputs
            else SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)
        )

    return run, calls


@pytest.fixture
def hooks_on(monkeypatch):
    monkeypatch.setattr(settings, "hooks_enabled", True)


@pytest.fixture
def hooks_off(monkeypatch):
    """settings 默认 hooks_enabled=True（base_settings），关闭态必须显式钉死。"""
    monkeypatch.setattr(settings, "hooks_enabled", False)


class TestConfigAcceptsTailEvents:
    def test_four_tail_events_parse(self, tmp_path):
        hooks_json = tmp_path / ".mini-claude" / "hooks.json"
        hooks_json.parent.mkdir(parents=True)
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [{"hooks": [{"type": "command", "command": "echo ss"}]}],
                        "SessionEnd": [{"hooks": [{"type": "command", "command": "echo se"}]}],
                        "PreCompact": [{"hooks": [{"type": "command", "command": "echo pc"}]}],
                        "SubagentStart": [{"hooks": [{"type": "command", "command": "echo sa"}]}],
                    }
                }
            ),
            encoding="utf-8",
        )
        config, warnings = load_hooks_config(workspace_root=tmp_path)
        assert not warnings, f"尾部事件不应产生 warning：{warnings}"
        for ev in ("SessionStart", "SessionEnd", "PreCompact", "SubagentStart"):
            assert ev in config.entries, f"{ev} 应被接受"

    def test_valid_events_cover_ten(self):
        from mini_claude.hooks.config import VALID_EVENTS

        for ev in ("SessionStart", "SessionEnd", "PreCompact", "SubagentStart"):
            assert ev in VALID_EVENTS


class TestSessionStart:
    @pytest.mark.asyncio
    async def test_stdout_becomes_session_context(self, hooks_on):
        run, _ = _runner(
            [
                SimpleNamespace(
                    exit_code=0, stdout="项目当前在 v2 分支\n", stderr="", timed_out=False
                )
            ]
        )
        d = HookDispatcher(_cfg("SessionStart"), runner=run)
        blocked, reason, context = await d.dispatch_session_start("startup", thread_id="t")
        assert blocked is False and reason == ""
        assert "v2 分支" in context

    @pytest.mark.asyncio
    async def test_json_additional_context(self, hooks_on):
        out = SimpleNamespace(
            exit_code=0,
            stdout=json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "今天先跑回归",
                    }
                }
            ),
            stderr="",
            timed_out=False,
        )
        run, calls = _runner([out])
        d = HookDispatcher(_cfg("SessionStart"), runner=run)
        _, _, context = await d.dispatch_session_start("startup", thread_id="t")
        assert "今天先跑回归" in context
        assert calls[0]["source"] == "startup"
        assert calls[0]["thread_id"] == "t"

    @pytest.mark.asyncio
    async def test_exit2_does_not_block_session(self, hooks_on):
        run, _ = _runner(
            [SimpleNamespace(exit_code=2, stdout="", stderr="启动检查失败", timed_out=False)]
        )
        d = HookDispatcher(_cfg("SessionStart"), runner=run)
        blocked, reason, context = await d.dispatch_session_start("startup", thread_id="t")
        assert blocked is False and context == ""

    @pytest.mark.asyncio
    async def test_disabled_skips_runner(self, hooks_off):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("SessionStart"), runner=run)
        blocked, _, context = await d.dispatch_session_start("startup", thread_id="t")
        assert blocked is False and context == "" and calls == []


class TestFireOnlyEvents:
    """SessionEnd / PreCompact / SubagentStart：只触发不判断，payload 完整。"""

    @pytest.mark.asyncio
    async def test_session_end_payload(self, hooks_on):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("SessionEnd"), runner=run)
        await d.dispatch_session_end("exit", thread_id="t")
        assert calls[0]["reason"] == "exit"
        assert calls[0]["thread_id"] == "t"

    @pytest.mark.asyncio
    async def test_pre_compact_payload(self, hooks_on):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("PreCompact"), runner=run)
        await d.dispatch_pre_compact("manual", custom_instructions="保留决策", thread_id="t")
        assert calls[0]["trigger"] == "manual"
        assert calls[0]["custom_instructions"] == "保留决策"

    @pytest.mark.asyncio
    async def test_subagent_start_payload(self, hooks_on):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("SubagentStart"), runner=run)
        await d.dispatch_subagent_start("a1", "写模块", thread_id="t")
        assert calls[0]["agent_id"] == "a1"
        assert calls[0]["agent_task"] == "写模块"

    @pytest.mark.asyncio
    async def test_all_disabled_skips_runner(self, hooks_off):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("SessionEnd", "PreCompact", "SubagentStart"), runner=run)
        await d.dispatch_session_end("exit", thread_id="t")
        await d.dispatch_pre_compact("auto", thread_id="t")
        await d.dispatch_subagent_start("a1", "任务", thread_id="t")
        assert calls == []

    @pytest.mark.asyncio
    async def test_runner_exception_swallowed(self, hooks_on):
        async def boom(command, payload, timeout=None, cwd=None):
            raise RuntimeError("hook 进程崩了")

        d = HookDispatcher(_cfg("SessionEnd", "PreCompact", "SubagentStart"), runner=boom)
        # 只触发不判断：异常吞掉、不外抛
        await d.dispatch_session_end("exit", thread_id="t")
        await d.dispatch_pre_compact("auto", thread_id="t")
        await d.dispatch_subagent_start("a1", "任务", thread_id="t")


class TestPreCompactAutoTrigger:
    """act 自动摘要压缩前触发 PreCompact（trigger=auto）。"""

    @pytest.mark.asyncio
    async def test_handle_token_budget_fires_pre_compact(self, hooks_on, monkeypatch):
        from mini_claude.agent.nodes._act_helpers import handle_token_budget
        from mini_claude.utils.token_manager import TokenCounter, TokenLimitStrategy

        calls = []

        class _FakeDispatcher:
            async def dispatch_pre_compact(self, trigger, custom_instructions="", thread_id=""):
                calls.append({"trigger": trigger, "thread_id": thread_id})

        import mini_claude.hooks.dispatcher as dispatcher_mod

        monkeypatch.setattr(dispatcher_mod, "get_hook_dispatcher", lambda: _FakeDispatcher())

        # 摘要 LLM 可控：_act_helpers 模块级引用 _shared.llm_provider 实例，patch 实例方法
        from mini_claude.agent.nodes import _shared

        msg = SimpleNamespace(content="摘要", tool_calls=None)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

        async def fake_chat(*a, **k):
            return response

        monkeypatch.setattr(_shared.llm_provider, "chat", fake_chat)

        counter = TokenCounter(model="deepseek-chat", strategy=TokenLimitStrategy.SUMMARIZE)
        counter.token_budget = 10  # 强制超预算
        counter.warn_threshold = 5

        messages = [SimpleNamespace(content=f"历史消息 {i}", type="ai") for i in range(6)]
        litellm_messages = [{"role": "assistant", "content": f"历史消息 {i}"} for i in range(6)]

        _, summarized = await handle_token_budget(
            messages, litellm_messages, counter, thread_id="t-auto"
        )
        assert calls, "超预算摘要压缩前应触发 PreCompact"
        assert calls[0]["trigger"] == "auto"
        assert calls[0]["thread_id"] == "t-auto"
