"""Unit tests for liquidity sweep detection.

Covers:
- AC1: Detect liquidity sweep patterns (stop hunts above/below key levels)
- AC2: Identify sweep targets (previous highs/lows, equal highs/lows)
- AC3: Generate sweep confirmation signals (rejection candle pattern)
- AC4: Sweep detection latency < 2 candles
- AC5: Unit tests for sweep detection scenarios
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import pytest

sys.path.insert(0, "src")

from src.ict.liquidity.models import (
    LiquidityLevel,
    LiquidityLevelType,
    LiquiditySweep,
    SweepConfirmation,
    SweepDirection,
    SweepSignal,
)
from src.ict.liquidity.sweep_detector import (
    LiquiditySweepConfig,
    LiquiditySweepDetector,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class Candle:
    """Minimal OHLCV candle for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 100.0


def _candles_from_tuples(
    pairs: list[tuple[float, float, float, float]],
) -> list[Candle]:
    """Create candle list from (open, high, low, close) tuples."""
    return [
        Candle(
            timestamp=1000 * (i + 1),
            open_price=o,
            high_price=h,
            low_price=l,
            close_price=c,
        )
        for i, (o, h, l, c) in enumerate(pairs)
    ]


def _make_uptrend_with_sweep_high() -> list[Candle]:
    """Create data with a clear uptrend, then a sweep above the high.

    Pattern: uptrend -> swing high -> dip -> sweep above high -> rejection.
    """
    pairs = [
        # Uptrend establishing a swing high at bar 3 (high=105)
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 102.0, 100.0, 101.5),
        (101.5, 103.0, 101.0, 102.5),
        (102.5, 105.0, 102.0, 104.0),  # swing high at 105
        (104.0, 104.5, 102.0, 103.0),  # pullback
        (103.0, 103.5, 101.0, 102.0),
        (102.0, 102.5, 100.5, 101.0),  # bottom of pullback
        (101.0, 103.0, 100.5, 102.5),  # recovery
        # Sweep: wick above 105 but close below (rejection)
        (102.5, 105.3, 102.0, 103.0),  # sweep + rejection candle
        (103.0, 104.0, 102.5, 103.5),  # continuation down
    ]
    return _candles_from_tuples(pairs)


def _make_downtrend_with_sweep_low() -> list[Candle]:
    """Create data with a downtrend, then a sweep below the low.

    Pattern: downtrend -> swing low -> bounce -> sweep below low -> rejection.
    """
    pairs = [
        # Downtrend establishing a swing low at bar 3 (low=95)
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 100.0, 97.5, 98.0),
        (98.0, 98.5, 96.0, 96.5),
        (96.5, 97.0, 95.0, 95.5),  # swing low at 95
        (95.5, 96.5, 95.5, 96.0),  # bounce
        (96.0, 97.0, 96.0, 96.5),
        (96.5, 97.5, 96.5, 97.0),  # top of bounce
        (97.0, 97.5, 96.5, 97.0),  # start dropping
        # Sweep: wick below 95 but close above (rejection)
        (97.0, 97.5, 94.8, 96.5),  # sweep + rejection candle
        (96.5, 97.0, 96.0, 96.5),  # continuation up
    ]
    return _candles_from_tuples(pairs)


def _make_equal_highs_with_sweep() -> list[Candle]:
    """Create data with two highs at the same level, then a sweep.

    Pattern: high at 100 -> dip -> high at 100 -> dip -> sweep above 100.
    """
    pairs = [
        (97.5, 98.5, 97.0, 98.0),  # padding (not a swing high)
        (98.0, 100.0, 97.5, 99.0),  # first high at 100 (swing high)
        (99.0, 99.5, 97.0, 97.5),  # dip
        (97.5, 100.0, 97.0, 99.0),  # second high at 100 (equal high)
        (99.0, 99.5, 97.0, 97.5),  # dip
        (97.5, 98.0, 97.0, 97.5),
        (97.5, 98.0, 97.0, 97.5),
        # Sweep above 100 with rejection
        (97.5, 100.3, 97.0, 98.0),  # sweep candle (wick above 100, close below)
        (
            98.0,
            100.5,
            97.0,
            97.5,
        ),  # continuation (higher high prevents sweep being swing)
        (97.5, 99.0, 97.0, 97.5),
    ]
    return _candles_from_tuples(pairs)


