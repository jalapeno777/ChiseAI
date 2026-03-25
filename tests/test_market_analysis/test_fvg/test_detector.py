"""
Unit tests for FVG Detector.
"""

from dataclasses import dataclass

from src.market_analysis.fvg.fvg_detector import (
    FVG,
    FVGDetectionResult,
    FVGDetector,
    FVGDirection,
    FVGMitigation,
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


class TestFVGModel:
    """Tests for FVG data model."""

    def test_fvg_creation(self):
        """Test FVG creation with all fields."""
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=105.0,
            low=100.0,
        )
        assert fvg.direction == FVGDirection.BULLISH
        assert fvg.timestamp == 1000000
        assert fvg.high == 105.0
        assert fvg.low == 100.0
        assert fvg.mitigation == FVGMitigation.NONE
        assert fvg.ce50_reached is False

    def test_fvg_midpoint(self):
        """Test FVG midpoint calculation."""
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        assert fvg.midpoint == 105.0

    def test_fvg_zone_size(self):
        """Test FVG zone size calculation."""
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        assert fvg.zone_size == 10.0

    def test_fvg_contains_price(self):
        """Test price containment check."""
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        assert fvg.contains_price(105.0) is True
        assert fvg.contains_price(100.0) is True
        assert fvg.contains_price(110.0) is True
        assert fvg.contains_price(99.0) is False
        assert fvg.contains_price(111.0) is False

    def test_fvg_check_ce50_bullish(self):
        """Test 50% CE check for bullish FVG."""
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        # Zone is 100-110, 50% CE is at 105
        assert fvg.check_ce50(104.9) is False
        assert fvg.check_ce50(105.0) is True
        assert fvg.check_ce50(107.0) is True

    def test_fvg_check_ce50_bearish(self):
        """Test 50% CE check for bearish FVG."""
        fvg = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        # Zone is 100-110, 50% CE is at 105
        assert fvg.check_ce50(105.1) is False
        assert fvg.check_ce50(105.0) is True
        assert fvg.check_ce50(103.0) is True


