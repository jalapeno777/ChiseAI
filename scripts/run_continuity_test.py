#!/usr/bin/env python3
"""Continuity test script for P0-REPAIR-001.

Runs a 20-30 minute test to verify end-to-end pipeline continuity:
- Signals → Orders → Fills → Positions → Discord alerts

Captures state every 5 minutes and reports deltas.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as redis

from config.bootstrap import bootstrap
from config.trading_mode import TradingModeConfig, TradingMode, ModuleType
from data_ingestion.ohlcv_fetcher import OHLCVFetcher
from data_ingestion.timeframe_config import Timeframe
from execution.kill_switch.executor import KillSwitchExecutor
from execution.paper import create_simulator
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.risk_models import RiskCheck
from execution.paper.signal_consumer import SignalConsumer
from execution.paper.position_tracker import PaperPositionTracker
from execution.telemetry.collector import ExecutionCollector
from execution.telemetry.exporter import ExecutionTelemetryExporter
from execution.paper.position_tracker import PaperPositionTracker
from signal_generation.signal_generator import SignalGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ContinuityTest:
    """Runs continuity test and captures state snapshots."""

    def __init__(self, duration_seconds: int = 1800):
        self.duration = duration_seconds
        self.snapshots = []
        self.redis_client = None
        self.orchestrator = None
        self.signal_consumer = None

    async def _get_redis(self):
        """Get Redis client."""
        if self.redis_client is None:
            self.redis_client = redis.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
            )
        return self.redis_client

    async def capture_state(self, label: str) -> dict:
        """Capture current state from Redis."""
        redis = await self._get_redis()

        # Count keys
        signal_keys = await redis.keys("bmad:chiseai:signals:*")
        order_keys = await redis.keys("paper:order:*")
        position_keys = await redis.keys("paper:position:*")
        fill_keys = await redis.keys("paper:fill:*")

        # Get paper trading status
        status = await redis.get("paper_trading:status")

        # Get processed signals count
        processed = await redis.scard("bmad:chiseai:signals:processed")

        state = {
            "timestamp": datetime.now(UTC).isoformat(),
            "label": label,
            "signals": len(signal_keys),
            "orders": len(order_keys),
            "positions": len(position_keys),
            "fills": len(fill_keys),
            "processed_signals": processed or 0,
            "paper_status": status or "unknown",
        }

        return state

    async def print_state(self, state: dict):
        """Print state in readable format."""
        print(f"\n{'=' * 60}")
        print(f"STATE SNAPSHOT: {state['label']}")
        print(f"Timestamp: {state['timestamp']}")
        print(f"{'=' * 60}")
        print(f"  Signals:           {state['signals']}")
        print(f"  Orders:            {state['orders']}")
        print(f"  Positions:         {state['positions']}")
        print(f"  Fills:             {state['fills']}")
        print(f"  Processed Signals: {state['processed_signals']}")
        print(f"  Paper Status:      {state['paper_status']}")
        print(f"{'=' * 60}\n")

    async def setup(self):
        """Initialize all components."""
        logger.info("Bootstrapping environment...")
        bootstrap(load_env=True, verbose=False)

        # Create config
        config = TradingModeConfig.create_paper_config(
            portfolio_value=10000.0,
            signal_threshold=0.75,
        )

        logger.info("Initializing components...")

        # Initialize components
        fetcher = OHLCVFetcher()
        signal_generator = SignalGenerator(config=None)
        order_simulator = create_simulator()
        position_tracker = PaperPositionTracker()

        risk_config = RiskCheck(
            min_confidence=0.75,
            max_position_pct=0.2,
        )
        risk_enforcer = PaperRiskEnforcer(config=risk_config)
        kill_switch = KillSwitchExecutor()

        # Create telemetry
        try:
            exporter = ExecutionTelemetryExporter(influxdb_client=None)
            telemetry = ExecutionCollector(exporter=exporter, environment="paper")
        except Exception as e:
            logger.warning(f"Telemetry init failed: {e}")
            telemetry = None

        # Create orchestrator
        self.orchestrator = PaperTradingOrchestrator(
            signal_generator=signal_generator,
            order_simulator=order_simulator,
            position_tracker=position_tracker,
            risk_enforcer=risk_enforcer,
            telemetry_collector=telemetry,
            kill_switch=kill_switch,
            portfolio_value=10000.0,
        )

        # Create signal consumer
        self.signal_consumer = SignalConsumer(
            orchestrator=self.orchestrator,
            poll_interval=5.0,
        )

        # Start orchestrator
        await self.orchestrator.start()

        logger.info("Setup complete!")

    async def teardown(self):
        """Shutdown all components."""
        logger.info("Shutting down...")
        if self.orchestrator:
            await self.orchestrator.stop()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Shutdown complete!")

    async def run(self):
        """Run the continuity test."""
        try:
            await self.setup()

            # Capture T-0 state
            t0 = await self.capture_state("T-0 (Pre-test)")
            await self.print_state(t0)
            self.snapshots.append(t0)

            # Start signal consumer
            await self.signal_consumer.start()
            logger.info(f"Signal consumer started, running for {self.duration}s...")

            # Run test with periodic snapshots
            start_time = time.time()
            snapshot_times = [
                0,
                300,
                600,
                900,
                1200,
                1500,
                1800,
            ]  # 0, 5, 10, 15, 20, 25, 30 min
            next_snapshot_idx = 1

            while time.time() - start_time < self.duration:
                elapsed = time.time() - start_time

                # Check if it's time for a snapshot
                if next_snapshot_idx < len(snapshot_times):
                    target_time = snapshot_times[next_snapshot_idx]
                    if elapsed >= target_time:
                        label = f"T+{target_time // 60}min"
                        state = await self.capture_state(label)
                        await self.print_state(state)
                        self.snapshots.append(state)
                        next_snapshot_idx += 1

                # Print progress every minute
                if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                    logger.info(
                        f"Test running... {int(elapsed)}/{self.duration}s elapsed"
                    )

                await asyncio.sleep(1)

            # Capture final state
            tf = await self.capture_state("T-End (Post-test)")
            await self.print_state(tf)
            self.snapshots.append(tf)

            # Generate report
            await self.generate_report()

        finally:
            await self.teardown()

    async def generate_report(self):
        """Generate final continuity test report."""
        print("\n" + "=" * 60)
        print("CONTINUITY TEST REPORT")
        print("=" * 60)

        if len(self.snapshots) < 2:
            print("ERROR: Not enough snapshots for report")
            return

        t0 = self.snapshots[0]
        tf = self.snapshots[-1]

        # Calculate deltas
        deltas = {
            "signals": tf["signals"] - t0["signals"],
            "orders": tf["orders"] - t0["orders"],
            "positions": tf["positions"] - t0["positions"],
            "fills": tf["fills"] - t0["fills"],
            "processed": tf["processed_signals"] - t0["processed_signals"],
        }

        print(f"\nDELTAS (Changes during test):")
        print(f"  Signals:   {deltas['signals']:+d}")
        print(f"  Orders:    {deltas['orders']:+d}")
        print(f"  Positions: {deltas['positions']:+d}")
        print(f"  Fills:     {deltas['fills']:+d}")
        print(f"  Processed: {deltas['processed']:+d}")

        # Gate evaluation
        print(f"\nGATE RESULTS:")
        gates = {
            "G1 (Signal growth)": deltas["signals"] > 0 or deltas["processed"] > 0,
            "G2 (Order creation)": deltas["orders"] > 0,
            "G3 (Fill recording)": deltas["fills"] > 0,
            "G4 (Position persistence)": deltas["positions"] > 0 or tf["positions"] > 0,
            "G5 (Signal processing)": deltas["processed"] > 0,
        }

        all_passed = True
        for gate, passed in gates.items():
            status = "PASS" if passed else "FAIL"
            print(f"  {gate}: {status}")
            if not passed:
                all_passed = all_passed and False

        print(f"\nOVERALL: {'ALL GATES PASSED' if all_passed else 'SOME GATES FAILED'}")
        print("=" * 60)

        # Save report to file
        report = {
            "test_type": "continuity_test",
            "duration_seconds": self.duration,
            "snapshots": self.snapshots,
            "deltas": deltas,
            "gates": {k: v for k, v in gates.items()},
            "all_passed": all_passed,
        }

        output_dir = Path("_bmad-output")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filepath = output_dir / f"continuity-test-report-{timestamp}.json"

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nReport saved to: {filepath}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run continuity test")
    parser.add_argument(
        "--duration",
        type=int,
        default=600,  # 10 minutes default for testing
        help="Test duration in seconds (default: 600 = 10 min)",
    )
    args = parser.parse_args()

    test = ContinuityTest(duration_seconds=args.duration)
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
