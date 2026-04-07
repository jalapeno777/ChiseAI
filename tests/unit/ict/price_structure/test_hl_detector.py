"""Tests for HLDetector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.ict.price_structure import HLBreakout, HLDetector, HLDetectorConfig

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_candle(
    idx: int,
    timestamp_ms: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1000.0,
) -> MagicMock:
    """Create a mock OHLCVData candle."""
    candle = MagicMock()
    candle.timestamp = timestamp_ms
    candle.open_price = open_price
    candle.high_price = high_price
    candle.low_price = low_price
    candle.close_price = close_price
    candle.volume = volume
    return candle


# ------------------------------------------------------------------
# Test Suite: HLBreakout Dataclass
# ------------------------------------------------------------------


class TestHLBreakout:
    """Tests for HLBreakout dataclass."""

    def test_valid_creation(self) -> None:
        """Test creating a valid HLBreakout."""
        breakout = HLBreakout(
            breakout_type="h",
            price=1.5000,
            direction="long",
            confidence=0.75,
            timestamp=1000000,
            level_price=1.4800,
            penetration_pct=0.1,
        )
        assert breakout.breakout_type == "h"
        assert breakout.price == 1.5000
        assert breakout.direction == "long"
        assert breakout.confidence == 0.75
        assert breakout.timestamp == 1000000

    def test_invalid_breakout_type(self) -> None:
        """Test ValueError for invalid breakout_type."""
        with pytest.raises(ValueError, match="breakout_type must be one of"):
            HLBreakout(
                breakout_type="invalid",
                price=1.5000,
                direction="long",
                confidence=0.75,
                timestamp=1000000,
                level_price=1.4800,
                penetration_pct=0.1,
            )

    def test_invalid_direction(self) -> None:
        """Test ValueError for invalid direction."""
        with pytest.raises(ValueError, match="direction must be 'long' or 'short'"):
            HLBreakout(
                breakout_type="h",
                price=1.5000,
                direction="invalid",
                confidence=0.75,
                timestamp=1000000,
                level_price=1.4800,
                penetration_pct=0.1,
            )

    def test_invalid_confidence_too_high(self) -> None:
        """Test ValueError for confidence > 1.0."""
        with pytest.raises(ValueError, match="confidence must be in \\[0.0, 1.0\\]"):
            HLBreakout(
                breakout_type="h",
                price=1.5000,
                direction="long",
                confidence=1.5,
                timestamp=1000000,
                level_price=1.4800,
                penetration_pct=0.1,
            )

    def test_invalid_confidence_negative(self) -> None:
        """Test ValueError for negative confidence."""
        with pytest.raises(ValueError, match="confidence must be in \\[0.0, 1.0\\]"):
            HLBreakout(
                breakout_type="h",
                price=1.5000,
                direction="long",
                confidence=-0.1,
                timestamp=1000000,
                level_price=1.4800,
                penetration_pct=0.1,
            )

    def test_to_signal_dict(self) -> None:
        """Test conversion to signal dict for ICTSignalEmitter."""
        breakout = HLBreakout(
            breakout_type="high_old",
            price=1.5000,
            direction="long",
            confidence=0.75,
            timestamp=1000000,
            swing_high=1.4900,
            swing_low=1.4500,
            level_price=1.4800,
            penetration_pct=0.1,
        )
        signal_dict = breakout.to_signal_dict()
        assert signal_dict["price"] == 1.5000
        assert signal_dict["direction"] == "long"
        assert signal_dict["confidence"] == 0.75
        assert signal_dict["timestamp"] == 1000000
        assert signal_dict["swing_high"] == 1.4900
        assert signal_dict["swing_low"] == 1.4500


# ------------------------------------------------------------------
# Test Suite: HLDetectorConfig
# ------------------------------------------------------------------


class TestHLDetectorConfig:
    """Tests for HLDetectorConfig."""

    def test_valid_config(self) -> None:
        """Test creating a valid config."""
        config = HLDetectorConfig(lookback=20, break_threshold_pct=0.01)
        assert config.lookback == 20
        assert config.break_threshold_pct == 0.01

    def test_invalid_lookback_too_low(self) -> None:
        """Test ValueError for lookback < 2."""
        with pytest.raises(ValueError, match="lookback must be >= 2"):
            HLDetectorConfig(lookback=1)

    def test_invalid_break_threshold_negative(self) -> None:
        """Test ValueError for negative break_threshold_pct."""
        with pytest.raises(
            ValueError, match="break_threshold_pct must be non-negative"
        ):
            HLDetectorConfig(break_threshold_pct=-0.01)


# ------------------------------------------------------------------
# Test Suite: HLDetector - H Detection
# ------------------------------------------------------------------


class TestHLDetectorH:
    """Tests for H breakout detection."""

    def test_h_breakout_bullish(self) -> None:
        """Test H breakout detected when close closes above previous high."""
        # Previous candle: high at 1.4800, close at 1.4700
        # Current candle: high at 1.4900, close at 1.4850 (above previous high)
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4900, 1.4650, 1.4850),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["h"] is not None
        assert result["h"].breakout_type == "h"
        assert result["h"].direction == "long"
        assert result["h"].price == 1.4850
        assert result["h"].level_price == 1.4800
        assert result["l"] is None

    def test_h_no_breakout_close_below_previous_high(self) -> None:
        """Test no H breakout when close closes below previous high."""
        # Previous candle: high at 1.4800
        # Current candle: close at 1.4750 (below previous high)
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4900, 1.4650, 1.4750),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["h"] is None
        assert result["l"] is None

    def test_h_no_breakout_close_only_wick_above(self) -> None:
        """Test no H breakout when only the wick goes above (close stays below)."""
        # Previous candle: high at 1.4800
        # Current candle: high at 1.4850 (wick only), close at 1.4750
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4850, 1.4650, 1.4750),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        # Close (1.4750) did NOT close above previous high (1.4800)
        assert result["h"] is None

    def test_h_no_breakout_below_threshold(self) -> None:
        """Test no H breakout when penetration is below threshold."""
        # Previous candle: high at 1.4800
        # Current candle: close at 1.4805 (only 0.03% above, below 0.1% threshold)
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4810, 1.4650, 1.4805),
        ]
        detector = HLDetector(break_threshold_pct=0.1)
        result = detector.detect(candles)

        assert result["h"] is None


# ------------------------------------------------------------------
# Test Suite: HLDetector - L Detection
# ------------------------------------------------------------------


class TestHLDetectorL:
    """Tests for L breakout detection."""

    def test_l_breakout_bearish(self) -> None:
        """Test L breakout detected when close closes below previous low."""
        # Previous candle: low at 1.5200, close at 1.5300
        # Current candle: low at 1.5100, close at 1.5150 (below previous low)
        candles = [
            _make_candle(0, 1000, 1.5500, 1.5600, 1.5300, 1.5400),
            _make_candle(1, 2000, 1.5300, 1.5400, 1.5200, 1.5300),
            _make_candle(2, 3000, 1.5250, 1.5350, 1.5100, 1.5150),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["l"] is not None
        assert result["l"].breakout_type == "l"
        assert result["l"].direction == "short"
        assert result["l"].price == 1.5150
        assert result["l"].level_price == 1.5200
        assert result["h"] is None

    def test_l_no_breakout_close_above_previous_low(self) -> None:
        """Test no L breakout when close closes above previous low."""
        # Previous candle: low at 1.5200
        # Current candle: close at 1.5250 (above previous low)
        candles = [
            _make_candle(0, 1000, 1.5500, 1.5600, 1.5300, 1.5400),
            _make_candle(1, 2000, 1.5300, 1.5400, 1.5200, 1.5300),
            _make_candle(2, 3000, 1.5250, 1.5350, 1.5100, 1.5250),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["l"] is None
        assert result["h"] is None


# ------------------------------------------------------------------
# Test Suite: HLDetector - H-OLD Detection
# ------------------------------------------------------------------


class TestHLDetectorHOLD:
    """Tests for H-OLD breakout detection."""

    def test_high_old_breakout_bullish(self) -> None:
        """Test H-OLD breakout detected when close closes above OLD high."""
        # Build 26 candles where the OLD high (candle 15) is 1.5000
        # With lookback=20, lookback_end=25, lookback_start=5
        # So indices 5-24 are in the lookback window; index 15 is valid
        candles = []
        for i in range(25):
            ts = 1000 + i * 60000
            if i == 15:
                # This is the OLD high - within the lookback window
                candles.append(_make_candle(i, ts, 1.4800, 1.5000, 1.4700, 1.4900))
            else:
                candles.append(_make_candle(i, ts, 1.4500, 1.4600, 1.4400, 1.4500))

        # Current candle closes at 1.5050 (above OLD high of 1.5000)
        candles.append(
            _make_candle(25, 1000 + 25 * 60000, 1.4950, 1.5100, 1.4900, 1.5050)
        )

        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["high_old"] is not None
        assert result["high_old"].breakout_type == "high_old"
        assert result["high_old"].direction == "long"
        assert result["high_old"].price == 1.5050
        assert result["high_old"].level_price == 1.5000
        assert result["high_old"].swing_high == 1.5000

    def test_high_old_no_breakout_close_below_old_high(self) -> None:
        """Test no H-OLD breakout when close stays below OLD high."""
        candles = []
        for i in range(25):
            ts = 1000 + i * 60000
            if i == 15:
                candles.append(_make_candle(i, ts, 1.4800, 1.5000, 1.4700, 1.4900))
            else:
                candles.append(_make_candle(i, ts, 1.4500, 1.4600, 1.4400, 1.4500))

        # Current candle closes at 1.4950 (below OLD high of 1.5000)
        candles.append(
            _make_candle(25, 1000 + 25 * 60000, 1.4900, 1.5000, 1.4800, 1.4950)
        )

        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["high_old"] is None


# ------------------------------------------------------------------
# Test Suite: HLDetector - L-OLD Detection
# ------------------------------------------------------------------


class TestHLDetectorLOLD:
    """Tests for L-OLD breakout detection."""

    def test_low_old_breakout_bearish(self) -> None:
        """Test L-OLD breakout detected when close closes below OLD low."""
        # Build 25 candles where the OLD low (candle 5) is 1.5000
        candles = []
        for i in range(25):
            ts = 1000 + i * 60000
            if i == 5:
                # This is the OLD low
                candles.append(_make_candle(i, ts, 1.5100, 1.5200, 1.5000, 1.5100))
            else:
                candles.append(_make_candle(i, ts, 1.5100, 1.5200, 1.5100, 1.5150))

        # Current candle closes at 1.4950 (below OLD low of 1.5000)
        candles.append(
            _make_candle(25, 1000 + 25 * 60000, 1.5050, 1.5100, 1.4900, 1.4950)
        )

        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["low_old"] is not None
        assert result["low_old"].breakout_type == "low_old"
        assert result["low_old"].direction == "short"
        assert result["low_old"].price == 1.4950
        assert result["low_old"].level_price == 1.5000
        assert result["low_old"].swing_low == 1.5000

    def test_low_old_no_breakout_close_above_old_low(self) -> None:
        """Test no L-OLD breakout when close stays above OLD low."""
        candles = []
        for i in range(25):
            ts = 1000 + i * 60000
            if i == 5:
                candles.append(_make_candle(i, ts, 1.5100, 1.5200, 1.5000, 1.5100))
            else:
                candles.append(_make_candle(i, ts, 1.5100, 1.5200, 1.5100, 1.5150))

        # Current candle closes at 1.5050 (above OLD low of 1.5000)
        candles.append(
            _make_candle(25, 1000 + 25 * 60000, 1.5000, 1.5100, 1.4950, 1.5050)
        )

        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["low_old"] is None


# ------------------------------------------------------------------
# Test Suite: Edge Cases
# ------------------------------------------------------------------


class TestHLDetectorEdgeCases:
    """Tests for edge cases."""

    def test_insufficient_data_returns_none(self) -> None:
        """Test with only 1 candle, returns None for all signals."""
        candles = [_make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500)]
        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result == {"h": None, "l": None, "high_old": None, "low_old": None}

    def test_no_lookback_data_for_old_signals(self) -> None:
        """Test that H-OLD/L-OLD signals are None when lookback insufficient."""
        # Only 3 candles - lookback=20 requires at least 22
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4900, 1.4650, 1.4750),
        ]
        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        # H and L can still be detected
        assert result["h"] is None  # close didn't break above
        assert result["l"] is None  # close didn't break below
        # H-OLD/L-OLD need more candles
        assert result["high_old"] is None
        assert result["low_old"] is None

    def test_gap_up_jump_past_old_high(self) -> None:
        """Test breakout detection when price gaps up past OLD high."""
        # OLD high at 1.5000 (candle 5)
        candles = []
        for i in range(22):
            ts = 1000 + i * 60000
            if i == 5:
                candles.append(_make_candle(i, ts, 1.4800, 1.5000, 1.4700, 1.4900))
            else:
                candles.append(_make_candle(i, ts, 1.4500, 1.4600, 1.4400, 1.4500))

        # Current candle opens at 1.4900 and closes at 1.5100 (gap up past OLD high)
        candles.append(
            _make_candle(22, 1000 + 22 * 60000, 1.4900, 1.5150, 1.4850, 1.5100)
        )

        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["high_old"] is not None
        assert result["high_old"].direction == "long"
        assert result["high_old"].price == 1.5100
        assert result["high_old"].level_price == 1.5000

    def test_equal_highs_no_false_break(self) -> None:
        """Test that equal highs don't cause false positives."""
        # Previous high and current high are equal (both 1.4800)
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4800, 1.4650, 1.4750),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["h"] is None
        assert result["l"] is None


