#!/usr/bin/env python3
"""Bybit truth freshness watchdog.

Monitors Bybit truth data freshness and triggers alerts/recovery when data goes stale.
Designed to keep G12 green by ensuring bmad:chiseai:bybit_truth:last_collection_timestamp
stays < 60 minutes old.

Usage:
    python3 scripts/monitoring/bybit_freshness_watchdog.py
    python3 scripts/monitoring/bybit_freshness_watchdog.py --auto-recover
    python3 scripts/monitoring/bybit_freshness_watchdog.py --interval 300 --warning-threshold 45

Exit codes:
    0 - Data is fresh (< threshold)
    1 - Data is stale (> threshold)
    2 - Error occurred during check

Redis Keys:
    - bmad:chiseai:bybit_truth:last_collection_timestamp
    - bmad:chiseai:bybit_truth:watchdog:last_check
    - bmad:chiseai:bybit_truth:watchdog:status
    - bmad:chiseai:bybit_truth:recovery_lock (for auto-recovery)

For P0-KPI-GUARDRAILS-003: Bybit Truth Freshness Watchdog
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class FreshnessStatus(Enum):
    """Freshness status codes."""

    FRESH = "fresh"
    WARNING = "warning"
    STALE = "stale"
    ERROR = "error"


class RecoveryStatus(Enum):
    """Recovery attempt status."""

    SUCCESS = "success"
    LOCKED = "locked"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


# Redis key prefixes
REDIS_KEY_PREFIX = "bmad:chiseai:bybit_truth"
REDIS_KEYS = {
    "timestamp": f"{REDIS_KEY_PREFIX}:last_collection_timestamp",
    "count": f"{REDIS_KEY_PREFIX}:last_collection_count",
    "status": f"{REDIS_KEY_PREFIX}:last_collection_status",
    "reason": f"{REDIS_KEY_PREFIX}:last_collection_reason",
    "execution_id": f"{REDIS_KEY_PREFIX}:last_collection_execution_id",
    "error_message": f"{REDIS_KEY_PREFIX}:last_collection_error",
    "watchdog_last_check": f"{REDIS_KEY_PREFIX}:watchdog:last_check",
    "watchdog_status": f"{REDIS_KEY_PREFIX}:watchdog:status",
    "watchdog_alert_count": f"{REDIS_KEY_PREFIX}:watchdog:alert_count",
    "recovery_lock": f"{REDIS_KEY_PREFIX}:recovery_lock",
}

# Default configuration
DEFAULT_CHECK_INTERVAL_SECONDS = 300  # 5 minutes
DEFAULT_WARNING_THRESHOLD_MINUTES = 45  # 75% of fail threshold
DEFAULT_FAIL_THRESHOLD_MINUTES = 60  # 60 minutes = G12 threshold
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380
RECOVERY_LOCK_TTL_SECONDS = 300  # 5 minutes
RECOVERY_TIMEOUT_SECONDS = 120  # 2 minutes for collector subprocess


@dataclass
class WatchdogResult:
    """Result of a watchdog check.

    Attributes:
        status: Status string ("fresh", "warning", "stale", "error")
        minutes_since_collection: Minutes since last collection
        last_collection_timestamp: ISO timestamp of last collection
        last_collection_count: Number of executions in last collection
        threshold_minutes: Fail threshold in minutes
        warning_threshold_minutes: Warning threshold in minutes
        error_message: Error message if check failed
        recovery_status: Status of recovery attempt (if auto-recover enabled)
        recovery_output: Output from recovery subprocess
    """

    status: str = "unknown"
    minutes_since_collection: float = 0.0
    last_collection_timestamp: str = ""
    last_collection_count: int = 0
    threshold_minutes: int = DEFAULT_FAIL_THRESHOLD_MINUTES
    warning_threshold_minutes: int = DEFAULT_WARNING_THRESHOLD_MINUTES
    error_message: str = ""
    recovery_status: str = RecoveryStatus.NOT_ATTEMPTED.value
    recovery_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "minutes_since_collection": round(self.minutes_since_collection, 2),
            "last_collection_timestamp": self.last_collection_timestamp,
            "last_collection_count": self.last_collection_count,
            "threshold_minutes": self.threshold_minutes,
            "warning_threshold_minutes": self.warning_threshold_minutes,
            "error_message": self.error_message,
            "recovery_status": self.recovery_status,
            "recovery_output": self.recovery_output,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def get_exit_code(self) -> int:
        """Get exit code based on status.

        Returns:
            0 - fresh, 1 - stale, 2 - error
        """
        if self.status == FreshnessStatus.FRESH.value:
            return 0
        elif self.status == FreshnessStatus.STALE.value:
            return 1
        else:
            return 2


class BybitFreshnessWatchdog:
    """Watchdog for Bybit truth data freshness.

    Monitors Redis for last collection timestamp and triggers alerts
    and optional auto-recovery when data goes stale.

    Attributes:
        redis_host: Redis host address
        redis_port: Redis port
        warning_threshold_minutes: Minutes before warning
        fail_threshold_minutes: Minutes before stale/fail
        auto_recover: Whether to attempt recovery when stale
        check_interval_seconds: Seconds between checks (in loop mode)
    """

    def __init__(
        self,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        warning_threshold_minutes: int = DEFAULT_WARNING_THRESHOLD_MINUTES,
        fail_threshold_minutes: int = DEFAULT_FAIL_THRESHOLD_MINUTES,
        auto_recover: bool = False,
        check_interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
    ):
        """Initialize the watchdog.

        Args:
            redis_host: Redis host address
            redis_port: Redis port
            warning_threshold_minutes: Minutes before warning
            fail_threshold_minutes: Minutes before stale/fail
            auto_recover: Whether to attempt recovery when stale
            check_interval_seconds: Seconds between checks (in loop mode)
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.warning_threshold_minutes = warning_threshold_minutes
        self.fail_threshold_minutes = fail_threshold_minutes
        self.auto_recover = auto_recover
        self.check_interval_seconds = check_interval_seconds
        self._redis: Any = None

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib

                self._redis = redis_lib.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
                logger.debug(
                    f"Connected to Redis at {self.redis_host}:{self.redis_port}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    def _parse_timestamp(self, timestamp_str: str) -> datetime | None:
        """Parse ISO timestamp string.

        Args:
            timestamp_str: ISO format timestamp

        Returns:
            Parsed datetime or None if invalid
        """
        if not timestamp_str:
            return None

        try:
            # Handle both with and without timezone
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None

    def _calculate_minutes_since(self, timestamp: datetime) -> float:
        """Calculate minutes since a timestamp.

        Args:
            timestamp: Timestamp to calculate from

        Returns:
            Minutes since timestamp
        """
        now = datetime.now(UTC)

        # Ensure timestamp has timezone info
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        diff = now - timestamp
        return diff.total_seconds() / 60

    def _acquire_recovery_lock(self) -> bool:
        """Try to acquire the recovery lock.

        Returns:
            True if lock acquired, False if already held
        """
        try:
            redis = self._get_redis()
            lock_key = REDIS_KEYS["recovery_lock"]

            # Try to set lock with NX (only if not exists) and EX (expiry)
            acquired = redis.set(
                lock_key,
                datetime.now(UTC).isoformat(),
                nx=True,
                ex=RECOVERY_LOCK_TTL_SECONDS,
            )

            if acquired:
                logger.info("Acquired recovery lock")
                return True
            else:
                # Check if lock is expired (in case TTL failed)
                lock_value = redis.get(lock_key)
                if lock_value:
                    try:
                        lock_time = datetime.fromisoformat(lock_value)
                        elapsed = (datetime.now(UTC) - lock_time).total_seconds()
                        if elapsed > RECOVERY_LOCK_TTL_SECONDS:
                            # Lock is stale, force acquire
                            redis.set(
                                lock_key,
                                datetime.now(UTC).isoformat(),
                                ex=RECOVERY_LOCK_TTL_SECONDS,
                            )
                            logger.warning("Acquired stale recovery lock")
                            return True
                    except (ValueError, TypeError):
                        pass

                logger.warning("Recovery lock already held by another process")
                return False

        except Exception as e:
            logger.error(f"Failed to acquire recovery lock: {e}")
            return False

    def _release_recovery_lock(self) -> None:
        """Release the recovery lock."""
        try:
            redis = self._get_redis()
            redis.delete(REDIS_KEYS["recovery_lock"])
            logger.info("Released recovery lock")
        except Exception as e:
            logger.error(f"Failed to release recovery lock: {e}")

    def _trigger_recovery(self) -> tuple[RecoveryStatus, str]:
        """Trigger the Bybit truth collector to recover freshness.

        Returns:
            Tuple of (recovery_status, output)
        """
        if not self._acquire_recovery_lock():
            return RecoveryStatus.LOCKED, "Recovery already in progress (lock held)"

        try:
            logger.info("Triggering Bybit truth collector for recovery...")

            # Build command to run collector
            cmd = [
                sys.executable,
                "-m",
                "scripts.validation.bybit_truth_collector",
                "--dry-run",  # Use dry-run for safety in recovery
            ]

            # Run collector subprocess with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=RECOVERY_TIMEOUT_SECONDS,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )

            if result.returncode == 0:
                logger.info("Recovery successful")
                return RecoveryStatus.SUCCESS, result.stdout
            else:
                logger.error(f"Recovery failed with exit code {result.returncode}")
                return (
                    RecoveryStatus.FAILED,
                    f"stderr: {result.stderr}\nstdout: {result.stdout}",
                )

        except subprocess.TimeoutExpired:
            logger.error(f"Recovery timed out after {RECOVERY_TIMEOUT_SECONDS}s")
            return RecoveryStatus.FAILED, f"Timeout after {RECOVERY_TIMEOUT_SECONDS}s"
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            return RecoveryStatus.FAILED, str(e)
        finally:
            self._release_recovery_lock()

    def _store_watchdog_status(self, result: WatchdogResult) -> bool:
        """Store watchdog check status in Redis.

        Args:
            result: Watchdog check result

        Returns:
            True if stored successfully
        """
        try:
            redis = self._get_redis()
            now = datetime.now(UTC)

            # Update watchdog status
            redis.set(REDIS_KEYS["watchdog_last_check"], now.isoformat())
            redis.set(REDIS_KEYS["watchdog_status"], result.status)

            # Increment alert count if stale
            if result.status == FreshnessStatus.STALE.value:
                alert_count = redis.incr(REDIS_KEYS["watchdog_alert_count"])
                logger.warning(f"Alert count incremented to {alert_count}")

            return True

        except Exception as e:
            logger.error(f"Failed to store watchdog status: {e}")
            return False

    def check(self) -> WatchdogResult:
        """Check freshness and optionally trigger recovery.

        Returns:
            WatchdogResult with status and metadata
        """
        result = WatchdogResult(
            threshold_minutes=self.fail_threshold_minutes,
            warning_threshold_minutes=self.warning_threshold_minutes,
        )

        try:
            redis = self._get_redis()

            # Fetch collection metadata from Redis
            timestamp_str = redis.get(REDIS_KEYS["timestamp"]) or ""
            count_str = redis.get(REDIS_KEYS["count"]) or "0"
            status_str = redis.get(REDIS_KEYS["status"]) or ""
            _ = redis.get(REDIS_KEYS["reason"]) or ""  # Reserved for future use
            error_msg = redis.get(REDIS_KEYS["error_message"]) or ""

            result.last_collection_timestamp = timestamp_str
            result.last_collection_count = int(count_str) if count_str else 0

            # Check if we have any collection data
            if not timestamp_str:
                result.status = FreshnessStatus.STALE.value
                result.error_message = "No collection data found in Redis"
                logger.warning("No collection timestamp found in Redis")

                # Attempt recovery if enabled
                if self.auto_recover:
                    recovery_status, recovery_output = self._trigger_recovery()
                    result.recovery_status = recovery_status.value
                    result.recovery_output = recovery_output

                self._store_watchdog_status(result)
                return result

            # Parse timestamp
            last_collection = self._parse_timestamp(timestamp_str)
            if last_collection is None:
                result.status = FreshnessStatus.ERROR.value
                result.error_message = f"Failed to parse timestamp: {timestamp_str}"
                logger.error(f"Failed to parse collection timestamp: {timestamp_str}")
                self._store_watchdog_status(result)
                return result

            # Calculate minutes since collection
            minutes_since = self._calculate_minutes_since(last_collection)
            result.minutes_since_collection = minutes_since

            # Check if collection had an error
            if status_str == "api_error":
                result.status = FreshnessStatus.STALE.value
                result.error_message = (
                    error_msg or "Last collection failed with API error"
                )
                logger.warning(
                    f"Last collection had API error: {minutes_since:.2f}m ago"
                )

                # Attempt recovery if enabled
                if self.auto_recover:
                    recovery_status, recovery_output = self._trigger_recovery()
                    result.recovery_status = recovery_status.value
                    result.recovery_output = recovery_output

                self._store_watchdog_status(result)
                return result

            if status_str == "redis_error":
                result.status = FreshnessStatus.STALE.value
                result.error_message = (
                    error_msg or "Last collection failed with Redis error"
                )
                logger.warning(
                    f"Last collection had Redis error: {minutes_since:.2f}m ago"
                )

                # Attempt recovery if enabled
                if self.auto_recover:
                    recovery_status, recovery_output = self._trigger_recovery()
                    result.recovery_status = recovery_status.value
                    result.recovery_output = recovery_output

                self._store_watchdog_status(result)
                return result

            # Determine freshness status
            if minutes_since > self.fail_threshold_minutes:
                result.status = FreshnessStatus.STALE.value
                result.error_message = (
                    f"Data is stale: {minutes_since:.2f}m since last collection "
                    f"(threshold: {self.fail_threshold_minutes}m)"
                )
                logger.warning(result.error_message)

                # Attempt recovery if enabled
                if self.auto_recover:
                    recovery_status, recovery_output = self._trigger_recovery()
                    result.recovery_status = recovery_status.value
                    result.recovery_output = recovery_output

            elif minutes_since > self.warning_threshold_minutes:
                result.status = FreshnessStatus.WARNING.value
                result.error_message = (
                    f"Data is aging: {minutes_since:.2f}m since last collection "
                    f"(warning: {self.warning_threshold_minutes}m, fail: {self.fail_threshold_minutes}m)"
                )
                logger.warning(result.error_message)

            else:
                result.status = FreshnessStatus.FRESH.value
                logger.info(
                    f"Data is fresh: {minutes_since:.2f}m since last collection "
                    f"(threshold: {self.fail_threshold_minutes}m)"
                )

            # Store watchdog status
            self._store_watchdog_status(result)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Watchdog check failed: {error_msg}")

            result.status = FreshnessStatus.ERROR.value
            result.error_message = f"Redis error during check: {error_msg}"

        return result

    def run_loop(self) -> None:
        """Run watchdog in continuous loop mode."""
        logger.info(
            f"Starting watchdog loop (interval: {self.check_interval_seconds}s, "
            f"warning: {self.warning_threshold_minutes}m, fail: {self.fail_threshold_minutes}m, "
            f"auto_recover: {self.auto_recover})"
        )

        while True:
            try:
                result = self.check()
                logger.info(f"Watchdog check complete: {result.status}")

                # Exit with error if stale and not auto-recovering
                if (
                    result.status == FreshnessStatus.STALE.value
                    and not self.auto_recover
                ):
                    logger.error("Stale data detected and auto-recovery disabled")
                    sys.exit(1)

            except Exception as e:
                logger.error(f"Watchdog cycle failed: {e}")

            # Wait for next cycle
            logger.debug(f"Waiting {self.check_interval_seconds}s until next check...")
            time.sleep(self.check_interval_seconds)


def print_result(result: WatchdogResult, output_format: str = "text") -> None:
    """Print watchdog check result.

    Args:
        result: Watchdog check result
        output_format: Output format ("text" or "json")
    """
    if output_format == "json":
        print(result.to_json())
        return

    # Text format
    print("\n" + "=" * 70)
    print("BYBIT TRUTH FRESHNESS WATCHDOG")
    print("=" * 70)
    print(f"Check Time: {datetime.now(UTC).isoformat()}")
    print(f"Warning Threshold: {result.warning_threshold_minutes} minutes")
    print(f"Fail Threshold: {result.threshold_minutes} minutes")
    print("-" * 70)

    # Status icon
    if result.status == FreshnessStatus.FRESH.value:
        status_icon = "✓"
        status_text = "FRESH"
    elif result.status == FreshnessStatus.WARNING.value:
        status_icon = "⚠"
        status_text = "WARNING"
    elif result.status == FreshnessStatus.ERROR.value:
        status_icon = "⚠"
        status_text = "ERROR"
    else:
        status_icon = "✗"
        status_text = "STALE"

    print(f"\n📊 STATUS: {status_icon} {status_text}")
    print(f"  Minutes since collection: {result.minutes_since_collection:.2f}")

    print("\n📋 LAST COLLECTION")
    print(f"  Timestamp: {result.last_collection_timestamp or 'N/A'}")
    print(f"  Count: {result.last_collection_count}")

    if result.recovery_status != RecoveryStatus.NOT_ATTEMPTED.value:
        print("\n🔄 RECOVERY ATTEMPT")
        print(f"  Status: {result.recovery_status}")
        if result.recovery_output:
            print(f"  Output: {result.recovery_output[:200]}...")

    if result.error_message:
        print("\n⚠️  ERROR MESSAGE")
        print(f"  {result.error_message}")

    print("\n" + "=" * 70)


def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Watchdog for Bybit truth data freshness"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_CHECK_INTERVAL_SECONDS,
        help=f"Check interval in seconds (default: {DEFAULT_CHECK_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--warning-threshold",
        type=int,
        default=DEFAULT_WARNING_THRESHOLD_MINUTES,
        help=f"Warning threshold in minutes (default: {DEFAULT_WARNING_THRESHOLD_MINUTES})",
    )
    parser.add_argument(
        "--fail-threshold",
        type=int,
        default=DEFAULT_FAIL_THRESHOLD_MINUTES,
        help=f"Fail threshold in minutes (default: {DEFAULT_FAIL_THRESHOLD_MINUTES})",
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default=os.getenv("REDIS_HOST", DEFAULT_REDIS_HOST),
        help=f"Redis host (default: {DEFAULT_REDIS_HOST})",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", str(DEFAULT_REDIS_PORT))),
        help=f"Redis port (default: {DEFAULT_REDIS_PORT})",
    )
    parser.add_argument(
        "--auto-recover",
        action="store_true",
        help="Enable auto-recovery when stale data detected",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run in continuous loop mode",
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
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

    try:
        # Create watchdog
        watchdog = BybitFreshnessWatchdog(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            warning_threshold_minutes=args.warning_threshold,
            fail_threshold_minutes=args.fail_threshold,
            auto_recover=args.auto_recover,
            check_interval_seconds=args.interval,
        )

        if args.loop:
            # Run continuous loop
            watchdog.run_loop()
            return 0  # Never reached unless loop exits
        else:
            # Run single check
            result = watchdog.check()

            # Print result
            print_result(result, output_format=args.output)

            # Return appropriate exit code
            return result.get_exit_code()

    except Exception as e:
        logger.error(f"Watchdog failed: {e}")

        # Print error result
        error_result = WatchdogResult(
            status=FreshnessStatus.ERROR.value,
            error_message=str(e),
            threshold_minutes=args.fail_threshold,
            warning_threshold_minutes=args.warning_threshold,
        )
        print_result(error_result, output_format=args.output)

        return 2


if __name__ == "__main__":
    sys.exit(main())
