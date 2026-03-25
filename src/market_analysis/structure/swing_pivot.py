"""Swing Pivot Detection Module.

This module provides swing pivot identification using a window-based algorithm.
A swing high is a bar whose high is higher than surrounding highs within a window.
A swing low is a bar whose low is lower than surrounding lows within a window.

Key concepts:
- Swing High: Price high surrounded by lower highs
- Swing Low: Price low surrounded by higher lows
- Window size: Number of bars on each side to compare

Usage:
    detector = SwingPivotDetector(window_size=5)
    pivots = detector.detect(data)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


class PivotType(Enum):
    """Type of swing pivot."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    NONE = "none"


@dataclass
class SwingPivot:
    """Represents a detected swing pivot point.

    Attributes:
        index: Bar index in the data array
        timestamp: Timestamp of the pivot bar
        pivot_type: Type of pivot (SWING_HIGH or SWING_LOW)
        price: The price level of the pivot (high for swing high, low for swing low)
        strength: Relative strength (ratio of how much it stands out)
        lookback_bars: Number of bars used for lookback
        lookahead_bars: Number of bars used for lookahead
    """

    index: int
    timestamp: datetime
    pivot_type: PivotType
    price: float
    strength: float = 1.0
    lookback_bars: int = 5
    lookahead_bars: int = 5

    def __post_init__(self) -> None:
        """Validate swing pivot data."""
        if self.pivot_type not in (PivotType.SWING_HIGH, PivotType.SWING_LOW):
            raise ValueError(f"Invalid pivot type for SwingPivot: {self.pivot_type}")
        if self.strength < 0:
            raise ValueError(f"Strength must be non-negative, got {self.strength}")


@dataclass
class SwingPivotDetectionResult:
    """Result of swing pivot detection.

    Attributes:
        pivots: List of detected swing pivots (sorted by index)
        swing_highs: List of swing high pivots
        swing_lows: List of swing low pivots
        data_length: Number of bars in input data
        window_size: Window size used for detection
    """

    pivots: list[SwingPivot]
    swing_highs: list[SwingPivot]
    swing_lows: list[SwingPivot]
    data_length: int
    window_size: int

    def __post_init__(self) -> None:
        """Validate result consistency."""
        # Pivots should be sorted by index
        self.pivots = sorted(self.pivots, key=lambda p: p.index)
        self.swing_highs = sorted(self.swing_highs, key=lambda p: p.index)
        self.swing_lows = sorted(self.swing_lows, key=lambda p: p.index)


