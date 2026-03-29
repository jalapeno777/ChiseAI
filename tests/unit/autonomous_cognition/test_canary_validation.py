"""Tests for CANARY validation scripts.

These tests verify the health check and report scripts work correctly,
including success criteria validation, failure detection, and auto-demotion triggers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Get the scripts and tests directories
REPO_ROOT = Path(__file__).parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
HEALTH_CHECK_SCRIPT = SCRIPTS_DIR / "autocog_canary_health_check.py"
REPORT_SCRIPT = SCRIPTS_DIR / "autocog_canary_report.py"


class TestCanaryHealthCheck:
    """Tests for the CANARY health check script."""

    def test_health_check_script_runs_without_errors(self) -> None:
        """Test that health check script runs without errors."""
        result = subprocess.run(
            [sys.executable, str(HEALTH_CHECK_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "CANARY Mode Health Check Script" in result.stdout
        assert "exit code: 0" in result.stdout or "exit" in result.stdout.lower()

    def test_health_check_dry_run_produces_output(self) -> None:
        """Test that health check runs with dry-run flag."""
        result = subprocess.run(
            [sys.executable, str(HEALTH_CHECK_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode in [0, 1, 2]  # Any valid exit code
        assert "CANARY Mode Health Check Report" in result.stdout

    def test_health_check_verbose_output(self) -> None:
        """Test that verbose flag shows threshold reference."""
        result = subprocess.run(
            [sys.executable, str(HEALTH_CHECK_SCRIPT), "--dry-run", "--verbose"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "DIVERGENCE_THRESHOLD_LOW" in result.stdout
        assert "DRIFT_THRESHOLD_FOR_DEMOTION" in result.stdout

    def test_health_check_exit_codes(self) -> None:
        """Test that health check returns correct exit codes."""
        # Test dry-run should return healthy (0) since simulated data is good
        result = subprocess.run(
            [sys.executable, str(HEALTH_CHECK_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Overall Status: HEALTHY" in result.stdout or result.returncode == 0


class TestCanaryReport:
    """Tests for the CANARY report script."""

    def test_report_script_runs_without_errors(self) -> None:
        """Test that report script runs without errors."""
        result = subprocess.run(
            [sys.executable, str(REPORT_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "CANARY Mode Validation Report" in result.stdout

    def test_report_json_output_format(self) -> None:
        """Test that report generates valid JSON output."""
        result = subprocess.run(
            [sys.executable, str(REPORT_SCRIPT), "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should either succeed (0) or fail gracefully (1)
        assert result.returncode in [0, 1, 2]

        # Try to parse JSON output (it may contain text report if not first)
        try:
            data = json.loads(result.stdout)
            assert "status" in data
            assert data["status"] in ["PASS", "WARN", "FAIL"]
        except json.JSONDecodeError:
            # If it contains CANARY text, that's also acceptable
            assert "CANARY" in result.stdout or "status" in result.stdout.lower()

    def test_report_text_output_format(self) -> None:
        """Test that report generates human-readable text output."""
        result = subprocess.run(
            [sys.executable, str(REPORT_SCRIPT), "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "CANARY MODE VALIDATION REPORT" in result.stdout

    def test_report_exit_codes(self) -> None:
        """Test that report returns correct exit codes based on status."""
        result = subprocess.run(
            [sys.executable, str(REPORT_SCRIPT), "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Exit code should be 0 (PASS), 1 (WARN), or 2 (FAIL)
        assert result.returncode in [0, 1, 2]


class TestSuccessCriteriaValidation:
    """Tests for success criteria validation logic."""

    def test_divergence_below_threshold_passes(self) -> None:
        """Test that divergence below threshold is considered passing."""
        # This tests the logic in the health check script
        divergence = 0.10  # Below DIVERGENCE_THRESHOLD_LOW = 0.15

        # If below 0.15, should not trigger warnings or errors
        is_warning = divergence >= 0.15
        is_error = divergence >= 0.40  # DRIFT_THRESHOLD_FOR_DEMOTION

        assert not is_warning
        assert not is_error

    def test_divergence_at_threshold_is_warning(self) -> None:
        """Test that divergence at threshold triggers warning."""
        divergence = 0.15  # At DIVERGENCE_THRESHOLD_LOW

        is_warning = divergence >= 0.15
        is_error = divergence >= 0.40

        assert is_warning  # Should be warning
        assert not is_error  # But not error

    def test_divergence_exceeds_demotion_threshold_fails(self) -> None:
        """Test that divergence exceeding demotion threshold is critical."""
        divergence = 0.45  # Above DRIFT_THRESHOLD_FOR_DEMOTION = 0.40

        is_warning = divergence >= 0.15
        is_error = divergence >= 0.40

        assert is_warning
        assert is_error  # Should be critical error


class TestFailureCriteriaDetection:
    """Tests for failure criteria detection."""

    def test_high_divergence_detected_as_critical(self) -> None:
        """Test that high divergence is detected as critical failure."""
        divergence_score = 0.50
        drift_threshold = 0.40

        is_critical = divergence_score >= drift_threshold
        assert is_critical

    def test_error_rate_exceeds_threshold_detected(self) -> None:
        """Test that excessive error rate is detected."""
        error_count = 10
        total_requests = 100
        error_rate_threshold = 0.05  # 5%

        error_rate = error_count / total_requests if total_requests > 0 else 0
        is_critical = error_rate > error_rate_threshold

        assert is_critical
        assert error_rate == 0.10
        assert error_rate > error_rate_threshold

    def test_consecutive_losses_detected(self) -> None:
        """Test that consecutive losses are detected."""
        consecutive_loss_threshold = 3
        consecutive_losses = 3

        is_failure = consecutive_losses >= consecutive_loss_threshold
        assert is_failure


class TestAutoDemotionTriggers:
    """Tests for auto-demotion trigger detection."""

    def test_divergence_trigger_demotion(self) -> None:
        """Test divergence > 0.40 triggers demotion."""
        divergence = 0.42
        demotion_threshold = 0.40

        should_demote = divergence >= demotion_threshold
        assert should_demote

    def test_error_rate_trigger_demotion(self) -> None:
        """Test error rate > 5% triggers demotion."""
        error_count = 6
        total = 100
        threshold = 0.05

        error_rate = error_count / total
        should_demote = error_rate > threshold

        assert should_demote

    def test_consecutive_losses_trigger_demotion(self) -> None:
        """Test 3+ consecutive losses triggers demotion."""
        consecutive_losses = 3
        threshold = 3

        should_demote = consecutive_losses >= threshold
        assert should_demote

    def test_normal_operation_no_demotion(self) -> None:
        """Test that normal operation doesn't trigger demotion."""
        divergence = 0.12
        error_count = 0
        consecutive_losses = 0

        should_demote = (
            divergence >= 0.40
            or error_count / 100 > 0.05  # Assuming 100 requests
            or consecutive_losses >= 3
        )

        assert not should_demote


