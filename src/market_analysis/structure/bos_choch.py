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
from datetime import UTC, datetime
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
    """

    events: list[BOSCHoCH]
    bullish_bos_events: list[BOSCHoCH]
    bearish_bos_events: list[BOSCHoCH]
    bullish_choch_events: list[BOSCHoCH]
    bearish_choch_events: list[BOSCHoCH]
    current_structure_high: StructureLevel | None
    current_structure_low: StructureLevel | None
    last_bos_direction: str | None


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

        # Track current structure levels
        current_high: StructureLevel | None = None
        current_low: StructureLevel | None = None
        last_bos_dir: str | None = None

        # Get swings in order
        swings = pivot_result.pivots

        for i in range(1, len(swings)):
            prev_swings = swings[:i]
            current_swings = swings[i:]

            # Check for breaks
            for current in current_swings:
                if current.pivot_type.value == "swing_high":
                    # Check if this breaks a previous swing high (BOS in uptrend)
                    # or breaks a previous swing low (CHoCH)
                    break_result = self._check_bullish_break(current, prev_swings, data)
                    if break_result is not None:
                        event, is_bos = break_result
                        events.append(event)
                        if event.event_type == BOSCHoCHType.BULLISH_BOS:
                            bullish_bos.append(event)
                            last_bos_dir = "bullish"
                            # Update structure high
                            current_high = StructureLevel(
                                pivot=current,
                                price=current.price,
                            )
                        else:
                            bullish_choch.append(event)
                            # CHoCH updates structure in opposite direction
                            current_low = StructureLevel(
                                pivot=current,
                                price=current.price,
                            )

                elif current.pivot_type.value == "swing_low":
                    # Check if this breaks a previous swing low (BOS in downtrend)
                    # or breaks a previous swing high (CHoCH)
                    break_result = self._check_bearish_break(current, prev_swings, data)
                    if break_result is not None:
                        event, is_bos = break_result
                        events.append(event)
                        if event.event_type == BOSCHoCHType.BEARISH_BOS:
                            bearish_bos.append(event)
                            last_bos_dir = "bearish"
                            # Update structure low
                            current_low = StructureLevel(
                                pivot=current,
                                price=current.price,
                            )
                        else:
                            bearish_choch.append(event)
                            # CHoCH updates structure in opposite direction
                            current_high = StructureLevel(
                                pivot=current,
                                price=current.price,
                            )

        return BOSCHoCHClassificationResult(
            events=events,
            bullish_bos_events=bullish_bos,
            bearish_bos_events=bearish_bos,
            bullish_choch_events=bullish_choch,
            bearish_choch_events=bearish_choch,
            current_structure_high=current_high,
            current_structure_low=current_low,
            last_bos_direction=last_bos_dir,
        )

    def _check_bullish_break(
        self,
        swing: SwingPivot,
        prev_swings: list[SwingPivot],
        data: list[OHLCVData],
    ) -> tuple[BOSCHoCH, bool] | None:
        """Check if a bullish break (BOS or CHoCH) occurred.

        Returns:
            Tuple of (event, is_bos) or None if no break
        """
        # Look for broken structure levels
        for prev in prev_swings:
            if prev.pivot_type.value == "swing_high":
                # This is a bullish break of a previous high = BOS
                if self._is_level_broken(swing, prev, data, is_bullish=True):
                    strength = self._calculate_strength(
                        swing.price, prev.price, is_bullish=True
                    )
                    if strength >= self.min_strength_ratio:
                        event = BOSCHoCH(
                            event_type=BOSCHoCHType.BULLISH_BOS,
                            broken_level=StructureLevel(pivot=prev, price=prev.price),
                            break_index=swing.index,
                            break_price=swing.price,
                            timestamp=swing.timestamp,
                            confirmation_index=swing.index + self.confirmation_bars,
                            is_bos=True,
                            strength=strength,
                        )
                        return (event, True)

            elif prev.pivot_type.value == "swing_low":
                # This is a bullish break of a previous low = CHoCH
                if self._is_level_broken(swing, prev, data, is_bullish=True):
                    strength = self._calculate_strength(
                        swing.price, prev.price, is_bullish=True
                    )
                    if strength >= self.min_strength_ratio:
                        event = BOSCHoCH(
                            event_type=BOSCHoCHType.BULLISH_CHOCH,
                            broken_level=StructureLevel(pivot=prev, price=prev.price),
                            break_index=swing.index,
                            break_price=swing.price,
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

        Returns:
            Tuple of (event, is_bos) or None if no break
        """
        for prev in prev_swings:
            if prev.pivot_type.value == "swing_low":
                # This is a bearish break of a previous low = BOS
                if self._is_level_broken(swing, prev, data, is_bullish=False):
                    strength = self._calculate_strength(
                        prev.price, swing.price, is_bullish=False
                    )
                    if strength >= self.min_strength_ratio:
                        event = BOSCHoCH(
                            event_type=BOSCHoCHType.BEARISH_BOS,
                            broken_level=StructureLevel(pivot=prev, price=prev.price),
                            break_index=swing.index,
                            break_price=swing.price,
                            timestamp=swing.timestamp,
                            confirmation_index=swing.index + self.confirmation_bars,
                            is_bos=True,
                            strength=strength,
                        )
                        return (event, True)

            elif prev.pivot_type.value == "swing_high":
                # This is a bearish break of a previous high = CHoCH
                if self._is_level_broken(swing, prev, data, is_bullish=False):
                    strength = self._calculate_strength(
                        prev.price, swing.price, is_bullish=False
                    )
                    if strength >= self.min_strength_ratio:
                        event = BOSCHoCH(
                            event_type=BOSCHoCHType.BEARISH_CHOCH,
                            broken_level=StructureLevel(pivot=prev, price=prev.price),
                            break_index=swing.index,
                            break_price=swing.price,
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

        Args:
            swing: The swing that potentially breaks the level
            level: The structure level (swing high or low)
            data: OHLCV data
            is_bullish: True for bullish break, False for bearish

        Returns:
            True if level was broken
        """
        # For bullish break: current swing low breaks a previous swing low
        # For bearish break: current swing high breaks a previous swing high

        if is_bullish:
            # Bullish break: swing low must be below previous swing low
            if swing.pivot_type.value != "swing_low":
                return False
            return swing.price < level.price
        else:
            # Bearish break: swing high must be above previous swing high
            if swing.pivot_type.value != "swing_high":
                return False
            return swing.price > level.price

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
            # For bullish: how much lower did we go vs level
            return (level_price - break_price) / level_price
        else:
            # For bearish: how much higher did we go vs level
            return (break_price - level_price) / level_price

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
