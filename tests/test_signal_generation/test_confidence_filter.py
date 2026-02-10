"""Tests for confidence filter module."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import patch

from signal_generation.confidence_filter import ConfidenceFilter, FilterResult
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
