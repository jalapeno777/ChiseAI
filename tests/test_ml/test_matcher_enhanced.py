"""Enhanced tests for Prediction-Outcome Matcher.

Tests the enhanced matcher functionality including:
- Outcome capture service integration
- Matching windows per timeframe
- Match quality metrics (precision, recall, F1) per signal type
- Batch processing with graceful partial failure handling
- >95% matching accuracy requirement

For ST-LAUNCH-008: Prediction-Outcome Matcher Enhancement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Import the enhanced matcher
from ml.feedback.matcher import (
    DEFAULT_MATCHING_WINDOWS,
    MatchBatchResult,
    MatchConfidence,
    MatchConfig,
    MatchQualityMetrics,
    MatchStatus,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
    SignalType,
)


class MockDirection(Enum):
    """Mock direction enum."""

    LONG = "long"
    SHORT = "short"


@dataclass
class MockSignalRecord:
    """Mock signal record for testing."""

    signal_id: str
    token: str
    direction: MockDirection
    timestamp: int
    signal_type: str = "entry"
    timeframe: str = "1h"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "token": self.token,
            "direction": self.direction.value,
            "timestamp": self.timestamp,
            "signal_type": self.signal_type,
            "timeframe": self.timeframe,
        }


@dataclass
class MockOutcomeRecord:
    """Mock outcome record for testing."""

    outcome_id: str
    symbol: str
    side: str
    exit_timestamp: int
    outcome_type: str = "tp_hit"
    pnl: Decimal = field(default_factory=lambda: Decimal("100"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "symbol": self.symbol,
            "side": self.side,
            "exit_timestamp": self.exit_timestamp,
            "outcome_type": self.outcome_type,
            "pnl": str(self.pnl),
        }


class TestMatchConfig:
    """Tests for MatchConfig."""

    def test_default_creation(self):
        """Test creating MatchConfig with defaults."""
        config = MatchConfig()

        assert config.matching_window_hours == 24.0
        assert config.min_confidence_threshold == 0.95
        assert config.allow_multiple_outcomes is False
        assert config.enable_partial_failure_handling is True
        assert config.max_concurrent_matches == 10
        assert config.batch_size == 100

    def test_timeframe_windows_loaded(self):
        """Test that default timeframe windows are loaded."""
        config = MatchConfig()

        # Check acceptance criteria windows
        assert config.timeframe_windows["1m"] == 0.5  # 30 minutes
        assert config.timeframe_windows["5m"] == 2.0  # 2 hours
        assert config.timeframe_windows["15m"] == 6.0  # 6 hours
        assert config.timeframe_windows["1h"] == 24.0  # 24 hours
        assert config.timeframe_windows["4h"] == 72.0  # 3 days
        assert config.timeframe_windows["1d"] == 168.0  # 7 days

    def test_get_window_for_timeframe(self):
        """Test getting window for specific timeframe."""
        config = MatchConfig()

        assert config.get_window_for_timeframe("1m") == 0.5
        assert config.get_window_for_timeframe("5m") == 2.0
        assert config.get_window_for_timeframe("15m") == 6.0
        assert config.get_window_for_timeframe("1h") == 24.0
        assert config.get_window_for_timeframe("4h") == 72.0
        assert config.get_window_for_timeframe("1d") == 168.0

    def test_get_window_for_unknown_timeframe(self):
        """Test getting window for unknown timeframe returns default."""
        config = MatchConfig(matching_window_hours=48.0)

        assert config.get_window_for_timeframe("unknown") == 48.0
        assert config.get_window_for_timeframe(None) == 48.0

    def test_custom_timeframe_windows(self):
        """Test custom timeframe windows override defaults."""
        config = MatchConfig(timeframe_windows={"1m": 1.0, "custom": 100.0})

        # Custom overrides default
        assert config.timeframe_windows["1m"] == 1.0
        # New custom window added
        assert config.timeframe_windows["custom"] == 100.0
        # Other defaults still present
        assert config.timeframe_windows["5m"] == 2.0

    def test_get_window_for_signal(self):
        """Test getting window for a signal."""
        config = MatchConfig()

        signal = MockSignalRecord(
            signal_id="test-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=0,
            timeframe="5m",
        )

        window = config.get_window_for_signal(signal)
        assert window == 2.0  # 5m timeframe window


class TestMatchQualityMetrics:
    """Tests for MatchQualityMetrics."""

    def test_default_creation(self):
        """Test creating MatchQualityMetrics."""
        metrics = MatchQualityMetrics(signal_type=SignalType.ENTRY)

        assert metrics.signal_type == SignalType.ENTRY
        assert metrics.true_positives == 0
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0

    def test_calculate_perfect_metrics(self):
        """Test metrics calculation with perfect predictions."""
        metrics = MatchQualityMetrics(
            signal_type=SignalType.ENTRY,
            true_positives=100,
            false_positives=0,
            false_negatives=0,
            total_predictions=100,
        )
        metrics.calculate()

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.accuracy == 1.0

    def test_calculate_with_errors(self):
        """Test metrics calculation with errors."""
        metrics = MatchQualityMetrics(
            signal_type=SignalType.ENTRY,
            true_positives=80,
            false_positives=10,
            false_negatives=10,
            total_predictions=100,
        )
        metrics.calculate()

        # Precision: 80 / (80 + 10) = 0.8889
        assert abs(metrics.precision - 0.8889) < 0.001
        # Recall: 80 / (80 + 10) = 0.8889
        assert abs(metrics.recall - 0.8889) < 0.001
        # F1: 2 * (0.8889 * 0.8889) / (0.8889 + 0.8889) = 0.8889
        assert abs(metrics.f1_score - 0.8889) < 0.001
        # Accuracy: 80 / 100 = 0.8
        assert metrics.accuracy == 0.8

    def test_calculate_zero_division(self):
        """Test metrics calculation with zero division."""
        metrics = MatchQualityMetrics(
            signal_type=SignalType.ENTRY,
            true_positives=0,
            false_positives=0,
            false_negatives=0,
            total_predictions=0,
        )
        metrics.calculate()

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.accuracy == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = MatchQualityMetrics(
            signal_type=SignalType.EXIT,
            true_positives=50,
            false_positives=10,
            false_negatives=5,
            total_predictions=65,
        )
        metrics.calculate()

        data = metrics.to_dict()

        assert data["signal_type"] == "exit"
        assert data["true_positives"] == 50
        assert data["false_positives"] == 10
        assert data["false_negatives"] == 5
        assert "precision" in data
        assert "recall" in data
        assert "f1_score" in data


class TestPredictionOutcomeMatch:
    """Tests for PredictionOutcomeMatch."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        signal = MockSignalRecord(
            signal_id="test-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000,
        )
        outcome = MockOutcomeRecord(
            outcome_id="out-1",
            symbol="BTCUSDT",
            side="Buy",
            exit_timestamp=5000,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-1",
            signal=signal,
            outcome=outcome,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            confidence_score=0.98,
            match_time_ms=6000,
            match_latency_hours=1.0,
            resolution_quality=0.95,
            signal_type=SignalType.ENTRY,
        )

        data = match.to_dict()

        assert data["signal_id"] == "test-1"
        assert data["status"] == "matched"
        assert data["confidence"] == "high"
        assert data["confidence_score"] == 0.98
        assert data["signal_type"] == "entry"


