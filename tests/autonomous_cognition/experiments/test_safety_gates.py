"""Tests for experiment safety gates."""

from __future__ import annotations

import time

import pytest

from autonomous_cognition.experiments.safety_gates import (
    ExperimentSafetyGates,
    SafetyGateResult,
    ValidationError,
)


class TestExperimentSafetyGates:
    """Test suite for ExperimentSafetyGates."""

    @pytest.fixture
    def gates(self) -> ExperimentSafetyGates:
        """Create a safety gates instance with test defaults."""
        return ExperimentSafetyGates(
            max_experiments_per_cycle=3,
            default_timeout_seconds=300,
            max_risk_level="medium",
        )

    # =========================================================================
    # check_max_experiments tests
    # =========================================================================

    def test_check_max_experiments_zero_count_passes(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Zero experiments should pass (nothing to run)."""
        result = gates.check_max_experiments(0)
        assert result.passed is True
        assert "count=0" in result.message

    def test_check_max_experiments_within_limit(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Count within limit should pass."""
        result = gates.check_max_experiments(1)
        assert result.passed is True

        result = gates.check_max_experiments(2)
        assert result.passed is True

        result = gates.check_max_experiments(3)
        assert result.passed is True

    def test_check_max_experiments_at_limit(self, gates: ExperimentSafetyGates) -> None:
        """Count exactly at limit should pass."""
        result = gates.check_max_experiments(3)
        assert result.passed is True

    def test_check_max_experiments_exceeds_limit(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Count exceeding limit should fail."""
        result = gates.check_max_experiments(4)
        assert result.passed is False
        assert "exceeds maximum allowed 3" in result.message
        assert result.errors is not None
        assert len(result.errors) == 1

    def test_check_max_experiments_well_over_limit(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Count well over limit should fail with clear message."""
        result = gates.check_max_experiments(100)
        assert result.passed is False
        assert "100" in result.message
        assert "exceeds maximum allowed 3" in result.message

    def test_check_max_experiments_negative_count(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Negative count should pass (edge case - nothing to run)."""
        result = gates.check_max_experiments(-1)
        assert result.passed is True

    # =========================================================================
    # check_timeout tests
    # =========================================================================

    def test_check_timeout_none_start_time_passes(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """None start time should pass (no timing available)."""
        result = gates.check_timeout(None)
        assert result.passed is True
        assert "skipped" in result.message.lower()

    def test_check_timeout_within_limit(self, gates: ExperimentSafetyGates) -> None:
        """Recent start time should pass."""
        start = time.time() - 10  # 10 seconds ago
        result = gates.check_timeout(start)
        assert result.passed is True
        assert "within timeout" in result.message.lower()

    def test_check_timeout_exactly_at_limit(self, gates: ExperimentSafetyGates) -> None:
        """Time exactly at limit should pass (use 299 to avoid floating point edge)."""
        start = time.time() - 299  # 299 seconds ago (safely within 300 limit)
        result = gates.check_timeout(start)
        assert result.passed is True

    def test_check_timeout_exceeds_limit(self, gates: ExperimentSafetyGates) -> None:
        """Time exceeding limit should fail."""
        start = time.time() - 400  # 400 seconds ago (> 300 limit)
        result = gates.check_timeout(start)
        assert result.passed is False
        assert "timed out" in result.message.lower()
        assert "elapsed=" in result.message
        assert "limit=300" in result.message

    def test_check_timeout_custom_timeout(self, gates: ExperimentSafetyGates) -> None:
        """Custom timeout should be respected."""
        start = time.time() - 10  # 10 seconds ago
        result = gates.check_timeout(start, timeout_seconds=5)
        assert result.passed is False
        assert "limit=5" in result.message

    def test_check_timeout_zero_timeout(self, gates: ExperimentSafetyGates) -> None:
        """Zero timeout should fail immediately."""
        start = time.time()
        result = gates.check_timeout(start, timeout_seconds=0)
        assert result.passed is False

    # =========================================================================
    # validate_result tests
    # =========================================================================

    def test_validate_result_valid(self, gates: ExperimentSafetyGates) -> None:
        """Valid result should pass validation."""
        result = {
            "hypothesis_id": "test-hyp-1",
            "sharpe": 1.5,
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_result_none(self, gates: ExperimentSafetyGates) -> None:
        """None result should fail validation."""
        is_valid, errors = gates.validate_result(None)
        assert is_valid is False
        assert len(errors) == 1
        assert errors[0].field == "result"

    def test_validate_result_not_dict(self, gates: ExperimentSafetyGates) -> None:
        """Non-dict result should fail validation."""
        is_valid, errors = gates.validate_result("not a dict")
        assert is_valid is False
        assert len(errors) == 1
        assert "not a dictionary" in errors[0].message

    def test_validate_result_missing_sharpe(self, gates: ExperimentSafetyGates) -> None:
        """Missing sharpe should fail validation."""
        result = {
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        assert any(e.field == "sharpe" for e in errors)

    def test_validate_result_missing_all_metrics(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Missing all metrics should fail with all errors."""
        result: dict = {}
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        error_fields = {e.field for e in errors}
        assert error_fields == {"sharpe", "sortino", "drawdown", "ece"}

    def test_validate_result_negative_sharpe(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Negative sharpe should fail validation."""
        result = {
            "sharpe": -0.5,
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        sharpe_errors = [e for e in errors if e.field == "sharpe"]
        assert len(sharpe_errors) == 1
        assert "must be >= 0" in sharpe_errors[0].message

    def test_validate_result_sharpe_not_numeric(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Non-numeric sharpe should fail validation."""
        result = {
            "sharpe": "high",
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        sharpe_errors = [e for e in errors if e.field == "sharpe"]
        assert len(sharpe_errors) == 1
        assert "must be numeric" in sharpe_errors[0].message

    def test_validate_result_drawdown_negative(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Negative drawdown should fail validation."""
        result = {
            "sharpe": 1.5,
            "sortino": 1.8,
            "drawdown": -0.1,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        drawdown_errors = [e for e in errors if e.field == "drawdown"]
        assert len(drawdown_errors) == 1
        assert "must be 0 <= x <= 1" in drawdown_errors[0].message

    def test_validate_result_drawdown_too_high(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Drawdown > 1 should fail validation."""
        result = {
            "sharpe": 1.5,
            "sortino": 1.8,
            "drawdown": 1.5,
            "ece": 0.05,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        drawdown_errors = [e for e in errors if e.field == "drawdown"]
        assert len(drawdown_errors) == 1

    def test_validate_result_ece_negative(self, gates: ExperimentSafetyGates) -> None:
        """Negative ECE should fail validation."""
        result = {
            "sharpe": 1.5,
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": -0.01,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        ece_errors = [e for e in errors if e.field == "ece"]
        assert len(ece_errors) == 1
        assert "must be 0 <= x <= 1" in ece_errors[0].message

    def test_validate_result_ece_too_high(self, gates: ExperimentSafetyGates) -> None:
        """ECE > 1 should fail validation."""
        result = {
            "sharpe": 1.5,
            "sortino": 1.8,
            "drawdown": 0.1,
            "ece": 2.0,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is False
        ece_errors = [e for e in errors if e.field == "ece"]
        assert len(ece_errors) == 1

    def test_validate_result_boundary_values(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Boundary values should pass validation."""
        result = {
            "sharpe": 0.0,
            "sortino": 0.0,
            "drawdown": 0.0,
            "ece": 0.0,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is True
        assert len(errors) == 0

        result = {
            "sharpe": 100.0,
            "sortino": 100.0,
            "drawdown": 1.0,
            "ece": 1.0,
        }
        is_valid, errors = gates.validate_result(result)
        assert is_valid is True
        assert len(errors) == 0

    # =========================================================================
    # check_risk_level tests
    # =========================================================================

    def test_check_risk_level_low_passes(self, gates: ExperimentSafetyGates) -> None:
        """Low risk level should pass for medium max."""
        result = gates.check_risk_level("low")
        assert result.passed is True

    def test_check_risk_level_medium_passes(self, gates: ExperimentSafetyGates) -> None:
        """Medium risk level should pass for medium max."""
        result = gates.check_risk_level("medium")
        assert result.passed is True

    def test_check_risk_level_high_fails_for_medium_max(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """High risk level should fail when max is medium."""
        result = gates.check_risk_level("high")
        assert result.passed is False
        assert "exceeds maximum" in result.message
        assert "high" in result.message
        assert "medium" in result.message

    def test_check_risk_level_critical_fails(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Critical risk level should fail even with high max."""
        gates_high = ExperimentSafetyGates(max_risk_level="high")
        result = gates_high.check_risk_level("critical")
        assert result.passed is False

    def test_check_risk_level_none_fails(self, gates: ExperimentSafetyGates) -> None:
        """None risk level should fail."""
        result = gates.check_risk_level(None)
        assert result.passed is False
        assert "None" in result.message

    def test_check_risk_level_unknown_fails(self, gates: ExperimentSafetyGates) -> None:
        """Unknown risk level should fail."""
        result = gates.check_risk_level("unknown")
        assert result.passed is False
        assert "Unknown risk level" in result.message

    def test_check_risk_level_custom_max(self, gates: ExperimentSafetyGates) -> None:
        """Custom max should override instance max."""
        result = gates.check_risk_level("high", max_allowed="high")
        assert result.passed is True

    def test_check_risk_level_custom_max_low(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Custom max=low should only allow low."""
        result = gates.check_risk_level("medium", max_allowed="low")
        assert result.passed is False

    def test_check_risk_level_unknown_max_fails(
        self, gates: ExperimentSafetyGates
    ) -> None:
        """Unknown max risk level should fail (config error)."""
        result = gates.check_risk_level("low", max_allowed="unknown")
        assert result.passed is False
        assert "Unknown max risk level" in result.message

    # =========================================================================
    # run_all_gates tests
    # =========================================================================

    def test_run_all_gates_all_pass(self, gates: ExperimentSafetyGates) -> None:
        """All gates should pass with valid inputs."""
        result = gates.run_all_gates(
            experiment_count=2,
            start_time=time.time() - 10,
            result={
                "hypothesis_id": "test",
                "sharpe": 1.5,
                "sortino": 1.8,
                "drawdown": 0.1,
                "ece": 0.05,
            },
            risk_level="low",
        )
        assert "max_experiments" in result
        assert "timeout" in result
        assert "result_validation" in result
        assert "risk_level" in result
        assert all(r.passed for r in result.values())

    def test_run_all_gates_one_fails(self, gates: ExperimentSafetyGates) -> None:
        """One gate failure should be reflected in result dict."""
        result = gates.run_all_gates(
            experiment_count=5,  # exceeds limit
            start_time=time.time() - 10,
            result={
                "hypothesis_id": "test",
                "sharpe": 1.5,
                "sortino": 1.8,
                "drawdown": 0.1,
                "ece": 0.05,
            },
            risk_level="low",
        )
        assert result["max_experiments"].passed is False
        assert result["timeout"].passed is True
        assert result["result_validation"].passed is True
        assert result["risk_level"].passed is True

    # =========================================================================
    # all_gates_passed tests
    # =========================================================================

    def test_all_gates_passed_true(self, gates: ExperimentSafetyGates) -> None:
        """Should return True when all gates pass."""
        passed = gates.all_gates_passed(
            experiment_count=2,
            start_time=time.time() - 10,
            result={
                "hypothesis_id": "test",
                "sharpe": 1.5,
                "sortino": 1.8,
                "drawdown": 0.1,
                "ece": 0.05,
            },
            risk_level="low",
        )
        assert passed is True

    def test_all_gates_passed_false(self, gates: ExperimentSafetyGates) -> None:
        """Should return False when any gate fails."""
        passed = gates.all_gates_passed(
            experiment_count=100,  # exceeds limit
            start_time=time.time() - 10,
            result={
                "hypothesis_id": "test",
                "sharpe": 1.5,
                "sortino": 1.8,
                "drawdown": 0.1,
                "ece": 0.05,
            },
            risk_level="low",
        )
        assert passed is False

    # =========================================================================
    # Property access tests
    # =========================================================================

    def test_properties(self, gates: ExperimentSafetyGates) -> None:
        """Properties should return configured values."""
        assert gates.max_experiments_per_cycle == 3
        assert gates.default_timeout_seconds == 300
        assert gates.max_risk_level == "medium"

    def test_custom_properties(self) -> None:
        """Custom configuration should be reflected in properties."""
        gates = ExperimentSafetyGates(
            max_experiments_per_cycle=10,
            default_timeout_seconds=600,
            max_risk_level="high",
        )
        assert gates.max_experiments_per_cycle == 10
        assert gates.default_timeout_seconds == 600
        assert gates.max_risk_level == "high"

    # =========================================================================
    # SafetyGateResult tests
    # =========================================================================

    def test_safety_gate_result_bool(self) -> None:
        """SafetyGateResult should support bool conversion."""
        passing = SafetyGateResult(passed=True, message="ok")
        failing = SafetyGateResult(passed=False, message="fail")

        assert bool(passing) is True
        assert bool(failing) is False

    def test_validation_error_dataclass(self) -> None:
        """ValidationError should store all fields."""
        error = ValidationError(
            field="sharpe",
            message="must be >= 0",
            value=-1.0,
        )
        assert error.field == "sharpe"
        assert error.message == "must be >= 0"
        assert error.value == -1.0
