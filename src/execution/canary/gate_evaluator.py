"""Gate evaluator for canary deployments.

Provides functionality to evaluate gate criteria and make promotion/rollback decisions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from execution.canary.models import (
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    GateCheck,
    GateCheckResult,
    GateCriteria,
)


class GateEvaluator:
    """Evaluates gate criteria for canary deployments.

    This class provides methods to:
    - Evaluate individual gate criteria
    - Check if canary should be promoted or rolled back
    - Generate evaluation reports
    """

    def __init__(self, criteria: GateCriteria | None = None) -> None:
        """Initialize the gate evaluator.

        Args:
            criteria: Gate criteria to use (default if None)
        """
        self.criteria = criteria or GateCriteria()

    def evaluate_drawdown(
        self, metrics: CanaryMetrics, threshold: float | None = None
    ) -> GateCheck:
        """Evaluate the maximum drawdown criterion.

        Args:
            metrics: Current canary metrics
            threshold: Override threshold (uses criteria default if None)

        Returns:
            Gate check result
        """
        threshold = threshold or self.criteria.max_drawdown_pct
        actual_drawdown = metrics.max_drawdown_pct

        if actual_drawdown > threshold:
            return GateCheck(
                gate_name="max_drawdown",
                result=GateCheckResult.FAIL,
                actual_value=actual_drawdown,
                threshold_value=threshold,
                message=(
                    f"FAIL: Drawdown {actual_drawdown:.2f}% exceeds "
                    f"threshold {threshold:.2f}%"
                ),
            )
        else:
            return GateCheck(
                gate_name="max_drawdown",
                result=GateCheckResult.PASS,
                actual_value=actual_drawdown,
                threshold_value=threshold,
                message=(
                    f"PASS: Drawdown {actual_drawdown:.2f}% within "
                    f"threshold {threshold:.2f}%"
                ),
            )

    def evaluate_win_rate(
        self, metrics: CanaryMetrics, threshold: float | None = None
    ) -> GateCheck:
        """Evaluate the minimum win rate criterion.

        Args:
            metrics: Current canary metrics
            threshold: Override threshold (uses criteria default if None)

        Returns:
            Gate check result
        """
        threshold = threshold or self.criteria.min_win_rate_pct
        actual_win_rate = metrics.win_rate_pct

        # Only evaluate if we have minimum trades
        if metrics.total_trades < self.criteria.min_trades:
            return GateCheck(
                gate_name="min_win_rate",
                result=GateCheckResult.PENDING,
                actual_value=actual_win_rate,
                threshold_value=threshold,
                message=(
                    f"PENDING: Insufficient trades "
                    f"({metrics.total_trades}/{self.criteria.min_trades})"
                ),
            )

        if actual_win_rate < threshold:
            return GateCheck(
                gate_name="min_win_rate",
                result=GateCheckResult.FAIL,
                actual_value=actual_win_rate,
                threshold_value=threshold,
                message=(
                    f"FAIL: Win rate {actual_win_rate:.2f}% below "
                    f"threshold {threshold:.2f}%"
                ),
            )
        else:
            return GateCheck(
                gate_name="min_win_rate",
                result=GateCheckResult.PASS,
                actual_value=actual_win_rate,
                threshold_value=threshold,
                message=(
                    f"PASS: Win rate {actual_win_rate:.2f}% meets "
                    f"threshold {threshold:.2f}%"
                ),
            )

    def evaluate_duration(
        self,
        start_time: int,
        current_time: int | None = None,
        required_days: int | None = None,
    ) -> GateCheck:
        """Evaluate the minimum duration criterion.

        Args:
            start_time: Canary start timestamp (Unix seconds)
            current_time: Current timestamp (default: now)
            required_days: Override duration (uses criteria default if None)

        Returns:
            Gate check result
        """
        required_days = required_days or self.criteria.duration_days
        current_time = current_time or int(datetime.now().timestamp())

        elapsed_seconds = current_time - start_time
        required_seconds = required_days * 24 * 60 * 60
        elapsed_days = elapsed_seconds / (24 * 60 * 60)

        if elapsed_seconds < required_seconds:
            return GateCheck(
                gate_name="duration",
                result=GateCheckResult.PENDING,
                actual_value=elapsed_days,
                threshold_value=float(required_days),
                message=(
                    f"PENDING: Duration {elapsed_days:.2f} days < required "
                    f"{required_days} days"
                ),
            )
        else:
            return GateCheck(
                gate_name="duration",
                result=GateCheckResult.PASS,
                actual_value=elapsed_days,
                threshold_value=float(required_days),
                message=(
                    f"PASS: Duration {elapsed_days:.2f} days meets required "
                    f"{required_days} days"
                ),
            )

    def evaluate_all_gates(self, canary: CanaryDeployment) -> list[GateCheck]:
        """Evaluate all gate criteria for a canary deployment.

        Args:
            canary: Canary deployment to evaluate

        Returns:
            List of gate check results
        """
        checks = []

        # Check drawdown
        checks.append(self.evaluate_drawdown(canary.metrics))

        # Check win rate
        checks.append(self.evaluate_win_rate(canary.metrics))

        # Check duration
        checks.append(
            self.evaluate_duration(
                canary.start_time,
                canary.last_check_time or int(datetime.now().timestamp()),
            )
        )

        return checks

    def determine_status(
        self, checks: list[GateCheck]
    ) -> tuple[CanaryStatus, list[str]]:
        """Determine canary status from gate checks.

        Args:
            checks: List of gate check results

        Returns:
            Tuple of (status, failure_messages)
        """
        failures = []
        pending = []

        for check in checks:
            if check.result == GateCheckResult.FAIL:
                failures.append(check.message)
            elif check.result == GateCheckResult.PENDING:
                pending.append(check.message)

        if failures:
            return CanaryStatus.FAILED, failures
        elif pending:
            return CanaryStatus.RUNNING, pending
        else:
            return CanaryStatus.PASSED, []

    def should_rollback(self, canary: CanaryDeployment) -> tuple[bool, list[str]]:
        """Check if canary should be rolled back.

        Args:
            canary: Canary deployment to check

        Returns:
            Tuple of (should_rollback, reasons)
        """
        checks = self.evaluate_all_gates(canary)
        status, messages = self.determine_status(checks)
        return status == CanaryStatus.FAILED, messages

    def can_promote(self, canary: CanaryDeployment) -> tuple[bool, list[str]]:
        """Check if canary can be promoted.

        Args:
            canary: Canary deployment to check

        Returns:
            Tuple of (can_promote, pending_messages)
        """
        if canary.status != CanaryStatus.PASSED:
            return False, [f"Canary status is {canary.status.value} (expected passed)"]

        checks = self.evaluate_all_gates(canary)
        status, messages = self.determine_status(checks)

        if status == CanaryStatus.PASSED:
            return True, []
        else:
            return False, messages

    def generate_evaluation_report(self, canary: CanaryDeployment) -> dict[str, Any]:
        """Generate a comprehensive evaluation report.

        Args:
            canary: Canary deployment to report on

        Returns:
            Report dictionary
        """
        checks = self.evaluate_all_gates(canary)
        status, messages = self.determine_status(checks)

        return {
            "canary_id": canary.canary_id,
            "strategy_id": canary.strategy_id,
            "status": canary.status.value,
            "evaluated_status": status.value,
            "allocation_pct": canary.allocation_pct,
            "start_time": canary.start_time,
            "end_time": canary.end_time,
            "metrics": canary.metrics.to_dict(),
            "gate_checks": [check.to_dict() for check in checks],
            "messages": messages,
            "can_promote": status == CanaryStatus.PASSED,
            "should_rollback": status == CanaryStatus.FAILED,
            "timestamp": int(datetime.now().timestamp()),
        }
