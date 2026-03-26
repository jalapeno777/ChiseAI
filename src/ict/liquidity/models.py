"""Data models for liquidity sweep detection.

Defines the core data structures used throughout the liquidity analysis
module: sweep direction, liquidity levels, sweep events, and confirmation
signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SweepDirection(Enum):
    """Direction of a liquidity sweep."""

    BULLISH_SWEEP = "bullish_sweep"  # swept below a low, expect reversal up
    BEARISH_SWEEP = "bearish_sweep"  # swept above a high, expect reversal down


class LiquidityLevelType(Enum):
    """Type of liquidity level acting as a sweep target."""

    PREVIOUS_HIGH = "previous_high"
    PREVIOUS_LOW = "previous_low"
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"


@dataclass(frozen=True, slots=True)
class LiquidityLevel:
    """A key price level where liquidity pools accumulate.

    Attributes:
        price: The price level of the liquidity pool.
        level_type: Type of liquidity level (previous high/low, equal highs/lows).
        source_indices: Bar indices that contributed to this level.
        strength: Relative strength (higher = more significant level).
        timestamp_ms: Timestamp of the most recent contributing bar.
    """

    price: float
    level_type: LiquidityLevelType
    source_indices: tuple[int, ...]
    strength: float = 1.0
    timestamp_ms: int = 0

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"LiquidityLevel price must be positive, got {self.price}")
        if self.strength <= 0:
            raise ValueError(
                f"LiquidityLevel strength must be positive, got {self.strength}"
            )


@dataclass(frozen=True, slots=True)
class SweepConfirmation:
    """Confirmation details for a detected sweep.

    A sweep is confirmed when a rejection candle appears after the sweep
    candle, indicating price has reversed away from the swept level.

    Attributes:
        confirmed: Whether the sweep has been confirmed.
        rejection_candle_index: Index of the candle that confirms rejection.
        wick_ratio: Ratio of the sweep candle's wick to its body.
            Higher values indicate stronger rejection.
        close_beyond_level: Whether the close is back on the correct side
            of the swept level.
    """

    confirmed: bool
    rejection_candle_index: int = -1
    wick_ratio: float = 0.0
    close_beyond_level: bool = False


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    """A detected liquidity sweep event.

    Represents price momentarily exceeding a key level (stop hunt)
    before reversing.

    Attributes:
        sweep_candle_index: Index of the candle that performed the sweep.
        direction: Direction of the sweep (bullish = swept low, bearish = swept high).
        level: The liquidity level that was swept.
        sweep_high: The extreme price reached during the sweep.
        sweep_low: The extreme price reached during the sweep.
        penetration: How far price exceeded the level (absolute).
        penetration_pct: How far price exceeded the level (percentage).
        confirmation: Rejection candle confirmation details.
    """

    sweep_candle_index: int
    direction: SweepDirection
    level: LiquidityLevel
    sweep_high: float
    sweep_low: float
    penetration: float
    penetration_pct: float
    confirmation: SweepConfirmation = field(
        default_factory=lambda: SweepConfirmation(False)
    )

    def __post_init__(self) -> None:
        if self.penetration < 0:
            raise ValueError(
                f"Penetration must be non-negative, got {self.penetration}"
            )
        if self.penetration_pct < 0:
            raise ValueError(
                f"Penetration percentage must be non-negative, got {self.penetration_pct}"
            )


@dataclass
class SweepSignal:
    """Trading signal generated from a confirmed liquidity sweep.

    Attributes:
        sweep: The underlying sweep event.
        signal_direction: Expected price direction after the sweep.
        confidence: Confidence score from 0.0 to 1.0.
        metadata: Additional context about the signal.
    """

    sweep: LiquiditySweep
    signal_direction: SweepDirection
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")
