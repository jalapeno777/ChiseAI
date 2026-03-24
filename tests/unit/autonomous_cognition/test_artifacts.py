"""Unit tests for autonomous cognition self-assessment artifacts."""

from __future__ import annotations

from autonomous_cognition.artifacts import SelfAssessmentArtifact


def test_self_assessment_artifact_round_trip() -> None:
    """Artifact should serialize and deserialize without loss."""
    artifact = SelfAssessmentArtifact(
        assessment_id="sa-20260313-abc12345",
        assessment_date="2026-03-13",
        created_at="2026-03-13T00:00:00+00:00",
        status="ok",
        overall_score=0.91,
        dimensions={"memory_health": 1.0},
        findings=["No issues"],
        recommendations=["Keep monitoring"],
        evidence={"memory_daily_sweep_enabled": True},
        run_metadata={"runner": "test"},
    )

    parsed = SelfAssessmentArtifact.from_json(artifact.to_json())
    assert parsed.assessment_id == artifact.assessment_id
    assert parsed.assessment_date == artifact.assessment_date
    assert parsed.overall_score == artifact.overall_score
    assert parsed.dimensions["memory_health"] == 1.0
    assert parsed.findings == ["No issues"]
