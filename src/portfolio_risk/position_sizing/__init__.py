"""Position sizing calculation engine.

Provides multiple position sizing methods including Kelly Criterion,
fixed fractional sizing, and volatility-based sizing with risk management
constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

import numpy as np

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


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
        if not 0 < self.max_leverage:
            raise ValueError("max_leverage must be positive")
        if not 0 < self.kelly_fraction <= 1:
            raise ValueError("kelly_fraction must be between 0 and 1")
        # tick_value validation: must be positive and within reasonable range
        if self.tick_value <= 0:
            raise ValueError("tick_value must be positive")
        if self.tick_value > 1_000_000:
            raise ValueError("tick_value exceeds maximum allowed value (1,000,000)")


class PositionSizingEngine:
    """Core engine for position sizing calculations.

    Implements multiple sizing methods with risk management constraints:
    - Kelly Criterion: f* = (bp - q) / b
    - Fixed Fractional: Fixed percentage of account at risk
    - Volatility-Based: Adjust position size based on ATR/volatility

    All methods respect the safety constraints:
    - ≤1% per-trade risk limit
    - ≤2% per-grid worst-case
    - Max 3x leverage
    """

    def __init__(self, config: SizingConfig | None = None):
        """Initialize the sizing engine.

        Args:
            config: Sizing configuration (uses defaults if None)
        """
        self.config = config or SizingConfig()

    def kelly_criterion_sizing(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        kelly_inputs: KellyInputs,
    ) -> PositionSizeResult:
        """Calculate position size using Kelly Criterion.

        The Kelly Criterion formula: f* = (bp - q) / b
        where:
        - b = win/loss ratio (average win / average loss)
        - p = win probability
        - q = 1 - p (loss probability)

        Uses fractional Kelly (default 0.25) for safety.

        Args:
            account_balance: Current account balance in USD
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            kelly_inputs: Kelly Criterion inputs (win probability, win/loss ratio)

        Returns:
            PositionSizeResult with calculated position size
        """
        if account_balance <= 0:
            raise ValueError("account_balance must be positive")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if stop_loss_price <= 0:
            raise ValueError("stop_loss_price must be positive")

        # Calculate Kelly fraction: f* = (bp - q) / b
        p = kelly_inputs.win_probability
        b = kelly_inputs.win_loss_ratio
        q = 1 - p

        kelly_fraction = (b * p - q) / b if b != 0 else 0

        # Kelly fraction can be negative (unfavorable bet) or > 1 (too aggressive)
        # Clamp to reasonable bounds and apply fractional Kelly
        kelly_fraction = max(0.0, min(kelly_fraction, 1.0))
        adjusted_kelly = kelly_fraction * self.config.kelly_fraction

        # Calculate risk amount based on Kelly fraction
        # Limit to max risk per trade
        risk_pct = min(
            adjusted_kelly * 100,
            self.config.max_risk_per_trade_pct,
        )
        risk_amount = account_balance * (risk_pct / 100)

        # Calculate stop distance
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance == 0:
            raise ValueError("stop_loss_price must differ from entry_price")

        # Calculate position size: (Account × Risk%) / (Stop Distance × Tick Value)
        position_size = risk_amount / (stop_distance * self.config.tick_value)
        notional_value = position_size * entry_price

        # Apply leverage
        leverage_used = min(
            notional_value / account_balance,
            self.config.max_leverage,
        )

        # Check if we need to cap by position limits
        max_notional_by_leverage = account_balance * self.config.max_leverage
        max_notional_by_position_pct = (
            account_balance * self.config.max_position_size_pct / 100
        )
        max_notional = min(max_notional_by_leverage, max_notional_by_position_pct)

        capped_by_limit = False
        if notional_value > max_notional:
            notional_value = max_notional
            position_size = notional_value / entry_price
            risk_amount = position_size * stop_distance * self.config.tick_value
            risk_pct = (risk_amount / account_balance) * 100
            # Recalculate leverage_used to reflect actual leverage after capping
            leverage_used = notional_value / account_balance
            capped_by_limit = True

        # Ensure we meet minimum position size
        if position_size < self.config.min_position_size:
            position_size = 0.0
            notional_value = 0.0
            risk_amount = 0.0
            risk_pct = 0.0

        return PositionSizeResult(
            position_size=position_size,
            notional_value=notional_value,
            risk_amount=risk_amount,
            risk_percentage=risk_pct,
            method_used=SizingMethod.KELLY_CRITERION,
            leverage_used=leverage_used,
            capped_by_limit=capped_by_limit,
            metadata={
                "kelly_fraction": kelly_fraction,
                "adjusted_kelly": adjusted_kelly,
                "win_probability": p,
                "win_loss_ratio": b,
                "stop_distance": stop_distance,
            },
        )

    def fixed_fractional_sizing(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percentage: float | None = None,
    ) -> PositionSizeResult:
        """Calculate position size using fixed fractional method.

        Position size = (Account Balance × Risk %) / (Stop Distance × Tick Value)

        Args:
            account_balance: Current account balance in USD
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            risk_percentage: Risk percentage (uses config default if None)

        Returns:
            PositionSizeResult with calculated position size
        """
        if account_balance <= 0:
            raise ValueError("account_balance must be positive")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if stop_loss_price <= 0:
            raise ValueError("stop_loss_price must be positive")

        # Use provided risk percentage or default
        risk_pct = (
            risk_percentage
            if risk_percentage is not None
            else self.config.default_risk_pct
        )

        # Clamp to max risk per trade
        risk_pct = min(risk_pct, self.config.max_risk_per_trade_pct)

        if risk_pct <= 0:
            raise ValueError("risk_percentage must be positive")

        # Calculate risk amount
        risk_amount = account_balance * (risk_pct / 100)

        # Calculate stop distance
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance == 0:
            raise ValueError("stop_loss_price must differ from entry_price")

        # Calculate position size: (Account × Risk%) / (Stop Distance × Tick Value)
        position_size = risk_amount / (stop_distance * self.config.tick_value)
        notional_value = position_size * entry_price

        # Apply leverage constraints
        leverage_used = notional_value / account_balance
        capped_by_limit = False

        if leverage_used > self.config.max_leverage:
            leverage_used = self.config.max_leverage
            notional_value = account_balance * leverage_used
            position_size = notional_value / entry_price
            risk_amount = position_size * stop_distance * self.config.tick_value
            risk_pct = (risk_amount / account_balance) * 100
            capped_by_limit = True

        # Check position size limit
        max_position_value = account_balance * self.config.max_position_size_pct / 100
        if notional_value > max_position_value:
            notional_value = max_position_value
            position_size = notional_value / entry_price
            risk_amount = position_size * stop_distance * self.config.tick_value
            risk_pct = (risk_amount / account_balance) * 100
            # Recalculate leverage_used to reflect actual leverage after capping
            leverage_used = notional_value / account_balance
            capped_by_limit = True

        # Ensure we meet minimum position size
        if position_size < self.config.min_position_size:
            position_size = 0.0
            notional_value = 0.0
            risk_amount = 0.0
            risk_pct = 0.0

        return PositionSizeResult(
            position_size=position_size,
            notional_value=notional_value,
            risk_amount=risk_amount,
            risk_percentage=risk_pct,
            method_used=SizingMethod.FIXED_FRACTIONAL,
            leverage_used=leverage_used,
            capped_by_limit=capped_by_limit,
            metadata={
                "stop_distance": stop_distance,
                "requested_risk_pct": risk_percentage,
            },
        )

    def volatility_based_sizing(
        self,
        account_balance: float,
        entry_price: float,
        volatility_inputs: VolatilityInputs,
        direction: str = "long",
    ) -> PositionSizeResult:
        """Calculate position size based on volatility (ATR).

        Uses ATR to determine stop distance and adjusts position size
        inversely to volatility - higher volatility = smaller position.

        Stop Distance = ATR × ATR Multiplier
        Position Size = (Account × Risk%) / (Stop Distance × Tick Value)

        Args:
            account_balance: Current account balance in USD
            entry_price: Entry price for the trade
            volatility_inputs: Volatility inputs (ATR, multiplier, etc.)
            direction: Trade direction ("long" or "short")

        Returns:
            PositionSizeResult with calculated position size
        """
        if account_balance <= 0:
            raise ValueError("account_balance must be positive")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")

        # Handle zero volatility edge case
        if volatility_inputs.atr_value == 0:
            logger.warning(
                "ATR is zero for volatility-based sizing. Using minimum position size or zero. "
                "This may indicate insufficient price data or a flat market."
            )
            # With zero volatility, use minimum position size or return zero
            if self.config.min_position_size > 0:
                position_size = self.config.min_position_size
                notional_value = position_size * entry_price
                return PositionSizeResult(
                    position_size=position_size,
                    notional_value=notional_value,
                    risk_amount=0.0,
                    risk_percentage=0.0,
                    method_used=SizingMethod.VOLATILITY_BASED,
                    leverage_used=notional_value / account_balance,
                    capped_by_limit=True,
                    metadata={
                        "atr_value": 0.0,
                        "atr_multiplier": volatility_inputs.atr_multiplier,
                        "stop_distance": 0.0,
                        "note": "Zero volatility - using minimum position size",
                    },
                )
            else:
                return PositionSizeResult(
                    position_size=0.0,
                    notional_value=0.0,
                    risk_amount=0.0,
                    risk_percentage=0.0,
                    method_used=SizingMethod.VOLATILITY_BASED,
                    leverage_used=0.0,
                    capped_by_limit=True,
                    metadata={
                        "atr_value": 0.0,
                        "atr_multiplier": volatility_inputs.atr_multiplier,
                        "stop_distance": 0.0,
                        "note": "Zero volatility - no position",
                    },
                )

        # Calculate stop distance from ATR
        stop_distance = volatility_inputs.atr_value * volatility_inputs.atr_multiplier

        # Adjust risk percentage based on volatility regime
        base_risk_pct = self.config.default_risk_pct

        if volatility_inputs.volatility_percent is not None:
            # Reduce position size in high volatility, increase in low volatility
            if volatility_inputs.volatility_percent > 5.0:  # High volatility
                base_risk_pct *= 0.5  # Reduce by 50%
            elif volatility_inputs.volatility_percent < 1.0:  # Low volatility
                base_risk_pct *= 1.2  # Increase by 20%

        # Clamp to max risk per trade
        risk_pct = min(base_risk_pct, self.config.max_risk_per_trade_pct)
        risk_amount = account_balance * (risk_pct / 100)

        # Calculate position size
        position_size = risk_amount / (stop_distance * self.config.tick_value)
        notional_value = position_size * entry_price

        # Calculate stop loss price for reference
        if direction == "long":
            stop_loss_price = entry_price - stop_distance
        else:
            stop_loss_price = entry_price + stop_distance

        # Apply leverage constraints
        leverage_used = notional_value / account_balance
        capped_by_limit = False

        if leverage_used > self.config.max_leverage:
            leverage_used = self.config.max_leverage
            notional_value = account_balance * leverage_used
            position_size = notional_value / entry_price
            risk_amount = position_size * stop_distance * self.config.tick_value
            risk_pct = (risk_amount / account_balance) * 100
            capped_by_limit = True

        # Check position size limit
        max_position_value = account_balance * self.config.max_position_size_pct / 100
        if notional_value > max_position_value:
            notional_value = max_position_value
            position_size = notional_value / entry_price
            risk_amount = position_size * stop_distance * self.config.tick_value
            risk_pct = (risk_amount / account_balance) * 100
            # Recalculate leverage_used to reflect actual leverage after capping
            leverage_used = notional_value / account_balance
            capped_by_limit = True

        # Ensure we meet minimum position size
        if position_size < self.config.min_position_size:
            position_size = 0.0
            notional_value = 0.0
            risk_amount = 0.0
            risk_pct = 0.0

        return PositionSizeResult(
            position_size=position_size,
            notional_value=notional_value,
            risk_amount=risk_amount,
            risk_percentage=risk_pct,
            method_used=SizingMethod.VOLATILITY_BASED,
            leverage_used=leverage_used,
            capped_by_limit=capped_by_limit,
            metadata={
                "atr_value": volatility_inputs.atr_value,
                "atr_multiplier": volatility_inputs.atr_multiplier,
                "stop_distance": stop_distance,
                "stop_loss_price": stop_loss_price,
                "volatility_percent": volatility_inputs.volatility_percent,
            },
        )


class PositionSizeCalculator:
    """Main calculator for position sizing with unified interface.

    Provides a single entry point for position size calculations with
    automatic method selection and risk constraint enforcement.
    """

    def __init__(self, config: SizingConfig | None = None):
        """Initialize the calculator.

        Args:
            config: Sizing configuration (uses defaults if None)
        """
        self.config = config or SizingConfig()
        self._engine = PositionSizingEngine(self.config)

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None = None,
        method: SizingMethod = SizingMethod.FIXED_FRACTIONAL,
        risk_percentage: float | None = None,
        kelly_inputs: KellyInputs | None = None,
        volatility_inputs: VolatilityInputs | None = None,
        direction: str = "long",
    ) -> PositionSizeResult:
        """Calculate position size using the specified method.

        This is the main entry point for position sizing calculations.
        Automatically enforces all risk constraints.

        Args:
            account_balance: Current account balance in USD
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price (required for Kelly and Fixed Fractional)
            method: Sizing method to use (default: FIXED_FRACTIONAL)
            risk_percentage: Risk percentage for fixed fractional (optional)
            kelly_inputs: Kelly Criterion inputs (required for Kelly method)
            volatility_inputs: Volatility inputs (required for Volatility method)
            direction: Trade direction ("long" or "short")

        Returns:
            PositionSizeResult with calculated position size

        Raises:
            ValueError: If required inputs are missing or invalid
        """
        if method == SizingMethod.KELLY_CRITERION:
            if kelly_inputs is None:
                raise ValueError("kelly_inputs required for Kelly Criterion method")
            if stop_loss_price is None:
                raise ValueError("stop_loss_price required for Kelly Criterion method")
            return self._engine.kelly_criterion_sizing(
                account_balance=account_balance,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                kelly_inputs=kelly_inputs,
            )

        elif method == SizingMethod.FIXED_FRACTIONAL:
            if stop_loss_price is None:
                raise ValueError("stop_loss_price required for Fixed Fractional method")
            return self._engine.fixed_fractional_sizing(
                account_balance=account_balance,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                risk_percentage=risk_percentage,
            )

        elif method == SizingMethod.VOLATILITY_BASED:
            if volatility_inputs is None:
                raise ValueError(
                    "volatility_inputs required for Volatility Based method"
                )
            return self._engine.volatility_based_sizing(
                account_balance=account_balance,
                entry_price=entry_price,
                volatility_inputs=volatility_inputs,
                direction=direction,
            )

        else:
            raise ValueError(f"Unknown sizing method: {method}")

    def calculate_atr(
        self,
        data: list["OHLCVData"],
        period: int = 14,
    ) -> float:
        """Calculate Average True Range (ATR) from OHLCV data.

        Args:
            data: List of OHLCV data points
            period: ATR calculation period (default: 14)

        Returns:
            ATR value
        """
        if len(data) < period + 1:
            return 0.0

        # Calculate True Range for each period
        tr_values: list[float] = []
        for i in range(1, len(data)):
            high = data[i].high_price
            low = data[i].low_price
            prev_close = data[i - 1].close_price

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        if len(tr_values) < period:
            return 0.0

        # Calculate ATR using Wilder's smoothing
        atr_values: list[float] = []
        # First ATR is simple average
        atr_values.append(np.mean(tr_values[:period]))

        # Subsequent values use smoothing formula
        for i in range(period, len(tr_values)):
            atr = (atr_values[-1] * (period - 1) + tr_values[i]) / period
            atr_values.append(atr)

        return float(atr_values[-1]) if atr_values else 0.0

    def validate_position_limits(
        self,
        position_result: PositionSizeResult,
        account_balance: float,
        existing_positions: list[PositionSizeResult] | None = None,
    ) -> tuple[bool, str]:
        """Validate position against risk limits.

        Args:
            position_result: Position size result to validate
            account_balance: Current account balance
            existing_positions: List of existing positions (optional)

        Returns:
            Tuple of (is_valid, reason)
        """
        existing_positions = existing_positions or []

        # Check per-trade risk limit (≤1%)
        if position_result.risk_percentage > self.config.max_risk_per_trade_pct:
            return (
                False,
                f"Risk {position_result.risk_percentage:.2f}% exceeds max per-trade limit "
                f"of {self.config.max_risk_per_trade_pct}%",
            )

        # Check leverage limit (≤3x)
        if position_result.leverage_used > self.config.max_leverage:
            return (
                False,
                f"Leverage {position_result.leverage_used:.2f}x exceeds max of "
                f"{self.config.max_leverage}x",
            )

        # Check position size limit
        max_position_value = account_balance * self.config.max_position_size_pct / 100
        if position_result.notional_value > max_position_value:
            return (
                False,
                f"Position value ${position_result.notional_value:,.2f} exceeds max of "
                f"${max_position_value:,.2f} ({self.config.max_position_size_pct}% of account)",
            )

        # Check grid risk (sum of all position risks ≤2%)
        # NOTE: Grid risk uses stop-loss based risk_amount, which represents the
        # maximum loss if all stops are hit simultaneously. This is NOT the same
        # as worst-case notional exposure. For grid strategies with multiple
        # positions, consider also monitoring total notional exposure separately.
        total_grid_risk = position_result.risk_amount
        total_grid_notional = position_result.notional_value
        for pos in existing_positions:
            total_grid_risk += pos.risk_amount
            total_grid_notional += pos.notional_value

        total_grid_risk_pct = (total_grid_risk / account_balance) * 100
        if total_grid_risk_pct > self.config.max_risk_per_grid_pct:
            return (
                False,
                f"Total grid risk {total_grid_risk_pct:.2f}% exceeds max of "
                f"{self.config.max_risk_per_grid_pct}%",
            )

        # Additional check: grid leverage should not exceed max_leverage * 2
        # This provides a safety limit on worst-case notional exposure
        total_grid_leverage = total_grid_notional / account_balance
        max_grid_leverage = (
            self.config.max_leverage * 2
        )  # Allow 2x max leverage for grids
        if total_grid_leverage > max_grid_leverage:
            return (
                False,
                f"Total grid leverage {total_grid_leverage:.2f}x exceeds max of "
                f"{max_grid_leverage:.2f}x (grid notional exposure too high)",
            )

        return True, "Position within all risk limits"
