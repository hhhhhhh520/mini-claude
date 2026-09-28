"""HookDispatcher 事件分发测试（P3-1）

用注入的 fake runner 测分发语义（真子进程在 test_runner.py）：
- PreToolUse：exit 2 / JSON decision=block → 阻断；exit 0 放行；其他非零不阻断
- PostToolUse：JSON replacement → 替换输出；exit 2 不阻断
- Stop：只触发不判断
- matcher 正则匹配 tool 名；超时视为非阻断错误
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mini_claude.hooks.config import HookCommand, HookConfig, HookRule
from mini_claude.hooks.dispatcher import HookDispatcher


def _rule(matcher, command, timeout=30):
    return HookRule(matcher=matcher, hooks=[HookCommand(command=command, timeout=timeout)])


def _make_dispatcher(entries=None, runner=None):
    config = HookConfig(entries=entries or {})
    return HookDispatcher(
        config,
        runner=runner
        or AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)
        ),
    )


class TestPreToolUse:
    @pytest.mark.asyncio
    async def test_exit_zero_continues(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "ok")]}, runner)
        assert (await d.dispatch_pre_tool_use("read_file", {})).blocked is None
        runner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exit_two_blocks_with_stderr_reason(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=2, stdout="", stderr="policy says no", timed_out=False
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        verdict = await d.dispatch_pre_tool_use("run_command", {"command": "rm"})
        assert verdict.blocked is not None and "policy says no" in verdict.blocked

    @pytest.mark.asyncio
    async def test_json_decision_block(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=0,
                stdout=json.dumps({"decision": "block", "reason": "json block"}),
                stderr="",
                timed_out=False,
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        verdict = await d.dispatch_pre_tool_use("run_command", {})
        assert verdict.blocked is not None and "json block" in verdict.blocked

    @pytest.mark.asyncio
    async def test_other_nonzero_exit_does_not_block(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=3, stdout="", stderr="oops", timed_out=False)
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        assert (await d.dispatch_pre_tool_use("read_file", {})).blocked is None

    @pytest.mark.asyncio
    async def test_timeout_does_not_block(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=True)
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "slow")]}, runner)
        assert (await d.dispatch_pre_tool_use("read_file", {})).blocked is None

    @pytest.mark.asyncio
    async def test_matcher_regex_selects_tools(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=2, stdout="", stderr="no writes", timed_out=False
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("write_file|edit_file", "x")]}, runner)
        # matcher 命中 → 阻断
        assert (await d.dispatch_pre_tool_use("write_file", {"path": "a"})).blocked is not None
        # matcher 未命中 → 完全不执行 hook
        assert (await d.dispatch_pre_tool_use("read_file", {})).blocked is None
        assert runner.await_count == 1

    @pytest.mark.asyncio
    async def test_no_matching_hooks_returns_none(self):
        d = _make_dispatcher({})
        assert (await d.dispatch_pre_tool_use("read_file", {})).blocked is None


class TestPreToolUseVerdict:
    """收敛批次①：结构化裁决（permissionDecision 三态 + updatedInput + payload 增强）"""

    @pytest.mark.asyncio
    async def test_permission_decision_allow(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "allow",
                        }
                    }
                ),
                stderr="",
                timed_out=False,
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        v = await d.dispatch_pre_tool_use("run_command", {})
        assert v.blocked is None and v.allow is True

    @pytest.mark.asyncio
    async def test_permission_decision_deny_blocks_with_reason(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": "高危命令",
                        }
                    }
                ),
                stderr="",
                timed_out=False,
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        v = await d.dispatch_pre_tool_use("run_command", {})
        assert v.blocked is not None and "高危命令" in v.blocked and v.allow is False

    @pytest.mark.asyncio
    async def test_updated_input_from_hook_specific_output(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "updatedInput": {"command": "git status"},
                        }
                    }
                ),
                stderr="",
                timed_out=False,
            )
        )
        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        v = await d.dispatch_pre_tool_use("run_command", {"command": "rm -rf"})
        assert v.updated_input == {"command": "git status"}

    @pytest.mark.asyncio
    async def test_payload_enrichment(self):
        """payload 补齐本体字段：session_id/permission_mode/cwd"""
        calls = []

        async def runner(command, payload, timeout=None, cwd=None):
            calls.append(payload)
            return SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)

        d = HookDispatcher(
            HookConfig(entries={"PreToolUse": [_rule("", "x")]}),
            runner=runner,
            cwd="D:\proj",
        )
        await d.dispatch_pre_tool_use("run_command", {}, thread_id="t1")
        assert calls[0]["session_id"] == "t1"
        assert calls[0]["cwd"] == "D:\proj"
        assert "permission_mode" in calls[0]


class TestPostToolUse:
    @pytest.mark.asyncio
    async def test_replacement_rewrites_output(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(
                exit_code=0,
                stdout=json.dumps({"replacement": "cleared by hook"}),
                stderr="",
                timed_out=False,
            )
        )
        d = _make_dispatcher({"PostToolUse": [_rule("", "x")]}, runner)
        result = await d.dispatch_post_tool_use("read_file", {}, "secret content")
        assert result == "cleared by hook"

    @pytest.mark.asyncio
    async def test_no_replacement_keeps_original(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)
        )
        d = _make_dispatcher({"PostToolUse": [_rule("", "x")]}, runner)
        assert await d.dispatch_post_tool_use("read_file", {}, "original") is None

    @pytest.mark.asyncio
    async def test_post_exit_two_does_not_block(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=2, stdout="", stderr="late", timed_out=False)
        )
        d = _make_dispatcher({"PostToolUse": [_rule("", "x")]}, runner)
        assert await d.dispatch_post_tool_use("read_file", {}, "original") is None


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_fires_and_ignores_errors(self):
        runner = AsyncMock(
            return_value=SimpleNamespace(exit_code=1, stdout="", stderr="", timed_out=False)
        )
        d = _make_dispatcher({"Stop": [_rule("", "x")]}, runner)
        await d.dispatch_stop("task_complete", "done")  # 不抛异常即通过
        runner.assert_awaited_once()


class TestPayload:
    @pytest.mark.asyncio
    async def test_payload_contains_event_and_tool(self):
        captured = {}

        async def runner(command, payload, timeout, cwd):
            captured.update(payload)
            return SimpleNamespace(exit_code=0, stdout="", stderr="", timed_out=False)

        d = _make_dispatcher({"PreToolUse": [_rule("", "x")]}, runner)
        await d.dispatch_pre_tool_use("run_command", {"command": "ls"}, thread_id="t1")
        assert captured["event"] == "PreToolUse"
        assert captured["tool_name"] == "run_command"
        assert captured["tool_input"] == {"command": "ls"}
        assert captured["thread_id"] == "t1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
