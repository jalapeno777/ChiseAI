"""Fill model for paper trading with realistic slippage.

Implements fill price calculation with configurable slippage
and latency simulation to mimic real exchange behavior.

For PAPER-LOOP-001: Paper Trading Order Simulator
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PaperFill, PaperOrder


@dataclass
class SlippageConfig:
    """Configuration for slippage simulation.

    Attributes:
        min_slippage_pct: Minimum slippage percentage (e.g., 0.01 for 0.01%)
        max_slippage_pct: Maximum slippage percentage (e.g., 0.05 for 0.05%)
        volatility_factor: Multiplier for market volatility impact (default 1.0)
    """

    min_slippage_pct: float = 0.01
    max_slippage_pct: float = 0.05
    volatility_factor: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.min_slippage_pct < 0 or self.max_slippage_pct < 0:
            raise ValueError("Slippage percentages must be non-negative")
        if self.min_slippage_pct > self.max_slippage_pct:
            raise ValueError("min_slippage_pct cannot exceed max_slippage_pct")
        if self.volatility_factor < 0:
            raise ValueError("volatility_factor must be non-negative")


@dataclass
class LatencyConfig:
    """Configuration for latency simulation.

    Attributes:
        min_latency_ms: Minimum latency in milliseconds
        max_latency_ms: Maximum latency in milliseconds
    """

    min_latency_ms: float = 50.0
    max_latency_ms: float = 200.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.min_latency_ms < 0 or self.max_latency_ms < 0:
            raise ValueError("Latency values must be non-negative")
        if self.min_latency_ms > self.max_latency_ms:
            raise ValueError("min_latency_ms cannot exceed max_latency_ms")

    def get_latency_seconds(self) -> float:
        """Get random latency in seconds.

        Returns:
            Random latency between min and max, in seconds
        """
        latency_ms = random.uniform(self.min_latency_ms, self.max_latency_ms)
        return latency_ms / 1000.0


class FillModel:
    """Fill model for paper trading with slippage and latency simulation.

    This class simulates realistic fill behavior including:
    - Price slippage for market orders (0.01-0.05% by default)
    - Latency simulation (50-200ms by default)
    - Limit order fill logic based on market price crossing

    Attributes:
        slippage_config: Configuration for slippage simulation
        latency_config: Configuration for latency simulation
    """

    def __init__(
        self,
        slippage_config: SlippageConfig | None = None,
        latency_config: LatencyConfig | None = None,
    ) -> None:
        """Initialize fill model with configuration.

        Args:
            slippage_config: Slippage configuration (uses defaults if None)
            latency_config: Latency configuration (uses defaults if None)
        """
        self.slippage_config = slippage_config or SlippageConfig()
        self.latency_config = latency_config or LatencyConfig()

    async def simulate_latency(self) -> None:
        """Simulate network latency by sleeping.

        Uses the configured min/max latency range.
        """
        latency = self.latency_config.get_latency_seconds()
        await asyncio.sleep(latency)

    def calculate_market_fill_price(
        self,
        market_price: float,
        side: str,
        quantity: float,
    ) -> float:
        """Calculate fill price for a market order with slippage.

        Market orders fill at the market price with slight slippage
        that works against the trader (worse price).

        Args:
            market_price: Current market price
            side: Order side - "buy" or "sell"
            quantity: Order quantity (can affect slippage for large orders)

        Returns:
            Fill price with slippage applied

        Raises:
            ValueError: If inputs are invalid
        """
        if market_price <= 0:
            raise ValueError(f"Invalid market_price: {market_price}")
        if side.lower() not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {side}")
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}")

        # Calculate slippage percentage
        slippage_pct = random.uniform(
            self.slippage_config.min_slippage_pct,
            self.slippage_config.max_slippage_pct,
        )

        # Adjust for quantity (larger orders = more slippage)
        # Use a simple square root model: 1x quantity = 1x slippage, 4x quantity = 2x slippage
        quantity_factor = 1.0 + (quantity / 100.0) ** 0.5 * 0.1
        slippage_pct *= quantity_factor

        # Apply slippage against the trader
        # Buy orders fill at higher price (slippage added)
        # Sell orders fill at lower price (slippage subtracted)
        slippage_multiplier = slippage_pct / 100.0

        if side.lower() == "buy":
            fill_price = market_price * (1 + slippage_multiplier)
        else:  # sell
            fill_price = market_price * (1 - slippage_multiplier)

        return round(fill_price, 8)

    def should_limit_order_fill(
        self,
        order: PaperOrder,
        market_price: float,
    ) -> bool:
        """Determine if a limit order should fill based on market price.

        Limit orders fill when the market price crosses the limit:
        - Buy limit: fills when market price <= limit price
        - Sell limit: fills when market price >= limit price

        Args:
            order: The limit order to check
            market_price: Current market price

        Returns:
            True if order should fill, False otherwise
        """
        if order.order_type != "limit":
            return False

        if order.price is None:
            return False

        if order.side == "buy":
            # Buy limit fills when market is at or below limit price
            return market_price <= order.price
        else:  # sell
            # Sell limit fills when market is at or above limit price
            return market_price >= order.price

    def calculate_limit_fill_price(
        self,
        order: PaperOrder,
        market_price: float,
    ) -> float:
        """Calculate fill price for a limit order.

        Limit orders fill at the limit price, not the market price.

        Args:
            order: The limit order
            market_price: Current market price (for validation)

        Returns:
            Fill price (the limit price)

        Raises:
            ValueError: If order is not a valid limit order
        """
        if order.order_type != "limit":
            raise ValueError(f"Expected limit order, got: {order.order_type}")

        if order.price is None:
            raise ValueError("Limit order must have a price")

        return order.price

    async def create_fill(
        self,
        order: PaperOrder,
        fill_price: float,
        fill_quantity: float | None = None,
    ) -> PaperFill:
        """Create a fill for an order.

        Simulates latency before creating the fill.

        Args:
            order: The order being filled
            fill_price: The fill price
            fill_quantity: Quantity to fill (defaults to remaining quantity)

        Returns:
            New PaperFill instance
        """
        from .models import PaperFill

        # Simulate latency
        await self.simulate_latency()

        # Determine fill quantity
        if fill_quantity is None:
            fill_quantity = order.remaining_quantity

        # Ensure we don't overfill
        fill_quantity = min(fill_quantity, order.remaining_quantity)

        return PaperFill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill_quantity,
            price=fill_price,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "slippage_min_pct": self.slippage_config.min_slippage_pct,
                "slippage_max_pct": self.slippage_config.max_slippage_pct,
            },
        )

    async def fill_market_order(
        self,
        order: PaperOrder,
        market_price: float,
    ) -> PaperFill:
        """Fill a market order completely.

        Market orders fill immediately at market price with slippage.

        Args:
            order: The market order to fill
            market_price: Current market price

        Returns:
            Fill event

        Raises:
            ValueError: If order is not a market order
        """
        if order.order_type != "market":
            raise ValueError(f"Expected market order, got: {order.order_type}")

        fill_price = self.calculate_market_fill_price(
            market_price=market_price,
            side=order.side,
            quantity=order.quantity,
        )

        return await self.create_fill(order, fill_price)

    async def fill_limit_order(
        self,
        order: PaperOrder,
        market_price: float,
        partial: bool = False,
    ) -> PaperFill | None:
        """Fill a limit order if market price crosses.

        Args:
            order: The limit order to fill
            market_price: Current market price
            partial: If True, only fill partial quantity

        Returns:
            Fill event if order fills, None otherwise
        """
        if not self.should_limit_order_fill(order, market_price):
            return None

        fill_price = self.calculate_limit_fill_price(order, market_price)

        if partial:
            # Simulate partial fill (10-50% of remaining)
            fill_quantity = order.remaining_quantity * random.uniform(0.1, 0.5)
        else:
            fill_quantity = order.remaining_quantity

        return await self.create_fill(order, fill_price, fill_quantity)


def create_fill_model(
    min_slippage_pct: float = 0.01,
    max_slippage_pct: float = 0.05,
    min_latency_ms: float = 50.0,
    max_latency_ms: float = 200.0,
) -> FillModel:
    """Create a FillModel with custom configuration.

    Args:
        min_slippage_pct: Minimum slippage percentage (default 0.01%)
        max_slippage_pct: Maximum slippage percentage (default 0.05%)
        min_latency_ms: Minimum latency in milliseconds (default 50ms)
        max_latency_ms: Maximum latency in milliseconds (default 200ms)

    Returns:
        Configured FillModel instance
    """
    slippage_config = SlippageConfig(
        min_slippage_pct=min_slippage_pct,
        max_slippage_pct=max_slippage_pct,
    )
    latency_config = LatencyConfig(
        min_latency_ms=min_latency_ms,
        max_latency_ms=max_latency_ms,
    )

    return FillModel(
        slippage_config=slippage_config,
        latency_config=latency_config,
    )
