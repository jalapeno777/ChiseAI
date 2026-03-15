"""Tests for governance notification formatters."""

from governance.notifications.formatters import AutocogEventFormatter


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
        assert "**Intended Resolution:** Promote candidate into active policy set." in content
        assert "**How This Should Improve Things:** Higher risk-adjusted returns." in content
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
        assert "**Why This Happened (Plain English):** Contradiction on memory reliability" in content
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
        assert "Previous Belief: belief-memory-outdated | Memory is outdated." in content
        assert "Replacement Belief: belief-memory-health | Memory is healthy." in content
        assert "Why This Won: Winner had stronger evidence support." in content
        assert "Source Diversity: distinct=3 non_llm=2" in content
        assert "Rollback Hint: Restore belief-memory-outdated if regressions occur." in content
