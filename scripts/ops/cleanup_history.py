#!/usr/bin/env python3
"""
Query cleanup history and generate reports from Redis.

Usage:
    python3 scripts/ops/cleanup_history.py --last 7
    python3 scripts/ops/cleanup_history.py --sprint SPRINT-2026-Q1-01
    python3 scripts/ops/cleanup_history.py --trend 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Redis import with fallback
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: redis not available", file=sys.stderr)


# Redis key patterns
REDIS_CLEANUP_LOG = "bmad:chiseai:sprint_cleanup:log"
REDIS_CLEANUP_SUMMARY = "bmad:chiseai:sprint_cleanup:summary"
REDIS_SPRINT_BOUNDARY = "bmad:chiseai:sprint:boundary"


class CleanupHistory:
    """Query and report on cleanup history."""

    def __init__(self):
        self.client: Optional[Any] = None
        self.host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
        self.port = int(os.getenv("CHISE_REDIS_PORT", "6380"))
        self.db = int(os.getenv("CHISE_REDIS_DB", "0"))
        self._connect()

    def _connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            return False

        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            return self.client.ping()
        except Exception as e:
            print(f"Redis connection failed: {e}", file=sys.stderr)
            return False

    def get_recent_logs(self, count: int = 50) -> list[dict]:
        """Get recent cleanup log entries."""
        if not self.client:
            return []

        try:
            entries = self.client.lrange(REDIS_CLEANUP_LOG, 0, count - 1)
            return [json.loads(e) for e in entries if e]
        except Exception as e:
            print(f"Failed to get logs: {e}", file=sys.stderr)
            return []

    def get_sprint_boundaries(self, count: int = 10) -> list[dict]:
        """Get recent sprint boundaries."""
        if not self.client:
            return []

        try:
            entries = self.client.lrange(REDIS_SPRINT_BOUNDARY, 0, count - 1)
            return [json.loads(e) for e in entries if e]
        except Exception as e:
            print(f"Failed to get sprint boundaries: {e}", file=sys.stderr)
            return []

    def get_daily_summaries(self, days: int = 30) -> list[dict]:
        """Get daily cleanup summaries."""
        if not self.client:
            return []

        summaries = []
        today = datetime.now(timezone.utc)

        for i in range(days):
            date = today - timedelta(days=i)
            date_key = date.strftime("%Y-%m-%d")
            key = f"{REDIS_CLEANUP_SUMMARY}:{date_key}"

            try:
                data = self.client.hget(key, "report")
                if data:
                    summary = json.loads(data)
                    summary["date"] = date_key
                    summaries.append(summary)
            except Exception:
                pass

        return summaries

    def generate_trend_report(self, days: int = 30) -> str:
        """Generate a trend report over time."""
        summaries = self.get_daily_summaries(days)

        if not summaries:
            return f"No cleanup data available for the last {days} days."

        lines = []
        lines.append("=" * 60)
        lines.append(f"CLEANUP TREND REPORT - Last {days} Days")
        lines.append("=" * 60)
        lines.append("")

        # Calculate statistics
        total_cleanups = len(summaries)
        critical_issues = sum(s.get("critical_count", 0) for s in summaries)
        warning_issues = sum(s.get("warning_count", 0) for s in summaries)
        total_actions = sum(s.get("actions_taken", 0) for s in summaries)

        # Find days with critical issues
        critical_days = [s["date"] for s in summaries if s.get("critical_count", 0) > 0]

        lines.append("STATISTICS")
        lines.append("-" * 40)
        lines.append(f"Total cleanups: {total_cleanups}")
        lines.append(f"Critical issues: {critical_issues}")
        lines.append(f"Warning issues: {warning_issues}")
        lines.append(f"Auto-fix actions: {total_actions}")
        lines.append(f"Days with critical issues: {len(critical_days)}")
        lines.append("")

        if critical_days:
            lines.append("DAYS WITH CRITICAL ISSUES")
            lines.append("-" * 40)
            for date in critical_days[:10]:  # Show first 10
                lines.append(f"  - {date}")
            lines.append("")

        # Daily breakdown
        lines.append("DAILY BREAKDOWN (Last 14 Days)")
        lines.append("-" * 40)
        lines.append(f"{'Date':<12} {'Critical':<10} {'Warnings':<10} {'Actions':<10}")
        lines.append("-" * 42)

        for summary in summaries[:14]:
            date = summary.get("date", "N/A")
            critical = summary.get("critical_count", 0)
            warnings = summary.get("warning_count", 0)
            actions = summary.get("actions_taken", 0)
            lines.append(f"{date:<12} {critical:<10} {warnings:<10} {actions:<10}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def generate_sprint_report(self, sprint_id: str) -> str:
        """Generate report for a specific sprint."""
        boundaries = self.get_sprint_boundaries(count=50)

        # Find the sprint
        sprint_start = None
        sprint_end = None

        for i, boundary in enumerate(boundaries):
            if boundary.get("sprint_id") == sprint_id:
                sprint_start = boundary
                # Try to find the end (next sprint or now)
                if i > 0:
                    sprint_end = boundaries[i - 1]
                break

        if not sprint_start:
            return f"Sprint '{sprint_id}' not found in history."

        lines = []
        lines.append("=" * 60)
        lines.append(f"SPRINT REPORT: {sprint_id}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Start Date: {sprint_start.get('started_at', 'N/A')}")
        lines.append(f"Initial State: {sprint_start.get('repository_state', 'N/A')}")
        lines.append(
            f"Critical Issues at Start: {sprint_start.get('issues_critical', 0)}"
        )
        lines.append(f"Warnings at Start: {sprint_start.get('issues_warning', 0)}")

        if sprint_end:
            lines.append(f"\nEnd Date: {sprint_end.get('started_at', 'N/A')}")
            lines.append(
                f"Duration: {self._calculate_duration(sprint_start, sprint_end)}"
            )

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _calculate_duration(self, start: dict, end: dict) -> str:
        """Calculate duration between two sprint boundaries."""
        try:
            start_time = datetime.fromisoformat(
                start.get("started_at", "").replace("Z", "+00:00")
            )
            end_time = datetime.fromisoformat(
                end.get("started_at", "").replace("Z", "+00:00")
            )
            duration = end_time - start_time
            return f"{duration.days} days, {duration.seconds // 3600} hours"
        except (ValueError, TypeError):
            return "Unknown"

    def export_to_json(self, output_file: str, days: int = 30) -> bool:
        """Export cleanup history to JSON file."""
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sprint_boundaries": self.get_sprint_boundaries(count=50),
            "daily_summaries": self.get_daily_summaries(days=days),
            "recent_logs": self.get_recent_logs(count=100),
        }

        try:
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to export: {e}", file=sys.stderr)
            return False


def main():
    """Main entry point."""
    # Bootstrap environment first
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Query ChiseAI cleanup history from Redis"
    )

    parser.add_argument(
        "--last", type=int, metavar="N", help="Show last N cleanup log entries"
    )
    parser.add_argument(
        "--sprint", metavar="SPRINT_ID", help="Show report for specific sprint"
    )
    parser.add_argument(
        "--trend",
        type=int,
        metavar="DAYS",
        help="Generate trend report for last N days",
    )
    parser.add_argument(
        "--boundaries", action="store_true", help="Show recent sprint boundaries"
    )
    parser.add_argument("--export", metavar="FILE", help="Export history to JSON file")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to include in export (default: 30)",
    )

    args = parser.parse_args()

    history = CleanupHistory()

    if not history.client:
        print("Error: Redis not available. Cannot query history.", file=sys.stderr)
        return 1

    if args.last:
        logs = history.get_recent_logs(args.last)
        print(f"Recent {len(logs)} cleanup log entries:")
        print("-" * 60)
        for log in logs:
            print(f"[{log.get('timestamp', 'N/A')}] {log.get('action', 'N/A')}")
            details = log.get("details", "{}")
            if details and details != "{}":
                print(f"  Details: {details}")

    elif args.sprint:
        print(history.generate_sprint_report(args.sprint))

    elif args.trend:
        print(history.generate_trend_report(args.trend))

    elif args.boundaries:
        boundaries = history.get_sprint_boundaries()
        print(f"Recent {len(boundaries)} sprint boundaries:")
        print("-" * 60)
        for boundary in boundaries:
            sprint_id = boundary.get("sprint_id", "N/A")
            started = boundary.get("started_at", "N/A")
            state = boundary.get("repository_state", "N/A")
            print(f"[{started}] {sprint_id} - {state}")

    elif args.export:
        if history.export_to_json(args.export, args.days):
            print(f"Exported cleanup history to: {args.export}")
        else:
            return 1

    else:
        # Default: show trend for last 14 days
        print(history.generate_trend_report(14))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
