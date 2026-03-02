#!/usr/bin/env python3
"""
Tempmemory Migration Tracker CLI for ChiseAI.

Provides commands to track and report on tempmemory migration status.

Usage:
    python3 scripts/ops/tempmemory_tracker.py --status
    python3 scripts/ops/tempmemory_tracker.py --report
    python3 scripts/ops/tempmemory_tracker.py --list-failed
    python3 scripts/ops/tempmemory_tracker.py --audit-log

This script is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory import (
    MigrationStatus,
    TempmemoryTracker,
    TrackingReportType,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_redis_client() -> Any | None:
    """Create Redis client if available."""
    try:
        import redis

        host = os.environ.get("REDIS_HOST", "host.docker.internal")
        port = int(os.environ.get("REDIS_PORT", "6380"))

        client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
        )
        client.ping()
        logger.info(f"Redis client connected to {host}:{port}")
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def cmd_status(args: argparse.Namespace) -> int:
    """Show migration status summary."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    summary = tracker.get_summary()

    print(f"\n{'=' * 60}")
    print("Tempmemory Migration Status")
    print(f"{'=' * 60}")
    print(f"Generated at: {summary.timestamp.isoformat()}")
    print(f"\nTotal tracked files: {summary.total_tracked}")
    print(f"\nBy Status:")
    print(f"  Pending:      {summary.pending_count}")
    print(f"  In Progress:  {summary.in_progress_count}")
    print(f"  Completed:    {summary.completed_count}")
    print(f"  Failed:       {summary.failed_count}")
    print(f"  Skipped:      {summary.skipped_count}")

    if summary.by_story:
        print(f"\nBy Story:")
        for story_id, count in sorted(summary.by_story.items()):
            print(f"  {story_id}: {count}")

    if summary.by_type:
        print(f"\nBy Type:")
        for memory_type, count in sorted(summary.by_type.items()):
            print(f"  {memory_type}: {count}")

    print(f"{'=' * 60}\n")

    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate detailed report."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    report_type = TrackingReportType(args.type)
    report = tracker.generate_report(report_type)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        # Pretty print
        print(f"\n{'=' * 60}")
        print(f"Migration Report - {report_type.value.upper()}")
        print(f"{'=' * 60}")
        print(f"Generated at: {report['generated_at']}")

        summary = report.get("summary", {})
        print(f"\nSummary:")
        print(f"  Total tracked: {summary.get('total_tracked', 0)}")
        print(f"  Completed: {summary.get('completed_count', 0)}")
        print(f"  Failed: {summary.get('failed_count', 0)}")
        print(f"  Pending: {summary.get('pending_count', 0)}")

        if "records" in report:
            print(f"\nRecords ({len(report['records'])}):")
            for record in report["records"][:10]:  # Show first 10
                print(f"\n  {record['file_path']}")
                print(f"    Status: {record['status']}")
                if record.get("story_id"):
                    print(f"    Story: {record['story_id']}")
                if record.get("error_message"):
                    print(f"    Error: {record['error_message']}")

        if "failed_files" in report:
            print(f"\nFailed Files ({len(report['failed_files'])}):")
            for f in report["failed_files"][:10]:
                print(f"\n  {f['file_path']}")
                print(f"    Error: {f.get('error_message', 'Unknown')}")
                print(f"    Attempts: {f.get('attempt_count', 0)}")

        if "pending_files" in report:
            print(f"\nPending Files ({len(report['pending_files'])}):")
            for f in report["pending_files"][:10]:
                print(f"  {f['file_path']}")

        print(f"\n{'=' * 60}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")

    return 0


def cmd_list_failed(args: argparse.Namespace) -> int:
    """List failed migrations."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    failed = tracker.get_files_by_status(MigrationStatus.FAILED)

    print(f"\n{'=' * 60}")
    print(f"Failed Migrations ({len(failed)})")
    print(f"{'=' * 60}")

    if not failed:
        print("No failed migrations found.")
    else:
        for record in failed:
            print(f"\n  {record.file_path}")
            print(f"    Story: {record.story_id or 'N/A'}")
            print(f"    Type: {record.memory_type or 'N/A'}")
            print(f"    Attempts: {record.attempt_count}")
            print(
                f"    Last Attempt: {record.last_attempt.isoformat() if record.last_attempt else 'N/A'}"
            )
            if record.error_message:
                print(f"    Error: {record.error_message}")

    print(f"\n{'=' * 60}\n")

    return 0


def cmd_list_pending(args: argparse.Namespace) -> int:
    """List pending migrations."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    pending = tracker.get_files_by_status(MigrationStatus.PENDING)

    print(f"\n{'=' * 60}")
    print(f"Pending Migrations ({len(pending)})")
    print(f"{'=' * 60}")

    if not pending:
        print("No pending migrations found.")
    else:
        for record in pending:
            print(f"\n  {record.file_path}")
            print(f"    Story: {record.story_id or 'N/A'}")
            print(f"    Type: {record.memory_type or 'N/A'}")

    print(f"\n{'=' * 60}\n")

    return 0


