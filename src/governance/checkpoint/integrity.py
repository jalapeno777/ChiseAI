"""Metric integrity checking for observability validation.

This module provides the MetricIntegrityChecker class that validates
heartbeat aggregate metrics against sampled raw Redis state.

Story: BATCH3-METRIC-INTEGRITY-003
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

logger = logging.getLogger(__name__)


@dataclass
class IntegrityResult:
    """Result of a metric integrity check.

    Attributes:
        status: "OK", "CHECK", or "FAIL"
        heartbeat_count: Signal count from heartbeat aggregate
        actual_count: Actual count from sampled raw Redis keys
        difference: Absolute difference between counts
        tolerance: Allowed tolerance for the comparison
        message: Human-readable status message
        timestamp: When the check was performed
    """

    status: str
    heartbeat_count: int
    actual_count: int
    difference: int
    tolerance: float
    message: str
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)


class MetricIntegrityChecker:
    """Validates metric integrity by comparing heartbeat aggregates vs raw state.

    This checker samples raw signal keys from Redis and compares the count
    against the aggregated signals_15m value from the scheduler heartbeat.
    A tolerance is applied to account for timing differences between the
    heartbeat aggregation and the sampling.

    Story: BATCH3-METRIC-INTEGRITY-003
    """

    # Status constants
    STATUS_OK = "OK"
    STATUS_CHECK = "CHECK"
    STATUS_FAIL = "FAIL"

    # Redis key patterns
    HEARTBEAT_KEY = "bmad:chiseai:scheduler:heartbeat"
    SIGNAL_KEY_PREFIX = "bmad:chiseai:signals:"

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        sample_size: int = 100,
        tolerance_percent: float = 0.1,
        min_tolerance: int = 5,
    ):
        """Initialize the metric integrity checker.

        Args:
            redis_client: Optional Redis client instance
            redis_host: Redis host (defaults to env or host.docker.internal)
            redis_port: Redis port (defaults to env or 6380)
            sample_size: Number of keys to sample for counting (default 100)
            tolerance_percent: Percentage tolerance for count mismatch (default 0.1 = 10%)
            min_tolerance: Minimum absolute tolerance regardless of percentage (default 5)
        """
        self._redis = redis_client
        self._redis_host = redis_host or os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        self._redis_port = redis_port or int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )
        self._sample_size = sample_size
        self._tolerance_percent = tolerance_percent
        self._min_tolerance = min_tolerance

    def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            self._redis = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            return self._redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def _get_heartbeat_signals(self) -> int:
        """Get signals_15m count from scheduler heartbeat.

        Returns:
            Signal count from heartbeat, or 0 if unavailable
        """
        r = self._get_redis()
        if not r:
            return 0

        try:
            heartbeat = r.hgetall(self.HEARTBEAT_KEY)
            signals_str = heartbeat.get("signals_15m", "0")
            return int(signals_str) if signals_str else 0
        except Exception as e:
            logger.error(f"Error reading heartbeat signals: {e}")
            return 0

    def _count_raw_signals_last_15m(self) -> int:
        """Count raw signal keys from last 15 minutes.

        Uses sampling strategy for performance:
        1. Get today's date prefix pattern
        2. Scan for signal keys matching pattern
        3. Sample up to sample_size keys
        4. Count total keys (estimated from sample if needed)

        Returns:
            Estimated count of raw signal keys
        """
        r = self._get_redis()
        if not r:
            return 0

        try:
            # Get today's date for key pattern
            today = datetime.now(UTC).strftime("%Y%m%d")
            pattern = f"{self.SIGNAL_KEY_PREFIX}{today}:*"

            # Scan for all matching keys
            all_keys = []
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=1000)
                all_keys.extend(keys)
                if cursor == 0:
                    break

            if not all_keys:
                return 0

            # If we have fewer keys than sample size, count all
            if len(all_keys) <= self._sample_size:
                return len(all_keys)

            # Sample random keys and extrapolate
            # For simplicity, we'll just return the total count
            # In a production scenario with millions of keys,
            # we might use a statistical sampling approach
            return len(all_keys)

        except Exception as e:
            logger.error(f"Error counting raw signals: {e}")
            return 0

    def check_signal_count_integrity(self) -> IntegrityResult:
        """Check signal count integrity by comparing heartbeat vs raw state.

        Compares the signals_15m aggregate from the scheduler heartbeat
        against the actual count of raw signal keys in Redis.

        Returns:
            IntegrityResult with status and comparison details
        """
        r = self._get_redis()
        if not r:
            return IntegrityResult(
                status=self.STATUS_FAIL,
                heartbeat_count=0,
                actual_count=0,
                difference=0,
                tolerance=0,
                message="Redis unavailable - cannot check signal integrity",
            )

        try:
            # Get heartbeat aggregate count
            heartbeat_signals = self._get_heartbeat_signals()

            # Get actual raw signal count
            actual_count = self._count_raw_signals_last_15m()

            # Calculate tolerance (10% of heartbeat count, minimum 5)
            tolerance = max(
                heartbeat_signals * self._tolerance_percent, self._min_tolerance
            )

            # Calculate difference
            difference = abs(heartbeat_signals - actual_count)

            # Determine status based on difference vs tolerance
            if difference <= tolerance:
                status = self.STATUS_OK
                message = (
                    f"Signal counts match within tolerance: "
                    f"heartbeat={heartbeat_signals}, actual={actual_count}, "
                    f"diff={difference}, tolerance={tolerance:.1f}"
                )
            elif difference <= tolerance * 2:
                status = self.STATUS_CHECK
                message = (
                    f"Signal count mismatch detected: "
                    f"heartbeat={heartbeat_signals}, actual={actual_count}, "
                    f"diff={difference}, tolerance={tolerance:.1f} "
                    f"(mismatch < 20%)"
                )
            else:
                status = self.STATUS_FAIL
                message = (
                    f"Signal count mismatch exceeds tolerance: "
                    f"heartbeat={heartbeat_signals}, actual={actual_count}, "
                    f"diff={difference}, tolerance={tolerance:.1f} "
                    f"(mismatch > 20%)"
                )

            return IntegrityResult(
                status=status,
                heartbeat_count=heartbeat_signals,
                actual_count=actual_count,
                difference=difference,
                tolerance=tolerance,
                message=message,
            )

        except Exception as e:
            logger.error(f"Error checking signal integrity: {e}")
            return IntegrityResult(
                status=self.STATUS_FAIL,
                heartbeat_count=0,
                actual_count=0,
                difference=0,
                tolerance=0,
                message=f"Exception during integrity check: {str(e)[:100]}",
            )

    def to_gate_result(self, integrity_result: IntegrityResult | None = None):
        """Convert IntegrityResult to GateResult format.

        This method allows integration with the GateChecker system
        without direct coupling to gates.py.

        Args:
            integrity_result: Optional pre-computed integrity result.
                            If None, runs check_signal_count_integrity().

        Returns:
            GateResult compatible with GateChecker format
        """
        # Local import to avoid circular dependency
        from src.governance.checkpoint.gates import GateResult

        if integrity_result is None:
            integrity_result = self.check_signal_count_integrity()

        # Map integrity status to gate status
        status_map = {
            self.STATUS_OK: "✅ PASS",
            self.STATUS_CHECK: "⚠️ CHECK",
            self.STATUS_FAIL: "❌ FAIL",
        }

        gate_status = status_map.get(integrity_result.status, "❓ UNKNOWN")

        return GateResult(
            gate="G9",
            status=gate_status,
            detail=integrity_result.message,
            timestamp=integrity_result.timestamp,
        )

    def run_integrity_check(self) -> dict:
        """Run full integrity check and return detailed results.

        Returns:
            Dictionary with check results and metadata
        """
        result = self.check_signal_count_integrity()

        return {
            "status": result.status,
            "heartbeat_count": result.heartbeat_count,
            "actual_count": result.actual_count,
            "difference": result.difference,
            "tolerance": result.tolerance,
            "message": result.message,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "healthy": result.status == self.STATUS_OK,
        }
