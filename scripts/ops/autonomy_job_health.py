#!/usr/bin/env python3
"""Autonomy job health diagnostic tool.

Query and display job state from autonomy cadence controller output.
Provides quick diagnostics for job health, trends, and alerts.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("_bmad-output") / "autonomy-cadence"
STATE_PATH = DEFAULT_OUTPUT_DIR / "state.json"
RUNS_PATH = DEFAULT_OUTPUT_DIR / "runs.jsonl"


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d {hours}h"


def format_age_human(timestamp_str: str | None) -> str:
    """Format the age of a timestamp as human-readable string."""
    if not timestamp_str:
        return "never"
    dt = parse_iso(timestamp_str)
    if not dt:
        return "invalid"
    age_seconds = int((now_utc() - dt).total_seconds())
    return f"{format_duration(age_seconds)} ago"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"jobs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("jobs", {})
            return data
    except Exception:
        pass
    return {"jobs": {}}


def load_runs(
    path: Path, job_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Load run history from runs.jsonl, optionally filtered by job_id."""
    runs: list[dict[str, Any]] = []
    if not path.exists():
        return runs

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    run = json.loads(line)
                    if job_id is None or run.get("job_id") == job_id:
                        runs.append(run)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    # Return most recent runs first, limited to limit
    return runs[-limit:][::-1]


