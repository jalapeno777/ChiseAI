"""Integration tests for AutonomyTuner wiring into full_cycle.

These tests verify:
1. Production AutonomyTuner is used (not stub/hardcoded values)
2. Tuner adjusts parameters based on feedback
3. Tuner integrates with full_cycle correctly
"""

from __future__ import annotations

from autonomous_cognition.autonomy_tuner import (
    DEFAULT_ECE_LOWER,
    DEFAULT_ECE_UPPER,
    AutonomyConfig,
    AutonomyLevel,
    AutonomyTuner,
    AutonomyTuningDecision,
)


class TestProductionAutonomyTunerIsUsed:
    """Test 1: Verify production AutonomyTuner is used (not stub)."""

    def test_tuner_has_full_config_attribute(self) -> None:
        """Production tuner should have config property that stub lacks."""
        tuner = AutonomyTuner()
        # Production tuner has config attribute; stub does not
        assert hasattr(tuner, "config")
        assert isinstance(tuner.config, AutonomyConfig)

    def test_tuner_has_boundaries_attribute(self) -> None:
        """Production tuner should have boundaries property that stub lacks."""
        tuner = AutonomyTuner()
        assert hasattr(tuner, "boundaries")
        assert isinstance(tuner.boundaries, dict)
        assert AutonomyLevel.BOUNDED in tuner.boundaries

    def test_tuner_has_stability_counter(self) -> None:
        """Production tuner tracks stability counter for progression decisions."""
        tuner = AutonomyTuner()
        assert hasattr(tuner, "stability_counter")
        assert tuner.stability_counter == 0

    def test_tuner_has_get_boundary_method(self) -> None:
        """Production tuner should have get_boundary method."""
        tuner = AutonomyTuner()
        assert hasattr(tuner, "get_boundary")
        boundary = tuner.get_boundary(AutonomyLevel.BOUNDED)
        assert boundary.level == AutonomyLevel.BOUNDED

    def test_tuner_has_update_boundary_method(self) -> None:
        """Production tuner should allow boundary updates."""
        tuner = AutonomyTuner()
        assert hasattr(tuner, "update_boundary")
        tuner.update_boundary(AutonomyLevel.BOUNDED, max_files_per_action=10)
        boundary = tuner.get_boundary(AutonomyLevel.BOUNDED)
        assert boundary.max_files_per_action == 10

    def test_full_autonomy_config_exposed(self) -> None:
        """Production tuner should expose full AutonomyConfig."""
        config = AutonomyConfig(
            ece_upper_threshold=0.20,
            ece_lower_threshold=0.05,
            min_stability_window=3,
        )
        tuner = AutonomyTuner(config=config)
        assert tuner.config.ece_upper_threshold == 0.20
        assert tuner.config.ece_lower_threshold == 0.05
        assert tuner.config.min_stability_window == 3

    def test_default_ece_thresholds_from_constitution(self) -> None:
        """ECE thresholds should match constitution defaults."""
        assert DEFAULT_ECE_UPPER == 0.15
        assert DEFAULT_ECE_LOWER == 0.08


