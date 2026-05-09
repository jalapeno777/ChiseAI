"""Tests for zero-signal metrics module.

Tests cover:
- Metrics tracking (counter increments, duration calculation)
- Prometheus text exposition format
- Severity classification
- Redis fallback to in-memory
- Rate limiting thresholds
- Recovery tracking

Story: ST-MVP-006
"""

from __future__ import annotations

from unittest.mock import MagicMock

from monitoring.zero_signal_metrics import (
    METRICS_KEY_PREFIX,
    DatasourceMetrics,
    ZeroSignalMetrics,
)


class TestDatasourceMetrics:
    """Tests for DatasourceMetrics dataclass."""

    def test_default_values(self):
        m = DatasourceMetrics()
        assert m.event_count == 0
        assert m.total_duration_minutes == 0.0
        assert m.current_duration_minutes == 0.0
        assert m.last_signal_timestamp == 0.0
        assert m.last_zero_signal_timestamp == 0.0
        assert m.is_zero_signal_active is False
        assert m.severity == "none"


class TestZeroSignalMetricsBasic:
    """Tests for basic ZeroSignalMetrics operations."""

    def test_init_no_redis(self):
        """Should initialize with in-memory storage when no Redis."""
        metrics = ZeroSignalMetrics()
        assert metrics._redis is None
        assert metrics._redis_available is None
        assert len(metrics._metrics) == 0

    def test_init_with_mock_redis(self):
        """Should accept a Redis client."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        metrics = ZeroSignalMetrics(redis_client=mock_redis)
        assert metrics._redis is mock_redis

    def test_record_zero_signal_basic(self):
        """Should record a zero-signal event and return result dict."""
        metrics = ZeroSignalMetrics()
        result = metrics.record_zero_signal("binance", duration_minutes=30)

        assert result["datasource"] == "binance"
        assert result["severity"] == "warning"  # 30m >= 15m warning threshold
        assert result["event_count"] == 1
        assert result["duration_minutes"] == 30.0
        assert result["window_count"] == 1

    def test_record_zero_signal_multiple(self):
        """Should accumulate event count across multiple recordings."""
        metrics = ZeroSignalMetrics()

        metrics.record_zero_signal("binance", duration_minutes=15)
        result = metrics.record_zero_signal("binance", duration_minutes=30)

        assert result["event_count"] == 2
        assert result["duration_minutes"] == 30.0

    def test_record_zero_signal_severity_info(self):
        """Short duration should be info severity."""
        metrics = ZeroSignalMetrics()
        result = metrics.record_zero_signal("binance", duration_minutes=5)

        assert result["severity"] == "info"

    def test_record_zero_signal_severity_warning(self):
        """Medium duration should be warning severity."""
        metrics = ZeroSignalMetrics()
        result = metrics.record_zero_signal("binance", duration_minutes=20)

        assert result["severity"] == "warning"

    def test_record_zero_signal_severity_critical(self):
        """Long duration should be critical severity."""
        metrics = ZeroSignalMetrics()
        result = metrics.record_zero_signal("binance", duration_minutes=50)

        assert result["severity"] == "critical"

    def test_record_zero_signal_updates_metrics(self):
        """Should update internal DatasourceMetrics."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("binance", duration_minutes=30, window_count=3)

        m = metrics.get_metrics("binance")
        assert m is not None
        assert m.event_count == 1
        assert m.current_duration_minutes == 30.0
        assert m.total_duration_minutes == 30.0
        assert m.is_zero_signal_active is True
        assert m.severity == "warning"
        assert m.last_zero_signal_timestamp > 0

    def test_record_multiple_datasources(self):
        """Should track metrics independently per datasource."""
        metrics = ZeroSignalMetrics()

        metrics.record_zero_signal("binance", duration_minutes=30)
        metrics.record_zero_signal("kraken", duration_minutes=10)

        all_metrics = metrics.get_all_metrics()
        assert len(all_metrics) == 2
        assert "binance" in all_metrics
        assert "kraken" in all_metrics
        assert all_metrics["binance"].event_count == 1
        assert all_metrics["kraken"].event_count == 1


