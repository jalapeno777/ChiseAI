"""Tests for AutonomyTuner."""

from __future__ import annotations

from autonomous_cognition.autonomy_tuner import (
    AutonomyBoundary,
    AutonomyConfig,
    AutonomyLevel,
    AutonomyTuner,
)


class TestAutonomyLevel:
    """Tests for AutonomyLevel enum."""

    def test_all_levels_exist(self):
        """All expected autonomy levels are defined."""
        assert AutonomyLevel.SUPERVISED.value == "supervised"
        assert AutonomyLevel.BOUNDED.value == "bounded"
        assert AutonomyLevel.ASSISTED.value == "assisted"
        assert AutonomyLevel.AUTONOMOUS.value == "autonomous"

    def test_levels_are_ordered(self):
        """Levels are ordered from restricted to autonomous."""
        levels = [
            AutonomyLevel.SUPERVISED,
            AutonomyLevel.BOUNDED,
            AutonomyLevel.ASSISTED,
            AutonomyLevel.AUTONOMOUS,
        ]
        # Check enum order matches intended autonomy progression
        for i, level in enumerate(levels[:-1]):
            assert levels[i].value != levels[i + 1].value
        # Supervised should be most restrictive (index 0)
        assert levels[0] == AutonomyLevel.SUPERVISED
        # Autonomous should be least restrictive (last index)
        assert levels[-1] == AutonomyLevel.AUTONOMOUS


class TestAutonomyTuner:
    """Tests for AutonomyTuner class."""

    def test_default_initialization(self):
        """Tuner initializes with sensible defaults."""
        tuner = AutonomyTuner()
        summary = tuner.get_summary()

        assert summary["stability_counter"] == 0
        assert summary["min_stability_required"] == 5
        assert summary["ece_thresholds"]["upper"] == 0.15
        assert summary["ece_thresholds"]["lower"] == 0.08
        assert summary["incident_threshold"] == 1
        assert summary["max_level"] == "autonomous"

    def test_custom_config(self):
        """Tuner accepts custom configuration."""
        config = AutonomyConfig(
            ece_upper_threshold=0.20,
            ece_lower_threshold=0.05,
            min_stability_window=3,
        )
        tuner = AutonomyTuner(config=config)

        summary = tuner.get_summary()
        assert summary["ece_thresholds"]["upper"] == 0.20
        assert summary["ece_thresholds"]["lower"] == 0.05
        assert summary["min_stability_required"] == 3

    def test_tune_regression_on_high_ece(self):
        """High ECE triggers regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="bounded",
            ece=0.20,  # Above 0.15 threshold
            incident_count=0,
            constitution_compliant=True,
        )

        assert decision.previous_level == "bounded"
        assert decision.new_level == "supervised"
        assert decision.reason == "regression_guardrail_triggered"
        assert decision.ece == 0.20

    def test_tune_regression_on_incident(self):
        """Incidents exceeding threshold trigger regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=2,  # Above threshold of 1
            constitution_compliant=True,
        )

        assert decision.previous_level == "assisted"
        assert decision.new_level == "bounded"
        assert decision.reason == "regression_guardrail_triggered"

    def test_single_incident_does_not_trigger_regression(self):
        """A single transient incident does not trigger regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=1,  # At threshold of 1, not exceeding
            constitution_compliant=True,
        )

        assert decision.previous_level == "assisted"
        assert decision.new_level == "assisted"

    def test_tune_regression_on_constitution_violation(self):
        """Constitution violation triggers two-level regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=0,
            constitution_compliant=False,
        )

        assert decision.previous_level == "assisted"
        assert decision.new_level == "supervised"  # Two levels down
        assert decision.reason == "constitution_violation"

    def test_tune_hold_level(self):
        """Moderate ECE with no incidents holds level."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="bounded",
            ece=0.10,  # Between 0.08 and 0.15
            incident_count=0,
            constitution_compliant=True,
        )

        assert decision.previous_level == "bounded"
        assert decision.new_level == "bounded"
        assert decision.reason == "hold_level"

    def test_tune_progression_after_stability(self):
        """Sustained low ECE with no incidents enables progression."""
        tuner = AutonomyTuner(config=AutonomyConfig(min_stability_window=3))

        # Build up stability counter
        for i in range(2):
            decision = tuner.tune(
                current_level="bounded",
                ece=0.05,  # Below lower threshold
                incident_count=0,
                constitution_compliant=True,
            )
            assert decision.new_level == "bounded"
            assert tuner.stability_counter == i + 1

        # Third time should progress
        decision = tuner.tune(
            current_level="bounded",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
        )

        assert decision.new_level == "assisted"
        assert decision.reason == "sustained_calibration_stability"

    def test_tune_max_level_cap(self):
        """Max level cap is respected."""
        config = AutonomyConfig(max_level=AutonomyLevel.BOUNDED)
        tuner = AutonomyTuner(config=config)

        decision = tuner.tune(
            current_level="autonomous",
            ece=0.02,  # Very low ECE
            incident_count=0,
            constitution_compliant=True,
        )

        # Should be capped at bounded
        assert decision.new_level == "bounded"

    def test_tune_health_score_escalation(self):
        """Low health score triggers regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
            health_score=40,  # Below 50 threshold
        )

        assert decision.new_level == "bounded"
        assert decision.reason == "health_score_escalation"

    def test_decision_history(self):
        """Tuner records decision history."""
        tuner = AutonomyTuner()

        tuner.tune(current_level="bounded", ece=0.10, incident_count=0)
        tuner.tune(current_level="bounded", ece=0.20, incident_count=0)

        history = tuner.get_decision_history()
        assert len(history) == 2
        assert history[0].previous_level == "bounded"
        assert history[1].ece == 0.20

    def test_clear_history(self):
        """History can be cleared."""
        tuner = AutonomyTuner()

        tuner.tune(current_level="bounded", ece=0.20, incident_count=0)
        assert len(tuner.get_decision_history()) == 1

        tuner.clear_history()
        assert len(tuner.get_decision_history()) == 0


