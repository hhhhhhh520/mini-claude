"""新 hooks 事件测试：UserPromptSubmit / Notification / SubagentStop。

对齐 Claude Code 的事件面（本体共 6+ 事件，本仓库原有 3 个）：
- UserPromptSubmit：exit 2 / decision=block 阻断该输入；exit 0 纯 stdout 或
  hookSpecificOutput.additionalContext 注入回合上下文
- Notification：只触发不判断（确认请求等需用户注意的时刻）
- SubagentStop：exit 2 / decision=block 阻断子代理收工（原因喂回继续）
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


class TestConfigAcceptsNewEvents:
    def test_three_new_events_parse(self, tmp_path):
        hooks_json = tmp_path / ".mini-claude" / "hooks.json"
        hooks_json.parent.mkdir(parents=True)
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {"hooks": [{"type": "command", "command": "echo up"}]}
                        ],
                        "Notification": [{"hooks": [{"type": "command", "command": "echo nt"}]}],
                        "SubagentStop": [{"hooks": [{"type": "command", "command": "echo ss"}]}],
                    }
                }
            ),
            encoding="utf-8",
        )
        config, warnings = load_hooks_config(workspace_root=tmp_path)
        assert not warnings, f"新事件不应产生 warning：{warnings}"
        for ev in ("UserPromptSubmit", "Notification", "SubagentStop"):
            assert ev in config.entries, f"{ev} 应被接受"


class TestUserPromptSubmit:
    @pytest.mark.asyncio
    async def test_exit0_stdout_becomes_context(self, hooks_on):
        run, _ = _runner(
            [SimpleNamespace(exit_code=0, stdout="注入的上下文\n", stderr="", timed_out=False)]
        )
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        blocked, reason, context = await d.dispatch_user_prompt_submit(
            "帮我写个脚本", thread_id="t"
        )
        assert blocked is False and reason == ""
        assert "注入的上下文" in context

    @pytest.mark.asyncio
    async def test_exit2_blocks_prompt(self, hooks_on):
        run, _ = _runner(
            [SimpleNamespace(exit_code=2, stdout="", stderr="该提示词违反政策\n", timed_out=False)]
        )
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        blocked, reason, context = await d.dispatch_user_prompt_submit("bad prompt", thread_id="t")
        assert blocked is True
        assert "该提示词违反政策" in reason
        assert context == ""

    @pytest.mark.asyncio
    async def test_json_decision_block(self, hooks_on):
        out = SimpleNamespace(
            exit_code=0,
            stdout=json.dumps({"decision": "block", "reason": "不允许问这个"}),
            stderr="",
            timed_out=False,
        )
        run, _ = _runner([out])
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        blocked, reason, _ = await d.dispatch_user_prompt_submit("x", thread_id="t")
        assert blocked is True and "不允许问这个" in reason

    @pytest.mark.asyncio
    async def test_json_additional_context(self, hooks_on):
        out = SimpleNamespace(
            exit_code=0,
            stdout=json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": "项目用 pnpm",
                    }
                }
            ),
            stderr="",
            timed_out=False,
        )
        run, _ = _runner([out])
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        _, _, context = await d.dispatch_user_prompt_submit("x", thread_id="t")
        assert "项目用 pnpm" in context

    @pytest.mark.asyncio
    async def test_nonblocking_error_ignored(self, hooks_on):
        run, calls = _runner(
            [SimpleNamespace(exit_code=1, stdout="部分输出", stderr="oops", timed_out=False)]
        )
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        blocked, reason, context = await d.dispatch_user_prompt_submit("x", thread_id="t")
        assert blocked is False and context == "" and len(calls) == 1

    @pytest.mark.asyncio
    async def test_payload_contains_prompt(self, hooks_on):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("UserPromptSubmit"), runner=run)
        await d.dispatch_user_prompt_submit("我的问题", thread_id="tid-1")
        assert calls[0]["event"] == "UserPromptSubmit"
        assert calls[0]["prompt"] == "我的问题"
        assert calls[0]["thread_id"] == "tid-1"


class TestNotification:
    @pytest.mark.asyncio
    async def test_fires_with_message(self, hooks_on):
        run, calls = _runner([])
        d = HookDispatcher(_cfg("Notification"), runner=run)
        await d.dispatch_notification("工具 write_file 请求确认", thread_id="t")
        assert len(calls) == 1
        assert calls[0]["event"] == "Notification"
        assert "write_file" in calls[0]["message"]

    @pytest.mark.asyncio
    async def test_runner_exception_swallowed(self, hooks_on):
        async def boom(command, payload, timeout=None, cwd=None):
            raise RuntimeError("runner down")

        d = HookDispatcher(_cfg("Notification"), runner=boom)
        await d.dispatch_notification("msg", thread_id="t")  # 不应抛出


class TestSubagentStop:
    @pytest.mark.asyncio
    async def test_exit2_blocks_completion(self, hooks_on):
        run, calls = _runner(
            [SimpleNamespace(exit_code=2, stdout="", stderr="还要补测试\n", timed_out=False)]
        )
        d = HookDispatcher(_cfg("SubagentStop"), runner=run)
        blocked, reason = await d.dispatch_subagent_stop(
            agent_id="a1", agent_task="写模块", result_summary="done", thread_id="t"
        )
        assert blocked is True and "还要补测试" in reason
        assert calls[0]["agent_id"] == "a1"
        assert calls[0]["agent_task"] == "写模块"

    @pytest.mark.asyncio
    async def test_exit0_allows_completion(self, hooks_on):
        run, _ = _runner([SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)])
        d = HookDispatcher(_cfg("SubagentStop"), runner=run)
        blocked, reason = await d.dispatch_subagent_stop("a1", "写模块", "done", "t")
        assert blocked is False and reason == ""

    @pytest.mark.asyncio
    async def test_json_decision_block(self, hooks_on):
        out = SimpleNamespace(
            exit_code=0,
            stdout=json.dumps({"decision": "block", "reason": "结果不完整"}),
            stderr="",
            timed_out=False,
        )
        run, _ = _runner([out])
        d = HookDispatcher(_cfg("SubagentStop"), runner=run)
        blocked, reason = await d.dispatch_subagent_stop("a1", "写模块", "done", "t")
        assert blocked is True and "结果不完整" in reason
