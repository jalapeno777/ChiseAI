"""Tests for gate_evaluator module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "ci_integration")
)

from gate_evaluator import (
    GateEvaluationReport,
    GateResult,
    apply_override,
    check_gate_black,
    check_gate_code_quality,
    check_gate_coverage,
    check_gate_pylint,
    check_gate_tests,
    evaluate_gates,
)
from gate_evaluator import (
    main as gate_main,
)


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_gate_result_defaults(self):
        """Test GateResult with defaults."""
        result = GateResult(name="test", passed=True)
        assert result.name == "test"
        assert result.passed is True
        assert result.mandatory is True
        assert result.override_applied is False

    def test_gate_result_with_override(self):
        """Test GateResult with override applied."""
        result = GateResult(
            name="test",
            passed=False,
            mandatory=True,
            message="Failed",
            override_applied=True,
        )
        assert result.override_applied is True


class TestGateEvaluationReport:
    """Tests for GateEvaluationReport dataclass."""

    def test_report_defaults(self):
        """Test report with defaults."""
        report = GateEvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
        )
        assert report.overall_passed is True
        assert report.failed_mandatory_gates == 0
        assert len(report.gates) == 0


class TestCheckGateCoverage:
    """Tests for coverage gate check."""

    def test_coverage_passes(self):
        """Test coverage gate when above minimum."""
        result = check_gate_coverage(80.0, 85.0, "line")
        assert result.passed is True
        assert result.name == "coverage_line"

    def test_coverage_fails(self):
        """Test coverage gate when below minimum."""
        result = check_gate_coverage(80.0, 75.0, "line")
        assert result.passed is False

    def test_coverage_at_threshold(self):
        """Test coverage gate at exact threshold."""
        result = check_gate_coverage(80.0, 80.0, "line")
        assert result.passed is True


class TestCheckGateTests:
    """Tests for test pass rate gate."""

    def test_all_tests_pass(self):
        """Test gate when all tests pass."""
        result = check_gate_tests(0.95, 100, 0, 0)
        assert result.passed is True

    def test_some_tests_fail(self):
        """Test gate when some tests fail."""
        result = check_gate_tests(0.95, 96, 4, 0)
        assert result.passed is True

    def test_too_many_fail(self):
        """Test gate when too many tests fail."""
        result = check_gate_tests(0.95, 90, 10, 0)
        assert result.passed is False

    def test_no_tests(self):
        """Test gate when no tests run."""
        result = check_gate_tests(0.95, 0, 0, 0)
        assert result.passed is False
        assert "No tests" in result.message


class TestCheckGateCodeQuality:
    """Tests for code quality gate."""

    def test_no_issues(self):
        """Test gate with no issues."""
        result = check_gate_code_quality(0, 0, "ruff")
        assert result.passed is True
        assert result.name == "code_quality_ruff"

    def test_some_issues(self):
        """Test gate with issues above threshold."""
        result = check_gate_code_quality(0, 5, "ruff")
        assert result.passed is False


class TestCheckGatePylint:
    """Tests for pylint gate."""

    def test_high_score(self):
        """Test gate with high pylint score."""
        result = check_gate_pylint(8.0, 9.5)
        assert result.passed is True

    def test_low_score(self):
        """Test gate with low pylint score."""
        result = check_gate_pylint(8.0, 7.0)
        assert result.passed is False

    def test_at_threshold(self):
        """Test gate at exact threshold."""
        result = check_gate_pylint(8.0, 8.0)
        assert result.passed is True


class TestCheckGateBlack:
    """Tests for black formatting gate."""

    def test_black_gate(self):
        """Test black formatting gate."""
        result = check_gate_black()
        assert result.passed is True
        assert result.mandatory is True


class TestApplyOverride:
    """Tests for apply_override function."""

    def test_no_override(self):
        """Test when no override is set."""
        result = apply_override("coverage_line", "testing", {})
        assert result is False

    def test_override_true(self):
        """Test when override is set to true."""
        result = apply_override(
            "coverage_line", "testing", {"OVERRIDE_COVERAGE_LINE": "true"}
        )
        assert result is True

    def test_override_false(self):
        """Test when override is set to false."""
        result = apply_override(
            "coverage_line", "testing", {"OVERRIDE_COVERAGE_LINE": "false"}
        )
        assert result is False

    def test_reason_override(self):
        """Test when reason override is set."""
        result = apply_override(
            "coverage_line",
            "testing",
            {"OVERRIDE_COVERAGE_LINE_REASON": "needed for demo"},
        )
        assert result is True


class TestEvaluateGates:
    """Tests for evaluate_gates function."""

    def test_evaluate_gates_all_pass(self):
        """Test evaluation when all gates pass."""
        report = evaluate_gates(
            coverage_line=85.0,
            coverage_branch=75.0,
            test_passed=100,
            test_failed=0,
            test_error=0,
            ruff_issues=0,
            pylint_score=9.0,
            environment_vars={},
            branch="main",
            commit_sha="abc123",
        )

        assert report.overall_passed is True
        assert report.failed_mandatory_gates == 0
        assert report.passed_gates > 0

    def test_evaluate_gates_coverage_fail(self):
        """Test evaluation when coverage fails."""
        report = evaluate_gates(
            coverage_line=70.0,  # Below 80% threshold
            coverage_branch=75.0,
            test_passed=100,
            test_failed=0,
            test_error=0,
            ruff_issues=0,
            pylint_score=9.0,
            environment_vars={},
            branch="main",
            commit_sha="abc123",
        )

        assert report.overall_passed is False
        assert report.failed_mandatory_gates > 0

    def test_evaluate_gates_test_fail(self):
        """Test evaluation when test pass rate fails."""
        report = evaluate_gates(
            coverage_line=85.0,
            coverage_branch=75.0,
            test_passed=90,  # Below 95% threshold
            test_failed=10,
            test_error=0,
            ruff_issues=0,
            environment_vars={},
            branch="main",
            commit_sha="abc123",
        )

        assert report.overall_passed is False

    def test_evaluate_gates_override(self):
        """Test evaluation with override applied."""
        report = evaluate_gates(
            coverage_line=70.0,  # Would fail
            coverage_branch=75.0,
            test_passed=100,
            test_failed=0,
            test_error=0,
            ruff_issues=0,
            pylint_score=9.0,
            environment_vars={"OVERRIDE_COVERAGE_LINE": "true"},
            branch="main",
            commit_sha="abc123",
        )

        # Coverage gate should have override applied
        coverage_gate = next(
            (g for g in report.gates if g.name == "coverage_line"), None
        )
        assert coverage_gate is not None
        assert coverage_gate.override_applied is True

    def test_evaluate_gates_no_coverage_data(self):
        """Test evaluation without coverage data."""
        report = evaluate_gates(
            test_passed=100,
            test_failed=0,
            test_error=0,
            ruff_issues=0,
            environment_vars={},
            branch="main",
            commit_sha="abc123",
        )

        # Should not have coverage gates
        coverage_gates = [g for g in report.gates if "coverage" in g.name]
        assert len(coverage_gates) == 0


class TestGateMain:
    """Tests for gate_evaluator main function."""

    @patch("gate_evaluator.evaluate_gates")
    @patch("sys.argv", ["gate_evaluator"])
    def test_main_all_pass(self, mock_evaluate):
        """Test main when all gates pass."""
        mock_evaluate.return_value = GateEvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            gates=[],
            overall_passed=True,
        )

        with patch("sys.stdout", new=MagicMock()) as mock_stdout:
            exit_code = gate_main()

        assert exit_code == 0

    @patch("gate_evaluator.evaluate_gates")
    @patch("sys.argv", ["gate_evaluator"])
    def test_main_some_fail(self, mock_evaluate):
        """Test main when some gates fail."""
        mock_evaluate.return_value = GateEvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            gates=[GateResult(name="test", passed=False)],
            overall_passed=False,
            failed_mandatory_gates=1,
        )

        with patch("sys.stdout", new=MagicMock()) as mock_stdout:
            exit_code = gate_main()

        assert exit_code == 1

    @patch("gate_evaluator.evaluate_gates")
    @patch("sys.argv", ["gate_evaluator"])
    def test_main_outputs_json(self, mock_evaluate):
        """Test main outputs JSON."""
        mock_evaluate.return_value = GateEvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            gates=[],
            overall_passed=True,
        )

        from io import StringIO

        output = StringIO()
        with patch("sys.stdout", output):
            gate_main()

        result = output.getvalue()
        parsed = json.loads(result)
        assert "overall_passed" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
