"""Market impact model for paper trading execution simulation.

Provides realistic market impact calculation for large orders relative to ADV.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class MarketImpactConfig:
    """Configuration for market impact model.

    Attributes:
        base_coefficient: Base coefficient for impact calculation (k in formula)
        volatility_sensitivity: How much volatility affects impact
        min_impact_bps: Minimum impact in basis points
        max_impact_bps: Maximum impact in basis points
        adv_threshold: Minimum order size as fraction of ADV to calculate impact
        temporary_impact_fraction: Fraction of impact that is temporary
    """

    base_coefficient: float = 1.0
    volatility_sensitivity: float = 0.5
    min_impact_bps: float = 1.0
    max_impact_bps: float = 500.0
    adv_threshold: float = 0.001  # 0.1% of ADV
    temporary_impact_fraction: float = 0.7


class MarketImpact:
    """Models market impact for large orders in paper trading.

    Calculates temporary and permanent market impact based on order size
    relative to Average Daily Volume (ADV) and volatility.

    Formula: impact = k * sqrt(order_size / ADV)
    where k is volatility-adjusted coefficient
    """

    def __init__(self, config: MarketImpactConfig | None = None):
        """Initialize market impact model.

        Args:
            config: Market impact configuration
        """
        self.config = config or MarketImpactConfig()
        logger.info(
            f"MarketImpact initialized: base_coefficient={self.config.base_coefficient}, "
            f"adv_threshold={self.config.adv_threshold}"
        )

    def calculate_impact(
        self,
        order_size: float,
        adv: float,
        volatility: float = 0.0,
    ) -> float:
        """Calculate market impact for an order.

        Formula: impact = k * sqrt(order_size / ADV)
        where k is volatility-adjusted coefficient

        Only calculates impact for orders > 0.1% of ADV.

        Args:
            order_size: Order size in base token units
            adv: Average Daily Volume
            volatility: Current volatility as decimal (e.g., 0.02 = 2%)

        Returns:
            Market impact as a decimal (e.g., 0.001 = 10 bps)
        """
        # Check if order size warrants impact calculation
        if adv <= 0:
            logger.warning("ADV must be positive for impact calculation")
            return 0.0

        size_ratio = order_size / adv

        if size_ratio < self.config.adv_threshold:
            logger.debug(
                f"Order size {order_size} ({size_ratio:.4%} of ADV) below threshold, "
                f"no impact calculated"
            )
            return 0.0

        # Calculate volatility-adjusted coefficient
        k = self.config.base_coefficient * (
            1 + volatility * self.config.volatility_sensitivity
        )

        # Calculate impact using square root formula
        impact = k * math.sqrt(size_ratio)

        # Convert to basis points range for validation
        impact * 10000

        # Apply min/max bounds
        min_impact = self.config.min_impact_bps / 10000
        max_impact = self.config.max_impact_bps / 10000
        impact = max(min_impact, min(impact, max_impact))

        logger.debug(
            f"Market impact: size_ratio={size_ratio:.4%}, k={k:.4f}, "
            f"impact={impact:.4f} ({impact * 10000:.2f} bps)"
        )

        return impact

    def calculate_temporary_impact(
        self,
        order_size: float,
        adv: float,
        volatility: float = 0.0,
    ) -> float:
        """Calculate temporary (transient) market impact.

        Temporary impact decays over time after order execution.

        Args:
            order_size: Order size in base token units
            adv: Average Daily Volume
            volatility: Current volatility as decimal

        Returns:
            Temporary impact as a decimal
        """
        total_impact = self.calculate_impact(order_size, adv, volatility)
        temporary = total_impact * self.config.temporary_impact_fraction

        logger.debug(f"Temporary impact: {temporary:.4f} ({temporary * 10000:.2f} bps)")
        return temporary

    def calculate_permanent_impact(
        self,
        order_size: float,
        adv: float,
        volatility: float = 0.0,
    ) -> float:
        """Calculate permanent market impact.

        Permanent impact persists after order execution.

        Args:
            order_size: Order size in base token units
            adv: Average Daily Volume
            volatility: Current volatility as decimal

        Returns:
            Permanent impact as a decimal
        """
        total_impact = self.calculate_impact(order_size, adv, volatility)
        permanent = total_impact * (1 - self.config.temporary_impact_fraction)

        logger.debug(f"Permanent impact: {permanent:.4f} ({permanent * 10000:.2f} bps)")
        return permanent

    def estimate_price_impact(
        self,
        price: float,
        order_size: float,
        adv: float,
        volatility: float = 0.0,
        is_buy: bool = True,
    ) -> float:
        """Estimate the price impact in absolute terms.

        Args:
            price: Current market price
            order_size: Order size in base token units
            adv: Average Daily Volume
            volatility: Current volatility as decimal
            is_buy: True for buy orders, False for sell

        Returns:
            Price with impact applied
        """
        impact = self.calculate_impact(order_size, adv, volatility)

        if is_buy:
            # Buy orders push price up
            return price * (1 + impact)
        else:
            # Sell orders push price down
            return price * (1 - impact)

    def get_config(self) -> MarketImpactConfig:
        """Get current configuration.

        Returns:
            Current market impact configuration
        """
        return self.config

    def update_config(self, config: MarketImpactConfig) -> None:
        """Update configuration.

        Args:
            config: New market impact configuration
        """
        self.config = config
        logger.info(
            f"MarketImpact config updated: base_coefficient={config.base_coefficient}, "
            f"adv_threshold={config.adv_threshold}"
        )

    def get_optimal_execution_size(
        self,
        total_size: float,
        adv: float,
        max_acceptable_impact_bps: float = 50.0,
    ) -> float:
        """Calculate optimal execution size to limit market impact.

        Args:
            total_size: Total order size to execute
            adv: Average Daily Volume
            max_acceptable_impact_bps: Maximum acceptable impact in basis points

        Returns:
            Recommended execution size per slice
        """
        if adv <= 0:
            return total_size

        max_acceptable_impact = max_acceptable_impact_bps / 10000

        # Rearrange impact formula to solve for size_ratio:
        # impact = k * sqrt(size_ratio)
        # size_ratio = (impact / k) ^ 2
        k = self.config.base_coefficient
        max_size_ratio = (max_acceptable_impact / k) ** 2

        max_slice_size = max_size_ratio * adv

        # Ensure at least some minimum size
        min_slice_size = adv * self.config.adv_threshold
        optimal_size = max(min_slice_size, min(max_slice_size, total_size))

        logger.debug(
            f"Optimal execution size: {optimal_size:.2f} "
            f"(max_slice={max_slice_size:.2f}, total={total_size:.2f})"
        )

        return optimal_size
