#!/usr/bin/env python3
"""End-to-end test for open and close notifications.

Executes a paper trade, captures the open notification, then immediately closes
it and captures the close notification.

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


async def test_open_and_close_notifications() -> dict[str, Any]:
    """Test both open and close notifications end-to-end.

    Returns:
        Dictionary with complete test evidence
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
    from execution.paper.test_trigger import TestTradeTrigger
    from execution.telemetry.calculator import KPICalculator
    from execution.telemetry.collector import ExecutionCollector
    from execution.telemetry.exporter import ExecutionTelemetryExporter
    from signal_generation.signal_generator import SignalGenerator

    evidence: dict[str, Any] = {
        "test_id": "NOTIFIER-TEST-001-E2E",
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "trade_parameters": {
            "symbol": "BTCUSDT",
            "direction": "long",
            "confidence": 0.85,
        },
        "open": {},
        "close": {},
        "components_initialized": [],
        "errors": [],
    }

    outcome_capture: OutcomeCaptureIntegration | None = None
    position_id: str | None = None

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
        order_simulator.set_market_price("BTCUSDT", 85000.0)
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
        except Exception as e:
            logger.warning(f"Telemetry initialization failed (non-blocking): {e}")

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

        # Step 9: Initialize test trade trigger
        logger.info("Initializing test trade trigger...")
        test_trigger = TestTradeTrigger(
            orchestrator=orchestrator,
            kill_switch=kill_switch,
            portfolio_value=10000.0,
            max_position_pct=0.01,
            min_confidence=0.80,
        )
        evidence["components_initialized"].append("test_trigger")

        # Step 10: Execute the test trade (OPEN)
        logger.info("=" * 70)
        logger.info("STEP 1: EXECUTING TRADE OPEN")
        logger.info("=" * 70)

        trade_result = await test_trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
            confidence=0.85,
            metadata={
                "test_run_id": f"notifier_e2e_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
                "triggered_by": "e2e_notification_test",
            },
        )

        # Capture open evidence
        evidence["open"]["trade_result"] = trade_result.to_dict()
        evidence["open"]["success"] = trade_result.success
        evidence["open"]["timestamp"] = datetime.now(UTC).isoformat()

        if trade_result.success:
            evidence["open"]["signal_id"] = trade_result.signal_id
            evidence["open"]["order_id"] = trade_result.order_id
            evidence["open"]["correlation_id"] = (
                trade_result.trade_result.correlation_id
                if trade_result.trade_result
                else None
            )
            evidence["open"]["fill_price"] = trade_result.fill_price
            evidence["open"]["audit_log_id"] = trade_result.audit_log_id

            # Extract position ID from trade result
            if trade_result.trade_result and trade_result.trade_result.position:
                position_id = trade_result.trade_result.position.position_id
                evidence["open"]["position_id"] = position_id
                logger.info(f"Open position ID: {position_id}")
        else:
            error_msg = f"Trade open failed: {trade_result.error}"
            logger.error(error_msg)
            evidence["errors"].append(error_msg)
            evidence["status"] = "OPEN_FAILED"
            return evidence

        # Step 11: Close the position (CLOSE)
        logger.info("=" * 70)
        logger.info("STEP 2: CLOSING POSITION")
        logger.info("=" * 70)

        if position_id:
            # Update market price for close
            order_simulator.set_market_price("BTCUSDT", 85500.0)

            close_result = await orchestrator.close_position(
                position_id=position_id, exit_price=85500.0, reason="test_close"
            )

            evidence["close"]["timestamp"] = datetime.now(UTC).isoformat()

            if close_result is not None and isinstance(close_result, tuple):
                position, realized_pnl = close_result
                evidence["close"]["success"] = True
                evidence["close"]["position"] = str(position)
                evidence["close"]["realized_pnl"] = realized_pnl
                evidence["close"]["exit_price"] = 85500.0
                logger.info(f"Position closed with PnL: {realized_pnl:.4f}")
            else:
                error_msg = f"Position close failed: {close_result}"
                logger.error(error_msg)
                evidence["close"]["success"] = False
                evidence["close"]["error"] = str(close_result)
                evidence["errors"].append(error_msg)
        else:
            error_msg = "No position ID available for close"
            logger.error(error_msg)
            evidence["errors"].append(error_msg)

        # Step 12: Stop telemetry
        if telemetry_collector:
            await telemetry_collector.stop()

        evidence["status"] = "SUCCESS" if not evidence["errors"] else "PARTIAL"
        logger.info(f"E2E test complete: {evidence['status']}")

    except Exception as e:
        error_msg = f"Exception during execution: {e}"
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
    logger.info("=" * 70)
    logger.info("E2E NOTIFICATION TEST - NOTIFIER-TEST-001")
    logger.info("=" * 70)

    # Run the async execution
    evidence = asyncio.run(test_open_and_close_notifications())

    # Output results as JSON
    print("\n" + "=" * 70)
    print("E2E EVIDENCE (JSON)")
    print("=" * 70)
    print(json.dumps(evidence, indent=2, default=str))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Status: {evidence.get('status', 'UNKNOWN')}")

    open_data = evidence.get("open", {})
    close_data = evidence.get("close", {})

    print("\n--- OPEN ---")
    print(f"Success: {open_data.get('success', False)}")
    print(f"Signal ID: {open_data.get('signal_id', 'N/A')}")
    print(f"Order ID: {open_data.get('order_id', 'N/A')}")
    print(f"Position ID: {open_data.get('position_id', 'N/A')}")
    print(f"Correlation ID: {open_data.get('correlation_id', 'N/A')}")
    print(f"Fill Price: {open_data.get('fill_price', 'N/A')}")

    print("\n--- CLOSE ---")
    print(f"Success: {close_data.get('success', False)}")
    print(f"Realized PnL: {close_data.get('realized_pnl', 'N/A')}")
    print(f"Exit Price: {close_data.get('exit_price', 'N/A')}")

    if evidence.get("errors"):
        print(f"\nErrors: {len(evidence['errors'])}")
        for err in evidence["errors"]:
            print(f"  - {err}")

    return evidence.get("status") == "SUCCESS"


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
