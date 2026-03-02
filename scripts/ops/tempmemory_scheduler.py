#!/usr/bin/env python3
"""
Tempmemory Migration Scheduler for ChiseAI.

Provides Docker-based scheduling for tempmemory migration operations.
Runs as a long-lived process within a Docker container with cron-like scheduling.

Usage:
    python3 scripts/ops/tempmemory_scheduler.py --run
    python3 scripts/ops/tempmemory_scheduler.py --test
    python3 scripts/ops/tempmemory_scheduler.py --once

This script is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).

Docker Usage:
    docker run --network chiseai \
        -v /path/to/chiseai:/app \
        -e REDIS_HOST=chiseai-redis \
        -e SCHEDULE_INTERVAL=daily \
        chiseai-tempmemory-scheduler
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory import (
    TempmemoryArchiveReconciler,
    TempmemoryMigrationEngine,
    TempmemoryTracker,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key for scheduler state
SCHEDULER_STATE_KEY = "bmad:chiseai:tempmemory:scheduler:state"
SCHEDULER_LOCK_KEY = "bmad:chiseai:tempmemory:scheduler:lock"


class ScheduleInterval:
    """Schedule interval definitions."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class TempmemoryScheduler:
    """
    Docker-based scheduler for tempmemory migration.

    Runs as a long-lived process with configurable intervals.
    Uses Redis for coordination and state management.
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        interval: str = ScheduleInterval.DAILY,
        dry_run: bool = True,
    ):
        """
        Initialize the scheduler.

        Args:
            redis_client: Optional Redis client.
            interval: Schedule interval (hourly, daily, weekly).
            dry_run: If True, don't make actual changes.
        """
        self._redis_client = redis_client
        self._interval = interval
        self._dry_run = dry_run
        self._running = False
        self._last_run: datetime | None = None
        self._next_run: datetime | None = None

        # Calculate interval seconds
        self._interval_seconds = self._get_interval_seconds(interval)

        logger.info(
            "TempmemoryScheduler initialized",
            extra={
                "interval": interval,
                "interval_seconds": self._interval_seconds,
                "dry_run": dry_run,
                "has_redis": redis_client is not None,
            },
        )

    def _get_interval_seconds(self, interval: str) -> int:
        """Get interval in seconds."""
        intervals = {
            ScheduleInterval.HOURLY: 3600,
            ScheduleInterval.DAILY: 24 * 3600,
            ScheduleInterval.WEEKLY: 7 * 24 * 3600,
        }
        return intervals.get(interval, 24 * 3600)

    def _create_redis_client(self) -> Any | None:
        """Create Redis client if not provided."""
        if self._redis_client:
            return self._redis_client

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
            self._redis_client = client
            return client
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            return None

    def _create_qdrant_client(self) -> Any | None:
        """Create Qdrant client if available."""
        try:
            from qdrant_client import QdrantClient

            host = os.environ.get("QDRANT_HOST", "host.docker.internal")
            port = int(os.environ.get("QDRANT_PORT", "6334"))

            client = QdrantClient(host=host, port=port)
            logger.info(f"Qdrant client connected to {host}:{port}")
            return client
        except Exception as e:
            logger.warning(f"Qdrant not available: {e}")
            return None

    def _acquire_lock(self) -> bool:
        """Acquire scheduler lock to prevent multiple instances."""
        if not self._redis_client:
            return True  # No Redis, no lock needed

        try:
            # Try to set lock with NX (only if not exists) and EX (expire)
            acquired = self._redis_client.set(
                SCHEDULER_LOCK_KEY,
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "started_at": datetime.now(UTC).isoformat(),
                    }
                ),
                nx=True,
                ex=300,  # 5 minute expiry
            )

            if acquired:
                logger.debug("Acquired scheduler lock")
                return True
            else:
                logger.warning(
                    "Could not acquire scheduler lock - another instance running?"
                )
                return False

        except Exception as e:
            logger.warning(f"Failed to acquire lock: {e}")
            return True  # Continue without lock on error

    def _release_lock(self) -> None:
        """Release scheduler lock."""
        if not self._redis_client:
            return

        try:
            self._redis_client.delete(SCHEDULER_LOCK_KEY)
            logger.debug("Released scheduler lock")
        except Exception as e:
            logger.warning(f"Failed to release lock: {e}")

    def _renew_lock(self) -> None:
        """Renew scheduler lock."""
        if not self._redis_client:
            return

        try:
            self._redis_client.expire(SCHEDULER_LOCK_KEY, 300)
        except Exception as e:
            logger.warning(f"Failed to renew lock: {e}")

    def _update_state(self, status: str, message: str = "") -> None:
        """Update scheduler state in Redis."""
        if not self._redis_client:
            return

        try:
            state = {
                "status": status,
                "message": message,
                "updated_at": datetime.now(UTC).isoformat(),
                "interval": self._interval,
                "dry_run": self._dry_run,
            }

            if self._last_run:
                state["last_run"] = self._last_run.isoformat()
            if self._next_run:
                state["next_run"] = self._next_run.isoformat()

            self._redis_client.hset(SCHEDULER_STATE_KEY, mapping=state)
            self._redis_client.expire(SCHEDULER_STATE_KEY, 7 * 24 * 3600)  # 7 days

        except Exception as e:
            logger.warning(f"Failed to update state: {e}")

    def _should_run(self) -> bool:
        """Check if it's time to run the scheduled task."""
        if not self._last_run:
            return True

        elapsed = (datetime.now(UTC) - self._last_run).total_seconds()
        return elapsed >= self._interval_seconds

    def _run_scheduled_task(self) -> dict[str, Any]:
        """Run the scheduled tempmemory migration task."""
        logger.info("Running scheduled tempmemory migration task")

        redis_client = self._create_redis_client()
        qdrant_client = self._create_qdrant_client()

        results: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "migration": None,
            "tracking": None,
            "reconciliation": None,
        }

        try:
            # Step 1: Run migration
            logger.info("Step 1: Running migration")
            engine = TempmemoryMigrationEngine(
                redis_client=redis_client,
                qdrant_client=qdrant_client,
                dry_run=self._dry_run,
            )
            migration_report = engine.run_migration()
            results["migration"] = migration_report.to_dict()

            # Update tracking
            if redis_client and not self._dry_run:
                tracker = TempmemoryTracker(redis_client=redis_client)
                for result in migration_report.results:
                    tracker.track_file(
                        file_path=result.file_path,
                        status=result.status,
                    )

            # Step 2: Run reconciliation
            logger.info("Step 2: Running reconciliation")
            reconciler = TempmemoryArchiveReconciler(
                redis_client=redis_client,
                dry_run=self._dry_run,
            )
            reconciliation_report = reconciler.reconcile()
            results["reconciliation"] = reconciliation_report.to_dict()

            # Step 3: Archive completed files
            if not self._dry_run:
                logger.info("Step 3: Archiving completed files")
                archive_results = reconciler.archive_completed_files()
                results["archived_count"] = len(
                    [r for r in archive_results if r.success]
                )

            logger.info("Scheduled task completed successfully")
            return results

        except Exception as e:
            logger.exception("Scheduled task failed")
            results["error"] = str(e)
            return results

    def run(self) -> None:
        """Run the scheduler loop."""
        self._running = True
        self._create_redis_client()

        # Setup signal handlers
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self._running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("Scheduler started")
        self._update_state("running", "Scheduler started")

        while self._running:
            try:
                # Acquire lock
                if not self._acquire_lock():
                    logger.error("Could not acquire lock, exiting")
                    break

                # Check if it's time to run
                if self._should_run():
                    self._update_state("running", "Executing scheduled task")
                    self._run_scheduled_task()
                    self._last_run = datetime.now(UTC)
                    self._next_run = self._last_run + timedelta(
                        seconds=self._interval_seconds
                    )
                    self._update_state("running", "Waiting for next interval")

                # Renew lock
                self._renew_lock()

                # Sleep for a bit
                time.sleep(60)  # Check every minute

            except Exception as e:
                logger.exception("Error in scheduler loop")
                self._update_state("error", str(e))
                time.sleep(60)

        # Cleanup
        self._release_lock()
        self._update_state("stopped", "Scheduler stopped")
        logger.info("Scheduler stopped")

    def run_once(self) -> dict[str, Any]:
        """Run the scheduled task once."""
        self._create_redis_client()
        return self._run_scheduled_task()

    def test(self) -> int:
        """Test the scheduler configuration."""
        logger.info("Testing scheduler configuration")

        redis_client = self._create_redis_client()
        qdrant_client = self._create_qdrant_client()

        print(f"\n{'=' * 60}")
        print("Scheduler Configuration Test")
        print(f"{'=' * 60}")
        print(f"Interval: {self._interval}")
        print(f"Interval (seconds): {self._interval_seconds}")
        print(f"Dry run: {self._dry_run}")
        print(f"\nRedis: {'Connected' if redis_client else 'Not available'}")
        print(f"Qdrant: {'Connected' if qdrant_client else 'Not available'}")

        # Test migration scan
        print(f"\n{'=' * 60}")
        print("Testing Migration Engine")
        print(f"{'=' * 60}")

        engine = TempmemoryMigrationEngine(
            redis_client=redis_client,
            qdrant_client=qdrant_client,
            dry_run=True,
        )

        files = engine.scan_files()
        print(f"Files found: {len(files)}")

        if files:
            print("\nSample files:")
            for f in files[:3]:
                print(f"  - {f.relative_path}")
                print(f"    Story: {f.story_id or 'N/A'}")
                print(f"    Type: {f.memory_type or 'N/A'}")
                print(f"    Target: {f.determine_target().value}")

        # Test tracking
        if redis_client:
            print(f"\n{'=' * 60}")
            print("Testing Tracker")
            print(f"{'=' * 60}")

            tracker = TempmemoryTracker(redis_client=redis_client, dry_run=True)
            summary = tracker.get_summary()
            print(f"Total tracked: {summary.total_tracked}")
            print(f"Completed: {summary.completed_count}")
            print(f"Failed: {summary.failed_count}")

        # Test reconciliation
        print(f"\n{'=' * 60}")
        print("Testing Reconciler")
        print(f"{'=' * 60}")

        reconciler = TempmemoryArchiveReconciler(
            redis_client=redis_client,
            dry_run=True,
        )

        report = reconciler.reconcile()
        print(f"Total files in tempmemory: {report.total_files_in_tempmemory}")
        print(f"Total files in archive: {report.total_files_in_archive}")
        print(f"Orphaned files: {len(report.orphaned_files)}")
        print(f"Missing files: {len(report.missing_files)}")
        print(f"Mismatched files: {len(report.mismatched_files)}")

        print(f"\n{'=' * 60}")
        print("All tests passed!")
        print(f"{'=' * 60}\n")

        return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run the scheduler continuously."""
    scheduler = TempmemoryScheduler(
        interval=args.interval,
        dry_run=args.dry_run,
    )
    scheduler.run()
    return 0


def cmd_once(args: argparse.Namespace) -> int:
    """Run the scheduled task once."""
    scheduler = TempmemoryScheduler(
        interval=args.interval,
        dry_run=args.dry_run,
    )
    results = scheduler.run_once()
    print(json.dumps(results, indent=2))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Test the scheduler configuration."""
    scheduler = TempmemoryScheduler(
        interval=args.interval,
        dry_run=True,
    )
    return scheduler.test()