# ------------------------------------------------------------------
# Test Suite: Confidence Scoring
# ------------------------------------------------------------------


class TestHLDetectorConfidence:
    """Tests for confidence scoring."""

    def test_confidence_at_minimum_threshold(self) -> None:
        """Test confidence at minimum threshold."""
        # prev_high = 1.4800, close = 1.4813 -> 0.087% penetration (above 0.01% threshold)
        candles = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4820, 1.4650, 1.4813),
        ]
        detector = HLDetector(break_threshold_pct=0.01)
        result = detector.detect(candles)

        assert result["h"] is not None
        # At minimum threshold, confidence should be around 0.60
        assert result["h"].confidence >= 0.60
        assert result["h"].confidence <= 0.80

    def test_confidence_increases_with_penetration(self) -> None:
        """Test that deeper penetration yields higher confidence."""
        # shallow: prev_high = 1.4800, close = 1.4807 -> 0.047% (4.7x threshold)
        # expected: 0.60 + (4.7/10)*0.20 = 0.694 -> ~0.69
        candles_shallow = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4820, 1.4650, 1.4807),
        ]
        # deep: prev_high = 1.4800, close = 1.4815 -> 0.101% (10.1x threshold)
        # expected: 0.60 + (10.1/10)*0.20 = 0.802 -> ~0.80
        candles_deep = [
            _make_candle(0, 1000, 1.4500, 1.4600, 1.4400, 1.4500),
            _make_candle(1, 2000, 1.4700, 1.4800, 1.4600, 1.4700),
            _make_candle(2, 3000, 1.4750, 1.4830, 1.4650, 1.4815),
        ]

        detector = HLDetector(break_threshold_pct=0.01)
        result_shallow = detector.detect(candles_shallow)
        result_deep = detector.detect(candles_deep)

        assert result_shallow["h"] is not None
        assert result_deep["h"] is not None
        assert result_deep["h"].confidence > result_shallow["h"].confidence


# ------------------------------------------------------------------
# Test Suite: Metadata
# ------------------------------------------------------------------


class TestHLDetectorMetadata:
    """Tests for metadata."""

    def test_get_metadata(self) -> None:
        """Test metadata returns correct configuration."""
        detector = HLDetector(lookback=20, break_threshold_pct=0.01)
        metadata = detector.get_metadata()

        assert metadata["name"] == "HLDetector"
        assert (
            metadata["description"]
            == "ICT H/L/H-OLD/L-OLD price structure breakout detector"
        )
        assert metadata["parameters"]["lookback"] == 20
        assert metadata["parameters"]["break_threshold_pct"] == 0.01
