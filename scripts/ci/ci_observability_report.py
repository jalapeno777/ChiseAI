#!/usr/bin/env python3
"""
CI Observability Report

Story: ST-CI-OBS-001

Aggregates CI step timings and provides diagnostic visibility for CI failures.
Generates a comprehensive report of step durations, status, and failure diagnostics.

Usage:
    python scripts/ci/ci_observability_report.py
    python scripts/ci/ci_observability_report.py --ci-dir /woodpecker/ci-status/123
    python scripts/ci/ci_observability_report.py --verbose --json

Exit Codes:
    0 - Success (report generated)
    1 - No CI data found or error

Output:
    JSON report to stdout (with --json)
    Human-readable report to stdout (default)
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

# Configuration
CI_STATUS_DIR_ENV = "CI_STATUS_DIR"
DEFAULT_CI_STATUS_DIR = "/woodpecker/ci-status/${CI_PIPELINE_NUMBER}"

OBSERVABILITY_REPORT_VERSION = "1.0.0"

# Step timing patterns in logs
TIMING_PATTERNS = [
    # Duration in seconds: "Completed in 120s" or "Duration: 120s"
    r"(?:Completed|Duration) in (\d+)s",
    # ISO timestamp with 'Started at' and 'Ended at'
    r"Started at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)",
    r"Ended at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)",
    # Unix timestamp: "START_TIME=1234567890"
    r"START_TIME[=:](\d+)",
    r"END_TIME[=:](\d+)",
    # Performance JSON: "duration_seconds": 123
    r'"duration_seconds"\s*:\s*(\d+(?:\.\d+)?)',
    # Step timing header: "[step-name] Starting..." to "[step-name] Completed in Xs"
    r"\[([\w-]+)\] Completed in (\d+)s",
    # Group timing: "GROUP_START_TIME" and "GROUP_END_TIME"
    r"GROUP_START_TIME=(\d+)",
    r"GROUP_END_TIME=(\d+)",
]


@dataclass
class StepTiming:
    """Timing information for a single CI step."""

    step_name: str
    duration_seconds: float | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str = "unknown"  # pass, fail, skip, unknown
    has_timing: bool = False
    exit_code: int | None = None


@dataclass
class StepDiagnostics:
    """Diagnostic information for a CI step."""

    step_name: str
    exit_code: int | None = None
    error_summary: str | None = None
    failed_commands: list[str] = field(default_factory=list)
    traceback_lines: int = 0
    has_stack_trace: bool = False


@dataclass
class CIObservabilityReport:
    """Complete CI observability report."""

    version: str
    timestamp: str
    pipeline_number: str | None
    branch: str | None
    commit_sha: str | None
    steps: list[dict]
    total_duration_seconds: float | None
    overall_status: str  # pass, fail, partial, unknown
    diagnostics_available: bool = False
    summary: dict = field(default_factory=dict)


class CIObservabilityCollector:
    """Collects and analyzes CI observability data."""

    def __init__(self, ci_dir: Path):
        self.ci_dir = ci_dir
        self.steps: dict[str, StepTiming] = {}
        self.diagnostics: dict[str, StepDiagnostics] = {}

    def collect(self) -> CIObservabilityReport:
        """Collect all CI observability data."""
        if not self.ci_dir.exists():
            return self._empty_report()

        # Get pipeline context
        pipeline_number = os.environ.get("CI_PIPELINE_NUMBER")
        branch = os.environ.get("CI_COMMIT_BRANCH") or os.environ.get(
            "WOODPECKER_COMMIT_BRANCH"
        )
        commit_sha = os.environ.get("CI_COMMIT_SHA") or os.environ.get(
            "WOODPECKER_COMMIT_SHA"
        )

        # Scan all status and log files
        self._scan_status_files()
        self._scan_log_files()
        self._extract_diagnostics()

        # Build summary
        steps_data = []
        total_duration = 0.0
        steps_with_timing = 0
        passed_steps = 0
        failed_steps = 0

        for step_name, timing in sorted(self.steps.items()):
            step_dict = asdict(timing)
            # Merge diagnostics into step data if available
            if step_name in self.diagnostics:
                diag = self.diagnostics[step_name]
                step_dict["diagnostics"] = asdict(diag)
            steps_data.append(step_dict)
            if timing.duration_seconds is not None:
                total_duration += timing.duration_seconds
                steps_with_timing += 1
            if timing.status == "pass":
                passed_steps += 1
            elif timing.status == "fail":
                failed_steps += 1

        # Determine overall status
        if failed_steps > 0:
            overall_status = "fail"
        elif passed_steps > 0:
            overall_status = "pass"
        else:
            overall_status = "unknown"

        summary = {
            "total_steps": len(self.steps),
            "steps_with_timing": steps_with_timing,
            "total_duration_seconds": total_duration if steps_with_timing > 0 else None,
            "passed_steps": passed_steps,
            "failed_steps": failed_steps,
            "diagnostics_available": any(
                d.exit_code is not None or d.error_summary
                for d in self.diagnostics.values()
            ),
        }

        return CIObservabilityReport(
            version=OBSERVABILITY_REPORT_VERSION,
            timestamp=datetime.now(UTC).isoformat(),
            pipeline_number=pipeline_number,
            branch=branch,
            commit_sha=commit_sha,
            steps=steps_data,
            total_duration_seconds=total_duration if steps_with_timing > 0 else None,
            overall_status=overall_status,
            diagnostics_available=summary["diagnostics_available"],
            summary=summary,
        )

    def _scan_status_files(self):
        """Scan status files for step status information."""
        if not self.ci_dir.exists():
            return

        for status_file in self.ci_dir.glob("*.status"):
            step_name = status_file.stem
            try:
                content = status_file.read_text(encoding="utf-8").strip()
                status = "unknown"

                if content in ("0", "PASS", "WARN", "SKIP"):
                    status = "pass"
                elif content in ("1", "FAIL", "ERROR"):
                    status = "fail"

                if step_name not in self.steps:
                    self.steps[step_name] = StepTiming(step_name=step_name)

                self.steps[step_name].status = status
                self.steps[step_name].exit_code = (
                    int(content) if content.isdigit() else None
                )
            except (ValueError, OSError):
                pass

    def _scan_log_files(self):
        """Scan log files for timing information."""
        if not self.ci_dir.exists():
            return

        for log_file in self.ci_dir.glob("*.log"):
            step_name = log_file.stem
            timing = self.steps.get(step_name, StepTiming(step_name=step_name))

            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")

                # Try to extract timing from log content
                duration = self._extract_duration(content)
                if duration is not None:
                    timing.duration_seconds = duration
                    timing.has_timing = True

                # Try to extract start/end times
                start_time = self._extract_timestamp(content, "start")
                end_time = self._extract_timestamp(content, "end")
                if start_time:
                    timing.start_time = start_time
                if end_time:
                    timing.end_time = end_time

                # Check for timing patterns like GROUP_START_TIME/END_TIME
                group_timing = self._extract_group_timing(content)
                if group_timing:
                    timing.duration_seconds = group_timing
                    timing.has_timing = True

                self.steps[step_name] = timing

            except OSError:
                pass

    def _extract_duration(self, content: str) -> float | None:
        """Extract duration in seconds from log content."""
        # Look for explicit duration patterns
        patterns = [
            r"(?:Completed|Duration) in (\d+(?:\.\d+)?)s",
            r'"duration_seconds"\s*:\s*(\d+(?:\.\d+)?)',
            r"\[([\w-]+)\] Completed in (\d+(?:\.\d+)?)s",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                # Handle both single group and multi-group matches
                for match in matches:
                    if isinstance(match, tuple):
                        try:
                            return float(match[1])
                        except (ValueError, IndexError):
                            continue
                    else:
                        try:
                            return float(match)
                        except ValueError:
                            continue
        return None

    def _extract_timestamp(self, content: str, which: str) -> str | None:
        """Extract timestamp from log content."""
        patterns = {
            "start": [
                r"Started at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)",
                r"START_TIME[=:](\d+)",
            ],
            "end": [
                r"Ended at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)",
                r"END_TIME[=:](\d+)",
            ],
        }

        for pattern in patterns.get(which, []):
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        return None

    def _extract_group_timing(self, content: str) -> float | None:
        """Extract group timing from GROUP_START_TIME and GROUP_END_TIME."""
        start_match = re.search(r"GROUP_START_TIME=(\d+)", content)
        end_match = re.search(r"GROUP_END_TIME=(\d+)", content)

        if start_match and end_match:
            try:
                start = int(start_match.group(1))
                end = int(end_match.group(1))
                if end > start:
                    return float(end - start)
            except ValueError:
                pass
        return None

    def _extract_diagnostics(self):
        """Extract diagnostic information from logs."""
        if not self.ci_dir.exists():
            return

        for log_file in self.ci_dir.glob("*.log"):
            step_name = log_file.stem
            diag = StepDiagnostics(step_name=step_name)

            # Copy exit_code from StepTiming if available (set by _scan_status_files)
            if step_name in self.steps and self.steps[step_name].exit_code is not None:
                diag.exit_code = self.steps[step_name].exit_code

            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")

                # Check for tracebacks
                traceback_count = sum(1 for line in lines if "Traceback" in line)
                diag.traceback_lines = traceback_count
                diag.has_stack_trace = traceback_count > 0

                # Extract error summary (last error line before exit)
                error_lines = [
                    line.strip()
                    for line in lines
                    if any(
                        marker in line.lower()
                        for marker in ["error", "failed", "failure", "exception"]
                    )
                    and not line.strip().startswith("#")
                ]
                if error_lines:
                    # Get the last meaningful error line
                    diag.error_summary = error_lines[-1][:200]

                # Check for failed commands in set -euo pipefail output
                failed_cmds = re.findall(
                    r"^\s*([^:\s]+:?)[^;]*failed|error code (\d+)",
                    content,
                    re.MULTILINE,
                )
                if failed_cmds:
                    diag.failed_commands = [str(cmd) for cmd in failed_cmds if cmd]

                self.diagnostics[step_name] = diag

            except OSError:
                pass

    def _empty_report(self) -> CIObservabilityReport:
        """Return an empty report when no CI data is available."""
        return CIObservabilityReport(
            version=OBSERVABILITY_REPORT_VERSION,
            timestamp=datetime.now(UTC).isoformat(),
            pipeline_number=None,
            branch=None,
            commit_sha=None,
            steps=[],
            total_duration_seconds=None,
            overall_status="unknown",
            diagnostics_available=False,
            summary={
                "total_steps": 0,
                "steps_with_timing": 0,
                "total_duration_seconds": None,
                "passed_steps": 0,
                "failed_steps": 0,
                "diagnostics_available": False,
            },
        )


def format_human_report(report: CIObservabilityReport, verbose: bool = False) -> str:
    """Format report as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("CI OBSERVABILITY REPORT")
    lines.append("=" * 80)
    lines.append(f"Version: {report.version}")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append(f"Pipeline: {report.pipeline_number or 'unknown'}")
    lines.append(f"Branch: {report.branch or 'unknown'}")
    lines.append(f"Commit: {report.commit_sha or 'unknown'[:8]}")
    lines.append("")

    # Summary
    lines.append("SUMMARY:")
    lines.append(f"  Overall Status: {report.overall_status.upper()}")
    lines.append(f"  Total Steps: {report.summary['total_steps']}")
    lines.append(f"  Steps with Timing: {report.summary['steps_with_timing']}")
    if report.summary.get("total_duration_seconds"):
        lines.append(
            f"  Total Duration: {report.summary['total_duration_seconds']:.1f}s"
        )
    lines.append(f"  Passed: {report.summary['passed_steps']}")
    lines.append(f"  Failed: {report.summary['failed_steps']}")
    lines.append("")

    # Step timing table
    if report.steps:
        lines.append("STEP TIMINGS:")
        lines.append("-" * 80)
        lines.append(f"{'Step Name':<40} {'Duration':>10} {'Status':>10}")
        lines.append("-" * 80)

        for step in report.steps:
            name = step["step_name"]
            duration = step.get("duration_seconds")
            status = step.get("status", "unknown")

            duration_str = f"{duration:.1f}s" if duration else "N/A"
            status_str = status.upper()

            lines.append(f"{name:<40} {duration_str:>10} {status_str:>10}")

        lines.append("-" * 80)
        lines.append("")

    # Diagnostics for failed steps
    if verbose:
        failed_steps = [s for s in report.steps if s.get("status") == "fail"]
        if failed_steps:
            lines.append("FAILED STEP DIAGNOSTICS:")
            lines.append("-" * 80)
            for step in failed_steps:
                lines.append(f"  Step: {step['step_name']}")
                if step.get("duration_seconds"):
                    lines.append(f"    Duration: {step['duration_seconds']:.1f}s")
                lines.append("")
            lines.append("-" * 80)
            lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def format_json_report(report: CIObservabilityReport) -> str:
    """Format report as JSON."""
    return json.dumps(asdict(report), indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CI Observability Report - Aggregate CI step timings and diagnostics"
    )
    parser.add_argument(
        "--ci-dir",
        type=str,
        default=None,
        help=f"CI status directory (or set {CI_STATUS_DIR_ENV} env var)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed diagnostics",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Determine CI status directory
    ci_dir_path = args.ci_dir or os.environ.get(CI_STATUS_DIR_ENV, "")

    # Expand CI_PIPELINE_NUMBER in path if present
    pipeline_number = os.environ.get("CI_PIPELINE_NUMBER", "")
    if "${CI_PIPELINE_NUMBER}" in ci_dir_path and pipeline_number:
        ci_dir_path = ci_dir_path.replace("${CI_PIPELINE_NUMBER}", pipeline_number)

    # Handle empty/unset path
    if not ci_dir_path or ci_dir_path == "${CI_PIPELINE_NUMBER}":
        # Try to find CI status dir in common locations
        for candidate in [
            Path("/woodpecker/ci-status/latest"),
            Path("/tmp/ci-status/latest"),
            Path.cwd() / "_bmad-output" / "ci",
        ]:
            if candidate.exists():
                ci_dir_path = str(candidate)
                break
        else:
            ci_dir_path = str(Path.cwd() / "_bmad-output" / "ci")

    ci_dir = Path(ci_dir_path)

    # Collect observability data
    collector = CIObservabilityCollector(ci_dir)
    report = collector.collect()

    # Output report
    if args.json:
        print(format_json_report(report))
    else:
        print(format_human_report(report, verbose=args.verbose))

    # Return exit code based on status
    if report.overall_status == "fail":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