class TestMatchBatchResult:
    """Tests for MatchBatchResult."""

    def test_match_rate(self):
        """Test match rate calculation."""
        result = MatchBatchResult(
            total_signals=100,
            matched=80,
        )

        assert result.match_rate == 0.8

    def test_match_rate_zero(self):
        """Test match rate with zero signals."""
        result = MatchBatchResult(total_signals=0)

        assert result.match_rate == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        result = MatchBatchResult(
            total_signals=100,
            matched=80,
            errors=5,
        )

        assert result.success_rate == 0.95


class TestPredictionOutcomeMatcher:
    """Tests for PredictionOutcomeMatcher."""

    @pytest.fixture
    def mock_signal_tracker(self):
        """Create mock signal tracker."""
        tracker = AsyncMock()
        return tracker

    @pytest.fixture
    def mock_outcome_service(self):
        """Create mock outcome capture service."""
        service = AsyncMock()
        return service

    @pytest.fixture
    def matcher(self, mock_signal_tracker, mock_outcome_service):
        """Create matcher with mocks."""
        config = MatchConfig(min_confidence_threshold=0.95)
        return PredictionOutcomeMatcher(
            signal_tracker=mock_signal_tracker,
            config=config,
            outcome_capture_service=mock_outcome_service,
        )

    @pytest.fixture
    def sample_signal(self):
        """Create sample signal."""
        return MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000000,
            signal_type="entry",
            timeframe="1h",
        )

    @pytest.fixture
    def sample_outcome(self):
        """Create sample outcome."""
        return MockOutcomeRecord(
            outcome_id="out-1",
            symbol="BTCUSDT",
            side="Buy",
            exit_timestamp=2000000,  # Within 24h window
            outcome_type="tp_hit",
        )

    @pytest.mark.asyncio
    async def test_match_single_unresolved(self, matcher, sample_signal):
        """Test matching signal within window (unresolved)."""
        current_time = sample_signal.timestamp + 1000  # Within window

        result = await matcher.match_single(
            signal=sample_signal,
            outcomes=[],
            current_time_ms=current_time,
        )

        assert result.status == MatchStatus.UNRESOLVED
        assert result.confidence == MatchConfidence.UNKNOWN
        assert result.signal_id == sample_signal.signal_id

    @pytest.mark.asyncio
    async def test_match_single_expired_no_outcomes(self, matcher, sample_signal):
        """Test matching expired signal with no outcomes."""
        # Set time past 24h window
        current_time = sample_signal.timestamp + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=sample_signal,
            outcomes=[],
            current_time_ms=current_time,
        )

        assert result.status == MatchStatus.EXPIRED
        assert result.confidence == MatchConfidence.UNKNOWN

    @pytest.mark.asyncio
    async def test_match_single_success(self, matcher, sample_signal, sample_outcome):
        """Test successful match."""
        # Set time past window but with valid outcome
        current_time = sample_signal.timestamp + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=sample_signal,
            outcomes=[sample_outcome],
            current_time_ms=current_time,
        )

        assert result.status == MatchStatus.MATCHED
        assert result.outcome == sample_outcome
        assert result.signal_id == sample_signal.signal_id

    @pytest.mark.asyncio
    async def test_match_single_high_confidence(self, matcher, sample_signal):
        """Test high confidence match (>=95%)."""
        # Create outcome that matches perfectly
        outcome = MockOutcomeRecord(
            outcome_id="out-1",
            symbol="BTCUSDT",
            side="Buy",
            exit_timestamp=sample_signal.timestamp + 3600000,  # 1 hour later
            outcome_type="tp_hit",
        )

        current_time = sample_signal.timestamp + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=sample_signal,
            outcomes=[outcome],
            current_time_ms=current_time,
        )

        assert result.status == MatchStatus.MATCHED
        assert result.confidence_score >= 0.95
        assert result.confidence == MatchConfidence.HIGH

    @pytest.mark.asyncio
    async def test_match_batch(self, matcher):
        """Test batch matching."""
        signals = [
            MockSignalRecord(
                signal_id=f"sig-{i}",
                token="BTC",
                direction=MockDirection.LONG,
                timestamp=1000000 + (i * 1000),
                timeframe="1h",
            )
            for i in range(5)
        ]

        # Provide outcomes for all signals - 2 with valid outcomes, 3 with empty lists
        outcomes = {
            "sig-0": [MockOutcomeRecord("out-0", "BTCUSDT", "Buy", 2000000)],
            "sig-1": [MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2100000)],
            "sig-2": [],  # Empty outcomes - should be expired
            "sig-3": [],  # Empty outcomes - should be expired
            "sig-4": [],  # Empty outcomes - should be expired
        }

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_batch(signals, outcomes, current_time)

        assert result.total_signals == 5
        assert result.matched == 2
        assert result.expired == 3  # No outcomes for sig-2, sig-3, sig-4
        assert len(result.matches) == 5

    @pytest.mark.asyncio
    async def test_match_batch_with_partial_failure_handling(self, matcher):
        """Test batch matching with partial failure handling."""
        signals = [
            MockSignalRecord(
                signal_id=f"sig-{i}",
                token="BTC",
                direction=MockDirection.LONG,
                timestamp=1000000,
                timeframe="1h",
            )
            for i in range(5)
        ]

        # Provide outcomes for all signals - 2 with valid outcomes, 3 with empty lists
        outcomes = {
            "sig-0": [MockOutcomeRecord("out-0", "BTCUSDT", "Buy", 2000000)],
            "sig-1": [MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2100000)],
            "sig-2": [],  # Empty outcomes
            "sig-3": [],  # Empty outcomes
            "sig-4": [],  # Empty outcomes
        }

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_batch_with_partial_failure_handling(
            signals, outcomes, current_time
        )

        assert result.total_signals == 5
        assert result.matched == 2
        assert result.expired == 3  # 3 signals expired (no outcomes)
        # partial_failure is only True when there are actual errors, not expired signals
        assert result.partial_failure is False  # No errors, just expired

    @pytest.mark.asyncio
    async def test_partial_failure_with_exception(self, matcher, sample_signal):
        """Test partial failure handling with actual exception."""
        # Create a signal that will cause an error
        bad_signal = MockSignalRecord(
            signal_id="bad-sig",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=None,  # This will cause an error
        )

        signals = [sample_signal, bad_signal]
        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_batch_with_partial_failure_handling(
            signals, {}, current_time
        )

        assert result.partial_failure is True
        assert result.errors >= 1
        assert "bad-sig" in result.failed_signal_ids
        # First signal should still be processed
        assert result.total_signals == 2

    def test_calculate_match_quality_metrics(self, matcher):
        """Test match quality metrics calculation."""
        # Simulate some matches
        signal = MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000000,
            signal_type="entry",
        )
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000)

        # Create high confidence match
        match1 = PredictionOutcomeMatch(
            signal_id="sig-1",
            signal=signal,
            outcome=outcome,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            confidence_score=0.98,
            signal_type=SignalType.ENTRY,
        )
        matcher._match_history.append(match1)
        matcher._update_metrics(match1)

        # Create expired match (false negative)
        match2 = PredictionOutcomeMatch(
            signal_id="sig-2",
            signal=signal,
            outcome=None,
            status=MatchStatus.EXPIRED,
            confidence=MatchConfidence.UNKNOWN,
            confidence_score=0.0,
            signal_type=SignalType.ENTRY,
        )
        matcher._match_history.append(match2)
        matcher._update_metrics(match2)

        metrics = matcher.calculate_match_quality_metrics(SignalType.ENTRY)

        assert metrics.signal_type == SignalType.ENTRY
        assert metrics.true_positives == 1
        assert metrics.false_negatives == 1
        assert metrics.total_predictions == 2

    def test_get_high_confidence_match_rate(self, matcher):
        """Test high confidence match rate calculation."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000)

        # Add high confidence match
        matcher._match_history.append(
            PredictionOutcomeMatch(
                signal_id="sig-1",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                confidence_score=0.98,
            )
        )

        # Add low confidence match
        matcher._match_history.append(
            PredictionOutcomeMatch(
                signal_id="sig-2",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.LOW,
                confidence_score=0.5,
            )
        )

        rate = matcher.get_high_confidence_match_rate()
        assert rate == 0.5  # 1 out of 2

    def test_get_overall_accuracy(self, matcher):
        """Test overall accuracy calculation."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000)

        # Add successful match
        match = PredictionOutcomeMatch(
            signal_id="sig-1",
            signal=signal,
            outcome=outcome,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            confidence_score=0.98,
            signal_type=SignalType.ENTRY,
        )
        matcher._update_metrics(match)

        accuracy = matcher.get_overall_accuracy()
        assert accuracy == 1.0  # 1 TP out of 1 prediction

    def test_detect_signal_type(self, matcher):
        """Test signal type detection."""
        entry_signal = MockSignalRecord(
            "sig-1", "BTC", MockDirection.LONG, 1000, signal_type="entry"
        )
        exit_signal = MockSignalRecord(
            "sig-2", "BTC", MockDirection.LONG, 1000, signal_type="exit"
        )
        sl_signal = MockSignalRecord(
            "sig-3", "BTC", MockDirection.LONG, 1000, signal_type="sl"
        )
        tp_signal = MockSignalRecord(
            "sig-4", "BTC", MockDirection.LONG, 1000, signal_type="tp"
        )

        assert matcher._detect_signal_type(entry_signal) == SignalType.ENTRY
        assert matcher._detect_signal_type(exit_signal) == SignalType.EXIT
        assert matcher._detect_signal_type(sl_signal) == SignalType.STOP_LOSS
        assert matcher._detect_signal_type(tp_signal) == SignalType.TAKE_PROFIT

    def test_get_metrics_summary(self, matcher):
        """Test metrics summary generation."""
        summary = matcher.get_metrics_summary()

        assert "overall_accuracy" in summary
        assert "high_confidence_match_rate" in summary
        assert "total_matches" in summary
        assert "metrics_by_signal_type" in summary

    def test_clear_history(self, matcher):
        """Test clearing match history."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000)
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000)

        matcher._match_history.append(
            PredictionOutcomeMatch(
                signal_id="sig-1",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
            )
        )

        assert len(matcher._match_history) == 1

        matcher.clear_history()

        assert len(matcher._match_history) == 0


class TestMatchingAccuracy:
    """Tests specifically for >95% matching accuracy requirement."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with default config."""
        return PredictionOutcomeMatcher(config=MatchConfig())

    @pytest.mark.asyncio
    async def test_accuracy_calculation(self, matcher):
        """Test that accuracy is calculated correctly."""
        # Create 100 signals with 95 perfect matches (95% accuracy)
        base_time = 1000000

        for i in range(95):
            signal = MockSignalRecord(
                signal_id=f"sig-{i}",
                token="BTC",
                direction=MockDirection.LONG,
                timestamp=base_time + (i * 1000),
                signal_type="entry",
            )
            outcome = MockOutcomeRecord(
                outcome_id=f"out-{i}",
                symbol="BTCUSDT",
                side="Buy",
                exit_timestamp=base_time + (i * 1000) + 3600000,  # 1 hour later
            )

            match = PredictionOutcomeMatch(
                signal_id=signal.signal_id,
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                confidence_score=1.0,
                signal_type=SignalType.ENTRY,
            )
            matcher._match_history.append(match)
            matcher._update_metrics(match)

        # Add 5 expired (missed matches)
        for i in range(95, 100):
            signal = MockSignalRecord(
                signal_id=f"sig-{i}",
                token="BTC",
                direction=MockDirection.LONG,
                timestamp=base_time + (i * 1000),
                signal_type="entry",
            )

            match = PredictionOutcomeMatch(
                signal_id=signal.signal_id,
                signal=signal,
                outcome=None,
                status=MatchStatus.EXPIRED,
                confidence=MatchConfidence.UNKNOWN,
                confidence_score=0.0,
                signal_type=SignalType.ENTRY,
            )
            matcher._match_history.append(match)
            matcher._update_metrics(match)

        accuracy = matcher.get_overall_accuracy()
        assert accuracy == 0.95  # 95% accuracy

    @pytest.mark.asyncio
    async def test_high_confidence_threshold(self, matcher):
        """Test that high confidence matches are >=95%."""
        base_time = 1000000

        signal = MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=base_time,
        )
        outcome = MockOutcomeRecord(
            outcome_id="out-1",
            symbol="BTCUSDT",
            side="Buy",
            exit_timestamp=base_time + 3600000,
        )

        # Test with current time past the window
        current_time = base_time + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=signal,
            outcomes=[outcome],
            current_time_ms=current_time,
        )

        # Should have high confidence (>=0.95)
        if result.status == MatchStatus.MATCHED:
            assert result.confidence_score >= 0.95
            assert result.confidence == MatchConfidence.HIGH