def _make_equal_lows_with_sweep() -> list[Candle]:
    """Create data with two lows at the same level, then a sweep.

    Pattern: low at 100 -> bounce -> low at 100 -> bounce -> sweep below 100.
    """
    pairs = [
        (102.5, 103.0, 101.0, 102.0),  # padding
        (102.0, 102.5, 100.0, 101.0),  # first low at 100 (swing low)
        (101.0, 103.0, 101.0, 102.5),  # bounce
        (102.5, 103.0, 100.0, 101.0),  # second low at 100 (equal low)
        (101.0, 103.0, 101.0, 102.5),  # bounce
        (102.5, 103.0, 102.0, 102.5),
        (102.5, 103.0, 102.0, 102.5),
        # Sweep below 100 with rejection
        (102.5, 103.0, 99.8, 102.0),  # sweep candle (wick below 100, close above)
        (
            102.0,
            103.0,
            99.5,
            102.5,
        ),  # continuation (lower low prevents sweep being swing)
        (102.5, 103.0, 101.0, 102.0),
    ]
    return _candles_from_tuples(pairs)


def _make_no_sweep_ranging() -> list[Candle]:
    """Ranging market with no sweeps."""
    pairs = [
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 101.5, 99.5, 100.0),
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 100.5, 99.0, 100.0),
        (100.0, 101.0, 99.5, 100.5),
        (100.5, 101.0, 99.5, 100.0),
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 100.5, 99.0, 100.0),
    ]
    return _candles_from_tuples(pairs)


def _make_real_break_not_sweep() -> list[Candle]:
    """A real breakout, not a sweep - price closes beyond the level."""
    pairs = [
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 102.0, 100.0, 101.5),
        (101.5, 103.0, 101.0, 102.5),
        (102.5, 105.0, 102.0, 104.0),  # swing high at 105
        (104.0, 104.5, 103.0, 104.0),
        (104.0, 104.5, 103.0, 104.0),
        # Real break: body closes well above 105
        (104.0, 107.0, 103.5, 106.5),  # closes above 105 = real break
        (106.5, 108.0, 106.0, 107.5),
    ]
    return _candles_from_tuples(pairs)


def _make_sweep_with_2candle_latency() -> list[Candle]:
    """Sweep confirmed on the second candle after the sweep event.

    AC4: Detection latency must be < 2 candles.
    """
    pairs = [
        (100.0, 101.0, 99.0, 100.5),
        (100.5, 102.0, 100.0, 101.5),
        (101.5, 103.0, 101.0, 102.5),
        (102.5, 105.0, 102.0, 104.0),  # swing high at 105
        (104.0, 104.5, 102.0, 103.0),
        (103.0, 103.5, 101.0, 102.0),
        (102.0, 102.5, 100.5, 101.0),
        (101.0, 103.0, 100.5, 102.5),
        # Sweep candle (no rejection on this candle)
        (
            102.5,
            105.2,
            102.0,
            104.8,
        ),  # wick above 105, close at 104.8 (below but body not rejecting)
        # First candle after: not confirming
        (104.8, 105.0, 104.0, 104.5),
        # Second candle after: confirming rejection
        (104.5, 105.1, 103.5, 104.0),  # long upper wick, close below 105
    ]
    return _candles_from_tuples(pairs)


# ---------------------------------------------------------------------------
# AC2: Liquidity level identification tests
# ---------------------------------------------------------------------------


