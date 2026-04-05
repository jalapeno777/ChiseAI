"""Unit tests for Signal confidence initialization and validation.

Tests cover:
- Signal.__post_init__ handling of NaN, None, and invalid values
- is_actionable property guards against invalid confidence
- ConfidenceFilter handling of invalid confidence values
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.signal_generation.confidence_filter import ConfidenceFilter
from src.signal_generation.models import Signal, SignalDirection, SignalStatus


class TestSignalConfidenceInitialization:
    """Tests for Signal confidence initialization and validation."""

    def _make_signal(
        self,
        confidence: float = 0.8,
        status: SignalStatus = SignalStatus.LOGGED_ONLY,
        **kwargs,
    ) -> Signal:
        """Helper to create a Signal with defaults."""
        defaults = {
            "token": "BTC/USDT",
            "direction": SignalDirection.LONG,
            "confidence": confidence,
            "base_score": 70.0,
            "timestamp": datetime.now(UTC),
            "status": status,
            "timeframe": "1H",
        }
        defaults.update(kwargs)
        return Signal(**defaults)

    # === NaN handling tests ===

    def test_signal_init_with_nan_confidence_defaults_to_zero(self):
        """Signal initialized with NaN confidence should default to 0.0."""
        signal = self._make_signal(confidence=float("nan"))
        assert signal.confidence == 0.0

    def test_signal_init_with_inf_confidence_defaults_to_zero(self):
        """Signal initialized with inf confidence should default to 0.0."""
        signal = self._make_signal(confidence=float("inf"))
        assert signal.confidence == 0.0

    def test_signal_init_with_negative_inf_confidence_defaults_to_zero(self):
        """Signal initialized with -inf confidence should default to 0.0."""
        signal = self._make_signal(confidence=float("-inf"))
        assert signal.confidence == 0.0

    def test_signal_init_with_none_confidence_defaults_to_zero(self):
        """Signal initialized with None confidence should default to 0.0."""
        # Pass None as a float conversion
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=None,  # type: ignore
            base_score=70.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1H",
        )
        assert signal.confidence == 0.0

    # === Valid confidence tests ===

    def test_signal_init_with_valid_confidence(self):
        """Signal initialized with valid confidence should preserve it."""
        signal = self._make_signal(confidence=0.75)
        assert signal.confidence == 0.75

    def test_signal_init_with_zero_confidence(self):
        """Signal initialized with 0.0 confidence should keep it."""
        signal = self._make_signal(confidence=0.0)
        assert signal.confidence == 0.0

    def test_signal_init_with_confidence_above_one_defaults_to_one(self):
        """Signal initialized with confidence > 1.0 should be clamped to 1.0."""
        signal = self._make_signal(confidence=1.5)
        assert signal.confidence == 1.0

    def test_signal_init_with_negative_confidence_defaults_to_zero(self):
        """Signal initialized with negative confidence should be clamped to 0.0."""
        signal = self._make_signal(confidence=-0.5)
        assert signal.confidence == 0.0

    # === base_score NaN handling tests ===

    def test_signal_init_with_nan_base_score_defaults_to_zero(self):
        """Signal initialized with NaN base_score should default to 0.0."""
        signal = self._make_signal(base_score=float("nan"))
        assert signal.base_score == 0.0

    def test_signal_init_with_none_base_score_defaults_to_zero(self):
        """Signal initialized with None base_score should default to 0.0."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            base_score=None,  # type: ignore
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1H",
        )
        assert signal.base_score == 0.0


