"""Unit tests for SignalQualityFilter.

Tests cover:
- Quality score threshold enforcement
- Missing quality_score handling
- Metadata preservation
- Metric tracking
- Edge cases (NaN, inf, boundary values)
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from signal_generation.quality_filter import (
    QualityFilter,
    QualityFilterMetrics,
    QualityFilterResult,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestQualityFilterInit:
    """Tests for QualityFilter initialization."""

    def test_default_threshold_is_50_percent(self):
        """Default threshold should be 0.5."""
        filter = QualityFilter()
        assert filter.threshold == 0.5

    def test_custom_threshold_from_constructor(self):
        """Custom threshold should be applied from constructor."""
        filter = QualityFilter(threshold=0.7)
        assert filter.threshold == 0.7

    def test_threshold_from_environment_variable(self, monkeypatch):
        """Threshold should be read from SIGNAL_QUALITY_THRESHOLD env var."""
        monkeypatch.setenv("SIGNAL_QUALITY_THRESHOLD", "0.65")
        filter = QualityFilter()
        assert filter.threshold == 0.65

    def test_constructor_override_environment(self, monkeypatch):
        """Constructor should override environment variable."""
        monkeypatch.setenv("SIGNAL_QUALITY_THRESHOLD", "0.65")
        filter = QualityFilter(threshold=0.8)
        assert filter.threshold == 0.8

    def test_threshold_clamped_to_valid_range(self):
        """Threshold above max should be clamped."""
        filter = QualityFilter(threshold=1.5)
        assert filter.threshold == 1.0

    def test_threshold_below_min_clamped(self):
        """Threshold below min should be clamped."""
        filter = QualityFilter(threshold=-0.5)
        assert filter.threshold == 0.0


class TestQualityFilterResult:
    """Tests for QualityFilterResult dataclass."""

    def test_result_attributes(self):
        """Result should contain all required attributes."""
        result = QualityFilterResult(
            is_qualified=True,
            threshold=0.5,
            quality_score=0.7,
            reason="Test reason",
            metadata_preserved=True,
        )
        assert result.is_qualified is True
        assert result.threshold == 0.5
        assert result.quality_score == 0.7
        assert result.reason == "Test reason"
        assert result.metadata_preserved is True

    def test_result_defaults_metadata_preserved(self):
        """Result should default metadata_preserved to True."""
        result = QualityFilterResult(
            is_qualified=False,
            threshold=0.5,
            quality_score=None,
            reason="Missing quality_score",
        )
        assert result.metadata_preserved is True


class TestQualityFilterMetrics:
    """Tests for QualityFilterMetrics."""

    def test_initial_metrics_are_zero(self):
        """Initial metrics should be zero."""
        metrics = QualityFilterMetrics()
        assert metrics.total_processed == 0
        assert metrics.signals_filtered == 0
        assert metrics.signals_passed == 0
        assert metrics.signals_missing_quality == 0

    def test_filter_rate_calculation(self):
        """Filter rate should be filtered/total."""
        metrics = QualityFilterMetrics()
        metrics.total_processed = 100
        metrics.signals_filtered = 25
        assert metrics.filter_rate == 0.25

    def test_pass_rate_calculation(self):
        """Pass rate should be passed/total."""
        metrics = QualityFilterMetrics()
        metrics.total_processed = 100
        metrics.signals_passed = 75
        assert metrics.pass_rate == 0.75

    def test_missing_quality_rate_calculation(self):
        """Missing quality rate should be missing/total."""
        metrics = QualityFilterMetrics()
        metrics.total_processed = 100
        metrics.signals_missing_quality = 10
        assert metrics.missing_quality_rate == 0.1

    def test_zero_total_returns_zero_rates(self):
        """Zero total processed should return 0.0 for all rates."""
        metrics = QualityFilterMetrics()
        assert metrics.filter_rate == 0.0
        assert metrics.pass_rate == 0.0
        assert metrics.missing_quality_rate == 0.0

    def test_to_dict_format(self):
        """Metrics should export to dict correctly."""
        metrics = QualityFilterMetrics()
        metrics.total_processed = 50
        metrics.signals_filtered = 10
        metrics.signals_passed = 35
        metrics.signals_missing_quality = 5

        result = metrics.to_dict()
        assert result["total_processed"] == 50
        assert result["signals_filtered"] == 10
        assert result["signals_passed"] == 35
        assert result["signals_missing_quality"] == 5
        assert result["filter_rate"] == 0.2
        assert result["pass_rate"] == 0.7
        assert result["missing_quality_rate"] == 0.1
        assert "last_updated" in result


class SignalFactory:
    """Helper to create test signals."""

    @staticmethod
    def create_signal(
        token: str = "BTC/USDT",
        direction: SignalDirection = SignalDirection.LONG,
        confidence: float = 0.8,
        base_score: float = 70.0,
        status: SignalStatus = SignalStatus.ACTIONABLE,
        timeframe: str = "1H",
        metadata: dict | None = None,
    ) -> Signal:
        """Create a test signal."""
        return Signal(
            token=token,
            direction=direction,
            confidence=confidence,
            base_score=base_score,
            timestamp=datetime.now(UTC),
            status=status,
            timeframe=timeframe,
            metadata=metadata or {},
        )


class TestQualityFilterFiltering:
    """Tests for QualityFilter.filter() method."""

    def test_signal_above_threshold_passes(self):
        """Signal with quality_score above threshold should pass."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.7})

        result = filter.filter(signal)

        assert result.is_qualified is True
        assert result.quality_score == 0.7
        assert result.metadata_preserved is True

    def test_signal_at_threshold_passes(self):
        """Signal with quality_score at threshold should pass."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.5})

        result = filter.filter(signal)

        assert result.is_qualified is True
        assert result.quality_score == 0.5

    def test_signal_below_threshold_filtered(self):
        """Signal with quality_score below threshold should be filtered."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.3})

        result = filter.filter(signal)

        assert result.is_qualified is False
        assert result.quality_score == 0.3

    def test_signal_missing_quality_score_filtered(self):
        """Signal missing quality_score should be filtered."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={})

        result = filter.filter(signal)

        assert result.is_qualified is False
        assert result.quality_score is None
        assert "missing" in result.reason.lower()

    def test_signal_with_none_metadata_filtered(self):
        """Signal with None metadata should be filtered."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata=None)

        result = filter.filter(signal)

        assert result.is_qualified is False

    def test_signal_with_nan_quality_filtered(self):
        """Signal with NaN quality_score should be filtered."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": float("nan")})

        result = filter.filter(signal)

        assert result.is_qualified is False

    def test_signal_with_inf_quality_filtered(self):
        """Signal with inf quality_score should be filtered."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": float("inf")})

        result = filter.filter(signal)

        assert result.is_qualified is False

    def test_signal_with_string_quality_treated_as_missing(self):
        """Signal with non-numeric quality_score should be treated as missing."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": "high"})

        result = filter.filter(signal)

        assert result.is_qualified is False
        assert result.quality_score is None


class TestQualityFilterShouldTrade:
    """Tests for QualityFilter.should_trade() method."""

    def test_should_trade_above_threshold(self):
        """should_trade returns True for quality above threshold."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.7})

        assert filter.should_trade(signal) is True

    def test_should_trade_below_threshold(self):
        """should_trade returns False for quality below threshold."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.3})

        assert filter.should_trade(signal) is False

    def test_should_trade_missing_quality(self):
        """should_trade returns False when quality is missing."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={})

        assert filter.should_trade(signal) is False


