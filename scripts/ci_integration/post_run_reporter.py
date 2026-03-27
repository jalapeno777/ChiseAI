#!/usr/bin/env python3
"""Post-run reporter for CI integration.

This script collects test results, coverage, and metrics from CI runs,
then generates a unified CI report in both JSON and markdown formats.
Metrics are also exported in InfluxDB line protocol format.

Exit codes:
    0 - Success (always, even if tests failed - reports are still generated)
    1 - Fatal error (e.g., can't read results)

Output:
    JSON report to stdout
    Markdown report to file (default: ci_report.md)
    InfluxDB metrics to stdout (when --influxdb flag used)
"""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class CIResultSummary:
    """Summary of test results."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    duration_seconds: float = 0.0


@dataclass
class CoverageData:
    """Coverage summary."""

    line_percent: float = 0.0
    branch_percent: float = 0.0
    covered_lines: int = 0
    total_lines: int = 0


@dataclass
class MetricsData:
    """Additional metrics summary."""

    pylint_score: float | None = None
    ruff_issues: int = 0
    black_formatting_issues: int = 0


@dataclass
class CIReport:
    """Complete CI report."""

    timestamp: str
    branch: str
    commit_sha: str
    test_summary: CIResultSummary
    coverage_summary: CoverageData | None = None
    metrics_summary: MetricsData | None = None
    gates_passed: bool = True
    gate_details: dict = field(default_factory=dict)


def get_git_info(repo_path: Path) -> tuple[str, str]:
    """Get branch and commit SHA from git."""
    try:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=repo_path,
        )
        branch = branch_result.stdout.strip() or "unknown"

        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=repo_path,
        )
        commit_sha = sha_result.stdout.strip() or "unknown"

        return branch, commit_sha
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown", "unknown"


def parse_pytest_json(json_path: Path) -> CIResultSummary | None:
    """Parse pytest JSON report file."""
    try:
        with open(json_path) as f:
            data = json.load(f)

        summary = CIResultSummary()
        summary.total = data.get("num_tests", 0)

        if "summary" in data:
            summary.passed = data["summary"].get("passed", 0)
            summary.failed = data["summary"].get("failed", 0)
            summary.skipped = data["summary"].get("skipped", 0)
            summary.error = data["summary"].get("error", 0)

        if "duration" in data:
            summary.duration_seconds = float(data["duration"])

        return summary
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None


def parse_coverage_json(coverage_path: Path) -> CoverageData | None:
    """Parse coverage JSON report."""
    try:
        with open(coverage_path) as f:
            data = json.load(f)

        summary = CoverageData()

        if "totals" in data:
            totals = data["totals"]
            summary.line_percent = totals.get("percent_covered", 0)
            summary.branch_percent = totals.get("branch_covered", 0)
            summary.covered_lines = totals.get("covered_lines", 0)
            summary.total_lines = totals.get("total_lines", 0)

        return summary
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None


def generate_markdown_report(report: CIReport) -> str:
    """Generate markdown report from CI report."""
    md = []
    md.append(f"# CI Report - {report.branch}")
    md.append(f"\n**Timestamp:** {report.timestamp}")
    md.append(f"**Commit:** `{report.commit_sha}`")
    md.append(f"**Status:** {'✅ PASSED' if report.gates_passed else '❌ FAILED'}")
    md.append("")

    md.append("## Test Summary")
    md.append(f"- Total: {report.test_summary.total}")
    md.append(f"- Passed: {report.test_summary.passed}")
    md.append(f"- Failed: {report.test_summary.failed}")
    md.append(f"- Skipped: {report.test_summary.skipped}")
    md.append(f"- Error: {report.test_summary.error}")
    md.append(f"- Duration: {report.test_summary.duration_seconds:.2f}s")
    md.append("")

    if report.coverage_summary:
        md.append("## Coverage")
        cov = report.coverage_summary
        md.append(f"- Line Coverage: {cov.line_percent:.2f}%")
        md.append(f"- Branch Coverage: {cov.branch_percent:.2f}%")
        md.append(f"- Lines: {cov.covered_lines}/{cov.total_lines}")
        md.append("")

    if report.metrics_summary:
        md.append("## Code Quality Metrics")
        metrics = report.metrics_summary
        if metrics.pylint_score is not None:
            md.append(f"- Pylint Score: {metrics.pylint_score:.2f}")
        if metrics.ruff_issues > 0:
            md.append(f"- Ruff Issues: {metrics.ruff_issues}")
        if metrics.black_formatting_issues > 0:
            md.append(f"- Black Formatting Issues: {metrics.black_formatting_issues}")
        md.append("")

    if report.gate_details:
        md.append("## Gate Details")
        for gate_name, gate_result in report.gate_details.items():
            status = "✅" if gate_result.get("passed") else "❌"
            md.append(f"- {status} {gate_name}: {gate_result.get('message', '')}")
        md.append("")

    return "\n".join(md)


def generate_influxdb_line_protocol(report: CIReport) -> list[str]:
    """Generate InfluxDB line protocol from CI report."""
    lines = []
    timestamp = int(datetime.now(UTC).timestamp() * 1e9)

    # Test metrics
    if report.test_summary.total > 0:
        lines.append(
            f"ci_tests,branch={report.branch},commit={report.commit_sha[:8]} "
            f"total={report.test_summary.total},passed={report.test_summary.passed},"
            f"failed={report.test_summary.failed},skipped={report.test_summary.skipped},"
            f"error={report.test_summary.error},duration={report.test_summary.duration_seconds} {timestamp}"
        )

    # Coverage metrics
    if report.coverage_summary:
        cov = report.coverage_summary
        lines.append(
            f"ci_coverage,branch={report.branch},commit={report.commit_sha[:8]} "
            f"line_percent={cov.line_percent},branch_percent={cov.branch_percent},"
            f"covered_lines={cov.covered_lines},total_lines={cov.total_lines} {timestamp}"
        )

    # Gates
    lines.append(
        f"ci_gates,branch={report.branch},commit={report.commit_sha[:8]} "
        f"passed={1 if report.gates_passed else 0} {timestamp}"
    )

    return lines


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CI Post-Run Reporter")
    parser.add_argument("--pytest-json", type=Path, help="Path to pytest JSON report")
    parser.add_argument(
        "--coverage-json", type=Path, help="Path to coverage JSON report"
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("ci_report.md"),
        help="Output markdown file",
    )
    parser.add_argument(
        "--influxdb", action="store_true", help="Output InfluxDB line protocol"
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=Path("/tmp/worktrees/ST-LOCAL-009-dev"),
        help="Repository path",
    )
    parser.add_argument(
        "--gates-passed", type=lambda x: x.lower() == "true", default=True
    )
    parser.add_argument("--gate-details", type=json.loads, default=dict())

    args = parser.parse_args()

    branch, commit_sha = get_git_info(args.repo_path)

    # Parse test results
    test_summary = CIResultSummary()
    if args.pytest_json and args.pytest_json.exists():
        parsed = parse_pytest_json(args.pytest_json)
        if parsed:
            test_summary = parsed

    # Parse coverage
    coverage_summary = None
    if args.coverage_json and args.coverage_json.exists():
        coverage_summary = parse_coverage_json(args.coverage_json)

    # Build report
    report = CIReport(
        timestamp=datetime.now(UTC).isoformat(),
        branch=branch,
        commit_sha=commit_sha,
        test_summary=test_summary,
        coverage_summary=coverage_summary,
        gates_passed=args.gates_passed,
        gate_details=args.gate_details,
    )

    # Output JSON to stdout
    print(json.dumps(asdict(report), indent=2))

    # Generate markdown report
    md_report = generate_markdown_report(report)
    args.output_md.write_text(md_report)

    # Output InfluxDB line protocol if requested
    if args.influxdb:
        for line in generate_influxdb_line_protocol(report):
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