def cmd_status(args: argparse.Namespace) -> int:
    """Check scheduler status."""
    try:
        import redis

        client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "host.docker.internal"),
            port=int(os.environ.get("REDIS_PORT", "6380")),
            decode_responses=True,
        )

        state = cast(dict[str, Any], client.hgetall(SCHEDULER_STATE_KEY))

        print(f"\n{'=' * 60}")
        print("Scheduler Status")
        print(f"{'=' * 60}")

        if state:
            for key, value in state.items():
                print(f"{key}: {value}")
        else:
            print("No scheduler state found")

        # Check lock
        lock = client.get(SCHEDULER_LOCK_KEY)
        if lock:
            print("\nLock: Active")
            try:
                lock_data = json.loads(cast(str, lock))
                print(f"  PID: {lock_data.get('pid')}")
                print(f"  Started: {lock_data.get('started_at')}")
            except json.JSONDecodeError:
                print(f"  Raw: {lock}")
        else:
            print("\nLock: Not active")

        print(f"{'=' * 60}\n")
        return 0

    except Exception as e:
        print(f"Error checking status: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tempmemory Migration Scheduler for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run scheduler continuously (Docker mode)
  python3 scripts/ops/tempmemory_scheduler.py --run

  # Run once (for testing or manual execution)
  python3 scripts/ops/tempmemory_scheduler.py --once

  # Test configuration
  python3 scripts/ops/tempmemory_scheduler.py --test

  # Check scheduler status
  python3 scripts/ops/tempmemory_scheduler.py --status

  # Run with specific interval
  python3 scripts/ops/tempmemory_scheduler.py --run --interval daily

Environment Variables:
  REDIS_HOST - Redis hostname (default: host.docker.internal)
  REDIS_PORT - Redis port (default: 6380)
  QDRANT_HOST - Qdrant hostname (default: host.docker.internal)
  QDRANT_PORT - Qdrant port (default: 6334)
        """,
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run scheduler continuously",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run scheduled task once",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test scheduler configuration",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Check scheduler status",
    )

    parser.add_argument(
        "--interval",
        choices=["hourly", "daily", "weekly"],
        default="daily",
        help="Schedule interval (default: daily)",
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
    if args.run:
        return cmd_run(args)
    elif args.once:
        return cmd_once(args)
    elif args.test:
        return cmd_test(args)
    elif args.status:
        return cmd_status(args)
    else:
        # Default to test mode
        return cmd_test(args)


if __name__ == "__main__":
    sys.exit(main())