class SwingPivotDetector:
    """Detector for swing highs and lows using window-based algorithm.

    A bar is identified as a swing high if its high is greater than the highs
    of a specified number of bars before and after it. Similarly for swing lows.

    The algorithm uses a fixed window size on each side, making it deterministic
    and non-repainting (once a swing is confirmed, it won't be invalidated).

    Parameters:
        window_size: Number of bars to check on each side (default: 5)
        min_window_size: Minimum allowed window size (default: 2)
        max_window_size: Maximum allowed window size (default: 20)
    """

    MIN_WINDOW = 2
    MAX_WINDOW = 20
    DEFAULT_WINDOW = 5

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW,
        min_window_size: int = MIN_WINDOW,
        max_window_size: int = MAX_WINDOW,
    ):
        """Initialize swing pivot detector.

        Args:
            window_size: Number of bars to check on each side (default: 5)
            min_window_size: Minimum allowed window size (default: 2)
            max_window_size: Maximum allowed window size (default: 20)

        Raises:
            ValueError: If window_size is out of valid range
        """
        if not min_window_size <= window_size <= max_window_size:
            raise ValueError(
                f"window_size must be between {min_window_size} and {max_window_size}, "
                f"got {window_size}"
            )

        self.window_size = window_size
        self.min_window_size = min_window_size
        self.max_window_size = max_window_size

    def detect(self, data: list[OHLCVData]) -> SwingPivotDetectionResult:
        """Detect all swing pivots in the data.

        Uses a window-based algorithm where a bar is a swing high if its high
        is greater than all highs within the lookback and lookahead windows.
        Similarly for swing lows.

        Args:
            data: List of OHLCV data points

        Returns:
            SwingPivotDetectionResult containing all detected pivots
        """
        if len(data) < self.window_size * 2 + 1:
            # Not enough data for detection
            return SwingPivotDetectionResult(
                pivots=[],
                swing_highs=[],
                swing_lows=[],
                data_length=len(data),
                window_size=self.window_size,
            )

        pivots: list[SwingPivot] = []
        swing_highs: list[SwingPivot] = []
        swing_lows: list[SwingPivot] = []

        # Iterate through data, starting from window_size to avoid edge effects
        for i in range(self.window_size, len(data) - self.window_size):
            current = data[i]
            pivot_type, strength = self._classify_bar(data, i)

            if pivot_type != PivotType.NONE:
                pivot = SwingPivot(
                    index=i,
                    timestamp=(
                        current.timestamp
                        if hasattr(current, "timestamp")
                        else datetime.now(UTC)
                    ),
                    pivot_type=pivot_type,
                    price=(
                        current.high_price
                        if pivot_type == PivotType.SWING_HIGH
                        else current.low_price
                    ),
                    strength=strength,
                    lookback_bars=self.window_size,
                    lookahead_bars=self.window_size,
                )
                pivots.append(pivot)

                if pivot_type == PivotType.SWING_HIGH:
                    swing_highs.append(pivot)
                else:
                    swing_lows.append(pivot)

        return SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            data_length=len(data),
            window_size=self.window_size,
        )

    def _classify_bar(
        self, data: list[OHLCVData], index: int
    ) -> tuple[PivotType, float]:
        """Classify a bar at the given index as swing high, low, or none.

        Args:
            data: List of OHLCV data points
            index: Index of bar to classify

        Returns:
            Tuple of (pivot_type, strength_ratio)
        """
        current = data[index]
        current_high = current.high_price
        current_low = current.low_price

        # Check lookback window
        lookback_highs = [
            data[i].high_price for i in range(index - self.window_size, index)
        ]
        lookback_lows = [
            data[i].low_price for i in range(index - self.window_size, index)
        ]

        # Check lookahead window
        lookahead_highs = [
            data[i].high_price for i in range(index + 1, index + self.window_size + 1)
        ]
        lookahead_lows = [
            data[i].low_price for i in range(index + 1, index + self.window_size + 1)
        ]

        # Determine if swing high
        is_swing_high = current_high > max(lookback_highs) and current_high > max(
            lookahead_highs
        )

        # Determine if swing low
        is_swing_low = current_low < min(lookback_lows) and current_low < min(
            lookahead_lows
        )

        if is_swing_high and not is_swing_low:
            # Calculate strength as ratio above the next best high
            lookback_max = max(lookback_highs)
            lookahead_max = max(lookahead_highs)
            next_best = max(lookback_max, lookahead_max)
            if next_best > 0:
                strength = (current_high - next_best) / next_best
            else:
                strength = 1.0  # Maximum strength if no comparison available
            return PivotType.SWING_HIGH, strength

        if is_swing_low and not is_swing_high:
            # Calculate strength as ratio below the next best low
            lookback_min = min(lookback_lows)
            lookahead_min = min(lookahead_lows)
            next_best = min(lookback_min, lookahead_min)
            if next_best > 0:
                strength = (next_best - current_low) / next_best
            else:
                strength = 1.0
            return PivotType.SWING_LOW, strength

        return PivotType.NONE, 0.0

    def get_last_pivot(self, data: list[OHLCVData]) -> SwingPivot | None:
        """Get the most recent confirmed swing pivot.

        This is useful for real-time analysis where you only care about
        the latest swing structure.

        Args:
            data: List of OHLCV data points

        Returns:
            Most recent SwingPivot or None if no pivots detected
        """
        result = self.detect(data)
        if result.pivots:
            return result.pivots[-1]
        return None

    def get_pivots_since(
        self, data: list[OHLCVData], since_index: int
    ) -> SwingPivotDetectionResult:
        """Get all pivots since a given bar index.

        Useful for incremental analysis when new data arrives.

        Args:
            data: List of OHLCV data points
            since_index: Start looking from this index (inclusive)

        Returns:
            SwingPivotDetectionResult with pivots at or after since_index
        """
        result = self.detect(data)
        filtered_pivots = [p for p in result.pivots if p.index >= since_index]
        filtered_highs = [p for p in result.swing_highs if p.index >= since_index]
        filtered_lows = [p for p in result.swing_lows if p.index >= since_index]

        return SwingPivotDetectionResult(
            pivots=filtered_pivots,
            swing_highs=filtered_highs,
            swing_lows=filtered_lows,
            data_length=result.data_length,
            window_size=result.window_size,
        )

    def validate(self, data: list[OHLCVData]) -> bool:
        """Validate that data is sufficient for pivot detection.

        Args:
            data: List of OHLCV data points

        Returns:
            True if data has enough bars for detection
        """
        return len(data) >= self.window_size * 2 + 1

    def get_metadata(self) -> dict[str, Any]:
        """Get indicator metadata for serialization.

        Returns:
            Dictionary with name, description, parameters
        """
        return {
            "name": "SwingPivotDetector",
            "description": "Window-based swing high/low detection",
            "parameters": {
                "window_size": self.window_size,
                "min_window_size": self.min_window_size,
                "max_window_size": self.max_window_size,
            },
        }
