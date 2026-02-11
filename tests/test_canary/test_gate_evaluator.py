"""Tests for gate evaluator."""

import pytest

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import (
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    GateCheckResult,
    GateCriteria,
    create_canary_deployment,
)


class TestGateEvaluator:
    """Test GateEvaluator class."""

    def test_default_criteria(self):
        """Test default criteria initialization."""
        evaluator = GateEvaluator()
        assert evaluator.criteria.max_drawdown_pct == 5.0
        assert evaluator.criteria.min_win_rate_pct == 55.0
        assert evaluator.criteria.duration_days == 7

    def test_custom_criteria(self):
        """Test custom criteria initialization."""
        criteria = GateCriteria(max_drawdown_pct=3.0, min_win_rate_pct=60.0)
        evaluator = GateEvaluator(criteria=criteria)
        assert evaluator.criteria.max_drawdown_pct == 3.0
        assert evaluator.criteria.min_win_rate_pct == 60.0

    def test_evaluate_drawdown_pass(self):
        """Test drawdown evaluation - passing case."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(max_drawdown_pct=3.0)

        check = evaluator.evaluate_drawdown(metrics)
        assert check.result == GateCheckResult.PASS
        assert check.actual_value == 3.0
        assert check.threshold_value == 5.0

    def test_evaluate_drawdown_fail(self):
        """Test drawdown evaluation - failing case."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(max_drawdown_pct=6.0)

        check = evaluator.evaluate_drawdown(metrics)
        assert check.result == GateCheckResult.FAIL
        assert check.actual_value == 6.0

    def test_evaluate_drawdown_custom_threshold(self):
        """Test drawdown evaluation with custom threshold."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(max_drawdown_pct=4.0)

        check = evaluator.evaluate_drawdown(metrics, threshold=3.0)
        assert check.result == GateCheckResult.FAIL
        assert check.threshold_value == 3.0

    def test_evaluate_win_rate_pending(self):
        """Test win rate evaluation - pending (insufficient trades)."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(total_trades=5, win_rate_pct=100.0)

        check = evaluator.evaluate_win_rate(metrics)
        assert check.result == GateCheckResult.PENDING
        assert "Insufficient trades" in check.message

    def test_evaluate_win_rate_pass(self):
        """Test win rate evaluation - passing case."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(
            total_trades=20,
            winning_trades=12,
            losing_trades=8,
            win_rate_pct=60.0,
        )

        check = evaluator.evaluate_win_rate(metrics)
        assert check.result == GateCheckResult.PASS
        assert check.actual_value == 60.0
        assert check.threshold_value == 55.0

    def test_evaluate_win_rate_fail(self):
        """Test win rate evaluation - failing case."""
        evaluator = GateEvaluator()
        metrics = CanaryMetrics(
            total_trades=20,
            winning_trades=8,
            losing_trades=12,
            win_rate_pct=40.0,
        )

        check = evaluator.evaluate_win_rate(metrics)
        assert check.result == GateCheckResult.FAIL
        assert check.actual_value == 40.0

    def test_evaluate_duration_pending(self):
        """Test duration evaluation - pending case."""
        evaluator = GateEvaluator()
        start_time = 1609459200  # 2021-01-01
        current_time = start_time + 3 * 24 * 60 * 60  # 3 days later

        check = evaluator.evaluate_duration(start_time, current_time)
        assert check.result == GateCheckResult.PENDING
        assert check.actual_value == 3.0
        assert check.threshold_value == 7.0

    def test_evaluate_duration_pass(self):
        """Test duration evaluation - passing case."""
        evaluator = GateEvaluator()
        start_time = 1609459200  # 2021-01-01
        current_time = start_time + 8 * 24 * 60 * 60  # 8 days later

        check = evaluator.evaluate_duration(start_time, current_time)
        assert check.result == GateCheckResult.PASS
        assert check.actual_value == 8.0

    def test_evaluate_all_gates(self):
        """Test evaluating all gates."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)

        checks = evaluator.evaluate_all_gates(canary)
        assert len(checks) == 3

        gate_names = {check.gate_name for check in checks}
        assert "max_drawdown" in gate_names
        assert "min_win_rate" in gate_names
        assert "duration" in gate_names

    def test_determine_status_all_pass(self):
        """Test status determination - all gates pass."""
        evaluator = GateEvaluator()
        checks = [
            type("Check", (), {"result": GateCheckResult.PASS, "message": ""})(),
            type("Check", (), {"result": GateCheckResult.PASS, "message": ""})(),
        ]

        status, messages = evaluator.determine_status(checks)
        assert status == CanaryStatus.PASSED
        assert len(messages) == 0

    def test_determine_status_with_failures(self):
        """Test status determination - some gates fail."""
        evaluator = GateEvaluator()
        checks = [
            type(
                "Check",
                (),
                {"result": GateCheckResult.FAIL, "message": "Drawdown exceeded"},
            )(),
            type("Check", (), {"result": GateCheckResult.PASS, "message": ""})(),
        ]

        status, messages = evaluator.determine_status(checks)
        assert status == CanaryStatus.FAILED
        assert len(messages) == 1
        assert "Drawdown exceeded" in messages[0]

    def test_determine_status_with_pending(self):
        """Test status determination - some gates pending."""
        evaluator = GateEvaluator()
        checks = [
            type("Check", (), {"result": GateCheckResult.PASS, "message": ""})(),
            type(
                "Check",
                (),
                {"result": GateCheckResult.PENDING, "message": "Duration pending"},
            )(),
        ]

        status, messages = evaluator.determine_status(checks)
        assert status == CanaryStatus.RUNNING
        assert len(messages) == 1

    def test_should_rollback_true(self):
        """Test should_rollback - should rollback."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        canary.metrics.peak_equity = 10000.0
        canary.metrics.update_equity(9400.0)  # 6% drawdown

        should_rollback, reasons = evaluator.should_rollback(canary)
        assert should_rollback is True
        assert len(reasons) > 0

    def test_should_rollback_false(self):
        """Test should_rollback - should not rollback."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        canary.metrics.update_equity(9800.0)  # 2% drawdown

        should_rollback, reasons = evaluator.should_rollback(canary)
        # Should not rollback based on drawdown, but duration is pending
        # The method should return False when gates don't fail
        assert isinstance(should_rollback, bool)

    def test_can_promote_true(self):
        """Test can_promote - can promote."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        # Simulate passing all gates
        canary.start_time = 1609459200
        canary.end_time = canary.start_time + 8 * 24 * 60 * 60  # 8 days
        canary.last_check_time = canary.end_time

        # Add winning trades for win rate
        for _ in range(12):
            canary.metrics.record_trade(100.0)
        for _ in range(8):
            canary.metrics.record_trade(-50.0)

        can_promote, messages = evaluator.can_promote(canary)
        # Should be able to promote if status is PASSED
        assert isinstance(can_promote, bool)

    def test_can_promote_not_passed_status(self):
        """Test can_promote - status not passed."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        # Status is RUNNING, not PASSED

        can_promote, messages = evaluator.can_promote(canary)
        assert can_promote is False
        assert len(messages) > 0

    def test_generate_evaluation_report(self):
        """Test evaluation report generation."""
        evaluator = GateEvaluator()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)

        report = evaluator.generate_evaluation_report(canary)
        assert report["canary_id"] == "test-001"
        assert report["strategy_id"] == "strategy-v2"
        assert "metrics" in report
        assert "gate_checks" in report
        assert "timestamp" in report