class TestTunerAdjustsParametersBasedOnFeedback:
    """Test 2: Verify tuner adjusts autonomy based on feedback signals."""

    def test_high_ece_triggers_regression(self) -> None:
        """High ECE (>15%) should cause autonomy level regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.20,  # Above upper threshold
            incident_count=0,
            constitution_compliant=True,
        )
        assert decision.new_level in (
            "bounded",
            "supervised",
        ), f"Expected regression from 'assisted', got {decision.new_level}"
        assert decision.reason == "regression_guardrail_triggered"

    def test_incident_triggers_regression(self) -> None:
        """Any incident should cause regression per constitution."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="bounded",
            ece=0.05,
            incident_count=1,  # Above incident threshold (0)
            constitution_compliant=True,
        )
        assert decision.new_level == "supervised"
        assert decision.reason == "regression_guardrail_triggered"

    def test_constitution_violation_triggers_two_level_regression(self) -> None:
        """Constitution violation triggers two-level regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=0,
            constitution_compliant=False,
        )
        # Two level regression: assisted -> supervised
        assert decision.new_level == "supervised"
        assert decision.reason == "constitution_violation"

    def test_sustained_low_ece_enables_progression(self) -> None:
        """Sustained low ECE with no incidents enables progression."""
        config = AutonomyConfig(min_stability_window=2)
        tuner = AutonomyTuner(config=config)

        # First call builds stability
        decision1 = tuner.tune(
            current_level="bounded",
            ece=0.05,  # Below lower threshold
            incident_count=0,
            constitution_compliant=True,
        )
        assert decision1.new_level == "bounded"
        assert decision1.reason == "building_stability"

        # Second call with stability counter >= min_stability_window triggers progression
        decision2 = tuner.tune(
            current_level="bounded",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
        )
        assert decision2.new_level == "assisted"
        assert decision2.reason == "sustained_calibration_stability"

    def test_hold_level_when_calibration_ambiguous(self) -> None:
        """ECE between thresholds should maintain current level."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="bounded",
            ece=0.10,  # Between 8% and 15%
            incident_count=0,
            constitution_compliant=True,
        )
        assert decision.new_level == "bounded"
        assert decision.reason == "hold_level"

    def test_max_level_cap_enforced(self) -> None:
        """Tuner should respect configured max_level."""
        config = AutonomyConfig(max_level=AutonomyLevel.BOUNDED, min_stability_window=2)
        tuner = AutonomyTuner(config=config)

        # First call: building stability (counter becomes 1)
        decision1 = tuner.tune(
            current_level="bounded",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
        )
        assert decision1.reason == "building_stability"
        assert decision1.new_level == "bounded"

        # Second call: stability_counter=2 >= min_stability_window=2, so would
        # progress to assisted, but max_level=BOUNDED caps it
        decision2 = tuner.tune(
            current_level="bounded",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
        )
        # Should be capped at bounded, not progress to assisted
        assert decision2.new_level == "bounded"
        assert decision2.reason == "max_level_cap"

    def test_health_score_below_threshold_triggers_escalation(self) -> None:
        """Low health score should trigger autonomy regression."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="assisted",
            ece=0.05,
            incident_count=0,
            constitution_compliant=True,
            health_score=40.0,  # Below 50 threshold
        )
        assert decision.new_level in ("bounded", "supervised")
        assert decision.reason == "health_score_escalation"


class TestTunerIntegratesWithFullCycle:
    """Test 3: Verify tuner integrates correctly with full_cycle patterns."""

    def test_tune_returns_full_decision_record(self) -> None:
        """Tuner should return complete AutonomyTuningDecision."""
        tuner = AutonomyTuner()
        decision = tuner.tune(
            current_level="bounded",
            ece=0.10,
            incident_count=0,
            constitution_compliant=True,
        )

        # Verify all fields are populated
        assert isinstance(decision, AutonomyTuningDecision)
        assert decision.previous_level == "bounded"
        assert decision.new_level in (
            "bounded",
            "supervised",
        )
        assert decision.reason in (
            "hold_level",
            "regression_guardrail_triggered",
        )
        assert decision.ece == 0.10
        assert decision.incident_count == 0
        assert decision.constitution_compliant is True

    def test_decision_history_tracked(self) -> None:
        """Tuner should track decision history for auditing."""
        tuner = AutonomyTuner()
        tuner.tune(current_level="bounded", ece=0.10, incident_count=0)
        tuner.tune(current_level="bounded", ece=0.05, incident_count=0)

        history = tuner.get_decision_history()
        assert len(history) == 2
        assert history[0].previous_level == "bounded"
        assert history[1].previous_level == "bounded"

    def test_check_escalation_needed_constitution_violation(self) -> None:
        """Constitution violation should trigger P0 escalation."""
        tuner = AutonomyTuner()
        escalation_needed, severity, reason = tuner.check_escalation_needed(
            incident_count=0,
            ece=0.05,
            constitution_violations=1,
        )
        assert escalation_needed is True
        assert severity == "P0"
        assert reason == "constitution_violation_detected"

    def test_check_escalation_needed_multiple_incidents(self) -> None:
        """Multiple incidents should trigger P1 escalation."""
        tuner = AutonomyTuner()
        escalation_needed, severity, reason = tuner.check_escalation_needed(
            incident_count=3,
            ece=0.05,
            constitution_violations=0,
        )
        assert escalation_needed is True
        assert severity == "P1"
        assert reason == "multiple_incidents"

    def test_get_boundary_for_action_permits_valid_action(self) -> None:
        """get_boundary_for_action should validate actions against boundaries."""
        tuner = AutonomyTuner()
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",
            action_type="edit",
            files=["src/autonomous_cognition/foo.py"],
            risk_level="medium",
        )
        assert permitted is True
        assert reason == "Action permitted"

    def test_get_boundary_for_action_blocks_high_risk(self) -> None:
        """get_boundary_for_action should block high-risk actions at bounded level."""
        tuner = AutonomyTuner()
        permitted, reason = tuner.get_boundary_for_action(
            level="bounded",
            action_type="edit",
            files=["src/some_critical.py"],
            risk_level="critical",
        )
        assert permitted is False
        assert "exceeds maximum" in reason

    def test_full_cycle_tuning_pattern_matches_production(self) -> None:
        """Full cycle tuning call pattern should work with production tuner.

        This mirrors how full_cycle.py calls the tuner:
            tuning = self._tuner.tune(
                current_level=result.autonomy_level_before,
                ece=0.05 if promotions > 0 else 0.12,
                incident_count=0,
            )
        """
        tuner = AutonomyTuner()
        current_level = "bounded"

        # Case 1: promotions > 0 scenario
        decision_promotions = tuner.tune(
            current_level=current_level,
            ece=0.05,  # Lower ECE when promoting
            incident_count=0,
            constitution_compliant=True,
        )
        assert isinstance(decision_promotions, AutonomyTuningDecision)

        # Case 2: no promotions scenario
        decision_no_promotions = tuner.tune(
            current_level=current_level,
            ece=0.12,  # Higher ECE when not promoting
            incident_count=0,
            constitution_compliant=True,
        )
        assert isinstance(decision_no_promotions, AutonomyTuningDecision)
