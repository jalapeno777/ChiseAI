"""Tests for assessment_schema module."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from autonomous_cognition.schema.assessment_schema import (
    CURRENT_SCHEMA_VERSION,
    AssessmentArtifact,
    AssessmentStatus,
    DimensionScore,
    Evidence,
    Finding,
    Recommendation,
)


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_create_valid_dimension_score(self) -> None:
        """Test creating a valid dimension score."""
        dim = DimensionScore(dimension="test_dim", score=0.75, weight=1.0)
        assert dim.dimension == "test_dim"
        assert dim.score == 0.75
        assert dim.weight == 1.0

    def test_dimension_score_default_weight(self) -> None:
        """Test default weight is 1.0."""
        dim = DimensionScore(dimension="test_dim", score=0.5)
        assert dim.weight == 1.0

    def test_dimension_score_to_dict(self) -> None:
        """Test conversion to dictionary."""
        dim = DimensionScore(dimension="test_dim", score=0.8, details={"key": "value"})
        result = dim.to_dict()
        assert result["dimension"] == "test_dim"
        assert result["score"] == 0.8
        assert result["details"] == {"key": "value"}

    def test_dimension_score_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "dimension": "belief_consistency",
            "score": 0.9,
            "weight": 2.0,
        }
        dim = DimensionScore.from_dict(data)
        assert dim.dimension == "belief_consistency"
        assert dim.score == 0.9
        assert dim.weight == 2.0

    def test_dimension_score_invalid_score_raises(self) -> None:
        """Test that invalid score raises ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            DimensionScore(dimension="test", score=1.5)

    def test_dimension_score_negative_weight_raises(self) -> None:
        """Test that negative weight raises ValueError."""
        with pytest.raises(ValueError, match="Weight must be non-negative"):
            DimensionScore(dimension="test", score=0.5, weight=-0.5)


class TestFinding:
    """Tests for Finding dataclass."""

    def test_create_finding(self) -> None:
        """Test creating a valid finding."""
        finding = Finding(
            finding_id="find-001",
            category="safety",
            description="All safety checks passed",
            severity="info",
        )
        assert finding.finding_id == "find-001"
        assert finding.category == "safety"
        assert finding.severity == "info"

    def test_finding_default_severity(self) -> None:
        """Test default severity is info."""
        finding = Finding(finding_id="find-001", category="test", description="Test")
        assert finding.severity == "info"

    def test_finding_with_evidence_refs(self) -> None:
        """Test finding with evidence references."""
        finding = Finding(
            finding_id="find-001",
            category="test",
            description="Test",
            evidence_refs=["ev-001", "ev-002"],
        )
        assert len(finding.evidence_refs) == 2

    def test_finding_to_dict(self) -> None:
        """Test conversion to dictionary."""
        finding = Finding(
            finding_id="find-001",
            category="safety",
            description="Test finding",
            severity="warning",
            evidence_refs=["ev-001"],
        )
        result = finding.to_dict()
        assert result["finding_id"] == "find-001"
        assert result["severity"] == "warning"
        assert result["evidence_refs"] == ["ev-001"]

    def test_finding_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "finding_id": "find-002",
            "category": "performance",
            "description": "Performance acceptable",
            "severity": "info",
        }
        finding = Finding.from_dict(data)
        assert finding.finding_id == "find-002"
        assert finding.category == "performance"


