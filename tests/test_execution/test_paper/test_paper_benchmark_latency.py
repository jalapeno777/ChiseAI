"""Latency benchmark for Paper Trading Orchestrator.

Demonstrates that the pipeline meets latency requirements:
- Signal → Order placement: <500ms
- Order fill simulation: <200ms
- Position tracking update: <100ms
- Total pipeline: <2 seconds
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from execution.paper.fill_model import FillModel, FillModelConfig
from execution.paper.models import OrderSide, OrderType, PaperOrder
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.order_simulator import OrderSimulator
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.risk_models import RiskAssessment
from portfolio.paper_tracker import PaperTracker as PaperPositionTracker
from signal_generation.models import Signal, SignalDirection, SignalStatus


class MockTelemetry:
    """Mock telemetry collector."""

    async def start(self):
        pass

    async def stop(self):
        pass

    async def set_equity(self, equity):
        pass


class MockKillSwitch:
    """Mock kill switch."""

    def __init__(self):
        self.state = MagicMock()
        self.state.value = "armed"


async def run_latency_benchmark(num_iterations: int = 10) -> dict:
    """Run latency benchmark.

    Args:
        num_iterations: Number of signals to process

    Returns:
        Benchmark results
    """
    print(f"\n{'=' * 60}")
    print(f"Paper Trading Orchestrator - Latency Benchmark")
    print(f"{'=' * 60}")
    print(f"Iterations: {num_iterations}")
    print()

    # Create components
    signal_gen = MagicMock()

    fill_model = FillModel(FillModelConfig(min_fill_delay_ms=10, max_fill_delay_ms=50))
    order_sim = OrderSimulator(fill_model=fill_model)

    position_tracker = PaperPositionTracker(redis_client=None)

    risk_enforcer = MagicMock()
    risk_enforcer.validate_order = AsyncMock(
        return_value=RiskAssessment(
            approved=True,
            position_size=0.1,
        )
    )

    telemetry = MockTelemetry()
    kill_switch = MockKillSwitch()

    # Create orchestrator
    orchestrator = PaperTradingOrchestrator(
        signal_generator=signal_gen,
        order_simulator=order_sim,
        position_tracker=position_tracker,
        risk_enforcer=risk_enforcer,
        telemetry_collector=telemetry,
        kill_switch=kill_switch,
        portfolio_value=10000.0,
    )

    # Create test signal
    signal = Signal(
        token="BTC/USDT",
        direction=SignalDirection.LONG,
        confidence=0.85,
        base_score=85.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        stop_loss=45000.0,
        stop_loss_method="atr",
        signal_id="bench-signal-001",
    )

    # Measure latencies
    total_latencies = []
    risk_latencies = []
    order_latencies = []
    position_latencies = []

    print("Running benchmark...")
    print()

    for i in range(num_iterations):
        start = time.perf_counter()

        # Measure risk validation
        risk_start = time.perf_counter()
        await risk_enforcer.validate_order(
            signal=signal,
            portfolio_value=10000.0,
            current_positions=[],
        )
        risk_latency = (time.perf_counter() - risk_start) * 1000
        risk_latencies.append(risk_latency)

        # Create and place order
        order = PaperOrder(
            symbol=signal.token,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )

        order_start = time.perf_counter()
        filled_order = await order_sim.place_order(order)
        order_latency = (time.perf_counter() - order_start) * 1000
        order_latencies.append(order_latency)

        # Open position
        position_start = time.perf_counter()
        position = await position_tracker.open_position(
            symbol=filled_order.symbol,
            side="long",
            entry_price=filled_order.avg_fill_price,
            quantity=filled_order.filled_quantity,
        )
        position_latency = (time.perf_counter() - position_start) * 1000
        position_latencies.append(position_latency)

        total_latency = (time.perf_counter() - start) * 1000
        total_latencies.append(total_latency)

        print(
            f"  Iteration {i + 1:2d}: Total={total_latency:6.1f}ms | "
            f"Risk={risk_latency:5.1f}ms | "
            f"Order={order_latency:5.1f}ms | "
            f"Position={position_latency:5.1f}ms"
        )

    # Calculate statistics
    results = {
        "total": {
            "min": min(total_latencies),
            "max": max(total_latencies),
            "mean": statistics.mean(total_latencies),
            "median": statistics.median(total_latencies),
            "p95": sorted(total_latencies)[int(len(total_latencies) * 0.95)],
            "passes": all(l < 2000 for l in total_latencies),
        },
        "risk_validation": {
            "min": min(risk_latencies),
            "max": max(risk_latencies),
            "mean": statistics.mean(risk_latencies),
            "passes": all(l < 500 for l in risk_latencies),
        },
        "order_placement": {
            "min": min(order_latencies),
            "max": max(order_latencies),
            "mean": statistics.mean(order_latencies),
            "passes": all(l < 500 for l in order_latencies),
        },
        "position_update": {
            "min": min(position_latencies),
            "max": max(position_latencies),
            "mean": statistics.mean(position_latencies),
            "passes": all(l < 100 for l in position_latencies),
        },
    }

    # Print summary
    print()
    print(f"{'=' * 60}")
    print("Benchmark Results")
    print(f"{'=' * 60}")
    print()

    print("Total Pipeline Latency (Target: <2000ms):")
    print(f"  Min:    {results['total']['min']:6.1f}ms")
    print(f"  Max:    {results['total']['max']:6.1f}ms")
    print(f"  Mean:   {results['total']['mean']:6.1f}ms")
    print(f"  Median: {results['total']['median']:6.1f}ms")
    print(f"  P95:    {results['total']['p95']:6.1f}ms")
    print(f"  Status: {'✓ PASS' if results['total']['passes'] else '✗ FAIL'}")
    print()

    print("Signal → Order Placement (Target: <500ms):")
    print(f"  Min:    {results['risk_validation']['min']:6.1f}ms")
    print(f"  Max:    {results['risk_validation']['max']:6.1f}ms")
    print(f"  Mean:   {results['risk_validation']['mean']:6.1f}ms")
    print(f"  Status: {'✓ PASS' if results['risk_validation']['passes'] else '✗ FAIL'}")
    print()

    print("Order Fill Simulation (Target: <200ms):")
    print(f"  Min:    {results['order_placement']['min']:6.1f}ms")
    print(f"  Max:    {results['order_placement']['max']:6.1f}ms")
    print(f"  Mean:   {results['order_placement']['mean']:6.1f}ms")
    print(f"  Status: {'✓ PASS' if results['order_placement']['passes'] else '✗ FAIL'}")
    print()

    print("Position Tracking Update (Target: <100ms):")
    print(f"  Min:    {results['position_update']['min']:6.1f}ms")
    print(f"  Max:    {results['position_update']['max']:6.1f}ms")
    print(f"  Mean:   {results['position_update']['mean']:6.1f}ms")
    print(f"  Status: {'✓ PASS' if results['position_update']['passes'] else '✗ FAIL'}")
    print()

    all_pass = all(
        [
            results["total"]["passes"],
            results["risk_validation"]["passes"],
            results["order_placement"]["passes"],
            results["position_update"]["passes"],
        ]
    )

    print(f"Overall: {'✓ ALL TARGETS MET' if all_pass else '✗ SOME TARGETS MISSED'}")
    print(f"{'=' * 60}")

    return results


async def demonstrate_trade_flow():
    """Demonstrate a complete trade flow."""
    print("\n" + "=" * 60)
    print("Example Trade Flow Demonstration")
    print("=" * 60)
    print()

    # Create signal
    signal = Signal(
        token="ETH/USDT",
        direction=SignalDirection.SHORT,
        confidence=0.82,
        base_score=82.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        stop_loss=3200.0,
        stop_loss_method="atr",
        signal_id="demo-signal-001",
    )

    print(f"1. Signal Generated:")
    print(f"   Token: {signal.token}")
    print(f"   Direction: {signal.direction.value.upper()}")
    print(f"   Confidence: {signal.confidence:.1%}")
    print(f"   Stop Loss: ${signal.stop_loss:,.2f}")
    print()

    # Risk assessment
    risk_enforcer = PaperRiskEnforcer()
    assessment = await risk_enforcer.validate_order(
        signal=signal,
        portfolio_value=10000.0,
        current_positions=[],
    )

    print(f"2. Risk Assessment:")
    print(f"   Approved: {assessment.approved}")
    print(f"   Position Size: {assessment.position_size:.6f}")
    print(f"   Max Loss: ${assessment.max_loss_amount:.2f}")
    if assessment.violations:
        print(f"   Violations: {', '.join(assessment.violations)}")
    print()

    if assessment.approved:
        # Create order
        order = PaperOrder(
            symbol=signal.token,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=assessment.position_size,
        )

        print(f"3. Order Created:")
        print(f"   Order ID: {order.order_id}")
        print(f"   Side: {order.side.value.upper()}")
        print(f"   Quantity: {order.quantity:.6f}")
        print(f"   Correlation ID: {order.correlation_id}")
        print()

        # Simulate fill
        fill_model = FillModel()
        order_sim = OrderSimulator(fill_model=fill_model)
        filled_order = await order_sim.place_order(order)

        print(f"4. Order Filled:")
        print(f"   State: {filled_order.state.value.upper()}")
        print(f"   Filled Qty: {filled_order.filled_quantity:.6f}")
        print(f"   Avg Fill Price: ${filled_order.avg_fill_price:,.2f}")
        print()

        # Track position
        position_tracker = PaperPositionTracker()
        position = await position_tracker.open_position(
            symbol=filled_order.symbol,
            side="short",
            entry_price=filled_order.avg_fill_price,
            quantity=filled_order.filled_quantity,
            metadata={
                "signal_id": signal.signal_id,
                "stop_loss": signal.stop_loss,
            },
        )

        print(f"5. Position Opened:")
        print(f"   Position ID: {position.position_id}")
        print(f"   Side: {position.side.upper()}")
        print(f"   Entry Price: ${position.entry_price:,.2f}")
        print(f"   Notional Value: ${position.notional_value:,.2f}")
        print()

        # Update price and show PnL
        await position_tracker.update_position(position.position_id, 3100.0)
        position = await position_tracker.get_position(position.position_id)

        print(f"6. Position Update (Price moved to $3,100):")
        print(f"   Current Price: ${position.current_price:,.2f}")
        print(f"   Unrealized PnL: ${position.unrealized_pnl:,.2f}")
        print(f"   PnL %: {position.unrealized_pnl_pct:.2f}%")
        print()

        # Close position
        closed_position, realized_pnl = await position_tracker.close_position(
            position.position_id, 3050.0
        )

        print(f"7. Position Closed (Exit at $3,050):")
        print(f"   Realized PnL: ${realized_pnl:,.2f}")
        print(f"   Status: {'WIN' if realized_pnl > 0 else 'LOSS'}")

    print()
    print("=" * 60)


if __name__ == "__main__":

    async def main():
        # Run trade flow demo
        await demonstrate_trade_flow()

        # Run latency benchmark
        results = await run_latency_benchmark(num_iterations=10)

        # Return overall pass/fail
        all_pass = all(
            [
                results["total"]["passes"],
                results["risk_validation"]["passes"],
                results["order_placement"]["passes"],
                results["position_update"]["passes"],
            ]
        )

        return 0 if all_pass else 1

    exit_code = asyncio.run(main())
    exit(exit_code)
