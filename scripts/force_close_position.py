#!/usr/bin/env python3
"""Force close the paper trade position and capture close notification.

For NOTIFIER-TEST-001: Sanity Trade with Discord Notifications
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")


async def force_close_position(position_id: str, outcome_id: str) -> dict[str, Any]:
    """Force close a paper trading position.

    Args:
        position_id: The position ID to close
        outcome_id: The outcome ID for correlation

    Returns:
        Dictionary with close evidence
    """
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchConfig
    from execution.outcome_capture.integration import OutcomeCaptureIntegration
    from execution.paper.fill_model import create_fill_model
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from execution.paper.order_simulator import OrderSimulator
    from execution.paper.position_tracker import PaperPositionTracker
    from execution.paper.risk_enforcer import PaperRiskEnforcer
    from execution.paper.risk_models import RiskCheck
    from execution.telemetry.calculator import KPICalculator
    from execution.telemetry.collector import ExecutionCollector
    from execution.telemetry.exporter import ExecutionTelemetryExporter
    from signal_generation.signal_generator import SignalGenerator

    evidence: dict[str, Any] = {
        "test_id": "NOTIFIER-TEST-001-CLOSE",
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "position_id": position_id,
        "outcome_id": outcome_id,
        "components_initialized": [],
        "errors": [],
    }

    outcome_capture: OutcomeCaptureIntegration | None = None

    try:
        # Step 1: Initialize kill-switch executor
        logger.info("Initializing kill-switch executor...")
        kill_switch_config = KillSwitchConfig(
            drawdown_threshold_pct=15.0,
            require_reauthorization=True,
        )
        kill_switch = KillSwitchExecutor(config=kill_switch_config)
        evidence["components_initialized"].append("kill_switch")

        # Step 2: Initialize order simulator with market data
        logger.info("Initializing order simulator...")
        fill_model = create_fill_model()
        order_simulator = OrderSimulator(fill_model=fill_model)
        # Set a slightly higher price to simulate market movement
        order_simulator.set_market_price("BTCUSDT", 85500.0)
        evidence["market_price_set"] = {"BTCUSDT": 85500.0}
        evidence["components_initialized"].append("order_simulator")

        # Step 3: Initialize position tracker
        logger.info("Initializing position tracker...")
        position_tracker = PaperPositionTracker()
        evidence["components_initialized"].append("position_tracker")

        # Step 4: Initialize risk enforcer
        logger.info("Initializing risk enforcer...")
        risk_config = RiskCheck(
            max_position_pct=0.10,
            max_leverage=1.0,
            min_confidence=0.75,
            max_drawdown_pct=0.15,
        )
        risk_enforcer = PaperRiskEnforcer(
            config=risk_config,
            kill_switch_executor=kill_switch,
        )
        evidence["components_initialized"].append("risk_enforcer")

        # Step 5: Initialize telemetry collector
        logger.info("Initializing telemetry collector...")
        telemetry_collector = None
        try:
            from influxdb_client import InfluxDBClient as InfluxDBClientReal

            influx_client = InfluxDBClientReal(  # nosec B106
                url="http://host.docker.internal:18087",
                token="",
                org="chiseai",
            )
            exporter = ExecutionTelemetryExporter(influx_client)
            calculator = KPICalculator()
            telemetry_collector = ExecutionCollector(
                exporter=exporter,
                calculator=calculator,
                environment="paper",
                portfolio_id="test_trigger_portfolio",
            )
            await telemetry_collector.start()
            evidence["components_initialized"].append("telemetry_collector")
            evidence["telemetry_status"] = "started"
        except Exception as e:
            logger.warning(f"Telemetry initialization failed (non-blocking): {e}")
            evidence["telemetry_status"] = f"skipped: {e}"

        # Step 6: Initialize outcome capture integration
        logger.info("Initializing outcome capture integration...")
        outcome_capture = OutcomeCaptureIntegration()
        evidence["components_initialized"].append("outcome_capture")

        # Step 7: Initialize signal generator
        logger.info("Initializing signal generator...")
        signal_generator = SignalGenerator()
        evidence["components_initialized"].append("signal_generator")

        # Step 8: Initialize orchestrator WITH outcome capture
        logger.info("Initializing paper trading orchestrator...")
        orchestrator = PaperTradingOrchestrator(
            signal_generator=signal_generator,
            order_simulator=order_simulator,
            position_tracker=position_tracker,
            risk_enforcer=risk_enforcer,
            telemetry_collector=telemetry_collector,
            kill_switch=kill_switch,
            portfolio_value=10000.0,
            outcome_capture=outcome_capture,
        )
        evidence["components_initialized"].append("orchestrator")

        # Step 9: Close the position
        logger.info(f"Closing position {position_id}...")
        close_result = await orchestrator.close_position(
            position_id=position_id, exit_price=85500.0, reason="test_close"
        )

        # Handle close_result which is a tuple (position, realized_pnl) or None
        if close_result is not None and isinstance(close_result, tuple):
            position, realized_pnl = close_result
            evidence["close_result"] = {
                "position": str(position) if position else None,
                "realized_pnl": realized_pnl,
            }
            evidence["close_success"] = True
            evidence["close_pnl"] = realized_pnl
            evidence["status"] = "SUCCESS"
        elif close_result is not None:
            evidence["close_result"] = str(close_result)
            evidence["close_success"] = False
            evidence["close_error"] = str(close_result)
            evidence["status"] = "FAILED"
        else:
            evidence["close_result"] = None
            evidence["close_success"] = False
            evidence["close_error"] = "Position not found or close failed"
            evidence["status"] = "FAILED"

        # Step 10: Stop telemetry
        if telemetry_collector:
            await telemetry_collector.stop()
            evidence["telemetry_status"] = "stopped"

        logger.info(f"Position close complete: {evidence['status']}")

    except Exception as e:
        error_msg = f"Exception during close: {e}"
        logger.exception(error_msg)
        evidence["errors"].append(error_msg)
        evidence["status"] = "EXCEPTION"

    finally:
        # Close outcome capture resources
        if outcome_capture:
            try:
                await outcome_capture.close()
                logger.info("Outcome capture resources closed")
            except Exception as e:
                logger.error(f"Error closing outcome capture: {e}")

    return evidence


def main():
    """Main entry point."""
    # Get position ID from command line or use default
    position_id = (
        sys.argv[1] if len(sys.argv) > 1 else "9153c819-e016-4455-b927-d11112e6ed63"
    )
    outcome_id = (
        sys.argv[2] if len(sys.argv) > 2 else "9f534c0a-34dc-4f6f-96f0-f8d4d5aa11a7"
    )

    logger.info("=" * 70)
    logger.info("FORCE CLOSE POSITION - NOTIFIER-TEST-001")
    logger.info("=" * 70)
    logger.info(f"Position ID: {position_id}")
    logger.info(f"Outcome ID: {outcome_id}")

    # Run the async execution
    evidence = asyncio.run(force_close_position(position_id, outcome_id))

    # Output results as JSON
    print("\n" + "=" * 70)
    print("CLOSE EVIDENCE (JSON)")
    print("=" * 70)
    print(json.dumps(evidence, indent=2, default=str))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Status: {evidence.get('status', 'UNKNOWN')}")
    print(f"Position ID: {evidence.get('position_id', 'N/A')}")
    print(f"Close Order ID: {evidence.get('close_order_id', 'N/A')}")
    print(f"Close Fill Price: {evidence.get('close_fill_price', 'N/A')}")
    print(f"PnL: {evidence.get('close_pnl', 'N/A')}")

    if evidence.get("errors"):
        print(f"\nErrors: {len(evidence['errors'])}")
        for err in evidence["errors"]:
            print(f"  - {err}")

    return evidence.get("status") == "SUCCESS"


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
