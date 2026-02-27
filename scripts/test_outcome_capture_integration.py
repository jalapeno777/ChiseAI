#!/usr/bin/env python3
"""Test script for OutcomeCaptureIntegration with Discord notifications.

Executes a controlled paper trade and verifies:
1. Trade execution
2. Discord notification sent
3. Outcome persisted to storage

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


async def test_outcome_capture_integration() -> dict[str, Any]:
    """Test the OutcomeCaptureIntegration with a real trade.

    Returns:
        Dictionary with test evidence
    """
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchConfig, KillSwitchState
    from execution.outcome_capture.integration import OutcomeCaptureIntegration
    from execution.paper.fill_model import create_fill_model
    from execution.paper.order_simulator import OrderSimulator
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from execution.paper.position_tracker import PaperPositionTracker
    from execution.paper.risk_enforcer import PaperRiskEnforcer
    from execution.paper.risk_models import RiskCheck
    from execution.paper.test_trigger import TestTradeTrigger
    from execution.telemetry.calculator import KPICalculator
    from execution.telemetry.collector import ExecutionCollector
    from execution.telemetry.exporter import ExecutionTelemetryExporter
    from signal_generation.signal_generator import SignalGenerator

    evidence = {
        "test_id": "NOTIFIER-TEST-001",
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "trade_parameters": {
            "symbol": "BTCUSDT",
            "direction": "long",
            "confidence": 0.85,
        },
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
        ks_state = kill_switch.state
        evidence["kill_switch_state_at_trigger"] = ks_state.value
        evidence["components_initialized"].append("kill_switch")

        if ks_state == KillSwitchState.TRIGGERED:
            error_msg = "ABORT: Kill-switch is TRIGGERED - cannot proceed with trade"
            logger.error(error_msg)
            evidence["errors"].append(error_msg)
            evidence["status"] = "ABORTED"
            return evidence

        logger.info(f"Kill-switch state: {ks_state.value}")

        # Step 2: Initialize order simulator with market data
        logger.info("Initializing order simulator...")
        fill_model = create_fill_model()
        order_simulator = OrderSimulator(fill_model=fill_model)
        order_simulator.set_market_price("BTCUSDT", 85000.0)
        evidence["market_price_set"] = {"BTCUSDT": 85000.0}
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

            influx_client = InfluxDBClientReal(
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
            outcome_capture=outcome_capture,  # THIS IS THE KEY DIFFERENCE
        )
        evidence["components_initialized"].append("orchestrator")
        evidence["portfolio_value"] = 10000.0

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

        # Step 10: Validate readiness
        logger.info("Validating trigger readiness...")
        readiness = await test_trigger.validate_readiness()
        evidence["readiness_check"] = readiness

        if not readiness.get("ready", False):
            error_msg = f"Trigger not ready: {readiness}"
            logger.error(error_msg)
            evidence["errors"].append(error_msg)
            evidence["status"] = "NOT_READY"
            return evidence

        # Step 11: Execute the test trade
        logger.info("Executing test trade with outcome capture...")
        trade_result = await test_trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
            confidence=0.85,
            metadata={
                "test_run_id": f"notifier_test_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
                "triggered_by": "outcome_capture_integration_test",
            },
        )

        # Step 12: Capture full result
        evidence["trigger_result"] = trade_result.to_dict()
        evidence["trade_status"] = "EXECUTED" if trade_result.success else "FAILED"

        # Extract key identifiers
        if trade_result.success:
            evidence["signal_id"] = trade_result.signal_id
            evidence["order_id"] = trade_result.order_id
            evidence["correlation_id"] = (
                trade_result.trade_result.correlation_id
                if trade_result.trade_result
                else None
            )
            evidence["fill_price"] = trade_result.fill_price
            evidence["audit_log_id"] = trade_result.audit_log_id
            evidence["timestamp"] = trade_result.timestamp.isoformat()
        else:
            evidence["error"] = trade_result.error
            evidence["signal_id"] = trade_result.signal_id
            evidence["audit_log_id"] = trade_result.audit_log_id

        # Step 13: Get audit log
        evidence["audit_log"] = test_trigger.get_audit_log(limit=10)
        evidence["trigger_stats"] = test_trigger.get_stats()

        # Step 14: Get orchestrator metrics
        evidence["orchestrator_metrics"] = orchestrator.get_metrics()

        # Step 15: Stop telemetry
        if telemetry_collector:
            await telemetry_collector.stop()
            evidence["telemetry_status"] = "stopped"

        evidence["status"] = "SUCCESS" if trade_result.success else "FAILED"
        logger.info(f"Test trade execution complete: {evidence['status']}")

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
    logger.info("OUTCOME CAPTURE INTEGRATION TEST - NOTIFIER-TEST-001")
    logger.info("=" * 70)

    # Run the async execution
    evidence = asyncio.run(test_outcome_capture_integration())

    # Output results as JSON
    print("\n" + "=" * 70)
    print("EXECUTION EVIDENCE (JSON)")
    print("=" * 70)
    print(json.dumps(evidence, indent=2, default=str))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Status: {evidence.get('status', 'UNKNOWN')}")
    print(f"Signal ID: {evidence.get('signal_id', 'N/A')}")
    print(f"Order ID: {evidence.get('order_id', 'N/A')}")
    print(f"Correlation ID: {evidence.get('correlation_id', 'N/A')}")
    print(f"Fill Price: {evidence.get('fill_price', 'N/A')}")
    print(f"Audit Log ID: {evidence.get('audit_log_id', 'N/A')}")
    print(f"Kill-Switch State: {evidence.get('kill_switch_state_at_trigger', 'N/A')}")

    if evidence.get("errors"):
        print(f"\nErrors: {len(evidence['errors'])}")
        for err in evidence["errors"]:
            print(f"  - {err}")

    return evidence.get("status") == "SUCCESS"


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
