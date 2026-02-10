"""Tests for signal tracker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_analysis.signal_history.tracker import SignalTracker
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)


@pytest.fixture
def mock_storage():
    """Create a mock storage backend."""
    storage = MagicMock()
    storage.store_signal = AsyncMock(return_value=True)
    storage.store_outcome = AsyncMock(return_value=True)
    storage.query_signals = AsyncMock(return_value=[])
    storage.query_signals_with_outcomes = AsyncMock(return_value=[])
    storage.get_signal_by_id = AsyncMock(return_value=None)
    storage.get_outcome_by_signal_id = AsyncMock(return_value=None)
    storage.get_unresolved_signals = AsyncMock(return_value=[])
    storage.close = AsyncMock()
    return storage


@pytest.fixture
def tracker(mock_storage):
    """Create a SignalTracker with mock storage."""
    return SignalTracker(storage=mock_storage, outcome_matching_window_hours=24.0)


class TestSignalTrackerStoreSignal:
    """Tests for store_signal method."""

    @pytest.mark.asyncio
    async def test_store_signal_basic(self, tracker, mock_storage):
        """Test storing a basic signal."""
        signal = await tracker.store_signal(
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi", "macd"],
            timeframes_used=["1h", "4h"],
        )

        assert signal.token == "BTC"
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == 0.75
        assert signal.signal_id is not None
        mock_storage.store_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_signal_with_custom_id(self, tracker, mock_storage):
        """Test storing a signal with custom ID."""
        custom_id = "custom-uuid-123"
        signal = await tracker.store_signal(
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi"],
            timeframes_used=["1h"],
            signal_id=custom_id,
        )

        assert signal.signal_id == custom_id

    @pytest.mark.asyncio
    async def test_store_signal_with_metadata(self, tracker, mock_storage):
        """Test storing a signal with metadata."""
        metadata = {"source": "test", "version": "1.0"}
        signal = await tracker.store_signal(
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi"],
            timeframes_used=["1h"],
            metadata=metadata,
        )

        assert signal.metadata == metadata


class TestSignalTrackerRecordOutcome:
    """Tests for record_outcome method."""

    @pytest.mark.asyncio
    async def test_record_outcome_basic(self, tracker, mock_storage):
        """Test recording a basic outcome."""
        outcome = await tracker.record_outcome(
            signal_id="test-signal-123",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.5,
            outcome_type=OutcomeType.TP_HIT,
            note="Take profit hit",
        )

        assert outcome.signal_id == "test-signal-123"
        assert outcome.is_win is True
        assert outcome.pnl == 100.0
        assert outcome.outcome_type == OutcomeType.TP_HIT
        mock_storage.store_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_outcome_loss(self, tracker, mock_storage):
        """Test recording a loss outcome."""
        outcome = await tracker.record_outcome(
            signal_id="test-signal-123",
            exit_timestamp=1234567950000,
            is_win=False,
            pnl=-50.0,
            exit_price=49950.0,
            duration_hours=2.0,
            outcome_type=OutcomeType.SL_HIT,
        )

        assert outcome.is_win is False
        assert outcome.pnl == -50.0
        assert outcome.outcome_type == OutcomeType.SL_HIT


class TestSignalTrackerGetSignalHistory:
    """Tests for get_signal_history method."""

    @pytest.mark.asyncio
    async def test_get_signal_history_with_outcomes(self, tracker, mock_storage):
        """Test getting signal history with outcomes."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.0,
        )
        mock_storage.query_signals_with_outcomes.return_value = [
            SignalWithOutcome(signal=signal, outcome=outcome)
        ]

        results = await tracker.get_signal_history(token="BTC", include_outcomes=True)

        assert len(results) == 1
        assert results[0].signal.token == "BTC"
        assert results[0].outcome.is_win is True

    @pytest.mark.asyncio
    async def test_get_signal_history_without_outcomes(self, tracker, mock_storage):
        """Test getting signal history without outcomes."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )
        mock_storage.query_signals.return_value = [signal]

        results = await tracker.get_signal_history(token="BTC", include_outcomes=False)

        assert len(results) == 1
        assert results[0].signal.token == "BTC"
        assert results[0].outcome is None

    @pytest.mark.asyncio
    async def test_get_signal_history_with_filters(self, tracker, mock_storage):
        """Test getting signal history with filters."""
        await tracker.get_signal_history(
            token="BTC",
            direction="LONG",
            start_time=1234567800000,
            end_time=1234567900000,
            indicators=["rsi"],
            timeframes=["1h"],
            min_confidence=0.5,
            max_confidence=0.9,
            limit=50,
        )

        mock_storage.query_signals_with_outcomes.assert_called_once()
        call_kwargs = mock_storage.query_signals_with_outcomes.call_args.kwargs
        assert call_kwargs["token"] == "BTC"
        assert call_kwargs["direction"] == "LONG"
        assert call_kwargs["min_confidence"] == 0.5


class TestSignalTrackerGetUnresolvedSignals:
    """Tests for get_unresolved_signals method."""

    @pytest.mark.asyncio
    async def test_get_unresolved_signals(self, tracker, mock_storage):
        """Test getting unresolved signals."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )
        mock_storage.get_unresolved_signals.return_value = [signal]

        results = await tracker.get_unresolved_signals(
            before_timestamp=1234567900000, token="BTC", limit=10
        )

        assert len(results) == 1
        assert results[0].signal_id == "test-1"
        mock_storage.get_unresolved_signals.assert_called_once()


class TestSignalTrackerFindSignalsNeedingOutcomes:
    """Tests for find_signals_needing_outcomes method."""

    @pytest.mark.asyncio
    async def test_find_signals_needing_outcomes(self, tracker, mock_storage):
        """Test finding signals that need outcomes."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )
        mock_storage.get_unresolved_signals.return_value = [signal]

        with patch("time.time", return_value=1234567890.0 + 86400):  # 24 hours later
            results = await tracker.find_signals_needing_outcomes(token="BTC")

        assert len(results) == 1


class TestSignalTrackerContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_storage):
        """Test async context manager."""
        tracker = SignalTracker(storage=mock_storage)

        async with tracker as t:
            assert t is tracker

        mock_storage.close.assert_called_once()