def cmd_audit_log(args: argparse.Namespace) -> int:
    """Show audit log."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    entries = tracker.get_audit_log(limit=args.limit)

    print(f"\n{'=' * 60}")
    print(f"Audit Log ({len(entries)} entries)")
    print(f"{'=' * 60}")

    if not entries:
        print("No audit entries found.")
    else:
        for entry in entries:
            print(f"\n  {entry.get('timestamp', 'Unknown')}")
            print(f"    File: {entry.get('file_path', 'Unknown')}")
            print(f"    Status: {entry.get('status', 'Unknown')}")
            if entry.get("error_message"):
                print(f"    Error: {entry['error_message']}")

    print(f"\n{'=' * 60}\n")

    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset tracking for a file or all files."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client, dry_run=args.dry_run)

    if args.file:
        if tracker.reset_tracking(args.file):
            print(f"Reset tracking for: {args.file}")
        else:
            print(f"Failed to reset tracking for: {args.file}")
            return 1
    elif args.all:
        if args.force:
            if tracker.reset_tracking():
                print("Reset all tracking data")
            else:
                print("Failed to reset tracking")
                return 1
        else:
            print("Use --force to reset all tracking data")
            return 1
    else:
        print("Use --file to reset specific file or --all --force to reset all")
        return 1

    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update status for a specific file."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Error: Redis not available")
        return 1

    if not args.file or not args.status:
        print("Usage: --update --file <path> --status <status>")
        return 1

    try:
        status = MigrationStatus(args.status)
    except ValueError:
        print(f"Invalid status: {args.status}")
        print(f"Valid statuses: {[s.value for s in MigrationStatus]}")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client, dry_run=args.dry_run)

    if tracker.track_file(
        file_path=args.file,
        status=status,
        story_id=args.story,
        error_message=args.error,
    ):
        print(f"Updated {args.file} -> {status.value}")
    else:
        print(f"Failed to update {args.file}")
        return 1

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tempmemory Migration Tracker CLI for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status summary
  python3 scripts/ops/tempmemory_tracker.py --status

  # Generate detailed report
  python3 scripts/ops/tempmemory_tracker.py --report --type detailed

  # List failed migrations
  python3 scripts/ops/tempmemory_tracker.py --list-failed

  # Show audit log
  python3 scripts/ops/tempmemory_tracker.py --audit-log --limit 50

  # Update status for a file
  python3 scripts/ops/tempmemory_tracker.py --update --file path/to/file.md --status completed

  # Reset tracking for a file
  python3 scripts/ops/tempmemory_tracker.py --reset --file path/to/file.md
        """,
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status summary",
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate detailed report",
    )

    parser.add_argument(
        "--type",
        choices=["summary", "detailed", "failed_only", "pending_only"],
        default="summary",
        help="Report type (default: summary)",
    )

    parser.add_argument(
        "--list-failed",
        action="store_true",
        help="List failed migrations",
    )

    parser.add_argument(
        "--list-pending",
        action="store_true",
        help="List pending migrations",
    )

    parser.add_argument(
        "--audit-log",
        action="store_true",
        help="Show audit log",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit for audit log entries (default: 100)",
    )

    parser.add_argument(
        "--update",
        action="store_true",
        help="Update status for a file",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset tracking",
    )

    parser.add_argument(
        "--file",
        type=str,
        help="File path (for --update or --reset)",
    )

    parser.add_argument(
        "--status-value",
        dest="status",
        type=str,
        help="New status (for --update)",
    )

    parser.add_argument(
        "--story",
        type=str,
        help="Story ID (for --update)",
    )

    parser.add_argument(
        "--error",
        type=str,
        help="Error message (for --update)",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Reset all (for --reset)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reset all (for --reset --all)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file for report",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making actual changes",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Route to appropriate command
    if args.update:
        return cmd_update(args)
    elif args.reset:
        return cmd_reset(args)
    elif args.list_failed:
        return cmd_list_failed(args)
    elif args.list_pending:
        return cmd_list_pending(args)
    elif args.audit_log:
        return cmd_audit_log(args)
    elif args.report:
        return cmd_report(args)
    else:
        return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
