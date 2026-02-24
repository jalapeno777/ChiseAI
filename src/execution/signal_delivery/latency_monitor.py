"""Latency monitoring for signal delivery.

Tracks signal delivery latency, calculates p95/p99 metrics,
and alerts when thresholds are exceeded.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LatencyStage(Enum):
    """Stages in signal delivery pipeline."""

    GENERATION = "generation"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    DELIVERY = "delivery"
    ACKNOWLEDGMENT = "acknowledgment"
    TOTAL = "total"


@dataclass
class LatencyThresholds:
    """Thresholds for latency alerts.

    Attributes:
        warning_ms: Warning threshold in milliseconds
        critical_ms: Critical threshold in milliseconds
        p95_target_ms: Target for p95 latency
        p99_target_ms: Target for p99 latency
    """

    warning_ms: float = 500.0
    critical_ms: float = 1000.0
    p95_target_ms: float = 800.0
    p99_target_ms: float = 950.0

    @classmethod
    def default(cls) -> LatencyThresholds:
        """Get default thresholds."""
        return cls()

    @classmethod
    def strict(cls) -> LatencyThresholds:
        """Get stricter thresholds."""
        return cls(
            warning_ms=300.0,
            critical_ms=500.0,
            p95_target_ms=400.0,
            p99_target_ms=450.0,
        )


@dataclass
class LatencyMetric:
    """Single latency measurement.

    Attributes:
        signal_id: Signal identifier
        stage: Pipeline stage
        latency_ms: Latency in milliseconds
        timestamp: When measurement was taken
        success: Whether operation succeeded
        metadata: Additional metadata
    """

    signal_id: str
    stage: str
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_slow(self, thresholds: LatencyThresholds | None = None) -> bool:
        """Check if latency is slow.

        Args:
            thresholds: Thresholds to check against

        Returns:
            True if latency exceeds warning threshold
        """
        threshold = (thresholds or LatencyThresholds.default()).warning_ms
        return self.latency_ms > threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "stage": self.stage,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "is_slow": self.is_slow(),
        }


@dataclass
class LatencyStats:
    """Statistics for latency measurements.

    Attributes:
        count: Number of measurements
        min_ms: Minimum latency
        max_ms: Maximum latency
        avg_ms: Average latency
        p50_ms: 50th percentile
        p95_ms: 95th percentile
        p99_ms: 99th percentile
    """

    count: int = 0
    min_ms: float = 0.0
    max_ms: float = 0.0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "count": self.count,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
        }


class LatencyMonitor:
    """Monitor for tracking signal delivery latency.

    Tracks latency metrics by stage, calculates percentiles,
    and identifies slow deliveries.

    Example:
        monitor = LatencyMonitor()
        monitor.record(LatencyMetric("sig-1", "delivery", 150))
        stats = monitor.get_stats("delivery")
        print(f"P95 latency: {stats.p95_ms}ms")
    """

    def __init__(
        self,
        thresholds: LatencyThresholds | None = None,
        history_size: int = 10000,
    ):
        """Initialize latency monitor.

        Args:
            thresholds: Latency thresholds for alerting
            history_size: Maximum number of metrics to keep per stage
        """
        self.thresholds = thresholds or LatencyThresholds.default()
        self.history_size = history_size

        # Store metrics by stage
        self._metrics: dict[str, list[LatencyMetric]] = defaultdict(list)

        # Alert tracking
        self._slow_count = 0
        self._total_count = 0

    def record_latency(
        self,
        signal_id: str,
        stage: str,
        latency_ms: float,
        success: bool = True,
    ) -> bool:
        """Record a latency measurement.

        This is a convenience method for simple latency recording.

        Args:
            signal_id: Signal identifier
            stage: Pipeline stage (e.g., "generation", "delivery")
            latency_ms: Latency in milliseconds
            success: Whether operation succeeded

        Returns:
            True if latency was slow (exceeded warning threshold)
        """
        metric = LatencyMetric(
            signal_id=signal_id,
            stage=stage,
            latency_ms=latency_ms,
            success=success,
        )
        return self.record(metric)

    def record(self, metric: LatencyMetric) -> bool:
        """Record a latency metric.

        Args:
            metric: LatencyMetric to record

        Returns:
            True if metric was slow
        """
        self._metrics[metric.stage].append(metric)
        self._total_count += 1

        # Trim history
        if len(self._metrics[metric.stage]) > self.history_size:
            self._metrics[metric.stage] = self._metrics[metric.stage][
                -self.history_size :
            ]

        # Check if slow
        if metric.is_slow(self.thresholds):
            self._slow_count += 1
            logger.warning(
                f"Slow delivery detected: {metric.signal_id} "
                f"stage={metric.stage} latency={metric.latency_ms:.0f}ms"
            )
            return True

        return False

    def record_stage(
        self,
        signal_id: str,
        stage: str,
        latency_ms: float,
        success: bool = True,
    ) -> LatencyMetric:
        """Record latency for a specific stage.

        Args:
            signal_id: Signal identifier
            stage: Pipeline stage
            latency_ms: Latency in milliseconds
            success: Whether operation succeeded

        Returns:
            Created LatencyMetric
        """
        metric = LatencyMetric(
            signal_id=signal_id,
            stage=stage,
            latency_ms=latency_ms,
            success=success,
        )
        self.record(metric)
        return metric

    def get_stats(
        self,
        stage: str | None = None,
        since: datetime | None = None,
    ) -> LatencyStats:
        """Get latency statistics.

        Args:
            stage: Optional stage to filter by
            since: Only include metrics after this time

        Returns:
            LatencyStats with calculated metrics
        """
        # Collect metrics
        if stage:
            metrics = self._metrics.get(stage, [])
        else:
            metrics = []
            for stage_metrics in self._metrics.values():
                metrics.extend(stage_metrics)

        # Filter by time
        if since:
            metrics = [m for m in metrics if m.timestamp >= since]

        if not metrics:
            return LatencyStats()

        # Calculate stats
        latencies = sorted(m.latency_ms for m in metrics)
        count = len(latencies)

        return LatencyStats(
            count=count,
            min_ms=latencies[0],
            max_ms=latencies[-1],
            avg_ms=sum(latencies) / count,
            p50_ms=self._percentile(latencies, 50),
            p95_ms=self._percentile(latencies, 95),
            p99_ms=self._percentile(latencies, 99),
        )

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

    def get_slow_metrics(
        self,
        stage: str | None = None,
        limit: int = 100,
    ) -> list[LatencyMetric]:
        """Get list of slow metrics.

        Args:
            stage: Optional stage to filter by
            limit: Maximum number to return

        Returns:
            List of slow LatencyMetric instances
        """
        # Collect metrics
        if stage:
            metrics = self._metrics.get(stage, [])
        else:
            metrics = []
            for stage_metrics in self._metrics.values():
                metrics.extend(stage_metrics)

        # Filter slow
        slow = [m for m in metrics if m.is_slow(self.thresholds)]

        # Sort by latency descending
        slow.sort(key=lambda m: m.latency_ms, reverse=True)

        return slow[:limit]

    def get_stage_breakdown(self) -> dict[str, LatencyStats]:
        """Get latency breakdown by stage.

        Returns:
            Dictionary of stage -> stats
        """
        result = {}
        for stage in self._metrics:
            result[stage] = self.get_stats(stage)
        return result

    def check_thresholds(self) -> list[dict[str, Any]]:
        """Check if thresholds are exceeded.

        Returns:
            List of threshold violations
        """
        violations = []

        for stage in self._metrics:
            stats = self.get_stats(stage)

            # Check p95
            if stats.p95_ms > self.thresholds.p95_target_ms:
                violations.append(
                    {
                        "stage": stage,
                        "type": "p95_exceeded",
                        "value": stats.p95_ms,
                        "threshold": self.thresholds.p95_target_ms,
                        "message": f"P95 latency {stats.p95_ms:.0f}ms exceeds target {self.thresholds.p95_target_ms}ms",
                    }
                )

            # Check p99
            if stats.p99_ms > self.thresholds.p99_target_ms:
                violations.append(
                    {
                        "stage": stage,
                        "type": "p99_exceeded",
                        "value": stats.p99_ms,
                        "threshold": self.thresholds.p99_target_ms,
                        "message": f"P99 latency {stats.p99_ms:.0f}ms exceeds target {self.thresholds.p99_target_ms}ms",
                    }
                )

        return violations

    def get_summary(self) -> dict[str, Any]:
        """Get latency summary.

        Returns:
            Dictionary with latency summary
        """
        total_stats = self.get_stats()
        stage_breakdown = self.get_stage_breakdown()
        violations = self.check_thresholds()

        slow_rate = (
            self._slow_count / self._total_count * 100 if self._total_count > 0 else 0.0
        )

        return {
            "total_metrics": self._total_count,
            "slow_metrics": self._slow_count,
            "slow_rate": round(slow_rate, 2),
            "overall_stats": total_stats.to_dict(),
            "stages": {
                stage: stats.to_dict() for stage, stats in stage_breakdown.items()
            },
            "threshold_violations": len(violations),
            "thresholds": {
                "warning_ms": self.thresholds.warning_ms,
                "critical_ms": self.thresholds.critical_ms,
                "p95_target_ms": self.thresholds.p95_target_ms,
                "p99_target_ms": self.thresholds.p99_target_ms,
            },
        }

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()
        self._slow_count = 0
        self._total_count = 0

    def health_check(self) -> dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result
        """
        violations = self.check_thresholds()
        stats = self.get_stats()

        # Determine health
        if any(v["value"] > self.thresholds.critical_ms for v in violations):
            status = "unhealthy"
        elif violations:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "p95_ms": round(stats.p95_ms, 2),
            "p99_ms": round(stats.p99_ms, 2),
            "violations": len(violations),
            "summary": self.get_summary(),
        }
