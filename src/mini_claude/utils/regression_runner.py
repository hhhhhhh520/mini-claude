"""Regression test runner module.

This module is not a test file, it contains the RegressionRunner class.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Security: Use defusedxml for XML parsing to prevent XML attacks
try:
    from defusedxml.ElementTree import parse as safe_parse
    XML_SAFE = True
except ImportError:
    # Fallback to standard library if defusedxml not installed
    import xml.etree.ElementTree as ET  # noqa: B314
    safe_parse = ET.parse  # type: ignore[assignment]
    XML_SAFE = False


@dataclass
class RegressionResult:
    """Single test result."""
    name: str
    status: str  # passed, failed, skipped, error
    duration: float
    message: Optional[str] = None
    traceback: Optional[str] = None


@dataclass
class GroupResult:
    """Results for a test group (unit, integration, etc.)."""
    group_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    tests: list[RegressionResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 100.0
        return (self.passed / self.total) * 100


@dataclass
class Report:
    """Full regression test report."""
    timestamp: str
    duration: float
    groups: list[GroupResult]
    baseline_comparison: Optional[dict] = None

    @property
    def total_tests(self) -> int:
        return sum(g.total for g in self.groups)

    @property
    def total_passed(self) -> int:
        return sum(g.passed for g in self.groups)

    @property
    def total_failed(self) -> int:
        return sum(g.failed for g in self.groups)

    @property
    def total_skipped(self) -> int:
        return sum(g.skipped for g in self.groups)

    @property
    def overall_success_rate(self) -> float:
        if self.total_tests == 0:
            return 100.0
        return (self.total_passed / self.total_tests) * 100


class RegressionRunner:
    """Automated regression test runner with baseline comparison."""

    # Test groups in priority order
    TEST_GROUPS = [
        ("unit", "tests/test_utils", "tests/test_config", "tests/test_tools", "tests/test_llm"),
        ("integration", "tests/test_integration"),
        ("e2e", "tests/test_e2e"),
        ("stress", "tests/test_stress"),
        ("chaos", "tests/test_chaos"),
    ]

    # Quick test groups for fast feedback
    QUICK_GROUPS = ["unit"]

    def __init__(
        self,
        project_root: Path,
        baseline_file: Optional[Path] = None,
        report_dir: Optional[Path] = None,
    ):
        self.project_root = Path(project_root)
        self.baseline_file = baseline_file or self.project_root / ".baseline" / "baseline.json"
        self.report_dir = report_dir or self.project_root / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def run_group(self, group_name: str, test_paths: list[str], extra_args: Optional[list[str]] = None) -> GroupResult:
        """Run tests for a specific group."""
        result = GroupResult(group_name=group_name)
        start_time = time.time()

        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "-v",
            "--tb=short",
            f"--junitxml=.baseline/junit_{group_name}.xml",
            *test_paths,
        ]

        if extra_args:
            cmd.extend(extra_args)

        # Add group marker filter if available
        cmd.extend(["-m", group_name])

        try:
            subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout per group
            )

            # Parse JUnit XML if exists
            junit_file = self.project_root / ".baseline" / f"junit_{group_name}.xml"
            if junit_file.exists():
                result = self._parse_junit_xml(junit_file, group_name)

            result.duration = time.time() - start_time

        except subprocess.TimeoutExpired:
            result.errors = 1
            result.tests.append(RegressionResult(
                name=f"{group_name}_timeout",
                status="error",
                duration=600,
                message="Test group timed out after 10 minutes",
            ))
            result.duration = 600

        except Exception as e:
            result.errors = 1
            result.tests.append(RegressionResult(
                name=f"{group_name}_error",
                status="error",
                duration=time.time() - start_time,
                message=str(e),
            ))
            result.duration = time.time() - start_time

        return result

    def _parse_junit_xml(self, xml_file: Path, group_name: str) -> GroupResult:
        """Parse JUnit XML file to extract test results."""
        result = GroupResult(group_name=group_name)

        try:
            tree = safe_parse(xml_file)
            root = tree.getroot()

            for testcase in root.iter("testcase"):
                name = testcase.get("name", "unknown")
                classname = testcase.get("classname", "")
                full_name = f"{classname}::{name}" if classname else name

                # Determine status
                status = "passed"
                message = None
                traceback = None

                failure = testcase.find("failure")
                error = testcase.find("error")
                skipped = testcase.find("skipped")

                if failure is not None:
                    status = "failed"
                    message = failure.get("message")
                    traceback = failure.text
                    result.failed += 1
                elif error is not None:
                    status = "error"
                    message = error.get("message")
                    traceback = error.text
                    result.errors += 1
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.get("message")
                    result.skipped += 1
                else:
                    result.passed += 1

                result.total += 1

                # Parse duration
                time_str = testcase.get("time", "0")
                try:
                    duration = float(time_str)
                except ValueError:
                    duration = 0.0

                result.tests.append(RegressionResult(
                    name=full_name,
                    status=status,
                    duration=duration,
                    message=message,
                    traceback=traceback,
                ))

        except ET.ParseError:
            # If XML parsing fails, return empty result
            pass

        return result

    def run_quick(self) -> Report:
        """Run quick regression tests (unit tests only)."""
        return self.run(groups=self.QUICK_GROUPS)

    def run_full(self) -> Report:
        """Run full regression test suite."""
        return self.run(groups=None)

    def run(self, groups: Optional[list[str]] = None) -> Report:
        """Run regression tests for specified groups.

        Args:
            groups: List of group names to run. If None, run all groups.

        Returns:
            Report with test results.
        """
        start_time = time.time()
        report_groups: list[GroupResult] = []

        # Create baseline directory
        baseline_dir = self.project_root / ".baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)

        # Determine which groups to run
        groups_to_run = groups if groups else [g[0] for g in self.TEST_GROUPS]

        for group_name, *test_paths in self.TEST_GROUPS:
            if group_name not in groups_to_run:
                continue

            # Check if test paths exist
            existing_paths = [
                str(self.project_root / p)
                for p in test_paths
                if (self.project_root / p).exists()
            ]

            if not existing_paths:
                # Try running by marker only if paths don't exist
                existing_paths = [str(self.project_root / "tests")]

            print(f"\n{'='*60}")
            print(f"Running {group_name} tests...")
            print(f"{'='*60}")

            group_result = self.run_group(group_name, existing_paths)
            report_groups.append(group_result)

            print(f"\n{group_name.capitalize()} tests: "
                  f"{group_result.passed} passed, "
                  f"{group_result.failed} failed, "
                  f"{group_result.skipped} skipped, "
                  f"{group_result.errors} errors "
                  f"in {group_result.duration:.2f}s")

        total_duration = time.time() - start_time

        # Load baseline and compare
        baseline_comparison = None
        if self.baseline_file.exists():
            baseline_comparison = self._compare_with_baseline(report_groups)

        report = Report(
            timestamp=datetime.now().isoformat(),
            duration=total_duration,
            groups=report_groups,
            baseline_comparison=baseline_comparison,
        )

        # Save new baseline
        self._save_baseline(report)

        return report

    def _compare_with_baseline(self, current_groups: list[GroupResult]) -> dict:
        """Compare current results with baseline."""
        try:
            with open(self.baseline_file, encoding="utf-8") as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return None

        comparison = {
            "regressions": [],
            "improvements": [],
            "new_failures": [],
            "new_passes": [],
        }

        baseline_tests = {}
        for group in baseline.get("groups", []):
            for test in group.get("tests", []):
                baseline_tests[test["name"]] = test["status"]

        current_tests = {}
        for group in current_groups:
            for test in group.tests:
                current_tests[test.name] = test.status

        # Find regressions (passed -> failed)
        for name, status in current_tests.items():
            if name in baseline_tests:
                old_status = baseline_tests[name]
                if old_status == "passed" and status in ("failed", "error"):
                    comparison["regressions"].append({
                        "name": name,
                        "old_status": old_status,
                        "new_status": status,
                    })
                elif old_status in ("failed", "error") and status == "passed":
                    comparison["improvements"].append({
                        "name": name,
                        "old_status": old_status,
                        "new_status": status,
                    })

        # Find new failures (tests that didn't exist before)
        for name, status in current_tests.items():
            if name not in baseline_tests and status in ("failed", "error"):
                comparison["new_failures"].append({
                    "name": name,
                    "status": status,
                })

        # Find new passes
        for name, status in current_tests.items():
            if name not in baseline_tests and status == "passed":
                comparison["new_passes"].append({
                    "name": name,
                    "status": status,
                })

        return comparison

    def _save_baseline(self, report: Report) -> None:
        """Save current results as baseline."""
        baseline_data = {
            "timestamp": report.timestamp,
            "duration": report.duration,
            "total_tests": report.total_tests,
            "total_passed": report.total_passed,
            "total_failed": report.total_failed,
            "total_skipped": report.total_skipped,
            "groups": [
                {
                    "group_name": g.group_name,
                    "total": g.total,
                    "passed": g.passed,
                    "failed": g.failed,
                    "skipped": g.skipped,
                    "errors": g.errors,
                    "tests": [
                        {
                            "name": t.name,
                            "status": t.status,
                            "duration": t.duration,
                            "message": t.message,
                        }
                        for t in g.tests
                    ],
                }
                for g in report.groups
            ],
        }

        self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.baseline_file, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, indent=2)

    def generate_json_report(self, report: Report) -> Path:
        """Generate JSON report."""
        report_path = self.report_dir / f"regression_{report.timestamp.replace(':', '-')}.json"

        report_data = {
            "timestamp": report.timestamp,
            "duration": report.duration,
            "summary": {
                "total_tests": report.total_tests,
                "passed": report.total_passed,
                "failed": report.total_failed,
                "skipped": report.total_skipped,
                "success_rate": report.overall_success_rate,
            },
            "groups": [
                {
                    "name": g.group_name,
                    "total": g.total,
                    "passed": g.passed,
                    "failed": g.failed,
                    "skipped": g.skipped,
                    "errors": g.errors,
                    "duration": g.duration,
                    "success_rate": g.success_rate,
                    "failed_tests": [
                        {
                            "name": t.name,
                            "message": t.message,
                            "traceback": t.traceback,
                        }
                        for t in g.tests
                        if t.status in ("failed", "error")
                    ],
                }
                for g in report.groups
            ],
            "baseline_comparison": report.baseline_comparison,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        return report_path

    def generate_markdown_report(self, report: Report) -> Path:
        """Generate Markdown report."""
        report_path = self.report_dir / f"regression_{report.timestamp.replace(':', '-')}.md"

        lines = [
            "# Regression Test Report",
            "",
            f"**Timestamp**: {report.timestamp}",
            f"**Duration**: {report.duration:.2f}s",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Tests | {report.total_tests} |",
            f"| Passed | {report.total_passed} |",
            f"| Failed | {report.total_failed} |",
            f"| Skipped | {report.total_skipped} |",
            f"| Success Rate | {report.overall_success_rate:.1f}% |",
            "",
            "## Test Groups",
            "",
        ]

        for group in report.groups:
            lines.extend([
                f"### {group.group_name.capitalize()}",
                "",
                "| Status | Count |",
                "|--------|-------|",
                f"| Passed | {group.passed} |",
                f"| Failed | {group.failed} |",
                f"| Skipped | {group.skipped} |",
                f"| Errors | {group.errors} |",
                f"| Duration | {group.duration:.2f}s |",
                "",
            ])

            # List failed tests
            failed_tests = [t for t in group.tests if t.status in ("failed", "error")]
            if failed_tests:
                lines.extend([
                    "#### Failed Tests",
                    "",
                ])
                for test in failed_tests:
                    lines.append(f"- **{test.name}**")
                    if test.message:
                        lines.append(f"  - Message: {test.message}")
                    lines.append("")

        # Baseline comparison
        if report.baseline_comparison:
            lines.extend([
                "## Baseline Comparison",
                "",
            ])

            regressions = report.baseline_comparison.get("regressions", [])
            if regressions:
                lines.append(f"### Regressions ({len(regressions)})")
                lines.append("")
                for r in regressions:
                    lines.append(f"- {r['name']}: {r['old_status']} -> {r['new_status']}")
                lines.append("")

            improvements = report.baseline_comparison.get("improvements", [])
            if improvements:
                lines.append(f"### Improvements ({len(improvements)})")
                lines.append("")
                for i in improvements:
                    lines.append(f"- {i['name']}: {i['old_status']} -> {i['new_status']}")
                lines.append("")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return report_path

    def run_incremental(self, changed_files: list[str]) -> Report:
        """Run tests affected by changed files.

        This is a simplified implementation that runs tests from directories
        matching the changed files. A more sophisticated implementation would
        analyze imports and dependencies.
        """
        # Map file paths to test directories
        test_dirs = set()

        for file_path in changed_files:
            file_path = Path(file_path)

            # Check if it's a test file
            if "test_" in file_path.name:
                test_dirs.add(str(file_path.parent))
                continue

            # Map source files to test directories
            parts = file_path.parts
            if "mini_claude" in parts:
                idx = parts.index("mini_claude")
                if idx + 1 < len(parts):
                    module = parts[idx + 1]
                    test_dir = self.project_root / "tests" / f"test_{module}"
                    if test_dir.exists():
                        test_dirs.add(str(test_dir))

        if not test_dirs:
            # Default to all tests if no mapping found
            test_dirs = {str(self.project_root / "tests")}

        # Run tests for affected directories
        start_time = time.time()
        report_groups: list[GroupResult] = []

        baseline_dir = self.project_root / ".baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)

        group_result = self.run_group("incremental", list(test_dirs))
        report_groups.append(group_result)

        total_duration = time.time() - start_time

        return Report(
            timestamp=datetime.now().isoformat(),
            duration=total_duration,
            groups=report_groups,
        )