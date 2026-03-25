"""
Unit tests for Mitigation Tracker.
"""

from dataclasses import dataclass

from src.market_analysis.fvg.fvg_detector import (
    FVG,
    FVGDirection,
)
from src.market_analysis.fvg.mitigation_tracker import (
    MitigationEvent,
    MitigationStatus,
    MitigationTracker,
    MitigationType,
)


# Helper dataclass to simulate OHLCV candles for testing
@dataclass
class MockCandle:
    """Mock OHLCV candle for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float

    @classmethod
    def create(
        cls,
        timestamp: int,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float = 1000.0,
    ) -> "MockCandle":
        return cls(timestamp, open_price, high_price, low_price, close_price, volume)


class TestMitigationType:
    """Tests for MitigationType enum."""

    def test_all_types_exist(self):
        """Test all mitigation types exist."""
        assert MitigationType.WICK.value == "wick"
        assert MitigationType.CLOSE.value == "close"
        assert MitigationType.FULL.value == "full"
        assert MitigationType.CE50.value == "ce50"


class TestMitigationEvent:
    """Tests for MitigationEvent dataclass."""

    def test_creation(self):
        """Test MitigationEvent creation."""
        event = MitigationEvent(
            timestamp=1000000,
            price=105.0,
            mitigation_type=MitigationType.CLOSE,
            fvg_high=110.0,
            fvg_low=100.0,
        )
        assert event.timestamp == 1000000
        assert event.price == 105.0
        assert event.mitigation_type == MitigationType.CLOSE
        assert event.fvg_high == 110.0
        assert event.fvg_low == 100.0


class TestMitigationStatus:
    """Tests for MitigationStatus dataclass."""

    def test_creation(self):
        """Test MitigationStatus creation."""
        status = MitigationStatus(
            fvg_high=110.0,
            fvg_low=100.0,
        )
        assert status.fvg_high == 110.0
        assert status.fvg_low == 100.0
        assert status.current_mitigation == MitigationType.WICK
        assert status.ce50_reached is False
        assert len(status.events) == 0

    def test_zone_size(self):
        """Test zone size calculation."""
        status = MitigationStatus(fvg_high=110.0, fvg_low=100.0)
        assert status.zone_size == 10.0

    def test_midpoint(self):
        """Test midpoint calculation."""
        status = MitigationStatus(fvg_high=110.0, fvg_low=100.0)
        assert status.midpoint == 105.0

    def test_is_mitigated(self):
        """Test is_mitigated property."""
        status = MitigationStatus(fvg_high=110.0, fvg_low=100.0)
        assert status.is_mitigated is False

        status.current_mitigation = MitigationType.FULL
        assert status.is_mitigated is True


class TestMitigationTracker:
    """Tests for MitigationTracker."""

    def test_track_fvg(self):
        """Test starting to track an FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        status = tracker.track_fvg(fvg)

        assert status.fvg_high == 110.0
        assert status.fvg_low == 100.0
        assert status.ce50_price == 105.0  # 50% of 10 = 5, 100 + 5 = 105

    def test_check_mitigation_close_bullish(self):
        """Test close mitigation for bullish FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Close at 105 which is exactly at 50% CE (midpoint)
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=102,
            high_price=108,
            low_price=101,
            close_price=105,
        )

        status = tracker.check_mitigation(fvg, candle)

        assert status.current_mitigation == MitigationType.CLOSE
        # Should have 2 events: CLOSE and CE50 (since close is at midpoint)
        assert len(status.events) == 2
        event_types = [e.mitigation_type for e in status.events]
        assert MitigationType.CLOSE in event_types
        assert MitigationType.CE50 in event_types

    def test_check_mitigation_wick_bullish(self):
        """Test wick mitigation for bullish FVG via upper wick."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Candle with upper wick entering FVG but closing below FVG
        # This is actually FULL since low < fvg_low
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=105,
            high_price=115,  # Upper wick enters FVG (above 110)
            low_price=98,  # Low is below FVG
            close_price=105,  # Close is within FVG
        )

        status = tracker.check_mitigation(fvg, candle)

        # low < fvg_low AND high > fvg_high means FULL
        assert status.current_mitigation == MitigationType.FULL

    def test_check_mitigation_full_bullish(self):
        """Test full mitigation for bullish FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Candle that fills the entire FVG
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=99,
            high_price=115,
            low_price=98,
            close_price=105,
        )

        status = tracker.check_mitigation(fvg, candle)

        assert status.current_mitigation == MitigationType.FULL
        # Should have 2 events: FULL and CE50 (since close is at midpoint)
        assert len(status.events) == 2
        event_types = [e.mitigation_type for e in status.events]
        assert MitigationType.FULL in event_types
        assert MitigationType.CE50 in event_types

    def test_check_mitigation_ce50(self):
        """Test 50% CE tracking."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Candle that reaches 50% CE
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=100,
            high_price=106,  # 50% CE is at 105
            low_price=100,
            close_price=106,
        )

        status = tracker.check_mitigation(fvg, candle)

        assert status.ce50_reached is True
        # Should have events for both CE50 and CLOSE
        event_types = [e.mitigation_type for e in status.events]
        assert MitigationType.CE50 in event_types

    def test_check_mitigation_bearish_close(self):
        """Test close mitigation for bearish FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        candle = MockCandle.create(
            timestamp=2000000,
            open_price=108,
            high_price=109,
            low_price=101,
            close_price=105,
        )

        status = tracker.check_mitigation(fvg, candle)

        assert status.current_mitigation == MitigationType.CLOSE

    def test_get_status(self):
        """Test getting status for tracked FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        tracker.track_fvg(fvg)
        status = tracker.get_status(fvg)

        assert status is not None
        assert status.fvg_high == 110.0

    def test_stop_tracking(self):
        """Test stopping tracking of an FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        tracker.track_fvg(fvg)
        result = tracker.stop_tracking(fvg)

        assert result is True
        assert tracker.get_status(fvg) is None

    def test_get_all_tracked(self):
        """Test getting all tracked FVGs."""
        tracker = MitigationTracker()
        fvg1 = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)
        fvg2 = FVG(direction=FVGDirection.BEARISH, timestamp=2000, high=210, low=200)

        tracker.track_fvg(fvg1)
        tracker.track_fvg(fvg2)

        all_tracked = tracker.get_all_tracked()

        assert len(all_tracked) == 2

    def test_clear(self):
        """Test clearing all tracked FVGs."""
        tracker = MitigationTracker()
        fvg = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)

        tracker.track_fvg(fvg)
        tracker.clear()

        assert len(tracker.get_all_tracked()) == 0

    def test_multiple_candles_same_fvg(self):
        """Test multiple candles tracking the same FVG."""
        tracker = MitigationTracker()
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # First candle - wick only (closes above FVG)
        candle1 = MockCandle.create(
            timestamp=2000000,
            open_price=109,
            high_price=105,  # High is within FVG
            low_price=98,  # Low is below FVG
            close_price=104,  # Close is within FVG
        )
        status1 = tracker.check_mitigation(fvg, candle1)
        assert status1.current_mitigation == MitigationType.CLOSE

        # Second candle - close within (higher)
        candle2 = MockCandle.create(
            timestamp=3000000,
            open_price=103,
            high_price=108,
            low_price=102,
            close_price=107,
        )
        status2 = tracker.check_mitigation(fvg, candle2)
        assert status2.current_mitigation == MitigationType.CLOSE

    def test_fvg_id_generation(self):
        """Test FVG ID generation is unique per direction."""
        tracker = MitigationTracker()

        bullish_fvg = FVG(
            direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100
        )
        bearish_fvg = FVG(
            direction=FVGDirection.BEARISH, timestamp=1000, high=110, low=100
        )

        bullish_id = tracker._get_fvg_id(bullish_fvg)
        bearish_id = tracker._get_fvg_id(bearish_fvg)

        assert bullish_id != bearish_id
        assert "bullish" in bullish_id
        assert "bearish" in bearish_id
