"""Tests for signal throughput tracking.

Tests cover throughput calculations, latency percentiles,
Redis integration, and threshold checking.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from execution.signal_delivery.throughput_tracker import (
    LatencyPercentiles,
    SignalRecord,
    ThroughputMetrics,
    ThroughputTracker,
)


class TestThroughputMetrics:
    """Tests for ThroughputMetrics dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating ThroughputMetrics."""
        metrics = ThroughputMetrics(
            window_name="5min",
            signals_count=100,
            signals_per_minute=20.0,
        )
        assert metrics.window_name == "5min"
        assert metrics.signals_count == 100
        assert metrics.signals_per_minute == 20.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = ThroughputMetrics(
            window_name="1min",
            signals_count=50,
            signals_per_minute=50.0,
        )
        data = metrics.to_dict()
        assert data["window_name"] == "1min"
        assert data["signals_count"] == 50
        assert data["signals_per_minute"] == 50.0
        assert "timestamp" in data


class TestLatencyPercentiles:
    """Tests for LatencyPercentiles dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        percentiles = LatencyPercentiles()
        assert percentiles.p50_ms == 0.0
        assert percentiles.p95_ms == 0.0
        assert percentiles.p99_ms == 0.0
        assert percentiles.count == 0

    def test_custom_values(self) -> None:
        """Test custom values."""
        percentiles = LatencyPercentiles(
            p50_ms=100.0,
            p95_ms=200.0,
            p99_ms=300.0,
            min_ms=50.0,
            max_ms=500.0,
            avg_ms=150.0,
            count=100,
        )
        assert percentiles.p50_ms == 100.0
        assert percentiles.p95_ms == 200.0
        assert percentiles.p99_ms == 300.0
        assert percentiles.count == 100

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        percentiles = LatencyPercentiles(
            p50_ms=100.0,
            p95_ms=200.0,
            p99_ms=300.0,
            count=100,
        )
        data = percentiles.to_dict()
        assert data["p50_ms"] == 100.0
        assert data["p95_ms"] == 200.0
        assert data["p99_ms"] == 300.0
        assert data["count"] == 100


class TestSignalRecord:
    """Tests for SignalRecord dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating SignalRecord."""
        now = datetime.now(UTC)
        record = SignalRecord(
            signal_id="sig-1",
            timestamp=now,
            latency_ms=150.0,
            success=True,
        )
        assert record.signal_id == "sig-1"
        assert record.timestamp == now
        assert record.latency_ms == 150.0
        assert record.success is True

    def test_with_metadata(self) -> None:
        """Test creating with metadata."""
        record = SignalRecord(
            signal_id="sig-2",
            timestamp=datetime.now(UTC),
            latency_ms=200.0,
            success=True,
            metadata={"source": "test", "priority": "high"},
        )
        assert record.metadata["source"] == "test"
        assert record.metadata["priority"] == "high"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        record = SignalRecord(
            signal_id="sig-3",
            timestamp=now,
            latency_ms=100.0,
            success=True,
        )
        data = record.to_dict()
        assert data["signal_id"] == "sig-3"
        assert data["latency_ms"] == 100.0
        assert data["success"] is True


