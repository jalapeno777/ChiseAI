#!/usr/bin/env python3
"""
Workflow Status Daily Health Report
Story: ST-WORKFLOW-ARCHIVAL-001

Generates daily health metrics for workflow status archival system.
Returns JSON with health metrics for monitoring and alerting.

Usage:
    python scripts/workflow/daily_health_report.py
    python scripts/workflow/daily_health_report.py --verbose
    python scripts/workflow/daily_health_report.py --json
    python scripts/workflow/daily_health_report.py --notify

Exit Codes:
    0 - Health check passed (no critical issues)
    1 - Health check found issues (warnings only)
    2 - Health check found critical issues
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yaml

# Configuration
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_ENTRIES_DIR = Path("docs/archives/workflow-status/entries")
VERIFY_SCRIPT = Path("scripts/workflow/migration/verify_archive.py")
NOTIFIER_SCRIPT = Path("scripts/notifications/discord_workflow_notifier.py")

HEALTH_REPORT_VERSION = "1.0.0"

# Health thresholds
ORPHAN_AGE_DAYS = 7  # Archives older than this without workflow entry are orphaned
MAX_INTEGRITY_FAILURES = 0  # Any integrity failure is critical
WARNING_ARCHIVE_RATIO = 0.8  # Warn if archived/active ratio exceeds this


class HealthMetric:
    """Represents a single health metric."""

    def __init__(
        self, name: str, value: Any, unit: str = "", threshold: Any | None = None
    ):
        self.name = name
        self.value = value
        self.unit = unit
        self.threshold = threshold
        self.status = "ok"  # ok, warning, critical

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "threshold": self.threshold,
            "status": self.status,
        }


class HealthReport:
    """Aggregates all health metrics and status."""

    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        self.version = HEALTH_REPORT_VERSION
        self.metrics: list[HealthMetric] = []
        self.issues: list[dict] = []
        self.summary = {
            "total_stories": 0,
            "archived_stories": 0,
            "active_stories": 0,
            "orphaned_archives": 0,
            "integrity_failures": 0,
            "overall_status": "healthy",  # healthy, degraded, critical
        }

    def add_metric(self, metric: HealthMetric):
        self.metrics.append(metric)

    def add_issue(
        self,
        severity: str,
        category: str,
        description: str,
        details: dict | None = None,
    ):
        self.issues.append(
            {
                "severity": severity,
                "category": category,
                "description": description,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            }
        )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "metrics": [m.to_dict() for m in self.metrics],
            "issues": self.issues,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def print_report(self, verbose: bool = False):
        """Print human-readable health report."""
        print("=" * 80)
        print("WORKFLOW STATUS DAILY HEALTH REPORT")
        print("=" * 80)
        print(f"Version: {self.version}")
        print(f"Timestamp: {self.timestamp}")
        print()

        print("SUMMARY:")
        print(f"  Overall Status: {self.summary['overall_status'].upper()}")
        print(f"  Total Stories: {self.summary['total_stories']}")
        print(f"  Archived Stories: {self.summary['archived_stories']}")
        print(f"  Active Stories: {self.summary['active_stories']}")
        print(f"  Orphaned Archives: {self.summary['orphaned_archives']}")
        print(f"  Integrity Failures: {self.summary['integrity_failures']}")
        print()

        if self.metrics:
            print("METRICS:")
            for metric in self.metrics:
                status_icon = (
                    "✓"
                    if metric.status == "ok"
                    else "⚠" if metric.status == "warning" else "✗"
                )
                threshold_str = (
                    f" (threshold: {metric.threshold})" if metric.threshold else ""
                )
                print(
                    f"  {status_icon} {metric.name}: {metric.value}{metric.unit}{threshold_str}"
                )
            print()

        if self.issues:
            print("ISSUES:")
            for issue in self.issues:
                severity_icon = "⚠" if issue["severity"] == "warning" else "✗"
                print(
                    f"  {severity_icon} [{issue['severity'].upper()}] {issue['category']}"
                )
                print(f"     {issue['description']}")
                if verbose and issue["details"]:
                    for key, value in issue["details"].items():
                        print(f"     {key}: {value}")
            print()

        print("=" * 80)
        if self.summary["overall_status"] == "healthy":
            print("STATUS: ✓ HEALTHY - No issues detected")
        elif self.summary["overall_status"] == "degraded":
            print("STATUS: ⚠ DEGRADED - Warnings present, no critical issues")
        else:
            print("STATUS: ✗ CRITICAL - Critical issues require attention")
        print("=" * 80)


def count_stories(workflow_data: dict) -> tuple[int, int, int]:
    """
    Count total, archived, and active stories.

    Returns:
        (total, archived, active)
    """
    total = 0
    archived = 0
    active = 0

    sections = ["completed", "backlog", "launch_stories"]

    for section in sections:
        if section not in workflow_data:
            continue

        for story in workflow_data[section]:
            total += 1
            if story.get("status") == "archived" or story.get("archive_ref"):
                archived += 1
            else:
                active += 1

    return total, archived, active


def check_orphaned_archives(workflow_data: dict) -> tuple[int, list[dict]]:
    """
    Check for orphaned archives (no corresponding workflow entry).

    Returns:
        (orphan_count, orphan_details)
    """
    if not ARCHIVE_ENTRIES_DIR.exists():
        return 0, []

    # Build set of story IDs in workflow
    workflow_story_ids = set()
    sections = ["completed", "backlog", "launch_stories"]

    for section in sections:
        if section not in workflow_data:
            continue
        for story in workflow_data[section]:
            story_id = story.get("id")
            if story_id:
                workflow_story_ids.add(story_id)

    # Check each archive file
    orphans = []

    for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
        with open(archive_file) as f:
            archive_entry = yaml.safe_load(f)

        story_id = archive_entry.get("original_story_id")

        # Check if story exists in workflow
        if story_id not in workflow_story_ids:
            # Check archive age
            archived_at = archive_entry.get("archived_at", "")
            try:
                archive_date = datetime.fromisoformat(
                    archived_at.replace("Z", "+00:00")
                )
                age_days = (
                    datetime.now(timezone.utc) - archive_date.replace(tzinfo=None)
                ).days

                if age_days > ORPHAN_AGE_DAYS:
                    orphans.append(
                        {
                            "archive_ref": archive_entry.get("archive_ref"),
                            "story_id": story_id,
                            "archived_at": archived_at,
                            "age_days": age_days,
                        }
                    )
            except Exception:
                # If we can't parse date, consider it potentially orphaned
                orphans.append(
                    {
                        "archive_ref": archive_entry.get("archive_ref"),
                        "story_id": story_id,
                        "archived_at": archived_at,
                        "age_days": -1,
                    }
                )

    return len(orphans), orphans


def check_archive_integrity() -> tuple[int, int, list[dict]]:
    """
    Check archive integrity using verify_archive.py.

    Returns:
        (total, failed, failures_details)
    """
    try:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT), "--all", "--json"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0 and not result.stdout:
            return 0, 0, []

        # Parse JSON output
        try:
            verify_results = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Try to parse from mixed output
            lines = result.stdout.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)
            if json_lines:
                verify_results = json.loads("\n".join(json_lines))
            else:
                return 0, 0, []

        total = verify_results.get("total", 0)
        failed = verify_results.get("failed", 0)

        failures = []
        for entry in verify_results.get("entries", []):
            if not entry.get("overall_passed", True):
                failures.append(
                    {
                        "archive_ref": entry.get("archive_ref"),
                        "story_id": entry.get("story_id"),
                        "integrity_passed": entry.get("integrity_passed", False),
                        "no_data_loss_passed": entry.get("no_data_loss_passed", False),
                    }
                )

        return total, failed, failures

    except subprocess.TimeoutExpired:
        return 0, 0, [{"error": "Integrity check timed out"}]
    except Exception as e:
        return 0, 0, [{"error": str(e)}]


def calculate_archive_size_metrics() -> dict:
    """Calculate archive size metrics."""
    metrics = {
        "total_archives": 0,
        "total_size_bytes": 0,
        "total_size_mb": 0,
        "avg_size_bytes": 0,
        "largest_archive": None,
        "smallest_archive": None,
    }

    if not ARCHIVE_ENTRIES_DIR.exists():
        return metrics

    sizes = []
    largest = None
    smallest = None

    for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
        size = archive_file.stat().st_size
        sizes.append(size)

        if largest is None or size > largest["size"]:
            largest = {"ref": archive_file.stem, "size": size}
        if smallest is None or size < smallest["size"]:
            smallest = {"ref": archive_file.stem, "size": size}

    if sizes:
        metrics["total_archives"] = len(sizes)
        metrics["total_size_bytes"] = sum(sizes)
        metrics["total_size_mb"] = round(sum(sizes) / (1024 * 1024), 2)
        metrics["avg_size_bytes"] = round(sum(sizes) / len(sizes))
        metrics["largest_archive"] = largest
        metrics["smallest_archive"] = smallest

    return metrics


def generate_health_report(verbose: bool = False) -> HealthReport:
    """Generate complete health report."""
    report = HealthReport()

    # Load workflow status
    with open(WORKFLOW_STATUS_PATH) as f:
        workflow_data = yaml.safe_load(f)

    # Count stories
    total, archived, active = count_stories(workflow_data)
    report.summary["total_stories"] = total
    report.summary["archived_stories"] = archived
    report.summary["active_stories"] = active

    # Add metrics
    report.add_metric(HealthMetric("total_stories", total, "stories"))
    report.add_metric(HealthMetric("archived_stories", archived, "stories"))
    report.add_metric(HealthMetric("active_stories", active, "stories"))

    # Archive ratio
    if total > 0:
        archive_ratio = archived / total
        ratio_metric = HealthMetric(
            "archive_ratio",
            round(archive_ratio * 100, 1),
            "%",
            WARNING_ARCHIVE_RATIO * 100,
        )
        if archive_ratio > WARNING_ARCHIVE_RATIO:
            ratio_metric.status = "warning"
            report.add_issue(
                severity="warning",
                category="archive_ratio",
                description=f"Archive ratio ({archive_ratio:.1%}) exceeds threshold ({WARNING_ARCHIVE_RATIO:.1%})",
                details={"ratio": archive_ratio, "threshold": WARNING_ARCHIVE_RATIO},
            )
        report.add_metric(ratio_metric)

    # Check for orphaned archives
    orphan_count, orphans = check_orphaned_archives(workflow_data)
    report.summary["orphaned_archives"] = orphan_count
    report.add_metric(HealthMetric("orphaned_archives", orphan_count, "archives"))

    if orphan_count > 0:
        report.add_issue(
            severity="warning",
            category="orphaned_archives",
            description=f"Found {orphan_count} orphaned archives (no workflow entry)",
            details={"orphans": orphans[:5]},  # First 5
        )

    # Check archive integrity
    total_archives, failed_integrity, failures = check_archive_integrity()
    report.summary["integrity_failures"] = failed_integrity
    report.add_metric(
        HealthMetric("total_archives_checked", total_archives, "archives")
    )
    report.add_metric(
        HealthMetric(
            "integrity_failures", failed_integrity, "archives", MAX_INTEGRITY_FAILURES
        )
    )

    if failed_integrity > 0:
        report.add_issue(
            severity="critical",
            category="integrity_failure",
            description=f"Found {failed_integrity} archives with integrity failures",
            details={"failures": failures},
        )

    # Archive size metrics
    size_metrics = calculate_archive_size_metrics()
    report.add_metric(
        HealthMetric("total_archive_size_mb", size_metrics["total_size_mb"], "MB")
    )
    report.add_metric(
        HealthMetric("avg_archive_size_bytes", size_metrics["avg_size_bytes"], "bytes")
    )

    # Determine overall status
    has_critical = any(issue["severity"] == "critical" for issue in report.issues)
    has_warnings = any(issue["severity"] == "warning" for issue in report.issues)

    if has_critical:
        report.summary["overall_status"] = "critical"
    elif has_warnings:
        report.summary["overall_status"] = "degraded"
    else:
        report.summary["overall_status"] = "healthy"

    return report


def send_health_notification(
    report: HealthReport, webhook_url: str | None = None
) -> bool:
    """Send health report notification."""
    if not NOTIFIER_SCRIPT.exists():
        return False

    # Determine notification level
    if report.summary["overall_status"] == "critical":
        level = "CRITICAL"
    elif report.summary["overall_status"] == "degraded":
        level = "WARNING"
    else:
        level = "INFO"

    # Build message
    title = f"Daily Health Report - {report.summary['overall_status'].upper()}"
    message = (
        f"Total: {report.summary['total_stories']} stories | "
        f"Archived: {report.summary['archived_stories']} | "
        f"Active: {report.summary['active_stories']} | "
        f"Orphans: {report.summary['orphaned_archives']} | "
        f"Integrity Failures: {report.summary['integrity_failures']}"
    )

    cmd = [
        "python3",
        str(NOTIFIER_SCRIPT),
        "--level",
        level,
        "--title",
        title,
        "--message",
        message,
    ]

    if webhook_url:
        cmd.extend(["--webhook-url", webhook_url])

    # Suppress notifications if healthy and no issues
    if report.summary["overall_status"] == "healthy" and not report.issues:
        cmd.append("--suppress-if-healthy")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Daily health report for workflow status archival system"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Discord notification",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help="Discord webhook URL (or set DISCORD_WEBHOOK_URL env var)",
    )

    args = parser.parse_args()

    # Generate health report
    report = generate_health_report(verbose=args.verbose)

    # Send notification if requested
    if args.notify:
        webhook = args.webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
        if webhook:
            send_health_notification(report, webhook)

    # Output report
    if args.json:
        print(report.to_json())
    else:
        report.print_report(verbose=args.verbose)

    # Exit with appropriate code
    if report.summary["overall_status"] == "critical":
        return 2
    elif report.summary["overall_status"] == "degraded":
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
