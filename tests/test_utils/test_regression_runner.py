"""❌2 回归：regression_runner 不得再出现悬空引用或指向不存在路径的测试组.

背景：2026-06-28 那轮「删除死代码」误删了 `utils/regression_runner.py`，
而 `scripts/run_regression.py:20` 仍 import 它 → CI 每日回归 job 静默 no-op。
本文件锁住两条契约，防止同类问题复发：
  1. `scripts/run_regression.py` 的 import 目标必须真实存在；
  2. `RegressionRunner.TEST_GROUPS` 里每个路径必须真实存在（历史上列过
     tests/test_chaos、tests/test_e2e、tests/test_stress 等已不存在的路径）。
"""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_run_regression_script_import_target_exists():
    """scripts/run_regression.py import 的模块必须可导入."""
    from mini_claude.utils.regression_runner import RegressionRunner, Report

    assert RegressionRunner is not None
    assert Report is not None


def test_regression_runner_script_is_importable():
    """脚本本身应能编译（语法/顶层 import 不炸），不执行 main()."""
    import py_compile

    script = PROJECT_ROOT / "scripts" / "run_regression.py"
    assert script.exists(), f"缺少 {script}"
    py_compile.compile(str(script), doraise=True)


def test_all_regression_group_paths_exist():
    """TEST_GROUPS 中每个测试路径必须存在，否则 run() 收集阶段即报错."""
    from mini_claude.utils.regression_runner import RegressionRunner

    for group_name, *paths in RegressionRunner.TEST_GROUPS:
        for p in paths:
            assert os.path.exists(PROJECT_ROOT / p), f"回归组 {group_name!r} 指向不存在的路径：{p}"


def test_report_has_total_failed_field():
    """CI 的 Check-for-regressions 步骤依赖 Report.total_failed."""
    from mini_claude.utils.regression_runner import Report, GroupResult

    report = Report(
        timestamp="2026-09-04T00:00:00",
        duration=1.0,
        groups=[GroupResult(group_name="unit", total=3, passed=3, failed=0)],
    )
    assert report.total_failed == 0
    assert report.total_passed == 3
    assert report.total_tests == 3
