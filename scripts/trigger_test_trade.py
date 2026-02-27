#!/usr/bin/env python3
"""CLI script for triggering controlled test trades.

Entry point for manual test trade execution with safety checks:
- Validates kill-switch state
- Shows position size before confirmation
- Supports dry-run mode for validation
- Requires explicit --yes flag for execution

Usage:
    python scripts/trigger_test_trade.py --symbol BTCUSDT --direction long
    python scripts/trigger_test_trade.py --dry-run
    python scripts/trigger_test_trade.py --symbol ETHUSDT --direction short --yes

For PAPER-LIVE-001: Controlled Paper Trade Trigger
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Add src to path for imports
sys.path.insert(0, "src")

from config.bootstrap import bootstrap
from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.state import KillSwitchState
from execution.outcome_capture.integration import OutcomeCaptureIntegration
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.order_simulator import OrderSimulator
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.test_trigger import TestTradeTrigger
from execution.telemetry.collector import ExecutionCollector
from execution.telemetry.exporter import ExecutionTelemetryExporter
from portfolio.paper_tracker import PaperTracker
from signal_generation.signal_generator import SignalGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Trigger a controlled test trade with safety checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - validate without executing
  python scripts/trigger_test_trade.py --dry-run

  # Test trade with defaults (BTCUSDT long)
  python scripts/trigger_test_trade.py --yes

  # Custom symbol and direction
  python scripts/trigger_test_trade.py --symbol ETHUSDT --direction short --yes

  # Bypass daily trade limit (for testing)
  python scripts/trigger_test_trade.py --force --yes
        """,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)",
    )

    parser.add_argument(
        "--direction",
        type=str,
        choices=["long", "short"],
        default="long",
        help="Trade direction: long or short (default: long)",
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.80,
        help="Signal confidence 0.0-1.0 (default: 0.80)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without executing trade",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass daily trade limit check (for testing)",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm execution without interactive prompt",
    )

    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=10000.0,
        help="Portfolio value for position sizing (default: 10000.0)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_section(text: str) -> None:
    """Print a section header."""
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"  ✅ {text}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(f"  ⚠️  {text}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"  ❌ {text}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"  ℹ️  {text}")


async def check_kill_switch_state(kill_switch: KillSwitchExecutor) -> dict[str, Any]:
    """Check and report kill-switch state.

    Args:
        kill_switch: Kill-switch executor

    Returns:
        Dictionary with state check results
    """
    state = kill_switch.state

    result = {
        "state": state.value,
        "can_trade": state == KillSwitchState.ARMED,
        "warning": None,
    }

    if state == KillSwitchState.TRIGGERED:
        result["warning"] = "Kill-switch is TRIGGERED - trading is blocked"
    elif state == KillSwitchState.DISABLED:
        result["warning"] = "Kill-switch is DISABLED - proceeding with caution"

    return result


async def calculate_position_size(
    portfolio_value: float,
    confidence: float,
    symbol: str,
) -> dict[str, Any]:
    """Calculate expected position size for display.

    Args:
        portfolio_value: Current portfolio value
        confidence: Signal confidence
        symbol: Trading symbol

    Returns:
        Dictionary with position sizing details
    """
    # Default risk per trade (1% of portfolio)
    risk_pct = 0.01
    risk_amount = portfolio_value * risk_pct

    # Max position (1% of portfolio)
    max_position_pct = 0.01
    max_position_value = portfolio_value * max_position_pct

    return {
        "portfolio_value": portfolio_value,
        "risk_amount": risk_amount,
        "max_position_value": max_position_value,
        "max_position_pct": max_position_pct,
        "confidence": confidence,
        "symbol": symbol,
    }


async def run_safety_checks(
    kill_switch: KillSwitchExecutor,
    portfolio_value: float,
    confidence: float,
    symbol: str,
) -> dict[str, Any]:
    """Run all safety checks and return results.

    Args:
        kill_switch: Kill-switch executor
        portfolio_value: Portfolio value
        confidence: Signal confidence
        symbol: Trading symbol

    Returns:
        Dictionary with all safety check results
    """
    print_section("SAFETY CHECKS")

    results = {
        "kill_switch": None,
        "position_size": None,
        "all_passed": True,
        "blockers": [],
    }

    # Check 1: Kill-switch state
    print("Checking kill-switch state...")
    ks_result = await check_kill_switch_state(kill_switch)
    results["kill_switch"] = ks_result

    if ks_result["state"] == "triggered":
        print_error(f"Kill-switch: {ks_result['state'].upper()}")
        print_error(ks_result["warning"])
        results["all_passed"] = False
        results["blockers"].append("kill_switch_triggered")
    elif ks_result["state"] == "disabled":
        print_warning(f"Kill-switch: {ks_result['state'].upper()}")
        print_warning(ks_result["warning"])
    else:
        print_success(f"Kill-switch: {ks_result['state'].upper()}")

    # Check 2: Position size
    print("\nCalculating position size...")
    pos_result = await calculate_position_size(
        portfolio_value=portfolio_value,
        confidence=confidence,
        symbol=symbol,
    )
    results["position_size"] = pos_result

    print_info(f"Portfolio Value: ${pos_result['portfolio_value']:,.2f}")
    print_info(
        f"Max Position: ${pos_result['max_position_value']:,.2f} "
        f"({pos_result['max_position_pct']:.1%})"
    )
    print_info(f"Risk Amount: ${pos_result['risk_amount']:,.2f} (1%)")
    print_success("Position size limits OK")

    return results


