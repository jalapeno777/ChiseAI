"""Tests for ICT signal tracker module."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ml.feedback.ict_signal_tracker import (
    ICTSignalDirection,
    ICTSignalRecord,
    ICTSignalTracker,
    get_ict_tracker,
)
from signal_generation.registry.signal_types import ICTSignalType


class TestICTSignalDirection:
    """Tests for ICTSignalDirection enum."""

    def test_bullish_value(self) -> None:
        """Test bullish direction value."""
        assert ICTSignalDirection.BULLISH.value == "bullish"

    def test_bearish_value(self) -> None:
        """Test bearish direction value."""
        assert ICTSignalDirection.BEARISH.value == "bearish"

    def test_neutral_value(self) -> None:
        """Test neutral direction value."""
        assert ICTSignalDirection.NEUTRAL.value == "neutral"


class TestICTSignalRecord:
    """Tests for ICTSignalRecord class."""

    def test_record_creation(self) -> None:
        """Test ICT signal record creation."""
        record = ICTSignalRecord(
            signal_id="test-1",
            signal_type=ICTSignalType.CVD,
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        assert record.signal_id == "test-1"
        assert record.signal_type == ICTSignalType.CVD
        assert record.direction == ICTSignalDirection.BULLISH
        assert record.confidence == 0.75
        assert record.token == "BTC"
        assert record.timeframe == "1H"
        assert record.tracked is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        timestamp = datetime.now(UTC)
        record = ICTSignalRecord(
            signal_id="test-1",
            signal_type=ICTSignalType.FVG,
            direction=ICTSignalDirection.BEARISH,
            confidence=0.8,
            timestamp=timestamp,
            token="ETH",
            timeframe="4H",
            entry_price=2500.0,
        )

        data = record.to_dict()

        assert data["signal_id"] == "test-1"
        assert data["signal_type"] == "fvg"
        assert data["direction"] == "bearish"
        assert data["confidence"] == 0.8
        assert data["token"] == "ETH"
        assert data["timeframe"] == "4H"
        assert data["entry_price"] == 2500.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "signal_id": "test-2",
            "signal_type": "order_block",
            "direction": "bullish",
            "confidence": 0.7,
            "timestamp": datetime.now(UTC).isoformat(),
            "token": "BTC",
            "timeframe": "1H",
            "tracked": False,
        }

        record = ICTSignalRecord.from_dict(data)

        assert record.signal_id == "test-2"
        assert record.signal_type == ICTSignalType.ORDER_BLOCK
        assert record.direction == ICTSignalDirection.BULLISH
        assert record.confidence == 0.7


class TestICTSignalTracker:
    """Tests for ICTSignalTracker class."""

    @pytest.fixture
    def tracker(self) -> ICTSignalTracker:
        """Create tracker fixture."""
        return ICTSignalTracker()

    def test_is_bos_choch(self, tracker: ICTSignalTracker) -> None:
        """Test BOS/CHoCH detection."""
        assert tracker.is_bos_choch(ICTSignalType.CVD) is False
        assert tracker.is_bos_choch(ICTSignalType.FVG) is False
        assert tracker.is_bos_choch(ICTSignalType.ORDER_BLOCK) is False

    def test_track_cvd_signal(self, tracker: ICTSignalTracker) -> None:
        """Test tracking CVD signal."""
        record = tracker.track_signal(
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        assert record is not None
        assert record.signal_id == "cvd-1"
        assert record.signal_type == ICTSignalType.CVD

    def test_track_fvg_signal(self, tracker: ICTSignalTracker) -> None:
        """Test tracking FVG signal."""
        record = tracker.track_signal(
            signal_type=ICTSignalType.FVG,
            signal_id="fvg-1",
            direction=ICTSignalDirection.BEARISH,
            confidence=0.8,
            timestamp=datetime.now(UTC),
            token="ETH",
            timeframe="4H",
        )

        assert record is not None
        assert record.signal_id == "fvg-1"
        assert record.signal_type == ICTSignalType.FVG

    def test_track_order_block_signal(self, tracker: ICTSignalTracker) -> None:
        """Test tracking Order Block signal."""
        record = tracker.track_signal(
            signal_type=ICTSignalType.ORDER_BLOCK,
            signal_id="ob-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.7,
            timestamp=datetime.now(UTC),
            token="SOL",
            timeframe="1H",
        )

        assert record is not None
        assert record.signal_id == "ob-1"
        assert record.signal_type == ICTSignalType.ORDER_BLOCK

    def test_bos_choch_included(self, tracker: ICTSignalTracker) -> None:
        """Test that BOS/CHoCH signals are now included (re-enabled)."""
        # BOS_CHOCH is now re-enabled in the enum
        valid_types = tracker.VALID_SIGNAL_TYPES
        assert ICTSignalType.CVD in valid_types
        assert ICTSignalType.FVG in valid_types
        assert ICTSignalType.ORDER_BLOCK in valid_types
        # BOS_CHOCH is now included
        assert ICTSignalType.BOS_CHOCH in valid_types

    def test_get_signals_by_type(self, tracker: ICTSignalTracker) -> None:
        """Test getting signals by type."""
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
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-2",
            direction=ICTSignalDirection.BEARISH,
            confidence=0.8,
            timestamp=datetime.now(UTC),
            token="ETH",
            timeframe="4H",
        )
        tracker.track_signal(
            signal_type=ICTSignalType.FVG,
            signal_id="fvg-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.7,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        cvd_signals = tracker.get_signals_by_type(ICTSignalType.CVD)
        assert len(cvd_signals) == 2

        fvg_signals = tracker.get_signals_by_type(ICTSignalType.FVG)
        assert len(fvg_signals) == 1

    def test_get_signals_by_token(self, tracker: ICTSignalTracker) -> None:
        """Test getting signals by token."""
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
            token="BTC",
            timeframe="4H",
        )
        tracker.track_signal(
            signal_type=ICTSignalType.ORDER_BLOCK,
            signal_id="ob-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.7,
            timestamp=datetime.now(UTC),
            token="ETH",
            timeframe="1H",
        )

        btc_signals = tracker.get_signals_by_token("BTC")
        assert len(btc_signals) == 2

        eth_signals = tracker.get_signals_by_token("ETH")
        assert len(eth_signals) == 1

    def test_mark_tracked(self, tracker: ICTSignalTracker) -> None:
        """Test marking signals as tracked."""
        tracker.track_signal(
            signal_type=ICTSignalType.CVD,
            signal_id="cvd-1",
            direction=ICTSignalDirection.BULLISH,
            confidence=0.75,
            timestamp=datetime.now(UTC),
            token="BTC",
            timeframe="1H",
        )

        untracked = tracker.get_untracked_signals()
        assert len(untracked) == 1

        tracker.mark_tracked("cvd-1")

        untracked = tracker.get_untracked_signals()
        assert len(untracked) == 0

    def test_get_signal_counts(self, tracker: ICTSignalTracker) -> None:
        """Test getting signal counts."""
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

        counts = tracker.get_signal_counts()
        assert counts["cvd"] == 1
        assert counts["fvg"] == 1
        assert counts["order_block"] == 0

    def test_global_tracker(self) -> None:
        """Test global tracker instance."""
        tracker1 = get_ict_tracker()
        tracker2 = get_ict_tracker()

        # Should be the same instance
        assert tracker1 is tracker2
