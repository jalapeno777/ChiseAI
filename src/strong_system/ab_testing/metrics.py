"""A/B Testing Metrics Collection.

Provides real-time metrics collection and aggregation for A/B tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricType(Enum):
    """Types of metrics that can be collected."""

    CONVERSION = "conversion"  # Binary success/failure
    CLICK_THROUGH = "click_through"  # Click events
    TIME_ON_PAGE = "time_on_page"  # Duration metrics
    REVENUE = "revenue"  # Revenue metrics
    ENGAGEMENT = "engagement"  # Engagement score
    BOUNCE_RATE = "bounce_rate"  # Bounce rate


@dataclass
class MetricEvent:
    """Single metric event.

    Attributes:
        session_id: Session identifier
        test_id: Test identifier
        variant: Variant assigned
        metric_type: Type of metric
        value: Metric value
        timestamp: Event timestamp
        metadata: Additional event metadata
    """

    session_id: str
    test_id: str
    variant: str
    metric_type: MetricType
    value: float
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricAggregate:
    """Aggregated metrics for a variant.

    Attributes:
        count: Number of events
        sum: Sum of values
        mean: Mean value
        variance: Variance of values
        min: Minimum value
        max: Maximum value
        stddev: Standard deviation
    """

    count: int = 0
    sum: float = 0.0
    mean: float = 0.0
    variance: float = 0.0
    min: float = float("inf")
    max: float = float("-inf")
    stddev: float = 0.0

    def add_value(self, value: float) -> None:
        """Add a value to the aggregate using Welford's algorithm."""
        self.count += 1
        self.sum += value

        # Update min/max
        self.min = min(self.min, value)
        self.max = max(self.max, value)

        # Welford's algorithm for variance
        if self.count == 1:
            self.mean = value
            self._sum_squared_diffs = 0.0
        else:
            old_mean = self.mean
            self.mean = self.mean + (value - self.mean) / self.count
            self._sum_squared_diffs = self._sum_squared_diffs + (value - old_mean) * (
                value - self.mean
            )

        # Store sample variance (divided by count - 1)
        if self.count > 1:
            self.variance = self._sum_squared_diffs / (self.count - 1)
            self.stddev = self.variance**0.5
        else:
            self.variance = 0.0
            self.stddev = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "count": self.count,
            "sum": self.sum,
            "mean": self.mean,
            "variance": self.variance,
            "min": self.min if self.count > 0 else 0.0,
            "max": self.max if self.count > 0 else 0.0,
            "stddev": self.stddev,
        }


class ABMetricsCollector:
    """Collects and aggregates metrics for A/B tests."""

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._events: list[MetricEvent] = []
        self._aggregates: dict[tuple[str, str, MetricType], MetricAggregate] = {}

    def record_event(
        self,
        session_id: str,
        test_id: str,
        variant: str,
        metric_type: MetricType,
        value: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a metric event.

        Args:
            session_id: Session identifier
            test_id: Test identifier
            variant: Variant assigned
            metric_type: Type of metric
            value: Metric value
            metadata: Additional metadata
        """
        event = MetricEvent(
            session_id=session_id,
            test_id=test_id,
            variant=variant,
            metric_type=metric_type,
            value=value,
            metadata=metadata or {},
        )
        self._events.append(event)

        # Update aggregates
        key = (test_id, variant, metric_type)
        if key not in self._aggregates:
            self._aggregates[key] = MetricAggregate()
        self._aggregates[key].add_value(value)

    def get_aggregate(
        self, test_id: str, variant: str, metric_type: MetricType
    ) -> MetricAggregate | None:
        """Get aggregated metrics for a test variant.

        Args:
            test_id: Test identifier
            variant: Variant name
            metric_type: Metric type

        Returns:
            MetricAggregate or None if no data
        """
        key = (test_id, variant, metric_type)
        return self._aggregates.get(key)

    def get_all_aggregates(self, test_id: str) -> dict[str, dict[str, Any]]:
        """Get all aggregates for a test.

        Args:
            test_id: Test identifier

        Returns:
            Dictionary mapping variant -> metric_type -> aggregate
        """
        result: dict[str, dict[str, Any]] = {}

        for (tid, variant, metric_type), aggregate in self._aggregates.items():
            if tid == test_id:
                if variant not in result:
                    result[variant] = {}
                result[variant][metric_type.value] = aggregate.to_dict()

        return result

    def get_events(
        self,
        test_id: str | None = None,
        variant: str | None = None,
        metric_type: MetricType | None = None,
    ) -> list[MetricEvent]:
        """Get metric events with optional filtering.

        Args:
            test_id: Filter by test ID
            variant: Filter by variant
            metric_type: Filter by metric type

        Returns:
            List of matching events
        """
        events = self._events

        if test_id:
            events = [e for e in events if e.test_id == test_id]
        if variant:
            events = [e for e in events if e.variant == variant]
        if metric_type:
            events = [e for e in events if e.metric_type == metric_type]

        return events

    def clear(self, test_id: str | None = None) -> None:
        """Clear metrics data.

        Args:
            test_id: Clear data for specific test, or all if None
        """
        if test_id:
            self._events = [e for e in self._events if e.test_id != test_id]
            keys_to_remove = [key for key in self._aggregates if key[0] == test_id]
            for key in keys_to_remove:
                del self._aggregates[key]
        else:
            self._events.clear()
            self._aggregates.clear()

    def get_summary(self, test_id: str) -> dict[str, Any]:
        """Get summary statistics for a test.

        Args:
            test_id: Test identifier

        Returns:
            Summary dictionary with counts and aggregates
        """
        events = self.get_events(test_id=test_id)
        aggregates = self.get_all_aggregates(test_id)

        return {
            "total_events": len(events),
            "test_id": test_id,
            "aggregates": aggregates,
            "variants": list(aggregates.keys()),
        }
