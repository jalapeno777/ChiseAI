"""Fill model for paper trading order execution simulation.

Provides realistic fill price calculation and slippage modeling
for paper trading simulations.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.models import OrderSide, OrderType, PaperOrder

logger = logging.getLogger(__name__)


@dataclass
class FillModelConfig:
    """Configuration for fill model behavior.

    Attributes:
        base_slippage_bps: Base slippage in basis points (default 5 bps = 0.05%)
        volatility_factor: Multiplier for volatility-based slippage
        max_slippage_bps: Maximum allowed slippage
        min_fill_delay_ms: Minimum fill delay in milliseconds
        max_fill_delay_ms: Maximum fill delay in milliseconds
        partial_fill_probability: Probability of partial fill (0.0-1.0)
        market_order_fill_probability: Probability of immediate fill for market orders
    """

    base_slippage_bps: float = 5.0
    volatility_factor: float = 1.0
    max_slippage_bps: float = 50.0  # 0.5% max slippage
    min_fill_delay_ms: float = 50.0
    max_fill_delay_ms: float = 200.0
    partial_fill_probability: float = 0.1
    market_order_fill_probability: float = 0.95


class FillModel:
    """Models realistic order fills for paper trading.

    Calculates fill prices with slippage and simulates fill delays.
    Provides deterministic fills for reproducible backtesting.
    """

    def __init__(self, config: FillModelConfig | None = None, seed: int | None = None):
        """Initialize fill model.

        Args:
            config: Fill model configuration
            seed: Random seed for reproducible fills
        """
        self.config = config or FillModelConfig()
        self._rng = random.Random(seed)

        logger.info(
            f"FillModel initialized: base_slippage={self.config.base_slippage_bps}bps, "
            f"seed={seed}"
        )

    def calculate_fill_price(
        self,
        order: PaperOrder,
        market_price: float,
        volatility: float = 0.0,
    ) -> float:
        """Calculate realistic fill price with slippage.

        Args:
            order: The order being filled
            market_price: Current market price
            volatility: Current volatility as decimal (e.g., 0.02 = 2%)

        Returns:
            Fill price with slippage applied
        """
        # Calculate base slippage in price terms
        base_slippage_pct = self.config.base_slippage_bps / 10000

        # Add volatility-based slippage
        volatility_slippage = volatility * self.config.volatility_factor

        # Total slippage
        total_slippage_pct = base_slippage_pct + volatility_slippage

        # Cap at max slippage
        max_slippage_pct = self.config.max_slippage_bps / 10000
        total_slippage_pct = min(total_slippage_pct, max_slippage_pct)

        # Apply slippage based on order side
        # Buy orders fill higher, sell orders fill lower
        if order.side.value == "buy":
            fill_price = market_price * (1 + total_slippage_pct)
        else:
            fill_price = market_price * (1 - total_slippage_pct)

        # Add small random variation (-10% to +10% of slippage)
        variation = self._rng.uniform(-0.1, 0.1) * total_slippage_pct
        fill_price = fill_price * (1 + variation)

        logger.debug(
            f"Fill price for {order.symbol}: market={market_price:.2f}, "
            f"fill={fill_price:.2f}, slippage={total_slippage_pct * 100:.3f}%"
        )

        return fill_price

    def calculate_fill_delay_ms(self) -> float:
        """Calculate simulated fill delay.

        Returns:
            Fill delay in milliseconds
        """
        return self._rng.uniform(
            self.config.min_fill_delay_ms,
            self.config.max_fill_delay_ms,
        )

    def should_fill_immediately(self, order: PaperOrder) -> bool:
        """Determine if order should fill immediately.

        Args:
            order: The order to check

        Returns:
            True if order should fill immediately
        """
        if order.order_type.value == "market":
            return self._rng.random() < self.config.market_order_fill_probability

        # Limit orders may not fill immediately depending on price
        return False

    def calculate_partial_fill_quantity(
        self,
        order: PaperOrder,
        available_liquidity: float,
    ) -> float:
        """Calculate partial fill quantity.

        Args:
            order: The order being filled
            available_liquidity: Available market liquidity

        Returns:
            Quantity to fill (may be less than order quantity)
        """
        # Determine if partial fill should occur
        if self._rng.random() > self.config.partial_fill_probability:
            # Full fill (or as much as liquidity allows)
            return min(order.quantity, available_liquidity)

        # Partial fill - random portion of order
        fill_ratio = self._rng.uniform(0.1, 0.9)
        partial_quantity = order.quantity * fill_ratio

        # Cap at available liquidity
        return min(partial_quantity, available_liquidity)

    def calculate_fee(self, notional_value: float, fee_rate: float = 0.0006) -> float:
        """Calculate trading fee.

        Args:
            notional_value: Value of the fill
            fee_rate: Fee rate as decimal (default 0.06% = 0.0006)

        Returns:
            Fee amount
        """
        return notional_value * fee_rate

    def reset_seed(self, seed: int) -> None:
        """Reset random seed for reproducible fills.

        Args:
            seed: New random seed
        """
        self._rng = random.Random(seed)
        logger.debug(f"FillModel seed reset to {seed}")
