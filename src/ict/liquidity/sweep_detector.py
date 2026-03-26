"""Liquidity sweep detector.

Detects stop-hunt patterns where price briefly exceeds a key level
(previous high/low, equal highs/lows) before reversing. Generates
confirmation signals based on rejection candle analysis.

Detection latency target: < 2 candles from sweep event.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.ict.liquidity.models import (
    LiquidityLevel,
    LiquidityLevelType,
    LiquiditySweep,
    SweepConfirmation,
    SweepDirection,
    SweepSignal,
)

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData

logger = logging.getLogger(__name__)


@dataclass
class LiquiditySweepConfig:
    """Configuration for the liquidity sweep detector.

    Attributes:
        lookback: Number of bars to look back for swing highs/lows.
        equal_level_tolerance_pct: Percentage tolerance for identifying
            equal highs/lows (e.g. 0.1 = 0.1%).
        min_sweep_penetration_pct: Minimum penetration beyond the level
            to qualify as a sweep (e.g. 0.01 = 0.01%).
        max_sweep_penetration_pct: Maximum penetration before it's
            considered a break, not a sweep (e.g. 0.5 = 0.5%).
        rejection_wick_ratio_min: Minimum wick-to-body ratio for
            rejection candle confirmation.
        confirmation_lookahead: Maximum bars after sweep to look for
            confirmation (controls latency).
    """

    lookback: int = 20
    equal_level_tolerance_pct: float = 0.1
    min_sweep_penetration_pct: float = 0.01
    max_sweep_penetration_pct: float = 0.5
    rejection_wick_ratio_min: float = 1.5
    confirmation_lookahead: int = 2


class LiquiditySweepDetector:
    """Detects liquidity sweep (stop hunt) patterns.

    A liquidity sweep occurs when price briefly moves beyond a key
    level (previous high/low, equal highs/lows) to trigger stop-loss
    orders, then reverses. The detector identifies these patterns
    and generates confirmation signals based on rejection candles.

    Detection flow:
        1. Identify liquidity levels (swing highs/lows, equal highs/lows)
        2. Check if recent candles sweep beyond those levels
        3. Confirm sweeps via rejection candle patterns
        4. Generate signals with confidence scores

    Parameters:
        config: Detector configuration parameters.
    """

    def __init__(self, config: LiquiditySweepConfig | None = None) -> None:
        self.config = config or LiquiditySweepConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, data: list[OHLCVData]) -> list[LiquiditySweep]:
        """Run full sweep detection on the candle data.

        Identifies liquidity levels from historical data (excluding the
        most recent confirmation window), then scans recent candles for
        sweeps against those levels.

        Args:
            data: List of OHLCV candles.

        Returns:
            List of detected liquidity sweeps, sorted by candle index.
        """
        if len(data) < self.config.confirmation_lookahead + 4:
            return []

        # Identify levels from historical data only (exclude sweep scan zone)
        level_cutoff = max(0, len(data) - self.config.confirmation_lookahead - 1)
        historical_data = (
            data[:level_cutoff]
            if level_cutoff > 0
            else data[: -self.config.confirmation_lookahead - 1]
        )
        if len(historical_data) < 3:
            return []

        # Identify levels from historical data only (exclude sweep scan zone)
        level_cutoff = max(0, len(data) - self.config.confirmation_lookahead - 1)
        historical_data = (
            data[:level_cutoff]
            if level_cutoff > 0
            else data[: -self.config.confirmation_lookahead - 1]
        )
        if len(historical_data) < 3:
            return []

        levels = self._identify_liquidity_levels(historical_data)
        if not levels:
            return []

        sweeps: list[LiquiditySweep] = []

        # Scan recent candles for sweeps
        scan_start = max(
            0, len(data) - self.config.lookback - self.config.confirmation_lookahead
        )
        for i in range(scan_start, len(data)):
            candle = data[i]
            for level in levels:
                sweep = self._check_sweep(candle, i, level)
                if sweep is not None:
                    # Try to confirm with subsequent candles
                    confirmation = self._check_confirmation(data, sweep)
                    confirmed_sweep = LiquiditySweep(
                        sweep_candle_index=sweep.sweep_candle_index,
                        direction=sweep.direction,
                        level=sweep.level,
                        sweep_high=sweep.sweep_high,
                        sweep_low=sweep.sweep_low,
                        penetration=sweep.penetration,
                        penetration_pct=sweep.penetration_pct,
                        confirmation=confirmation,
                    )
                    sweeps.append(confirmed_sweep)

        # Deduplicate: keep the strongest sweep per candle
        sweeps = self._deduplicate_sweeps(sweeps)
        return sorted(sweeps, key=lambda s: s.sweep_candle_index)

    def generate_signals(self, sweeps: list[LiquiditySweep]) -> list[SweepSignal]:
        """Convert confirmed sweeps into trading signals.

        Only sweeps with confirmed rejection candles produce signals.

        Args:
            sweeps: List of detected sweeps.

        Returns:
            List of sweep-based trading signals.
        """
        signals: list[SweepSignal] = []
        for sweep in sweeps:
            if not sweep.confirmation.confirmed:
                continue

            confidence = self._calculate_confidence(sweep)
            signal = SweepSignal(
                sweep=sweep,
                signal_direction=sweep.direction,
                confidence=confidence,
                metadata={
                    "level_type": sweep.level.level_type.value,
                    "level_price": sweep.level.price,
                    "penetration_pct": sweep.penetration_pct,
                    "wick_ratio": sweep.confirmation.wick_ratio,
                    "strength": sweep.level.strength,
                },
            )
            signals.append(signal)

        return sorted(signals, key=lambda s: s.confidence, reverse=True)

    # ------------------------------------------------------------------
    # Liquidity level identification
    # ------------------------------------------------------------------

    def _identify_liquidity_levels(self, data: list[OHLCVData]) -> list[LiquidityLevel]:
        """Identify key liquidity levels from candle data.

        Finds swing highs, swing lows, and groups nearby levels into
        equal highs/lows.

        Args:
            data: List of OHLCV candles.

        Returns:
            List of liquidity levels, sorted by price.
        """
        if len(data) < 3:
            return []

        lookback = min(self.config.lookback, len(data) - 1)
        levels: list[LiquidityLevel] = []

        # Collect swing highs and lows from recent data
        swing_highs: list[tuple[int, float]] = []
        swing_lows: list[tuple[int, float]] = []

        for i in range(1, len(data) - 1):
            prev_h = data[i - 1].high_price
            curr_h = data[i].high_price
            next_h = data[i + 1].high_price
            prev_l = data[i - 1].low_price
            curr_l = data[i].low_price
            next_l = data[i + 1].low_price

            if curr_h > prev_h and curr_h > next_h:
                swing_highs.append((i, curr_h))
            if curr_l < prev_l and curr_l < next_l:
                swing_lows.append((i, curr_l))

        # Only keep levels within lookback
        cutoff = max(0, len(data) - lookback - 1)
        swing_highs = [(i, p) for i, p in swing_highs if i >= cutoff]
        swing_lows = [(i, p) for i, p in swing_lows if i >= cutoff]

        # Group swing highs into equal highs
        high_groups = self._group_equal_levels(swing_highs)
        for group_indices, group_price in high_groups:
            level_type = (
                LiquidityLevelType.EQUAL_HIGHS
                if len(group_indices) > 1
                else LiquidityLevelType.PREVIOUS_HIGH
            )
            strength = min(len(group_indices) * 1.0, 5.0)
            ts = max(
                (data[i].timestamp for i in group_indices if i < len(data)),
                default=0,
            )
            levels.append(
                LiquidityLevel(
                    price=group_price,
                    level_type=level_type,
                    source_indices=tuple(group_indices),
                    strength=strength,
                    timestamp_ms=ts,
                )
            )

        # Group swing lows into equal lows
        low_groups = self._group_equal_levels(swing_lows)
        for group_indices, group_price in low_groups:
            level_type = (
                LiquidityLevelType.EQUAL_LOWS
                if len(group_indices) > 1
                else LiquidityLevelType.PREVIOUS_LOW
            )
            strength = min(len(group_indices) * 1.0, 5.0)
            ts = max(
                (data[i].timestamp for i in group_indices if i < len(data)),
                default=0,
            )
            levels.append(
                LiquidityLevel(
                    price=group_price,
                    level_type=level_type,
                    source_indices=tuple(group_indices),
                    strength=strength,
                    timestamp_ms=ts,
                )
            )

        return sorted(levels, key=lambda lv: lv.price)

    def _group_equal_levels(
        self, levels: list[tuple[int, float]]
    ) -> list[tuple[list[int], float]]:
        """Group price levels that are within tolerance of each other.

        Args:
            levels: List of (index, price) tuples.

        Returns:
            List of (indices, average_price) groups.
        """
        if not levels:
            return []

        tolerance = self.config.equal_level_tolerance_pct / 100.0
        groups: list[list[tuple[int, float]]] = []
        current_group: list[tuple[int, float]] = [levels[0]]

        for i in range(1, len(levels)):
            prev_price = current_group[0][1]
            curr_price = levels[i][1]
            if (
                prev_price > 0
                and abs(curr_price - prev_price) / prev_price <= tolerance
            ):
                current_group.append(levels[i])
            else:
                groups.append(current_group)
                current_group = [levels[i]]

        groups.append(current_group)

        result: list[tuple[list[int], float]] = []
        for group in groups:
            indices = [idx for idx, _ in group]
            avg_price = sum(p for _, p in group) / len(group)
            result.append((indices, avg_price))

        return result

    # ------------------------------------------------------------------
    # Sweep detection
    # ------------------------------------------------------------------

    def _check_sweep(
        self,
        candle: OHLCVData,
        index: int,
        level: LiquidityLevel,
    ) -> LiquiditySweep | None:
        """Check if a candle sweeps beyond a liquidity level.

        A bearish sweep: candle high exceeds a previous high/equal high.
        A bullish sweep: candle low goes below a previous low/equal low.

        Args:
            candle: The OHLCV candle to check.
            index: Index of the candle in the data array.
            level: The liquidity level to check against.

        Returns:
            A LiquiditySweep if a sweep is detected, None otherwise.
        """
        # Check for bearish sweep (above a high)
        if level.level_type in (
            LiquidityLevelType.PREVIOUS_HIGH,
            LiquidityLevelType.EQUAL_HIGHS,
        ):
            if candle.high_price > level.price:
                penetration = candle.high_price - level.price
                penetration_pct = penetration / level.price * 100

                if (
                    penetration_pct >= self.config.min_sweep_penetration_pct
                    and penetration_pct <= self.config.max_sweep_penetration_pct
                ):
                    return LiquiditySweep(
                        sweep_candle_index=index,
                        direction=SweepDirection.BEARISH_SWEEP,
                        level=level,
                        sweep_high=candle.high_price,
                        sweep_low=candle.low_price,
                        penetration=penetration,
                        penetration_pct=penetration_pct,
                    )

        # Check for bullish sweep (below a low)
        if level.level_type in (
            LiquidityLevelType.PREVIOUS_LOW,
            LiquidityLevelType.EQUAL_LOWS,
        ):
            if candle.low_price < level.price:
                penetration = level.price - candle.low_price
                penetration_pct = penetration / level.price * 100

                if (
                    penetration_pct >= self.config.min_sweep_penetration_pct
                    and penetration_pct <= self.config.max_sweep_penetration_pct
                ):
                    return LiquiditySweep(
                        sweep_candle_index=index,
                        direction=SweepDirection.BULLISH_SWEEP,
                        level=level,
                        sweep_high=candle.high_price,
                        sweep_low=candle.low_price,
                        penetration=penetration,
                        penetration_pct=penetration_pct,
                    )

        return None

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def _check_confirmation(
        self,
        data: list[OHLCVData],
        sweep: LiquiditySweep,
    ) -> SweepConfirmation:
        """Check for rejection candle confirmation of a sweep.

        A confirmed sweep shows a rejection candle after the sweep,
        where price closes back on the correct side of the level.

        For bearish sweeps: close should be below the swept high.
        For bullish sweeps: close should be above the swept low.

        Args:
            data: Full candle data array.
            sweep: The sweep event to confirm.

        Returns:
            SweepConfirmation with confirmation details.
        """
        sweep_idx = sweep.sweep_candle_index
        level_price = sweep.level.price

        # Check the sweep candle itself and the next candle(s)
        for offset in range(self.config.confirmation_lookahead + 1):
            check_idx = sweep_idx + offset
            if check_idx >= len(data):
                continue

            candle = data[check_idx]
            wick_ratio = self._compute_wick_ratio(candle, sweep.direction)

            if wick_ratio < self.config.rejection_wick_ratio_min:
                continue

            # Check if close is back on the correct side
            close_beyond = False
            if sweep.direction == SweepDirection.BEARISH_SWEEP:
                close_beyond = candle.close_price < level_price
            else:
                close_beyond = candle.close_price > level_price

            if close_beyond:
                return SweepConfirmation(
                    confirmed=True,
                    rejection_candle_index=check_idx,
                    wick_ratio=round(wick_ratio, 4),
                    close_beyond_level=True,
                )

        return SweepConfirmation(confirmed=False)

    def _compute_wick_ratio(
        self,
        candle: OHLCVData,
        direction: SweepDirection,
    ) -> float:
        """Compute the wick-to-body ratio for a candle.

        For bearish sweeps: upper wick / body.
        For bullish sweeps: lower wick / body.

        A high ratio indicates strong rejection.

        Args:
            candle: The OHLCV candle.
            direction: Sweep direction to determine which wick to measure.

        Returns:
            Wick-to-body ratio. Returns 0.0 for doji candles.
        """
        body = abs(candle.close_price - candle.open_price)
        if body < 1e-10:
            return 0.0  # Doji - no meaningful body

        if direction == SweepDirection.BEARISH_SWEEP:
            # Upper wick: high minus max(open, close)
            wick = candle.high_price - max(candle.open_price, candle.close_price)
        else:
            # Lower wick: min(open, close) minus low
            wick = min(candle.open_price, candle.close_price) - candle.low_price

        return wick / body

    # ------------------------------------------------------------------
    # Confidence and deduplication
    # ------------------------------------------------------------------

    def _calculate_confidence(self, sweep: LiquiditySweep) -> float:
        """Calculate a confidence score for a confirmed sweep signal.

        Factors:
        - Level strength (equal highs/lows are stronger)
        - Wick ratio of rejection candle
        - Penetration depth (moderate is better than extreme)

        Args:
            sweep: A confirmed liquidity sweep.

        Returns:
            Confidence score from 0.0 to 1.0.
        """
        # Base confidence from level strength (1-5 -> 0.4-0.8)
        strength_factor = min(sweep.level.strength / 5.0, 1.0) * 0.4 + 0.4

        # Wick ratio factor (higher = more confident, capped at 3.0)
        wick = min(sweep.confirmation.wick_ratio / 3.0, 1.0)
        wick_factor = wick * 0.3

        # Penetration factor (moderate penetration is ideal)
        # Too little = weak sweep; too much = possible real break
        mid_pen = (
            self.config.min_sweep_penetration_pct
            + self.config.max_sweep_penetration_pct
        ) / 2
        pen_dev = abs(sweep.penetration_pct - mid_pen)
        pen_range = (
            self.config.max_sweep_penetration_pct
            - self.config.min_sweep_penetration_pct
        )
        pen_factor = max(0.0, 1.0 - pen_dev / pen_range) * 0.3

        confidence = round(strength_factor + wick_factor + pen_factor, 4)
        return min(max(confidence, 0.0), 1.0)

    def _deduplicate_sweeps(self, sweeps: list[LiquiditySweep]) -> list[LiquiditySweep]:
        """Remove duplicate sweeps at the same candle index.

        When multiple sweeps occur at the same candle, keep only the
        one with the strongest level.

        Args:
            sweeps: List of detected sweeps.

        Returns:
            Deduplicated list.
        """
        by_candle: dict[int, LiquiditySweep] = {}
        for sweep in sweeps:
            idx = sweep.sweep_candle_index
            if (
                idx not in by_candle
                or sweep.level.strength > by_candle[idx].level.strength
            ):
                by_candle[idx] = sweep
        return list(by_candle.values())

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self) -> dict[str, Any]:
        """Return detector configuration metadata."""
        return {
            "name": "LiquiditySweepDetector",
            "description": "ICT liquidity sweep (stop hunt) pattern detector",
            "parameters": {
                "lookback": self.config.lookback,
                "equal_level_tolerance_pct": self.config.equal_level_tolerance_pct,
                "min_sweep_penetration_pct": self.config.min_sweep_penetration_pct,
                "max_sweep_penetration_pct": self.config.max_sweep_penetration_pct,
                "rejection_wick_ratio_min": self.config.rejection_wick_ratio_min,
                "confirmation_lookahead": self.config.confirmation_lookahead,
            },
        }
