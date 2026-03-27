"""Core Aggregation Logic for Local CI Metrics.

Provides aggregation of historical metrics by time windows (day/week/month)
and trend analysis computation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ci.metrics.models import (
        AggregatedMetric,
        AggregationWindow,
        MetricPoint,
        Trend,
    )

from src.ci.metrics.models import (
    AggregatedMetric,
    AggregatedMetricsOutput,
    AggregationWindow,
    MetricPoint,
    Trend,
)


class MetricsAggregator:
    """Aggregates metric points by time windows and computes trends.

    Example:
        >>> aggregator = MetricsAggregator()
        >>> aggregator.add_metric(metric_point)
        >>> aggregated = aggregator.aggregate(window=AggregationWindow.DAILY)
        >>> trends = aggregator.compute_trends(AggregationWindow.DAILY)
    """

    def __init__(self) -> None:
        """Initialize the metrics aggregator."""
        self._metrics: list[MetricPoint] = []
        self._metrics_by_window: dict[AggregationWindow, list[MetricPoint]] = (
            defaultdict(list)
        )

    def add_metric(self, metric: MetricPoint) -> None:
        """Add a metric point to the aggregator.

        Args:
            metric: MetricPoint to add
        """
        self._metrics.append(metric)
        for window in AggregationWindow:
            if self._is_in_window(metric, window):
                self._metrics_by_window[window].append(metric)

    def add_metrics(self, metrics: list[MetricPoint]) -> None:
        """Add multiple metric points to the aggregator.

        Args:
            metrics: List of MetricPoints to add
        """
        for metric in metrics:
            self.add_metric(metric)

    def clear(self) -> None:
        """Clear all stored metrics."""
        self._metrics.clear()
        self._metrics_by_window.clear()

    def _is_in_window(self, metric: MetricPoint, window: AggregationWindow) -> bool:
        """Check if a metric point falls within its timestamp's window.

        Args:
            metric: MetricPoint to check
            window: Aggregation window to check against

        Returns:
            True if metric should be grouped in this window
        """
        if not metric.timestamp:
            return False

        metric_dt = metric.get_datetime()
        now = datetime.now(UTC)

        # Check if metric is within the last N periods based on window
        if window == AggregationWindow.DAILY:
            # Include metrics from the last 30 days
            cutoff = now - timedelta(days=30)
            return metric_dt >= cutoff
        elif window == AggregationWindow.WEEKLY:
            # Include metrics from the last 12 weeks
            cutoff = now - timedelta(weeks=12)
            return metric_dt >= cutoff
        elif window == AggregationWindow.MONTHLY:
            # Include metrics from the last 12 months
            cutoff = now - timedelta(days=365)
            return metric_dt >= cutoff

        return False

    def _get_window_bounds(
        self,
        dt: datetime,
        window: AggregationWindow,
    ) -> tuple[datetime, datetime]:
        """Get the start and end bounds for a time window containing dt.

        Args:
            dt: Datetime to get bounds for
            window: Aggregation window type

        Returns:
            Tuple of (window_start, window_end)
        """
        if window == AggregationWindow.DAILY:
            # Start of day
            window_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(days=1)
        elif window == AggregationWindow.WEEKLY:
            # Start of week (Monday)
            days_since_monday = dt.weekday()
            window_start = (dt - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            window_end = window_start + timedelta(weeks=1)
        else:  # MONTHLY
            # Start of month
            window_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # End of month (next month's first day)
            if window_start.month == 12:
                window_end = window_start.replace(year=window_start.year + 1, month=1)
            else:
                window_end = window_start.replace(month=window_start.month + 1)

        return window_start, window_end

    def _group_by_window(
        self,
        metrics: list[MetricPoint],
        window: AggregationWindow,
    ) -> dict[str, list[MetricPoint]]:
        """Group metrics by time window.

        Args:
            metrics: List of metric points
            window: Window type to group by

        Returns:
            Dict mapping window key to list of metrics in that window
        """
        grouped: dict[str, list[MetricPoint]] = defaultdict(list)

        for metric in metrics:
            if not metric.timestamp:
                continue

            metric_dt = metric.get_datetime()
            window_start, window_end = self._get_window_bounds(metric_dt, window)

            # Create a key for this window
            window_key = window_start.strftime("%Y-%m-%d")
            if window == AggregationWindow.WEEKLY:
                window_key = f"{window_start.strftime('%Y-%W')}"
            elif window == AggregationWindow.MONTHLY:
                window_key = window_start.strftime("%Y-%m")

            grouped[window_key].append(metric)

        return grouped

    def aggregate(self, window: AggregationWindow) -> list[AggregatedMetric]:
        """Aggregate metrics by the specified time window.

        Args:
            window: Time window for aggregation

        Returns:
            List of AggregatedMetric, one per time window that has data
        """
        if window not in self._metrics_by_window:
            return []

        metrics = self._metrics_by_window[window]
        if not metrics:
            return []

        grouped = self._group_by_window(metrics, window)
        results: list[AggregatedMetric] = []

        # Sort window keys chronologically
        for window_key in sorted(grouped.keys()):
            window_metrics = grouped[window_key]
            if not window_metrics:
                continue

            # Calculate aggregate statistics
            test_counts = [m.test_count for m in window_metrics]
            durations = [m.duration for m in window_metrics]
            cache_hit_rates = [m.cache_hit_rate for m in window_metrics]
            parallel_speedups = [m.parallel_speedup for m in window_metrics]
            worker_utilizations = [m.worker_utilization for m in window_metrics]
            tests_passed = [m.tests_passed for m in window_metrics]
            tests_failed = [m.tests_failed for m in window_metrics]

            # Get window bounds from first metric
            first_dt = window_metrics[0].get_datetime()
            window_start, window_end = self._get_window_bounds(first_dt, window)

            aggregated = AggregatedMetric(
                window=window,
                window_start=window_start,
                window_end=window_end,
                test_count_avg=sum(test_counts) / len(test_counts),
                test_count_min=min(test_counts),
                test_count_max=max(test_counts),
                duration_avg=sum(durations) / len(durations),
                duration_min=min(durations),
                duration_max=max(durations),
                cache_hit_rate_avg=sum(cache_hit_rates) / len(cache_hit_rates),
                cache_hit_rate_min=min(cache_hit_rates),
                cache_hit_rate_max=max(cache_hit_rates),
                parallel_speedup_avg=(
                    sum(parallel_speedups) / len(parallel_speedups)
                    if parallel_speedups
                    else 0.0
                ),
                worker_utilization_avg=(
                    sum(worker_utilizations) / len(worker_utilizations)
                    if worker_utilizations
                    else 0.0
                ),
                tests_passed_total=sum(tests_passed),
                tests_failed_total=sum(tests_failed),
                sample_count=len(window_metrics),
            )
            results.append(aggregated)

        return results

    def aggregate_all_windows(self) -> dict[str, list[AggregatedMetric]]:
        """Aggregate metrics for all time windows.

        Returns:
            Dict mapping window name to list of aggregated metrics
        """
        results: dict[str, list[AggregatedMetric]] = {}
        for window in AggregationWindow:
            aggregated = self.aggregate(window)
            if aggregated:
                results[window.value] = aggregated
        return results

    def compute_trends(
        self,
        window: AggregationWindow,
    ) -> list[Trend]:
        """Compute trends for all metrics using the specified window.

        Args:
            window: Time window to use for trend calculation

        Returns:
            List of Trend objects for each metric
        """
        aggregated = self.aggregate(window)
        if not aggregated:
            return []

        trends: list[Trend] = []

        # Metrics to analyze trends for
        metric_names = [
            "cache_hit_rate",
            "duration",
            "parallel_speedup",
            "worker_utilization",
            "test_count",
        ]

        for metric_name in metric_names:
            # Extract values in chronological order
            values: list[float] = []
            for agg in sorted(aggregated, key=lambda x: x.window_start):
                if metric_name == "cache_hit_rate":
                    values.append(agg.cache_hit_rate_avg)
                elif metric_name == "duration":
                    values.append(agg.duration_avg)
                elif metric_name == "parallel_speedup":
                    values.append(agg.parallel_speedup_avg)
                elif metric_name == "worker_utilization":
                    values.append(agg.worker_utilization_avg)
                elif metric_name == "test_count":
                    values.append(agg.test_count_avg)

            if len(values) >= 2:
                trend = Trend.calculate(metric_name, window, values)
                trends.append(trend)

        return trends

    def compute_trends_all_windows(self) -> dict[str, list[Trend]]:
        """Compute trends for all time windows.

        Returns:
            Dict mapping window name to list of trends
        """
        results: dict[str, list[Trend]] = {}
        for window in AggregationWindow:
            trends = self.compute_trends(window)
            if trends:
                results[window.value] = trends
        return results

    def get_aggregated_output(self) -> AggregatedMetricsOutput:
        """Generate complete aggregated output with trends.

        Returns:
            AggregatedMetricsOutput containing all aggregation results and trends
        """
        now = datetime.now(UTC)
        output = AggregatedMetricsOutput(generated_at=now.isoformat())
        output.source_metrics_count = len(self._metrics)

        # Aggregate all windows
        for window in AggregationWindow:
            aggregated = self.aggregate(window)
            if aggregated:
                output.aggregation_windows[window.value] = [
                    agg.to_dict() for agg in aggregated
                ]

        # Compute trends all windows
        for window in AggregationWindow:
            trends = self.compute_trends(window)
            if trends:
                output.trends.extend([trend.to_dict() for trend in trends])

        return output


def aggregate_metrics(
    metrics: list[MetricPoint],
    window: AggregationWindow,
) -> list[AggregatedMetric]:
    """Convenience function to aggregate a list of metrics.

    Args:
        metrics: List of metric points to aggregate
        window: Time window for aggregation

    Returns:
        List of aggregated metrics
    """
    aggregator = MetricsAggregator()
    aggregator.add_metrics(metrics)
    return aggregator.aggregate(window)


def compute_metric_trends(
    metrics: list[MetricPoint],
    window: AggregationWindow,
) -> list[Trend]:
    """Convenience function to compute trends for metrics.

    Args:
        metrics: List of metric points
        window: Time window for trend calculation

    Returns:
        List of trend analyses
    """
    aggregator = MetricsAggregator()
    aggregator.add_metrics(metrics)
    return aggregator.compute_trends(window)
