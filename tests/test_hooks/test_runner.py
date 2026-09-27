"""hook 命令执行器测试（P3-1）

真子进程跑临时脚本：stdin 收 JSON payload，stdout/stderr/exit code 回传。
超时强杀、shell 引号、Windows 编码都靠这条兜底。
"""

import sys

import pytest

from mini_claude.hooks.runner import HookOutcome, run_hook_command


def _script(tmp_path, body):
    p = tmp_path / f"h_{abs(hash(body))}.py"
    p.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{p}"'


PAYLOAD = {"event": "PreToolUse", "tool_name": "run_command", "tool_input": {"command": "ls"}}


class TestRunHookCommand:
    @pytest.mark.asyncio
    async def test_exit_zero_and_stdin_payload(self, tmp_path):
        """payload 经 stdin 传入，脚本可读；exit 0"""
        cmd = _script(
            tmp_path,
            "import json,sys\n"
            "d = json.load(sys.stdin)\n"
            "assert d['tool_name'] == 'run_command'\n"
            "print('seen', d['tool_input']['command'])\n",
        )
        outcome = await run_hook_command(cmd, PAYLOAD, timeout=30, cwd=str(tmp_path))
        assert isinstance(outcome, HookOutcome)
        assert outcome.exit_code == 0
        assert "seen ls" in outcome.stdout
        assert not outcome.timed_out

    @pytest.mark.asyncio
    async def test_exit_two_with_stderr(self, tmp_path):
        cmd = _script(
            tmp_path,
            "import sys\nsys.stderr.write('blocked by policy')\nsys.exit(2)\n",
        )
        outcome = await run_hook_command(cmd, PAYLOAD, timeout=30, cwd=str(tmp_path))
        assert outcome.exit_code == 2
        assert "blocked by policy" in outcome.stderr

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, tmp_path):
        cmd = _script(tmp_path, "import time\ntime.sleep(30)\n")
        outcome = await run_hook_command(cmd, PAYLOAD, timeout=1, cwd=str(tmp_path))
        assert outcome.timed_out is True

    @pytest.mark.asyncio
    async def test_nonzero_exit_is_error_not_crash(self, tmp_path):
        cmd = _script(tmp_path, "import sys\nsys.exit(3)\n")
        outcome = await run_hook_command(cmd, PAYLOAD, timeout=30, cwd=str(tmp_path))
        assert outcome.exit_code == 3

    @pytest.mark.asyncio
    async def test_missing_command_returns_error_outcome(self, tmp_path):
        outcome = await run_hook_command(
            f'"{sys.executable}" "{tmp_path / "nope.py"}"', PAYLOAD, timeout=30, cwd=str(tmp_path)
        )
        # 找不到命令/脚本不算崩，返回非零 outcome 由 dispatcher 决策
        assert outcome.exit_code != 0

    @pytest.mark.asyncio
    async def test_utf8_output_on_windows(self, tmp_path):
        cmd = _script(
            tmp_path,
            "import sys\nsys.stdout.write('中文输出OK')\n",
        )
        outcome = await run_hook_command(cmd, PAYLOAD, timeout=30, cwd=str(tmp_path))
        assert "中文输出OK" in outcome.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
