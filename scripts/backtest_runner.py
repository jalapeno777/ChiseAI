#!/usr/bin/env python3
"""Standalone script for continuous backtest runner.

This script provides a command-line interface for running the continuous
backtest runner. It can be run as a daemon process for always-on operation.

Usage:
    # Start continuous backtest runner
    python scripts/backtest_runner.py --start

    # Run single backtest
    python scripts/backtest_runner.py --strategy strategy_001

    # Run walk-forward backtests for all active strategies
    python scripts/backtest_runner.py --walk-forward

    # Check status
    python scripts/backtest_runner.py --status

    # Stop runner
    python scripts/backtest_runner.py --stop

Environment Variables:
    INFLUXDB_URL: InfluxDB URL (default: http://chiseai-influxdb:8086)
    INFLUXDB_TOKEN: InfluxDB token (default: chiseai-token)
    INFLUXDB_ORG: InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET: InfluxDB bucket (default: chiseai)
    BACKTEST_MAX_CONCURRENT: Max concurrent backtests (default: 3)
    BACKTEST_RECOVERY_DELAY: Recovery delay in seconds (default: 60)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap
from operations.backtest_runner import (
    BacktestKPIs,
    BacktestRunner,
    BacktestStatus,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("backtest_runner_script")


class BacktestRunnerService:
    """Service wrapper for running backtest runner as a daemon."""

    def __init__(self) -> None:
        """Initialize the service."""
        self.runner: BacktestRunner | None = None
        self._shutdown_event = asyncio.Event()

    async def start(
        self,
        max_concurrent: int = 3,
        recovery_delay_seconds: float = 60.0,
    ) -> None:
        """Start the continuous backtest runner service.

        Args:
            max_concurrent: Maximum concurrent backtests
            recovery_delay_seconds: Recovery delay after failure
        """
        logger.info("Starting backtest runner service...")

        # Create runner with config from environment
        self.runner = BacktestRunner(
            max_concurrent=max_concurrent,
            recovery_delay_seconds=recovery_delay_seconds,
        )

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        # Start runner
        await self.runner.start()

        logger.info("Backtest runner service started successfully")
        logger.info("Press Ctrl+C to stop")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Graceful shutdown
        await self.stop()

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def stop(self) -> None:
        """Stop the service gracefully."""
        logger.info("Stopping backtest runner service...")

        if self.runner:
            await self.runner.stop()
            self.runner = None

        logger.info("Backtest runner service stopped")

    async def run_single_backtest(self, strategy_id: str) -> BacktestKPIs:
        """Run a single backtest.

        Args:
            strategy_id: Strategy identifier

        Returns:
            BacktestKPIs with results
        """
        logger.info(f"Running single backtest for strategy: {strategy_id}")

        runner = BacktestRunner()
        kpis = await runner.run_backtest(strategy_id=strategy_id)

        logger.info(f"Backtest completed with status: {kpis.status.value}")
        logger.info(f"  Sharpe Ratio: {kpis.sharpe_ratio:.2f}")
        logger.info(f"  Max Drawdown: {kpis.max_drawdown_pct:.2f}%")
        logger.info(f"  Win Rate: {kpis.win_rate_pct:.1f}%")
        logger.info(f"  Trade Count: {kpis.trade_count}")

        return kpis

    async def run_walk_forward(
        self,
        strategy_ids: list[str] | None = None,
    ) -> list[BacktestKPIs]:
        """Run walk-forward backtests.

        Args:
            strategy_ids: List of strategy IDs (uses defaults if None)

        Returns:
            List of BacktestKPIs
        """
        if strategy_ids is None:
            # Default active strategies
            strategy_ids = [
                "grid_btc_usdt",
                "grid_eth_usdt",
                "momentum_btc",
                "mean_reversion_eth",
            ]

        logger.info(
            f"Running walk-forward backtests for {len(strategy_ids)} strategies"
        )

        runner = BacktestRunner()
        await runner.start()

        try:
            results = await runner.run_walk_forward_backtests(strategy_ids)
            logger.info(f"Submitted {len(strategy_ids)} walk-forward backtests")

            # Wait a bit for processing
            await asyncio.sleep(5.0)

        finally:
            await runner.stop()

        return results

    def get_status(self) -> dict:
        """Get current runner status.

        Returns:
            Dictionary with status information
        """
        if self.runner is None:
            return {
                "status": "not_running",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # This would need to be enhanced to actually query the runner state
        return {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Bootstrap environment first
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Continuous Backtest Runner for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start continuous runner
  python backtest_runner.py --start

  # Run single backtest
  python backtest_runner.py --strategy strategy_001

  # Run walk-forward backtests
  python backtest_runner.py --walk-forward

  # Check status
  python backtest_runner.py --status
        """,
    )

    parser.add_argument(
        "--start",
        action="store_true",
        help="Start continuous backtest runner",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop continuous backtest runner",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check runner status",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        help="Run single backtest for strategy ID",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward backtests for active strategies",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=int(os.getenv("BACKTEST_MAX_CONCURRENT", "3")),
        help="Maximum concurrent backtests (default: 3)",
    )
    parser.add_argument(
        "--recovery-delay",
        type=float,
        default=float(os.getenv("BACKTEST_RECOVERY_DELAY", "60")),
        help="Recovery delay in seconds (default: 60)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    service = BacktestRunnerService()

    try:
        if args.start:
            await service.start(
                max_concurrent=args.max_concurrent,
                recovery_delay_seconds=args.recovery_delay,
            )
            return 0

        elif args.stop:
            await service.stop()
            return 0

        elif args.status:
            status = service.get_status()
            print(f"Status: {status['status']}")
            print(f"Timestamp: {status['timestamp']}")
            return 0

        elif args.strategy:
            kpis = await service.run_single_backtest(args.strategy)
            return 0 if kpis.status == BacktestStatus.COMPLETED else 1

        elif args.walk_forward:
            await service.run_walk_forward()
            return 0

        else:
            parser.print_help()
            return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await service.stop()
        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