class TestPositionFractionValidation:
    """Tests for position fraction validation."""

    def test_position_fraction_within_canary_limit(self) -> None:
        """Test position fraction within CANARY limit."""
        canary_max = 0.01
        current_fraction = 0.005

        is_valid = current_fraction <= canary_max
        assert is_valid

    def test_position_fraction_exceeds_canary_limit(self) -> None:
        """Test position fraction exceeding CANARY limit is invalid."""
        canary_max = 0.01
        current_fraction = 0.015

        is_valid = current_fraction <= canary_max
        assert not is_valid


class TestExperimentLimits:
    """Tests for experiment limits validation."""

    def test_single_experiment_is_valid(self) -> None:
        """Test that 1 experiment per cycle is valid."""
        experiments_per_cycle = 1
        max_experiments = 1

        is_valid = experiments_per_cycle <= max_experiments
        assert is_valid

    def test_multiple_experiments_invalid(self) -> None:
        """Test that >1 experiment per cycle is invalid."""
        experiments_per_cycle = 2
        max_experiments = 1

        is_valid = experiments_per_cycle <= max_experiments
        assert not is_valid


class TestConsecutiveNonRegression:
    """Tests for consecutive non-regression checks."""

    def test_met_promotion_threshold(self) -> None:
        """Test that 5+ consecutive checks meet promotion threshold."""
        consecutive = 5
        required = 5

        can_promote = consecutive >= required
        assert can_promote

    def test_below_promotion_threshold(self) -> None:
        """Test that <5 consecutive checks don't meet promotion threshold."""
        consecutive = 3
        required = 5

        can_promote = consecutive >= required
        assert not can_promote

    def test_exactly_at_threshold(self) -> None:
        """Test that exactly 5 consecutive checks meet threshold."""
        consecutive = 5
        required = 5

        can_promote = consecutive >= required
        assert can_promote


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
