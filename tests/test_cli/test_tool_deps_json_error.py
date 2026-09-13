"""ISSUE-021：`tool-deps --json <不存在的工具>` 未捕获 ValueError。

无 --json 路径有存在性检查（友好报错 + exit 1）；--json 分支在检查之前就调
`get_dependency_info`，直接抛 ValueError。退出码碰巧非 0，但脚本/CI 拿到的是
traceback 而非可解析错误。修法：存在性检查前移，两条路径同一出口，
--json 下输出结构化错误。
"""
import json
import os
import subprocess
import sys

from click.testing import CliRunner
from unittest.mock import patch

from mini_claude.cli.main import main


def _invoke_tool_deps(*args: str):
    with (
        patch("mini_claude.cli.main.init_logging"),
        patch("mini_claude.cli.main.load_environment"),
    ):
        return CliRunner().invoke(main, ["tool-deps", *args])


class TestToolDepsJsonUnknownTool:
    def test_json_mode_reports_friendly_error(self):
        """判别性用例：未捕获 ValueError 时输出里没有友好错误，本用例转红。"""
        result = _invoke_tool_deps("--json", "__no_such_tool__")

        assert result.exit_code != 0, result.output
        assert "Traceback" not in result.output, (
            f"--json 模式不得吐 traceback:\n{result.output[-800:]}"
        )
        assert "__no_such_tool__" in result.output and "not found" in result.output.lower(), (
            f"--json 模式要有可解析的友好错误:\n{result.output[-800:]}"
        )

    def test_json_mode_error_is_parseable(self):
        """结构化错误必须真是 JSON（脚本/CI 要 parse 的）。"""
        result = _invoke_tool_deps("--json", "__no_such_tool__")

        assert result.exit_code != 0, result.output
        payload = json.loads(result.output)
        assert "error" in payload, f"结构化错误缺 error 键: {payload}"


_ENV_ALLOWLIST = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)

_PROCESS_STUB = '''\
import sys
from unittest.mock import patch

from mini_claude.cli.main import main

with patch("mini_claude.cli.main.init_logging"), patch(
    "mini_claude.cli.main.load_environment"
):
    main(["tool-deps", "--json", "__no_such_tool__"])
'''


class TestToolDepsJsonUnknownToolInRealProcess:
    """进程级复核：真实终端里不得出现 traceback。"""

    def test_real_process_has_no_traceback(self, tmp_path):
        script = tmp_path / "run_tool_deps_json.py"
        script.write_text(_PROCESS_STUB, encoding="utf-8")
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

        assert proc.returncode != 0, proc.stdout[-500:]
        assert "Traceback" not in (proc.stdout + proc.stderr), (
            f"真实终端出现 traceback:\n{proc.stderr[-800:]}"
        )
        assert "__no_such_tool__" in proc.stdout, proc.stdout[-500:]
