#!/usr/bin/env python3
"""Bybit truth data freshness checker.

Checks if Bybit truth data is fresh by examining the last collection timestamp
in Redis. Returns explicit reason codes and appropriate exit codes.

Usage:
    python3 scripts/validation/bybit_freshness_check.py
    python3 scripts/validation/bybit_freshness_check.py --output json
    python3 scripts/validation/bybit_freshness_check.py --threshold-hours 24

Exit codes:
    0 - Data is fresh (< threshold)
    1 - Data is stale (> threshold)
    2 - Error occurred during check

For P0-KPI-GUARDRAILS-003: Bybit Truth Freshness Checker
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
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


class FreshnessReason(Enum):
    """Reason codes for freshness status."""

    FRESH = "fresh"
    STALE_NO_COLLECTION = "stale_no_collection"
    STALE_OLD = "stale_old"
    STALE_API_ERROR = "stale_api_error"
    STALE_REDIS_ERROR = "stale_redis_error"


class CollectionStatus(Enum):
    """Collection status codes."""

    SUCCESS = "success"
    API_ERROR = "api_error"
    REDIS_ERROR = "redis_error"
    CONFIG_ERROR = "config_error"
    NETWORK_ERROR = "network_error"


# Redis key prefixes
REDIS_KEY_PREFIX = "bmad:chiseai:bybit_truth"
REDIS_KEYS = {
    "timestamp": f"{REDIS_KEY_PREFIX}:last_collection_timestamp",
    "count": f"{REDIS_KEY_PREFIX}:last_collection_count",
    "status": f"{REDIS_KEY_PREFIX}:last_collection_status",
    "reason": f"{REDIS_KEY_PREFIX}:last_collection_reason",
    "execution_id": f"{REDIS_KEY_PREFIX}:last_collection_execution_id",
    "error_message": f"{REDIS_KEY_PREFIX}:last_collection_error",
}

# Default configuration
DEFAULT_STALE_THRESHOLD_HOURS = 24
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380


@dataclass
class FreshnessCheckResult:
    """Result of a freshness check.

    Attributes:
        is_fresh: Whether data is fresh
        status: Status string ("fresh", "stale", "error")
        reason: Reason code from FreshnessReason
        hours_since_collection: Hours since last collection
        last_collection_timestamp: ISO timestamp of last collection
        last_collection_count: Number of executions in last collection
        last_collection_status: Status of last collection
        threshold_hours: Stale threshold in hours
        error_message: Error message if check failed
    """

    is_fresh: bool = False
    status: str = "unknown"
    reason: str = "unknown"
    hours_since_collection: float = 0.0
    last_collection_timestamp: str = ""
    last_collection_count: int = 0
    last_collection_status: str = "unknown"
    threshold_hours: int = DEFAULT_STALE_THRESHOLD_HOURS
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_fresh": self.is_fresh,
            "status": self.status,
            "reason": self.reason,
            "hours_since_collection": round(self.hours_since_collection, 2),
            "last_collection_timestamp": self.last_collection_timestamp,
            "last_collection_count": self.last_collection_count,
            "last_collection_status": self.last_collection_status,
            "threshold_hours": self.threshold_hours,
            "error_message": self.error_message,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class BybitFreshnessChecker:
    """Checks freshness of Bybit truth data.

    Examines Redis for last collection timestamp and determines
    if data is stale based on configurable threshold.

    Attributes:
        redis_host: Redis host address
        redis_port: Redis port
        threshold_hours: Hours before data is considered stale
    """

    def __init__(
        self,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        threshold_hours: int = DEFAULT_STALE_THRESHOLD_HOURS,
    ):
        """Initialize the checker.

        Args:
            redis_host: Redis host address
            redis_port: Redis port
            threshold_hours: Hours before data is considered stale
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.threshold_hours = threshold_hours
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

    def _calculate_hours_since(self, timestamp: datetime) -> float:
        """Calculate hours since a timestamp.

        Args:
            timestamp: Timestamp to calculate from

        Returns:
            Hours since timestamp
        """
        now = datetime.now(UTC)

        # Ensure timestamp has timezone info
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        diff = now - timestamp
        return diff.total_seconds() / 3600

    def check(self) -> FreshnessCheckResult:
        """Check freshness of Bybit truth data.

        Returns:
            FreshnessCheckResult with status and metadata
        """
        result = FreshnessCheckResult(threshold_hours=self.threshold_hours)

        try:
            redis = self._get_redis()

            # Fetch collection metadata from Redis
            timestamp_str = redis.get(REDIS_KEYS["timestamp"]) or ""
            count_str = redis.get(REDIS_KEYS["count"]) or "0"
            status_str = redis.get(REDIS_KEYS["status"]) or ""
            reason_str = redis.get(REDIS_KEYS["reason"]) or ""
            error_msg = redis.get(REDIS_KEYS["error_message"]) or ""

            result.last_collection_timestamp = timestamp_str
            result.last_collection_count = int(count_str) if count_str else 0
            result.last_collection_status = status_str

            # Check if we have any collection data
            if not timestamp_str:
                result.is_fresh = False
                result.status = "stale"
                result.reason = FreshnessReason.STALE_NO_COLLECTION.value
                result.error_message = "No collection data found in Redis"
                logger.warning("No collection timestamp found in Redis")
                return result

            # Parse timestamp
            last_collection = self._parse_timestamp(timestamp_str)
            if last_collection is None:
                result.is_fresh = False
                result.status = "error"
                result.reason = FreshnessReason.STALE_REDIS_ERROR.value
                result.error_message = f"Failed to parse timestamp: {timestamp_str}"
                logger.error(f"Failed to parse collection timestamp: {timestamp_str}")
                return result

            # Calculate hours since collection
            hours_since = self._calculate_hours_since(last_collection)
            result.hours_since_collection = hours_since

            # Check if collection had an error
            if status_str == CollectionStatus.API_ERROR.value:
                result.is_fresh = False
                result.status = "stale"
                result.reason = FreshnessReason.STALE_API_ERROR.value
                result.error_message = (
                    error_msg or "Last collection failed with API error"
                )
                logger.warning(f"Last collection had API error: {hours_since:.2f}h ago")
                return result

            if status_str == CollectionStatus.REDIS_ERROR.value:
                result.is_fresh = False
                result.status = "stale"
                result.reason = FreshnessReason.STALE_REDIS_ERROR.value
                result.error_message = (
                    error_msg or "Last collection failed with Redis error"
                )
                logger.warning(
                    f"Last collection had Redis error: {hours_since:.2f}h ago"
                )
                return result

            # Check if data is stale based on threshold
            if hours_since > self.threshold_hours:
                result.is_fresh = False
                result.status = "stale"
                result.reason = FreshnessReason.STALE_OLD.value
                logger.warning(
                    f"Data is stale: {hours_since:.2f}h since last collection "
                    f"(threshold: {self.threshold_hours}h)"
                )
                return result

            # Data is fresh
            result.is_fresh = True
            result.status = "fresh"
            result.reason = FreshnessReason.FRESH.value
            logger.info(
                f"Data is fresh: {hours_since:.2f}h since last collection "
                f"(threshold: {self.threshold_hours}h)"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Freshness check failed: {error_msg}")

            result.is_fresh = False
            result.status = "error"
            result.reason = FreshnessReason.STALE_REDIS_ERROR.value
            result.error_message = f"Redis error during check: {error_msg}"

        return result


def print_result(result: FreshnessCheckResult, output_format: str = "text") -> None:
    """Print freshness check result.

    Args:
        result: Freshness check result
        output_format: Output format ("text" or "json")
    """
    if output_format == "json":
        print(result.to_json())
        return

    # Text format
    print("\n" + "=" * 70)
    print("BYBIT TRUTH FRESHNESS CHECK")
    print("=" * 70)
    print(f"Threshold: {result.threshold_hours} hours")
    print("-" * 70)

    # Status icon
    if result.is_fresh:
        status_icon = "✓"
        status_text = "FRESH"
    elif result.status == "error":
        status_icon = "⚠"
        status_text = "ERROR"
    else:
        status_icon = "✗"
        status_text = "STALE"

    print(f"\n📊 STATUS: {status_icon} {status_text}")
    print(f"  Reason: {result.reason}")
    print(f"  Hours since collection: {result.hours_since_collection:.2f}")

    print(f"\n📋 LAST COLLECTION")
    print(f"  Timestamp: {result.last_collection_timestamp or 'N/A'}")
    print(f"  Count: {result.last_collection_count}")
    print(f"  Status: {result.last_collection_status}")

    if result.error_message:
        print(f"\n⚠️  ERROR MESSAGE")
        print(f"  {result.error_message}")

    print("\n" + "=" * 70)


def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(description="Check freshness of Bybit truth data")
    parser.add_argument(
        "--threshold-hours",
        type=int,
        default=DEFAULT_STALE_THRESHOLD_HOURS,
        help=f"Stale threshold in hours (default: {DEFAULT_STALE_THRESHOLD_HOURS})",
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
        # Create checker
        checker = BybitFreshnessChecker(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            threshold_hours=args.threshold_hours,
        )

        # Run check
        result = checker.check()

        # Print result
        print_result(result, output_format=args.output)

        # Return appropriate exit code
        if result.status == "fresh":
            return 0
        elif result.status == "stale":
            return 1
        else:
            return 2

    except Exception as e:
        logger.error(f"Freshness check failed: {e}")

        # Print error result
        error_result = FreshnessCheckResult(
            is_fresh=False,
            status="error",
            reason=FreshnessReason.STALE_REDIS_ERROR.value,
            error_message=str(e),
            threshold_hours=args.threshold_hours,
        )
        print_result(error_result, output_format=args.output)

        return 2


if __name__ == "__main__":
    sys.exit(main())
