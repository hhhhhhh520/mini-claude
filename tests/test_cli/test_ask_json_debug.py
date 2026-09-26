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


_JSON_OK_STUB = """\
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
        assert "Traceback" in result.output, f"--debug 下终端必须有堆栈:\n{result.output[-800:]}"

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

    def test_error_hint_escapes_markup(self, capsys):
        """hint 目前恒为常量，但注入面不该留给未来的分类器改动。

        模拟分类器返回带 markup 的文本，断言原样输出而非被 rich 渲染。
        """
        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch("mini_claude.llm.provider.LLMProvider", _FailingProvider),
            patch(
                "mini_claude.monitoring.health.classify_model_error",
                return_value="[green]fake-hint[/]",
            ),
        ):
            result = CliRunner().invoke(main, ["ask", "坏 key"])

        assert result.exit_code == 1, result.output
        assert "[green]fake-hint[/]" in result.output, (
            f"hint 未 escape，rich markup 被渲染即输出伪造，实测: {result.output!r}"
        )


class TestAskCleansBackgroundProcesses:
    """ISSUE-018：ask 退出前必须走清理（与 repl 同构）.

    登记一个活进程（count>0 即触发 finally）；cleanup 本体是既有代码
    （repl 在用，本单未动），这里只判别"ask 退出的 finally 调了它"。
    """

    def test_ask_invokes_cleanup_when_processes_tracked(self):
        called = []

        async def _fake_cleanup():
            called.append(1)

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        bash_mod._background_processes["task_test_018"] = proc
        try:
            with (
                patch.object(bash_mod, "cleanup_all_background_processes", _fake_cleanup),
                patch.object(bash_mod, "get_background_process_count", return_value=1),
            ):
                result = _invoke_ask("说 ok")

            assert result.exit_code == 0, result.output
            assert called == [1], "ask 退出时必须调用后台清理（repl 有，ask 缺）"
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            bash_mod._background_processes.pop("task_test_018", None)


class TestThirdPartyStdoutSuppression:
    """P0-3：litellm 广告不许污染 --json 的 stdout（真实子进程断终端）."""

    def test_suppress_flag_and_env(self):
        import os
        from mini_claude.cli.main import _suppress_third_party_stdout_noise

        _suppress_third_party_stdout_noise()
        assert os.environ.get("LITELLM_LOG") == "ERROR"
        try:
            import litellm

            assert litellm.suppress_debug_info is True
        except ImportError:
            pass

    def test_health_json_stdout_is_pure(self, tmp_path):
        # 与 TestAskJsonInRealProcess 同构：最小 env 白名单（挡项目 .env 与真 key）。
        # 网关指向必然拒绝连接的本地端口，模型检查毫秒级失败——
        # 保留真实子进程 + 真实 litellm 的 stdout 行为，但不发真请求、不花 token。
        env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"
        env["OPENAI_BASE_URL"] = "http://127.0.0.1:9/v1"
        env["OPENAI_API_KEY"] = "sk-not-a-real-key"
        env["DEFAULT_MODEL"] = "qwen3.8-flash"

        proc = subprocess.run(
            [sys.executable, "-m", "mini_claude.cli.main", "health", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=tmp_path,
            env=env,
            timeout=120,
        )
        assert "Give Feedback" not in proc.stdout
        assert "LiteLLM.Info" not in proc.stdout
        data = json.loads(proc.stdout)
        assert "overall_status" in data


class TestAskFullAndHint:
    """P1-6 ask --full 走主图 + P1-7 失败带中文 hint（mock，不花钱）."""

    def test_full_uses_graph(self):

        from langchain_core.messages import AIMessage

        class _FakeGraph:
            async def ainvoke(self, state, config=None):
                assert state["current_task"] == "做 full"
                return {"messages": [AIMessage(content="full-ok")]}

        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch(
                "mini_claude.agent.graph.build_agent_graph_no_checkpoint",
                return_value=_FakeGraph(),
            ),
        ):
            result = CliRunner().invoke(main, ["ask", "做 full", "--full"])
        assert result.exit_code == 0, result.output
        assert "full-ok" in result.output

    def test_error_payload_has_hint(self):
        result = _invoke_ask("坏 key", provider_cls=_FailingProvider)
        # 非 json 路径：原文 + 中文下一步都要有
        assert result.exit_code == 1, result.output
        assert "Insufficient Balance" in result.output
        assert "欠费" in result.output

    def test_error_json_has_hint_key(self):
        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch("mini_claude.llm.provider.LLMProvider", _FailingProvider),
        ):
            result = CliRunner().invoke(main, ["ask", "坏 key", "--json"])
        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert "Insufficient Balance" in payload["error"]
        assert "欠费" in payload.get("hint", "")

    def test_full_json_stdout_ignores_node_noise(self):
        """图节点里的 display 输出不许污染 --full --json 的 stdout."""
        from langchain_core.messages import AIMessage

        class _NoisyGraph:
            async def ainvoke(self, state, config=None):
                print("[tool] read_file(noise)")
                return {"messages": [AIMessage(content="full-ok")]}

        with (
            patch("mini_claude.cli.main.init_logging"),
            patch("mini_claude.cli.main.load_environment"),
            patch(
                "mini_claude.agent.graph.build_agent_graph_no_checkpoint",
                return_value=_NoisyGraph(),
            ),
        ):
            # 真实子进程里 stdout/stderr 是分开的，这里同样分流断 stdout。
            # click 8.2 移除了 mix_stderr（恒分流），老版本需显式传 False。
            try:
                runner = CliRunner(mix_stderr=False)
            except TypeError:
                runner = CliRunner()
            result = runner.invoke(main, ["ask", "读文件", "--full", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload == {"answer": "full-ok"}
