"""ISSUE-015：`mini-claude ask` 在 LLM 失败时必须以非 0 退出码结束。

退出码是脚本与 CI 判断成败的唯一依据。`display.show_error` 只打印、不改变退出码，
所以这里断言的是**退出码本身**，而不是输出文本——只看文本的话，修复前的实现
（打印错误 + 退出码 0）也会「通过」。
"""

import os
import subprocess
import sys
from unittest.mock import patch

from click.testing import CliRunner

from mini_claude.cli.main import main


def _fake_response(content: str):
    """构造一个 litellm 风格的最小响应对象。"""
    message = type("Msg", (), {"content": content, "tool_calls": None})()
    return type("Resp", (), {"choices": [type("Choice", (), {"message": message})()]})()


class _FailingProvider:
    """构造正常、chat 抛异常的 LLM stub（模拟 key 欠费 / 网络错误 / 超时）。"""

    def __init__(self, *args, **kwargs):
        pass

    async def chat(self, *args, **kwargs):
        raise RuntimeError("Insufficient Balance")


class _OkProvider:
    """chat 正常返回的 LLM stub。"""

    def __init__(self, *args, **kwargs):
        pass

    async def chat(self, *args, **kwargs):
        return _fake_response("ok")


def _invoke_ask(provider_cls):
    """进程内调用 ask，隔离掉与退出码无关的全局副作用。

    `init_logging()` 会重配 root logger，使后续用例的 caplog 收不到日志；
    `load_dotenv()` 会把 .env 写进 os.environ。二者都与「退出码」无关，
    真实路径（含这两个副作用）由下面的子进程用例覆盖。

    注入方式：patch cli.main 的 LLM 构造缝 `_build_ask_llm`——不全局替换
    LLMProvider 类，类替换会波及补丁窗口内的一切构造点（2026-10-02
    导入期单例事故的根源，2026-10-03 改依赖注入）。
    """
    with (
        patch("mini_claude.cli.main.init_logging"),
        patch("mini_claude.cli.main.load_environment"),
        patch("mini_claude.cli.main._build_ask_llm", lambda model=None: provider_cls()),
    ):
        return CliRunner().invoke(main, ["ask", "说 ok"])


class TestAskExitCode:
    """ask 的退出码必须反映 LLM 调用的成败。"""

    def test_ask_exits_nonzero_when_llm_call_raises(self):
        """判别性用例：except 分支若不把失败传播出去，本用例转红。"""
        result = _invoke_ask(_FailingProvider)

        assert result.exit_code != 0, (
            f"ask exited with code {result.exit_code} after an LLM failure; "
            f"scripts/CI would read that as success.\noutput: {result.output}"
        )

    def test_ask_reports_error_message_before_exiting(self):
        """守卫：改退出码时不能顺手吞掉错误提示。"""
        result = _invoke_ask(_FailingProvider)

        assert "Insufficient Balance" in result.output

    def test_ask_exits_zero_when_llm_succeeds(self):
        """守卫：正常路径仍必须是退出码 0。

        额外断言"无 Error"——只断言退出码 0 的话，被 except 吞掉的异常同样满足，
        这条守卫会变成假绿（编写时确实踩过一次）。
        """
        result = _invoke_ask(_OkProvider)

        assert "Error" not in result.output, result.output
        assert result.exit_code == 0, result.output


_PROCESS_STUB = """
import mini_claude.cli.main as _cli

{provider}

# 经依赖注入缝替换 LLM 构造（不全局替换 LLMProvider 类）
_cli._build_ask_llm = lambda model=None: _Provider()

_cli.main(["ask", "hi"])
"""

_FAILING_PROVIDER_SNIPPET = """
class _Provider:
    def __init__(self, *a, **k):
        pass

    async def chat(self, *a, **k):
        raise RuntimeError("Insufficient Balance")
"""

_OK_PROVIDER_SNIPPET = """
class _Provider:
    def __init__(self, *a, **k):
        pass

    async def chat(self, *a, **k):
        msg = type("M", (), {"content": "ok", "tool_calls": None})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
"""


_ENV_ALLOWLIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


class TestAskExitCodeInRealProcess:
    """进程级复核：CliRunner 跑在进程内，真实退出码必须由子进程说话。"""

    def _run_stub(self, tmp_path, snippet: str, filename: str):
        script = tmp_path / filename
        script.write_text(
            _PROCESS_STUB.format(provider=snippet.strip()),
            encoding="utf-8",
        )

        # 只透传运行解释器所需的最小环境：黑名单式剥离（"去掉 ANTHROPIC_*"）
        # 会把父进程的 API key、代理变量等一并带进子进程。
        env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"

        # cwd 用 tmp_path 而非项目根：init_logging() 往相对路径 logs/ 写日志，
        # 而 logs/mini_claude.log 是 git 跟踪文件——在项目根跑会脏工作区。
        # 注意 cwd 并不影响 .env 加载：load_dotenv() 走 find_dotenv(usecwd=False)，
        # 是从调用方文件（cli/main.py）向上查找，项目的 .env 照样会被读入。
        return subprocess.run(
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
        )

    def test_real_process_exits_nonzero_on_llm_failure(self, tmp_path):
        proc = self._run_stub(tmp_path, _FAILING_PROVIDER_SNIPPET, "run_ask_fail.py")

        assert proc.returncode != 0, (
            f"real process exited with code {proc.returncode} (expected non-zero)\n"
            f"stdout={proc.stdout[-500:]}\nstderr={proc.stderr[-800:]}"
        )

    def test_real_process_exits_zero_on_success(self, tmp_path):
        """守卫：同时验证子进程装置本身有判别力（成功时确实是 0 且无 Error）。"""
        proc = self._run_stub(tmp_path, _OK_PROVIDER_SNIPPET, "run_ask_ok.py")

        assert "Error" not in proc.stdout, (
            f"success path still reported an error:\n{proc.stdout[-800:]}"
        )
        assert proc.returncode == 0, (
            f"real process exited with code {proc.returncode} (expected 0)\n"
            f"stdout={proc.stdout[-500:]}\nstderr={proc.stderr[-800:]}"
        )