class TestZeroSignalMetricsRecovery:
    """Tests for signal recovery tracking."""

    def test_record_signal_resumed(self):
        """Should clear active state on recovery."""
        metrics = ZeroSignalMetrics()

        metrics.record_zero_signal("binance", duration_minutes=30)
        result = metrics.record_signal_resumed("binance")

        assert result["datasource"] == "binance"
        assert result["was_active"] is True
        assert result["outage_duration_minutes"] == 30.0
        assert result["event_count"] == 1

        m = metrics.get_metrics("binance")
        assert m.is_zero_signal_active is False
        assert m.current_duration_minutes == 0.0
        assert m.severity == "none"
        assert m.last_signal_timestamp > 0

    def test_record_signal_resumed_not_active(self):
        """Should handle recovery when no active alert."""
        metrics = ZeroSignalMetrics()

        result = metrics.record_signal_resumed("binance")
        assert result["was_active"] is False
        assert result["outage_duration_minutes"] == 0.0

    def test_update_last_signal_clears_active(self):
        """Should clear active state on heartbeat."""
        metrics = ZeroSignalMetrics()

        metrics.record_zero_signal("binance", duration_minutes=30)
        m = metrics.get_metrics("binance")
        assert m.is_zero_signal_active is True

        metrics.update_last_signal("binance")
        m = metrics.get_metrics("binance")
        assert m.is_zero_signal_active is False
        assert m.severity == "none"


class TestZeroSignalMetricsPrometheus:
    """Tests for Prometheus text exposition format."""

    def test_get_metrics_text_empty(self):
        """Should return valid Prometheus text with no datasources."""
        metrics = ZeroSignalMetrics()
        text = metrics.get_metrics_text()

        assert "# HELP chiseai_zero_signal_event_count" in text
        assert "# TYPE chiseai_zero_signal_event_count counter" in text
        assert "chiseai_zero_signal_active_datasources 0" in text
        assert "chiseai_zero_signal_total_datasources 0" in text

    def test_get_metrics_text_with_data(self):
        """Should include datasource metrics in Prometheus format."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("binance", duration_minutes=30)

        text = metrics.get_metrics_text()

        assert 'datasource="binance"' in text
        assert "chiseai_zero_signal_event_count" in text
        assert "chiseai_zero_signal_duration_minutes" in text
        assert "chiseai_zero_signal_active" in text
        assert "chiseai_zero_signal_severity" in text
        assert "chiseai_zero_signal_active_datasources 1" in text

    def test_get_metrics_text_severity_values(self):
        """Should encode severity as numeric values."""
        metrics = ZeroSignalMetrics()

        # No active zero signal - severity 0
        metrics.update_last_signal("kraken")
        text = metrics.get_metrics_text()
        assert 'chiseai_zero_signal_severity{datasource="kraken"} 0' in text

        # Info severity
        metrics.record_zero_signal("binance", duration_minutes=5)
        text = metrics.get_metrics_text()
        assert 'chiseai_zero_signal_severity{datasource="binance"} 1' in text

        # Warning severity
        metrics.record_zero_signal("okx", duration_minutes=20)
        text = metrics.get_metrics_text()
        assert 'chiseai_zero_signal_severity{datasource="okx"} 2' in text

        # Critical severity
        metrics.record_zero_signal("bybit", duration_minutes=50)
        text = metrics.get_metrics_text()
        assert 'chiseai_zero_signal_severity{datasource="bybit"} 3' in text

    def test_get_metrics_text_sorted_datasources(self):
        """Should output datasources in sorted order."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("zebra", duration_minutes=10)
        metrics.record_zero_signal("alpha", duration_minutes=10)

        text = metrics.get_metrics_text()

        alpha_pos = text.index('datasource="alpha"')
        zebra_pos = text.index('datasource="zebra"')
        assert alpha_pos < zebra_pos

    def test_get_metrics_text_contains_all_metric_types(self):
        """Should include all declared metric types."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("binance", duration_minutes=30)

        text = metrics.get_metrics_text()

        assert "# TYPE chiseai_zero_signal_event_count counter" in text
        assert "# TYPE chiseai_zero_signal_duration_minutes gauge" in text
        assert "# TYPE chiseai_zero_signal_total_duration_minutes counter" in text
        assert "# TYPE chiseai_zero_signal_last_signal_timestamp gauge" in text
        assert "# TYPE chiseai_zero_signal_active gauge" in text
        assert "# TYPE chiseai_zero_signal_severity gauge" in text
        assert "# TYPE chiseai_zero_signal_active_datasources gauge" in text
        assert "# TYPE chiseai_zero_signal_total_datasources gauge" in text


class TestZeroSignalMetricsThresholds:
    """Tests for threshold configuration."""

    def test_default_thresholds(self):
        """Should have default thresholds."""
        metrics = ZeroSignalMetrics()
        thresholds = metrics.get_thresholds()
        assert thresholds["warning_minutes"] == 15
        assert thresholds["critical_minutes"] == 45

    def test_set_thresholds(self):
        """Should update thresholds."""
        metrics = ZeroSignalMetrics()
        metrics.set_thresholds({"warning_minutes": 30, "critical_minutes": 60})

        thresholds = metrics.get_thresholds()
        assert thresholds["warning_minutes"] == 30
        assert thresholds["critical_minutes"] == 60

    def test_custom_thresholds_affect_severity(self):
        """Custom thresholds should change severity classification."""
        metrics = ZeroSignalMetrics()
        metrics.set_thresholds({"warning_minutes": 60, "critical_minutes": 120})

        # 30 minutes would have been warning with defaults, now info
        result = metrics.record_zero_signal("binance", duration_minutes=30)
        assert result["severity"] == "info"

        # 60 minutes should now be warning
        result = metrics.record_zero_signal("kraken", duration_minutes=60)
        assert result["severity"] == "warning"


class TestZeroSignalMetricsReset:
    """Tests for metrics reset."""

    def test_reset_specific_datasource(self):
        """Should reset metrics for a specific datasource."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("binance", duration_minutes=30)
        metrics.record_zero_signal("kraken", duration_minutes=10)

        metrics.reset("binance")

        assert metrics.get_metrics("binance") is None
        assert metrics.get_metrics("kraken") is not None

    def test_reset_all(self):
        """Should reset all datasource metrics."""
        metrics = ZeroSignalMetrics()
        metrics.record_zero_signal("binance", duration_minutes=30)
        metrics.record_zero_signal("kraken", duration_minutes=10)

        metrics.reset()

        assert len(metrics.get_all_metrics()) == 0