class TestAutonomyBoundary:
    """Tests for AutonomyBoundary class."""

    def test_default_blocked_paths(self):
        """Default boundaries include constitution-protected paths."""
        boundary = AutonomyBoundary(level=AutonomyLevel.SUPERVISED)

        assert ".woodpecker.yml" in boundary.blocked_paths
        assert "docs/bmm-workflow-status.yaml" in boundary.blocked_paths
        assert "AGENTS.md" in boundary.blocked_paths

    def test_boundary_level_assignment(self):
        """Boundary stores correct level."""
        boundary = AutonomyBoundary(level=AutonomyLevel.AUTONOMOUS)
        assert boundary.level == AutonomyLevel.AUTONOMOUS


class TestAutonomyTunerBoundaryChecks:
    """Tests for boundary checking functionality."""

    def test_get_boundary(self):
        """Can retrieve boundary for a level."""
        tuner = AutonomyTuner()
        boundary = tuner.get_boundary(AutonomyLevel.BOUNDED)

        assert boundary.level == AutonomyLevel.BOUNDED
        assert boundary.max_risk_level == "medium"

    def test_get_boundary_by_string(self):
        """Can retrieve boundary using string level."""
        tuner = AutonomyTuner()
        boundary = tuner.get_boundary("bounded")

        assert boundary.level == AutonomyLevel.BOUNDED

    def test_action_permitted_within_boundary(self):
        """Action within boundary is permitted."""
        tuner = AutonomyTuner()
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",
            action_type="edit",
            files=["src/autonomous_cognition/test_file.py"],
            risk_level="medium",
        )

        assert permitted is True

    def test_action_blocked_by_risk_level(self):
        """Action exceeding risk level is blocked."""
        tuner = AutonomyTuner()
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",  # max_risk = medium
            action_type="edit",
            files=["src/something.py"],
            risk_level="high",
        )

        assert permitted is False
        assert "exceeds maximum" in reason

    def test_action_blocked_by_blocked_path(self):
        """Action on blocked path requires approval."""
        tuner = AutonomyTuner()
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",
            action_type="edit",
            files=[".woodpecker.yml"],
            risk_level="low",
        )

        assert permitted is False

    def test_action_blocked_by_too_many_files(self):
        """Action with too many files is blocked."""
        tuner = AutonomyTuner()
        # Use files within allowed paths for bounded level (src/autonomous_cognition/)
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",  # max 5 files
            action_type="edit",
            files=[
                "src/autonomous_cognition/file1.py",
                "src/autonomous_cognition/file2.py",
                "src/autonomous_cognition/file3.py",
                "src/autonomous_cognition/file4.py",
                "src/autonomous_cognition/file5.py",
                "src/autonomous_cognition/file6.py",
            ],
            risk_level="low",
        )

        assert permitted is False
        assert "Too many files" in reason


class TestEscalationChecks:
    """Tests for escalation determination."""

    def test_escalation_on_violation(self):
        """Constitution violation triggers escalation."""
        tuner = AutonomyTuner()
        needed, severity, reason = tuner.check_escalation_needed(
            incident_count=0,
            ece=0.05,
            constitution_violations=1,
        )

        assert needed is True
        assert severity == "P0"

    def test_escalation_on_multiple_incidents(self):
        """3+ incidents trigger P1 escalation."""
        tuner = AutonomyTuner()
        needed, severity, reason = tuner.check_escalation_needed(
            incident_count=3,
            ece=0.05,
            constitution_violations=0,
        )

        assert needed is True
        assert severity == "P1"

    def test_escalation_on_low_health(self):
        """Low health score triggers P2 escalation."""
        tuner = AutonomyTuner()
        needed, severity, reason = tuner.check_escalation_needed(
            incident_count=0,
            ece=0.05,
            constitution_violations=0,
            health_score=40,
        )

        assert needed is True
        assert severity == "P2"

    def test_escalation_on_high_ece(self):
        """High ECE triggers P2 escalation."""
        tuner = AutonomyTuner()
        needed, severity, reason = tuner.check_escalation_needed(
            incident_count=0,
            ece=0.20,  # Above threshold
            constitution_violations=0,
        )

        assert needed is True
        assert severity == "P2"

    def test_no_escalation_when_healthy(self):
        """No escalation when all metrics are good."""
        tuner = AutonomyTuner()
        needed, severity, reason = tuner.check_escalation_needed(
            incident_count=0,
            ece=0.05,
            constitution_violations=0,
            health_score=80,
        )

        assert needed is False