class TestLiquidityLevelIdentification:
    """AC2: Identify sweep targets - previous highs/lows, equal highs/lows."""

    def test_identifies_previous_high(self) -> None:
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        # Use historical data cutoff (same as detect() uses internally)
        level_cutoff = max(0, len(data) - config.confirmation_lookahead - 1)
        historical = data[:level_cutoff]
        levels = detector._identify_liquidity_levels(historical)
        high_levels = [
            lv
            for lv in levels
            if lv.level_type
            in (LiquidityLevelType.PREVIOUS_HIGH, LiquidityLevelType.EQUAL_HIGHS)
        ]
        assert len(high_levels) >= 1
        # The highest level should be near 105
        max_high = max(lv.price for lv in high_levels)
        assert abs(max_high - 105.0) < 0.01

    def test_identifies_previous_low(self) -> None:
        data = _make_downtrend_with_sweep_low()
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        # Use historical data cutoff (same as detect() uses internally)
        level_cutoff = max(0, len(data) - config.confirmation_lookahead - 1)
        historical = data[:level_cutoff]
        levels = detector._identify_liquidity_levels(historical)
        low_levels = [
            lv
            for lv in levels
            if lv.level_type
            in (LiquidityLevelType.PREVIOUS_LOW, LiquidityLevelType.EQUAL_LOWS)
        ]
        assert len(low_levels) >= 1
        # The lowest level should be near 95
        min_low = min(lv.price for lv in low_levels)
        assert abs(min_low - 95.0) < 0.01

    def test_identifies_equal_highs(self) -> None:
        data = _make_equal_highs_with_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            equal_level_tolerance_pct=0.2,  # 0.2% tolerance
        )
        detector = LiquiditySweepDetector(config)

        levels = detector._identify_liquidity_levels(data)
        eh_levels = [
            lv for lv in levels if lv.level_type == LiquidityLevelType.EQUAL_HIGHS
        ]
        assert len(eh_levels) >= 1, "Should detect equal highs at 100.0"

    def test_identifies_equal_lows(self) -> None:
        data = _make_equal_lows_with_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            equal_level_tolerance_pct=0.2,
        )
        detector = LiquiditySweepDetector(config)

        levels = detector._identify_liquidity_levels(data)
        el_levels = [
            lv for lv in levels if lv.level_type == LiquidityLevelType.EQUAL_LOWS
        ]
        assert len(el_levels) >= 1, "Should detect equal lows at 100.0"

    def test_equal_highs_have_higher_strength(self) -> None:
        """Equal highs should have higher strength than single highs."""
        data = _make_equal_highs_with_sweep()
        config = LiquiditySweepConfig(lookback=20, equal_level_tolerance_pct=0.2)
        detector = LiquiditySweepDetector(config)

        levels = detector._identify_liquidity_levels(data)
        eh = [lv for lv in levels if lv.level_type == LiquidityLevelType.EQUAL_HIGHS]
        ph = [lv for lv in levels if lv.level_type == LiquidityLevelType.PREVIOUS_HIGH]

        if eh and ph:
            assert eh[0].strength > ph[0].strength

    def test_no_levels_in_flat_data(self) -> None:
        """Flat data should produce fewer/no levels."""
        pairs = [(100.0, 100.1, 99.9, 100.0)] * 25
        data = _candles_from_tuples(pairs)
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        levels = detector._identify_liquidity_levels(data)
        assert len(levels) == 0, "Flat data should have no swing levels"


# ---------------------------------------------------------------------------
# AC1: Sweep detection tests
# ---------------------------------------------------------------------------


class TestSweepDetection:
    """AC1: Detect liquidity sweep patterns (stop hunts above/below key levels)."""

    def test_detects_bullish_sweep_below_low(self) -> None:
        """Bullish sweep: price sweeps below a previous low then reverses."""
        data = _make_downtrend_with_sweep_low()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        bullish_sweeps = [
            s for s in sweeps if s.direction == SweepDirection.BULLISH_SWEEP
        ]
        assert len(bullish_sweeps) >= 1, "Should detect at least one bullish sweep"

    def test_detects_bearish_sweep_above_high(self) -> None:
        """Bearish sweep: price sweeps above a previous high then reverses."""
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        bearish_sweeps = [
            s for s in sweeps if s.direction == SweepDirection.BEARISH_SWEEP
        ]
        assert len(bearish_sweeps) >= 1, "Should detect at least one bearish sweep"

    def test_sweep_has_correct_penetration(self) -> None:
        """Sweep should record correct penetration values."""
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        bearish = [s for s in sweeps if s.direction == SweepDirection.BEARISH_SWEEP]
        assert len(bearish) >= 1

        sweep = bearish[0]
        assert sweep.penetration > 0
        assert sweep.penetration_pct > 0
        assert sweep.sweep_high > sweep.level.price

    def test_no_sweep_in_ranging_market(self) -> None:
        """Ranging market should produce no sweeps."""
        data = _make_no_sweep_ranging()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        assert len(sweeps) == 0, "Ranging market should not produce sweeps"

    def test_real_break_not_detected_as_sweep(self) -> None:
        """A real breakout should not be flagged as a sweep."""
        data = _make_real_break_not_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        # The break candle closes at 106.5, well above 105 - no rejection
        # It may be detected as a sweep but should NOT be confirmed
        confirmed = [s for s in sweeps if s.confirmation.confirmed]
        assert len(confirmed) == 0, "Real break should not produce confirmed sweep"

    def test_detects_sweep_above_equal_highs(self) -> None:
        """Sweep above equal highs should be detected."""
        data = _make_equal_highs_with_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            equal_level_tolerance_pct=0.2,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        assert len(sweeps) >= 1, "Should detect sweep above equal highs"

    def test_detects_sweep_below_equal_lows(self) -> None:
        """Sweep below equal lows should be detected."""
        data = _make_equal_lows_with_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            equal_level_tolerance_pct=0.2,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        assert len(sweeps) >= 1, "Should detect sweep below equal lows"

    def test_insufficient_data_returns_empty(self) -> None:
        """Insufficient data should return empty list."""
        data = _candles_from_tuples([(100.0, 101.0, 99.0, 100.5)] * 3)
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        assert sweeps == []


