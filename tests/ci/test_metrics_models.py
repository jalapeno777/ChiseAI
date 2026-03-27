"""Tests for CI Metrics Models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from src.ci.metrics.models import (
    AggregatedMetric,
    AggregatedMetricsOutput,
    AggregationWindow,
    MetricPoint,
    Trend,
)


class TestMetricPoint:
    """Tests for MetricPoint model."""

    def test_create_minimal(self) -> None:
        """Test creating a MetricPoint with minimal data."""
        point = MetricPoint(timestamp="2026-03-26T10:00:00+00:00")
        assert point.timestamp == "2026-03-26T10:00:00+00:00"
        assert point.test_count == 0
        assert point.duration == 0.0

    def test_create_full(self) -> None:
        """Test creating a MetricPoint with all fields."""
        point = MetricPoint(
            timestamp="2026-03-26T10:00:00+00:00",
            test_count=100,
            duration=45.5,
            cache_hit_rate=75.0,
            parallel_speedup=2.3,
            worker_utilization=0.85,
            cache_hits=75,
            cache_misses=25,
            tests_passed=98,
            tests_failed=2,
        )
        assert point.test_count == 100
        assert point.duration == 45.5
        assert point.cache_hit_rate == 75.0
        assert point.parallel_speedup == 2.3
        assert point.worker_utilization == 0.85
        assert point.cache_hits == 75
        assert point.cache_misses == 25
        assert point.tests_passed == 98
        assert point.tests_failed == 2

    def test_from_dict_flat(self) -> None:
        """Test creating MetricPoint from flat dictionary."""
        data = {
            "timestamp": "2026-03-26T10:00:00+00:00",
            "test_count": 100,
            "duration": 45.5,
            "cache_hit_rate": 75.0,
            "tests_passed": 98,
            "tests_failed": 2,
        }
        point = MetricPoint.from_dict(data)
        assert point.timestamp == "2026-03-26T10:00:00+00:00"
        assert point.test_count == 100
        assert point.cache_hit_rate == 75.0

    def test_from_dict_nested(self) -> None:
        """Test creating MetricPoint from nested dictionary (local_ci format)."""
        data = {
            "timestamp": "2026-03-26T10:00:00+00:00",
            "cache": {"hits": 75, "misses": 25, "hit_rate": 75.0},
            "parallel": {"speedup": 2.3, "worker_utilization": 0.85},
            "speedup": {
                "total_duration": 45.5,
                "tests_run": 100,
                "tests_passed": 98,
                "tests_failed": 2,
            },
        }
        point = MetricPoint.from_dict(data)
        assert point.timestamp == "2026-03-26T10:00:00+00:00"
        assert point.cache_hit_rate == 75.0
        assert point.parallel_speedup == 2.3
        assert point.worker_utilization == 0.85
        assert point.tests_passed == 98

    def test_to_dict(self) -> None:
        """Test converting MetricPoint to dictionary."""
        point = MetricPoint(
            timestamp="2026-03-26T10:00:00+00:00",
            test_count=100,
            duration=45.5,
        )
        data = point.to_dict()
        assert data["timestamp"] == "2026-03-26T10:00:00+00:00"
        assert data["test_count"] == 100
        assert data["duration"] == 45.5

    def test_get_datetime(self) -> None:
        """Test parsing timestamp to datetime."""
        point = MetricPoint(timestamp="2026-03-26T10:00:00+00:00")
        dt = point.get_datetime()
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 26


class TestAggregationWindow:
    """Tests for AggregationWindow enum."""

    def test_daily_value(self) -> None:
        """Test DAILY window value."""
        assert AggregationWindow.DAILY.value == "day"
        assert str(AggregationWindow.DAILY) == "day"

    def test_weekly_value(self) -> None:
        """Test WEEKLY window value."""
        assert AggregationWindow.WEEKLY.value == "week"
        assert str(AggregationWindow.WEEKLY) == "week"

    def test_monthly_value(self) -> None:
        """Test MONTHLY window value."""
        assert AggregationWindow.MONTHLY.value == "month"
        assert str(AggregationWindow.MONTHLY) == "month"


class TestAggregatedMetric:
    """Tests for AggregatedMetric model."""

    def test_create(self) -> None:
        """Test creating an AggregatedMetric."""
        now = datetime.now(UTC)
        agg = AggregatedMetric(
            window=AggregationWindow.DAILY,
            window_start=now,
            window_end=now,
            test_count_avg=100.0,
            test_count_min=80,
            test_count_max=120,
            sample_count=10,
        )
        assert agg.window == AggregationWindow.DAILY
        assert agg.test_count_avg == 100.0
        assert agg.sample_count == 10

    def test_to_dict(self) -> None:
        """Test converting AggregatedMetric to dictionary."""
        now = datetime.now(UTC)
        agg = AggregatedMetric(
            window=AggregationWindow.DAILY,
            window_start=now,
            window_end=now,
            test_count_avg=100.0,
            sample_count=10,
        )
        data = agg.to_dict()
        assert data["window"] == "day"
        assert data["test_count_avg"] == 100.0
        assert data["sample_count"] == 10


class TestTrend:
    """Tests for Trend model."""

    def test_calculate_stable(self) -> None:
        """Test trend calculation with stable values."""
        values = [100.0, 100.0, 100.0, 100.0, 100.0]
        trend = Trend.calculate("cache_hit_rate", AggregationWindow.DAILY, values)
        assert trend.direction == "stable"
        assert trend.metric_name == "cache_hit_rate"

    def test_calculate_increasing(self) -> None:
        """Test trend calculation with increasing values."""
        values = [50.0, 55.0, 60.0, 65.0, 70.0]
        trend = Trend.calculate("cache_hit_rate", AggregationWindow.DAILY, values)
        assert trend.direction == "increasing"
        assert trend.slope > 0

    def test_calculate_decreasing(self) -> None:
        """Test trend calculation with decreasing values."""
        values = [100.0, 90.0, 80.0, 70.0, 60.0]
        trend = Trend.calculate("duration", AggregationWindow.WEEKLY, values)
        assert trend.direction == "decreasing"
        assert trend.slope < 0

    def test_calculate_single_value(self) -> None:
        """Test trend calculation with single value."""
        values = [100.0]
        trend = Trend.calculate("cache_hit_rate", AggregationWindow.DAILY, values)
        assert trend.direction == "stable"
        assert trend.current_value == 100.0

    def test_calculate_empty_values(self) -> None:
        """Test trend calculation with empty list."""
        values: list[float] = []
        trend = Trend.calculate("cache_hit_rate", AggregationWindow.DAILY, values)
        assert trend.direction == "stable"
        assert trend.current_value == 0.0

    def test_r_squared(self) -> None:
        """Test R-squared calculation."""
        # Perfect linear relationship
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        trend = Trend.calculate("test", AggregationWindow.DAILY, values)
        assert trend.r_squared > 0.99

    def test_percent_change(self) -> None:
        """Test percent change calculation."""
        values = [100.0, 110.0]
        trend = Trend.calculate("test", AggregationWindow.DAILY, values)
        assert trend.percent_change == pytest.approx(10.0, rel=0.01)

    def test_to_dict(self) -> None:
        """Test converting Trend to dictionary."""
        values = [100.0, 110.0]
        trend = Trend.calculate("cache_hit_rate", AggregationWindow.DAILY, values)
        data = trend.to_dict()
        assert data["metric_name"] == "cache_hit_rate"
        assert data["window"] == "day"
        assert "direction" in data
        assert "slope" in data


class TestAggregatedMetricsOutput:
    """Tests for AggregatedMetricsOutput model."""

    def test_create(self) -> None:
        """Test creating an AggregatedMetricsOutput."""
        output = AggregatedMetricsOutput(
            generated_at="2026-03-26T10:00:00+00:00",
            source_metrics_count=100,
        )
        assert output.generated_at == "2026-03-26T10:00:00+00:00"
        assert output.source_metrics_count == 100
        assert output.aggregation_windows == {}
        assert output.trends == []

    def test_to_dict(self) -> None:
        """Test converting AggregatedMetricsOutput to dictionary."""
        output = AggregatedMetricsOutput(
            generated_at="2026-03-26T10:00:00+00:00",
            source_metrics_count=100,
        )
        output.aggregation_windows = {"day": [{"test": "data"}]}
        output.trends = [{"metric": "test"}]

        data = output.to_dict()
        assert data["generated_at"] == "2026-03-26T10:00:00+00:00"
        assert data["source_metrics_count"] == 100
        assert "day" in data["aggregation_windows"]
        assert len(data["trends"]) == 1
