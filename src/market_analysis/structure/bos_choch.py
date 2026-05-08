"""BOS/CHoCH Classification Module.

This module provides classification of Break of Structure (BOS) and
Change of Character (CHoCH) events based on swing pivot analysis.

Key concepts:
- BOS (Break of Structure): Break of a previous swing high/low in the trend direction
- CHoCH (Change of Character): Break of a previous swing high/low against the trend direction
- Structure Level: A swing high or low that defines a structural boundary

Usage:
    classifier = BOSCHoCHClassifier()
    events = classifier.classify(pivots, data)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from market_analysis.structure.swing_pivot import (
        SwingPivot,
        SwingPivotDetectionResult,
    )


class BOSCHoCHType(Enum):
    """Type of BOS/CHoCH event."""

    BULLISH_BOS = "bullish_bos"  # Break of structure to upside
    BEARISH_BOS = "bearish_bos"  # Break of structure to downside
    BULLISH_CHOCH = "bullish_choch"  # Change of character (bullish)
    BEARISH_CHOCH = "bearish_choch"  # Change of character (bearish)
    NONE = "none"


class TrendDirection(Enum):
    """Direction of the current trend.

    Used to distinguish BOS (break in trend direction) from CHoCH (break against trend).
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    UNDEFINED = "undefined"


@dataclass
class StructureLevel:
    """Represents a structure level (swing high or low).

    Attributes:
        pivot: The swing pivot that defines this level
        price: The price level
        broken: Whether this level has been broken
        broken_at: Index where level was broken (if broken)
    """

    pivot: SwingPivot
    price: float
    broken: bool = False
    broken_at: int | None = None

    @property
    def is_swing_high(self) -> bool:
        """Check if this is a swing high level."""
        return self.pivot.pivot_type.value == "swing_high"


@dataclass
class BOSCHoCH:
    """Represents a BOS or CHoCH event.

    Attributes:
        event_type: Type of event (BULLISH_BOS, BEARISH_BOS, etc.)
        broken_level: The structure level that was broken
        break_index: Index where the break occurred
        break_price: Price at which the break occurred
        timestamp: Timestamp of the break
        confirmation_index: Index of bar that confirmed the break
        is_bos: True if this is a BOS, False if CHoCH
        strength: Strength of the break (ratio of break vs level price)
    """

    event_type: BOSCHoCHType
    broken_level: StructureLevel
    break_index: int
    break_price: float
    timestamp: datetime
    confirmation_index: int
    is_bos: bool
    strength: float


@dataclass
class BOSCHoCHClassificationResult:
    """Result of BOS/CHoCH classification.

    Attributes:
        events: List of all BOS/CHoCH events (chronological)
        bullish_bos_events: List of bullish BOS events
        bearish_bos_events: List of bearish BOS events
        bullish_choch_events: List of bullish CHoCH events
        bearish_choch_events: List of bearish CHoCH events
        current_structure_high: Current active structure high level
        current_structure_low: Current active structure low level
        last_bos_direction: Last detected BOS direction (or None)
        trend_direction: Current tracked trend state (BULLISH, BEARISH, or UNDEFINED)
    """

    events: list[BOSCHoCH]
    bullish_bos_events: list[BOSCHoCH]
    bearish_bos_events: list[BOSCHoCH]
    bullish_choch_events: list[BOSCHoCH]
    bearish_choch_events: list[BOSCHoCH]
    current_structure_high: StructureLevel | None
    current_structure_low: StructureLevel | None
    last_bos_direction: str | None
    trend_direction: TrendDirection = TrendDirection.UNDEFINED


