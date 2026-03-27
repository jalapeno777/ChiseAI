"""Tests for CI Metrics Aggregator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.ci.metrics.aggregator import (
    MetricsAggregator,
    aggregate_metrics,
    compute_metric_trends,
)
from src.ci.metrics.models import AggregationWindow, MetricPoint


def create_metric(days_ago: int = 0, **kwargs) -> MetricPoint:
    """Helper to create a MetricPoint with offset timestamp."""
    timestamp = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    defaults = {
        "timestamp": timestamp,
        "test_count": 100,
        "duration": 45.0,
        "cache_hit_rate": 75.0,
        "parallel_speedup": 2.0,
        "worker_utilization": 0.85,
    }
    defaults.update(kwargs)
    return MetricPoint(**defaults)


class TestMetricsAggregator:
    """Tests for MetricsAggregator class."""

    def test_add_single_metric(self) -> None:
        """Test adding a single metric."""
        aggregator = MetricsAggregator()
        metric = create_metric(days_ago=0)
        aggregator.add_metric(metric)
        assert len(aggregator._metrics) == 1

    def test_add_multiple_metrics(self) -> None:
        """Test adding multiple metrics."""
        aggregator = MetricsAggregator()
        aggregator.add_metrics([create_metric(days_ago=0), create_metric(days_ago=1)])
        assert len(aggregator._metrics) == 2

    def test_clear(self) -> None:
        """Test clearing metrics."""
        aggregator = MetricsAggregator()
        aggregator.add_metric(create_metric(days_ago=0))
        aggregator.clear()
        assert len(aggregator._metrics) == 0

    def test_aggregate_empty(self) -> None:
        """Test aggregating with no metrics."""
        aggregator = MetricsAggregator()
        result = aggregator.aggregate(AggregationWindow.DAILY)
        assert result == []

    def test_aggregate_single_day(self) -> None:
        """Test aggregating metrics from single day."""
        aggregator = MetricsAggregator()
        # Add 3 metrics from today
        for _ in range(3):
            aggregator.add_metric(create_metric(days_ago=0, test_count=100))

        result = aggregator.aggregate(AggregationWindow.DAILY)
        assert len(result) == 1
        assert result[0].sample_count == 3
        assert result[0].test_count_avg == 100.0

    def test_aggregate_multiple_days(self) -> None:
        """Test aggregating metrics across multiple days."""
        aggregator = MetricsAggregator()
        # Add metrics from different days
        aggregator.add_metric(
            create_metric(days_ago=0, test_count=100, cache_hit_rate=80.0)
        )
        aggregator.add_metric(
            create_metric(days_ago=0, test_count=110, cache_hit_rate=82.0)
        )
        aggregator.add_metric(
            create_metric(days_ago=1, test_count=90, cache_hit_rate=70.0)
        )

        result = aggregator.aggregate(AggregationWindow.DAILY)
        # Should have 2 days of aggregation
        assert len(result) == 2

        # Find today's aggregation
        today_agg = next((r for r in result if r.window_end > datetime.now(UTC)), None)
        assert today_agg is not None
        assert today_agg.sample_count == 2
        assert today_agg.test_count_avg == 105.0

    def test_aggregate_weekly(self) -> None:
        """Test weekly aggregation."""
        aggregator = MetricsAggregator()
        # Add metrics from same week
        aggregator.add_metric(create_metric(days_ago=0, test_count=100))
        aggregator.add_metric(create_metric(days_ago=1, test_count=110))
        aggregator.add_metric(create_metric(days_ago=2, test_count=90))

        result = aggregator.aggregate(AggregationWindow.WEEKLY)
        assert len(result) >= 1

    def test_aggregate_min_max(self) -> None:
        """Test min/max calculation in aggregation."""
        aggregator = MetricsAggregator()
        aggregator.add_metric(create_metric(days_ago=0, test_count=100))
        aggregator.add_metric(create_metric(days_ago=0, test_count=200))
        aggregator.add_metric(create_metric(days_ago=0, test_count=150))

        result = aggregator.aggregate(AggregationWindow.DAILY)
        assert len(result) == 1
        assert result[0].test_count_min == 100
        assert result[0].test_count_max == 200
        assert result[0].test_count_avg == 150.0

    def test_aggregate_all_windows(self) -> None:
        """Test aggregating across all window types."""
        aggregator = MetricsAggregator()
        for i in range(5):
            aggregator.add_metric(create_metric(days_ago=i))

        result = aggregator.aggregate_all_windows()
        assert "day" in result or "week" in result or "month" in result

    def test_compute_trends_empty(self) -> None:
        """Test computing trends with no metrics."""
        aggregator = MetricsAggregator()
        trends = aggregator.compute_trends(AggregationWindow.DAILY)
        assert trends == []

    def test_compute_trends_stable(self) -> None:
        """Test computing trends with stable data."""
        aggregator = MetricsAggregator()
        # Use different days for stable trend
        for i in range(5):
            aggregator.add_metric(create_metric(days_ago=i, cache_hit_rate=75.0))

        result = aggregator.aggregate(AggregationWindow.DAILY)
        trends = aggregator.compute_trends(AggregationWindow.DAILY)
        assert len(trends) > 0

    def test_compute_trends_increasing(self) -> None:
        """Test computing trends with increasing data."""
        aggregator = MetricsAggregator()
        # Create metrics with increasing cache hit rate over time
        # Note: days_ago=4 is oldest, days_ago=0 is newest
        # We iterate in reverse so oldest is added first
        for i in range(4, -1, -1):
            aggregator.add_metric(
                create_metric(days_ago=i, cache_hit_rate=60.0 + (4 - i) * 5)
            )

        trends = aggregator.compute_trends(AggregationWindow.DAILY)
        cache_trend = next(
            (t for t in trends if t.metric_name == "cache_hit_rate"), None
        )
        assert cache_trend is not None
        assert cache_trend.direction == "increasing"

    def test_compute_trends_decreasing(self) -> None:
        """Test computing trends with decreasing data."""
        aggregator = MetricsAggregator()
        # Create metrics with decreasing duration over time
        # Note: days_ago=4 is oldest, days_ago=0 is newest
        for i in range(4, -1, -1):
            aggregator.add_metric(
                create_metric(days_ago=i, duration=100.0 - (4 - i) * 5)
            )

        trends = aggregator.compute_trends(AggregationWindow.DAILY)
        duration_trend = next((t for t in trends if t.metric_name == "duration"), None)
        assert duration_trend is not None
        # Duration is decreasing so slope should be negative
        assert duration_trend.slope < 0

    def test_compute_trends_all_windows(self) -> None:
        """Test computing trends for all windows."""
        aggregator = MetricsAggregator()
        for i in range(10):
            aggregator.add_metric(create_metric(days_ago=i, cache_hit_rate=70.0 + i))

        result = aggregator.compute_trends_all_windows()
        assert isinstance(result, dict)

    def test_get_aggregated_output(self) -> None:
        """Test generating complete aggregated output."""
        aggregator = MetricsAggregator()
        for i in range(5):
            aggregator.add_metric(create_metric(days_ago=i, cache_hit_rate=70.0 + i))

        output = aggregator.get_aggregated_output()
        assert output.source_metrics_count == 5
        assert isinstance(output.aggregation_windows, dict)
        assert isinstance(output.trends, list)


class TestAggregateMetricsFunction:
    """Tests for aggregate_metrics convenience function."""

    def test_aggregate_metrics_empty(self) -> None:
        """Test aggregating empty list."""
        result = aggregate_metrics([], AggregationWindow.DAILY)
        assert result == []

    def test_aggregate_metrics_single(self) -> None:
        """Test aggregating single metric."""
        metrics = [create_metric(days_ago=0, test_count=100)]
        result = aggregate_metrics(metrics, AggregationWindow.DAILY)
        assert len(result) == 1
        assert result[0].test_count_avg == 100.0


class TestComputeMetricTrendsFunction:
    """Tests for compute_metric_trends convenience function."""

    def test_compute_trends_empty(self) -> None:
        """Test computing trends with empty list."""
        result = compute_metric_trends([], AggregationWindow.DAILY)
        assert result == []

    def test_compute_trends_single(self) -> None:
        """Test computing trends with single point."""
        metrics = [create_metric(days_ago=0, cache_hit_rate=75.0)]
        result = compute_metric_trends(metrics, AggregationWindow.DAILY)
        # With single point, no trends computed (need 2+ points)
        assert isinstance(result, list)
