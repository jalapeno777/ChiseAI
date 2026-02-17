"""Slippage model for paper trading execution simulation.

Provides realistic slippage calculation based on order size, volatility,
and market conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.paper.models import OrderSide

logger = logging.getLogger(__name__)


@dataclass
class SlippageConfig:
    """Configuration for slippage model.

    Attributes:
        base_slippage_bps: Base slippage in basis points (default 2 bps = 0.02%)
        volatility_factor: Multiplier for volatility-based slippage adjustment
        min_slippage_bps: Minimum slippage in basis points
        max_slippage_bps: Maximum slippage in basis points
        order_size_factor: Factor for order size impact on slippage
        adv_threshold: Average Daily Volume threshold for size calculations
    """

    base_slippage_bps: float = 2.0
    volatility_factor: float = 1.0
    min_slippage_bps: float = 0.5
    max_slippage_bps: float = 100.0
    order_size_factor: float = 1.0
    adv_threshold: float = 0.001  # 0.1% of ADV


class SlippageModel:
    """Models realistic slippage for paper trading.

    Calculates slippage based on order size relative to ADV, volatility,
    and configurable base slippage parameters.
    """

    def __init__(self, config: SlippageConfig | None = None):
        """Initialize slippage model.

        Args:
            config: Slippage model configuration
        """
        self.config = config or SlippageConfig()
        logger.info(
            f"SlippageModel initialized: base_slippage={self.config.base_slippage_bps}bps, "
            f"volatility_factor={self.config.volatility_factor}"
        )

    def calculate_slippage(
        self,
        symbol: str,
        order_size: float,
        side: OrderSide,
        market_data: dict,
    ) -> float:
        """Calculate slippage for an order.

        Formula: base_slippage + (volatility_factor * order_size / avg_daily_volume)

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            order_size: Order size in base token units
            side: Order side (buy/sell)
            market_data: Market data dictionary containing:
                - avg_daily_volume: Average daily trading volume
                - volatility: Current volatility as decimal (e.g., 0.02 = 2%)
                - spread_bps: Current bid-ask spread in basis points

        Returns:
            Slippage as a decimal (e.g., 0.0002 = 2 bps)
        """
        # Extract market data with defaults
        avg_daily_volume = market_data.get("avg_daily_volume", 0.0)
        volatility = market_data.get("volatility", 0.0)
        spread_bps = market_data.get("spread_bps", 10.0)

        # Base slippage in decimal
        base_slippage = self.config.base_slippage_bps / 10000
        size_ratio = 0.0

        # If no ADV data, use spread-based estimate
        if avg_daily_volume <= 0:
            # Estimate slippage from spread (typically 1/2 spread for market orders)
            spread_slippage = (spread_bps / 10000) * 0.5
            total_slippage = max(base_slippage, spread_slippage)
        else:
            # Calculate order size relative to ADV
            size_ratio = order_size / avg_daily_volume

            # Volatility adjustment (scale down - volatility of 2% should add ~2 bps, not 200 bps)
            volatility_adjustment = volatility * self.config.volatility_factor * 0.001

            # Size-based slippage component (only for large orders)
            if size_ratio >= self.config.adv_threshold:
                size_slippage = self.config.volatility_factor * size_ratio * 0.01
            else:
                size_slippage = 0.0

            # Total slippage
            total_slippage = base_slippage + volatility_adjustment + size_slippage

        # Apply min/max bounds
        min_slippage = self.config.min_slippage_bps / 10000
        max_slippage = self.config.max_slippage_bps / 10000
        total_slippage = max(min_slippage, min(total_slippage, max_slippage))

        # Log with safe size_ratio reference
        size_ratio_str = f"{size_ratio:.6f}" if avg_daily_volume > 0 else "N/A"
        logger.debug(
            f"Slippage for {symbol} ({side.value}): "
            f"base={base_slippage:.4f}, total={total_slippage:.4f}, "
            f"size_ratio={size_ratio_str}"
        )

        return total_slippage

    def apply_slippage_to_price(
        self,
        price: float,
        slippage: float,
        side: OrderSide,
    ) -> float:
        """Apply slippage to a price.

        Args:
            price: Original price
            slippage: Slippage as decimal
            side: Order side (buy/sell)

        Returns:
            Price with slippage applied
        """
        if side.value == "buy":
            # Buy orders fill higher (worse price)
            return price * (1 + slippage)
        else:
            # Sell orders fill lower (worse price)
            return price * (1 - slippage)

    def get_config(self) -> SlippageConfig:
        """Get current configuration.

        Returns:
            Current slippage configuration
        """
        return self.config

    def update_config(self, config: SlippageConfig) -> None:
        """Update configuration.

        Args:
            config: New slippage configuration
        """
        self.config = config
        logger.info(
            f"SlippageModel config updated: base_slippage={config.base_slippage_bps}bps"
        )