class TestQualityFilterMetricsTracking:
    """Tests for metric tracking during filtering."""

    def test_metrics_increment_on_filter(self):
        """Metrics should increment correctly on filter()."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.7})

        filter.filter(signal)

        assert filter.metrics.total_processed == 1
        assert filter.metrics.signals_passed == 1
        assert filter.metrics.signals_filtered == 0

    def test_metrics_track_filtered_signals(self):
        """Metrics should track filtered signals."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.3})

        filter.filter(signal)

        assert filter.metrics.total_processed == 1
        assert filter.metrics.signals_filtered == 1
        assert filter.metrics.signals_passed == 0

    def test_metrics_track_missing_quality(self):
        """Metrics should track signals with missing quality_score."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={})

        filter.filter(signal)

        assert filter.metrics.total_processed == 1
        assert filter.metrics.signals_missing_quality == 1

    def test_reset_metrics(self):
        """reset_metrics should clear all counters."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.7})
        filter.filter(signal)

        filter.reset_metrics()

        assert filter.metrics.total_processed == 0
        assert filter.metrics.signals_passed == 0
        assert filter.metrics.signals_filtered == 0


class TestQualityFilterEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_threshold_passes_all(self):
        """Zero threshold should pass all signals with quality."""
        filter = QualityFilter(threshold=0.0)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.1})

        result = filter.filter(signal)

        assert result.is_qualified is True

    def test_full_quality_threshold(self):
        """Full (1.0) threshold should only pass perfect quality."""
        filter = QualityFilter(threshold=1.0)
        signal = SignalFactory.create_signal(metadata={"quality_score": 1.0})

        result = filter.filter(signal)

        assert result.is_qualified is True

    def test_just_below_full_quality_fails(self):
        """Just below 1.0 quality should fail at 1.0 threshold."""
        filter = QualityFilter(threshold=1.0)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.99})

        result = filter.filter(signal)

        assert result.is_qualified is False

    def test_boundary_value_0_5_exactly(self):
        """Boundary value 0.5 should pass at 0.5 threshold."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.5})

        result = filter.filter(signal)

        assert result.is_qualified is True

    def test_just_below_boundary_fails(self):
        """Just below boundary should fail."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.4999})

        result = filter.filter(signal)

        assert result.is_qualified is False