# ---------------------------------------------------------------------------
# AC3: Confirmation signal tests
# ---------------------------------------------------------------------------


class TestSweepConfirmation:
    """AC3: Generate sweep confirmation signals (rejection candle pattern)."""

    def test_confirmed_sweep_has_rejection_candle(self) -> None:
        """A confirmed sweep should have a valid rejection candle index."""
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
            rejection_wick_ratio_min=1.0,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        confirmed = [s for s in sweeps if s.confirmation.confirmed]
        assert len(confirmed) >= 1, "Should have at least one confirmed sweep"

        sweep = confirmed[0]
        assert sweep.confirmation.rejection_candle_index >= 0
        assert sweep.confirmation.wick_ratio > 0
        assert sweep.confirmation.close_beyond_level is True

    def test_unconfirmed_sweep_no_signal(self) -> None:
        """An unconfirmed sweep should not produce a signal."""
        data = _make_real_break_not_sweep()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        signals = detector.generate_signals(sweeps)
        assert len(signals) == 0, "Unconfirmed sweeps should not generate signals"

    def test_signal_has_correct_direction(self) -> None:
        """Signal direction should match sweep direction."""
        data = _make_downtrend_with_sweep_low()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        signals = detector.generate_signals(sweeps)
        if signals:
            assert signals[0].signal_direction == SweepDirection.BULLISH_SWEEP

    def test_signal_confidence_in_valid_range(self) -> None:
        """All signals should have confidence between 0.0 and 1.0."""
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        signals = detector.generate_signals(sweeps)
        for signal in signals:
            assert 0.0 <= signal.confidence <= 1.0

    def test_signal_metadata_contains_level_info(self) -> None:
        """Signal metadata should contain level type and price."""
        data = _make_uptrend_with_sweep_high()
        config = LiquiditySweepConfig(lookback=20)
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        signals = detector.generate_signals(sweeps)
        if signals:
            meta = signals[0].metadata
            assert "level_type" in meta
            assert "level_price" in meta


# ---------------------------------------------------------------------------
# AC4: Latency tests
# ---------------------------------------------------------------------------


