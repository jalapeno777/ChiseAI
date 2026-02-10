"""Position sizing types and enums.

This module contains type definitions to avoid circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class SizingMethod(Enum):
    """Available position sizing methods."""

    KELLY_CRITERION = auto()
    FIXED_FRACTIONAL = auto()
    VOLATILITY_BASED = auto()


@dataclass(frozen=True)
class PositionSizeResult:
    """Result of position size calculation.

    Attributes:
        position_size: Number of contracts/units to trade
        notional_value: Total notional value of the position in USD
        risk_amount: Maximum risk amount in USD
        risk_percentage: Risk as percentage of account
        method_used: Which sizing method was used
        leverage_used: Leverage applied to the position
        capped_by_limit: Whether position was capped by max limits
        metadata: Additional calculation details
    """

    position_size: float
    notional_value: float
    risk_amount: float
    risk_percentage: float
    method_used: SizingMethod
    leverage_used: float
    capped_by_limit: bool = False
    metadata: dict[str, float | str | None] | None = None


@dataclass(frozen=True)
class KellyInputs:
    """Inputs for Kelly Criterion calculation.

    Attributes:
        win_probability: Probability of winning (0-1)
        win_loss_ratio: Average win amount / average loss amount (b in Kelly formula)
    """

    win_probability: float
    win_loss_ratio: float

    def __post_init__(self) -> None:
        """Validate inputs."""
        if not 0 <= self.win_probability <= 1:
            raise ValueError("win_probability must be between 0 and 1")
        if self.win_loss_ratio <= 0:
            raise ValueError("win_loss_ratio must be positive")


@dataclass(frozen=True)
class VolatilityInputs:
    """Inputs for volatility-based sizing.

    Attributes:
        atr_value: Average True Range value
        atr_multiplier: Multiplier for stop distance (default: 2.0)
        volatility_percent: Current volatility as percentage (optional)
    """

    atr_value: float
    atr_multiplier: float = 2.0
    volatility_percent: float | None = None

    def __post_init__(self) -> None:
        """Validate inputs."""
        if self.atr_value < 0:
            raise ValueError("atr_value must be non-negative")
        if self.atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be positive")


@dataclass
class SizingConfig:
    """Configuration for position sizing calculations.

    Attributes:
        max_risk_per_trade_pct: Maximum risk per trade (default: 1.0%)
        max_risk_per_grid_pct: Maximum risk per grid (default: 2.0%)
        max_leverage: Maximum allowed leverage (default: 3.0x)
        default_risk_pct: Default risk percentage for fixed fractional (default: 1.0%)
        kelly_fraction: Fraction of full Kelly to use (default: 0.25 for quarter Kelly)
        min_position_size: Minimum position size (default: 0.0)
        max_position_size_pct: Max position as % of portfolio (default: 50.0%)
        tick_value: Value per tick/contract (default: 1.0)
    """

    max_risk_per_trade_pct: float = 1.0  # 1% per-trade risk limit
    max_risk_per_grid_pct: float = 2.0  # 2% per-grid worst-case
    max_leverage: float = 3.0  # Max 3x leverage per PRD
    default_risk_pct: float = 1.0  # Default 1-2% risk
    kelly_fraction: float = 0.25  # Quarter Kelly for safety
    min_position_size: float = 0.0
    max_position_size_pct: float = 50.0  # Max 50% of portfolio in one position
    tick_value: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 < self.max_risk_per_trade_pct <= 100:
            raise ValueError("max_risk_per_trade_pct must be between 0 and 100")
        if not 0 < self.max_risk_per_grid_pct <= 100:
            raise ValueError("max_risk_per_grid_pct must be between 0 and 100")
        if not self.max_leverage > 0:
            raise ValueError("max_leverage must be positive")
        if not 0 < self.kelly_fraction <= 1:
            raise ValueError("kelly_fraction must be between 0 and 1")
        # tick_value validation: must be positive and within reasonable range
        if self.tick_value <= 0:
            raise ValueError("tick_value must be positive")
        if self.tick_value > 1_000_000:
            raise ValueError("tick_value exceeds maximum allowed value (1,000,000)")
