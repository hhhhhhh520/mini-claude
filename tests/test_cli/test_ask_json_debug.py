"""ISSUE-017（ask --json / --debug 死参数）+ ISSUE-018（ask 不清理后台进程）
+ ISSUE-020（回显未转义 / except 丢 traceback，三张联动）。

ask 是唯一同时动这三处的函数，一起修、一起测。
"""
import json
import os
import subprocess
import sys
from unittest.mock import patch

from click.testing import CliRunner

from mini_claude.cli import main as main_mod
from mini_claude.cli.display import display
from mini_claude.cli.main import main
from mini_claude.tools import bash as bash_mod


def _fake_response(content: str):
    message = type("Msg", (), {"content": content, "tool_calls": None})()
    return type("Resp", (), {"choices": [type("Choice", (), {"message": message})()]})()


class _OkProvider:
    def __init__(self, *a, **k):
        pass

    async def chat(self, *a, **k):
        return _fake_response("ok")


class _FailingProvider:
    def __init__(self, *a, **k):
        pass

    async def chat(self, *a, **k):
        raise RuntimeError("Insufficient Balance")


def _invoke_ask(*args: str, provider_cls=_OkProvider):
    with (
        patch("mini_claude.cli.main.init_logging"),
        patch("mini_claude.cli.main.load_environment"),
        patch("mini_claude.llm.provider.LLMProvider", provider_cls),
    ):
        return CliRunner().invoke(main, ["ask", *args])


class TestAskJson:
    """--json 不再是死参数：只输出最终 JSON 一行。"""

    def test_json_success_outputs_single_parseable_line(self):
        result = _invoke_ask("--json", "说 ok")

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["answer"] == "ok", payload
        assert "Error" not in result.output, result.output

    def test_json_error_is_structured(self):
        result = _invoke_ask("--json", "说 ok", provider_cls=_FailingProvider)

        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert "Insufficient Balance" in payload["error"], payload

    def test_plain_output_unchanged(self):
        """守卫：默认输出不受影响。"""
        result = _invoke_ask("说 ok")

        assert result.exit_code == 0, result.output
        assert "ok" in result.output


_JSON_OK_STUB = '''\
from unittest.mock import patch

from mini_claude.cli.main import main


class _Provider:
    def __init__(self, *a, **k):
        pass

    async def chat(self, *a, **k):
        message = type("Msg", (), {"content": "ok", "tool_calls": None})()
        return type("Resp", (), {"choices": [type("C", (), {"message": message})()]})()


with patch("mini_claude.cli.main.init_logging"), patch(
    "mini_claude.cli.main.load_environment"
), patch("mini_claude.llm.provider.LLMProvider", _Provider):
    main(["ask", "--json", "hi"])
'''

_ENV_ALLOWLIST = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)


class TestAskJsonInRealProcess:
    """进程级复核：--json 的退出码与单行 JSON 在真实终端成立。"""

    def test_real_process_json_success(self, tmp_path):
        script = tmp_path / "run_ask_json.py"
        script.write_text(_JSON_OK_STUB, encoding="utf-8")
        env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
        )

        assert proc.returncode == 0, proc.stderr[-800:]
        payload = json.loads(proc.stdout)
        assert payload["answer"] == "ok", payload


class TestDebugFlag:
    """--debug 不再是死参数：提日志级别 + 终端打堆栈。"""

    def test_debug_sets_log_level(self, monkeypatch):
        from mini_claude.config.settings import settings

        monkeypatch.setattr(settings, "log_level", "INFO")
        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch("mini_claude.llm.provider.LLMProvider", _OkProvider),
        ):
            result = CliRunner().invoke(main, ["--debug", "ask", "说 ok"])

        assert result.exit_code == 0, result.output
        assert settings.log_level == "DEBUG", "--debug 必须把日志级别提到 DEBUG"

    def test_debug_prints_traceback_on_failure(self):
        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch("mini_claude.llm.provider.LLMProvider", _FailingProvider),
        ):
            result = CliRunner().invoke(main, ["--debug", "ask", "说 ok"])

        assert result.exit_code == 1, result.output
        assert "Traceback" in result.output, (
            f"--debug 下终端必须有堆栈:\n{result.output[-800:]}"
        )

    def test_no_debug_no_traceback(self):
        """守卫：默认不打堆栈（只记日志），终端保持干净。"""
        result = _invoke_ask("说 ok", provider_cls=_FailingProvider)

        assert result.exit_code == 1, result.output
        assert "Traceback" not in result.output, result.output


class TestDisplayEscape:
    """ISSUE-020 问题一：外部文本进 rich 必须 escape。"""

    def test_user_message_escapes_markup(self, capsys):
        display.user_message("[red]hi[/]")
        out = capsys.readouterr().out

        assert "[red]" in out, f"markup 被 rich 吃掉即输出伪造，实测输出: {out!r}"

    def test_show_error_escapes_markup(self, capsys):
        display.show_error("[green]fake-ok[/]")
        out = capsys.readouterr().out

        assert "[green]" in out, f"markup 被 rich 吃掉即输出伪造，实测输出: {out!r}"


class TestAskCleansBackgroundProcesses:
    """ISSUE-018：ask 退出前必须走清理（与 repl 同构）。

    登记一个活进程（count>0 即触发 finally）；cleanup 本体是既有代码
    （repl 在用，本单未动），这里只判别"ask 退出的 finally 调了它"。
    """

    def test_ask_invokes_cleanup_when_processes_tracked(self):
        called = []

        async def _fake_cleanup():
            called.append(1)

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"]
        )
        bash_mod._background_processes["task_test_018"] = proc
        try:
            with patch.object(
                bash_mod, "cleanup_all_background_processes", _fake_cleanup
            ), patch.object(bash_mod, "get_background_process_count", return_value=1):
                result = _invoke_ask("说 ok")

            assert result.exit_code == 0, result.output
            assert called == [1], "ask 退出时必须调用后台清理（repl 有，ask 缺）"
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            bash_mod._background_processes.pop("task_test_018", None)
