#!/usr/bin/env python3
"""Standalone Signal Consumer runner.

This script runs the SignalConsumer as a persistent background service,
continuously polling Redis for actionable signals and submitting them
to the paper trading orchestrator.

Usage:
    python scripts/run_signal_consumer.py
    python scripts/run_signal_consumer.py --poll-interval 5.0 --verbose

The consumer will:
1. Connect to Redis and scan for signals with status="actionable"
2. Submit signals to the paper trading orchestrator
3. Track processed signals to avoid duplicates
4. Maintain a health marker in Redis
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports BEFORE importing anything else
# This must be done before importing logging to avoid conflicts with scripts/logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Now import logging after path is set up
import logging

# Handle case where config was already imported from a different location
if "config" in sys.modules:
    del sys.modules["config"]
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("config."):
            del sys.modules[mod_name]

from config.bootstrap import bootstrap
from config.feature_flags import get_feature_flags
from config.trading_mode import ModuleType, TradingMode, TradingModeConfig

# Trading components
from data_ingestion.ohlcv_fetcher import OHLCVFetcher
from data_ingestion.timeframe_config import Timeframe
from execution.connectors.bybit_demo_connector import BybitDemoConnector
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SignalConsumerRunner:
    """Runner for the SignalConsumer as a persistent service.

    This class manages the full lifecycle of the SignalConsumer,
    including initialization, health monitoring, and graceful shutdown.
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        portfolio_value: float = 10000.0,
        confidence_threshold: float = 0.75,
    ):
        """Initialize the SignalConsumer runner.

        Args:
            poll_interval: Seconds between polling cycles
            portfolio_value: Starting portfolio value for paper trading
            confidence_threshold: Minimum confidence threshold for signals
        """
        self.poll_interval = poll_interval
        self.portfolio_value = portfolio_value
        self.confidence_threshold = confidence_threshold

        self._running = False
        self._shutdown_event = asyncio.Event()
        self._components: dict[str, Any] = {}
        self._start_time: datetime | None = None

        # Trading components
        self.orchestrator: PaperTradingOrchestrator | None = None
        self.signal_consumer: SignalConsumer | None = None

        logger.info(
            f"SignalConsumerRunner initialized: "
            f"poll_interval={poll_interval}s, portfolio=${portfolio_value:.2f}"
        )

    async def start(self) -> bool:
        """Start the SignalConsumer service.

        Returns:
            True if started successfully, False otherwise
        """
        logger.info("Starting SignalConsumer service...")
        self._running = True
        self._start_time = datetime.now(UTC)

        try:
            # Initialize all components
            await self._initialize_components()

            logger.info("SignalConsumer service started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start SignalConsumer service: {e}", exc_info=True)
            self._running = False
            return False

    async def _initialize_components(self) -> None:
        """Initialize all trading components."""
        logger.info("Initializing trading components...")

        # Create configuration
        TradingModeConfig.create_paper_config(
            portfolio_value=self.portfolio_value,
            signal_threshold=self.confidence_threshold,
        )

        # Initialize market data fetcher
        ohlcv_fetcher = OHLCVFetcher()
        self._components["ohlcv_fetcher"] = ohlcv_fetcher
        logger.info("OHLCV fetcher initialized")

        # Initialize signal generator
        signal_generator = SignalGenerator(config=None)
        self._components["signal_generator"] = signal_generator
        logger.info("Signal generator initialized")

        # Initialize paper trading components
        # PAPER-RECON-001: Route to BybitDemoConnector when credentials available
        # unless FORCE_SIMULATOR_MODE is enabled
        flags = get_feature_flags()
        force_simulator = flags.is_force_simulator_mode_enabled()

        if force_simulator:
            order_simulator = create_simulator()
            logger.info(
                "Paper trading components initialized: OrderSimulator "
                "(FORCE_SIMULATOR_MODE=true)"
            )
        else:
            # Try to use BybitDemoConnector when credentials available
            try:
                order_simulator = BybitDemoConnector.from_env()
                logger.info(
                    "Paper trading components initialized: BybitDemoConnector "
                    "(authenticated demo execution)"
                )
            except Exception as exc:
                logger.warning(
                    "BybitDemoConnector init failed (%s); using local simulator fallback",
                    exc,
                )
                order_simulator = create_simulator()
                logger.info(
                    "Paper trading components initialized: OrderSimulator "
                    "(simulator fallback)"
                )

        position_tracker = PaperPositionTracker()
        self._components["order_simulator"] = order_simulator
        self._components["position_tracker"] = position_tracker

        # Initialize risk management
        risk_config = RiskCheck(
            min_confidence=self.confidence_threshold,
            max_position_pct=0.1,  # 10% max position
        )
        risk_enforcer = PaperRiskEnforcer(config=risk_config)
        kill_switch = KillSwitchExecutor()
        self._components["risk_enforcer"] = risk_enforcer
        self._components["kill_switch"] = kill_switch
        logger.info("Risk management initialized")

        # Initialize telemetry (optional)
        try:
            exporter = ExecutionTelemetryExporter(influxdb_client=None)
            telemetry_collector = ExecutionCollector(
                exporter=exporter,
                environment="paper",
            )
            self._components["telemetry_collector"] = telemetry_collector
            logger.info("Telemetry collector initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize telemetry: {e}")
            telemetry_collector = None

        # Initialize outcome capture
        outcome_capture = OutcomeCaptureIntegration()
        self._components["outcome_capture"] = outcome_capture
        logger.info("Outcome capture initialized")

        # Create signal consumer
        self.signal_consumer = SignalConsumer(
            orchestrator=None,  # Will be set below
            poll_interval=self.poll_interval,
        )
        logger.info("Signal consumer created")

        # Create orchestrator
        self.orchestrator = PaperTradingOrchestrator(
            signal_generator=signal_generator,
            order_simulator=order_simulator,
            position_tracker=position_tracker,
            risk_enforcer=risk_enforcer,
            telemetry_collector=telemetry_collector,
            kill_switch=kill_switch,
            portfolio_value=self.portfolio_value,
            outcome_capture=outcome_capture,
            signal_consumer=self.signal_consumer,
        )

        # Wire the orchestrator to the signal consumer
        self.signal_consumer.orchestrator = self.orchestrator

        # Start the orchestrator (this also starts the signal consumer)
        await self.orchestrator.start()
        logger.info("Paper trading orchestrator started")

    async def _log_status(self) -> None:
        """Log current status of the consumer."""
        if not self.signal_consumer:
            return

        stats = self.signal_consumer.get_stats()
        logger.info(
            f"SignalConsumer status: running={stats.get('running')}, "
            f"processed={stats.get('processed_count', 0)}, "
            f"poll_interval={stats.get('poll_interval')}s"
        )

    async def stop(self) -> None:
        """Stop the SignalConsumer service gracefully."""
        logger.info("Stopping SignalConsumer service...")
        self._running = False
        self._shutdown_event.set()

        # Stop orchestrator (which stops signal consumer)
        if self.orchestrator:
            try:
                await self.orchestrator.stop()
                logger.info("Orchestrator stopped")
            except Exception as e:
                logger.error(f"Error stopping orchestrator: {e}")

        # Clear health marker
        try:
            import redis.asyncio as redis

            redis_client = redis.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
            )
            await redis_client.delete("paper:signal_consumer:health")
            await redis_client.close()
            logger.info("Health marker cleared")
        except Exception as e:
            logger.warning(f"Failed to clear health marker: {e}")

        logger.info("SignalConsumer service stopped")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    def get_stats(self) -> dict[str, Any]:
        """Get current service statistics."""
        stats = {
            "running": self._running,
            "started_at": self._start_time.isoformat() if self._start_time else None,
            "uptime_seconds": 0,
        }

        if self._start_time:
            stats["uptime_seconds"] = (
                datetime.now(UTC) - self._start_time
            ).total_seconds()

        if self.signal_consumer:
            stats["consumer"] = self.signal_consumer.get_stats()

        return stats


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run SignalConsumer as a persistent service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings
    python scripts/run_signal_consumer.py
    
    # Run with custom poll interval
    python scripts/run_signal_consumer.py --poll-interval 10.0
    
    # Run with verbose logging
    python scripts/run_signal_consumer.py --verbose
        """,
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between polling cycles (default: 5.0)",
    )

    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=10000.0,
        help="Starting portfolio value (default: 10000.0)",
    )

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.75,
        help="Minimum confidence threshold (default: 0.75)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point for SignalConsumer runner.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_arguments()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Bootstrap environment
    logger.info("Bootstrapping environment...")
    bootstrap(load_env=True, verbose=args.verbose)

    # Create runner
    runner = SignalConsumerRunner(
        poll_interval=args.poll_interval,
        portfolio_value=args.portfolio_value,
        confidence_threshold=args.confidence_threshold,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler(sig: int, frame: Any) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        asyncio.create_task(runner.stop())

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig, None)

    try:
        # Start the service
        if not await runner.start():
            logger.error("Failed to start SignalConsumer service")
            return 1

        logger.info("SignalConsumer service is running. Press Ctrl+C to stop.")

        # Wait for shutdown
        await runner.wait_for_shutdown()

    except asyncio.CancelledError:
        logger.info("Service cancelled")
    except Exception as e:
        logger.error(f"Error during service execution: {e}", exc_info=True)
        return 1
    finally:
        # Ensure shutdown is called
        await runner.stop()

    # Print final stats
    stats = runner.get_stats()
    print("\n" + "=" * 60)
    print("SIGNAL CONSUMER SERVICE SUMMARY")
    print("=" * 60)
    print(f"Uptime: {stats.get('uptime_seconds', 0):.1f} seconds")
    if stats.get("consumer"):
        print(f"Signals Processed: {stats['consumer'].get('processed_count', 0)}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