class TestThroughputTracker:
    """Tests for ThroughputTracker."""

    @pytest.fixture
    def tracker(self) -> ThroughputTracker:
        """Create a fresh tracker for testing."""
        return ThroughputTracker(redis_client=None)

    def test_initialization(self) -> None:
        """Test tracker initialization."""
        tracker = ThroughputTracker()
        assert tracker._signals == []
        assert tracker._metrics_history == []

    def test_record_signal(self, tracker: ThroughputTracker) -> None:
        """Test recording a signal."""
        tracker.record_signal("sig-1", latency_ms=150.0)
        assert len(tracker._signals) == 1
        assert tracker._signals[0].signal_id == "sig-1"
        assert tracker._signals[0].latency_ms == 150.0

    def test_record_multiple_signals(self, tracker: ThroughputTracker) -> None:
        """Test recording multiple signals."""
        for i in range(10):
            tracker.record_signal(f"sig-{i}", latency_ms=float(100 + i * 10))
        assert len(tracker._signals) == 10

    def test_record_signal_with_metadata(self, tracker: ThroughputTracker) -> None:
        """Test recording signal with metadata."""
        tracker.record_signal(
            "sig-1",
            latency_ms=150.0,
            metadata={"source": "test"},
        )
        assert tracker._signals[0].metadata["source"] == "test"

    def test_get_metrics_empty(self, tracker: ThroughputTracker) -> None:
        """Test getting metrics with no signals."""
        metrics = tracker.get_metrics("1min")
        assert metrics.signals_count == 0
        assert metrics.signals_per_minute == 0.0

    def test_get_metrics_with_signals(self, tracker: ThroughputTracker) -> None:
        """Test getting metrics with signals."""
        now = datetime.now(UTC)
        # Add signals within the window
        for i in range(10):
            record = SignalRecord(
                signal_id=f"sig-{i}",
                timestamp=now,
                latency_ms=100.0,
                success=True,
            )
            tracker._signals.append(record)

        metrics = tracker.get_metrics("1min")
        assert metrics.signals_count == 10
        assert metrics.signals_per_minute == 10.0  # 10 signals in 1 minute

    def test_get_metrics_outside_window(self, tracker: ThroughputTracker) -> None:
        """Test that signals outside window are excluded."""
        now = datetime.now(UTC)
        old_time = now - timedelta(minutes=10)

        # Add old signal
        tracker._signals.append(
            SignalRecord(
                signal_id="old-sig",
                timestamp=old_time,
                latency_ms=100.0,
                success=True,
            )
        )

        # Add recent signal
        tracker._signals.append(
            SignalRecord(
                signal_id="new-sig",
                timestamp=now,
                latency_ms=100.0,
                success=True,
            )
        )

        metrics = tracker.get_metrics("5min")
        assert metrics.signals_count == 1  # Only recent signal

    def test_get_latency_percentiles_empty(self, tracker: ThroughputTracker) -> None:
        """Test getting percentiles with no signals."""
        percentiles = tracker.get_latency_percentiles("1min")
        assert percentiles.p50_ms == 0.0
        assert percentiles.p95_ms == 0.0
        assert percentiles.p99_ms == 0.0

    def test_get_latency_percentiles(self, tracker: ThroughputTracker) -> None:
        """Test calculating latency percentiles."""
        now = datetime.now(UTC)
        # Add 100 signals with varying latencies
        for i in range(100):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=float(i * 10),  # 0, 10, 20, ..., 990
                    success=True,
                )
            )

        percentiles = tracker.get_latency_percentiles("1min")
        assert percentiles.count == 100
        assert percentiles.p50_ms == 500.0  # 50th of 0-990
        assert percentiles.p95_ms == 950.0  # 95th of 0-990
        assert percentiles.p99_ms == 990.0  # 99th of 0-990
        assert percentiles.min_ms == 0.0
        assert percentiles.max_ms == 990.0

    def test_get_all_windows_metrics(self, tracker: ThroughputTracker) -> None:
        """Test getting metrics for all windows."""
        now = datetime.now(UTC)
        for i in range(5):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=100.0,
                    success=True,
                )
            )

        all_metrics = tracker.get_all_windows_metrics()
        assert "1min" in all_metrics
        assert "5min" in all_metrics
        assert "15min" in all_metrics

    def test_get_all_windows_latencies(self, tracker: ThroughputTracker) -> None:
        """Test getting latencies for all windows."""
        now = datetime.now(UTC)
        for i in range(10):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=float(i * 100),
                    success=True,
                )
            )

        all_latencies = tracker.get_all_windows_latencies()
        assert "1min" in all_latencies
        assert "5min" in all_latencies
        assert "15min" in all_latencies

    def test_store_and_get_current_metrics(self, tracker: ThroughputTracker) -> None:
        """Test storing and retrieving current metrics."""
        # Add some signals
        for i in range(5):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0)

        # Store metrics
        stored = tracker.store_current_metrics()
        assert "timestamp" in stored
        assert "throughput" in stored
        assert "latency" in stored

        # Retrieve metrics
        retrieved = tracker.get_current_metrics()
        assert retrieved is not None
        assert retrieved["timestamp"] == stored["timestamp"]

    def test_get_summary(self, tracker: ThroughputTracker) -> None:
        """Test getting summary."""
        for i in range(10):
            tracker.record_signal(f"sig-{i}", latency_ms=float(i * 10))

        summary = tracker.get_summary()
        assert summary["total_signals_recorded"] == 10
        assert "throughput" in summary
        assert "latency" in summary

    def test_clear(self, tracker: ThroughputTracker) -> None:
        """Test clearing all data."""
        tracker.record_signal("sig-1", latency_ms=100.0)
        tracker.store_current_metrics()

        tracker.clear()
        assert len(tracker._signals) == 0
        assert len(tracker._metrics_history) == 0

    def test_check_throughput_threshold_pass(self, tracker: ThroughputTracker) -> None:
        """Test throughput threshold check - passing."""
        now = datetime.now(UTC)
        for i in range(10):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=100.0,
                    success=True,
                )
            )

        result = tracker.check_throughput_threshold("1min", min_spm=5.0)
        assert result["passed"] is True
        assert result["status"] == "healthy"

    def test_check_throughput_threshold_fail(self, tracker: ThroughputTracker) -> None:
        """Test throughput threshold check - failing."""
        result = tracker.check_throughput_threshold("1min", min_spm=1.0)
        assert result["passed"] is False
        assert result["status"] == "alert"

    def test_check_latency_threshold_pass(self, tracker: ThroughputTracker) -> None:
        """Test latency threshold check - passing."""
        now = datetime.now(UTC)
        for i in range(10):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=100.0,
                    success=True,
                )
            )

        result = tracker.check_latency_threshold("1min", max_p95_ms=500.0)
        assert result["passed"] is True
        assert result["status"] == "healthy"

    def test_check_latency_threshold_fail(self, tracker: ThroughputTracker) -> None:
        """Test latency threshold check - failing."""
        now = datetime.now(UTC)
        for i in range(10):
            tracker._signals.append(
                SignalRecord(
                    signal_id=f"sig-{i}",
                    timestamp=now,
                    latency_ms=1000.0,
                    success=True,
                )
            )

        result = tracker.check_latency_threshold("1min", max_p95_ms=500.0)
        assert result["passed"] is False
        assert result["status"] == "alert"

    def test_max_signal_records_limit(self, tracker: ThroughputTracker) -> None:
        """Test that signal records are limited."""
        # Add more than max records
        for i in range(tracker.MAX_SIGNAL_RECORDS + 100):
            tracker.record_signal(f"sig-{i}", latency_ms=100.0)

        assert len(tracker._signals) <= tracker.MAX_SIGNAL_RECORDS


