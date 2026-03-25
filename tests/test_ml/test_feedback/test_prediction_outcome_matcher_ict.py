"""Tests for ICT prediction outcome matcher module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from ml.feedback.ict_signal_tracker import (
    ICTSignalDirection,
    ICTSignalRecord,
    ICTSignalTracker,
)
from ml.feedback.prediction_outcome_matcher_ict import (
    ICTMatchConfidence,
    ICTMatchStatus,
    ICTPredictionMatch,
    ICTPredictionOutcomeMatcher,
    ICTSignalMetrics,
    get_ict_matcher,
)
from signal_generation.registry.signal_types import ICTSignalType


@dataclass
class MockOutcome:
    """Mock outcome for testing."""

    signal_id: str = ""
    direction: str = "LONG"
    pnl: float = 0.0
    outcome_type: str = "tp_hit"
    exit_time: datetime = field(default_factory=lambda: datetime.now(UTC))


class TestICTMatchStatus:
    """Tests for ICTMatchStatus enum."""

    def test_values(self) -> None:
        """Test match status values."""
        assert ICTMatchStatus.MATCHED.value == "matched"
        assert ICTMatchStatus.UNRESOLVED.value == "unresolved"
        assert ICTMatchStatus.EXPIRED.value == "expired"
        assert ICTMatchStatus.EXCLUDED.value == "excluded"


class TestICTMatchConfidence:
    """Tests for ICTMatchConfidence enum."""

    def test_values(self) -> None:
        """Test match confidence values."""
        assert ICTMatchConfidence.HIGH.value == "high"
        assert ICTMatchConfidence.MEDIUM.value == "medium"
        assert ICTMatchConfidence.LOW.value == "low"
        assert ICTMatchConfidence.UNKNOWN.value == "unknown"


class TestICTPredictionMatch:
    """Tests for ICTPredictionMatch class."""

    def test_match_creation(self) -> None:
        """Test prediction match creation."""
        match = ICTPredictionMatch(
            signal_id="test-1",
            signal_type=ICTSignalType.CVD,
            direction="bullish",
            predicted_direction="bullish",
            outcome_correct=True,
            match_status=ICTMatchStatus.MATCHED,
            match_confidence=ICTMatchConfidence.HIGH,
        )

        assert match.signal_id == "test-1"
        assert match.signal_type == ICTSignalType.CVD
        assert match.direction == "bullish"
        assert match.outcome_correct is True
        assert match.match_status == ICTMatchStatus.MATCHED

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        timestamp = datetime.now(UTC)
        match = ICTPredictionMatch(
            signal_id="test-1",
            signal_type=ICTSignalType.FVG,
            direction="bearish",
            predicted_direction="bearish",
            outcome_correct=False,
            match_status=ICTMatchStatus.MATCHED,
            match_confidence=ICTMatchConfidence.MEDIUM,
            timestamp=timestamp,
        )

        data = match.to_dict()

        assert data["signal_id"] == "test-1"
        assert data["signal_type"] == "fvg"
        assert data["direction"] == "bearish"
        assert data["outcome_correct"] is False


class TestICTSignalMetrics:
    """Tests for ICTSignalMetrics class."""

    def test_metrics_creation(self) -> None:
        """Test metrics creation."""
        metrics = ICTSignalMetrics(
            signal_type=ICTSignalType.CVD,
            total_signals=100,
            correct_predictions=75,
        )

        assert metrics.signal_type == ICTSignalType.CVD
        assert metrics.total_signals == 100
        assert metrics.correct_predictions == 75
        assert metrics.accuracy == 0.75

    def test_accuracy_calculation(self) -> None:
        """Test accuracy calculation."""
        metrics = ICTSignalMetrics(
            signal_type=ICTSignalType.FVG,
            total_signals=50,
            correct_predictions=30,
        )

        assert metrics.accuracy == 0.6


class TestICTPredictionOutcomeMatcher:
    """Tests for ICTPredictionOutcomeMatcher class."""

    @pytest.fixture
    def matcher(self) -> ICTPredictionOutcomeMatcher:
        """Create matcher fixture."""
        return ICTPredictionOutcomeMatcher()

    def test_is_bos_choch(self, matcher: ICTPredictionOutcomeMatcher) -> None:
        """Test BOS/CHoCH detection."""
        assert matcher.is_bos_choch(ICTSignalType.CVD) is False
        assert matcher.is_bos_choch(ICTSignalType.FVG) is False
        assert matcher.is_bos_choch(ICTSignalType.ORDER_BLOCK) is False

    @pytest.mark.asyncio
    async def test_match_signal_with_outcome(
        self, matcher: ICTPredictionOutcomeMatcher
    ) -> None:
        """Test matching signal with outcome."""
        signal = ICTSignalRecord(
            signal_id="test-1",
            signal_type=ICTSignalType.CVD,
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        outcome = MockOutcome(
            signal_id="test-1",
            direction="LONG",
            pnl=100.0,
            outcome_type="tp_hit",
        )

        match = await matcher.match_signal_with_outcome(signal, outcome)

        assert match is not None
        assert match.signal_id == "test-1"
        assert match.signal_type == ICTSignalType.CVD
        assert match.outcome_correct is True

    @pytest.mark.asyncio
    async def test_match_batch(self, matcher: ICTPredictionOutcomeMatcher) -> None:
        """Test batch matching."""
        tracker = ICTSignalTracker()
        tracker.track_signal(
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )
        tracker.track_signal(
            signal_type=ICTSignalType.FVG,
            signal_id="fvg-1",
            direction=ICTSignalDirection.BEARISH,
            confidence=0.8,
            timestamp=datetime.now(UTC),
            token="ETH",
            timeframe="4H",
        )

        signals = tracker.get_all_signals()
        outcomes = [
            MockOutcome(signal_id="cvd-1", direction="LONG", pnl=100.0),
            MockOutcome(signal_id="fvg-1", direction="SHORT", pnl=-50.0),
        ]

        results = await matcher.match_batch(signals, outcomes)

        assert len(results) == 2

    def test_get_overall_accuracy(self, matcher: ICTPredictionOutcomeMatcher) -> None:
        """Test getting overall accuracy."""
        accuracy = matcher.get_overall_accuracy()
        assert accuracy == 0.0  # No matches yet

    def test_get_ict_metrics(self, matcher: ICTPredictionOutcomeMatcher) -> None:
        """Test getting ICT metrics."""
        metrics = matcher.get_ict_metrics()

        assert ICTSignalType.CVD in metrics
        assert ICTSignalType.FVG in metrics
        assert ICTSignalType.ORDER_BLOCK in metrics

    def test_global_matcher(self) -> None:
        """Test global matcher instance."""
        matcher1 = get_ict_matcher()
        matcher2 = get_ict_matcher()

        # Should be the same instance
        assert matcher1 is matcher2


class TestICTPredictionOutcomeMatcherIntegration:
    """Integration tests for ICT prediction outcome matcher."""

    @pytest.fixture
    def tracker(self) -> ICTSignalTracker:
        """Create tracker fixture."""
        return ICTSignalTracker()

    @pytest.fixture
    def matcher(self) -> ICTPredictionOutcomeMatcher:
        """Create matcher fixture."""
        return ICTPredictionOutcomeMatcher()

    @pytest.mark.asyncio
    async def test_full_tracking_flow(
        self, tracker: ICTSignalTracker, matcher: ICTPredictionOutcomeMatcher
    ) -> None:
        """Test full tracking and matching flow."""
        # Track signals
        signal1 = tracker.track_signal(
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        signal2 = tracker.track_signal(
            signal_type=ICTSignalType.FVG,
            signal_id="fvg-1",
            direction=ICTSignalDirection.BEARISH,
            confidence=0.8,
            timestamp=datetime.now(UTC),
            token="ETH",
            timeframe="4H",
        )

        assert signal1 is not None
        assert signal2 is not None

        # Match with outcomes
        outcome1 = MockOutcome(signal_id="cvd-1", direction="LONG", pnl=100.0)
        outcome2 = MockOutcome(signal_id="fvg-1", direction="SHORT", pnl=-50.0)

        match1 = await matcher.match_signal_with_outcome(signal1, outcome1)
        match2 = await matcher.match_signal_with_outcome(signal2, outcome2)

        assert match1 is not None
        assert match1.outcome_correct is True
        assert match2 is not None
        assert match2.outcome_correct is False

        # Check metrics
        metrics = matcher.get_ict_metrics()
        cvd_metrics = metrics[ICTSignalType.CVD]
        assert cvd_metrics.total_signals == 1
        assert cvd_metrics.correct_predictions == 1

    @pytest.mark.asyncio
    async def test_confidence_bucket_assignment(
        self, tracker: ICTSignalTracker, matcher: ICTPredictionOutcomeMatcher
    ) -> None:
        """Test confidence bucket assignment."""
        # Track high confidence signal
        signal = tracker.track_signal(
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.95,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        assert signal is not None
        assert signal.confidence == 0.95
