"""Position size calculator module.

Extracted to avoid circular imports with integration module.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from portfolio_risk.position_sizing.engine import PositionSizingEngine
from portfolio_risk.position_sizing.types import (
    KellyInputs,
    PositionSizeResult,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData

from data_ingestion.ohlcv_fetcher import OHLCVData

logger = logging.getLogger(__name__)


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
        data: list[OHLCVData],
        period: int = 14,
    ) -> float:
        """Calculate Average True Range (ATR) from OHLCV data.

        Args:
            data: List of OHLCV data points
            period: ATR calculation period (default: 14)

        Returns:
            ATR value
        """
        import numpy as np

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
                f"Risk {position_result.risk_percentage:.2f}% exceeds max "
                f"per-trade limit of {self.config.max_risk_per_trade_pct}%",
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
                f"Position value ${position_result.notional_value:,.2f} "
                f"exceeds max of ${max_position_value:,.2f} "
                f"({self.config.max_position_size_pct}% of account)",
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
