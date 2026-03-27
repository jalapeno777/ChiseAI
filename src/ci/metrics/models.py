"""Local CI Metrics Models.

Data models for metrics aggregation system:
- MetricPoint: Individual metric data point with timestamp
- AggregationWindow: Time window for aggregation (day/week/month)
- Trend: Trend analysis result for a metric
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AggregationWindow(Enum):
    """Time window for metric aggregation."""

    DAILY = "day"
    WEEKLY = "week"
    MONTHLY = "month"

    def __str__(self) -> str:
        return self.value


@dataclass
class MetricPoint:
    """Individual metric data point with timestamp.

    Attributes:
        timestamp: ISO format timestamp of the measurement
        test_count: Number of tests run
        duration: Total execution time in seconds
        cache_hit_rate: Cache hit percentage (0-100)
        parallel_speedup: Speedup factor vs sequential execution
        worker_utilization: Worker utilization ratio (0-1)
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        tests_passed: Number of passing tests
        tests_failed: Number of failing tests
        metadata: Additional metadata dict
    """

    timestamp: str
    test_count: int = 0
    duration: float = 0.0
    cache_hit_rate: float = 0.0
    parallel_speedup: float = 0.0
    worker_utilization: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricPoint:
        """Create MetricPoint from dictionary (e.g., from JSON).

        Args:
            data: Dictionary containing metric data

        Returns:
            MetricPoint instance
        """
        # Handle nested structure from local_ci_metrics_exporter.py
        cache_data = data.get("cache", {})
        parallel_data = data.get("parallel", {})
        speedup_data = data.get("speedup", {})

        return cls(
            timestamp=data.get("timestamp", ""),
            test_count=data.get("test_count", speedup_data.get("tests_run", 0)),
            duration=data.get("duration", speedup_data.get("total_duration", 0.0)),
            cache_hit_rate=data.get("cache_hit_rate", cache_data.get("hit_rate", 0.0)),
            parallel_speedup=data.get(
                "parallel_speedup", parallel_data.get("speedup", 0.0)
            ),
            worker_utilization=data.get(
                "worker_utilization", parallel_data.get("worker_utilization", 0.0)
            ),
            cache_hits=cache_data.get("hits", 0),
            cache_misses=cache_data.get("misses", 0),
            tests_passed=speedup_data.get("tests_passed", data.get("tests_passed", 0)),
            tests_failed=speedup_data.get("tests_failed", data.get("tests_failed", 0)),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the metric point
        """
        return {
            "timestamp": self.timestamp,
            "test_count": self.test_count,
            "duration": self.duration,
            "cache_hit_rate": self.cache_hit_rate,
            "parallel_speedup": self.parallel_speedup,
            "worker_utilization": self.worker_utilization,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "metadata": self.metadata,
        }

    def get_datetime(self) -> datetime:
        """Parse timestamp to datetime object.

        Returns:
            datetime object in UTC
        """
        if self.timestamp:
            # Handle ISO format with timezone
            return datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        return datetime.now(UTC)


