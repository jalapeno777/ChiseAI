#!/usr/bin/env python3
"""Bybit truth data freshness collector.

Polls Bybit API for recent executions and stores collection metadata in Redis.
Runs with safe cadence (5 minutes) to avoid rate limits.

Redis Keys:
    - bmad:chiseai:bybit_truth:last_collection_timestamp
    - bmad:chiseai:bybit_truth:last_collection_count
    - bmad:chiseai:bybit_truth:last_collection_status
    - bmad:chiseai:bybit_truth:last_collection_reason

Usage:
    python3 scripts/validation/bybit_truth_collector.py
    python3 scripts/validation/bybit_truth_collector.py --dry-run
    python3 scripts/validation/bybit_truth_collector.py --interval 300

Exit codes:
    0 - Collection successful
    1 - Collection failed but error recorded
    2 - Configuration or connection error

For P0-KPI-GUARDRAILS-003: Bybit Truth Freshness Collector
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

# Add project root to path for cron_evidence import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_REDIS_HOST = "host.docker.internal"
DEFAULT_REDIS_PORT = 6380


@dataclass
class CollectionResult:
    """Result of a collection attempt.

    Attributes:
        execution_id: Unique execution ID
        timestamp: Collection timestamp (ISO format)
        count: Number of executions collected
        status: Collection status
        reason: Reason code
        error_message: Error message if failed
        lookback_hours: Hours of data queried
    """

    execution_id: str = field(default_factory=lambda: str(uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    count: int = 0
    status: str = "unknown"
    reason: str = "unknown"
    error_message: str = ""
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "count": self.count,
            "status": self.status,
            "reason": self.reason,
            "error_message": self.error_message,
            "lookback_hours": self.lookback_hours,
        }


@dataclass
class BybitExecution:
    """Normalized Bybit execution data.

    Attributes:
        order_id: Bybit order ID
        symbol: Trading pair symbol
        side: Trade side ("Buy" or "Sell")
        exec_price: Execution/fill price
        exec_qty: Executed quantity
        exec_fee: Execution fee
        exec_time: Execution timestamp (ms)
        exec_id: Unique execution ID from Bybit
    """

    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_fee: float
    exec_time: int  # milliseconds
    exec_id: str


class BybitTruthCollector:
    """Collects Bybit truth data with freshness tracking.

    Polls Bybit API for recent executions and stores collection metadata
    in Redis for freshness monitoring.

    Attributes:
        redis_host: Redis host address
        redis_port: Redis port
        lookback_hours: Hours of data to query
        dry_run: If True, use mock data instead of real APIs
    """

    def __init__(
        self,
        redis_host: str = DEFAULT_REDIS_HOST,
        redis_port: int = DEFAULT_REDIS_PORT,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        dry_run: bool = False,
    ):
        """Initialize the collector.

        Args:
            redis_host: Redis host address
            redis_port: Redis port
            lookback_hours: Hours of data to query
            dry_run: If True, use mock data for testing
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.lookback_hours = lookback_hours
        self.dry_run = dry_run
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

    def _generate_mock_executions(self) -> list[BybitExecution]:
        """Generate mock Bybit execution data for dry-run mode.

        Returns:
            List of mock BybitExecution objects
        """
        logger.info("Generating mock Bybit executions (dry-run mode)...")
        executions: list[BybitExecution] = []
        base_time = datetime.now(UTC)

        # Generate mock trades
        mock_trades = [
            {
                "order_id": f"ord-{i:03d}",
                "symbol": "BTCUSDT" if i % 2 == 0 else "ETHUSDT",
                "side": "Buy" if i % 3 == 0 else "Sell",
                "price": 65000.0 + (i * 100),
                "qty": 0.1 + (i * 0.01),
                "fee": 0.5 + (i * 0.1),
            }
            for i in range(5)
        ]

        for i, trade in enumerate(mock_trades):
            exec_time = int((base_time - timedelta(hours=i)).timestamp() * 1000)
            execution = BybitExecution(
                order_id=trade["order_id"],
                symbol=trade["symbol"],
                side=trade["side"],
                exec_price=trade["price"],
                exec_qty=trade["qty"],
                exec_fee=trade["fee"],
                exec_time=exec_time,
                exec_id=f"exec-{trade['order_id']}",
            )
            executions.append(execution)

        logger.info(f"Generated {len(executions)} mock Bybit executions")
        return executions

    async def fetch_bybit_executions(
        self,
        symbol: str | None = None,
    ) -> list[BybitExecution]:
        """Fetch execution data from Bybit API.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of normalized BybitExecution objects
        """
        if self.dry_run:
            return self._generate_mock_executions()

        executions: list[BybitExecution] = []

        try:
            # Import here to avoid dependency issues in tests
            from data.exchange.bybit_connector import BybitConnector

            end_time = int(datetime.now(UTC).timestamp() * 1000)
            start_time = int(
                (datetime.now(UTC) - timedelta(hours=self.lookback_hours)).timestamp()
                * 1000
            )

            logger.info(
                f"Fetching Bybit executions from last {self.lookback_hours} hours..."
            )

            async with BybitConnector.from_env() as connector:
                # Get execution history
                response = await connector.get_fills(
                    symbol=symbol,
                    start_time=start_time,
                    end_time=end_time,
                    limit=100,
                )

                result = response.get("result", {})
                exec_list = result.get("list", [])

                logger.info(f"Retrieved {len(exec_list)} executions from Bybit")

                for exec_data in exec_list:
                    try:
                        execution = BybitExecution(
                            order_id=exec_data.get("orderId", ""),
                            symbol=exec_data.get("symbol", ""),
                            side=exec_data.get("side", ""),
                            exec_price=float(exec_data.get("execPrice", 0)),
                            exec_qty=float(exec_data.get("execQty", 0)),
                            exec_fee=float(exec_data.get("execFee", 0)),
                            exec_time=int(exec_data.get("execTime", 0)),
                            exec_id=exec_data.get("execId", ""),
                        )
                        executions.append(execution)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse execution data: {e}")
                        continue

        except ImportError as e:
            logger.error(f"Failed to import BybitConnector: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Bybit executions: {e}")
            raise

        return executions

    def store_collection_result(self, result: CollectionResult) -> bool:
        """Store collection result in Redis.

        Args:
            result: Collection result to store

        Returns:
            True if stored successfully
        """
        try:
            redis = self._get_redis()

            # Store collection metadata
            redis.set(REDIS_KEYS["timestamp"], result.timestamp)
            redis.set(REDIS_KEYS["count"], str(result.count))
            redis.set(REDIS_KEYS["status"], result.status)
            redis.set(REDIS_KEYS["reason"], result.reason)
            redis.set(REDIS_KEYS["execution_id"], result.execution_id)

            if result.error_message:
                redis.set(REDIS_KEYS["error_message"], result.error_message)
            else:
                # Clear any previous error
                redis.delete(REDIS_KEYS["error_message"])

            logger.info(
                f"Stored collection result in Redis: {result.status} "
                f"({result.count} executions)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store collection result in Redis: {e}")
            return False

    async def collect(self, symbol: str | None = None) -> CollectionResult:
        """Run collection cycle.

        Args:
            symbol: Optional symbol filter

        Returns:
            CollectionResult with status and metadata
        """
        result = CollectionResult(lookback_hours=self.lookback_hours)

        try:
            # Fetch executions from Bybit
            executions = await self.fetch_bybit_executions(symbol=symbol)
            result.count = len(executions)

            # Success
            result.status = CollectionStatus.SUCCESS.value
            result.reason = FreshnessReason.FRESH.value

            logger.info(
                f"Collection successful: {result.count} executions "
                f"(execution_id: {result.execution_id})"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Collection failed: {error_msg}")

            result.status = CollectionStatus.API_ERROR.value
            result.reason = FreshnessReason.STALE_API_ERROR.value
            result.error_message = error_msg

        # Store result in Redis (even on failure)
        if not self.store_collection_result(result):
            # Redis storage failed
            if result.status == CollectionStatus.SUCCESS.value:
                result.status = CollectionStatus.REDIS_ERROR.value
                result.reason = FreshnessReason.STALE_REDIS_ERROR.value
                result.error_message = "Failed to store result in Redis"

        return result

    async def run_loop(
        self,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        symbol: str | None = None,
    ) -> None:
        """Run collection loop with periodic polling.

        Args:
            interval_seconds: Seconds between collections
            symbol: Optional symbol filter
        """
        logger.info(
            f"Starting collection loop (interval: {interval_seconds}s, "
            f"lookback: {self.lookback_hours}h)"
        )

        while True:
            try:
                result = await self.collect(symbol=symbol)
                logger.info(f"Collection cycle complete: {result.status}")

            except Exception as e:
                logger.error(f"Collection cycle failed: {e}")

            # Wait for next cycle
            logger.debug(f"Waiting {interval_seconds}s until next collection...")
            await asyncio.sleep(interval_seconds)


def print_result(result: CollectionResult) -> None:
    """Print collection result to console.

    Args:
        result: Collection result to print
    """
    print("\n" + "=" * 70)
    print("BYBIT TRUTH COLLECTION RESULT")
    print("=" * 70)
    print(f"Execution ID: {result.execution_id}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Lookback: {result.lookback_hours} hours")
    print("-" * 70)

    print("\n📊 COLLECTION DATA")
    print(f"  Executions collected: {result.count}")
    print(f"  Status: {result.status}")
    print(f"  Reason: {result.reason}")

    if result.error_message:
        print("\n⚠️  ERROR")
        print(f"  {result.error_message}")

    print("\n" + "=" * 70)


async def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Collect Bybit truth data with freshness tracking"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Collection interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Hours of data to query (default: {DEFAULT_LOOKBACK_HOURS})",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Filter by symbol (e.g., BTCUSDT)",
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
        "--loop",
        action="store_true",
        help="Run in continuous loop mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock data instead of real APIs (no credentials required)",
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
        # Create collector
        collector = BybitTruthCollector(
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            lookback_hours=args.lookback_hours,
            dry_run=args.dry_run,
        )

        if args.loop:
            # Run continuous loop - evidence written per-iteration in collect()
            await collector.run_loop(
                interval_seconds=args.interval,
                symbol=args.symbol,
            )
            # Loop doesn't return, but if it exits, write evidence
            try:
                from scripts.monitoring.cron_evidence import write_cron_evidence

                write_cron_evidence(
                    "bybit-truth-collector",
                    status="error",
                    error_message="Loop exited unexpectedly",
                    write_mode="direct",
                )
            except Exception as evidence_error:
                logger.warning(f"Failed to write cron evidence: {evidence_error}")
            return 2
        else:
            # Run single collection
            result = await collector.collect(symbol=args.symbol)
            print_result(result)

            # Write cron evidence for the execution result
            try:
                from scripts.monitoring.cron_evidence import write_cron_evidence

                evidence_status = (
                    "success"
                    if result.status == CollectionStatus.SUCCESS.value
                    else "error"
                )
                error_msg = result.error_message if evidence_status == "error" else None

                write_cron_evidence(
                    "bybit-truth-collector",
                    status=evidence_status,
                    error_message=error_msg,
                    write_mode="direct",
                )
            except Exception as evidence_error:
                logger.warning(f"Failed to write cron evidence: {evidence_error}")

            # Return appropriate exit code
            if result.status == CollectionStatus.SUCCESS.value:
                return 0
            elif result.status in [
                CollectionStatus.API_ERROR.value,
                CollectionStatus.NETWORK_ERROR.value,
            ]:
                return 1
            else:
                return 2

    except Exception as e:
        logger.error(f"Collector failed: {e}")
        # Write cron evidence for error
        try:
            from scripts.monitoring.cron_evidence import write_cron_evidence

            write_cron_evidence(
                "bybit-truth-collector",
                status="error",
                error_message=str(e),
                write_mode="direct",
            )
        except Exception as evidence_error:
            logger.warning(f"Failed to write cron evidence: {evidence_error}")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