class TestRecommendation:
    """Tests for Recommendation dataclass."""

    def test_create_recommendation(self) -> None:
        """Test creating a valid recommendation."""
        rec = Recommendation(
            recommendation_id="rec-001",
            category="improvement",
            description="Consider optimizing cache usage",
            priority="medium",
        )
        assert rec.recommendation_id == "rec-001"
        assert rec.priority == "medium"

    def test_recommendation_default_priority(self) -> None:
        """Test default priority is medium."""
        rec = Recommendation(
            recommendation_id="rec-001",
            category="test",
            description="Test",
        )
        assert rec.priority == "medium"

    def test_recommendation_to_dict(self) -> None:
        """Test conversion to dictionary."""
        rec = Recommendation(
            recommendation_id="rec-001",
            category="safety",
            description="Enable additional checks",
            priority="high",
            rationale="To improve safety margins",
        )
        result = rec.to_dict()
        assert result["recommendation_id"] == "rec-001"
        assert result["priority"] == "high"
        assert result["rationale"] == "To improve safety margins"

    def test_recommendation_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "recommendation_id": "rec-002",
            "category": "performance",
            "description": "Optimize queries",
            "priority": "low",
            "evidence_refs": ["ev-001"],
        }
        rec = Recommendation.from_dict(data)
        assert rec.recommendation_id == "rec-002"
        assert rec.priority == "low"


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_create_evidence(self) -> None:
        """Test creating valid evidence."""
        ev = Evidence(
            evidence_id="ev-001",
            source="metrics_collector",
            source_family="metrics",
            description="Response time data",
            timestamp="2026-03-27T10:00:00Z",
        )
        assert ev.evidence_id == "ev-001"
        assert ev.source == "metrics_collector"

    def test_evidence_with_content(self) -> None:
        """Test evidence with content payload."""
        ev = Evidence(
            evidence_id="ev-001",
            source="test",
            source_family="test",
            description="Test",
            timestamp="2026-03-27T10:00:00Z",
            content={"p50_ms": 45.2, "p95_ms": 120.0},
        )
        assert ev.content is not None
        assert ev.content["p50_ms"] == 45.2

    def test_evidence_to_dict(self) -> None:
        """Test conversion to dictionary."""
        ev = Evidence(
            evidence_id="ev-001",
            source="test",
            source_family="test",
            description="Test evidence",
            timestamp="2026-03-27T10:00:00Z",
        )
        result = ev.to_dict()
        assert result["evidence_id"] == "ev-001"
        assert result["description"] == "Test evidence"

    def test_evidence_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "evidence_id": "ev-002",
            "source": "api",
            "source_family": "api_metrics",
            "description": "API response times",
            "timestamp": "2026-03-27T10:00:00Z",
            "content": {"count": 1000},
        }
        ev = Evidence.from_dict(data)
        assert ev.evidence_id == "ev-002"
        assert ev.content == {"count": 1000}