class TestMetadataPreservation:
    """Tests for metadata integrity preservation."""

    def test_metadata_not_modified_after_filter(self):
        """Signal metadata should not be modified by filtering."""
        filter = QualityFilter(threshold=0.5)
        original_metadata = {"quality_score": 0.7, "custom_field": "test"}
        signal = SignalFactory.create_signal(metadata=original_metadata.copy())

        filter.filter(signal)

        # Metadata should be unchanged
        assert signal.metadata == original_metadata
        assert signal.metadata["quality_score"] == 0.7
        assert signal.metadata["custom_field"] == "test"

    def test_filter_does_not_add_fields_to_metadata(self):
        """Filter should not add fields to signal metadata."""
        filter = QualityFilter(threshold=0.5)
        original_metadata = {"quality_score": 0.7}
        signal = SignalFactory.create_signal(metadata=original_metadata.copy())

        filter.filter(signal)

        # Should only have original fields
        assert list(signal.metadata.keys()) == ["quality_score"]


class TestLogUnqualified:
    """Tests for logging unqualified signals."""

    def test_log_unqualified_with_score(self, caplog):
        """Log should include quality score when available."""
        import logging

        caplog.set_level(logging.INFO)
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.3})

        filter.log_unqualified(signal, 0.3)

        assert "quality_score" in caplog.text
        # Quality score 0.3 should appear in the log as 30.0%
        assert "30.0%" in caplog.text

    def test_log_unqualified_with_missing_score(self, caplog):
        """Log should indicate missing score."""
        import logging

        caplog.set_level(logging.INFO)
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={})

        filter.log_unqualified(signal, None)

        assert "missing" in caplog.text.lower()


class TestGetThresholdPercent:
    """Tests for threshold percentage conversion."""

    def test_get_threshold_percent(self):
        """Should return threshold as percentage."""
        filter = QualityFilter(threshold=0.5)
        assert filter.get_threshold_percent() == 50.0

    def test_get_threshold_percent_70(self):
        """Should return 70% for 0.7 threshold."""
        filter = QualityFilter(threshold=0.7)
        assert filter.get_threshold_percent() == 70.0


class TestGetMetricsDict:
    """Tests for metrics dictionary export."""

    def test_get_metrics_dict_format(self):
        """Should return properly formatted metrics dict."""
        filter = QualityFilter(threshold=0.5)
        signal = SignalFactory.create_signal(metadata={"quality_score": 0.7})
        filter.filter(signal)

        metrics_dict = filter.get_metrics_dict()

        assert "total_processed" in metrics_dict
        assert "signals_passed" in metrics_dict
        assert "signals_filtered" in metrics_dict
        assert "signals_missing_quality" in metrics_dict
        assert "filter_rate" in metrics_dict
        assert "pass_rate" in metrics_dict
        assert "last_updated" in metrics_dict
