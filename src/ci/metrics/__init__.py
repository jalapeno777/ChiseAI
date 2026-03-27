"""Local CI Metrics Module.

Provides metrics aggregation and trend analysis for Local CI metrics.

Example:
    >>> from src.ci.metrics import MetricsAggregator, MetricsStorage
    >>> storage = MetricsStorage()
    >>> metrics = storage.load_metrics("_bmad-output/ci/metrics.json")
    >>> aggregator = MetricsAggregator()
    >>> aggregator.add_metrics(metrics)
    >>> output = aggregator.get_aggregated_output()
"""

from __future__ import annotations

from src.ci.metrics.aggregator import (
    MetricsAggregator,
    aggregate_metrics,
    compute_metric_trends,
)
from src.ci.metrics.models import (
    AggregatedMetric,
    AggregatedMetricsOutput,
    AggregationWindow,
    MetricPoint,
    Trend,
)
from src.ci.metrics.storage import MetricsStorage, load_metrics_history

__all__ = [
    # Models
    "MetricPoint",
    "AggregatedMetric",
    "AggregatedMetricsOutput",
    "AggregationWindow",
    "Trend",
    # Aggregator
    "MetricsAggregator",
    "aggregate_metrics",
    "compute_metric_trends",
    # Storage
    "MetricsStorage",
    "load_metrics_history",
]