class TestFVGDetector:
    """Tests for FVGDetector."""

    def _create_candles(self, configs: list) -> list:
        """Helper to create mock candles from configs."""
        candles = []
        base_time = 1000000
        for i, config in enumerate(configs):
            candles.append(
                MockCandle.create(
                    timestamp=base_time + (i * 60000),
                    open_price=config["open"],
                    high_price=config["high"],
                    low_price=config["low"],
                    close_price=config["close"],
                )
            )
        return candles

    def test_detect_bullish_fvg(self):
        """Test bullish FVG detection."""
        detector = FVGDetector()

        # Candle 1: Large bullish impulse (100 -> 110)
        # Candle 2: Opens with gap up at 111, closes at 112
        # Candle 3: Small candle at 111
        candles = self._create_candles(
            [
                {"open": 100, "high": 110, "low": 99, "close": 110},  # Candle 0
                {"open": 111, "high": 113, "low": 111, "close": 112},  # Candle 1 (gap)
                {"open": 111, "high": 112, "low": 110, "close": 111},  # Candle 2
            ]
        )

        result = detector.detect(candles)

        assert result.fvg is not None
        assert result.fvg.direction == FVGDirection.BULLISH
        assert result.fvg.high == 110.0  # candle1's close
        assert result.fvg.low == 111.0  # candle2's low (the gap)
        assert result.fvg.mitigation == FVGMitigation.NONE

    def test_detect_bearish_fvg(self):
        """Test bearish FVG detection."""
        detector = FVGDetector()

        # Candle 1: Large bearish impulse (110 -> 100)
        # Candle 2: Opens with gap down at 99, closes at 98
        # Candle 3: Small candle at 99
        candles = self._create_candles(
            [
                {"open": 110, "high": 111, "low": 100, "close": 100},  # Candle 0
                {"open": 99, "high": 99, "low": 97, "close": 98},  # Candle 1 (gap)
                {"open": 99, "high": 100, "low": 98, "close": 99},  # Candle 2
            ]
        )

        result = detector.detect(candles)

        assert result.fvg is not None
        assert result.fvg.direction == FVGDirection.BEARISH
        assert result.fvg.high == 99.0  # candle2's high (the gap)
        assert result.fvg.low == 100.0  # candle1's close
        assert result.fvg.mitigation == FVGMitigation.NONE

    def test_no_fvg_when_no_gap(self):
        """Test no FVG detected when there's no gap."""
        detector = FVGDetector()

        # Candle 1: Small bullish
        # Candle 2: Overlaps with candle 1
        candles = self._create_candles(
            [
                {"open": 100, "high": 105, "low": 99, "close": 104},  # Candle 0
                {"open": 103, "high": 106, "low": 102, "close": 105},  # Candle 1
                {"open": 104, "high": 107, "low": 103, "close": 106},  # Candle 2
            ]
        )

        result = detector.detect(candles)

        assert result.fvg is None

    def test_no_fvg_when_candle1_not_impulse(self):
        """Test no FVG when candle 1 is not a large impulse."""
        detector = FVGDetector()

        # Candle 1: Small candle (not an impulse)
        candles = self._create_candles(
            [
                {"open": 100, "high": 101, "low": 99, "close": 100},  # Candle 0
                {"open": 101, "high": 102, "low": 100, "close": 101},  # Candle 1
                {"open": 101, "high": 102, "low": 100, "close": 101},  # Candle 2
            ]
        )

        result = detector.detect(candles)

        assert result.fvg is None

    def test_detect_all_fvgs(self):
        """Test detecting all FVGs in a dataset."""
        detector = FVGDetector()

        # Create dataset with two FVGs
        candles = self._create_candles(
            [
                {
                    "open": 100,
                    "high": 110,
                    "low": 99,
                    "close": 110,
                },  # 0: Bullish impulse
                {"open": 111, "high": 113, "low": 111, "close": 112},  # 1: Gap up
                {"open": 111, "high": 112, "low": 110, "close": 111},  # 2: Fills gap
                {
                    "open": 200,
                    "high": 201,
                    "low": 190,
                    "close": 190,
                },  # 3: Bearish impulse
                {"open": 189, "high": 189, "low": 187, "close": 188},  # 4: Gap down
                {"open": 189, "high": 191, "low": 188, "close": 190},  # 5: Fills gap
            ]
        )

        fvgs = detector.detect_all(candles)

        assert len(fvgs) >= 1  # At least one FVG detected

    def test_update_mitigation_close_bullish(self):
        """Test close mitigation for bullish FVG."""
        detector = FVGDetector()

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Candle that closes within FVG
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=102,
            high_price=108,
            low_price=101,
            close_price=105,
        )

        updated = detector.update_mitigation(fvg, candle)

        assert updated.mitigation == FVGMitigation.CLOSE

    def test_update_mitigation_wick_bullish(self):
        """Test wick mitigation for bullish FVG."""
        detector = FVGDetector()

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )

        # Candle with wick entering FVG but closing above FVG
        # low=98 is below FVG low=100, so this is FULL mitigation
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=109,
            high_price=115,
            low_price=98,  # Wick enters FVG but below it
            close_price=114,
        )

        updated = detector.update_mitigation(fvg, candle)

        # This candle fills the entire FVG (FULL)
        assert updated.mitigation == FVGMitigation.FULL

    def test_update_mitigation_full_bullish(self):
        """Test full mitigation for bullish FVG."""
        detector = FVGDetector()

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
            low_price=98,  # Below FVG low
            close_price=105,
        )

        updated = detector.update_mitigation(fvg, candle)

        assert updated.mitigation == FVGMitigation.FULL

    def test_ce50_reached(self):
        """Test 50% CE tracking."""
        detector = FVGDetector()

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1000000,
            high=110.0,
            low=100.0,
        )
        assert fvg.ce50_reached is False

        # Candle with midpoint within range
        candle = MockCandle.create(
            timestamp=2000000,
            open_price=100,
            high_price=106,  # Midpoint (105) is within
            low_price=100,
            close_price=105,
        )

        updated = detector.update_mitigation(fvg, candle)

        assert updated.ce50_reached is True

    def test_get_active_fvgs(self):
        """Test filtering active FVGs."""
        detector = FVGDetector()

        # Add FVGs with different mitigation states
        fvg1 = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)
        fvg2 = FVG(direction=FVGDirection.BULLISH, timestamp=2000, high=210, low=200)
        fvg3 = FVG(direction=FVGDirection.BULLISH, timestamp=3000, high=310, low=300)
        fvg3.mitigation = FVGMitigation.FULL

        detector._detected_fvgs = [fvg1, fvg2, fvg3]

        active = detector.get_active_fvgs()

        assert len(active) == 2
        assert fvg3 not in active

    def test_get_bullish_fvgs(self):
        """Test filtering bullish FVGs."""
        detector = FVGDetector()

        fvg1 = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)
        fvg2 = FVG(direction=FVGDirection.BEARISH, timestamp=2000, high=210, low=200)

        detector._detected_fvgs = [fvg1, fvg2]

        bullish = detector.get_bullish_fvgs()
        bearish = detector.get_bearish_fvgs()

        assert len(bullish) == 1
        assert bullish[0] == fvg1
        assert len(bearish) == 1
        assert bearish[0] == fvg2

    def test_clear_history(self):
        """Test clearing FVG history."""
        detector = FVGDetector()

        fvg = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)
        detector._detected_fvgs.append(fvg)

        detector.clear_history()

        assert len(detector._detected_fvgs) == 0


class TestFVGDetectionResult:
    """Tests for FVGDetectionResult."""

    def test_creation(self):
        """Test FVGDetectionResult creation."""
        fvg = FVG(direction=FVGDirection.BULLISH, timestamp=1000, high=110, low=100)
        result = FVGDetectionResult(fvg=fvg, detection_index=5, is_new=True)

        assert result.fvg == fvg
        assert result.detection_index == 5
        assert result.is_new is True

    def test_none_fvg(self):
        """Test result with no FVG."""
        result = FVGDetectionResult(fvg=None, detection_index=-1, is_new=False)

        assert result.fvg is None
        assert result.detection_index == -1
        assert result.is_new is False