class TestThroughputTrackerWithRedis:
    """Tests for ThroughputTracker with Redis."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.hset.return_value = 1
        redis.hget.return_value = None
        redis.hgetall.return_value = {}
        redis.expire.return_value = 1
        redis.delete.return_value = 1
        return redis

    def test_record_signal_with_redis(self, mock_redis: MagicMock) -> None:
        """Test recording signal with Redis."""
        tracker = ThroughputTracker(redis_client=mock_redis)
        tracker.record_signal("sig-1", latency_ms=150.0)

        # Verify Redis was called
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_store_metrics_with_redis(self, mock_redis: MagicMock) -> None:
        """Test storing metrics with Redis."""
        tracker = ThroughputTracker(redis_client=mock_redis)
        tracker.record_signal("sig-1", latency_ms=100.0)
        tracker.store_current_metrics()

        # Verify Redis was called
        assert mock_redis.hset.call_count >= 1

    def test_clear_with_redis(self, mock_redis: MagicMock) -> None:
        """Test clearing with Redis."""
        tracker = ThroughputTracker(redis_client=mock_redis)
        tracker.record_signal("sig-1", latency_ms=100.0)
        tracker.clear()

        # Verify Redis delete was called
        assert mock_redis.delete.call_count >= 1

    def test_redis_error_handling(self, mock_redis: MagicMock) -> None:
        """Test handling of Redis errors."""
        mock_redis.hset.side_effect = Exception("Redis error")

        tracker = ThroughputTracker(redis_client=mock_redis)
        # Should not raise exception
        tracker.record_signal("sig-1", latency_ms=100.0)

        # Signal should still be stored in memory
        assert len(tracker._signals) == 1


class TestWindowParsing:
    """Tests for window parsing."""

    @pytest.fixture
    def tracker(self) -> ThroughputTracker:
        """Create a fresh tracker."""
        return ThroughputTracker()

    def test_parse_1min(self, tracker: ThroughputTracker) -> None:
        """Test parsing 1min window."""
        seconds = tracker._parse_window("1min")
        assert seconds == 60

    def test_parse_5min(self, tracker: ThroughputTracker) -> None:
        """Test parsing 5min window."""
        seconds = tracker._parse_window("5min")
        assert seconds == 300

    def test_parse_15min(self, tracker: ThroughputTracker) -> None:
        """Test parsing 15min window."""
        seconds = tracker._parse_window("15min")
        assert seconds == 900

    def test_parse_invalid(self, tracker: ThroughputTracker) -> None:
        """Test parsing invalid window defaults to 1min."""
        seconds = tracker._parse_window("invalid")
        assert seconds == 60


class TestPercentileCalculation:
    """Tests for percentile calculation."""

    @pytest.fixture
    def tracker(self) -> ThroughputTracker:
        """Create a fresh tracker."""
        return ThroughputTracker()

    def test_percentile_empty(self, tracker: ThroughputTracker) -> None:
        """Test percentile with empty list."""
        result = tracker._percentile([], 50)
        assert result == 0.0

    def test_percentile_single_value(self, tracker: ThroughputTracker) -> None:
        """Test percentile with single value."""
        result = tracker._percentile([100.0], 50)
        assert result == 100.0

    def test_percentile_50th(self, tracker: ThroughputTracker) -> None:
        """Test 50th percentile."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = tracker._percentile(values, 50)
        assert result == 3.0

    def test_percentile_95th(self, tracker: ThroughputTracker) -> None:
        """Test 95th percentile."""
        values = list(range(100))  # 0-99
        result = tracker._percentile(values, 95)
        assert result == 95.0

    def test_percentile_99th(self, tracker: ThroughputTracker) -> None:
        """Test 99th percentile."""
        values = list(range(100))  # 0-99
        result = tracker._percentile(values, 99)
        assert result == 99.0


class TestRedisKeyPatterns:
    """Tests for Redis key patterns."""

    def test_key_prefix(self) -> None:
        """Test that key prefix matches spec."""
        assert ThroughputTracker.REDIS_PREFIX == "chise:paper:metrics:throughput"

    def test_current_key(self) -> None:
        """Test current metrics key."""
        assert ThroughputTracker.CURRENT_KEY == "chise:paper:metrics:throughput:current"

    def test_history_key(self) -> None:
        """Test history key."""
        assert ThroughputTracker.HISTORY_KEY == "chise:paper:metrics:throughput:history"

    def test_signals_key(self) -> None:
        """Test signals key."""
        assert ThroughputTracker.SIGNALS_KEY == "chise:paper:metrics:throughput:signals"
