#!/usr/bin/env python3
"""
Tempmemory Migration CLI Script for ChiseAI.

Migrates temporary memory files from docs/tempmemories/ to Redis and Qdrant.

Usage:
    python3 scripts/ops/tempmemory_migration.py --dry-run
    python3 scripts/ops/tempmemory_migration.py --migrate
    python3 scripts/ops/tempmemory_migration.py --status
    python3 scripts/ops/tempmemory_migration.py --report

This script is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory import (
    TempmemoryMigrationEngine,
    TempmemoryTracker,
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

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
        )
        client.ping()
        logger.info("Redis client connected")
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def create_qdrant_client() -> Any | None:
    """Create Qdrant client if available."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            host="host.docker.internal",
            port=6334,
        )
        logger.info("Qdrant client connected")
        return client
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return None


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Run migration in dry-run mode."""
    logger.info("Starting dry-run migration")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    engine = TempmemoryMigrationEngine(
        redis_client=redis_client,
        qdrant_client=qdrant_client,
        dry_run=True,
    )

    report = engine.run_migration()

    print(f"\n{'=' * 60}")
    print("Dry-Run Migration Report")
    print(f"{'=' * 60}")
    print(f"Total files scanned: {report.total_files}")
    print(f"Would migrate: {report.migrated_files}")
    print(f"Would fail: {report.failed_files}")
    print(f"Would skip: {report.skipped_files}")
    print(f"Duration: {report.duration_seconds:.2f}s")
    print(f"{'=' * 60}\n")

    # Show sample of files that would be migrated
    if report.results:
        print("Sample files to migrate:")
        for result in report.results[:5]:
            print(f"  - {result.file_path} -> {result.target.value}")
        if len(report.results) > 5:
            print(f"  ... and {len(report.results) - 5} more")

    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run actual migration."""
    logger.info("Starting migration")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    if not redis_client and not qdrant_client:
        logger.error("Neither Redis nor Qdrant is available. Cannot proceed.")
        return 1

    engine = TempmemoryMigrationEngine(
        redis_client=redis_client,
        qdrant_client=qdrant_client,
        dry_run=False,
    )

    tracker = TempmemoryTracker(
        redis_client=redis_client,
        dry_run=False,
    )

    report = engine.run_migration()

    # Update tracking for each result
    for result in report.results:
        tracker.track_file(
            file_path=result.file_path,
            status=result.status,
        )

    print(f"\n{'=' * 60}")
    print("Migration Report")
    print(f"{'=' * 60}")
    print(f"Total files scanned: {report.total_files}")
    print(f"Successfully migrated: {report.migrated_files}")
    print(f"Failed: {report.failed_files}")
    print(f"Skipped: {report.skipped_files}")
    print(f"Duration: {report.duration_seconds:.2f}s")
    print(f"{'=' * 60}\n")

    # Save report to file
    if args.output:
        with open(args.output, "w") as f:
            f.write(report.to_json())
        print(f"Report saved to: {args.output}")

    return 0 if report.failed_files == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Check migration status."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Redis not available - cannot check status")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)
    summary = tracker.get_summary()

    print(f"\n{'=' * 60}")
    print("Tempmemory Migration Status")
    print(f"{'=' * 60}")
    print(f"Total tracked files: {summary.total_tracked}")
    print(f"  Pending: {summary.pending_count}")
    print(f"  In Progress: {summary.in_progress_count}")
    print(f"  Completed: {summary.completed_count}")
    print(f"  Failed: {summary.failed_count}")
    print(f"  Skipped: {summary.skipped_count}")

    if summary.by_story:
        print("\nBy Story:")
        for story_id, count in sorted(summary.by_story.items()):
            print(f"  {story_id}: {count}")

    if summary.by_type:
        print("\nBy Type:")
        for memory_type, count in sorted(summary.by_type.items()):
            print(f"  {memory_type}: {count}")

    print(f"{'=' * 60}\n")

    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate detailed report."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Redis not available - cannot generate report")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client)

    from governance.tempmemory.tracking import TrackingReportType

    report_type = TrackingReportType(args.type)
    report = tracker.generate_report(report_type)

    print(json.dumps(report, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")

    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset tracking data."""
    redis_client = create_redis_client()

    if not redis_client:
        print("Redis not available - cannot reset")
        return 1

    tracker = TempmemoryTracker(redis_client=redis_client, dry_run=args.dry_run)

    if args.file:
        tracker.reset_tracking(args.file)
        print(f"Reset tracking for: {args.file}")
    else:
        if args.force:
            tracker.reset_tracking()
            print("Reset all tracking data")
        else:
            print("Use --force to reset all tracking data")
            return 1

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tempmemory Migration CLI for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be migrated
  python3 scripts/ops/tempmemory_migration.py --dry-run

  # Run actual migration
  python3 scripts/ops/tempmemory_migration.py --migrate

  # Check current status
  python3 scripts/ops/tempmemory_migration.py --status

  # Generate detailed report
  python3 scripts/ops/tempmemory_migration.py --report --type detailed

  # Reset tracking for a file
  python3 scripts/ops/tempmemory_migration.py --reset --file path/to/file.md
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making actual changes (default)",
    )

    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run actual migration",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Check migration status",
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
        "--reset",
        action="store_true",
        help="Reset tracking data",
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Specific file to reset (with --reset)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reset all (with --reset)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file for report",
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

    # Default to dry-run if no command specified
    if not any([args.migrate, args.status, args.report, args.reset]):
        args.dry_run = True

    # Route to appropriate command
    if args.reset:
        return cmd_reset(args)
    elif args.migrate:
        return cmd_migrate(args)
    elif args.status:
        return cmd_status(args)
    elif args.report:
        return cmd_report(args)
    else:
        return cmd_dry_run(args)


if __name__ == "__main__":
    sys.exit(main())
