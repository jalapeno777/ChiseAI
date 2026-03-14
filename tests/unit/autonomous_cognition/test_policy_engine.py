"""Unit tests for autonomous promotion gate policy."""

from __future__ import annotations

from autonomous_cognition.policy_engine import AutonomousPolicyEngine


def test_policy_engine_missing_constitution_metric_does_not_fail_gate() -> None:
    """Missing constitution metric should not imply a violation."""
    decision = AutonomousPolicyEngine().evaluate_promotion_gates(
        {"sharpe": 1.2, "ece": 0.08, "drawdown": 0.12}
    )
    assert decision.passed is True
    assert "constitution_gate" not in decision.failed_gates


def test_policy_engine_explicit_constitution_violation_fails_gate() -> None:
    """Explicit non-zero constitution violations must fail gate."""
    decision = AutonomousPolicyEngine().evaluate_promotion_gates(
        {"sharpe": 1.2, "ece": 0.08, "drawdown": 0.12, "constitution_violations": 1}
    )
    assert decision.passed is False
    assert "constitution_gate" in decision.failed_gates

