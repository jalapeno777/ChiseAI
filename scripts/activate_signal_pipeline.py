#!/usr/bin/env python3
"""Activate signal-to-order pipeline.

Processes existing signals through the paper trading orchestrator
to create orders and outcomes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Set Redis connection for containerized environment
os.environ["REDIS_HOST"] = "host.docker.internal"
os.environ["REDIS_PORT"] = "6380"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import redis
from signal_generation.models import Signal, SignalDirection, SignalStatus
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.order_simulator import OrderSimulator
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.position_tracker import PaperPositionTracker
from execution.telemetry.collector import ExecutionCollector
from execution.telemetry.exporter import ExecutionTelemetryExporter
from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.state import KillSwitchState
from signal_generation.signal_generator import SignalGenerator


async def activate_pipeline():
    """Activate the signal-to-order pipeline."""

    # Connect to Redis
    r = redis.Redis(
        host="host.docker.internal",
        port=6380,
        decode_responses=True,
        socket_connect_timeout=5,
    )

    # Get existing signals
    signal_keys = r.keys("bmad:chiseai:signals:2026-02-27:*")
    logger.info(f"Found {len(signal_keys)} signals from today")

    if not signal_keys:
        logger.warning("No signals found to process")
        return 0

    # Initialize components
    signal_generator = SignalGenerator()

    # Create order simulator with market data
    from execution.paper.order_simulator import MarketDataProvider

    market_data = MarketDataProvider()
    # Set mock prices for testing
    market_data.set_price("BTCUSDT", 50000.0)
    market_data.set_price("ETHUSDT", 3000.0)
    market_data.set_price("BTC/USDT", 50000.0)
    market_data.set_price("ETH/USDT", 3000.0)
    order_simulator = OrderSimulator(market_data=market_data)

    position_tracker = PaperPositionTracker()
    risk_enforcer = PaperRiskEnforcer()

    # Create telemetry exporter and collector
    telemetry_exporter = ExecutionTelemetryExporter()
    telemetry = ExecutionCollector(exporter=telemetry_exporter)

    # Create kill switch
    kill_switch = KillSwitchExecutor()

    # Create orchestrator
    orchestrator = PaperTradingOrchestrator(
        signal_generator=signal_generator,
        order_simulator=order_simulator,
        position_tracker=position_tracker,
        risk_enforcer=risk_enforcer,
        telemetry_collector=telemetry,
        kill_switch=kill_switch,
        portfolio_value=10000.0,
    )

    # Start orchestrator
    await orchestrator.start()

    processed_count = 0
    order_count = 0

    try:
        for key in signal_keys:
            try:
                data = r.hgetall(key)
                if not data:
                    continue

                # Skip if already consumed
                if data.get("status") == "consumed":
                    logger.info(f"Signal {key} already consumed, skipping")
                    continue

                # Reconstruct signal
                direction_str = data.get("direction", "LONG").lower()
                direction = (
                    SignalDirection.LONG
                    if direction_str == "long"
                    else SignalDirection.SHORT
                )

                signal = Signal(
                    token=data.get("token", "UNKNOWN"),
                    direction=direction,
                    confidence=float(data.get("confidence", 0.0)),
                    base_score=float(data.get("confidence", 0.0)),
                    timestamp=__import__("datetime").datetime.fromisoformat(
                        data.get("timestamp")
                    ),
                    status=SignalStatus.ACTIONABLE,
                    timeframe=data.get("timeframe", "1h"),
                    signal_id=data.get("signal_id"),
                )

                logger.info(
                    f"Processing signal: {signal.token} [{signal.direction.value}] {signal.confidence:.1%}"
                )

                # Process through orchestrator
                result = await orchestrator.process_signal(signal)

                logger.info(
                    f"Result: {result.status.value} - {result.reject_reason if result.reject_reason else 'OK'}"
                )

                if result.status.value == "executed":
                    order_count += 1
                    # Mark signal as consumed
                    r.hset(key, "status", "consumed")
                    logger.info(
                        f"Created order: {result.order_id if hasattr(result, 'order_id') else 'N/A'}"
                    )

                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing signal {key}: {e}")
                continue

    finally:
        await orchestrator.stop()

    logger.info(f"Processed {processed_count} signals, created {order_count} orders")
    return order_count


if __name__ == "__main__":
    try:
        orders_created = asyncio.run(activate_pipeline())
        if orders_created > 0:
            logger.info(f"✓ SUCCESS: Created {orders_created} orders from signals")
            sys.exit(0)
        else:
            logger.warning("⚠ No orders were created")
            sys.exit(1)
    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
