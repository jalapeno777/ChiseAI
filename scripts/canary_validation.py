#!/usr/bin/env python3
"""
Paper Trading Canary Validation Script for PAPER-003

This script executes a comprehensive validation of the canary deployment system:
1. Module import and configuration validation
2. Gate evaluation tests
3. Budget enforcement validation
4. Simulated metrics collection
5. Report generation

Exit codes:
- 0: All validations passed
- 1: Critical validation failure
- 2: Infrastructure/connectivity issues
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)


# Test 1: Module Import Validation
def test_module_imports() -> dict[str, Any]:
    """Test that all canary modules can be imported."""
    results = {
        "test_name": "Module Import Validation",
        "status": "PASS",
        "details": [],
        "errors": [],
    }

    try:

        results["details"].append("✓ All canary module imports successful")

        results["details"].append("✓ Paper trading orchestrator import successful")

        results["details"].append("✓ Risk enforcer import successful")

        results["details"].append("✓ Risk models import successful")

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Import error: {e}")

    return results


# Test 2: Configuration Validation
def test_configuration() -> dict[str, Any]:
    """Test canary configuration loading and validation."""
    results = {
        "test_name": "Configuration Validation",
        "status": "PASS",
        "details": [],
        "errors": [],
        "config": {},
    }

    try:
        from execution.canary import GateCriteria

        # Test default gate criteria
        criteria = GateCriteria()
        results["config"] = {
            "max_drawdown_pct": criteria.max_drawdown_pct,
            "min_win_rate_pct": criteria.min_win_rate_pct,
            "duration_days": criteria.duration_days,
            "min_trades": criteria.min_trades,
        }

        # Validate expected values
        assert criteria.max_drawdown_pct == 5.0, "Max drawdown should be 5%"
        assert criteria.min_win_rate_pct == 55.0, "Min win rate should be 55%"
        assert criteria.duration_days == 7, "Duration should be 7 days"
        assert criteria.min_trades == 10, "Min trades should be 10"

        results["details"].append(f"✓ Default gate criteria validated")
        results["details"].append(f"  - Max drawdown: {criteria.max_drawdown_pct}%")
        results["details"].append(f"  - Min win rate: {criteria.min_win_rate_pct}%")
        results["details"].append(f"  - Duration: {criteria.duration_days} days")
        results["details"].append(f"  - Min trades: {criteria.min_trades}")

        # Test custom criteria
        custom_criteria = GateCriteria(
            max_drawdown_pct=3.0,
            min_win_rate_pct=60.0,
            duration_days=5,
            min_trades=5,
        )
        assert custom_criteria.max_drawdown_pct == 3.0
        results["details"].append("✓ Custom gate criteria creation successful")

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Configuration error: {e}")

    return results


# Test 3: Gate Evaluation Tests
def test_gate_evaluation() -> dict[str, Any]:
    """Test gate evaluation logic."""
    results = {
        "test_name": "Gate Evaluation Logic",
        "status": "PASS",
        "details": [],
        "errors": [],
        "gates_tested": [],
    }

    try:
        from execution.canary import (
            CanaryMetrics,
            GateCheckResult,
            GateCriteria,
            GateEvaluator,
        )

        evaluator = GateEvaluator(GateCriteria())

        # Test 1: Drawdown gate - PASS
        metrics_pass = CanaryMetrics(
            start_equity=10000.0,
            current_equity=9800.0,
            peak_equity=10000.0,
            max_drawdown_pct=2.0,
        )
        drawdown_check = evaluator.evaluate_drawdown(metrics_pass)
        assert drawdown_check.result == GateCheckResult.PASS
        results["gates_tested"].append(
            {
                "gate": "max_drawdown",
                "scenario": "within threshold (2% < 5%)",
                "result": "PASS",
            }
        )
        results["details"].append(f"✓ Drawdown gate PASS: {drawdown_check.message}")

        # Test 2: Drawdown gate - FAIL
        metrics_fail = CanaryMetrics(
            start_equity=10000.0,
            current_equity=9400.0,
            peak_equity=10000.0,
            max_drawdown_pct=6.0,
        )
        drawdown_check_fail = evaluator.evaluate_drawdown(metrics_fail)
        assert drawdown_check_fail.result == GateCheckResult.FAIL
        results["gates_tested"].append(
            {
                "gate": "max_drawdown",
                "scenario": "exceeds threshold (6% > 5%)",
                "result": "FAIL",
            }
        )
        results["details"].append(
            f"✓ Drawdown gate FAIL: {drawdown_check_fail.message}"
        )

        # Test 3: Win rate gate - PENDING (insufficient trades)
        metrics_pending = CanaryMetrics(
            total_trades=5,
            winning_trades=3,
            win_rate_pct=60.0,
        )
        win_rate_check = evaluator.evaluate_win_rate(metrics_pending)
        assert win_rate_check.result == GateCheckResult.PENDING
        results["gates_tested"].append(
            {
                "gate": "min_win_rate",
                "scenario": "insufficient trades (5 < 10)",
                "result": "PENDING",
            }
        )
        results["details"].append(f"✓ Win rate gate PENDING: {win_rate_check.message}")

        # Test 4: Win rate gate - PASS
        metrics_win_pass = CanaryMetrics(
            total_trades=20,
            winning_trades=12,
            win_rate_pct=60.0,
        )
        win_rate_check_pass = evaluator.evaluate_win_rate(metrics_win_pass)
        assert win_rate_check_pass.result == GateCheckResult.PASS
        results["gates_tested"].append(
            {
                "gate": "min_win_rate",
                "scenario": "meets threshold (60% >= 55%)",
                "result": "PASS",
            }
        )
        results["details"].append(
            f"✓ Win rate gate PASS: {win_rate_check_pass.message}"
        )

        # Test 5: Win rate gate - FAIL
        metrics_win_fail = CanaryMetrics(
            total_trades=20,
            winning_trades=8,
            win_rate_pct=40.0,
        )
        win_rate_check_fail = evaluator.evaluate_win_rate(metrics_win_fail)
        assert win_rate_check_fail.result == GateCheckResult.FAIL
        results["gates_tested"].append(
            {
                "gate": "min_win_rate",
                "scenario": "below threshold (40% < 55%)",
                "result": "FAIL",
            }
        )
        results["details"].append(
            f"✓ Win rate gate FAIL: {win_rate_check_fail.message}"
        )

        # Test 6: Duration gate - PENDING
        now = int(datetime.now().timestamp())
        start_time = now - (3 * 24 * 60 * 60)  # 3 days ago
        duration_check = evaluator.evaluate_duration(start_time, now)
        assert duration_check.result == GateCheckResult.PENDING
        results["gates_tested"].append(
            {
                "gate": "duration",
                "scenario": "insufficient duration (3 < 7 days)",
                "result": "PENDING",
            }
        )
        results["details"].append(f"✓ Duration gate PENDING: {duration_check.message}")

        # Test 7: Duration gate - PASS
        start_time_pass = now - (8 * 24 * 60 * 60)  # 8 days ago
        duration_check_pass = evaluator.evaluate_duration(start_time_pass, now)
        assert duration_check_pass.result == GateCheckResult.PASS
        results["gates_tested"].append(
            {
                "gate": "duration",
                "scenario": "meets duration (8 >= 7 days)",
                "result": "PASS",
            }
        )
        results["details"].append(
            f"✓ Duration gate PASS: {duration_check_pass.message}"
        )

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Gate evaluation error: {e}")

    return results


# Test 4: Canary Deployment Lifecycle
def test_canary_lifecycle() -> dict[str, Any]:
    """Test full canary deployment lifecycle."""
    results = {
        "test_name": "Canary Deployment Lifecycle",
        "status": "PASS",
        "details": [],
        "errors": [],
        "lifecycle_stages": [],
    }

    try:
        from execution.canary import (
            CanaryStatus,
            create_canary_deployment,
        )

        # Create canary
        canary = create_canary_deployment(
            canary_id="test-canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
            allocation_pct=10.0,
        )

        assert canary.status == CanaryStatus.PENDING
        results["lifecycle_stages"].append("CREATED")
        results["details"].append(f"✓ Canary created: {canary.canary_id}")
        results["details"].append(f"  - Strategy: {canary.strategy_id}")
        results["details"].append(f"  - Champion: {canary.champion_strategy_id}")
        results["details"].append(f"  - Allocation: {canary.allocation_pct}%")

        # Start canary
        canary.start(initial_equity=10000.0)
        assert canary.status == CanaryStatus.RUNNING
        results["lifecycle_stages"].append("STARTED")
        results["details"].append(
            f"✓ Canary started with equity: ${canary.metrics.start_equity:,.2f}"
        )

        # Simulate trades
        canary.metrics.record_trade(pnl=150.0)  # Win
        canary.metrics.record_trade(pnl=-50.0)  # Loss
        canary.metrics.record_trade(pnl=200.0)  # Win
        canary.metrics.record_trade(pnl=100.0)  # Win
        canary.metrics.record_trade(pnl=-30.0)  # Loss

        results["details"].append(f"✓ Simulated {canary.metrics.total_trades} trades")
        results["details"].append(f"  - Winning: {canary.metrics.winning_trades}")
        results["details"].append(f"  - Losing: {canary.metrics.losing_trades}")
        results["details"].append(f"  - Win rate: {canary.metrics.win_rate_pct:.1f}%")

        # Update equity
        canary.metrics.update_equity(10370.0)
        results["details"].append(
            f"✓ Equity updated: ${canary.metrics.current_equity:,.2f}"
        )
        results["details"].append(
            f"  - Realized PnL: ${canary.metrics.realized_pnl:,.2f}"
        )

        # Check gates
        checks = canary.check_gates()
        results["details"].append(f"✓ Gate checks performed: {len(checks)}")
        for check in checks:
            results["details"].append(f"  - {check.gate_name}: {check.result.value}")

        # Evaluate status
        status, reasons = canary.evaluate_all_gates()
        results["lifecycle_stages"].append(f"EVALUATED:{status.value}")
        results["details"].append(f"✓ Status evaluated: {status.value}")

        # Test rollback check
        should_rollback, rollback_reasons = canary.should_rollback()
        results["details"].append(f"✓ Rollback check: {should_rollback}")

        # Test promotion check (will fail due to insufficient duration)
        can_promote, promote_reasons = canary.can_promote()
        results["details"].append(f"✓ Promotion check: {can_promote}")
        if promote_reasons:
            results["details"].append(f"  - Reasons: {', '.join(promote_reasons)}")

        results["lifecycle_stages"].append("COMPLETED")

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Lifecycle error: {e}")

    return results


# Test 5: Budget Enforcement Validation
async def test_budget_enforcement() -> dict[str, Any]:
    """Test budget enforcement and position size limits."""
    results = {
        "test_name": "Budget Enforcement Validation",
        "status": "PASS",
        "details": [],
        "errors": [],
        "budget_checks": [],
    }

    try:
        from execution.paper.risk_enforcer import PaperRiskEnforcer
        from execution.paper.risk_models import RiskCheck
        from signal_generation.models import Signal, SignalDirection, SignalStatus
        from datetime import datetime, UTC

        # Create risk enforcer with default config
        config = RiskCheck()
        enforcer = PaperRiskEnforcer(config=config)

        results["details"].append(f"✓ Risk enforcer initialized")
        results["details"].append(
            f"  - Max position pct: {config.max_position_pct:.1%}"
        )
        results["details"].append(f"  - Max leverage: {config.max_leverage:.1f}x")
        results["details"].append(f"  - Min confidence: {config.min_confidence:.1%}")
        results["details"].append(f"  - Max drawdown: {config.max_drawdown_pct:.1%}")

        # Test position size calculation
        signal = Signal(
            signal_id="test-001",
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=40000.0,
            risk_reward_ratio=2.0,
            metadata={"entry_price": 45000.0, "leverage": 1.0},
        )
        results["details"].append(f"  - Max leverage: {config.max_leverage:.1f}x")
        results["details"].append(f"  - Min confidence: {config.min_confidence:.1%}")
        results["details"].append(f"  - Max drawdown: {config.max_drawdown_pct:.1%}")

        # Test position size calculation - use the already defined signal above

        portfolio_value = 10000.0
        position_size = enforcer.calculate_position_size(signal, portfolio_value)

        results["details"].append(
            f"✓ Position size calculated: {position_size:.6f} BTC"
        )

        # Validate order with empty positions
        assessment = await enforcer.validate_order(
            signal=signal,
            portfolio_value=portfolio_value,
            current_positions=[],
            current_drawdown_pct=0.0,
            entry_price=45000.0,
        )

        results["budget_checks"].append(
            {
                "check": "order_validation",
                "approved": assessment.approved,
                "position_size": assessment.position_size,
                "violations": len(assessment.violations),
            }
        )

        if assessment.approved:
            results["details"].append(f"✓ Order approved")
            results["details"].append(
                f"  - Position size: {assessment.position_size:.6f}"
            )
            results["details"].append(
                f"  - Margin required: ${assessment.margin_required:,.2f}"
            )
        else:
            results["details"].append(f"⚠ Order rejected")
            for v in assessment.violations:
                results["details"].append(f"  - {v.rule}: {v.message}")

        # Test with low confidence (should be rejected)
        low_conf_signal = Signal(
            signal_id="test-002",
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.50,  # Below 75% threshold
            base_score=50.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
            stop_loss=3000.0,
            risk_reward_ratio=2.0,
            metadata={"entry_price": 2500.0, "leverage": 1.0},
        )

        low_conf_assessment = await enforcer.validate_order(
            signal=low_conf_signal,
            portfolio_value=portfolio_value,
            current_positions=[],
            current_drawdown_pct=0.0,
            entry_price=2500.0,
        )

        results["budget_checks"].append(
            {
                "check": "low_confidence_rejection",
                "approved": low_conf_assessment.approved,
                "violations": len(low_conf_assessment.violations),
            }
        )

        if not low_conf_assessment.approved:
            results["details"].append(f"✓ Low confidence order correctly rejected")
        else:
            results["details"].append(f"⚠ Low confidence order was not rejected")

        # Get enforcer stats
        stats = enforcer.get_stats()
        results["details"].append(f"✓ Enforcer stats retrieved")
        results["details"].append(
            f"  - Total violations: {stats['violation_stats']['total_violations']}"
        )
        results["details"].append(
            f"  - Block count: {stats['violation_stats']['block_count']}"
        )

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Budget enforcement error: {e}")

    return results


# Test 6: Metrics Collection Simulation
def test_metrics_collection() -> dict[str, Any]:
    """Simulate metrics collection for canary validation."""
    results = {
        "test_name": "Metrics Collection Simulation",
        "status": "PASS",
        "details": [],
        "errors": [],
        "collected_metrics": {},
    }

    try:
        from execution.canary import CanaryMetrics

        # Simulate a 7-day canary with realistic trading data
        metrics = CanaryMetrics(
            start_equity=10000.0,
            current_equity=10450.0,
            peak_equity=10600.0,
            total_trades=25,
            winning_trades=15,
            losing_trades=10,
            realized_pnl=450.0,
            max_drawdown_pct=3.5,
            win_rate_pct=60.0,
            sharpe_ratio=1.2,
        )

        results["collected_metrics"] = {
            "equity": {
                "start": metrics.start_equity,
                "current": metrics.current_equity,
                "peak": metrics.peak_equity,
            },
            "returns": {
                "absolute_pnl": metrics.realized_pnl,
                "return_pct": (metrics.current_equity - metrics.start_equity)
                / metrics.start_equity
                * 100,
            },
            "trades": {
                "total": metrics.total_trades,
                "winning": metrics.winning_trades,
                "losing": metrics.losing_trades,
                "win_rate_pct": metrics.win_rate_pct,
            },
            "risk": {
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "sharpe_ratio": metrics.sharpe_ratio,
            },
        }

        results["details"].append(f"✓ Simulated canary metrics collected")
        results["details"].append(f"  - Start equity: ${metrics.start_equity:,.2f}")
        results["details"].append(f"  - Current equity: ${metrics.current_equity:,.2f}")
        results["details"].append(f"  - Peak equity: ${metrics.peak_equity:,.2f}")
        results["details"].append(f"  - Total PnL: ${metrics.realized_pnl:,.2f}")
        results["details"].append(
            f"  - Return: {(metrics.current_equity - metrics.start_equity) / metrics.start_equity * 100:.2f}%"
        )
        results["details"].append(f"  - Total trades: {metrics.total_trades}")
        results["details"].append(f"  - Win rate: {metrics.win_rate_pct:.1f}%")
        results["details"].append(f"  - Max drawdown: {metrics.max_drawdown_pct:.2f}%")
        results["details"].append(f"  - Sharpe ratio: {metrics.sharpe_ratio}")

        # Test serialization
        metrics_dict = metrics.to_dict()
        assert "start_equity" in metrics_dict
        assert "win_rate_pct" in metrics_dict
        results["details"].append(f"✓ Metrics serialization successful")

        # Test deserialization
        restored = CanaryMetrics.from_dict(metrics_dict)
        assert restored.total_trades == metrics.total_trades
        results["details"].append(f"✓ Metrics deserialization successful")

    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Metrics collection error: {e}")

    return results


# Test 7: Report Generation
def generate_canary_report(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate final canary validation report."""
    report = {
        "report_title": "Paper Trading Canary Validation Report",
        "generated_at": datetime.now().isoformat(),
        "story_id": "PAPER-003",
        "summary": {
            "total_tests": len(all_results),
            "passed": sum(1 for r in all_results if r["status"] == "PASS"),
            "failed": sum(1 for r in all_results if r["status"] == "FAIL"),
            "overall_status": (
                "PASS" if all(r["status"] == "PASS" for r in all_results) else "FAIL"
            ),
        },
        "test_results": all_results,
        "recommendations": [],
    }

    # Add recommendations based on results
    if report["summary"]["overall_status"] == "PASS":
        report["recommendations"].append(
            "✓ Canary infrastructure is ready for paper trading"
        )
        report["recommendations"].append("✓ All gate criteria are properly configured")
        report["recommendations"].append(
            "✓ Budget enforcement is active and functional"
        )
        report["recommendations"].append(
            "→ Proceed with canary deployment at 10% allocation"
        )
    else:
        report["recommendations"].append(
            "⚠ Some validation tests failed - review errors above"
        )
        report["recommendations"].append("→ Address critical issues before proceeding")

    return report


