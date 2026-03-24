"""Throughput tracking for signal delivery.

Tracks signals per minute, calculates p50/p95/p99 latencies,
and stores metrics in Redis with sliding window calculations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    def hset(self, name: str, key: str, value: str) -> int: ...
    def hget(self, name: str, key: str) -> str | None: ...
    def hgetall(self, name: str) -> dict[str, str]: ...
    def expire(self, name: str, time: int) -> int: ...
    def delete(self, name: str) -> int: ...


@dataclass
class ThroughputMetrics:
    """Throughput metrics for a time window.

    Attributes:
        window_name: Name of the window (1min, 5min, 15min)
        signals_count: Number of signals in window
        signals_per_minute: Average signals per minute
        timestamp: When metrics were calculated
    """

    window_name: str
    signals_count: int
    signals_per_minute: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "window_name": self.window_name,
            "signals_count": self.signals_count,
            "signals_per_minute": round(self.signals_per_minute, 2),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class LatencyPercentiles:
    """Latency percentile metrics.

    Attributes:
        p50_ms: 50th percentile latency
        p95_ms: 95th percentile latency
        p99_ms: 99th percentile latency
        min_ms: Minimum latency
        max_ms: Maximum latency
        avg_ms: Average latency
        count: Number of measurements
    """

    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    avg_ms: float = 0.0
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "count": self.count,
        }


@dataclass
class SignalRecord:
    """Record of a signal delivery.

    Attributes:
        signal_id: Signal identifier
        timestamp: When signal was delivered
        latency_ms: Delivery latency in milliseconds
        success: Whether delivery succeeded
        metadata: Additional metadata
    """

    signal_id: str
    timestamp: datetime
    latency_ms: float
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": round(self.latency_ms, 2),
            "success": self.success,
            "metadata": self.metadata,
        }


class ThroughputTracker:
    """Track signal throughput and latency percentiles.

    Tracks signals per minute with sliding windows (1min, 5min, 15min)
    and calculates p50/p95/p99 latencies. Stores metrics in Redis.

    Redis Key Patterns:
        - chise:paper:metrics:throughput:current - Current metrics hash
        - chise:paper:metrics:throughput:history - Historical data list
        - chise:paper:metrics:throughput:signals - Recent signal records

    Example:
        tracker = ThroughputTracker(redis_client)
        tracker.record_signal("sig-1", latency_ms=150.0)
        metrics = tracker.get_metrics("5min")
        print(f"Throughput: {metrics.signals_per_minute} signals/min")
    """

    # Redis key prefixes
    REDIS_PREFIX = "chise:paper:metrics:throughput"
    CURRENT_KEY = f"{REDIS_PREFIX}:current"
    HISTORY_KEY = f"{REDIS_PREFIX}:history"
    SIGNALS_KEY = f"{REDIS_PREFIX}:signals"

    # Default TTL for Redis keys (1 hour)
    DEFAULT_TTL = 3600

    # Maximum number of signal records to keep in memory
    MAX_SIGNAL_RECORDS = 10000

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        ttl_seconds: int = DEFAULT_TTL,
    ):
        """Initialize throughput tracker.

        Args:
            redis_client: Redis client for persistence (optional)
            ttl_seconds: TTL for Redis keys
        """
        self._redis = redis_client
        self._ttl = ttl_seconds

        # In-memory storage (fallback when Redis unavailable)
        self._signals: list[SignalRecord] = []
        self._metrics_history: list[dict[str, Any]] = []

    def record_signal(
        self,
        signal_id: str,
        latency_ms: float,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a signal delivery.

        Args:
            signal_id: Signal identifier
            latency_ms: Delivery latency in milliseconds
            success: Whether delivery succeeded
            metadata: Additional metadata
        """
        record = SignalRecord(
            signal_id=signal_id,
            timestamp=datetime.now(UTC),
            latency_ms=latency_ms,
            success=success,
            metadata=metadata or {},
        )

        # Store in memory
        self._signals.append(record)

        # Trim memory storage
        if len(self._signals) > self.MAX_SIGNAL_RECORDS:
            self._signals = self._signals[-self.MAX_SIGNAL_RECORDS :]

        # Store in Redis if available
        if self._redis:
            self._store_signal_in_redis(record)

        logger.debug(f"Recorded signal {signal_id}: {latency_ms:.2f}ms")

    def _store_signal_in_redis(self, record: SignalRecord) -> None:
        """Store signal record in Redis.

        Args:
            record: Signal record to store
        """
        if not self._redis:
            return

        try:
            # Store in signals hash with timestamp as key
            key = f"{record.timestamp.isoformat()}:{record.signal_id}"
            self._redis.hset(
                self.SIGNALS_KEY,
                key,
                json.dumps(record.to_dict()),
            )
            self._redis.expire(self.SIGNALS_KEY, self._ttl)
        except Exception as e:
            logger.warning(f"Failed to store signal in Redis: {e}")

    def get_metrics(self, window: str = "1min") -> ThroughputMetrics:
        """Get throughput metrics for a time window.

        Args:
            window: Time window (1min, 5min, 15min)

        Returns:
            ThroughputMetrics for the window
        """
        window_seconds = self._parse_window(window)
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)

        # Get signals in window
        signals = self._get_signals_since(since)

        # Calculate metrics
        count = len(signals)
        minutes = window_seconds / 60.0
        spm = count / minutes if minutes > 0 else 0.0

        return ThroughputMetrics(
            window_name=window,
            signals_count=count,
            signals_per_minute=spm,
        )

    def get_latency_percentiles(self, window: str = "1min") -> LatencyPercentiles:
        """Get latency percentiles for a time window.

        Args:
            window: Time window (1min, 5min, 15min)

        Returns:
            LatencyPercentiles for the window
        """
        window_seconds = self._parse_window(window)
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)

        # Get latencies in window
        latencies = [s.latency_ms for s in self._get_signals_since(since) if s.success]

        if not latencies:
            return LatencyPercentiles()

        sorted_latencies = sorted(latencies)
        count = len(sorted_latencies)

        return LatencyPercentiles(
            p50_ms=self._percentile(sorted_latencies, 50),
            p95_ms=self._percentile(sorted_latencies, 95),
            p99_ms=self._percentile(sorted_latencies, 99),
            min_ms=sorted_latencies[0],
            max_ms=sorted_latencies[-1],
            avg_ms=sum(sorted_latencies) / count,
            count=count,
        )

    def _get_signals_since(self, since: datetime) -> list[SignalRecord]:
        """Get signals since a given time.

        Args:
            since: Cutoff time

        Returns:
            List of signal records
        """
        return [s for s in self._signals if s.timestamp >= since]

    def _parse_window(self, window: str) -> int:
        """Parse window string to seconds.

        Args:
            window: Window string (1min, 5min, 15min)

        Returns:
            Window duration in seconds
        """
        window_map = {
            "1min": 60,
            "5min": 300,
            "15min": 900,
        }
        return window_map.get(window, 60)

    def _percentile(self, sorted_values: list[float], percentile: int) -> float:
        """Calculate percentile from sorted values.

        Args:
            sorted_values: Sorted list of values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not sorted_values:
            return 0.0

        index = int(len(sorted_values) * percentile / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def get_all_windows_metrics(self) -> dict[str, ThroughputMetrics]:
        """Get metrics for all standard windows.

        Returns:
            Dictionary of window name -> metrics
        """
        return {
            "1min": self.get_metrics("1min"),
            "5min": self.get_metrics("5min"),
            "15min": self.get_metrics("15min"),
        }

    def get_all_windows_latencies(self) -> dict[str, LatencyPercentiles]:
        """Get latency percentiles for all standard windows.

        Returns:
            Dictionary of window name -> percentiles
        """
        return {
            "1min": self.get_latency_percentiles("1min"),
            "5min": self.get_latency_percentiles("5min"),
            "15min": self.get_latency_percentiles("15min"),
        }

    def store_current_metrics(self) -> dict[str, Any]:
        """Store current metrics in Redis.

        Returns:
            Stored metrics dictionary
        """
        metrics = {
            "timestamp": datetime.now(UTC).isoformat(),
            "throughput": {
                window: m.to_dict()
                for window, m in self.get_all_windows_metrics().items()
            },
            "latency": {
                window: lat.to_dict()
                for window, lat in self.get_all_windows_latencies().items()
            },
        }

        if self._redis:
            try:
                self._redis.hset(
                    self.CURRENT_KEY,
                    "metrics",
                    json.dumps(metrics),
                )
                self._redis.expire(self.CURRENT_KEY, self._ttl)
            except Exception as e:
                logger.warning(f"Failed to store metrics in Redis: {e}")

        # Also store in memory history
        self._metrics_history.append(metrics)

        return metrics

    def get_current_metrics(self) -> dict[str, Any] | None:
        """Get current metrics from Redis.

        Returns:
            Current metrics or None if not available
        """
        if not self._redis:
            return self._metrics_history[-1] if self._metrics_history else None

        try:
            data = self._redis.hget(self.CURRENT_KEY, "metrics")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to get metrics from Redis: {e}")

        return None

    def get_summary(self) -> dict[str, Any]:
        """Get summary of throughput and latency.

        Returns:
            Summary dictionary
        """
        throughput = self.get_all_windows_metrics()
        latency = self.get_all_windows_latencies()

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_signals_recorded": len(self._signals),
            "throughput": {window: m.to_dict() for window, m in throughput.items()},
            "latency": {window: lat.to_dict() for window, lat in latency.items()},
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._signals.clear()
        self._metrics_history.clear()

        if self._redis:
            try:
                self._redis.delete(self.SIGNALS_KEY)
                self._redis.delete(self.CURRENT_KEY)
            except Exception as e:
                logger.warning(f"Failed to clear Redis keys: {e}")

    def check_throughput_threshold(
        self,
        window: str,
        min_spm: float,
    ) -> dict[str, Any]:
        """Check if throughput meets threshold.

        Args:
            window: Time window to check
            min_spm: Minimum signals per minute

        Returns:
            Check result with status and details
        """
        metrics = self.get_metrics(window)
        passed = metrics.signals_per_minute >= min_spm

        return {
            "window": window,
            "threshold": min_spm,
            "actual": round(metrics.signals_per_minute, 2),
            "passed": passed,
            "status": "healthy" if passed else "alert",
            "message": (
                f"Throughput {metrics.signals_per_minute:.2f} signals/min "
                f"{'meets' if passed else 'below'} threshold {min_spm}"
            ),
        }

    def check_latency_threshold(
        self,
        window: str,
        max_p95_ms: float,
    ) -> dict[str, Any]:
        """Check if latency meets threshold.

        Args:
            window: Time window to check
            max_p95_ms: Maximum p95 latency in milliseconds

        Returns:
            Check result with status and details
        """
        percentiles = self.get_latency_percentiles(window)
        passed = percentiles.p95_ms <= max_p95_ms

        return {
            "window": window,
            "threshold_ms": max_p95_ms,
            "actual_p95_ms": round(percentiles.p95_ms, 2),
            "passed": passed,
            "status": "healthy" if passed else "alert",
            "message": (
                f"P95 latency {percentiles.p95_ms:.2f}ms "
                f"{'meets' if passed else 'exceeds'} threshold {max_p95_ms}ms"
            ),
        }


def create_tracker(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
) -> ThroughputTracker:
    """Create a ThroughputTracker with Redis connection.

    Args:
        redis_host: Redis host
        redis_port: Redis port
        redis_db: Redis database

    Returns:
        Configured ThroughputTracker
    """
    try:
        import redis

        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True,
        )
        # Test connection
        client.ping()
        return ThroughputTracker(redis_client=client)
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return ThroughputTracker(redis_client=None)