class TestAssessmentArtifact:
    """Tests for AssessmentArtifact dataclass."""

    def test_create_assessment_artifact(self) -> None:
        """Test creating a valid assessment artifact."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            status="completed",
            overall_score=0.85,
        )
        assert artifact.assessment_id == "assess-001"
        assert artifact.status == "completed"
        assert artifact.overall_score == 0.85

    def test_assessment_artifact_default_values(self) -> None:
        """Test default values are set correctly."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
        )
        assert artifact.schema_version == CURRENT_SCHEMA_VERSION
        assert artifact.status == AssessmentStatus.UNKNOWN.value
        assert artifact.overall_score == 0.0
        assert artifact.dimensions == []
        assert artifact.findings == []
        assert artifact.recommendations == []
        assert artifact.evidence == []

    def test_assessment_artifact_with_dimensions(self) -> None:
        """Test artifact with dimension scores."""
        dimensions = [
            DimensionScore(dimension="belief_consistency", score=0.9),
            DimensionScore(dimension="decision_quality", score=0.85),
        ]
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            dimensions=dimensions,
        )
        assert len(artifact.dimensions) == 2

    def test_assessment_artifact_invalid_score_raises(self) -> None:
        """Test that invalid overall_score raises ValueError."""
        with pytest.raises(
            ValueError, match="overall_score must be between 0.0 and 1.0"
        ):
            AssessmentArtifact(
                assessment_id="assess-001",
                assessment_date="2026-03-27",
                created_at="2026-03-27T10:00:00Z",
                overall_score=1.5,
            )

    def test_assessment_artifact_to_dict(self) -> None:
        """Test conversion to dictionary."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            status="completed",
            overall_score=0.9,
        )
        result = artifact.to_dict()
        assert result["assessment_id"] == "assess-001"
        assert result["status"] == "completed"
        assert result["overall_score"] == 0.9
        assert result["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_assessment_artifact_to_json(self) -> None:
        """Test serialization to JSON."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
        )
        json_str = artifact.to_json()
        parsed = json.loads(json_str)
        assert parsed["assessment_id"] == "assess-001"

    def test_assessment_artifact_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "assessment_id": "assess-002",
            "assessment_date": "2026-03-27",
            "created_at": "2026-03-27T10:00:00Z",
            "status": "completed",
            "overall_score": 0.85,
            "schema_version": "1.0.0",
        }
        artifact = AssessmentArtifact.from_dict(data)
        assert artifact.assessment_id == "assess-002"
        assert artifact.overall_score == 0.85

    def test_assessment_artifact_from_json(self) -> None:
        """Test creation from JSON string."""
        json_str = json.dumps(
            {
                "assessment_id": "assess-003",
                "assessment_date": "2026-03-27",
                "created_at": "2026-03-27T10:00:00Z",
            }
        )
        artifact = AssessmentArtifact.from_json(json_str)
        assert artifact.assessment_id == "assess-003"

    def test_assessment_artifact_create_empty(self) -> None:
        """Test create_empty factory method."""
        artifact = AssessmentArtifact.create_empty("assess-004")
        assert artifact.assessment_id == "assess-004"
        assert artifact.assessment_date == datetime.now(UTC).date().isoformat()
        assert artifact.created_at is not None

    def test_assessment_artifact_create_empty_with_date(self) -> None:
        """Test create_empty with specific date."""
        artifact = AssessmentArtifact.create_empty("assess-005", "2026-01-15")
        assert artifact.assessment_date == "2026-01-15"

    def test_assessment_artifact_backward_compat_legacy_dimensions(
        self,
    ) -> None:
        """Test backward compatibility with legacy dict dimensions format."""
        # Legacy format: dimensions as dict[str, float]
        data = {
            "assessment_id": "assess-legacy-001",
            "assessment_date": "2026-03-27",
            "created_at": "2026-03-27T10:00:00Z",
            "dimensions": {
                "belief_consistency": 0.9,
                "decision_quality": 0.8,
            },
            "overall_score": 0.85,
        }
        artifact = AssessmentArtifact.from_dict(data)
        assert len(artifact.dimensions) == 2
        dim_names = {d.dimension for d in artifact.dimensions}
        assert "belief_consistency" in dim_names
        assert "decision_quality" in dim_names

    def test_assessment_artifact_backward_compat_legacy_findings(
        self,
    ) -> None:
        """Test backward compatibility with legacy list[str] findings format."""
        data = {
            "assessment_id": "assess-legacy-002",
            "assessment_date": "2026-03-27",
            "created_at": "2026-03-27T10:00:00Z",
            "findings": [
                "Safety checks passed",
                "Performance within bounds",
            ],
        }
        artifact = AssessmentArtifact.from_dict(data)
        assert len(artifact.findings) == 2
        assert artifact.findings[0].description == "Safety checks passed"
        assert artifact.findings[0].severity == "info"

    def test_assessment_artifact_backward_compat_legacy_evidence(
        self,
    ) -> None:
        """Test backward compatibility with legacy dict evidence format."""
        data = {
            "assessment_id": "assess-legacy-003",
            "assessment_date": "2026-03-27",
            "created_at": "2026-03-27T10:00:00Z",
            "evidence": {
                "safety_metrics": {"passed": 100, "failed": 0},
                "perf_metrics": {"p50": 45.2},
            },
        }
        artifact = AssessmentArtifact.from_dict(data)
        assert len(artifact.evidence) == 2
        ev_ids = {e.evidence_id for e in artifact.evidence}
        assert "safety_metrics" in ev_ids
        assert "perf_metrics" in ev_ids

    def test_assessment_artifact_backward_compat_run_metadata(
        self,
    ) -> None:
        """Test backward compatibility with run_metadata field."""
        data = {
            "assessment_id": "assess-legacy-004",
            "assessment_date": "2026-03-27",
            "created_at": "2026-03-27T10:00:00Z",
            "run_metadata": {
                "agent_version": "1.0.0",
                "run_id": "run-123",
            },
        }
        artifact = AssessmentArtifact.from_dict(data)
        assert artifact.metadata.get("agent_version") == "1.0.0"
        assert artifact.metadata.get("run_id") == "run-123"

    def test_assessment_artifact_compute_weighted_score_no_dimensions(
        self,
    ) -> None:
        """Test weighted score computation with no dimensions."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            overall_score=0.75,
        )
        assert artifact.compute_weighted_score() == 0.75

    def test_assessment_artifact_compute_weighted_score_with_dimensions(
        self,
    ) -> None:
        """Test weighted score computation with dimensions."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            dimensions=[
                DimensionScore(dimension="dim1", score=0.8, weight=1.0),
                DimensionScore(dimension="dim2", score=0.6, weight=1.0),
            ],
        )
        # (0.8 * 1.0 + 0.6 * 1.0) / 2.0 = 0.7
        assert artifact.compute_weighted_score() == 0.7

    def test_assessment_artifact_compute_weighted_score_unequal_weights(
        self,
    ) -> None:
        """Test weighted score with unequal weights."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            dimensions=[
                DimensionScore(dimension="dim1", score=1.0, weight=3.0),
                DimensionScore(dimension="dim2", score=0.5, weight=1.0),
            ],
        )
        # (1.0 * 3.0 + 0.5 * 1.0) / 4.0 = 0.875
        assert artifact.compute_weighted_score() == 0.875

    def test_assessment_artifact_validate_valid(self) -> None:
        """Test validation passes for valid artifact."""
        artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
            overall_score=0.85,
        )
        errors = artifact.validate()
        assert errors == []

    def test_assessment_artifact_validate_missing_id(self) -> None:
        """Test validation fails for missing assessment_id."""
        artifact = AssessmentArtifact(
            assessment_id="",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
        )
        errors = artifact.validate()
        assert "assessment_id is required" in errors

    def test_assessment_artifact_validate_invalid_dimension_score(
        self,
    ) -> None:
        """Test that invalid dimension score raises ValueError at construction."""
        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            AssessmentArtifact(
                assessment_id="assess-001",
                assessment_date="2026-03-27",
                created_at="2026-03-27T10:00:00Z",
                dimensions=[
                    DimensionScore(dimension="dim1", score=1.5),
                ],
            )

    def test_assessment_artifact_is_valid(self) -> None:
        """Test is_valid helper method."""
        valid_artifact = AssessmentArtifact(
            assessment_id="assess-001",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
        )
        assert valid_artifact.is_valid() is True

        invalid_artifact = AssessmentArtifact(
            assessment_id="",
            assessment_date="2026-03-27",
            created_at="2026-03-27T10:00:00Z",
        )
        assert invalid_artifact.is_valid() is False


class TestAssessmentStatus:
    """Tests for AssessmentStatus enum."""

    def test_assessment_status_values(self) -> None:
        """Test all status values are defined."""
        assert AssessmentStatus.COMPLETED.value == "completed"
        assert AssessmentStatus.FAILED.value == "failed"
        assert AssessmentStatus.PARTIAL.value == "partial"
        assert AssessmentStatus.PENDING.value == "pending"
        assert AssessmentStatus.UNKNOWN.value == "unknown"

    def test_assessment_status_is_string(self) -> None:
        """Test status enum values are strings."""
        for status in AssessmentStatus:
            assert isinstance(status.value, str)
