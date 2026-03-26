"""Tests for ProvisionalAssessor.

For ST-ICT-033: Provisional Accuracy Assessment

CRITICAL: These tests verify that outcome_label is "provisional_pass" ONLY.
Final BOS/CHoCH enablement (outcome_label="final_pass") is blocked pending
EP-ICT-006 Part-B completion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from market_analysis.ict_signals.provisional_assessor import (
    FINAL_DIRECTIONAL_ACCURACY_THRESHOLD,
    PROVISIONAL_BEARISH_ACCURACY_THRESHOLD,
    PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD,
    AssessmentResult,
    ProvisionalAssessor,
)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = None
    mock_client.setex.return_value = True
    mock_client.scan_iter.return_value = iter([])
    return mock_client


@pytest.fixture
def assessor(mock_redis_client):
    """Create ProvisionalAssessor instance with mocked Redis."""
    assessor = ProvisionalAssessor(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )
    assessor._redis_client = mock_redis_client
    return assessor


class TestProvisionalAssessor:
    """Tests for ProvisionalAssessor class."""

    def test_outcome_label_is_provisional_pass(self, assessor):
        """CRITICAL: Verify outcome_label returns 'provisional_pass' only.

        This is the most important test - final_pass must NOT be returned.
        """
        assert assessor.outcome_label == "provisional_pass"
        # Ensure it's NOT final_pass
        assert assessor.outcome_label != "final_pass"

    def test_outcome_label_is_hardcoded_provisional(self, assessor):
        """Verify outcome_label cannot return final_pass by design."""
        # Even if thresholds are met, outcome_label must remain provisional_pass
        # This is intentional - final enablement is blocked by EP-ICT-006 Part-B
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=65,  # High accuracy
            total_bearish=50,
            correct_bearish=30,
        )
        assert result.outcome_label == "provisional_pass"
        assert result.meets_provisional_threshold is True
        assert result.meets_final_threshold is False
        assert result.blocked_reason == "EP-ICT-006 Part-B not complete"

    def test_check_final_gate_dependency(self, assessor):
        """Verify final gate is blocked by EP-ICT-006 Part-B."""
        status = assessor.check_final_gate_dependency()

        assert status["is_blocked"] is True
        assert status["blocking_item"] == "EP-ICT-006 Part-B"
        assert status["current_status"] == "not_completed"

    def test_assess_directional_accuracy_meets_threshold(self, assessor):
        """Test directional accuracy assessment with passing result."""
        result = assessor.assess_directional_accuracy(
            total_signals=100,
            correct_predictions=60,  # 60% >= 55% threshold
        )

        assert result["accuracy"] == 60.0
        assert result["meets_threshold"] is True
        assert "PASS" in result["message"]

    def test_assess_directional_accuracy_fails_threshold(self, assessor):
        """Test directional accuracy assessment with failing result."""
        result = assessor.assess_directional_accuracy(
            total_signals=100,
            correct_predictions=50,  # 50% < 55% threshold
        )

        assert result["accuracy"] == 50.0
        assert result["meets_threshold"] is False
        assert "FAIL" in result["message"]

    def test_assess_directional_accuracy_no_signals(self, assessor):
        """Test directional accuracy with no signals."""
        result = assessor.assess_directional_accuracy(
            total_signals=0,
            correct_predictions=0,
        )

        assert result["accuracy"] == 0.0
        assert result["meets_threshold"] is False
        assert "No signals" in result["message"]

    def test_assess_bearish_accuracy_meets_threshold(self, assessor):
        """Test bearish accuracy assessment with passing result."""
        result = assessor.assess_bearish_accuracy(
            total_bearish=50,
            correct_bearish=25,  # 50% >= 45% threshold
        )

        assert result["accuracy"] == 50.0
        assert result["meets_threshold"] is True

    def test_assess_bearish_accuracy_fails_threshold(self, assessor):
        """Test bearish accuracy assessment with failing result."""
        result = assessor.assess_bearish_accuracy(
            total_bearish=50,
            correct_bearish=20,  # 40% < 45% threshold
        )

        assert result["accuracy"] == 40.0
        assert result["meets_threshold"] is False

    def test_assess_bearish_accuracy_no_signals(self, assessor):
        """Test bearish accuracy with no bearish signals."""
        result = assessor.assess_bearish_accuracy(
            total_bearish=0,
            correct_bearish=0,
        )

        assert result["accuracy"] == 0.0
        assert result["meets_threshold"] is False
        assert "No bearish signals" in result["message"]

    def test_calculate_statistical_confidence(self, assessor):
        """Test statistical confidence calculation."""
        result = assessor.calculate_statistical_confidence(
            total_signals=100,
            correct_predictions=60,
        )

        assert "confidence_level" in result
        assert result["accuracy"] == 60.0
        assert "lower_bound" in result
        assert "upper_bound" in result
        assert "margin_of_error" in result
        assert "is_significant" in result

    def test_calculate_statistical_confidence_no_signals(self, assessor):
        """Test statistical confidence with no signals."""
        result = assessor.calculate_statistical_confidence(
            total_signals=0,
            correct_predictions=0,
        )

        assert result["total_signals"] == 0
        assert result["accuracy"] == 0.0
        assert result["is_significant"] is False

    def test_generate_provisional_report_passes(self, assessor):
        """Test generating a passing provisional report."""
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=60,  # 60% >= 55%
            total_bearish=50,
            correct_bearish=30,  # 60% >= 45%
        )

        assert result.total_signals == 100
        assert result.correct_predictions == 60
        assert result.incorrect_predictions == 40
        assert result.directional_accuracy == 60.0
        assert result.bearish_accuracy == 60.0
        assert result.outcome_label == "provisional_pass"
        assert result.meets_provisional_threshold is True
        assert result.meets_final_threshold is False  # Blocked
        assert result.blocked_reason is not None

    def test_generate_provisional_report_fails_directional(self, assessor):
        """Test generating a failing provisional report (directional)."""
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=50,  # 50% < 55%
            total_bearish=50,
            correct_bearish=30,  # 60% >= 45%
        )

        assert result.directional_accuracy == 50.0
        assert result.meets_provisional_threshold is False
        assert result.outcome_label == "provisional_pass"  # Still provisional_pass

    def test_generate_provisional_report_fails_bearish(self, assessor):
        """Test generating a failing provisional report (bearish)."""
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=60,  # 60% >= 55%
            total_bearish=50,
            correct_bearish=20,  # 40% < 45%
        )

        assert result.bearish_accuracy == 40.0
        assert result.meets_provisional_threshold is False
        assert result.outcome_label == "provisional_pass"  # Still provisional_pass

    def test_generate_provisional_report_with_signal_types(self, assessor):
        """Test generating report with signal type breakdown."""
        signals_by_type = {
            "bos_bull": 30,
            "bos_bear": 25,
            "choch_bull": 25,
            "choch_bear": 20,
        }
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=60,
            total_bearish=45,
            correct_bearish=25,
            signals_by_type=signals_by_type,
        )

        assert result.signals_by_type == signals_by_type
        assert result.signals_by_type["bos_bull"] == 30

    def test_generate_provisional_report_final_blocked(self, assessor):
        """Test that final threshold is blocked regardless of results."""
        # Even with 65% directional (>= 60% final threshold)
        result = assessor.generate_provisional_report(
            total_signals=100,
            correct_predictions=65,
            total_bearish=50,
            correct_bearish=30,
        )

        assert result.directional_accuracy == 65.0
        assert result.meets_final_threshold is False
        assert result.blocked_reason == "EP-ICT-006 Part-B not complete"

    def test_get_latest_assessment_no_data(self, assessor):
        """Test getting latest assessment when none exists."""
        result = assessor.get_latest_assessment()
        assert result is None


class TestAssessmentResult:
    """Tests for AssessmentResult dataclass."""

    def test_assessment_result_creation(self):
        """Test AssessmentResult creation."""
        result = AssessmentResult(
            timestamp=datetime.now(UTC),
            total_signals=100,
            correct_predictions=60,
            incorrect_predictions=40,
            directional_accuracy=60.0,
            bearish_accuracy=50.0,
            bullish_accuracy=70.0,
            statistical_confidence=55.0,
            outcome_label="provisional_pass",
            meets_provisional_threshold=True,
            meets_final_threshold=False,
            blocked_reason="EP-ICT-006 Part-B not complete",
            signals_by_type={"bos_bull": 50, "bos_bear": 50},
        )

        assert result.total_signals == 100
        assert result.outcome_label == "provisional_pass"
        assert result.meets_provisional_threshold is True
        assert result.meets_final_threshold is False


class TestThresholds:
    """Tests for threshold constants."""

    def test_provisional_directional_threshold(self):
        """Verify provisional directional threshold is 55%."""
        assert PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD == 55.0

    def test_provisional_bearish_threshold(self):
        """Verify provisional bearish threshold is 45%."""
        assert PROVISIONAL_BEARISH_ACCURACY_THRESHOLD == 45.0

    def test_final_directional_threshold(self):
        """Verify final directional threshold is 60%."""
        assert FINAL_DIRECTIONAL_ACCURACY_THRESHOLD == 60.0

    def test_provisional_threshold_lower_than_final(self):
        """Verify provisional threshold is lower than final threshold."""
        assert (
            PROVISIONAL_DIRECTIONAL_ACCURACY_THRESHOLD
            < FINAL_DIRECTIONAL_ACCURACY_THRESHOLD
        )


class TestProvisionalPassRequirement:
    """CRITICAL: Tests that verify provisional_pass is the ONLY valid outcome.

    These tests exist to prevent accidental "final_pass" usage.
    """

    def test_provisional_pass_is_only_valid_outcome_label(self, assessor):
        """CRITICAL: outcome_label must ONLY return 'provisional_pass'."""
        # This test verifies the core requirement
        valid_outcomes = ["provisional_pass"]
        invalid_outcomes = ["final_pass", "pass", "approved", "enabled"]

        assert assessor.outcome_label in valid_outcomes
        assert assessor.outcome_label not in invalid_outcomes

    def test_generate_report_never_returns_final_pass(self, assessor):
        """CRITICAL: generate_provisional_report must never return final_pass."""
        # Test various scenarios that might attempt to return final_pass
        scenarios = [
            {
                "total_signals": 100,
                "correct_predictions": 65,
                "total_bearish": 50,
                "correct_bearish": 30,
            },
            {
                "total_signals": 50,
                "correct_predictions": 30,
                "total_bearish": 25,
                "correct_bearish": 15,
            },
            {
                "total_signals": 200,
                "correct_predictions": 130,
                "total_bearish": 100,
                "correct_bearish": 60,
            },
        ]

        for scenario in scenarios:
            result = assessor.generate_provisional_report(**scenario)
            assert result.outcome_label == "provisional_pass", (
                f"Scenario {scenario} returned {result.outcome_label} instead of provisional_pass"
            )

    def test_outcome_label_property_documentation_enforces_provisional(self, assessor):
        """Verify outcome_label property documentation explicitly states provisional only."""
        # Access the docstring from the property on the class
        docstring = ProvisionalAssessor.outcome_label.__doc__
        assert docstring is not None
        assert "provisional" in docstring.lower()
        assert "NOT final_pass" in docstring or "not final_pass" in docstring