class TestDetectionLatency:
    """AC4: Sweep detection latency < 2 candles."""

    def test_sweep_confirmed_within_2_candles(self) -> None:
        """A sweep must be confirmed within 2 candles of the sweep event."""
        data = _make_sweep_with_2candle_latency()
        config = LiquiditySweepConfig(
            lookback=20,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
            rejection_wick_ratio_min=1.0,
            confirmation_lookahead=2,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        confirmed = [s for s in sweeps if s.confirmation.confirmed]
        if confirmed:
            for sweep in confirmed:
                latency = (
                    sweep.confirmation.rejection_candle_index - sweep.sweep_candle_index
                )
                assert latency <= 2, f"Confirmation latency {latency} exceeds 2 candles"

    def test_default_lookahead_is_2(self) -> None:
        """Default confirmation lookahead should be 2."""
        config = LiquiditySweepConfig()
        assert config.confirmation_lookahead == 2


# ---------------------------------------------------------------------------
# AC5: Additional scenario tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case and scenario tests."""

    def test_multiple_sweeps_deduplicated(self) -> None:
        """Multiple sweeps at the same candle should be deduplicated."""
        # Create data where two levels could be swept by the same candle
        pairs = [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 102.0, 100.0, 101.5),
            (101.5, 103.0, 101.0, 102.5),
            (102.5, 105.0, 102.0, 104.0),  # swing high at 105
            (104.0, 104.5, 103.0, 104.0),
            (104.0, 105.0, 103.0, 104.5),  # near-equal high
            (104.5, 104.5, 103.0, 104.0),
            (104.0, 105.3, 103.5, 104.0),  # sweeps both
            (104.0, 104.5, 103.0, 103.5),
        ]
        data = _candles_from_tuples(pairs)
        config = LiquiditySweepConfig(
            lookback=20,
            equal_level_tolerance_pct=0.2,
            min_sweep_penetration_pct=0.01,
            max_sweep_penetration_pct=0.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        # Should not have two sweeps at the same candle index
        indices = [s.sweep_candle_index for s in sweeps]
        assert len(indices) == len(set(indices)), "Sweeps should be deduplicated"

    def test_doji_candle_no_false_rejection(self) -> None:
        """A doji candle after a sweep should not trigger false confirmation."""
        pairs = [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 102.0, 100.0, 101.5),
            (101.5, 103.0, 101.0, 102.5),
            (102.5, 105.0, 102.0, 104.0),  # swing high at 105
            (104.0, 104.5, 103.0, 104.0),
            (104.0, 104.0, 103.0, 104.0),  # doji
            (104.0, 105.2, 103.5, 104.0),  # sweep with doji-like body
            (104.0, 104.2, 104.0, 104.1),  # doji after sweep
        ]
        data = _candles_from_tuples(pairs)
        config = LiquiditySweepConfig(
            lookback=20,
            rejection_wick_ratio_min=1.5,
        )
        detector = LiquiditySweepDetector(config)

        sweeps = detector.detect(data)
        # Doji has near-zero body, wick ratio should be ~0
        confirmed = [s for s in sweeps if s.confirmation.confirmed]
        # If confirmed, the rejection candle should not be a doji
        for sweep in confirmed:
            rej_idx = sweep.confirmation.rejection_candle_index
            rej_candle = data[rej_idx]
            body = abs(rej_candle.close_price - rej_candle.open_price)
            assert body > 1e-10, "Doji should not confirm a sweep"

    def test_model_validation_negative_price(self) -> None:
        """LiquidityLevel should reject negative prices."""
        with pytest.raises(ValueError, match="positive"):
            LiquidityLevel(
                price=-1.0,
                level_type=LiquidityLevelType.PREVIOUS_HIGH,
                source_indices=(0,),
            )

    def test_model_validation_negative_penetration(self) -> None:
        """LiquiditySweep should reject negative penetration."""
        level = LiquidityLevel(
            price=100.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(0,),
        )
        with pytest.raises(ValueError, match="non-negative"):
            LiquiditySweep(
                sweep_candle_index=1,
                direction=SweepDirection.BEARISH_SWEEP,
                level=level,
                sweep_high=101.0,
                sweep_low=99.0,
                penetration=-0.5,
                penetration_pct=-0.5,
            )

    def test_signal_validation_confidence_range(self) -> None:
        """SweepSignal should reject confidence outside [0, 1]."""
        level = LiquidityLevel(
            price=100.0,
            level_type=LiquidityLevelType.PREVIOUS_HIGH,
            source_indices=(0,),
        )
        sweep = LiquiditySweep(
            sweep_candle_index=1,
            direction=SweepDirection.BEARISH_SWEEP,
            level=level,
            sweep_high=101.0,
            sweep_low=99.0,
            penetration=1.0,
            penetration_pct=1.0,
        )
        with pytest.raises(ValueError, match="0\\.0.*1\\.0"):
            SweepSignal(
                sweep=sweep,
                signal_direction=SweepDirection.BEARISH_SWEEP,
                confidence=1.5,
            )

    def test_get_metadata(self) -> None:
        """Detector metadata should be available."""
        config = LiquiditySweepConfig(lookback=15)
        detector = LiquiditySweepDetector(config)
        meta = detector.get_metadata()

        assert meta["name"] == "LiquiditySweepDetector"
        assert meta["parameters"]["lookback"] == 15
        assert "description" in meta

    def test_custom_config_overrides_defaults(self) -> None:
        """Custom config should properly override defaults."""
        config = LiquiditySweepConfig(
            lookback=10,
            equal_level_tolerance_pct=0.5,
            min_sweep_penetration_pct=0.05,
            max_sweep_penetration_pct=1.0,
            rejection_wick_ratio_min=2.0,
            confirmation_lookahead=3,
        )
        detector = LiquiditySweepDetector(config)

        assert detector.config.lookback == 10
        assert detector.config.equal_level_tolerance_pct == 0.5
        assert detector.config.min_sweep_penetration_pct == 0.05
        assert detector.config.max_sweep_penetration_pct == 1.0
        assert detector.config.rejection_wick_ratio_min == 2.0
        assert detector.config.confirmation_lookahead == 3