class TestSignalIsActionable:
    """Tests for Signal.is_actionable property guards."""

    def _make_signal(
        self,
        confidence: float = 0.8,
        status: SignalStatus = SignalStatus.ACTIONABLE,
        **kwargs,
    ) -> Signal:
        """Helper to create a Signal with defaults."""
        defaults = {
            "token": "BTC/USDT",
            "direction": SignalDirection.LONG,
            "confidence": confidence,
            "base_score": 70.0,
            "timestamp": datetime.now(UTC),
            "status": status,
            "timeframe": "1H",
        }
        defaults.update(kwargs)
        return Signal(**defaults)

    def test_is_actionable_with_valid_confidence_above_threshold(self):
        """is_actionable should return True when confidence >= 0.75 and status is ACTIONABLE."""
        signal = self._make_signal(confidence=0.8, status=SignalStatus.ACTIONABLE)
        assert signal.is_actionable is True

    def test_is_actionable_with_confidence_at_threshold(self):
        """is_actionable should return True when confidence == 0.75 and status is ACTIONABLE."""
        signal = self._make_signal(confidence=0.75, status=SignalStatus.ACTIONABLE)
        assert signal.is_actionable is True

    def test_is_actionable_with_confidence_below_threshold(self):
        """is_actionable should return False when confidence < 0.75 even with ACTIONABLE status."""
        signal = self._make_signal(confidence=0.7, status=SignalStatus.ACTIONABLE)
        assert signal.is_actionable is False

    def test_is_actionable_with_zero_confidence(self):
        """is_actionable should return False when confidence is 0.0."""
        signal = self._make_signal(confidence=0.0, status=SignalStatus.ACTIONABLE)
        assert signal.is_actionable is False

    def test_is_actionable_with_nan_confidence(self):
        """is_actionable should return False when confidence is NaN."""
        signal = self._make_signal(
            confidence=float("nan"), status=SignalStatus.ACTIONABLE
        )
        assert signal.is_actionable is False

    def test_is_actionable_with_logged_only_status(self):
        """is_actionable should return False when status is LOGGED_ONLY."""
        signal = self._make_signal(confidence=0.9, status=SignalStatus.LOGGED_ONLY)
        assert signal.is_actionable is False

    def test_is_actionable_with_rate_limited_status(self):
        """is_actionable should return False when status is RATE_LIMITED."""
        signal = self._make_signal(confidence=0.9, status=SignalStatus.RATE_LIMITED)
        assert signal.is_actionable is False

    def test_is_actionable_with_stale_data_status(self):
        """is_actionable should return False when status is STALE_DATA."""
        signal = self._make_signal(confidence=0.9, status=SignalStatus.STALE_DATA)
        assert signal.is_actionable is False

    def test_is_actionable_with_error_status(self):
        """is_actionable should return False when status is ERROR."""
        signal = self._make_signal(confidence=0.9, status=SignalStatus.ERROR)
        assert signal.is_actionable is False


class TestConfidenceFilterWithInvalidConfidence:
    """Tests for ConfidenceFilter handling of invalid confidence values."""

    def _make_mock_signal(self, confidence: float = 0.8) -> MagicMock:
        """Create a mock signal with specified confidence."""
        signal = MagicMock()
        signal.confidence = confidence
        signal.token = "BTC/USDT"
        signal.direction_str = "LONG"
        signal.signal_id = "test-signal-id"
        return signal

    def test_filter_with_nan_confidence_returns_non_actionable(self):
        """Filter should mark signal with NaN confidence as non-actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=float("nan"))

        result = filter.filter(signal)

        assert result.is_actionable is False
        assert result.confidence == 0.0

    def test_filter_with_inf_confidence_returns_non_actionable(self):
        """Filter should mark signal with inf confidence as non-actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=float("inf"))

        result = filter.filter(signal)

        assert result.is_actionable is False
        assert result.confidence == 0.0

    def test_filter_with_negative_inf_confidence_returns_non_actionable(self):
        """Filter should mark signal with -inf confidence as non-actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=float("-inf"))

        result = filter.filter(signal)

        assert result.is_actionable is False
        assert result.confidence == 0.0

    def test_should_emit_with_nan_confidence_returns_false(self):
        """should_emit should return False when confidence is NaN."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=float("nan"))

        assert filter.should_emit(signal) is False

    def test_filter_with_valid_confidence_above_threshold(self):
        """Filter should mark signal with valid high confidence as actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=0.8)

        result = filter.filter(signal)

        assert result.is_actionable is True
        assert result.confidence == 0.8

    def test_filter_with_valid_confidence_at_threshold(self):
        """Filter should mark signal with confidence at threshold as actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=0.75)

        result = filter.filter(signal)

        assert result.is_actionable is True

    def test_filter_with_valid_confidence_below_threshold(self):
        """Filter should mark signal with valid low confidence as non-actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=0.7)

        result = filter.filter(signal)

        assert result.is_actionable is False

    def test_filter_with_zero_confidence_returns_non_actionable(self):
        """Filter should mark signal with 0.0 confidence as non-actionable."""
        filter = ConfidenceFilter(threshold=0.75)
        signal = self._make_mock_signal(confidence=0.0)

        result = filter.filter(signal)

        assert result.is_actionable is False
