"""`health` / `tool-deps` 的退出码必须反映失败（ISSUE-015 同类问题）。

约定沿用项目自己的 `health_handler`（`monitoring/health.py:472`）：
`HEALTHY → 成功`，其余（含 `DEGRADED`）→ 失败。不另发明一套。
"""

import time
from unittest.mock import patch

from click.testing import CliRunner

from mini_claude.cli.main import main
from mini_claude.monitoring.health import (
    HealthReport,
    HealthStatus,
    ModelHealth,
    ServiceHealth,
    ToolHealth,
)


def _report(model_status: HealthStatus) -> HealthReport:
    """构造一份真实健康报告，整体状态由 `model_status` 决定。"""
    healthy = HealthStatus.HEALTHY
    now = time.time()
    return HealthReport(
        service=ServiceHealth(status=healthy, uptime_seconds=1.0, memory_usage_mb=1.0),
        model=ModelHealth(
            status=model_status,
            model_name="stub-model",
            provider="stub",
            last_check_time=now,
            error_message=None if model_status == healthy else "Insufficient Balance",
        ),
        tools=ToolHealth(
            status=healthy, total_tools=1, available_tools=1, tool_names=["read_file"]
        ),
        timestamp=now,
    )


def _invoke_health(report: HealthReport, *args: str):
    async def _fake_check_health():
        return report

    # health 在函数体内 import check_health，故 patch 模块属性即可。
    with (
        patch("mini_claude.cli.main.init_logging"),
        patch("mini_claude.cli.main.load_environment"),
        patch("mini_claude.monitoring.health.check_health", _fake_check_health),
    ):
        return CliRunner().invoke(main, ["health", *args])


def _invoke_tool_deps(*args: str):
    with (
        patch("mini_claude.cli.main.init_logging"),
        patch("mini_claude.cli.main.load_environment"),
    ):
        return CliRunner().invoke(main, ["tool-deps", *args])


class TestHealthExitCode:
    """health 的退出码必须反映整体健康状态。"""

    def test_health_exits_nonzero_when_unhealthy(self):
        """判别性用例：不把 unhealthy 反映到退出码时本用例转红。"""
        result = _invoke_health(_report(HealthStatus.UNHEALTHY))

        assert result.exit_code != 0, (
            f"health reported unhealthy but exited with code {result.exit_code}; "
            f"scripts/CI would read that as healthy.\noutput: {result.output}"
        )

    def test_health_exits_nonzero_when_degraded(self):
        """与 health_handler（200/503）保持同一约定：非 HEALTHY 即失败。"""
        result = _invoke_health(_report(HealthStatus.DEGRADED))

        assert result.exit_code != 0, (
            f"health reported degraded but exited with code {result.exit_code}\n"
            f"output: {result.output}"
        )

    def test_health_json_mode_exits_nonzero_when_unhealthy(self):
        """--json 是给脚本/CI 用的模式，退出码同样必须反映失败。"""
        result = _invoke_health(_report(HealthStatus.UNHEALTHY), "--json")

        assert result.exit_code != 0, result.output

    def test_health_exits_zero_when_healthy(self):
        """守卫：健康时仍是 0，且不得出现 Error。"""
        result = _invoke_health(_report(HealthStatus.HEALTHY))

        assert "Error" not in result.output, result.output
        assert result.exit_code == 0, result.output


class TestToolDepsExitCode:
    """tool-deps 指定的工具不存在时，必须让调用方从退出码看出来。"""

    def test_tool_deps_exits_nonzero_for_unknown_tool(self):
        result = _invoke_tool_deps("__no_such_tool__")

        assert result.exit_code != 0, (
            f"tool-deps reported a missing tool but exited with code {result.exit_code}\n"
            f"output: {result.output}"
        )

    def test_tool_deps_exits_zero_for_known_tool(self):
        """守卫：正常查询仍是 0。"""
        result = _invoke_tool_deps("read_file")

        assert "Error" not in result.output, result.output
        assert result.exit_code == 0, result.output
