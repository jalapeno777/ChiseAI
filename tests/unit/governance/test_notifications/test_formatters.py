"""Tests for governance notification formatters."""

from governance.notifications.formatters import (
    AutocogEventFormatter,
    SelfAssessmentNotificationFormatter,
)


class TestAutocogEventFormatter:
    """Test autonomous cognition event message formatting."""

    def test_format_event_includes_layman_sections(self) -> None:
        formatter = AutocogEventFormatter()

        chunks = formatter.format_event(
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

        assert isinstance(chunks, list)
        content = "\n".join(chunks)
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

        chunks = formatter.format_event(
            event_type="belief_conflict_detected",
            severity="high",
            summary="Contradiction on memory reliability",
            impact="Belief graph contradiction requires revision or review.",
            top_metrics={"conflicts": 2},
            artifact_path=None,
            run_id="autocog-456",
        )

        assert isinstance(chunks, list)
        content = "\n".join(chunks)
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

        chunks = formatter.format_event(
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

        assert isinstance(chunks, list)
        content = "\n".join(chunks)
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

    def test_format_event_returns_list_of_strings(self) -> None:
        """Test that format_event returns a list of strings, not a single string."""
        formatter = AutocogEventFormatter()

        chunks = formatter.format_event(
            event_type="improvement_promoted",
            severity="low",
            summary="Promoted candidate h-001",
            impact="Candidate exceeded promotion gates",
            top_metrics={"sharpe_delta": 0.11},
            artifact_path=None,
            run_id="autocog-123",
            outcome_status="success",
        )

        assert isinstance(chunks, list)
        assert all(isinstance(chunk, str) for chunk in chunks)
        assert len(chunks) >= 1

    def test_format_event_includes_tldr_summary(self) -> None:
        """Test that TL;DR summary appears at the top of the first chunk."""
        formatter = AutocogEventFormatter()

        chunks = formatter.format_event(
            event_type="belief_revision_applied",
            severity="medium",
            summary="Revision applied",
            impact="Conflict resolved",
            top_metrics={"revisions": 1},
            artifact_path=None,
            run_id="autocog-789",
            title="Belief Revision Applied",
            issue="Memory health belief outdated",
            intended_resolution="Update to healthier belief",
            outcome_status="success",
        )

        assert isinstance(chunks, list)
        first_chunk = chunks[0]
        assert "**📋 TL;DR:**" in first_chunk
        # The TL;DR should be near the top (within first 200 chars)
        tldr_pos = first_chunk.find("**📋 TL;DR:**")
        assert tldr_pos < 200, "TL;DR should appear near the top of the message"
        # Should contain some form of the outcome
        assert "Result:" in first_chunk or "Succeeded" in first_chunk

    def test_format_event_short_content_single_chunk(self) -> None:
        """Test that short content returns a single chunk (no unnecessary splitting)."""
        formatter = AutocogEventFormatter()

        chunks = formatter.format_event(
            event_type="simple_event",
            severity="low",
            summary="Simple test",
            impact="No impact",
            top_metrics={},
            artifact_path=None,
            run_id="run-001",
        )

        assert isinstance(chunks, list)
        assert (
            len(chunks) == 1
        ), "Short content should not be split into multiple chunks"
        # Verify no continuation markers
        assert "(continued" not in chunks[0]

    def test_format_event_long_content_splits_into_chunks(self) -> None:
        """Test that long content is split into multiple chunks at section boundaries."""
        formatter = AutocogEventFormatter()

        # Test the _split_into_chunks method directly with content we know exceeds the limit
        # Create a long section that is bigger than _MAX_DISCORD_MESSAGE_LEN
        long_line = "x" * 2000  # Single line exceeding the limit
        long_section = (
            f"\n\nSection 1:\n{long_line}\n\nSection 2:\nAnother paragraph here."
        )

        # Should split this into multiple chunks
        chunks = formatter._split_into_chunks(long_section)

        assert isinstance(chunks, list)
        assert len(chunks) > 1, "Content exceeding limit should be split"
        # Verify no chunk exceeds the limit
        for i, chunk in enumerate(chunks):
            assert (
                len(chunk) <= formatter._MAX_DISCORD_MESSAGE_LEN
            ), f"Chunk {i} exceeds {formatter._MAX_DISCORD_MESSAGE_LEN} chars: {len(chunk)}"

        # Verify all content is preserved (x count matches)
        full_content = "\n".join(chunks)
        assert "Section 1" in full_content
        assert "Section 2" in full_content
        # All 2000 x's are preserved (just split across chunks)
        assert (
            full_content.count("x") == 2000
        ), f"Expected 2000 x's, got {full_content.count('x')}"

    def test_split_into_chunks_preserves_sections(self) -> None:
        """Test that _split_into_chunks keeps sections intact on chunk boundaries."""
        formatter = AutocogEventFormatter()

        # Create content with distinct sections that should stay together
        section1 = "Section 1 content" * 100  # Long section
        section2 = "Section 2 content" * 100
        section3 = "Section 3 content" * 100

        content = f"Header\n\n{section1}\n\n{section2}\n\n{section3}"

        chunks = formatter._split_into_chunks(content)

        # Each chunk should be under the limit
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= formatter._MAX_DISCORD_MESSAGE_LEN

        # Verify sections are preserved (not split in middle)
        full_content = "\n".join(chunks)
        assert "Section 1 content" in full_content
        assert "Section 2 content" in full_content
        assert "Section 3 content" in full_content

    def test_format_event_continuation_markers(self) -> None:
        """Test that non-first chunks have continuation markers."""
        formatter = AutocogEventFormatter()

        # Create content long enough to require splitting
        long_evidence = [f"Reason {i}: " + "x" * 100 for i in range(15)]

        chunks = formatter.format_event(
            event_type="split_event",
            severity="high",
            summary="An event that will be split",
            impact="Testing chunking",
            top_metrics={"m1": "v1", "m2": "v2", "m3": "v3", "m4": "v4", "m5": "v5"},
            artifact_path=None,
            run_id="run-003",
            evidence_reasoning=long_evidence,
        )

        assert isinstance(chunks, list)
        if len(chunks) > 1:
            # Check continuation markers on non-first chunks
            for i in range(1, len(chunks)):
                assert (
                    "(continued" in chunks[i]
                ), f"Chunk {i} should have continuation marker"
                assert (
                    f"/{len(chunks)})" in chunks[i]
                ), f"Chunk {i} should show total chunk count"

    def test_no_data_loss_when_splitting(self) -> None:
        """Test that splitting preserves all data - no truncation or data loss."""
        formatter = AutocogEventFormatter()

        # Create event with all possible fields populated
        decision_packet = {
            "contradiction": "test contradiction",
            "previous_belief": {
                "belief_id": "prev-001",
                "statement": "Previous statement",
            },
            "replacement_belief": {
                "belief_id": "new-001",
                "statement": "Replacement statement",
            },
            "selection_rationale": "Better evidence",
            "expected_improvements": ["improvement 1", "improvement 2"],
            "source_diversity": {
                "distinct_source_families": 3,
                "non_llm_source_families": 2,
                "source_families": ["family1", "family2"],
            },
            "rollback_hint": "rollback if needed",
        }

        chunks = formatter.format_event(
            event_type="belief_revision_applied",
            severity="medium",
            summary="Full test event",
            impact="Testing data preservation",
            top_metrics={"metric1": 100, "metric2": 200},
            artifact_path="/path/to/artifact.json",
            run_id="run-full-001",
            title="Full Test Event",
            issue="Test issue",
            intended_resolution="Test resolution",
            expected_improvement="Test improvement",
            outcome_status="success",
            evidence_reasoning=["Reason 1", "Reason 2", "Reason 3"],
            decision_packet=decision_packet,
        )

        assert isinstance(chunks, list)
        full_content = "\n".join(chunks)

        # Verify no truncation text appears
        assert "[truncated" not in full_content
        assert "..." not in full_content

        # Verify all key data is present
        assert "Full Test Event" in full_content
        assert "Test issue" in full_content
        assert "Test resolution" in full_content
        assert "Test improvement" in full_content
        assert "Reason 1" in full_content
        assert "Reason 3" in full_content
        assert "test contradiction" in full_content
        assert "prev-001" in full_content
        assert "new-001" in full_content
        assert "Better evidence" in full_content
        assert "improvement 1" in full_content
        assert "rollback if needed" in full_content
        assert "metric1" in full_content
        assert "metric2" in full_content
        assert "/path/to/artifact.json" in full_content


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
