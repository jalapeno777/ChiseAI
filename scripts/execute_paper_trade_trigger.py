#!/usr/bin/env python3
"""Controlled paper trade trigger execution script.

Executes a single controlled paper trade through the TestTradeTrigger class
and captures comprehensive evidence.

For PAPER-LIVE-001: Controlled Paper Trade Trigger
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


async def execute_controlled_paper_trade() -> dict[str, Any]:
    """Execute a controlled paper trade and capture evidence.

    Returns:
        Dictionary with full execution evidence
    """
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchConfig, KillSwitchState
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
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "trade_parameters": {
            "symbol": "BTCUSDT",
            "direction": "long",
            "confidence": 0.85,
        },
        "components_initialized": [],
        "errors": [],
    }

    try:
        # Step 1: Initialize kill-switch executor
        logger.info("Initializing kill-switch executor...")
        kill_switch_config = KillSwitchConfig(
            drawdown_threshold_pct=15.0,
            require_reauthorization=True,
        )
        kill_switch = KillSwitchExecutor(config=kill_switch_config)

        # Check kill-switch state
        ks_state = kill_switch.state
        evidence["kill_switch_state_at_trigger"] = ks_state.value
        evidence["components_initialized"].append("kill_switch")

        # Safety check: abort if kill-switch is TRIGGERED
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

        # Set market price for BTCUSDT
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
            max_position_pct=0.10,  # 10% max position
            max_leverage=1.0,  # No leverage for safety
            min_confidence=0.75,  # 75% minimum confidence
            max_drawdown_pct=0.15,  # 15% drawdown threshold
        )
        risk_enforcer = PaperRiskEnforcer(
            config=risk_config,
            kill_switch_executor=kill_switch,
        )
        evidence["components_initialized"].append("risk_enforcer")
        evidence["risk_config"] = {
            "max_position_pct": risk_config.max_position_pct,
            "max_leverage": risk_config.max_leverage,
            "min_confidence": risk_config.min_confidence,
            "max_drawdown_pct": risk_config.max_drawdown_pct,
        }

        # Step 5: Initialize telemetry collector (optional - won't fail if InfluxDB unavailable)
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

        # Step 6: Initialize signal generator
        logger.info("Initializing signal generator...")
        signal_generator = SignalGenerator()
        evidence["components_initialized"].append("signal_generator")

        # Step 7: Initialize orchestrator
        logger.info("Initializing paper trading orchestrator...")
        orchestrator = PaperTradingOrchestrator(
            signal_generator=signal_generator,
            order_simulator=order_simulator,
            position_tracker=position_tracker,
            risk_enforcer=risk_enforcer,
            telemetry_collector=telemetry_collector,
            kill_switch=kill_switch,
            portfolio_value=10000.0,
        )
        evidence["components_initialized"].append("orchestrator")
        evidence["portfolio_value"] = 10000.0

        # Step 8: Initialize test trade trigger
        logger.info("Initializing test trade trigger...")
        test_trigger = TestTradeTrigger(
            orchestrator=orchestrator,
            kill_switch=kill_switch,
            portfolio_value=10000.0,
            max_position_pct=0.01,  # 1% max for test trades
            min_confidence=0.80,  # 80% minimum for test trades
        )
        evidence["components_initialized"].append("test_trigger")

        # Step 9: Validate readiness
        logger.info("Validating trigger readiness...")
        readiness = await test_trigger.validate_readiness()
        evidence["readiness_check"] = readiness

        if not readiness.get("ready", False):
            error_msg = f"Trigger not ready: {readiness}"
            logger.error(error_msg)
            evidence["errors"].append(error_msg)
            evidence["status"] = "NOT_READY"
            return evidence

        # Step 10: Execute the test trade
        logger.info("Executing test trade...")
        trade_result = await test_trigger.trigger_test_trade(
            symbol="BTCUSDT",
            direction="long",
            confidence=0.85,
            metadata={
                "test_run_id": f"test_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
                "triggered_by": "controlled_test_script",
            },
        )

        # Step 11: Capture full result
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

        # Step 12: Get audit log
        evidence["audit_log"] = test_trigger.get_audit_log(limit=10)
        evidence["trigger_stats"] = test_trigger.get_stats()

        # Step 13: Get orchestrator metrics
        evidence["orchestrator_metrics"] = orchestrator.get_metrics()

        # Step 14: Stop telemetry
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

    return evidence


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("CONTROLLED PAPER TRADE TRIGGER EXECUTION")
    logger.info("=" * 60)

    # Run the async execution
    evidence = asyncio.run(execute_controlled_paper_trade())

    # Output results as JSON
    print("\n" + "=" * 60)
    print("EXECUTION EVIDENCE (JSON)")
    print("=" * 60)
    print(json.dumps(evidence, indent=2, default=str))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
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
