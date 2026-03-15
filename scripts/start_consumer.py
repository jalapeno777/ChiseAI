#!/usr/bin/env python3
"""Quick Signal Consumer starter - minimal version for testing.

This script starts the SignalConsumer with minimal dependencies.
"""

import sys
import os

# Set up paths BEFORE any imports
# Add src to path so imports work without 'src.' prefix
sys.path.insert(0, "/tmp/worktrees/PAPER-NOGO-REMEDIATION-002")
sys.path.insert(0, "/tmp/worktrees/PAPER-NOGO-REMEDIATION-002/src")

import asyncio
import logging
from datetime import UTC, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Start the SignalConsumer."""
    from config.bootstrap import bootstrap
    from config.trading_mode import TradingModeConfig
    from data_ingestion.ohlcv_fetcher import OHLCVFetcher
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.outcome_capture.integration import OutcomeCaptureIntegration
    from execution.paper import (
        OrderSimulator,
        PaperPositionTracker,
        create_simulator,
    )
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from execution.paper.risk_enforcer import PaperRiskEnforcer
    from execution.paper.risk_models import RiskCheck
    from execution.paper.signal_consumer import SignalConsumer
    from execution.telemetry.collector import ExecutionCollector
    from execution.telemetry.exporter import ExecutionTelemetryExporter
    from signal_generation.signal_generator import SignalGenerator

    logger.info("Bootstrapping environment...")
    bootstrap(load_env=True, verbose=False)

    logger.info("Initializing components...")

    # Create configuration
    config = TradingModeConfig.create_paper_config(
        portfolio_value=10000.0,
        signal_threshold=0.75,
    )

    # Initialize components
    signal_generator = SignalGenerator(config=None)
    order_simulator = create_simulator()
    position_tracker = PaperPositionTracker()

    risk_config = RiskCheck(
        min_confidence=0.75,
        max_position_pct=0.1,
    )
    risk_enforcer = PaperRiskEnforcer(config=risk_config)
    kill_switch = KillSwitchExecutor()

    outcome_capture = OutcomeCaptureIntegration()

    # Create signal consumer
    signal_consumer = SignalConsumer(
        orchestrator=None,
        poll_interval=5.0,
    )

    # Create orchestrator
    orchestrator = PaperTradingOrchestrator(
        signal_generator=signal_generator,
        order_simulator=order_simulator,
        position_tracker=position_tracker,
        risk_enforcer=risk_enforcer,
        telemetry_collector=None,
        kill_switch=kill_switch,
        portfolio_value=10000.0,
        outcome_capture=outcome_capture,
        signal_consumer=signal_consumer,
    )

    # Wire the orchestrator to the signal consumer
    signal_consumer.orchestrator = orchestrator

    # Set market prices for common symbols so orders can be filled
    # This is required for the order simulator to work
    logger.info("Setting market prices...")
    order_simulator.set_market_price("BTC/USDT", 85000.0)
    order_simulator.set_market_price("ETH/USDT", 4500.0)
    order_simulator.set_market_price("SOL/USDT", 180.0)
    order_simulator.set_market_price("BNB/USDT", 620.0)
    logger.info("Market prices set: BTC=$85000, ETH=$4500, SOL=$180, BNB=$620")

    # Start the orchestrator (this also starts the signal consumer)
    logger.info("Starting orchestrator...")
    await orchestrator.start()

    logger.info("SignalConsumer started successfully!")
    logger.info("Press Ctrl+C to stop")

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopping orchestrator...")
        await orchestrator.stop()
        logger.info("Stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested")
        sys.exit(0)
