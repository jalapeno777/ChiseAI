"""Position sizing engine module.

Extracted to avoid circular imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from portfolio_risk.position_sizing.types import (
    KellyInputs,
    PositionSizeResult,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
                "ATR is zero for volatility-based sizing. Using minimum position "
                "size or zero. This may indicate insufficient price data or a "
                "flat market."
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