class TestTimeframeWindows:
    """Tests for timeframe-specific matching windows."""

    def test_all_required_timeframes_present(self):
        """Test that all required timeframe windows are present."""
        required_windows = {
            "1m": 0.5,  # 30 minutes
            "5m": 2.0,  # 2 hours
            "15m": 6.0,  # 6 hours
            "1h": 24.0,  # 24 hours
            "4h": 72.0,  # 3 days
            "1d": 168.0,  # 7 days
        }

        for timeframe, expected_hours in required_windows.items():
            assert timeframe in DEFAULT_MATCHING_WINDOWS
            assert DEFAULT_MATCHING_WINDOWS[timeframe] == expected_hours

    @pytest.mark.asyncio
    async def test_1m_timeframe_window(self):
        """Test 1m timeframe uses 30 minute window."""
        config = MatchConfig()
        signal = MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000000,
            timeframe="1m",
        )

        window = config.get_window_for_signal(signal)
        assert window == 0.5  # 30 minutes

    @pytest.mark.asyncio
    async def test_4h_timeframe_window(self):
        """Test 4h timeframe uses 3 day window."""
        config = MatchConfig()
        signal = MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000000,
            timeframe="4h",
        )

        window = config.get_window_for_signal(signal)
        assert window == 72.0  # 3 days

    @pytest.mark.asyncio
    async def test_1d_timeframe_window(self):
        """Test 1d timeframe uses 7 day window."""
        config = MatchConfig()
        signal = MockSignalRecord(
            signal_id="sig-1",
            token="BTC",
            direction=MockDirection.LONG,
            timestamp=1000000,
            timeframe="1d",
        )

        window = config.get_window_for_signal(signal)
        assert window == 168.0  # 7 days


