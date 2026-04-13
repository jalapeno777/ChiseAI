"""Unit tests for BOSCHoCHClassifier._check_bullish_break and _check_bearish_break.

Tests the fix where swing.price (pivot price) was incorrectly used instead of
data[swing.index].close_price (candle close) for:
  - Strength calculation
  - BOSCHoCH event break_price

These methods are currently dead code (called only from classify() which has
its own inline logic), but the fix ensures correctness if they are ever wired up.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, "src")

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.structure.bos_choch import (
    BOSCHoCHClassifier,
    BOSCHoCHType,
)
from market_analysis.structure.swing_pivot import PivotType, SwingPivot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(
    index: int,
    open_p: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000.0,
    ts_ms: int = 1000000,
) -> OHLCVData:
    """Create an OHLCVData candle."""
    return OHLCVData(
        timestamp=ts_ms + index * 60000,
        open_price=open_p,
        high_price=high,
        low_price=low,
        close_price=close,
        volume=volume,
    )


def _make_swing(
    index: int,
    pivot_type: PivotType,
    price: float,
    ts: datetime | None = None,
) -> SwingPivot:
    """Create a SwingPivot."""
    return SwingPivot(
        index=index,
        timestamp=ts or datetime(2025, 1, 1, tzinfo=UTC),
        pivot_type=pivot_type,
        price=price,
        strength=1.0,
    )


def _make_classifier(min_strength_ratio: float = 0.0) -> BOSCHoCHClassifier:
    """Create a classifier with configurable min_strength_ratio."""
    return BOSCHoCHClassifier(min_strength_ratio=min_strength_ratio)


# ---------------------------------------------------------------------------
# Bullish break tests
# ---------------------------------------------------------------------------


class TestCheckBullishBreak:
    """Tests for _check_bullish_break method."""

    def test_bullish_bos_uses_close_price_not_swing_price(self) -> None:
        """BOS event break_price must be data[swing.index].close_price, not swing.price.

        Setup: swing_high with pivot price (high) = 110 but close = 105.
        Previous swing_high at price 100. The break_price in the BOS event
        must be 105 (close), NOT 110 (swing.price).
        """
        cls = _make_classifier(min_strength_ratio=0.0)

        # 10 candles: indices 0-9
        data = [_make_candle(i, 90, 95 + i, 85, 90 + i) for i in range(10)]
        # Index 9: high=104, close=99
        # Override to make swing_high have high=110 but close=105
        data[9] = _make_candle(9, 100, 110, 99, 105)

        # Current swing: swing_high at index 9, price=110 (the pivot/high)
        swing = _make_swing(9, PivotType.SWING_HIGH, 110)

        # Previous swing_high at index 4, price=100
        prev_sh = _make_swing(4, PivotType.SWING_HIGH, 100)

        result = cls._check_bullish_break(swing, [prev_sh], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is True
        assert event.event_type == BOSCHoCHType.BULLISH_BOS
        # CRITICAL: break_price must be close_price (105), not swing.price (110)
        assert (
            event.break_price == 105.0
        ), f"Expected break_price=105.0 (close_price), got {event.break_price}"

    def test_bullish_choch_uses_close_price_not_swing_price(self) -> None:
        """CHoCH event break_price must be data[swing.index].close_price.

        Setup: swing_high breaks a previous swing_low (CHoCH pattern).
        swing.price=110 but close=107. break_price must be 107.
        """
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 90, 95 + i, 85, 90 + i) for i in range(10)]
        data[9] = _make_candle(9, 100, 110, 99, 107)

        swing = _make_swing(9, PivotType.SWING_HIGH, 110)
        prev_sl = _make_swing(3, PivotType.SWING_LOW, 95)

        result = cls._check_bullish_break(swing, [prev_sl], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is False
        assert event.event_type == BOSCHoCHType.BULLISH_CHOCH
        assert (
            event.break_price == 107.0
        ), f"Expected break_price=107.0 (close_price), got {event.break_price}"

    def test_bullish_bos_priority_over_choch(self) -> None:
        """BOS takes priority over CHoCH when both candidates exist."""
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 90, 95 + i, 85, 90 + i) for i in range(10)]
        data[9] = _make_candle(9, 100, 115, 99, 112)

        swing = _make_swing(9, PivotType.SWING_HIGH, 115)
        prev_sh = _make_swing(4, PivotType.SWING_HIGH, 100)
        prev_sl = _make_swing(2, PivotType.SWING_LOW, 88)

        result = cls._check_bullish_break(swing, [prev_sl, prev_sh], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is True, "BOS should take priority over CHoCH"
        assert event.event_type == BOSCHoCHType.BULLISH_BOS

    def test_bullish_no_break_when_close_below_level(self) -> None:
        """No break when close_price does not exceed the level."""
        cls = _make_classifier(min_strength_ratio=0.0)

        # Close at 99 < swing_high level 100 → no break
        data = [_make_candle(i, 90, 95 + i, 85, 90 + i) for i in range(10)]
        data[9] = _make_candle(9, 98, 105, 97, 99)

        swing = _make_swing(9, PivotType.SWING_HIGH, 105)
        prev_sh = _make_swing(4, PivotType.SWING_HIGH, 100)

        result = cls._check_bullish_break(swing, [prev_sh], data)
        assert result is None


# ---------------------------------------------------------------------------
# Bearish break tests
# ---------------------------------------------------------------------------


class TestCheckBearishBreak:
    """Tests for _check_bearish_break method."""

    def test_bearish_bos_uses_close_price_not_swing_price(self) -> None:
        """BOS event break_price must be data[swing.index].close_price, not swing.price.

        Setup: swing_low with pivot price (low) = 90 but close = 95.
        Previous swing_low at price 100. The break_price must be 95 (close), NOT 90 (swing.price).
        """
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 100, 110, 100 - i, 105 - i) for i in range(10)]
        # Index 9: low=91, close=95 (close is higher than the pivot low)
        data[9] = _make_candle(9, 98, 105, 90, 95)

        swing = _make_swing(9, PivotType.SWING_LOW, 90)
        prev_sl = _make_swing(4, PivotType.SWING_LOW, 100)

        result = cls._check_bearish_break(swing, [prev_sl], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is True
        assert event.event_type == BOSCHoCHType.BEARISH_BOS
        # CRITICAL: break_price must be close_price (95), not swing.price (90)
        assert (
            event.break_price == 95.0
        ), f"Expected break_price=95.0 (close_price), got {event.break_price}"

    def test_bearish_choch_uses_close_price_not_swing_price(self) -> None:
        """CHoCH event break_price must be data[swing.index].close_price.

        Setup: swing_low breaks a previous swing_high (CHoCH pattern).
        swing.price=90 but close=93. break_price must be 93.
        """
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 100, 110, 100 - i, 105 - i) for i in range(10)]
        data[9] = _make_candle(9, 98, 105, 90, 93)

        swing = _make_swing(9, PivotType.SWING_LOW, 90)
        prev_sh = _make_swing(3, PivotType.SWING_HIGH, 105)

        result = cls._check_bearish_break(swing, [prev_sh], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is False
        assert event.event_type == BOSCHoCHType.BEARISH_CHOCH
        assert (
            event.break_price == 93.0
        ), f"Expected break_price=93.0 (close_price), got {event.break_price}"

    def test_bearish_bos_priority_over_choch(self) -> None:
        """BOS takes priority over CHoCH when both candidates exist."""
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 100, 110, 100 - i, 105 - i) for i in range(10)]
        data[9] = _make_candle(9, 98, 105, 85, 88)

        swing = _make_swing(9, PivotType.SWING_LOW, 85)
        prev_sl = _make_swing(4, PivotType.SWING_LOW, 100)
        prev_sh = _make_swing(2, PivotType.SWING_HIGH, 107)

        result = cls._check_bearish_break(swing, [prev_sh, prev_sl], data)

        assert result is not None
        event, is_bos = result
        assert is_bos is True, "BOS should take priority over CHoCH"
        assert event.event_type == BOSCHoCHType.BEARISH_BOS

    def test_bearish_no_break_when_close_above_level(self) -> None:
        """No break when close_price does not drop below the level."""
        cls = _make_classifier(min_strength_ratio=0.0)

        # Close at 101 > swing_low level 100 → no break
        data = [_make_candle(i, 100, 110, 100 - i, 105 - i) for i in range(10)]
        data[9] = _make_candle(9, 102, 108, 95, 101)

        swing = _make_swing(9, PivotType.SWING_LOW, 95)
        prev_sl = _make_swing(4, PivotType.SWING_LOW, 100)

        result = cls._check_bearish_break(swing, [prev_sl], data)
        assert result is None


# ---------------------------------------------------------------------------
# Strength calculation correctness
# ---------------------------------------------------------------------------


class TestStrengthCalculation:
    """Verify that strength is computed from close_price, not swing.price."""

    def test_bullish_strength_uses_close(self) -> None:
        """Strength ratio must be computed from close_price / level_price."""
        cls = _make_classifier(min_strength_ratio=0.0)

        # Level at 100, swing high=120, close=108
        # If bug existed: strength = 120/100 = 1.2
        # After fix: strength = 108/100 = 1.08
        data = [_make_candle(i, 95, 100 + i, 90, 95 + i) for i in range(10)]
        data[9] = _make_candle(9, 105, 120, 104, 108)

        swing = _make_swing(9, PivotType.SWING_HIGH, 120)
        prev_sh = _make_swing(4, PivotType.SWING_HIGH, 100)

        result = cls._check_bullish_break(swing, [prev_sh], data)
        assert result is not None
        event, _ = result
        # close_price=108, level=100 → strength ≈ 0.08
        # swing.price=120, level=100 → strength would be 0.20 (bug)
        assert event.strength == pytest.approx(
            0.08, abs=0.01
        ), f"Expected strength ≈ 0.08 (from close=108), got {event.strength}"

    def test_bearish_strength_uses_close(self) -> None:
        """Bearish strength ratio must be computed from close_price / level_price."""
        cls = _make_classifier(min_strength_ratio=0.0)

        # Level at 100, swing low=80, close=92
        # If bug existed: strength = 100/80 = 1.25
        # After fix: strength = 100/92 ≈ 1.087
        data = [_make_candle(i, 105, 110, 100 - i, 102 - i) for i in range(10)]
        data[9] = _make_candle(9, 95, 100, 80, 92)

        swing = _make_swing(9, PivotType.SWING_LOW, 80)
        prev_sl = _make_swing(4, PivotType.SWING_LOW, 100)

        result = cls._check_bearish_break(swing, [prev_sl], data)
        assert result is not None
        event, _ = result
        # close_price=92, level=100 → strength ≈ 0.087
        # swing.price=80, level=100 → strength would be 0.25 (bug)
        assert event.strength == pytest.approx(
            0.087, abs=0.01
        ), f"Expected strength ≈ 0.087 (from close=92), got {event.strength}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for BOS/CHoCH detection."""

    def test_empty_prev_swings_returns_none(self) -> None:
        """No break possible with empty previous swings list."""
        cls = _make_classifier()
        data = [_make_candle(i, 100, 105, 95, 102) for i in range(5)]
        swing = _make_swing(4, PivotType.SWING_HIGH, 105)

        assert cls._check_bullish_break(swing, [], data) is None
        assert cls._check_bearish_break(swing, [], data) is None

    def test_min_strength_ratio_filters_weak_breaks(self) -> None:
        """Breaks below min_strength_ratio are filtered out."""
        cls = _make_classifier(min_strength_ratio=0.5)

        data = [_make_candle(i, 95, 100 + i, 90, 95 + i) for i in range(10)]
        data[9] = _make_candle(9, 105, 120, 104, 108)

        swing = _make_swing(9, PivotType.SWING_HIGH, 120)
        prev_sh = _make_swing(4, PivotType.SWING_HIGH, 100)

        result = cls._check_bullish_break(swing, [prev_sh], data)
        # strength ≈ 0.08 < 0.5 threshold → filtered out
        assert result is None

    def test_consecutive_breaks_most_recent_wins(self) -> None:
        """When multiple breaks qualify, the most recent one is returned."""
        cls = _make_classifier(min_strength_ratio=0.0)

        data = [_make_candle(i, 95, 100 + i, 90, 95 + i) for i in range(10)]
        data[9] = _make_candle(9, 105, 115, 104, 112)

        swing = _make_swing(9, PivotType.SWING_HIGH, 115)
        prev_sh1 = _make_swing(2, PivotType.SWING_HIGH, 97)
        prev_sh2 = _make_swing(5, PivotType.SWING_HIGH, 100)

        result = cls._check_bullish_break(swing, [prev_sh1, prev_sh2], data)
        assert result is not None
        event, _ = result
        # Most recent is prev_sh2 at price 100
        assert event.broken_level.price == 100.0
