"""
Constitution Metrics Exporter for ChiseAI Governance.

Exports metrics related to constitution violations,
API compliance, and query rates.

Story: ST-GOV-004
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
    MetricType,
)

logger = logging.getLogger(__name__)

# Redis keys for constitution metrics
CONSTITUTION_PREFIX = "chise:governance:constitution"
VIOLATIONS_KEY = f"{CONSTITUTION_PREFIX}:violations"
QUERY_COUNT_KEY = f"{CONSTITUTION_PREFIX}:queries"
LATENCY_KEY = f"{CONSTITUTION_PREFIX}:latency"


class ConstitutionMetricsExporter(BaseMetricsExporter):
    """
    Metrics exporter for the Constitution governance feature.

    Collects and exports:
    - Violation counts (total and by type)
    - API latency percentiles
    - Query rates
    - Feature flag states

    Example:
        exporter = ConstitutionMetricsExporter(redis_client=redis)
        points = exporter.collect()
        # Returns metrics about constitution compliance
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the constitution metrics exporter.

        Args:
            influx_client: Optional InfluxDB client
            redis_client: Optional Redis client for reading metrics
        """
        super().__init__(
            feature_name="constitution",
            influx_client=influx_client,
            redis_client=redis_client,
        )

        # In-memory counters for when Redis is unavailable
        self._violation_count = 0
        self._query_count = 0
        self._latency_samples: list[float] = []

    def collect(self) -> list[MetricPoint]:
        """
        Collect constitution-related metrics.

        Returns:
            List of MetricPoint objects with constitution metrics
        """
        points: list[MetricPoint] = []
        now = datetime.now(UTC)

        # 1. Violation count
        violation_count = self._get_violation_count()
        points.append(
            MetricPoint(
                name="governance.constitution.violations.total",
                value=float(violation_count),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "constitution"},
            )
        )

        # 2. Violation rate (per hour)
        violation_rate = self._get_violation_rate()
        points.append(
            MetricPoint(
                name="governance.constitution.violations.rate",
                value=violation_rate,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "constitution", "unit": "per_hour"},
            )
        )

        # 3. Query count
        query_count = self._get_query_count()
        points.append(
            MetricPoint(
                name="governance.constitution.queries.total",
                value=float(query_count),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "constitution"},
            )
        )

        # 4. API latency percentiles
        latencies = self._get_latency_percentiles()
        for percentile, value in latencies.items():
            points.append(
                MetricPoint(
                    name="governance.constitution.latency",
                    value=value,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "constitution", "percentile": percentile},
                    fields={"unit": "milliseconds"},
                )
            )

        # 5. Feature flag state
        is_enabled = self._is_feature_enabled()
        points.append(
            MetricPoint(
                name="governance.constitution.enabled",
                value=1.0 if is_enabled else 0.0,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "constitution"},
            )
        )

        # 6. Last violation timestamp
        last_violation_ts = self._get_last_violation_timestamp()
        if last_violation_ts:
            points.append(
                MetricPoint(
                    name="governance.constitution.violations.last_timestamp",
                    value=last_violation_ts,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "constitution"},
                    fields={"unit": "unix_timestamp"},
                )
            )

        return points

    def _get_violation_count(self) -> int:
        """Get total violation count from Redis or local counter."""
        if self._redis_client:
            try:
                val = self._redis_client.get(VIOLATIONS_KEY)
                if val:
                    return int(val)
            except Exception as e:
                logger.debug(f"Could not get violation count from Redis: {e}")
        return self._violation_count

    def _get_violation_rate(self) -> float:
        """Get violation rate (violations per hour)."""
        # Calculate based on recent violations
        # For stub implementation, return a sample rate
        if self._redis_client:
            try:
                # Try to get rate from Redis (would be computed by a background job)
                rate_key = f"{VIOLATIONS_KEY}:rate"
                val = self._redis_client.get(rate_key)
                if val:
                    return float(val)
            except Exception:
                pass
        return 0.0

    def _get_query_count(self) -> int:
        """Get total query count from Redis or local counter."""
        if self._redis_client:
            try:
                val = self._redis_client.get(QUERY_COUNT_KEY)
                if val:
                    return int(val)
            except Exception as e:
                logger.debug(f"Could not get query count from Redis: {e}")
        return self._query_count

    def _get_latency_percentiles(self) -> dict[str, float]:
        """Get latency percentiles (p50, p95, p99)."""
        # Default values when no data available
        defaults = {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        if self._redis_client:
            try:
                # Get stored percentiles from Redis
                for p in ["p50", "p95", "p99"]:
                    val = self._redis_client.get(f"{LATENCY_KEY}:{p}")
                    if val:
                        defaults[p] = float(val)
            except Exception:
                pass

        return defaults

    def _is_feature_enabled(self) -> bool:
        """Check if constitution feature is enabled."""
        if self._redis_client:
            try:
                val: bytes | str | None = self._redis_client.get(
                    "chise:feature_flags:governance:constitution_enabled"
                )
                return val == b"true" or val == "true"
            except Exception:
                pass
        return False

    def _get_last_violation_timestamp(self) -> float:
        """Get timestamp of last violation."""
        if self._redis_client:
            try:
                ts = self._redis_client.get(f"{VIOLATIONS_KEY}:last_timestamp")
                if ts:
                    return float(ts)
            except Exception:
                pass
        return 0.0

    # Methods for updating metrics (called by constitution module)
    def record_violation(self, violation_type: str = "generic") -> None:
        """Record a constitution violation."""
        self._violation_count += 1
        if self._redis_client:
            try:
                self._redis_client.incr(VIOLATIONS_KEY)
                self._redis_client.set(
                    f"{VIOLATIONS_KEY}:last_timestamp", datetime.now(UTC).timestamp()
                )
            except Exception as e:
                logger.warning(f"Could not record violation to Redis: {e}")

    def record_query(self, latency_ms: float = 0.0) -> None:
        """Record a constitution query."""
        self._query_count += 1
        if latency_ms > 0:
            self._latency_samples.append(latency_ms)
            # Keep only recent samples
            if len(self._latency_samples) > 1000:
                self._latency_samples = self._latency_samples[-1000:]

        if self._redis_client:
            try:
                self._redis_client.incr(QUERY_COUNT_KEY)
            except Exception as e:
                logger.warning(f"Could not record query to Redis: {e}")
