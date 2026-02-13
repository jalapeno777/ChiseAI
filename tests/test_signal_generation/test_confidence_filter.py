"""Tests for confidence filter module."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import patch

from signal_generation.confidence_filter import (
    ConfidenceFilter,
    FilterMetrics,
    FilterResult,
    InfluxDBExporter,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestConfidenceFilter:
    """Tests for ConfidenceFilter."""

    def test_default_threshold(self):
        """Test default threshold is 75%."""
        filter_obj = ConfidenceFilter()
        assert filter_obj.threshold == 0.75
        assert filter_obj.get_threshold_percent() == 75.0

    def test_custom_threshold(self):
        """Test custom threshold via constructor."""
        filter_obj = ConfidenceFilter(threshold=0.80)
        assert filter_obj.threshold == 0.80

    def test_threshold_clamping(self):
        """Test threshold is clamped to valid range."""
        # Below minimum
        filter_obj = ConfidenceFilter(threshold=0.30)
        assert filter_obj.threshold == 0.50  # MIN_THRESHOLD

        # Above maximum
        filter_obj = ConfidenceFilter(threshold=0.99)
        assert filter_obj.threshold == 0.95  # MAX_THRESHOLD

    def test_filter_actionable_signal(self):
        """Test filtering an actionable signal (>=75%)."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)

        assert isinstance(result, FilterResult)
        assert result.is_actionable is True
        assert result.threshold == 0.75
        assert result.confidence == 0.85
        assert "meets threshold" in result.reason

    def test_filter_non_actionable_signal(self):
        """Test filtering a non-actionable signal (<75%)."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)

        assert isinstance(result, FilterResult)
        assert result.is_actionable is False
        assert result.threshold == 0.75
        assert result.confidence == 0.60
        assert "below threshold" in result.reason

    def test_should_emit(self):
        """Test quick emission check."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        # Actionable signal
        signal_high = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        assert filter_obj.should_emit(signal_high) is True

        # Non-actionable signal
        signal_low = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )
        assert filter_obj.should_emit(signal_low) is False

    def test_exact_threshold_boundary(self):
        """Test signal exactly at threshold boundary."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.75,  # Exactly at threshold
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)
        assert result.is_actionable is True

    def test_environment_variable_threshold(self):
        """Test threshold from environment variable."""
        with patch.dict(os.environ, {"SIGNAL_CONFIDENCE_THRESHOLD": "0.80"}):
            filter_obj = ConfidenceFilter()
            assert filter_obj.threshold == 0.80

    def test_invalid_environment_variable(self):
        """Test handling of invalid environment variable."""
        with patch.dict(os.environ, {"SIGNAL_CONFIDENCE_THRESHOLD": "invalid"}):
            filter_obj = ConfidenceFilter()
            # Should fall back to default
            assert filter_obj.threshold == 0.75

    def test_log_non_actionable(self, caplog):
        """Test logging of non-actionable signals."""
        import logging

        with caplog.at_level(logging.INFO):
            filter_obj = ConfidenceFilter(threshold=0.75)

            signal = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.60,
                base_score=60.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.LOGGED_ONLY,
                timeframe="1h",
            )

            filter_obj.log_non_actionable(signal)

            assert "Non-actionable signal" in caplog.text
            assert "BTC/USDT" in caplog.text
            assert "60.0%" in caplog.text

    def test_threshold_priority(self):
        """Test that constructor threshold overrides environment variable."""
        with patch.dict(os.environ, {"SIGNAL_CONFIDENCE_THRESHOLD": "0.80"}):
            filter_obj = ConfidenceFilter(threshold=0.70)
            # Constructor should take priority
            assert filter_obj.threshold == 0.70


class TestConfidenceFilterEdgeCases:
    """Edge case tests for ConfidenceFilter."""

    def test_zero_confidence(self):
        """Test filtering signal with zero confidence."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            base_score=50.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)
        assert result.is_actionable is False

    def test_max_confidence(self):
        """Test filtering signal with maximum confidence."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=1.0,
            base_score=100.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)
        assert result.is_actionable is True

    def test_negative_threshold(self):
        """Test handling of negative threshold."""
        filter_obj = ConfidenceFilter(threshold=-0.5)
        # Should be clamped to minimum
        assert filter_obj.threshold == 0.50


class TestFilterMetrics:
    """Tests for FilterMetrics dataclass."""

    def test_initial_metrics(self):
        """Test initial metrics state."""
        metrics = FilterMetrics()
        assert metrics.total_processed == 0
        assert metrics.signals_filtered == 0
        assert metrics.signals_passed == 0
        assert metrics.filter_rate == 0.0
        assert metrics.pass_rate == 0.0

    def test_filter_rate_calculation(self):
        """Test filter rate calculation."""
        metrics = FilterMetrics()
        metrics.total_processed = 10
        metrics.signals_filtered = 7
        metrics.signals_passed = 3
        assert metrics.filter_rate == 0.7
        assert metrics.pass_rate == 0.3

    def test_filter_rate_zero_total(self):
        """Test filter rate with zero total processed."""
        metrics = FilterMetrics()
        assert metrics.filter_rate == 0.0
        assert metrics.pass_rate == 0.0

    def test_to_dict(self):
        """Test metrics to dictionary conversion."""
        metrics = FilterMetrics()
        metrics.total_processed = 100
        metrics.signals_filtered = 60
        metrics.signals_passed = 40

        result = metrics.to_dict()
        assert result["total_processed"] == 100
        assert result["signals_filtered"] == 60
        assert result["signals_passed"] == 40
        assert result["filter_rate"] == 0.6
        assert result["pass_rate"] == 0.4
        assert "last_updated" in result

    def test_for_influxdb(self):
        """Test metrics formatting for InfluxDB."""
        metrics = FilterMetrics()
        metrics.total_processed = 50
        metrics.signals_filtered = 25
        metrics.signals_passed = 25

        result = metrics.for_influxdb()
        assert result["total_processed"] == 50
        assert result["signals_filtered"] == 25
        assert result["signals_passed"] == 25
        assert result["filter_rate"] == 0.5


class TestConfidenceFilterMetrics:
    """Tests for ConfidenceFilter metrics tracking."""

    def test_metrics_initialized_on_creation(self):
        """Test metrics are initialized when filter is created."""
        filter_obj = ConfidenceFilter(threshold=0.75)
        assert filter_obj.metrics is not None
        assert filter_obj.metrics.total_processed == 0

    def test_metrics_tracking_actionable_signal(self):
        """Test metrics update when filtering actionable signal."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)
        assert result.is_actionable is True

        assert filter_obj.metrics.total_processed == 1
        assert filter_obj.metrics.signals_passed == 1
        assert filter_obj.metrics.signals_filtered == 0

    def test_metrics_tracking_filtered_signal(self):
        """Test metrics update when filtering non-actionable signal."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        result = filter_obj.filter(signal)
        assert result.is_actionable is False

        assert filter_obj.metrics.total_processed == 1
        assert filter_obj.metrics.signals_passed == 0
        assert filter_obj.metrics.signals_filtered == 1

    def test_metrics_tracking_multiple_signals(self):
        """Test metrics tracking with multiple signals."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.60,
                base_score=60.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.LOGGED_ONLY,
                timeframe="1h",
            ),
            Signal(
                token="SOL/USDT",
                direction=SignalDirection.LONG,
                confidence=0.90,
                base_score=90.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="XRP/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.40,
                base_score=40.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.LOGGED_ONLY,
                timeframe="1h",
            ),
        ]

        for sig in signals:
            filter_obj.filter(sig)

        assert filter_obj.metrics.total_processed == 4
        assert filter_obj.metrics.signals_passed == 2
        assert filter_obj.metrics.signals_filtered == 2
        assert filter_obj.metrics.filter_rate == 0.5

    def test_get_metrics(self):
        """Test get_metrics returns FilterMetrics."""
        filter_obj = ConfidenceFilter(threshold=0.75)
        metrics = filter_obj.get_metrics()
        assert isinstance(metrics, FilterMetrics)

    def test_get_metrics_dict(self):
        """Test get_metrics_dict returns dictionary."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        filter_obj.filter(signal)

        result = filter_obj.get_metrics_dict()
        assert "total_processed" in result
        assert "signals_filtered" in result
        assert "signals_passed" in result
        assert "filter_rate" in result
        assert "pass_rate" in result

    def test_reset_metrics(self):
        """Test metrics reset functionality."""
        filter_obj = ConfidenceFilter(threshold=0.75)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )
        filter_obj.filter(signal)
        assert filter_obj.metrics.total_processed == 1

        filter_obj.reset_metrics()
        assert filter_obj.metrics.total_processed == 0
        assert filter_obj.metrics.signals_filtered == 0
        assert filter_obj.metrics.signals_passed == 0

    def test_get_filter_rate_trend(self):
        """Test filter rate trend returns list."""
        filter_obj = ConfidenceFilter(threshold=0.75)
        trend = filter_obj.get_filter_rate_trend()
        assert isinstance(trend, list)
        assert len(trend) == 1

    def test_set_influx_exporter(self):
        """Test setting InfluxDB exporter."""
        filter_obj = ConfidenceFilter(threshold=0.75)
        exporter = InfluxDBExporter()

        # Mock the logger to verify the message
        with patch("signal_generation.confidence_filter.logger") as mock_logger:
            filter_obj.set_influx_exporter(exporter)
            assert filter_obj._influx_exporter is exporter
            mock_logger.info.assert_called_once()


class TestInfluxDBExporter:
    """Tests for InfluxDBExporter."""

    def test_exporter_initialization(self):
        """Test InfluxDBExporter initialization."""
        exporter = InfluxDBExporter()
        assert exporter.influx_url == "http://chiseai-influxdb:18087"
        assert exporter.influx_org == "chiseai"
        assert exporter.influx_bucket == "chiseai"

    def test_exporter_custom_config(self):
        """Test InfluxDBExporter with custom config."""
        exporter = InfluxDBExporter(
            influx_url="http://custom:9999",
            influx_token="my-token",
            influx_org="my-org",
            influx_bucket="my-bucket",
        )
        assert exporter.influx_url == "http://custom:9999"
        assert exporter.influx_token == "my-token"
        assert exporter.influx_org == "my-org"
        assert exporter.influx_bucket == "my-bucket"

    def test_export_without_client(self):
        """Test export returns False without client."""
        exporter = InfluxDBExporter()
        metrics = FilterMetrics()
        result = exporter.export_filter_metrics(metrics)
        # Returns False because no client is configured
        assert result is False