@dataclass
class AggregatedMetric:
    """Aggregated metrics for a time window.

    Attributes:
        window: The aggregation window type
        window_start: Start of the aggregation window
        window_end: End of the aggregation window
        test_count_avg: Average test count
        test_count_min: Minimum test count
        test_count_max: Maximum test count
        duration_avg: Average duration
        duration_min: Minimum duration
        duration_max: Maximum duration
        cache_hit_rate_avg: Average cache hit rate
        cache_hit_rate_min: Minimum cache hit rate
        cache_hit_rate_max: Maximum cache hit rate
        parallel_speedup_avg: Average parallel speedup
        worker_utilization_avg: Average worker utilization
        tests_passed_total: Total tests passed
        tests_failed_total: Total tests failed
        sample_count: Number of samples in window
    """

    window: AggregationWindow
    window_start: datetime
    window_end: datetime
    test_count_avg: float = 0.0
    test_count_min: int = 0
    test_count_max: int = 0
    duration_avg: float = 0.0
    duration_min: float = 0.0
    duration_max: float = 0.0
    cache_hit_rate_avg: float = 0.0
    cache_hit_rate_min: float = 0.0
    cache_hit_rate_max: float = 0.0
    parallel_speedup_avg: float = 0.0
    worker_utilization_avg: float = 0.0
    tests_passed_total: int = 0
    tests_failed_total: int = 0
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation
        """
        return {
            "window": self.window.value,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "test_count_avg": self.test_count_avg,
            "test_count_min": self.test_count_min,
            "test_count_max": self.test_count_max,
            "duration_avg": self.duration_avg,
            "duration_min": self.duration_min,
            "duration_max": self.duration_max,
            "cache_hit_rate_avg": self.cache_hit_rate_avg,
            "cache_hit_rate_min": self.cache_hit_rate_min,
            "cache_hit_rate_max": self.cache_hit_rate_max,
            "parallel_speedup_avg": self.parallel_speedup_avg,
            "worker_utilization_avg": self.worker_utilization_avg,
            "tests_passed_total": self.tests_passed_total,
            "tests_failed_total": self.tests_failed_total,
            "sample_count": self.sample_count,
        }


@dataclass
class Trend:
    """Trend analysis result for a metric.

    Attributes:
        metric_name: Name of the metric being analyzed
        window: The aggregation window used
        direction: Trend direction ('increasing', 'decreasing', 'stable')
        slope: Linear regression slope (change per period)
        intercept: Linear regression intercept
        r_squared: R-squared coefficient for fit quality
        current_value: Most recent value
        previous_value: Previous period value
        percent_change: Percentage change from previous to current
    """

    metric_name: str
    window: AggregationWindow
    direction: str = "stable"
    slope: float = 0.0
    intercept: float = 0.0
    r_squared: float = 0.0
    current_value: float = 0.0
    previous_value: float = 0.0
    percent_change: float = 0.0

    def __post_init__(self) -> None:
        """Validate direction is one of allowed values."""
        if self.direction not in ("increasing", "decreasing", "stable"):
            self.direction = "stable"

    @classmethod
    def calculate(
        cls,
        metric_name: str,
        window: AggregationWindow,
        values: list[float],
    ) -> Trend:
        """Calculate trend from a list of values.

        Uses simple linear regression to determine trend direction.

        Args:
            metric_name: Name of the metric
            window: Aggregation window used
            values: List of metric values in chronological order

        Returns:
            Trend instance with analysis results
        """
        trend = cls(metric_name=metric_name, window=window)

        if len(values) < 2:
            trend.direction = "stable"
            trend.current_value = values[0] if values else 0.0
            trend.previous_value = trend.current_value
            return trend

        trend.current_value = values[-1]
        trend.previous_value = values[0]

        # Calculate percent change
        if trend.previous_value != 0:
            trend.percent_change = (
                (trend.current_value - trend.previous_value) / trend.previous_value
            ) * 100

        # Simple linear regression
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        # Calculate slope and intercept
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator != 0:
            trend.slope = numerator / denominator
            trend.intercept = y_mean - trend.slope * x_mean

            # Calculate R-squared
            ss_res = sum(
                (v - (trend.slope * i + trend.intercept)) ** 2
                for i, v in enumerate(values)
            )
            ss_tot = sum((v - y_mean) ** 2 for v in values)
            trend.r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # Determine direction
        if abs(trend.slope) < 0.01:  # Threshold for stability
            trend.direction = "stable"
        elif trend.slope > 0:
            trend.direction = "increasing"
        else:
            trend.direction = "decreasing"

        return trend

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation
        """
        return {
            "metric_name": self.metric_name,
            "window": self.window.value,
            "direction": self.direction,
            "slope": self.slope,
            "intercept": self.intercept,
            "r_squared": self.r_squared,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "percent_change": self.percent_change,
        }


@dataclass
class AggregatedMetricsOutput:
    """Complete aggregated metrics output.

    Attributes:
        generated_at: Timestamp when aggregation was generated
        aggregation_windows: Dict mapping window type to list of aggregated data
        trends: List of trend analyses
        source_metrics_count: Number of source metrics processed
    """

    generated_at: str
    aggregation_windows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    trends: list[dict[str, Any]] = field(default_factory=list)
    source_metrics_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation
        """
        return {
            "generated_at": self.generated_at,
            "aggregation_windows": self.aggregation_windows,
            "trends": self.trends,
            "source_metrics_count": self.source_metrics_count,
        }
