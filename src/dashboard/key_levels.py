"""Key levels identification for pre-market briefing.

Identifies support and resistance levels from multiple timeframes,
including pivot points, round numbers, and confluence detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


class LevelType(Enum):
    """Type of key level."""

    SUPPORT = "support"
    RESISTANCE = "resistance"
    PIVOT = "pivot"
    ROUND_NUMBER = "round_number"


@dataclass
class KeyLevel:
    """A single key level (support/resistance/pivot).

    Attributes:
        price: Price level
        level_type: Type of level (support/resistance/pivot/round)
        strength: Strength score (0-100) based on touches and timeframe
        timeframes: List of timeframes where this level appears
        touches: Number of times price touched this level
        confluence_score: Confluence score (0-100) for multiple timeframe alignment
        description: Human-readable description
    """

    price: float
    level_type: LevelType
    strength: float
    timeframes: list[str] = field(default_factory=list)
    touches: int = 0
    confluence_score: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.strength = max(0.0, min(100.0, self.strength))
        self.confluence_score = max(0.0, min(100.0, self.confluence_score))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "price": round(self.price, 2),
            "level_type": self.level_type.value,
            "strength": round(self.strength, 1),
            "timeframes": self.timeframes,
            "touches": self.touches,
            "confluence_score": round(self.confluence_score, 1),
            "description": self.description,
        }


@dataclass
class KeyLevelsResult:
    """Result of key levels analysis.

    Attributes:
        token: Trading pair
        support_levels: List of support levels (sorted by strength)
        resistance_levels: List of resistance levels (sorted by strength)
        pivot_levels: List of pivot levels
        round_levels: List of round number levels
        current_price: Current market price
        nearest_support: Nearest support level below current price
        nearest_resistance: Nearest resistance level above current price
    """

    token: str
    support_levels: list[KeyLevel] = field(default_factory=list)
    resistance_levels: list[KeyLevel] = field(default_factory=list)
    pivot_levels: list[KeyLevel] = field(default_factory=list)
    round_levels: list[KeyLevel] = field(default_factory=list)
    current_price: float = 0.0
    nearest_support: KeyLevel | None = None
    nearest_resistance: KeyLevel | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "token": self.token,
            "current_price": round(self.current_price, 2),
            "support_levels": [level.to_dict() for level in self.support_levels[:5]],
            "resistance_levels": [
                level.to_dict() for level in self.resistance_levels[:5]
            ],
            "pivot_levels": [level.to_dict() for level in self.pivot_levels[:3]],
            "round_levels": [level.to_dict() for level in self.round_levels[:3]],
            "nearest_support": (
                self.nearest_support.to_dict() if self.nearest_support else None
            ),
            "nearest_resistance": (
                self.nearest_resistance.to_dict() if self.nearest_resistance else None
            ),
        }


class KeyLevelsAnalyzer:
    """Analyzer for identifying key support/resistance levels.

    Identifies key levels from multiple timeframes:
    - Pivot points (previous period high/low/close)
    - Swing highs/lows
    - Round numbers (psychological levels)
    - Confluence detection across timeframes
    """

    def __init__(
        self,
        swing_lookback: int = 5,
        touch_threshold_pct: float = 0.5,
        round_number_step: float = 1000.0,
    ):
        """Initialize analyzer.

        Args:
            swing_lookback: Lookback period for swing detection (default: 5)
            touch_threshold_pct: Price proximity threshold for level touches
                (default: 0.5%)
            round_number_step: Step size for round numbers (default: 1000)
        """
        self.swing_lookback = swing_lookback
        self.touch_threshold_pct = touch_threshold_pct
        self.round_number_step = round_number_step

    def analyze(
        self,
        token: str,
        timeframe_data: dict[str, list[OHLCVData]],
        current_price: float,
    ) -> KeyLevelsResult:
        """Analyze key levels across multiple timeframes.

        Args:
            token: Trading pair
            timeframe_data: Map of timeframe -> OHLCV data
            current_price: Current market price

        Returns:
            KeyLevelsResult with all identified levels
        """
        all_levels: list[KeyLevel] = []

        for timeframe, data in timeframe_data.items():
            if not data or len(data) < 10:
                continue

            # Find pivot levels
            pivot_levels = self._find_pivot_levels(data, timeframe)
            all_levels.extend(pivot_levels)

            # Find swing levels
            swing_levels = self._find_swing_levels(data, timeframe)
            all_levels.extend(swing_levels)

        # Add round number levels
        round_levels = self._find_round_numbers(current_price)
        all_levels.extend(round_levels)

        # Merge nearby levels and calculate confluence
        merged_levels = self._merge_levels(all_levels, current_price)

        # Classify levels as support/resistance
        support_levels = []
        resistance_levels = []
        pivot_levels = []
        round_levels_out = []

        for level in merged_levels:
            if level.level_type == LevelType.PIVOT:
                pivot_levels.append(level)
            elif level.level_type == LevelType.ROUND_NUMBER:
                round_levels_out.append(level)
            elif level.price < current_price:
                level.level_type = LevelType.SUPPORT
                support_levels.append(level)
            else:
                level.level_type = LevelType.RESISTANCE
                resistance_levels.append(level)

        # Sort by strength (descending)
        support_levels.sort(key=lambda x: x.strength, reverse=True)
        resistance_levels.sort(key=lambda x: x.strength, reverse=True)
        pivot_levels.sort(key=lambda x: x.strength, reverse=True)
        round_levels_out.sort(key=lambda x: x.strength, reverse=True)

        # Find nearest support and resistance
        nearest_support = self._find_nearest_support(support_levels, current_price)
        nearest_resistance = self._find_nearest_resistance(
            resistance_levels, current_price
        )

        return KeyLevelsResult(
            token=token,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            pivot_levels=pivot_levels,
            round_levels=round_levels_out,
            current_price=current_price,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
        )

    def _find_pivot_levels(
        self,
        data: list[OHLCVData],
        timeframe: str,
    ) -> list[KeyLevel]:
        """Find pivot levels from previous period high/low/close.

        Args:
            data: OHLCV data
            timeframe: Timeframe string

        Returns:
            List of pivot levels
        """
        if len(data) < 2:
            return []

        # Use previous period's high, low, close as pivot levels
        prev_period = data[-2]  # Second to last candle

        levels = []

        # Previous high as resistance
        levels.append(
            KeyLevel(
                price=prev_period.high_price,
                level_type=LevelType.PIVOT,
                strength=70.0,
                timeframes=[timeframe],
                touches=1,
                description=f"Previous {timeframe} high",
            )
        )

        # Previous low as support
        levels.append(
            KeyLevel(
                price=prev_period.low_price,
                level_type=LevelType.PIVOT,
                strength=70.0,
                timeframes=[timeframe],
                touches=1,
                description=f"Previous {timeframe} low",
            )
        )

        # Previous close as pivot
        levels.append(
            KeyLevel(
                price=prev_period.close_price,
                level_type=LevelType.PIVOT,
                strength=60.0,
                timeframes=[timeframe],
                touches=1,
                description=f"Previous {timeframe} close",
            )
        )

        return levels

    def _find_swing_levels(
        self,
        data: list[OHLCVData],
        timeframe: str,
    ) -> list[KeyLevel]:
        """Find swing high/low levels.

        Args:
            data: OHLCV data
            timeframe: Timeframe string

        Returns:
            List of swing levels
        """
        if len(data) < self.swing_lookback * 2 + 1:
            return []

        levels = []
        lookback = self.swing_lookback

        # Find swing highs and lows
        for i in range(lookback, len(data) - lookback):
            # Check for swing high
            is_swing_high = all(
                data[i].high_price >= data[j].high_price
                for j in range(i - lookback, i + lookback + 1)
                if j != i
            )

            if is_swing_high:
                # Calculate strength based on recency
                recency_factor = i / len(data)
                strength = 50.0 + (recency_factor * 30.0)

                levels.append(
                    KeyLevel(
                        price=data[i].high_price,
                        level_type=LevelType.RESISTANCE,
                        strength=strength,
                        timeframes=[timeframe],
                        touches=1,
                        description=f"Swing high on {timeframe}",
                    )
                )

            # Check for swing low
            is_swing_low = all(
                data[i].low_price <= data[j].low_price
                for j in range(i - lookback, i + lookback + 1)
                if j != i
            )

            if is_swing_low:
                # Calculate strength based on recency
                recency_factor = i / len(data)
                strength = 50.0 + (recency_factor * 30.0)

                levels.append(
                    KeyLevel(
                        price=data[i].low_price,
                        level_type=LevelType.SUPPORT,
                        strength=strength,
                        timeframes=[timeframe],
                        touches=1,
                        description=f"Swing low on {timeframe}",
                    )
                )

        return levels

    def _find_round_numbers(self, current_price: float) -> list[KeyLevel]:
        """Find psychological round number levels.

        Args:
            current_price: Current market price

        Returns:
            List of round number levels
        """
        levels = []

        # Adjust step size based on price magnitude
        if current_price >= 50000:
            step = 1000.0
        elif current_price >= 10000:
            step = 500.0
        elif current_price >= 1000:
            step = 100.0
        elif current_price >= 100:
            step = 10.0
        else:
            step = 1.0

        # Find round numbers around current price
        center = round(current_price / step) * step

        for offset in [-2, -1, 0, 1, 2]:
            price = center + (offset * step)
            if price > 0:
                # Strength decreases with distance from current price
                distance = abs(price - current_price) / current_price * 100
                strength = max(20.0, 60.0 - distance * 5)

                levels.append(
                    KeyLevel(
                        price=price,
                        level_type=LevelType.ROUND_NUMBER,
                        strength=strength,
                        timeframes=["all"],
                        touches=0,
                        description=f"Round number ({step:.0f}s)",
                    )
                )

        return levels

    def _merge_levels(
        self,
        levels: list[KeyLevel],
        current_price: float,
    ) -> list[KeyLevel]:
        """Merge nearby levels and calculate confluence.

        Args:
            levels: List of raw levels
            current_price: Current market price for proximity calculation

        Returns:
            List of merged levels with confluence scores
        """
        if not levels:
            return []

        # Sort by price
        sorted_levels = sorted(levels, key=lambda x: x.price)

        merged: list[KeyLevel] = []
        threshold_pct = self.touch_threshold_pct / 100

        for level in sorted_levels:
            # Check if this level is close to an existing merged level
            found_match = False
            for merged_level in merged:
                price_diff = abs(level.price - merged_level.price) / current_price

                if price_diff < threshold_pct:
                    # Merge with existing level
                    merged_level.touches += level.touches
                    merged_level.timeframes = list(
                        set(merged_level.timeframes + level.timeframes)
                    )
                    merged_level.strength = min(
                        100.0, merged_level.strength + level.strength * 0.5
                    )

                    # Increase confluence score for multiple timeframe alignment
                    tf_count = len(merged_level.timeframes)
                    merged_level.confluence_score = min(100.0, tf_count * 25.0)

                    found_match = True
                    break

            if not found_match:
                # Add as new level
                level.confluence_score = min(100.0, len(level.timeframes) * 25.0)
                merged.append(level)

        # Re-sort by strength
        merged.sort(key=lambda x: x.strength + x.confluence_score, reverse=True)

        return merged

    def _find_nearest_support(
        self,
        support_levels: list[KeyLevel],
        current_price: float,
    ) -> KeyLevel | None:
        """Find the nearest support level below current price.

        Args:
            support_levels: List of support levels
            current_price: Current market price

        Returns:
            Nearest support level or None
        """
        valid_supports = [s for s in support_levels if s.price < current_price]
        if not valid_supports:
            return None

        return min(valid_supports, key=lambda x: current_price - x.price)

    def _find_nearest_resistance(
        self,
        resistance_levels: list[KeyLevel],
        current_price: float,
    ) -> KeyLevel | None:
        """Find the nearest resistance level above current price.

        Args:
            resistance_levels: List of resistance levels
            current_price: Current market price

        Returns:
            Nearest resistance level or None
        """
        valid_resistances = [r for r in resistance_levels if r.price > current_price]
        if not valid_resistances:
            return None

        return min(valid_resistances, key=lambda x: x.price - current_price)