class TestZeroSignalMetricsRedis:
    """Tests for Redis persistence."""

    def test_save_and_load_from_redis(self):
        """Should persist metrics to Redis and reload them."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.ping.return_value = True

        metrics = ZeroSignalMetrics(redis_client=mock_redis)

        # Record an event - this should call hset
        metrics.record_zero_signal("binance", duration_minutes=30)

        # Verify hset was called
        mock_redis.hset.assert_called()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == f"{METRICS_KEY_PREFIX}binance"
        mapping = call_args[1]["mapping"]
        assert mapping["event_count"] == 1
        assert mapping["current_duration_minutes"] == 30.0

    def test_load_from_redis_on_create(self):
        """Should load existing metrics from Redis on first access."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "event_count": "5",
            "total_duration_minutes": "150.0",
            "current_duration_minutes": "30.0",
            "last_signal_timestamp": "1700000000.0",
            "last_zero_signal_timestamp": "1700001000.0",
            "is_zero_signal_active": "1",
            "severity": "warning",
        }
        mock_redis.ping.return_value = True

        metrics = ZeroSignalMetrics(redis_client=mock_redis)

        # Trigger load by getting metrics
        result = metrics.record_zero_signal("binance", duration_minutes=30)

        # The existing count should be loaded and incremented
        # (record_zero_signal loads via _get_or_create_metrics -> _load_from_redis)
        assert result["event_count"] == 6  # 5 loaded + 1 new

    def test_redis_failure_fallback(self):
        """Should fall back to in-memory when Redis fails."""
        mock_redis = MagicMock()
        mock_redis.hset.side_effect = Exception("Redis connection lost")
        mock_redis.hgetall.return_value = {}

        metrics = ZeroSignalMetrics(redis_client=mock_redis)

        # Should still work in-memory despite Redis errors
        result = metrics.record_zero_signal("binance", duration_minutes=30)
        assert result.get("success_indicators", True)
        assert result["event_count"] == 1

        m = metrics.get_metrics("binance")
        assert m is not None
        assert m.event_count == 1


class TestZeroSignalMetricsIntegration:
    """Integration tests for the full metrics flow."""

    def test_full_lifecycle(self):
        """Should handle full zero-signal lifecycle."""
        metrics = ZeroSignalMetrics()

        # 1. Start receiving signals normally
        metrics.update_last_signal("binance")
        m = metrics.get_metrics("binance")
        assert m.is_zero_signal_active is False

        # 2. Zero-signal starts
        result = metrics.record_zero_signal(
            "binance", duration_minutes=15, window_count=1
        )
        assert result["severity"] == "warning"
        assert metrics.get_metrics("binance").is_zero_signal_active is True

        # 3. Zero-signal continues
        result = metrics.record_zero_signal(
            "binance", duration_minutes=30, window_count=2
        )
        assert result["severity"] == "warning"

        # 4. Zero-signal goes critical
        result = metrics.record_zero_signal(
            "binance", duration_minutes=50, window_count=3
        )
        assert result["severity"] == "critical"

        # 5. Check Prometheus output
        text = metrics.get_metrics_text()
        assert "chiseai_zero_signal_active_datasources 1" in text

        # 6. Signal resumes
        result = metrics.record_signal_resumed("binance")
        assert result["was_active"] is True
        assert result["outage_duration_minutes"] == 50.0

        # 7. Verify recovery state
        m = metrics.get_metrics("binance")
        assert m.is_zero_signal_active is False
        assert m.severity == "none"

        # 8. Check Prometheus output after recovery
        text = metrics.get_metrics_text()
        assert "chiseai_zero_signal_active_datasources 0" in text