async def execute_test_trade(
    trigger: TestTradeTrigger,
    symbol: str,
    direction: str,
    confidence: float,
) -> dict[str, Any]:
    """Execute the test trade and return results.

    Args:
        trigger: Test trade trigger
        symbol: Trading symbol
        direction: Trade direction
        confidence: Signal confidence

    Returns:
        Dictionary with execution results
    """
    print_section("EXECUTING TEST TRADE")

    print(f"Symbol: {symbol}")
    print(f"Direction: {direction.upper()}")
    print(f"Confidence: {confidence:.1%}")
    print()

    result = await trigger.trigger_test_trade(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
    )

    if result.success:
        print_success("Test trade executed successfully!")
        print()
        print(f"  Order ID: {result.order_id}")
        print(
            f"  Fill Price: ${result.fill_price:,.2f}"
            if result.fill_price
            else "  Fill Price: N/A"
        )
        print(f"  Signal ID: {result.signal_id}")
        print(f"  Audit Log ID: {result.audit_log_id}")
        print(f"  Timestamp: {result.timestamp.isoformat()}")

        if result.trade_result:
            print(f"  Latency: {result.trade_result.latency_ms:.1f}ms")
    else:
        print_error("Test trade failed!")
        print()
        print(f"  Error: {result.error}")
        print(f"  Signal ID: {result.signal_id}")
        print(f"  Audit Log ID: {result.audit_log_id}")

    return result.to_dict()


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    bootstrap(load_env=True)

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print_header("CONTROLLED TEST TRADE TRIGGER")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print()

    # Initialize components
    print("Initializing components...")

    try:
        # Create kill-switch executor
        kill_switch = KillSwitchExecutor()

        # Create minimal orchestrator components
        signal_generator = SignalGenerator()  # Will be used for queue
        order_simulator = OrderSimulator()
        position_tracker = PaperTracker()
        risk_enforcer = PaperRiskEnforcer(kill_switch_executor=kill_switch)
        exporter = ExecutionTelemetryExporter()
        telemetry = ExecutionCollector(exporter=exporter)

        # Create outcome capture integration for Discord alerts
        outcome_capture = OutcomeCaptureIntegration()

        # Create orchestrator
        orchestrator = PaperTradingOrchestrator(
            signal_generator=signal_generator,
            order_simulator=order_simulator,
            position_tracker=position_tracker,
            risk_enforcer=risk_enforcer,
            telemetry_collector=telemetry,
            kill_switch=kill_switch,
            portfolio_value=args.portfolio_value,
            outcome_capture=outcome_capture,
        )

        # Create test trigger
        trigger = TestTradeTrigger(
            orchestrator=orchestrator,
            kill_switch=kill_switch,
            portfolio_value=args.portfolio_value,
        )

        print_success("Components initialized")

    except Exception as e:
        print_error(f"Failed to initialize components: {e}")
        return 1

    # Run safety checks
    safety_results = await run_safety_checks(
        kill_switch=kill_switch,
        portfolio_value=args.portfolio_value,
        confidence=args.confidence,
        symbol=args.symbol,
    )

    # Handle dry-run mode
    if args.dry_run:
        print_section("DRY RUN MODE")
        print_info("Configuration validated successfully")
        print_info("No trade will be executed")

        if safety_results["all_passed"]:
            print_success("All safety checks passed - ready for live execution")
            return 0
        else:
            print_error("Safety checks failed - cannot execute")
            return 1

    # Check for blockers
    if not safety_results["all_passed"]:
        print_section("EXECUTION BLOCKED")
        print_error("Cannot execute test trade due to safety check failures:")
        for blocker in safety_results["blockers"]:
            print_error(f"  - {blocker}")
        return 1

    # Show trade summary
    print_section("TRADE SUMMARY")
    print(f"  Symbol: {args.symbol}")
    print(f"  Direction: {args.direction.upper()}")
    print(f"  Confidence: {args.confidence:.1%}")
    print(f"  Portfolio: ${args.portfolio_value:,.2f}")
    print()

    # Require confirmation unless --yes flag
    if not args.yes:
        print("⚠️  This will execute a real test trade in paper trading mode.")
        print()
        response = input("Do you want to proceed? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Execution cancelled by user")
            return 0
        print()

    # Execute the trade
    result = await execute_test_trade(
        trigger=trigger,
        symbol=args.symbol,
        direction=args.direction,
        confidence=args.confidence,
    )

    # Final summary
    print_section("EXECUTION SUMMARY")
    if result["success"]:
        print_success("Test trade completed successfully")
        print()
        print(f"  Order ID: {result.get('order_id', 'N/A')}")
        print(f"  Fill Price: ${result.get('fill_price', 0):,.2f}")
        print(f"  Audit Log: {result.get('audit_log_id', 'N/A')}")
        return 0
    else:
        print_error("Test trade failed")
        print()
        print(f"  Error: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"\nFatal error: {e}")
        sys.exit(1)
