"""Paper trading order simulator module.

Provides a realistic paper trading environment that mimics exchange
behavior without hitting live APIs. Supports market and limit orders
with realistic fill simulation, slippage, and order state tracking.

Example usage:
    >>> from src.execution.paper import OrderSimulator, create_simulator
    >>>
    >>> # Create simulator
    >>> sim = create_simulator()
    >>>
    >>> # Set market price
    >>> sim.set_market_price("BTCUSDT", 50000.0)
    >>>
    >>> # Place a market buy order
    >>> order = await sim.place_order(
    ...     symbol="BTCUSDT",
    ...     side="buy",
    ...     order_type="market",
    ...     quantity=0.1
    ... )
    >>> print(f"Order filled at {order.avg_fill_price}")
    >>>
    >>> # Place a limit sell order
    >>> limit_order = await sim.place_order(
    ...     symbol="BTCUSDT",
    ...     side="sell",
    ...     order_type="limit",
    ...     quantity=0.1,
    ...     price=55000.0
    ... )

For PAPER-LOOP-001: Paper Trading Order Simulator
"""

from .fill_model import (
    FillModel,
    LatencyConfig,
    SlippageConfig,
    create_fill_model,
)
from .models import (
    OrderState,
    OrderType,
    OrderSide,
    PaperFill,
    PaperOrder,
)
from .order_simulator import (
    MarketDataProvider,
    OrderSimulator,
    OrderSimulatorConfig,
)


def create_simulator(
    min_slippage_pct: float = 0.01,
    max_slippage_pct: float = 0.05,
    min_latency_ms: float = 50.0,
    max_latency_ms: float = 200.0,
) -> OrderSimulator:
    """Create a paper trading order simulator with standard configuration.

    This is the recommended factory function for creating simulators.

    Args:
        min_slippage_pct: Minimum slippage percentage (default 0.01%)
        max_slippage_pct: Maximum slippage percentage (default 0.05%)
        min_latency_ms: Minimum fill latency in milliseconds (default 50ms)
        max_latency_ms: Maximum fill latency in milliseconds (default 200ms)

    Returns:
        Configured OrderSimulator instance ready for use

    Example:
        >>> sim = create_simulator()
        >>> sim.set_market_price("BTCUSDT", 50000.0)
        >>> order = await sim.place_order(
        ...     symbol="BTCUSDT",
        ...     side="buy",
        ...     order_type="market",
        ...     quantity=0.1
        ... )
    """
    config = OrderSimulatorConfig(
        min_slippage_pct=min_slippage_pct,
        max_slippage_pct=max_slippage_pct,
        min_latency_ms=min_latency_ms,
        max_latency_ms=max_latency_ms,
    )
    return config.create_simulator()


__all__ = [
    # Core simulator
    "OrderSimulator",
    "create_simulator",
    "OrderSimulatorConfig",
    "MarketDataProvider",
    # Models
    "PaperOrder",
    "PaperFill",
    "OrderState",
    "OrderType",
    "OrderSide",
    # Fill model
    "FillModel",
    "SlippageConfig",
    "LatencyConfig",
    "create_fill_model",
]
