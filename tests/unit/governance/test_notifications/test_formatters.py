"""Tests for governance notification formatters."""

from governance.notifications.formatters import (
    AutocogEventFormatter,
    SelfAssessmentNotificationFormatter,
)


class TestAutocogEventFormatter:
    """Test autonomous cognition event message formatting."""

    def test_format_event_includes_layman_sections(self) -> None:
        formatter = AutocogEventFormatter()

        content = formatter.format_event(
            event_type="improvement_promoted",
            severity="low",
            summary="Promoted candidate h-001",
            impact="Candidate exceeded promotion gates",
            top_metrics={"sharpe_delta": 0.11, "drawdown_delta": -0.02},
            artifact_path="_bmad-output/autocog/cycles/run.json",
            run_id="autocog-123",
            title="Improvement Candidate Promoted",
            issue="Candidate outperformed baseline under constraints.",
            intended_resolution="Promote candidate into active policy set.",
            expected_improvement="Higher risk-adjusted returns.",
            outcome_status="success",
            evidence_reasoning=[
                "Sharpe improved vs champion.",
                "No non-regression guardrail violation.",
            ],
        )

        assert "**Title:** Improvement Candidate Promoted" in content
        assert "**Why This Happened (Plain English):**" in content
        assert (
            "**Intended Resolution:** Promote candidate into active policy set."
            in content
        )
        assert (
            "**How This Should Improve Things:** Higher risk-adjusted returns."
            in content
        )
        assert "**Result:** Succeeded" in content
        assert "**Evidence / Reasoning:**" in content
        assert "Sharpe improved vs champion." in content

    def test_format_event_uses_defaults_when_layman_fields_missing(self) -> None:
        formatter = AutocogEventFormatter()

        content = formatter.format_event(
            event_type="belief_conflict_detected",
            severity="high",
            summary="Contradiction on memory reliability",
            impact="Belief graph contradiction requires revision or review.",
            top_metrics={"conflicts": 2},
            artifact_path=None,
            run_id="autocog-456",
        )

        assert "**Title:** Belief Conflict Detected" in content
        assert (
            "**Why This Happened (Plain English):** Contradiction on memory reliability"
            in content
        )
        assert (
            "**Intended Resolution:** Belief graph contradiction requires revision or review."
            in content
        )
        assert "**Result:** Unknown" in content

    def test_format_event_includes_revision_decision_packet(self) -> None:
        formatter = AutocogEventFormatter()

        content = formatter.format_event(
            event_type="belief_revision_applied",
            severity="medium",
            summary="Revision applied",
            impact="Conflict resolved",
            top_metrics={"revisions": 1},
            artifact_path="_bmad-output/autocog/belief_revisions/run.json",
            run_id="autocog-789",
            decision_packet={
                "contradiction": "Heuristic contradiction phrase detected",
                "previous_belief": {
                    "belief_id": "belief-memory-outdated",
                    "statement": "Memory is outdated.",
                },
                "replacement_belief": {
                    "belief_id": "belief-memory-health",
                    "statement": "Memory is healthy.",
                },
                "selection_rationale": "Winner had stronger evidence support.",
                "expected_improvements": [
                    "Reduce contradictions.",
                    "Improve policy consistency.",
                ],
                "source_diversity": {
                    "distinct_source_families": 3,
                    "non_llm_source_families": 2,
                    "source_families": [
                        "self_assessment_current",
                        "runtime_telemetry",
                        "governance_metrics",
                    ],
                },
                "rollback_hint": "Restore belief-memory-outdated if regressions occur.",
            },
        )

        assert "**Revision Decision Packet:**" in content
        assert "Contradiction: Heuristic contradiction phrase detected" in content
        assert (
            "Previous Belief: belief-memory-outdated | Memory is outdated." in content
        )
        assert (
            "Replacement Belief: belief-memory-health | Memory is healthy." in content
        )
        assert "Why This Won: Winner had stronger evidence support." in content
        assert "Source Diversity: distinct=3 non_llm=2" in content
        assert (
            "Rollback Hint: Restore belief-memory-outdated if regressions occur."
            in content
        )


