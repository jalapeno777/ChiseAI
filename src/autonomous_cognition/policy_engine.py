"""Policy gate evaluation for autonomous cognition promotions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateDecision:
    """Result of gate evaluation."""

    passed: bool
    failed_gates: list[str] = field(default_factory=list)


class AutonomousPolicyEngine:
    """Evaluates promotion gates defined by autonomy governance."""

    def evaluate_promotion_gates(self, metrics: dict[str, float]) -> GateDecision:
        """Evaluate core gates for candidate promotion."""
        failures: list[str] = []
        if metrics.get("sharpe", 0.0) < 1.1:
            failures.append("statistical_improvement_gate")
        if metrics.get("ece", 1.0) > 0.15:
            failures.append("calibration_gate")
        if metrics.get("drawdown", 1.0) > 0.20:
            failures.append("risk_regression_gate")
        if metrics.get("constitution_violations", 0.0) > 0:
            failures.append("constitution_gate")
        return GateDecision(passed=not failures, failed_gates=failures)