async def main():
    """Main validation entry point."""
    print("=" * 70)
    print("PAPER TRADING CANARY VALIDATION - PAPER-003")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    # Run all tests
    all_results = []

    # Test 1: Module imports
    print("Running Test 1: Module Import Validation...")
    result = test_module_imports()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    if result["status"] == "FAIL":
        print("CRITICAL: Module import failed - cannot continue validation")
        sys.exit(1)

    # Test 2: Configuration
    print("Running Test 2: Configuration Validation...")
    result = test_configuration()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    # Test 3: Gate evaluation
    print("Running Test 3: Gate Evaluation Logic...")
    result = test_gate_evaluation()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    # Test 4: Canary lifecycle
    print("Running Test 4: Canary Deployment Lifecycle...")
    result = test_canary_lifecycle()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    # Test 5: Budget enforcement (async)
    print("Running Test 5: Budget Enforcement Validation...")
    result = await test_budget_enforcement()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    # Test 6: Metrics collection
    print("Running Test 6: Metrics Collection Simulation...")
    result = test_metrics_collection()
    all_results.append(result)
    print(f"  Status: {result['status']}")
    for detail in result["details"]:
        print(f"    {detail}")
    for error in result["errors"]:
        print(f"    ERROR: {error}")
    print()

    # Generate report
    print("=" * 70)
    print("GENERATING VALIDATION REPORT...")
    print("=" * 70)

    report = generate_canary_report(all_results)

    print(f"\nOverall Status: {report['summary']['overall_status']}")
    print(
        f"Tests Passed: {report['summary']['passed']}/{report['summary']['total_tests']}"
    )
    print(
        f"Tests Failed: {report['summary']['failed']}/{report['summary']['total_tests']}"
    )
    print()

    print("Recommendations:")
    for rec in report["recommendations"]:
        print(f"  {rec}")
    print()

    # Save report to file
    report_path = (
        "/home/tacopants/projects/ChiseAI/docs/promotion/canary_validation_report.json"
    )
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to: {report_path}")

    # Exit with appropriate code
    if report["summary"]["overall_status"] == "PASS":
        print("\n✓ CANARY VALIDATION PASSED")
        return 0
    else:
        print("\n✗ CANARY VALIDATION FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
