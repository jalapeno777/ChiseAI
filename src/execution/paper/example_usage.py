"""Example usage of the paper trading order simulator.

This script demonstrates how to use the OrderSimulator for paper trading.
Run this to see the simulator in action.

For PAPER-LOOP-001: Paper Trading Order Simulator
"""

import asyncio

from src.execution.paper import create_simulator


async def demo_market_orders():
    """Demonstrate market order functionality."""
    print("=" * 60)
    print("MARKET ORDER DEMO")
    print("=" * 60)

    # Create simulator
    sim = create_simulator(
        min_slippage_pct=0.01,
        max_slippage_pct=0.03,
        min_latency_ms=50,
        max_latency_ms=100,
    )

    # Set market price
    sim.set_market_price("BTCUSDT", 50000.0)

    print(f"\nMarket price for BTCUSDT: ${sim.get_market_price('BTCUSDT'):,.2f}")

    # Place a market buy order
    print("\n--- Placing market buy order (0.1 BTC) ---")
    buy_order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=0.1,
    )

    print(f"Order ID: {buy_order.order_id}")
    print(f"State: {buy_order.state.value}")
    print(f"Side: {buy_order.side}")
    print(f"Quantity: {buy_order.quantity}")
    print(f"Filled: {buy_order.filled_quantity}")
    print(f"Avg Fill Price: ${buy_order.avg_fill_price:,.2f}")

    # Show fill details
    for fill in buy_order.fills:
        print(f"  Fill: {fill.quantity} @ ${fill.price:,.2f}")

    # Place a market sell order
    print("\n--- Placing market sell order (0.05 BTC) ---")
    sell_order = await sim.place_order(
        symbol="BTCUSDT",
        side="sell",
        order_type="market",
        quantity=0.05,
    )

    print(f"Order ID: {sell_order.order_id}")
    print(f"State: {sell_order.state.value}")
    print(f"Avg Fill Price: ${sell_order.avg_fill_price:,.2f}")

    # Show position
    position = sim.get_position("BTCUSDT")
    print(f"\nCurrent Position: {position['quantity']} BTC")
    print(f"Avg Entry Price: ${position['avg_entry_price']:,.2f}")


async def demo_limit_orders():
    """Demonstrate limit order functionality."""
    print("\n" + "=" * 60)
    print("LIMIT ORDER DEMO")
    print("=" * 60)

    # Create simulator with faster latency for demo
    sim = create_simulator(
        min_slippage_pct=0.01,
        max_slippage_pct=0.02,
        min_latency_ms=10,
        max_latency_ms=20,
    )

    # Set initial market price
    sim.set_market_price("ETHUSDT", 3000.0)

    print(
        f"\nInitial market price for ETHUSDT: ${sim.get_market_price('ETHUSDT'):,.2f}"
    )

    # Place a limit buy order below market
    print("\n--- Placing limit buy order (2 ETH @ $2800) ---")
    limit_buy = await sim.place_order(
        symbol="ETHUSDT",
        side="buy",
        order_type="limit",
        quantity=2.0,
        price=2800.0,
    )

    print(f"Order ID: {limit_buy.order_id}")
    print(f"State: {limit_buy.state.value}")
    print(f"Limit Price: ${limit_buy.price:,.2f}")
    print(f"Fills: {len(limit_buy.fills)}")

    # Place a limit sell order above market
    print("\n--- Placing limit sell order (1 ETH @ $3200) ---")
    limit_sell = await sim.place_order(
        symbol="ETHUSDT",
        side="sell",
        order_type="limit",
        quantity=1.0,
        price=3200.0,
    )

    print(f"Order ID: {limit_sell.order_id}")
    print(f"State: {limit_sell.state.value}")

    # Update market price to trigger limit buy
    print("\n--- Market price drops to $2750 ---")
    sim.set_market_price("ETHUSDT", 2750.0)

    # Check for fills
    fills = await sim.update_limit_orders()

    print(f"New fills created: {len(fills)}")

    # Check order status
    updated_order = sim.get_order(limit_buy.order_id)
    if updated_order:
        print(f"Limit buy order state: {updated_order.state.value}")
        if updated_order.fills:
            print(f"Filled at: ${updated_order.fills[0].price:,.2f}")

    # Update market price to trigger limit sell
    print("\n--- Market price rises to $3250 ---")
    sim.set_market_price("ETHUSDT", 3250.0)

    fills = await sim.update_limit_orders()
    print(f"New fills created: {len(fills)}")

    updated_sell = sim.get_order(limit_sell.order_id)
    if updated_sell:
        print(f"Limit sell order state: {updated_sell.state.value}")


async def demo_order_cancellation():
    """Demonstrate order cancellation."""
    print("\n" + "=" * 60)
    print("ORDER CANCELLATION DEMO")
    print("=" * 60)

    sim = create_simulator(min_latency_ms=10, max_latency_ms=20)
    sim.set_market_price("BTCUSDT", 50000.0)

    # Place a limit order
    print("\n--- Placing limit buy order ---")
    order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        quantity=0.5,
        price=45000.0,
    )

    print(f"Order ID: {order.order_id}")
    print(f"State: {order.state.value}")

    # Cancel the order
    print("\n--- Cancelling order ---")
    result = await sim.cancel_order(order.order_id)

    print(f"Cancel result: {result}")
    print(f"New state: {order.state.value}")

    # Try to cancel already filled order
    print("\n--- Placing market order ---")
    market_order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=0.1,
    )

    print(f"Market order state: {market_order.state.value}")

    result = await sim.cancel_order(market_order.order_id)
    print(f"Attempt to cancel filled order: {result}")


async def demo_invalid_orders():
    """Demonstrate invalid order rejection."""
    print("\n" + "=" * 60)
    print("INVALID ORDER DEMO")
    print("=" * 60)

    sim = create_simulator()

    # Try to place market order without price
    print("\n--- Attempting market order without market price ---")
    order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=1.0,
    )

    print(f"State: {order.state.value}")
    print(f"Reject reason: {order.reject_reason}")

    # Try to place order with negative quantity
    print("\n--- Attempting order with negative quantity ---")
    sim.set_market_price("BTCUSDT", 50000.0)
    order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=-1.0,
    )

    print(f"State: {order.state.value}")
    print(f"Reject reason: {order.reject_reason}")

    # Try to place limit order without price
    print("\n--- Attempting limit order without price ---")
    order = await sim.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        quantity=1.0,
        price=None,
    )

    print(f"State: {order.state.value}")
    print(f"Reject reason: {order.reject_reason}")


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("PAPER TRADING ORDER SIMULATOR - DEMO")
    print("=" * 60)

    await demo_market_orders()
    await demo_limit_orders()
    await demo_order_cancellation()
    await demo_invalid_orders()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
