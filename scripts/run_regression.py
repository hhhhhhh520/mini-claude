#!/usr/bin/env python3
"""Regression test runner CLI.

Usage:
    python scripts/run_regression.py --quick    # Fast regression (unit tests)
    python scripts/run_regression.py --full     # Full regression suite
    python scripts/run_regression.py --report   # Generate reports only
    python scripts/run_regression.py --incremental <files>  # Incremental testing
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from mini_claude.utils.regression_runner import (
    RegressionRunner,
    Report,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run regression tests for Mini Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/run_regression.py --quick
        Run quick regression tests (unit tests only, ~2-5 minutes)

    python scripts/run_regression.py --full
        Run full regression test suite (all test groups)

    python scripts/run_regression.py --report
        Generate reports from existing baseline

    python scripts/run_regression.py --incremental src/mini_claude/agent/state.py
        Run tests affected by changed files
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--quick",
        action="store_true",
        help="Run quick regression tests (unit tests only)",
    )
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Run full regression test suite",
    )
    mode_group.add_argument(
        "--report",
        action="store_true",
        help="Generate reports from existing baseline",
    )
    mode_group.add_argument(
        "--incremental",
        nargs="+",
        metavar="FILE",
        help="Run incremental tests for changed files",
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=project_root,
        help="Project root directory",
    )
    parser.add_argument(
        "--baseline-file",
        type=Path,
        help="Path to baseline JSON file",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Directory for generated reports",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with non-zero code if regressions detected",
    )

    args = parser.parse_args()

    # Initialize runner
    runner = RegressionRunner(
        project_root=args.project_root,
        baseline_file=args.baseline_file,
        report_dir=args.report_dir,
    )

    # Run tests
    if args.quick:
        print("Running quick regression tests...")
        report = runner.run_quick()
    elif args.full:
        print("Running full regression test suite...")
        report = runner.run_full()
    elif args.incremental:
        print(f"Running incremental tests for {len(args.incremental)} files...")
        report = runner.run_incremental(args.incremental)
    elif args.report:
        print("Generating reports from existing baseline...")
        if runner.baseline_file.exists():
            with open(runner.baseline_file, encoding="utf-8") as f:
                baseline_data = json.load(f)
            # Create a minimal report from baseline
            report = Report(
                timestamp=baseline_data["timestamp"],
                duration=baseline_data["duration"],
                groups=[],
            )
        else:
            print("ERROR: No baseline file found. Run tests first.")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Generate reports
    json_report = runner.generate_json_report(report)
    md_report = runner.generate_markdown_report(report)

    print(f"\n{'='*60}")
    print("REGRESSION TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total tests: {report.total_tests}")
    print(f"Passed: {report.total_passed}")
    print(f"Failed: {report.total_failed}")
    print(f"Skipped: {report.total_skipped}")
    print(f"Duration: {report.duration:.2f}s")
    print(f"\nReports generated:")
    print(f"  JSON: {json_report}")
    print(f"  Markdown: {md_report}")

    # Check for regressions
    exit_code = 0
    if report.baseline_comparison:
        regressions = report.baseline_comparison.get("regressions", [])
        if regressions:
            print(f"\n{'!'*60}")
            print(f"WARNING: {len(regressions)} regression(s) detected!")
            print(f"{'!'*60}")
            for r in regressions:
                print(f"  - {r['name']}: {r['old_status']} -> {r['new_status']}")

            if args.fail_on_regression:
                exit_code = 1

    # Exit with error if tests failed
    if report.total_failed > 0:
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
