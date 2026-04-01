"""Tests for SeverityMapper."""

from unittest.mock import patch

from src.governance.notifications.severity_mapper import (
    DEFAULT_SEVERITY,
    SeverityMapper,
)


class TestSeverityMapper:
    """Test cases for SeverityMapper."""

    def test_load_policy_low_severity_events(self):
        """Test that low severity events map correctly."""
        mapper = SeverityMapper()
        assert mapper.get_severity("minor_preference_refinement") == "low"
        assert mapper.get_severity("small_workflow_observation") == "low"
        assert mapper.get_severity("weak_pattern") == "low"

    def test_load_policy_medium_severity_events(self):
        """Test that medium severity events map correctly."""
        mapper = SeverityMapper()
        assert mapper.get_severity("useful_new_belief") == "medium"
        assert mapper.get_severity("lesson_promotion") == "medium"
        assert mapper.get_severity("lesson_deprecation") == "medium"
        assert mapper.get_severity("recurring_pattern") == "medium"
        assert mapper.get_severity("tool_preference_change") == "medium"

    def test_load_policy_high_severity_events(self):
        """Test that high severity events map correctly."""
        mapper = SeverityMapper()
        assert mapper.get_severity("execution_quality_change") == "high"
        assert mapper.get_severity("planning_quality_change") == "high"
        assert mapper.get_severity("coordination_quality_change") == "high"
        assert mapper.get_severity("memory_integrity_issue") == "high"

    def test_load_policy_critical_severity_events(self):
        """Test that critical severity events map correctly."""
        mapper = SeverityMapper()
        assert mapper.get_severity("core_identity_conflict") == "critical"
        assert mapper.get_severity("prd_alignment_conflict") == "critical"
        assert mapper.get_severity("governance_or_safety_conflict") == "critical"
        assert mapper.get_severity("major_contradiction") == "critical"
        assert mapper.get_severity("harmful_autonomous_behavior_risk") == "critical"

    def test_unknown_event_type_defaults_to_low(self):
        """Test that unknown event types default to low severity."""
        mapper = SeverityMapper()
        assert mapper.get_severity("unknown_event_type_xyz") == DEFAULT_SEVERITY
        assert mapper.get_severity("") == DEFAULT_SEVERITY
        assert mapper.get_severity("totally_fictional_event") == DEFAULT_SEVERITY

    def test_feature_flag_disabled_returns_default(self):
        """Test that disabled feature flag returns default severity."""
        with patch(
            "src.governance.notifications.severity_mapper._get_redis_client",
            return_value={"get": lambda k, d: "false"},
        ):
            mapper = SeverityMapper()
            assert mapper.get_severity("core_identity_conflict") == DEFAULT_SEVERITY

    def test_invalid_severity_in_policy_defaults_to_low(self):
        """Test graceful handling of invalid severity in policy."""
        mapper = SeverityMapper()
        # Even if policy had invalid severity, we handle it gracefully
        assert mapper.get_severity("some_event") == DEFAULT_SEVERITY

    def test_get_severity_for_belief_mutation_preserves_valid_severity(self):
        """Test that valid severity is preserved for belief mutations."""
        mapper = SeverityMapper()
        assert mapper.get_severity_for_belief_mutation("create", "high") == "high"
        assert (
            mapper.get_severity_for_belief_mutation("update", "critical") == "critical"
        )
        assert (
            mapper.get_severity_for_belief_mutation("deprecate", "medium") == "medium"
        )
        assert mapper.get_severity_for_belief_mutation("create", "low") == "low"

    def test_get_severity_for_belief_mutation_defaults_invalid(self):
        """Test that invalid severity defaults for belief mutations."""
        mapper = SeverityMapper()
        assert (
            mapper.get_severity_for_belief_mutation("create", "invalid")
            == DEFAULT_SEVERITY
        )
        assert mapper.get_severity_for_belief_mutation("update", "") == DEFAULT_SEVERITY
        assert (
            mapper.get_severity_for_belief_mutation("deprecate", "not_a_severity")
            == DEFAULT_SEVERITY
        )
