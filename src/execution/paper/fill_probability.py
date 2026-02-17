"""Fill probability model for paper trading execution simulation.

Provides realistic fill probability calculation for orders based on
order type, price levels, and market depth.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.paper.models import OrderType

logger = logging.getLogger(__name__)


@dataclass
class FillProbabilityConfig:
    """Configuration for fill probability model.

    Attributes:
        market_order_fill_prob: Probability of immediate fill for market orders
        base_limit_fill_prob: Base probability for limit orders at mid price
        price_distance_factor: How price distance affects fill probability
        depth_factor: How book depth affects fill probability
        large_order_threshold: Threshold for large order classification (fraction of depth)
        large_order_penalty: Probability reduction for large orders
        time_decay_factor: How probability decays over time
    """

    market_order_fill_prob: float = 1.0
    base_limit_fill_prob: float = 0.8
    price_distance_factor: float = 2.0
    depth_factor: float = 1.0
    large_order_threshold: float = 0.01  # 1% of book depth
    large_order_penalty: float = 0.3
    time_decay_factor: float = 0.95


class FillProbability:
    """Models fill probability for orders in paper trading.

    Calculates the probability that an order will be filled based on:
    - Order type (market vs limit)
    - Limit price distance from mid price
    - Available book depth
    - Order size relative to depth
    """

    def __init__(
        self, config: FillProbabilityConfig | None = None, seed: int | None = None
    ):
        """Initialize fill probability model.

        Args:
            config: Fill probability configuration
            seed: Random seed for reproducible outcomes
        """
        self.config = config or FillProbabilityConfig()
        self._rng = random.Random(seed)

        logger.info(
            f"FillProbability initialized: market_order_prob={self.config.market_order_fill_prob}, "
            f"base_limit_prob={self.config.base_limit_fill_prob}"
        )

    def calculate_fill_probability(
        self,
        order_type: OrderType,
        limit_price: float | None,
        mid_price: float,
        book_depth: float,
        order_size: float = 0.0,
        time_elapsed_ms: float = 0.0,
    ) -> float:
        """Calculate fill probability for an order.

        Market orders: 100% fill probability (or configured value)
        Limit orders: probability based on distance from mid and book depth
        Large orders (>1% book depth): reduced fill probability

        Args:
            order_type: Type of order (market/limit/stop)
            limit_price: Limit price (for limit orders)
            mid_price: Current mid price
            book_depth: Available liquidity at relevant price level
            order_size: Order size to check against depth
            time_elapsed_ms: Time elapsed since order submission

        Returns:
            Fill probability as float between 0.0 and 1.0
        """
        # Market orders have high fill probability
        if order_type.value == "market":
            prob = self.config.market_order_fill_prob
            logger.debug(f"Market order fill probability: {prob:.2%}")
            return prob

        # Stop orders treated similar to market when triggered
        if order_type.value in ("stop_market", "stop_limit"):
            # Simplified: assume stop is triggered
            if order_type.value == "stop_market":
                prob = self.config.market_order_fill_prob
            else:
                # Stop limit uses limit logic
                prob = self._calculate_limit_probability(
                    limit_price, mid_price, book_depth, order_size
                )
            logger.debug(f"Stop order fill probability: {prob:.2%}")
            return prob

        # Limit orders need price and depth analysis
        if order_type.value == "limit" and limit_price is not None:
            prob = self._calculate_limit_probability(
                limit_price, mid_price, book_depth, order_size
            )

            # Apply time decay
            if time_elapsed_ms > 0:
                decay_periods = time_elapsed_ms / 1000.0  # Decay per second
                prob *= self.config.time_decay_factor**decay_periods

            logger.debug(f"Limit order fill probability: {prob:.2%}")
            return max(0.0, min(1.0, prob))

        # Default: unknown order type
        logger.warning(f"Unknown order type: {order_type}, returning 0 probability")
        return 0.0

    def _calculate_limit_probability(
        self,
        limit_price: float,
        mid_price: float,
        book_depth: float,
        order_size: float,
    ) -> float:
        """Calculate fill probability for a limit order.

        Args:
            limit_price: Limit price
            mid_price: Current mid price
            book_depth: Available liquidity
            order_size: Order size

        Returns:
            Fill probability
        """
        # Calculate price distance from mid (as percentage)
        if mid_price <= 0:
            return self.config.base_limit_fill_prob

        price_distance = abs(limit_price - mid_price) / mid_price

        # Base probability adjusted by price distance
        # Closer to mid = higher probability
        distance_adjustment = 1.0 - (price_distance * self.config.price_distance_factor)
        prob = self.config.base_limit_fill_prob * distance_adjustment

        # Adjust for book depth
        if book_depth > 0:
            depth_ratio = book_depth / (book_depth + order_size)
            depth_adjustment = depth_ratio**self.config.depth_factor
            prob *= depth_adjustment

        # Large order penalty
        if book_depth > 0:
            size_ratio = order_size / book_depth
            if size_ratio > self.config.large_order_threshold:
                # Reduce probability for large orders
                excess_ratio = (
                    size_ratio - self.config.large_order_threshold
                ) / size_ratio
                penalty = excess_ratio * self.config.large_order_penalty
                prob *= 1.0 - penalty

        return max(0.0, min(1.0, prob))

    def should_fill(
        self,
        order_type: OrderType,
        limit_price: float | None,
        mid_price: float,
        book_depth: float,
        order_size: float = 0.0,
    ) -> bool:
        """Determine if an order should be filled based on probability.

        Args:
            order_type: Type of order
            limit_price: Limit price (for limit orders)
            mid_price: Current mid price
            book_depth: Available liquidity
            order_size: Order size

        Returns:
            True if order should be filled
        """
        prob = self.calculate_fill_probability(
            order_type, limit_price, mid_price, book_depth, order_size
        )
        return self._rng.random() < prob

    def calculate_partial_fill_probability(
        self,
        order_size: float,
        book_depth: float,
    ) -> float:
        """Calculate probability of partial fill.

        Args:
            order_size: Total order size
            book_depth: Available liquidity

        Returns:
            Probability of partial fill (0.0-1.0)
        """
        if book_depth <= 0:
            return 0.0

        if order_size <= book_depth:
            return 0.0  # Will fully fill

        # Higher probability of partial fill when order >> depth
        size_ratio = order_size / book_depth
        partial_prob = min(0.9, 1.0 - (1.0 / size_ratio))

        logger.debug(f"Partial fill probability: {partial_prob:.2%}")
        return partial_prob

    def get_config(self) -> FillProbabilityConfig:
        """Get current configuration.

        Returns:
            Current fill probability configuration
        """
        return self.config

    def update_config(self, config: FillProbabilityConfig) -> None:
        """Update configuration.

        Args:
            config: New fill probability configuration
        """
        self.config = config
        logger.info(
            f"FillProbability config updated: market_order_prob={config.market_order_fill_prob}"
        )

    def reset_seed(self, seed: int) -> None:
        """Reset random seed for reproducible outcomes.

        Args:
            seed: New random seed
        """
        self._rng = random.Random(seed)
        logger.debug(f"FillProbability seed reset to {seed}")