def get_job_trends(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate job health trends from run history."""
    if not runs:
        return {
            "total_runs": 0,
            "success_rate": 0.0,
            "avg_duration": 0.0,
            "status_breakdown": {},
        }

    total = len(runs)
    successes = sum(1 for r in runs if r.get("status") == "success")
    durations = [
        r.get("duration_seconds", 0) for r in runs if r.get("duration_seconds")
    ]

    status_breakdown: dict[str, int] = {}
    for run in runs:
        status = run.get("status", "unknown")
        status_breakdown[status] = status_breakdown.get(status, 0) + 1

    return {
        "total_runs": total,
        "success_rate": round(successes / total * 100, 1) if total > 0 else 0.0,
        "avg_duration": round(sum(durations) / len(durations), 2) if durations else 0.0,
        "status_breakdown": status_breakdown,
    }


def calculate_health_score(
    job_state: dict[str, Any], cadence: str | None = None
) -> tuple[int, str]:
    """Calculate job health score (0-100) and status."""
    score = 100
    last_status = job_state.get("last_status", "unknown")

    if last_status == "success":
        pass
    elif last_status in ("failed", "timeout"):
        score -= 30
    elif last_status == "awaiting_approval":
        score -= 10
    else:
        score -= 5

    # Check cadence adherence if we have cadence info
    if cadence and cadence != "event":
        last_success = parse_iso(job_state.get("last_success_at"))
        if last_success:
            # Parse cadence
            interval = None
            normalized = cadence.strip().lower()
            if normalized == "daily":
                interval = 24 * 3600
            elif normalized == "weekly":
                interval = 7 * 24 * 3600
            elif normalized == "6h":
                interval = 6 * 3600
            elif normalized.endswith("h") and normalized[:-1].isdigit():
                interval = int(normalized[:-1]) * 3600

            if interval:
                age = (now_utc() - last_success).total_seconds()
                if age > interval * 1.5:
                    score -= 40
                elif age > interval:
                    score -= 20

    score = max(0, min(100, score))

    if score >= 80:
        status = "healthy"
    elif score >= 50:
        status = "degraded"
    else:
        status = "critical"

    return score, status


def needs_attention(job_state: dict[str, Any]) -> bool:
    """Check if a job needs attention based on its state."""
    last_status = job_state.get("last_status", "")
    if last_status in ("failed", "timeout", "awaiting_approval"):
        return True
    if last_status != "success":
        return True

    # Check if we have a recent success
    last_success = parse_iso(job_state.get("last_success_at"))
    return bool(not last_success)


def display_table(jobs_data: list[dict[str, Any]]) -> None:
    """Display job data in table format."""
    # Header
    print(
        f"{'Job ID':<35} {'Status':<12} {'Last Success':<18} {'Health':<10} {'Idempotency Key':<30}"
    )
    print("-" * 110)

    for job in jobs_data:
        job_id = job.get("job_id", "unknown")[:34]
        status = job.get("last_status", "unknown")[:11]
        last_success = format_age_human(job.get("last_success_at"))[:17]
        health = f"{job.get('health_score', 0)}/100 ({job.get('health_status', 'unknown')[:3]})"
        idem = (job.get("idempotency_key") or "-")[:29]

        print(f"{job_id:<35} {status:<12} {last_success:<18} {health:<10} {idem:<30}")


def display_json(jobs_data: list[dict[str, Any]]) -> None:
    """Display job data in JSON format."""
    print(json.dumps(jobs_data, indent=2))


def display_summary(jobs_data: list[dict[str, Any]]) -> None:
    """Display summary statistics."""
    total = len(jobs_data)
    if total == 0:
        print("No jobs found.")
        return

    healthy = sum(1 for j in jobs_data if j.get("health_status") == "healthy")
    degraded = sum(1 for j in jobs_data if j.get("health_status") == "degraded")
    critical = sum(1 for j in jobs_data if j.get("health_status") == "critical")
    needs_attn = sum(1 for j in jobs_data if j.get("needs_attention"))

    status_counts: dict[str, int] = {}
    for job in jobs_data:
        status = job.get("last_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"Total Jobs: {total}")
    print(
        f"Health: 🟢 {healthy} healthy | 🟡 {degraded} degraded | 🔴 {critical} critical"
    )
    print(f"Need Attention: {needs_attn}")
    print("\nStatus Breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


def display_job_details(job: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    """Display detailed information for a single job."""
    print(f"Job ID: {job.get('job_id', 'unknown')}")
    print(f"Status: {job.get('last_status', 'unknown')}")
    print(
        f"Health Score: {job.get('health_score', 0)}/100 ({job.get('health_status', 'unknown')})"
    )
    print(f"Needs Attention: {'Yes' if job.get('needs_attention') else 'No'}")
    print()

    print("Timestamps:")
    print(
        f"  Last Started: {job.get('last_started_at', 'never')} ({format_age_human(job.get('last_started_at'))})"
    )
    print(
        f"  Last Success: {job.get('last_success_at', 'never')} ({format_age_human(job.get('last_success_at'))})"
    )
    print(f"  Updated: {job.get('updated_at', 'never')}")
    print()

    print(f"Idempotency Key: {job.get('idempotency_key') or 'None'}")
    print(f"Duration (last): {job.get('last_duration_seconds', 'N/A')}s")
    print(f"Exit Code (last): {job.get('last_exit_code', 'N/A')}")
    print()

    if job.get("last_error"):
        print("Last Error:")
        error = job.get("last_error", "")
        # Show last 3 lines of error
        error_lines = error.strip().split("\n")[-3:]
        for line in error_lines:
            print(f"  {line}")
        print()

    if runs:
        print("Recent Runs:")
        trends = get_job_trends(runs)
        print(f"  Total runs (sampled): {trends['total_runs']}")
        print(f"  Success rate: {trends['success_rate']}%")
        print(f"  Avg duration: {trends['avg_duration']}s")
        print(f"  Status breakdown: {trends['status_breakdown']}")
        print()

        print("Last 5 Runs:")
        for run in runs[:5]:
            ts = run.get("timestamp_utc", "unknown")
            status = run.get("status", "unknown")
            duration = run.get("duration_seconds", "N/A")
            print(f"  {ts} | {status:12} | {duration}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomy job health diagnostic tool")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Path to autonomy cadence output directory",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        help="Filter to a specific job ID",
    )
    parser.add_argument(
        "--status",
        type=str,
        help="Filter by status (success, failed, timeout, awaiting_approval, etc.)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "summary"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Show only jobs needing attention",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor and refresh",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=5,
        help="Seconds between refreshes in watch mode (default: 5)",
    )
    parser.add_argument(
        "--trend-limit",
        type=int,
        default=50,
        help="Number of runs to analyze for trends (default: 50)",
    )
    args = parser.parse_args()

    state_path = args.output_dir / "state.json"
    runs_path = args.output_dir / "runs.jsonl"

    def refresh() -> list[dict[str, Any]]:
        state = load_state(state_path)
        jobs_state = state.get("jobs", {})

        jobs_data: list[dict[str, Any]] = []
        for job_id, job_state in jobs_state.items():
            # Apply filters
            if args.job_id and job_id != args.job_id:
                continue
            if args.status and job_state.get("last_status") != args.status:
                continue
            if args.alert and not needs_attention(job_state):
                continue

            # Calculate health
            score, health_status = calculate_health_score(job_state)

            job_data = {
                "job_id": job_id,
                "last_started_at": job_state.get("last_started_at"),
                "last_success_at": job_state.get("last_success_at"),
                "last_status": job_state.get("last_status", "unknown"),
                "idempotency_key": job_state.get("last_idempotency_key"),
                "last_duration_seconds": job_state.get("last_duration_seconds"),
                "last_exit_code": job_state.get("last_exit_code"),
                "last_error": job_state.get("last_error"),
                "updated_at": job_state.get("updated_at"),
                "health_score": score,
                "health_status": health_status,
                "needs_attention": needs_attention(job_state),
            }

            # Add trend data if showing details for single job
            if args.job_id:
                runs = load_runs(runs_path, job_id, limit=args.trend_limit)
                job_data["trends"] = get_job_trends(runs)
                job_data["recent_runs"] = runs[:10]

            jobs_data.append(job_data)

        return jobs_data

    if args.watch:
        try:
            while True:
                # Clear screen (cross-platform)
                print("\033[2J\033[H", end="")
                print(
                    f"Autonomy Job Health Monitor (refreshing every {args.watch_interval}s)"
                )
                print(f"Output: {args.output_dir}")
                print("-" * 80)

                jobs_data = refresh()

                if args.job_id and len(jobs_data) == 1:
                    # Detailed view for single job
                    load_state(state_path)
                    runs = load_runs(runs_path, args.job_id, limit=args.trend_limit)
                    display_job_details(jobs_data[0], runs)
                elif args.format == "table":
                    display_table(jobs_data)
                elif args.format == "json":
                    display_json(jobs_data)
                else:
                    display_summary(jobs_data)

                print(f"\nLast updated: {now_utc().isoformat()}")
                print("Press Ctrl+C to exit")
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\nExiting...")
            return 0
    else:
        jobs_data = refresh()

        if not jobs_data:
            print("No jobs found matching criteria.")
            return 0

        if args.job_id and len(jobs_data) == 1:
            # Detailed view for single job
            runs = load_runs(runs_path, args.job_id, limit=args.trend_limit)
            display_job_details(jobs_data[0], runs)
        elif args.format == "table":
            display_table(jobs_data)
        elif args.format == "json":
            display_json(jobs_data)
        else:
            display_summary(jobs_data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