class BOSCHoCHClassifier:
    """Classifier for BOS (Break of Structure) and CHoCH (Change of Character).

    BOS: Occurs when price breaks a structure level in the direction of the trend.
         In an uptrend: break of a previous swing high.
         In a downtrend: break of a previous swing low.

    CHoCH: Occurs when price breaks a structure level against the trend direction.
           This signals a potential trend change.
           In an uptrend: break of a previous swing low (structure low).
           In a downtrend: break of a previous swing high (structure high).

    Parameters:
        confirmation_bars: Number of bars required to confirm a break (default: 1)
        min_strength_ratio: Minimum strength ratio for valid break (default: 0.001)
    """

    DEFAULT_CONFIRMATION_BARS = 1
    DEFAULT_MIN_STRENGTH = 0.001

    def __init__(
        self,
        confirmation_bars: int = DEFAULT_CONFIRMATION_BARS,
        min_strength_ratio: float = DEFAULT_MIN_STRENGTH,
    ):
        """Initialize BOS/CHoCH classifier.

        Args:
            confirmation_bars: Bars needed to confirm break (default: 1)
            min_strength_ratio: Minimum strength ratio (default: 0.001 = 0.1%)
        """
        if confirmation_bars < 0:
            raise ValueError(
                f"confirmation_bars must be non-negative, got {confirmation_bars}"
            )
        if min_strength_ratio < 0:
            raise ValueError(
                f"min_strength_ratio must be non-negative, got {min_strength_ratio}"
            )

        self.confirmation_bars = confirmation_bars
        self.min_strength_ratio = min_strength_ratio

    def classify(
        self,
        pivot_result: SwingPivotDetectionResult,
        data: list[OHLCVData],
    ) -> BOSCHoCHClassificationResult:
        """Classify BOS and CHoCH events from swing pivots.

        Implements the design doc algorithm:
        1. Build structure levels from swing pivots
        2. For each candle, check if close exceeds active structure levels
        3. Classify break as BOS or CHoCH based on trend direction
        4. Update state on BOS detection

        BOS (Break of Structure): Break in SAME direction as trend.
        CHoCH (Change of Character): Break in OPPOSITE direction of trend.
        BOS takes priority over CHoCH when both could apply.

        Args:
            pivot_result: Result from SwingPivotDetector
            data: Original OHLCV data

        Returns:
            BOSCHoCHClassificationResult with all events and current structure
        """
        if not pivot_result.pivots or len(pivot_result.pivots) < 2:
            return self._empty_result()

        events: list[BOSCHoCH] = []
        bullish_bos: list[BOSCHoCH] = []
        bearish_bos: list[BOSCHoCH] = []
        bullish_choch: list[BOSCHoCH] = []
        bearish_choch: list[BOSCHoCH] = []

        # Track active structure levels (updated per design doc algorithm)
        active_structure_high: StructureLevel | None = None
        active_structure_low: StructureLevel | None = None

        # Track current trend direction (UNDEFINED initially)
        trend_direction: TrendDirection = TrendDirection.UNDEFINED

        # Track last BOS direction for backwards compatibility
        last_bos_dir: str | None = None

        # Track detected break pairs to avoid duplicates
        detected_breaks: set[tuple[int, int]] = set()

        swings = pivot_result.pivots

        for i in range(1, len(swings)):
            current = swings[i]
            candle = data[current.index]

            # Determine if this swing breaks the active structure level
            break_detected = False

            if current.pivot_type.value == "swing_high":
                # Check bullish break against active structure high
                if active_structure_high is not None:
                    if self._is_level_broken(
                        current, active_structure_high.pivot, data, is_bullish=True
                    ):
                        strength = self._calculate_strength(
                            candle.close_price,
                            active_structure_high.price,
                            is_bullish=True,
                        )
                        if strength >= self.min_strength_ratio:
                            # Determine BOS vs CHoCH based on trend
                            if trend_direction == TrendDirection.BULLISH:
                                # Break of structure in bullish direction = BOS
                                event_type = BOSCHoCHType.BULLISH_BOS
                                is_bos = True
                                new_trend = TrendDirection.BULLISH
                            elif trend_direction == TrendDirection.UNDEFINED:
                                # No established trend - treat as BOS (first break)
                                event_type = BOSCHoCHType.BULLISH_BOS
                                is_bos = True
                                new_trend = TrendDirection.BULLISH
                            else:
                                # trend_direction == BEARISH
                                # Break of structure against bearish trend = CHoCH
                                event_type = BOSCHoCHType.BULLISH_CHOCH
                                is_bos = False
                                new_trend = (
                                    TrendDirection.BULLISH  # CHoCH reverses trend
                                )

                            # Check for duplicate
                            pair = (current.index, active_structure_high.pivot.index)
                            if pair not in detected_breaks:
                                detected_breaks.add(pair)
                                break_detected = True

                                event = BOSCHoCH(
                                    event_type=event_type,
                                    broken_level=active_structure_high,
                                    break_index=current.index,
                                    break_price=candle.close_price,
                                    timestamp=current.timestamp,
                                    confirmation_index=current.index
                                    + self.confirmation_bars,
                                    is_bos=is_bos,
                                    strength=strength,
                                )
                                events.append(event)

                                if is_bos:
                                    bullish_bos.append(event)
                                    last_bos_dir = "bullish"
                                    trend_direction = new_trend
                                    # BOS updates active structure in SAME direction
                                    active_structure_high = StructureLevel(
                                        pivot=current,
                                        price=current.price,
                                    )
                                else:
                                    bullish_choch.append(event)
                                    # CHoCH reverses trend: this swing_high break
                                    # becomes the new structure high
                                    active_structure_high = StructureLevel(
                                        pivot=current,
                                        price=current.price,
                                    )
                                    trend_direction = new_trend

                # Update active structure high if no break (per design doc)
                if not break_detected:
                    if (
                        active_structure_high is None
                        or current.price > active_structure_high.price
                    ):
                        active_structure_high = StructureLevel(
                            pivot=current,
                            price=current.price,
                        )

            elif current.pivot_type.value == "swing_low":
                # Check bearish break against active structure low
                if active_structure_low is not None:
                    if self._is_level_broken(
                        current, active_structure_low.pivot, data, is_bullish=False
                    ):
                        strength = self._calculate_strength(
                            candle.close_price,
                            active_structure_low.price,
                            is_bullish=False,
                        )
                        if strength >= self.min_strength_ratio:
                            # Determine BOS vs CHoCH based on trend
                            if trend_direction == TrendDirection.BEARISH:
                                # Break of structure in bearish direction = BOS
                                event_type = BOSCHoCHType.BEARISH_BOS
                                is_bos = True
                                new_trend = TrendDirection.BEARISH
                            elif trend_direction == TrendDirection.UNDEFINED:
                                # No established trend - treat as BOS (first break)
                                event_type = BOSCHoCHType.BEARISH_BOS
                                is_bos = True
                                new_trend = TrendDirection.BEARISH
                            else:
                                # trend_direction == BULLISH
                                # Break of structure against bullish trend = CHoCH
                                event_type = BOSCHoCHType.BEARISH_CHOCH
                                is_bos = False
                                new_trend = (
                                    TrendDirection.BEARISH  # CHoCH reverses trend
                                )

                            # Check for duplicate
                            pair = (current.index, active_structure_low.pivot.index)
                            if pair not in detected_breaks:
                                detected_breaks.add(pair)
                                break_detected = True

                                event = BOSCHoCH(
                                    event_type=event_type,
                                    broken_level=active_structure_low,
                                    break_index=current.index,
                                    break_price=candle.close_price,
                                    timestamp=current.timestamp,
                                    confirmation_index=current.index
                                    + self.confirmation_bars,
                                    is_bos=is_bos,
                                    strength=strength,
                                )
                                events.append(event)

                                if is_bos:
                                    bearish_bos.append(event)
                                    last_bos_dir = "bearish"
                                    trend_direction = new_trend
                                    # BOS updates active structure in SAME direction
                                    active_structure_low = StructureLevel(
                                        pivot=current,
                                        price=current.price,
                                    )
                                else:
                                    bearish_choch.append(event)
                                    # CHoCH reverses trend: this swing_low break
                                    # becomes the new structure low
                                    active_structure_low = StructureLevel(
                                        pivot=current,
                                        price=current.price,
                                    )
                                    trend_direction = new_trend

                # Update active structure low if no break (per design doc)
                if not break_detected:
                    if (
                        active_structure_low is None
                        or current.price < active_structure_low.price
                    ):
                        active_structure_low = StructureLevel(
                            pivot=current,
                            price=current.price,
                        )

        return BOSCHoCHClassificationResult(
            events=events,
            bullish_bos_events=bullish_bos,
            bearish_bos_events=bearish_bos,
            bullish_choch_events=bullish_choch,
            bearish_choch_events=bearish_choch,
            current_structure_high=active_structure_high,
            current_structure_low=active_structure_low,
            last_bos_direction=last_bos_dir,
            trend_direction=trend_direction,
        )

    def _check_bullish_break(
        self,
        swing: SwingPivot,
        prev_swings: list[SwingPivot],
        data: list[OHLCVData],
    ) -> tuple[BOSCHoCH, bool] | None:
        """Check if a bullish break (BOS or CHoCH) occurred.

        BOS takes priority over CHoCH - if both are detected, BOS is returned.
        This ensures the trend direction is preserved when structure breaks.

        Returns:
            Tuple of (event, is_bos) or None if no break
        """
        # Collect all candidates to prioritize BOS over CHoCH
        bos_candidates: list[tuple[SwingPivot, float]] = []
        choch_candidates: list[tuple[SwingPivot, float]] = []

        for prev in prev_swings:
            if prev.pivot_type.value == "swing_high":
                # BOS: swing_high breaks a previous swing_high level
                if self._is_level_broken(swing, prev, data, is_bullish=True):
                    break_price = data[swing.index].close_price
                    strength = self._calculate_strength(
                        break_price, prev.price, is_bullish=True
                    )
                    if strength >= self.min_strength_ratio:
                        bos_candidates.append((prev, strength))

            elif prev.pivot_type.value == "swing_low":
                # CHoCH: swing_high breaks a previous swing_low level
                if self._is_level_broken(swing, prev, data, is_bullish=True):
                    break_price = data[swing.index].close_price
                    strength = self._calculate_strength(
                        break_price, prev.price, is_bullish=True
                    )
                    if strength >= self.min_strength_ratio:
                        choch_candidates.append((prev, strength))

        # Return most recent BOS candidate if available (BOS has priority)
        if bos_candidates:
            # bos_candidates are already in chronological order (prev_swings order)
            # The last one added is the most recent
            most_recent = bos_candidates[-1]
            prev, strength = most_recent
            event = BOSCHoCH(
                event_type=BOSCHoCHType.BULLISH_BOS,
                broken_level=StructureLevel(pivot=prev, price=prev.price),
                break_index=swing.index,
                break_price=data[swing.index].close_price,
                timestamp=swing.timestamp,
                confirmation_index=swing.index + self.confirmation_bars,
                is_bos=True,
                strength=strength,
            )
            return (event, True)

        # Return most recent CHoCH candidate
        if choch_candidates:
            most_recent = choch_candidates[-1]
            prev, strength = most_recent
            event = BOSCHoCH(
                event_type=BOSCHoCHType.BULLISH_CHOCH,
                broken_level=StructureLevel(pivot=prev, price=prev.price),
                break_index=swing.index,
                break_price=data[swing.index].close_price,
                timestamp=swing.timestamp,
                confirmation_index=swing.index + self.confirmation_bars,
                is_bos=False,
                strength=strength,
            )
            return (event, False)

        return None

    def _check_bearish_break(
        self,
        swing: SwingPivot,
        prev_swings: list[SwingPivot],
        data: list[OHLCVData],
    ) -> tuple[BOSCHoCH, bool] | None:
        """Check if a bearish break (BOS or CHoCH) occurred.

        BOS takes priority over CHoCH - if both are detected, BOS is returned.
        This ensures the trend direction is preserved when structure breaks.

        Returns:
            Tuple of (event, is_bos) or None if no break
        """
        # Collect all candidates to prioritize BOS over CHoCH
        bos_candidates: list[tuple[SwingPivot, float]] = []
        choch_candidates: list[tuple[SwingPivot, float]] = []

        for prev in prev_swings:
            if prev.pivot_type.value == "swing_low":
                # BOS: swing_low breaks a previous swing_low level
                if self._is_level_broken(swing, prev, data, is_bullish=False):
                    break_price = data[swing.index].close_price
                    strength = self._calculate_strength(
                        break_price, prev.price, is_bullish=False
                    )
                    if strength >= self.min_strength_ratio:
                        bos_candidates.append((prev, strength))

            elif prev.pivot_type.value == "swing_high":
                # CHoCH: swing_low breaks a previous swing_high level
                if self._is_level_broken(swing, prev, data, is_bullish=False):
                    break_price = data[swing.index].close_price
                    strength = self._calculate_strength(
                        break_price, prev.price, is_bullish=False
                    )
                    if strength >= self.min_strength_ratio:
                        choch_candidates.append((prev, strength))

        # Return most recent BOS candidate if available (BOS has priority)
        if bos_candidates:
            most_recent = bos_candidates[-1]
            prev, strength = most_recent
            event = BOSCHoCH(
                event_type=BOSCHoCHType.BEARISH_BOS,
                broken_level=StructureLevel(pivot=prev, price=prev.price),
                break_index=swing.index,
                break_price=data[swing.index].close_price,
                timestamp=swing.timestamp,
                confirmation_index=swing.index + self.confirmation_bars,
                is_bos=True,
                strength=strength,
            )
            return (event, True)

        # Return most recent CHoCH candidate
        if choch_candidates:
            most_recent = choch_candidates[-1]
            prev, strength = most_recent
            event = BOSCHoCH(
                event_type=BOSCHoCHType.BEARISH_CHOCH,
                broken_level=StructureLevel(pivot=prev, price=prev.price),
                break_index=swing.index,
                break_price=data[swing.index].close_price,
                timestamp=swing.timestamp,
                confirmation_index=swing.index + self.confirmation_bars,
                is_bos=False,
                strength=strength,
            )
            return (event, False)

        return None

    def _is_level_broken(
        self,
        swing: SwingPivot,
        level: SwingPivot,
        data: list[OHLCVData],
        is_bullish: bool,
    ) -> bool:
        """Check if a structure level was broken by a swing.

        A level is considered broken if:
        1. The swing candle's price (high for swing_high, low for swing_low)
           is beyond the level price, AND
        2. The swing candle's close is also beyond the level price

        This dual confirmation prevents false breaks where only the wick
        penetrates the level.

        Args:
            swing: The swing that potentially breaks the level
            level: The structure level (swing high or low)
            data: OHLCV data
            is_bullish: True for bullish break, False for bearish

        Returns:
            True if level was broken with candle close confirmation
        """
        # Validate indices are within bounds
        if level.index < 0 or level.index >= len(data):
            return False
        if swing.index < level.index or swing.index >= len(data):
            return False

        # Get the level price to break
        level_price = level.price

        # Get the swing candle
        swing_candle = data[swing.index]

        # Check if swing candle price and close are beyond the level
        if is_bullish:
            # For bullish break: swing high and close must be ABOVE the level
            if (
                swing_candle.high_price > level_price
                and swing_candle.close_price > level_price
            ):
                return True
        else:
            # For bearish break: swing low and close must be BELOW the level
            if (
                swing_candle.low_price < level_price
                and swing_candle.close_price < level_price
            ):
                return True

        return False

    def _calculate_strength(
        self,
        break_price: float,
        level_price: float,
        is_bullish: bool,
    ) -> float:
        """Calculate the strength ratio of a break.

        Args:
            break_price: Price at which break occurred
            level_price: Price of the broken level
            is_bullish: True for bullish break

        Returns:
            Strength ratio as a fraction
        """
        if level_price == 0:
            return 0.0

        if is_bullish:
            # For bullish: how much higher did we break above the level
            return (break_price - level_price) / level_price
        else:
            # For bearish: how much lower did we break below the level
            return (level_price - break_price) / level_price

    def _empty_result(self) -> BOSCHoCHClassificationResult:
        """Create an empty result when insufficient data."""
        return BOSCHoCHClassificationResult(
            events=[],
            bullish_bos_events=[],
            bearish_bos_events=[],
            bullish_choch_events=[],
            bearish_choch_events=[],
            current_structure_high=None,
            current_structure_low=None,
            last_bos_direction=None,
            trend_direction=TrendDirection.UNDEFINED,
        )

    def get_metadata(self) -> dict[str, Any]:
        """Get classifier metadata for serialization.

        Returns:
            Dictionary with name, description, parameters
        """
        return {
            "name": "BOSCHoCHClassifier",
            "description": "Break of Structure and Change of Character classification",
            "parameters": {
                "confirmation_bars": self.confirmation_bars,
                "min_strength_ratio": self.min_strength_ratio,
            },
        }
