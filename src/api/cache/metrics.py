"""Cache metrics collection and reporting.

Tracks cache hit/miss rates, response times, and exports metrics for
Grafana monitoring.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheMetricsSnapshot:
    """Snapshot of cache metrics at a point in time."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_response_time_ms: float = 0.0
    hit_response_time_ms: float = 0.0
    miss_response_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def total_requests(self) -> int:
        """Total number of cache requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self.total_requests
        if total == 0:
            return 0.0
        return (self.hits / total) * 100

    @property
    def miss_rate(self) -> float:
        """Cache miss rate as a percentage."""
        total = self.total_requests
        if total == 0:
            return 0.0
        return (self.misses / total) * 100

    @property
    def avg_response_time_ms(self) -> float:
        """Average response time in milliseconds."""
        total = self.total_requests
        if total == 0:
            return 0.0
        return self.total_response_time_ms / total

    @property
    def avg_hit_time_ms(self) -> float:
        """Average cache hit response time."""
        if self.hits == 0:
            return 0.0
        return self.hit_response_time_ms / self.hits

    @property
    def avg_miss_time_ms(self) -> float:
        """Average cache miss response time."""
        if self.misses == 0:
            return 0.0
        return self.miss_response_time_ms / self.misses

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate, 2),
            "miss_rate": round(self.miss_rate, 2),
            "avg_response_time_ms": round(self.avg_response_time_ms, 3),
            "avg_hit_time_ms": round(self.avg_hit_time_ms, 3),
            "avg_miss_time_ms": round(self.avg_miss_time_ms, 3),
            "timestamp": self.timestamp,
        }


class CacheMetricsCollector:
    """Collects and reports cache metrics.

    Thread-safe metrics collection for cache operations with
    export capabilities for monitoring systems.
    """

    def __init__(self, window_size: int = 1000) -> None:
        """Initialize metrics collector.

        Args:
            window_size: Number of operations to keep in sliding window
        """
        self.window_size = window_size
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_response_time_ms = 0.0
        self._hit_response_time_ms = 0.0
        self._miss_response_time_ms = 0.0
        self._operation_times: list[tuple[bool, float]] = []  # (is_hit, duration_ms)

    def record_hit(self, duration_ms: float) -> None:
        """Record a cache hit.

        Args:
            duration_ms: Response time in milliseconds
        """
        self._hits += 1
        self._total_response_time_ms += duration_ms
        self._hit_response_time_ms += duration_ms
        self._operation_times.append((True, duration_ms))
        self._trim_window()

    def record_miss(self, duration_ms: float) -> None:
        """Record a cache miss.

        Args:
            duration_ms: Response time in milliseconds
        """
        self._misses += 1
        self._total_response_time_ms += duration_ms
        self._miss_response_time_ms += duration_ms
        self._operation_times.append((False, duration_ms))
        self._trim_window()

    def record_eviction(self) -> None:
        """Record a cache eviction."""
        self._evictions += 1

    def _trim_window(self) -> None:
        """Trim operation window to size limit."""
        if len(self._operation_times) > self.window_size:
            self._operation_times = self._operation_times[-self.window_size :]

    def get_snapshot(self) -> CacheMetricsSnapshot:
        """Get current metrics snapshot."""
        return CacheMetricsSnapshot(
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            total_response_time_ms=self._total_response_time_ms,
            hit_response_time_ms=self._hit_response_time_ms,
            miss_response_time_ms=self._miss_response_time_ms,
        )

    def get_window_stats(self) -> dict[str, Any]:
        """Get statistics for the current operation window."""
        if not self._operation_times:
            return {
                "window_size": 0,
                "window_hits": 0,
                "window_misses": 0,
                "window_hit_rate": 0.0,
                "avg_window_time_ms": 0.0,
            }

        hits = sum(1 for is_hit, _ in self._operation_times if is_hit)
        misses = len(self._operation_times) - hits
        total_time = sum(duration for _, duration in self._operation_times)

        return {
            "window_size": len(self._operation_times),
            "window_hits": hits,
            "window_misses": misses,
            "window_hit_rate": round((hits / len(self._operation_times)) * 100, 2),
            "avg_window_time_ms": round(total_time / len(self._operation_times), 3),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_response_time_ms = 0.0
        self._hit_response_time_ms = 0.0
        self._miss_response_time_ms = 0.0
        self._operation_times = []

    def export_prometheus_format(self, prefix: str = "chiseai_cache") -> str:
        """Export metrics in Prometheus format.

        Args:
            prefix: Metric name prefix

        Returns:
            Prometheus-formatted metrics string
        """
        snapshot = self.get_snapshot()
        window = self.get_window_stats()

        lines = [
            f"# HELP {prefix}_hits_total Total cache hits",
            f"# TYPE {prefix}_hits_total counter",
            f"{prefix}_hits_total {snapshot.hits}",
            "",
            f"# HELP {prefix}_misses_total Total cache misses",
            f"# TYPE {prefix}_misses_total counter",
            f"{prefix}_misses_total {snapshot.misses}",
            "",
            f"# HELP {prefix}_hit_rate Cache hit rate percentage",
            f"# TYPE {prefix}_hit_rate gauge",
            f"{prefix}_hit_rate {snapshot.hit_rate}",
            "",
            f"# HELP {prefix}_response_time_ms Average response time",
            f"# TYPE {prefix}_response_time_ms gauge",
            f"{prefix}_response_time_ms {snapshot.avg_response_time_ms}",
            "",
            f"# HELP {prefix}_window_hit_rate Sliding window hit rate",
            f"# TYPE {prefix}_window_hit_rate gauge",
            f"{prefix}_window_hit_rate {window['window_hit_rate']}",
        ]

        return "\n".join(lines)

    def export_grafana_json(self) -> dict[str, Any]:
        """Export metrics in Grafana-compatible JSON format.

        Returns:
            Dictionary with metrics for Grafana
        """
        snapshot = self.get_snapshot()
        window = self.get_window_stats()

        return {
            "target": "chiseai_cache_metrics",
            "datapoints": [
                [snapshot.hit_rate, int(time.time() * 1000)],
            ],
            "meta": {
                "hits": snapshot.hits,
                "misses": snapshot.misses,
                "hit_rate": snapshot.hit_rate,
                "window_hit_rate": window["window_hit_rate"],
                "avg_response_time_ms": snapshot.avg_response_time_ms,
            },
        }