class TestSignalTypeMetrics:
    """Tests for metrics per signal type."""

    @pytest.fixture
    def matcher(self):
        """Create matcher."""
        return PredictionOutcomeMatcher()

    def test_metrics_per_signal_type(self, matcher):
        """Test that metrics are tracked per signal type."""
        # Add entry signal match
        entry_signal = MockSignalRecord(
            "sig-1", "BTC", MockDirection.LONG, 1000, signal_type="entry"
        )
        entry_outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000)

        entry_match = PredictionOutcomeMatch(
            signal_id="sig-1",
            signal=entry_signal,
            outcome=entry_outcome,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            signal_type=SignalType.ENTRY,
        )
        matcher._update_metrics(entry_match)

        # Add exit signal match
        exit_signal = MockSignalRecord(
            "sig-2", "BTC", MockDirection.LONG, 1000, signal_type="exit"
        )
        exit_outcome = MockOutcomeRecord("out-2", "BTCUSDT", "Sell", 2000)

        exit_match = PredictionOutcomeMatch(
            signal_id="sig-2",
            signal=exit_signal,
            outcome=exit_outcome,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            signal_type=SignalType.EXIT,
        )
        matcher._update_metrics(exit_match)

        # Get metrics for each type
        entry_metrics = matcher.calculate_match_quality_metrics(SignalType.ENTRY)
        exit_metrics = matcher.calculate_match_quality_metrics(SignalType.EXIT)

        assert entry_metrics.true_positives == 1
        assert exit_metrics.true_positives == 1

    def test_all_signal_types_tracked(self, matcher):
        """Test that all signal types have metrics tracked."""
        all_metrics = matcher.calculate_match_quality_metrics()

        assert SignalType.ENTRY in all_metrics
        assert SignalType.EXIT in all_metrics
        assert SignalType.STOP_LOSS in all_metrics
        assert SignalType.TAKE_PROFIT in all_metrics
        assert SignalType.UNKNOWN in all_metrics


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def matcher(self):
        """Create matcher."""
        return PredictionOutcomeMatcher()

    @pytest.mark.asyncio
    async def test_partial_fill_handling(self, matcher):
        """Test handling of partial fills."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)

        # Multiple outcomes for same signal (partial fills)
        outcomes = [
            MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000),
            MockOutcomeRecord("out-2", "BTCUSDT", "Buy", 2100000),
        ]

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=signal,
            outcomes=outcomes,
            current_time_ms=current_time,
        )

        # Should match with first (earliest) outcome
        assert result.status == MatchStatus.MATCHED
        assert result.outcome.outcome_id == "out-1"

    @pytest.mark.asyncio
    async def test_cancellation_handling(self, matcher):
        """Test handling of cancelled orders."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)

        # Outcome with cancellation
        outcome = MockOutcomeRecord(
            "out-1", "BTCUSDT", "Buy", 2000000, outcome_type="cancelled"
        )

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=signal,
            outcomes=[outcome],
            current_time_ms=current_time,
        )

        # Should still match but with potentially lower quality
        assert result.status == MatchStatus.MATCHED

    @pytest.mark.asyncio
    async def test_multiple_orders_same_signal(self, matcher):
        """Test handling of multiple orders for same signal."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)

        outcomes = [
            MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000),
            MockOutcomeRecord("out-2", "BTCUSDT", "Buy", 2200000),
            MockOutcomeRecord("out-3", "BTCUSDT", "Buy", 2400000),
        ]

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=signal,
            outcomes=outcomes,
            current_time_ms=current_time,
        )

        # Should match with earliest outcome
        assert result.status == MatchStatus.MATCHED
        assert result.outcome.outcome_id == "out-1"

    @pytest.mark.asyncio
    async def test_outcome_outside_window(self, matcher):
        """Test outcome that falls outside the matching window."""
        signal = MockSignalRecord(
            "sig-1", "BTC", MockDirection.LONG, 1000000, timeframe="1m"
        )

        # Outcome outside 30-minute window (at 2 hours)
        outcome = MockOutcomeRecord(
            "out-1", "BTCUSDT", "Buy", 1000000 + (2 * 3600 * 1000)
        )

        current_time = 1000000 + (25 * 3600 * 1000)

        result = await matcher.match_single(
            signal=signal,
            outcomes=[outcome],
            current_time_ms=current_time,
        )

        # Should be expired since outcome is outside window
        assert result.status == MatchStatus.EXPIRED
        assert result.metadata["reason"] == "outcomes_outside_window"


class TestIntegrationWithOutcomeService:
    """Tests for integration with outcome capture service."""

    @pytest.mark.asyncio
    async def test_outcome_service_integration(self):
        """Test matcher works with outcome capture service."""
        mock_service = AsyncMock()
        mock_service.get_outcomes_for_symbol.return_value = [
            MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000000)
        ]

        matcher = PredictionOutcomeMatcher(outcome_capture_service=mock_service)

        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000000)

        # Fetch outcomes through the service
        outcomes = await matcher._fetch_outcomes_for_signal(signal)

        # Should get outcomes from service
        mock_service.get_outcomes_for_symbol.assert_called_once()
        assert len(outcomes) == 1


class TestPrecisionRecallF1:
    """Tests for precision, recall, and F1 calculation."""

    @pytest.fixture
    def matcher(self):
        """Create matcher."""
        return PredictionOutcomeMatcher()

    def test_perfect_precision_recall(self, matcher):
        """Test perfect precision and recall."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000)
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000)

        # 10 perfect matches
        for i in range(10):
            match = PredictionOutcomeMatch(
                signal_id=f"sig-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                signal_type=SignalType.ENTRY,
            )
            matcher._update_metrics(match)

        metrics = matcher.calculate_match_quality_metrics(SignalType.ENTRY)

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0

    def test_zero_recall(self, matcher):
        """Test zero recall (all false negatives)."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000)

        # All expired (false negatives)
        for i in range(10):
            match = PredictionOutcomeMatch(
                signal_id=f"sig-{i}",
                signal=signal,
                outcome=None,
                status=MatchStatus.EXPIRED,
                confidence=MatchConfidence.UNKNOWN,
                signal_type=SignalType.ENTRY,
            )
            matcher._update_metrics(match)

        metrics = matcher.calculate_match_quality_metrics(SignalType.ENTRY)

        assert metrics.precision == 0.0  # No positive predictions
        assert metrics.recall == 0.0  # No true positives
        assert metrics.f1_score == 0.0

    def test_balanced_precision_recall(self, matcher):
        """Test balanced precision and recall."""
        signal = MockSignalRecord("sig-1", "BTC", MockDirection.LONG, 1000)
        outcome = MockOutcomeRecord("out-1", "BTCUSDT", "Buy", 2000)

        # 5 TP, 5 FP, 5 FN
        for i in range(5):
            # True positives
            match = PredictionOutcomeMatch(
                signal_id=f"sig-tp-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.HIGH,
                signal_type=SignalType.ENTRY,
            )
            matcher._update_metrics(match)

            # False positives (low confidence matches)
            match = PredictionOutcomeMatch(
                signal_id=f"sig-fp-{i}",
                signal=signal,
                outcome=outcome,
                status=MatchStatus.MATCHED,
                confidence=MatchConfidence.LOW,  # Low confidence = FP
                signal_type=SignalType.ENTRY,
            )
            matcher._update_metrics(match)

            # False negatives
            match = PredictionOutcomeMatch(
                signal_id=f"sig-fn-{i}",
                signal=signal,
                outcome=None,
                status=MatchStatus.EXPIRED,
                confidence=MatchConfidence.UNKNOWN,
                signal_type=SignalType.ENTRY,
            )
            matcher._update_metrics(match)

        metrics = matcher.calculate_match_quality_metrics(SignalType.ENTRY)

        # Precision: 5 / (5 + 5) = 0.5
        assert metrics.precision == 0.5
        # Recall: 5 / (5 + 5) = 0.5
        assert metrics.recall == 0.5
        # F1: 2 * (0.5 * 0.5) / (0.5 + 0.5) = 0.5
        assert metrics.f1_score == 0.5
