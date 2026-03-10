"""Tests for prediction-outcome matcher module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "src")

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)
from ml.feedback.matcher import (
    MatchBatchResult,
    MatchConfidence,
    MatchConfig,
    MatchStatus,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
)


class TestMatchConfig:
    """Tests for MatchConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MatchConfig()

        assert config.matching_window_hours == 24.0
        assert config.min_confidence_threshold == 0.5
        assert config.allow_multiple_outcomes is False
        assert config.token_specific_windows == {}
        assert config.signal_type_windows == {}

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = MatchConfig(
            matching_window_hours=48.0,
            min_confidence_threshold=0.7,
            allow_multiple_outcomes=True,
        )

        assert config.matching_window_hours == 48.0
        assert config.min_confidence_threshold == 0.7
        assert config.allow_multiple_outcomes is True

    def test_get_window_for_signal_default(self) -> None:
        """Test getting default window for signal."""
        config = MatchConfig(matching_window_hours=24.0)
        signal = SignalRecord(
            signal_id="test-123",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        window = config.get_window_for_signal(signal)
        assert window == 24.0

    def test_get_window_for_signal_token_specific(self) -> None:
        """Test getting token-specific window."""
        config = MatchConfig(
            matching_window_hours=24.0,
            token_specific_windows={"BTC": 48.0, "ETH": 12.0},
        )
        signal = SignalRecord(
            signal_id="test-123",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        window = config.get_window_for_signal(signal)
        assert window == 48.0


class TestPredictionOutcomeMatch:
    """Tests for PredictionOutcomeMatch class."""

    def test_match_creation(self) -> None:
        """Test match creation."""
        signal = SignalRecord(
            signal_id="test-123",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-123",
            signal=signal,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
        )

        assert match.signal_id == "test-123"
        assert match.status == MatchStatus.MATCHED
        assert match.confidence == MatchConfidence.HIGH

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        signal = SignalRecord(
            signal_id="test-123",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

        match = PredictionOutcomeMatch(
            signal_id="test-123",
            signal=signal,
            status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            match_time_ms=2000000,
            match_latency_hours=12.0,
            resolution_quality=0.95,
        )

        data = match.to_dict()

        assert data["signal_id"] == "test-123"
        assert data["status"] == "matched"
        assert data["confidence"] == "high"
        assert data["match_latency_hours"] == 12.0
        assert data["resolution_quality"] == 0.95


class TestMatchBatchResult:
    """Tests for MatchBatchResult class."""

    def test_batch_result_creation(self) -> None:
        """Test batch result creation."""
        result = MatchBatchResult(
            total_signals=100,
            matched=80,
            unresolved=10,
            expired=5,
            ambiguous=5,
        )

        assert result.total_signals == 100
        assert result.matched == 80
        assert result.unresolved == 10
        assert result.expired == 5
        assert result.ambiguous == 5

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = MatchBatchResult(
            total_signals=100,
            matched=80,
            batch_time_ms=3000000,
        )

        data = result.to_dict()

        assert data["total_signals"] == 100
        assert data["matched"] == 80
        assert data["batch_time_ms"] == 3000000


class TestPredictionOutcomeMatcher:
    """Tests for PredictionOutcomeMatcher class."""

    @pytest.fixture
    def matcher(self) -> PredictionOutcomeMatcher:
        """Create matcher fixture."""
        return PredictionOutcomeMatcher()

    @pytest.fixture
    def sample_signal(self) -> SignalRecord:
        """Create sample signal fixture."""
        return SignalRecord(
            signal_id="test-123",
            token="BTC",
            timestamp=1000000,
            direction=SignalDirection.LONG,
            confidence=0.8,
            entry_price=50000.0,
            score=75.0,
        )

    @pytest.fixture
    def sample_outcome(self) -> OutcomeRecord:
        """Create sample outcome fixture."""
        return OutcomeRecord(
            signal_id="test-123",
            exit_timestamp=1100000,  # 100 seconds later
            is_win=True,
            pnl=100.0,
            exit_price=51000.0,
            duration_hours=0.028,  # ~100 seconds
            outcome_type=OutcomeType.TP_HIT,
        )

    @pytest.mark.asyncio
    async def test_match_single_unresolved(self, matcher, sample_signal) -> None:
        """Test matching signal with no outcome yet."""
        current_time = sample_signal.timestamp + 1000  # Within window

        match = await matcher.match_single(
            signal=sample_signal,
            outcomes=[],
            current_time_ms=current_time,
        )

        assert match.status == MatchStatus.UNRESOLVED
        assert match.confidence == MatchConfidence.UNKNOWN

    @pytest.mark.asyncio
    async def test_match_single_matched(
        self, matcher, sample_signal, sample_outcome
    ) -> None:
        """Test successful match."""
        # Set current_time past the 24-hour window to allow matching
        current_time = sample_signal.timestamp + int(
            25 * 3600 * 1000
        )  # 25 hours after signal

        match = await matcher.match_single(
            signal=sample_signal,
            outcomes=[sample_outcome],
            current_time_ms=current_time,
        )

        assert match.status == MatchStatus.MATCHED
        assert match.confidence == MatchConfidence.HIGH
        assert match.outcome == sample_outcome

    @pytest.mark.asyncio
    async def test_match_single_expired(self, matcher, sample_signal) -> None:
        """Test expired signal with no outcome."""
        current_time = sample_signal.timestamp + 100000000  # Way past window

        match = await matcher.match_single(
            signal=sample_signal,
            outcomes=[],
            current_time_ms=current_time,
        )

        assert match.status == MatchStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_match_batch(self, matcher) -> None:
        """Test batch matching."""
        signals = [
            SignalRecord(
                signal_id=f"test-{i}",
                token="BTC",
                timestamp=1000000,
                direction=SignalDirection.LONG,
                confidence=0.8,
                entry_price=50000.0,
                score=75.0,
            )
            for i in range(5)
        ]

        outcomes = {
            "test-0": [
                OutcomeRecord(
                    signal_id="test-0",
                    exit_timestamp=1100000,
                    is_win=True,
                    pnl=100.0,
                    exit_price=51000.0,
                    duration_hours=0.028,
                    outcome_type=OutcomeType.TP_HIT,
                )
            ],
        }

        # Set current_time past the 24-hour window to allow matching
        current_time = 1000000 + int(25 * 3600 * 1000)  # 25 hours after signal

        result = await matcher.match_batch(
            signals=signals,
            outcomes=outcomes,
            current_time_ms=current_time,
        )

        assert result.total_signals == 5
        assert result.matched == 1
        assert result.expired == 4  # Past window with no outcome

    def test_calculate_resolution_quality_high(
        self, matcher, sample_signal, sample_outcome
    ) -> None:
        """Test high resolution quality calculation."""
        quality = matcher._calculate_resolution_quality(
            signal=sample_signal,
            outcome=sample_outcome,
            latency_hours=2.0,
            window_hours=24.0,
        )

        assert quality > 0.8  # Should be high for early TP hit

    def test_calculate_resolution_quality_with_latency(
        self, matcher, sample_signal, sample_outcome
    ) -> None:
        """Test resolution quality with moderate latency."""
        quality = matcher._calculate_resolution_quality(
            signal=sample_signal,
            outcome=sample_outcome,
            latency_hours=20.0,  # 83% of window used
            window_hours=24.0,
        )

        # Quality is reduced for latency but boosted for TP_HIT win
        # 0.85 * 1.1 = 0.935 for 20/24 = 0.83 time ratio
        assert quality > 0.8  # TP_HIT boost keeps quality high

    def test_get_match_history(self, matcher, sample_signal) -> None:
        """Test getting match history."""
        match = PredictionOutcomeMatch(
            signal_id="test-123",
            signal=sample_signal,
            status=MatchStatus.MATCHED,
        )
        matcher._match_history.append(match)

        history = matcher.get_match_history()

        assert len(history) == 1
        assert history[0].signal_id == "test-123"

    def test_get_match_history_filtered(self, matcher, sample_signal) -> None:
        """Test getting filtered match history."""
        matcher._match_history = [
            PredictionOutcomeMatch(
                signal_id="test-1",
                signal=sample_signal,
                status=MatchStatus.MATCHED,
            ),
            PredictionOutcomeMatch(
                signal_id="test-2",
                signal=sample_signal,
                status=MatchStatus.EXPIRED,
            ),
        ]

        history = matcher.get_match_history(status=MatchStatus.MATCHED)

        assert len(history) == 1
        assert history[0].signal_id == "test-1"

    def test_clear_history(self, matcher) -> None:
        """Test clearing match history."""
        match = PredictionOutcomeMatch(
            signal_id="test-123",
            signal=MagicMock(),
            status=MatchStatus.MATCHED,
        )
        matcher._match_history.append(match)

        matcher.clear_history()

        assert len(matcher._match_history) == 0


class TestMatcherHealth:
    """Tests for matcher health status."""

    @pytest.fixture
    def matcher(self) -> PredictionOutcomeMatcher:
        """Create matcher fixture."""
        return PredictionOutcomeMatcher()

    def test_get_health_status_no_matches(self, matcher) -> None:
        """Test health status with no matches."""
        health = matcher.get_health_status()

        assert health["component"] == "PredictionOutcomeMatcher"
        assert health["is_active"] is False
        assert health["total_matches"] == 0
        assert health["match_rate"] == 0.0
        assert health["is_healthy"] is False
        assert "No matches recorded" in health["reason"]
        assert health["last_match_time"] is None

    def test_get_health_status_with_matches(self, matcher) -> None:
        """Test health status with matches."""
        from datetime import UTC, datetime

        # Add some matches
        matcher._match_history = [
            PredictionOutcomeMatch(
                signal_id=f"test-{i}",
                signal=MagicMock(),
                status=MatchStatus.MATCHED,
            )
            for i in range(10)
        ]
        matcher._total_matches_processed = 10
        matcher._last_match_timestamp = datetime.now(UTC)

        health = matcher.get_health_status()

        assert health["is_active"] is True
        assert health["total_matches"] == 10
        assert health["match_rate"] == 1.0
        assert health["is_healthy"] is True
        assert "Last match" in health["reason"]
        assert "10 total matches processed" in health["reason"]

    def test_get_health_status_partial_match_rate(self, matcher) -> None:
        """Test health status with partial match rate."""
        from datetime import UTC, datetime

        # Add mixed matches
        matcher._match_history = [
            PredictionOutcomeMatch(
                signal_id=f"matched-{i}",
                signal=MagicMock(),
                status=MatchStatus.MATCHED,
            )
            for i in range(7)
        ]
        matcher._match_history.extend(
            [
                PredictionOutcomeMatch(
                    signal_id=f"expired-{i}",
                    signal=MagicMock(),
                    status=MatchStatus.EXPIRED,
                )
                for i in range(3)
            ]
        )
        matcher._total_matches_processed = 10
        matcher._last_match_timestamp = datetime.now(UTC)

        health = matcher.get_health_status()

        assert health["match_rate"] == 0.7
        assert "Match rate: 70.0%" in health["reason"]
