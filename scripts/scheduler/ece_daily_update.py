#!/usr/bin/env python3
"""ECE Daily Update Scheduler.

A scheduler script for running daily ECE (Expected Calibration Error) updates.
Imports ECEUpdater from src.ml.calibration.ece_updater and runs daily ECE
calculation for all signal types. Stores results in Redis with key pattern:
bmad:chiseai:ece:daily:{date}

Usage:
    python scripts/scheduler/ece_daily_update.py
    python scripts/scheduler/ece_daily_update.py --dry-run
    python scripts/scheduler/ece_daily_update.py --date 2026-03-10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load .env file for environment variables
env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv(
    "SCHEDULER_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("SCHEDULER_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))
REDIS_DB = int(os.getenv("SCHEDULER_REDIS_DB", os.getenv("REDIS_DB", "1")))

# Redis key patterns
ECE_DAILY_KEY_PREFIX = "bmad:chiseai:ece:daily"
ECE_SCHEDULER_HEARTBEAT_KEY = "bmad:chiseai:scheduler:ece_daily:heartbeat"
ECE_SCHEDULER_LAST_RUN_KEY = "bmad:chiseai:scheduler:ece_daily:last_run"


class MockOutcomeDataStore:
    """Mock outcome data store for dry-run mode."""

    async def fetch_prediction_outcomes(self, since: datetime) -> list:
        """Return mock prediction-outcome records."""
        # Return empty list for dry-run
        return []

    async def get_strategies(self) -> list[str]:
        """Return mock strategy list."""
        return ["mock_strategy_1", "mock_strategy_2"]


class MockHistoryTracker:
    """Mock history tracker for dry-run mode."""

    async def record_ece(self, result) -> bool:
        """Mock record ECE result."""
        logger.info(f"[DRY-RUN] Would record ECE: {result}")
        return True


class MockECEUpdater:
    """Mock ECE updater for dry-run mode."""

    def __init__(self, store, history_tracker, dry_run: bool = False):
        self.store = store
        self.history_tracker = history_tracker
        self.dry_run = dry_run
        self.config = type(
            "Config",
            (),
            {
                "lookback_days": 30,
                "min_samples": 10,
                "n_bins": 10,
            },
        )()

    async def trigger_update(self):
        """Mock trigger update."""
        logger.info("[DRY-RUN] Mock ECE update triggered")

        # Create mock results for all signal types
        from confidence.ece import SignalType

        results = {}
        for signal_type in SignalType:
            results[signal_type.value] = {
                "ece": 0.05 + (hash(signal_type.value) % 10) / 100,
                "sample_count": 100,
                "alert_triggered": False,
            }

        return type(
            "MockResult",
            (),
            {
                "success": True,
                "timestamp": datetime.now(UTC),
                "strategy_results": {
                    "mock_strategy": type(
                        "MockStrategyResult",
                        (),
                        {
                            "success": True,
                            "per_signal_type": results,
                        },
                    )()
                },
                "total_strategies": 1,
                "successful_strategies": 1,
                "failed_strategies": 0,
                "alerts_triggered": 0,
                "total_duration_ms": 100.0,
            },
        )()


def get_redis_connection():
    """Get Redis connection."""
    try:
        import redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def store_ece_results(
    redis_client,
    date_str: str,
    results: dict,
    dry_run: bool = False,
) -> bool:
    """Store ECE results in Redis.

    Args:
        redis_client: Redis connection
        date_str: Date string (YYYY-MM-DD)
        results: ECE calculation results
        dry_run: If True, only log what would be stored

    Returns:
        True if successful
    """
    key = f"{ECE_DAILY_KEY_PREFIX}:{date_str}"

    if dry_run:
        logger.info(f"[DRY-RUN] Would store ECE results to Redis key: {key}")
        logger.info(f"[DRY-RUN] Results: {json.dumps(results, indent=2, default=str)}")
        return True

    if not redis_client:
        logger.error("No Redis connection available")
        return False

    try:
        # Store results as JSON
        redis_client.set(key, json.dumps(results, default=str))
        # Set TTL to 90 days
        redis_client.expire(key, 90 * 24 * 3600)
        logger.info(f"Stored ECE results to Redis: {key}")
        return True
    except Exception as e:
        logger.error(f"Failed to store ECE results: {e}")
        return False


def record_scheduler_heartbeat(
    redis_client,
    status: str,
    message: str = "",
    dry_run: bool = False,
) -> bool:
    """Record scheduler heartbeat to Redis.

    Args:
        redis_client: Redis connection
        status: Current status (running, success, error)
        message: Optional status message
        dry_run: If True, only log what would be recorded

    Returns:
        True if successful
    """
    if dry_run:
        logger.info(
            f"[DRY-RUN] Would record heartbeat: status={status}, message={message}"
        )
        return True

    if not redis_client:
        logger.error("No Redis connection available")
        return False

    try:
        now = datetime.now(UTC)
        heartbeat_data = {
            "timestamp": now.isoformat(),
            "status": status,
            "unix_timestamp": str(int(now.timestamp())),
        }
        if message:
            heartbeat_data["message"] = message

        redis_client.hset(ECE_SCHEDULER_HEARTBEAT_KEY, mapping=heartbeat_data)
        redis_client.expire(ECE_SCHEDULER_HEARTBEAT_KEY, 7 * 24 * 3600)  # 7 days TTL
        return True
    except Exception as e:
        logger.error(f"Failed to record heartbeat: {e}")
        return False


def update_last_run_timestamp(
    redis_client,
    date_str: str,
    dry_run: bool = False,
) -> bool:
    """Update the last run timestamp.

    Args:
        redis_client: Redis connection
        date_str: Date string (YYYY-MM-DD)
        dry_run: If True, only log what would be updated

    Returns:
        True if successful
    """
    if dry_run:
        logger.info(f"[DRY-RUN] Would update last run timestamp: {date_str}")
        return True

    if not redis_client:
        logger.error("No Redis connection available")
        return False

    try:
        now = datetime.now(UTC)
        redis_client.hset(
            ECE_SCHEDULER_LAST_RUN_KEY,
            mapping={
                "date": date_str,
                "timestamp": now.isoformat(),
                "unix_timestamp": str(int(now.timestamp())),
            },
        )
        redis_client.expire(ECE_SCHEDULER_LAST_RUN_KEY, 90 * 24 * 3600)  # 90 days TTL
        return True
    except Exception as e:
        logger.error(f"Failed to update last run timestamp: {e}")
        return False


async def run_ece_update(
    target_date: datetime | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the daily ECE update.

    Args:
        target_date: Date to run update for (defaults to today)
        dry_run: If True, don't actually calculate or store

    Returns:
        Dictionary with update results
    """
    if target_date is None:
        target_date = datetime.now(UTC)

    date_str = target_date.strftime("%Y-%m-%d")
    logger.info(f"Starting ECE daily update for {date_str}")
    logger.info(f"Dry-run mode: {dry_run}")

    # Get Redis connection
    redis_client = get_redis_connection()
    if not redis_client and not dry_run:
        logger.error("Failed to connect to Redis and not in dry-run mode")
        return {"success": False, "error": "Redis connection failed"}

    # Record start heartbeat
    record_scheduler_heartbeat(
        redis_client, "running", f"Starting ECE update for {date_str}", dry_run
    )

    try:
        if dry_run:
            # Use mock implementations in dry-run mode
            store = MockOutcomeDataStore()
            history_tracker = MockHistoryTracker()
            updater = MockECEUpdater(store, history_tracker, dry_run=True)
        else:
            # Import actual implementations
            from confidence.ece_tracker import ECEHistoryTracker
            from ml.calibration.ece_calculator import InMemoryOutcomeDataStore
            from ml.calibration.ece_updater import ECEUpdateService, UpdateConfig

            # Create configuration
            config = UpdateConfig(
                update_time_utc="00:00",
                lookback_days=30,
                min_samples=10,
            )

            # Use actual production implementations
            store = InMemoryOutcomeDataStore()
            history_tracker = ECEHistoryTracker()
            updater = ECEUpdateService(config, store, history_tracker)

        # Trigger the update
        logger.info("Triggering ECE update...")
        result = await updater.trigger_update()

        # Prepare results for storage
        results_data = {
            "date": date_str,
            "timestamp": datetime.now(UTC).isoformat(),
            "success": result.success if hasattr(result, "success") else True,
            "total_strategies": getattr(result, "total_strategies", 0),
            "successful_strategies": getattr(result, "successful_strategies", 0),
            "failed_strategies": getattr(result, "failed_strategies", 0),
            "alerts_triggered": getattr(result, "alerts_triggered", 0),
            "duration_ms": getattr(result, "total_duration_ms", 0.0),
        }

        # Add per-signal-type results if available
        strategy_results = getattr(result, "strategy_results", {})
        if strategy_results:
            signal_type_summary = {}
            for strategy_id, strategy_result in strategy_results.items():
                per_signal = getattr(strategy_result, "per_signal_type", {})
                for signal_type, signal_result in per_signal.items():
                    signal_key = (
                        signal_type.value
                        if hasattr(signal_type, "value")
                        else str(signal_type)
                    )
                    signal_type_summary[signal_key] = {
                        "ece": getattr(signal_result, "ece", 0.0),
                        "sample_count": getattr(signal_result, "sample_count", 0),
                        "alert_triggered": getattr(
                            signal_result, "alert_triggered", False
                        ),
                    }
            results_data["signal_types"] = signal_type_summary

        # Store results in Redis
        store_success = store_ece_results(redis_client, date_str, results_data, dry_run)

        # Update last run timestamp
        update_last_run_timestamp(redis_client, date_str, dry_run)

        # Record success heartbeat
        status_msg = f"ECE update completed for {date_str}"
        if not store_success:
            status_msg += " (storage failed)"
        record_scheduler_heartbeat(
            redis_client,
            "success" if store_success else "error",
            status_msg,
            dry_run,
        )

        logger.info(f"ECE daily update completed for {date_str}")
        logger.info(f"  Success: {results_data['success']}")
        logger.info(
            f"  Strategies: {results_data['successful_strategies']}/{results_data['total_strategies']}"
        )
        logger.info(f"  Alerts: {results_data['alerts_triggered']}")
        logger.info(f"  Duration: {results_data['duration_ms']:.0f}ms")

        return results_data

    except Exception as e:
        logger.exception("ECE daily update failed")

        # Record error heartbeat
        record_scheduler_heartbeat(
            redis_client,
            "error",
            f"ECE update failed: {str(e)}",
            dry_run,
        )

        return {
            "success": False,
            "date": date_str,
            "error": str(e),
            "timestamp": datetime.now(UTC).isoformat(),
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ECE Daily Update Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/scheduler/ece_daily_update.py
  python scripts/scheduler/ece_daily_update.py --dry-run
  python scripts/scheduler/ece_daily_update.py --date 2026-03-10
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual calculations or storage)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Target date for ECE update (YYYY-MM-DD format, defaults to today)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse target date if provided
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)

    # Run the update
    result = asyncio.run(run_ece_update(target_date, args.dry_run))

    # Exit with appropriate code
    if result.get("success"):
        logger.info("ECE daily update completed successfully")
        sys.exit(0)
    else:
        logger.error(f"ECE daily update failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
