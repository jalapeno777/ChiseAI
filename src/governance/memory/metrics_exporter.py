"""
Memory Metrics Exporter for ChiseAI Governance.

Exports metrics related to memory deduplication,
retrieval statistics, and optimization recommendations.

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

# Redis keys for memory metrics
MEMORY_PREFIX = "chise:governance:memory"
ENTRIES_SCANNED_KEY = f"{MEMORY_PREFIX}:entries_scanned"
DUPLICATES_FOUND_KEY = f"{MEMORY_PREFIX}:duplicates_found"
ENTRIES_REMOVED_KEY = f"{MEMORY_PREFIX}:entries_removed"
RETRIEVAL_HITS_KEY = f"{MEMORY_PREFIX}:retrieval_hits"
RETRIEVAL_MISSES_KEY = f"{MEMORY_PREFIX}:retrieval_misses"


class MemoryMetricsExporter(BaseMetricsExporter):
    """
    Metrics exporter for the Memory Deduplication governance feature.

    Collects and exports:
    - Deduplication statistics (scanned, duplicates, removed)
    - Memory retrieval hit/miss rate
    - Storage savings
    - Optimization recommendations count
    - Feature flag state

    Example:
        exporter = MemoryMetricsExporter(redis_client=redis)
        points = exporter.collect()
        # Returns metrics about memory optimization
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the memory metrics exporter.

        Args:
            influx_client: Optional InfluxDB client
            redis_client: Optional Redis client for reading metrics
        """
        super().__init__(
            feature_name="memory",
            influx_client=influx_client,
            redis_client=redis_client,
        )

        # In-memory counters
        self._entries_scanned = 0
        self._duplicates_found = 0
        self._entries_removed = 0
        self._bytes_saved = 0
        self._retrieval_hits = 0
        self._retrieval_misses = 0
        self._recommendations_generated = 0

    def collect(self) -> list[MetricPoint]:
        """
        Collect memory-related metrics.

        Returns:
            List of MetricPoint objects with memory metrics
        """
        points: list[MetricPoint] = []
        now = datetime.now(UTC)

        # 1. Entries scanned
        entries_scanned = self._get_entries_scanned()
        points.append(
            MetricPoint(
                name="governance.memory.dedup.scanned",
                value=float(entries_scanned),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "dedup"},
            )
        )

        # 2. Duplicates found
        duplicates_found = self._get_duplicates_found()
        points.append(
            MetricPoint(
                name="governance.memory.dedup.duplicates_found",
                value=float(duplicates_found),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "dedup"},
            )
        )

        # 3. Entries removed
        entries_removed = self._get_entries_removed()
        points.append(
            MetricPoint(
                name="governance.memory.dedup.entries_removed",
                value=float(entries_removed),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "dedup"},
            )
        )

        # 4. Deduplication ratio
        if entries_scanned > 0:
            dedup_ratio = (duplicates_found / entries_scanned) * 100
            points.append(
                MetricPoint(
                    name="governance.memory.dedup.ratio",
                    value=dedup_ratio,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "memory", "operation": "dedup"},
                    fields={"unit": "percent"},
                )
            )

        # 5. Bytes saved
        bytes_saved = self._get_bytes_saved()
        points.append(
            MetricPoint(
                name="governance.memory.dedup.bytes_saved",
                value=float(bytes_saved),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "dedup"},
                fields={"unit": "bytes"},
            )
        )

        # 6. Retrieval hit rate
        hits = self._get_retrieval_hits()
        misses = self._get_retrieval_misses()
        total_retrievals = hits + misses

        points.append(
            MetricPoint(
                name="governance.memory.retrieval.hits",
                value=float(hits),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "retrieval"},
            )
        )

        points.append(
            MetricPoint(
                name="governance.memory.retrieval.misses",
                value=float(misses),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "retrieval"},
            )
        )

        if total_retrievals > 0:
            hit_rate = (hits / total_retrievals) * 100
            points.append(
                MetricPoint(
                    name="governance.memory.retrieval.hit_rate",
                    value=hit_rate,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "memory", "operation": "retrieval"},
                    fields={"unit": "percent"},
                )
            )

        # 7. Optimization recommendations
        recommendations = self._get_recommendations_count()
        points.append(
            MetricPoint(
                name="governance.memory.optimization.recommendations",
                value=float(recommendations),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "memory", "operation": "optimization"},
            )
        )

        # 8. Feature flag state
        is_enabled = self._is_feature_enabled()
        points.append(
            MetricPoint(
                name="governance.memory.enabled",
                value=1.0 if is_enabled else 0.0,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "memory"},
            )
        )

        return points

    def _get_entries_scanned(self) -> int:
        """Get total entries scanned."""
        if self._redis_client:
            try:
                val = self._redis_client.get(ENTRIES_SCANNED_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._entries_scanned

    def _get_duplicates_found(self) -> int:
        """Get duplicates found count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(DUPLICATES_FOUND_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._duplicates_found

    def _get_entries_removed(self) -> int:
        """Get entries removed count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(ENTRIES_REMOVED_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._entries_removed

    def _get_bytes_saved(self) -> int:
        """Get bytes saved from deduplication."""
        if self._redis_client:
            try:
                val = self._redis_client.get(f"{MEMORY_PREFIX}:bytes_saved")
                if val:
                    return int(val)
            except Exception:
                pass
        return self._bytes_saved

    def _get_retrieval_hits(self) -> int:
        """Get retrieval hit count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(RETRIEVAL_HITS_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._retrieval_hits

    def _get_retrieval_misses(self) -> int:
        """Get retrieval miss count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(RETRIEVAL_MISSES_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._retrieval_misses

    def _get_recommendations_count(self) -> int:
        """Get optimization recommendations count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(f"{MEMORY_PREFIX}:recommendations")
                if val:
                    return int(val)
            except Exception:
                pass
        return self._recommendations_generated

    def _is_feature_enabled(self) -> bool:
        """Check if memory dedup feature is enabled."""
        if self._redis_client:
            try:
                val = self._redis_client.get(
                    "chise:feature_flags:governance:memory_dedup_enabled"
                )
                return val == b"true" or val == "true"
            except Exception:
                pass
        return False

    # Methods for updating metrics
    def record_dedup_run(
        self,
        scanned: int,
        duplicates: int,
        removed: int,
        bytes_saved: int = 0,
    ) -> None:
        """Record a deduplication run."""
        self._entries_scanned += scanned
        self._duplicates_found += duplicates
        self._entries_removed += removed
        self._bytes_saved += bytes_saved

        if self._redis_client:
            try:
                self._redis_client.incrby(ENTRIES_SCANNED_KEY, scanned)
                self._redis_client.incrby(DUPLICATES_FOUND_KEY, duplicates)
                self._redis_client.incrby(ENTRIES_REMOVED_KEY, removed)
                self._redis_client.incrby(f"{MEMORY_PREFIX}:bytes_saved", bytes_saved)
            except Exception as e:
                logger.warning(f"Could not record dedup run to Redis: {e}")

    def record_retrieval(self, hit: bool) -> None:
        """Record a memory retrieval event."""
        if hit:
            self._retrieval_hits += 1
        else:
            self._retrieval_misses += 1

        if self._redis_client:
            try:
                if hit:
                    self._redis_client.incr(RETRIEVAL_HITS_KEY)
                else:
                    self._redis_client.incr(RETRIEVAL_MISSES_KEY)
            except Exception as e:
                logger.warning(f"Could not record retrieval to Redis: {e}")

    def record_recommendation(self) -> None:
        """Record an optimization recommendation generated."""
        self._recommendations_generated += 1

        if self._redis_client:
            try:
                self._redis_client.incr(f"{MEMORY_PREFIX}:recommendations")
            except Exception as e:
                logger.warning(f"Could not record recommendation to Redis: {e}")