class TestSelfAssessmentNotificationFormatter:
    """Test self-assessment notification formatter."""

    def test_format_self_assessment_completed_ok_status(self) -> None:
        """Test Discord embed format for OK status with green color."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-001"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "ok"
            overall_score = 0.95
            findings = ["System operating normally", "All metrics within thresholds"]
            recommendations = ["Continue current operations"]
            dimensions = {"accuracy": 0.95, "latency": 0.88, "reliability": 0.92}

        embed = formatter.format_self_assessment_completed(
            artifact=Artifact(),
            artifact_path="docs/governance/self_assessments/sa-20260327-001.json",
        )

        # Check embed structure
        assert "title" in embed
        assert "✅ Self-Assessment Completed" in embed["title"]
        assert embed["color"] == formatter.COLOR_OK
        assert "fields" in embed
        # Check fields exist
        field_names = [f["name"] for f in embed["fields"]]
        assert "Assessment ID" in field_names
        assert "Date" in field_names
        assert "Overall Score" in field_names
        assert "Status" in field_names
        assert "Findings" in field_names
        assert "Recommendations" in field_names
        assert "Dimensions" in field_names
        # Check footer
        assert "footer" in embed
        assert "sa-20260327-001.json" in embed["footer"]["text"]

    def test_format_self_assessment_completed_degraded_status(self) -> None:
        """Test Discord embed format for degraded status with yellow/orange color."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-002"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "degraded"
            overall_score = 0.65
            findings = ["Elevated latency detected", "Some metrics below threshold"]
            recommendations = ["Investigate latency issue"]
            dimensions = {"accuracy": 0.70, "latency": 0.55, "reliability": 0.80}

        embed = formatter.format_self_assessment_completed(
            artifact=Artifact(),
            artifact_path="docs/governance/self_assessments/sa-20260327-002.json",
        )

        assert "⚠️ Self-Assessment Completed" in embed["title"]
        assert embed["color"] == formatter.COLOR_DEGRADED

    def test_format_self_assessment_completed_failed_status(self) -> None:
        """Test Discord embed format for failed status with red color."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-003"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "failed"
            overall_score = 0.25
            findings = ["Critical failure detected", "Multiple systems affected"]
            recommendations = ["Immediate intervention required"]
            dimensions = {"accuracy": 0.30, "latency": 0.40, "reliability": 0.20}

        embed = formatter.format_self_assessment_completed(
            artifact=Artifact(),
            artifact_path=None,
        )

        assert "🚨 Self-Assessment Completed" in embed["title"]
        assert embed["color"] == formatter.COLOR_FAILED
        # When no artifact path, footer should show N/A
        assert "footer" in embed
        assert "N/A" in embed["footer"]["text"]

    def test_format_self_assessment_completed_unknown_status(self) -> None:
        """Test Discord embed format for unknown status uses default color."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-004"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "unknown"
            overall_score = 0.0
            findings = []
            recommendations = []
            dimensions = {}

        embed = formatter.format_self_assessment_completed(artifact=Artifact())

        assert "📌 Self-Assessment Completed" in embed["title"]
        assert embed["color"] == formatter.COLOR_DEFAULT

    def test_format_self_assessment_completed_includes_findings_count(self) -> None:
        """Test that findings count is properly included in embed."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-005"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "ok"
            overall_score = 0.85
            findings = ["Finding 1", "Finding 2", "Finding 3", "Finding 4"]
            recommendations = ["Rec 1", "Rec 2"]
            dimensions = {}

        embed = formatter.format_self_assessment_completed(artifact=Artifact())

        # Find findings field
        findings_field = next(f for f in embed["fields"] if f["name"] == "Findings")
        assert findings_field["value"] == "4"
        assert findings_field["inline"] is True

        # Find recommendations field
        rec_field = next(f for f in embed["fields"] if f["name"] == "Recommendations")
        assert rec_field["value"] == "2"

    def test_format_self_assessment_completed_includes_dimensions(self) -> None:
        """Test that dimensions summary is included when dimensions are present."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-006"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "ok"
            overall_score = 0.90
            findings = []
            recommendations = []
            dimensions = {"accuracy": 0.95, "latency": 0.88, "reliability": 0.92}

        embed = formatter.format_self_assessment_completed(artifact=Artifact())

        # Find dimensions field
        dims_field = next(f for f in embed["fields"] if f["name"] == "Dimensions")
        assert "accuracy: 0.95" in dims_field["value"]
        assert "latency: 0.88" in dims_field["value"]
        assert "reliability: 0.92" in dims_field["value"]

    def test_format_self_assessment_completed_timestamp(self) -> None:
        """Test that timestamp is set to created_at of artifact."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-007"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T15:30:00+00:00"
            status = "ok"
            overall_score = 0.88
            findings = []
            recommendations = []
            dimensions = {}

        embed = formatter.format_self_assessment_completed(artifact=Artifact())

        assert embed["timestamp"] == "2026-03-27T15:30:00+00:00"

    def test_format_self_assessment_completed_preserves_existing_format(self) -> None:
        """Test that existing format_self_assessment method still works."""
        formatter = SelfAssessmentNotificationFormatter()

        class Artifact:
            assessment_id = "sa-20260327-008"
            assessment_date = "2026-03-27"
            created_at = "2026-03-27T10:00:00+00:00"
            status = "ok"
            overall_score = 0.85
            findings = ["Finding 1"]
            recommendations = ["Rec 1"]

        content = formatter.format_self_assessment(artifact=Artifact())

        # Should return string format, not embed dict
        assert isinstance(content, str)
        assert "**Event Type:** `self_assessment_completed`" in content
        assert "**Assessment ID:** `sa-20260327-008`" in content
        assert "**Overall Score:** 0.85" in content
