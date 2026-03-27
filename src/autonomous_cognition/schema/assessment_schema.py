"""Canonical schema for self-assessment artifacts in autonomous cognition.

This module defines the official schema for assessment outputs, including
status, overall score, dimensions, findings, recommendations, evidence, and metadata.

Schema versioning is implemented to ensure backward compatibility as the
schema evolves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AssessmentStatus(str, Enum):
    """Enumeration of valid assessment statuses."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"
    UNKNOWN = "unknown"


class DimensionType(str, Enum):
    """Categories of assessment dimensions."""

    BELIEF_CONSISTENCY = "belief_consistency"
    DECISION_QUALITY = "decision_quality"
    EXECUTION_ACCURACY = "execution_accuracy"
    SAFETY_COMPLIANCE = "safety_compliance"
    AUTONOMY_LEVEL = "autonomy_level"
    OVERALL = "overall"


@dataclass
class DimensionScore:
    """Score for a specific assessment dimension.

    Attributes:
        dimension: The name/type of the dimension being scored.
        score: Numeric score between 0.0 and 1.0.
        weight: Optional weight for aggregation (defaults to 1.0).
        details: Optional additional details about the score.
    """

    dimension: str
    score: float
    weight: float = 1.0
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate score bounds after initialization."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")
        if self.weight < 0.0:
            raise ValueError(f"Weight must be non-negative, got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "dimension": self.dimension,
            "score": self.score,
            "weight": self.weight,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DimensionScore:
        """Create from dictionary representation."""
        return cls(
            dimension=data["dimension"],
            score=float(data["score"]),
            weight=float(data.get("weight", 1.0)),
            details=data.get("details"),
        )


@dataclass
class Finding:
    """A finding from the self-assessment.

    Attributes:
        finding_id: Unique identifier for this finding.
        category: Category or domain this finding belongs to.
        description: Human-readable description of the finding.
        severity: Severity level (info, warning, error, critical).
        evidence_refs: List of evidence IDs supporting this finding.
    """

    finding_id: str
    category: str
    description: str
    severity: str = "info"
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "description": self.description,
            "severity": self.severity,
            "evidence_refs": self.evidence_refs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        """Create from dictionary representation."""
        return cls(
            finding_id=data["finding_id"],
            category=data["category"],
            description=data["description"],
            severity=data.get("severity", "info"),
            evidence_refs=list(data.get("evidence_refs", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Recommendation:
    """A recommendation arising from the self-assessment.

    Attributes:
        recommendation_id: Unique identifier for this recommendation.
        category: Category or domain this recommendation belongs to.
        description: Human-readable description of the recommendation.
        priority: Priority level (low, medium, high, critical).
        rationale: Explanation of why this recommendation is made.
        evidence_refs: List of evidence IDs supporting this recommendation.
    """

    recommendation_id: str
    category: str
    description: str
    priority: str = "medium"
    rationale: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "recommendation_id": self.recommendation_id,
            "category": self.category,
            "description": self.description,
            "priority": self.priority,
            "rationale": self.rationale,
            "evidence_refs": self.evidence_refs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recommendation:
        """Create from dictionary representation."""
        return cls(
            recommendation_id=data["recommendation_id"],
            category=data["category"],
            description=data["description"],
            priority=data.get("priority", "medium"),
            rationale=data.get("rationale"),
            evidence_refs=list(data.get("evidence_refs", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Evidence:
    """A piece of evidence from the self-assessment.

    Attributes:
        evidence_id: Unique identifier for this evidence.
        source: Source system or component that produced this evidence.
        source_family: Logical grouping of the evidence source.
        description: Human-readable description of the evidence.
        timestamp: ISO-formatted timestamp of when the evidence was captured.
        content: The actual evidence content or reference.
    """

    evidence_id: str
    source: str
    source_family: str
    description: str
    timestamp: str
    content: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "source_family": self.source_family,
            "description": self.description,
            "timestamp": self.timestamp,
            "content": self.content,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        """Create from dictionary representation."""
        return cls(
            evidence_id=data["evidence_id"],
            source=data["source"],
            source_family=data["source_family"],
            description=data["description"],
            timestamp=data["timestamp"],
            content=data.get("content"),
            metadata=dict(data.get("metadata", {})),
        )


CURRENT_SCHEMA_VERSION = "1.1.0"


@dataclass
class AssessmentArtifact:
    """Canonical schema for autonomous cognition self-assessment artifacts.

    This is the official schema for assessment outputs, including status,
    overall score, dimensions, findings, recommendations, evidence, and metadata.

    Attributes:
        assessment_id: Unique identifier for this assessment.
        assessment_date: ISO-formatted date of the assessment.
        created_at: ISO-formatted timestamp when the artifact was created.
        schema_version: Version of the schema used (for compatibility).
        status: Overall assessment status.
        overall_score: Aggregated score between 0.0 and 1.0.
        dimensions: List of dimension-specific scores.
        findings: List of findings from the assessment.
        recommendations: List of recommendations from the assessment.
        evidence: List of supporting evidence for findings/recommendations.
        metadata: Additional arbitrary metadata.

    Example:
        >>> artifact = AssessmentArtifact(
        ...     assessment_id="assess-001",
        ...     assessment_date="2026-03-27",
        ...     created_at="2026-03-27T12:00:00Z",
        ...     status="completed",
        ...     overall_score=0.85,
        ...     dimensions=[
        ...         DimensionScore(dimension="belief_consistency", score=0.9),
        ...     ],
        ... )
    """

    assessment_id: str
    assessment_date: str
    created_at: str
    schema_version: str = CURRENT_SCHEMA_VERSION
    status: str = AssessmentStatus.UNKNOWN.value
    overall_score: float = 0.0
    dimensions: list[DimensionScore] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate artifact after initialization."""
        if not 0.0 <= self.overall_score <= 1.0:
            raise ValueError(
                f"overall_score must be between 0.0 and 1.0, got {self.overall_score}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary representation.

        Returns:
            Dictionary with all artifact fields serialized.
        """
        return {
            "assessment_id": self.assessment_id,
            "assessment_date": self.assessment_date,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "status": self.status,
            "overall_score": self.overall_score,
            "dimensions": [
                d.to_dict() if isinstance(d, DimensionScore) else d
                for d in self.dimensions
            ],
            "findings": [
                f.to_dict() if isinstance(f, Finding) else f for f in self.findings
            ],
            "recommendations": [
                r.to_dict() if isinstance(r, Recommendation) else r
                for r in self.recommendations
            ],
            "evidence": [
                e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence
            ],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize artifact to JSON string.

        Args:
            indent: Number of spaces for JSON indentation.

        Returns:
            JSON-formatted string representation.
        """
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssessmentArtifact:
        """Create artifact from dictionary representation.

        Args:
            data: Dictionary with artifact fields.

        Returns:
            New AssessmentArtifact instance.

        Note:
            Handles both the new structured format and legacy flat formats
            for backward compatibility.
        """
        # Handle legacy dimensions format (dict[str, float] -> list[DimensionScore])
        dimensions_data = data.get("dimensions", [])
        if dimensions_data and isinstance(dimensions_data, dict):
            # Legacy format: {"dimension_name": score}
            dimensions = [
                DimensionScore(dimension=name, score=float(score))
                for name, score in dimensions_data.items()
            ]
        else:
            dimensions = [
                DimensionScore.from_dict(d) if isinstance(d, dict) else d
                for d in dimensions_data
            ]

        # Handle legacy findings format (list[str] -> list[Finding])
        findings_data = data.get("findings", [])
        if findings_data and all(isinstance(f, str) for f in findings_data):
            # Legacy format: ["finding string"]
            findings = [
                Finding(
                    finding_id=f"legacy-{i}",
                    category="general",
                    description=findings_str,
                    severity="info",
                )
                for i, findings_str in enumerate(findings_data)
            ]
        else:
            findings = [
                Finding.from_dict(f) if isinstance(f, dict) else f
                for f in findings_data
            ]

        # Handle legacy recommendations format
        recommendations_data = data.get("recommendations", [])
        if recommendations_data and all(
            isinstance(r, str) for r in recommendations_data
        ):
            # Legacy format: ["recommendation string"]
            recommendations = [
                Recommendation(
                    recommendation_id=f"legacy-{i}",
                    category="general",
                    description=rec_str,
                    priority="medium",
                )
                for i, rec_str in enumerate(recommendations_data)
            ]
        else:
            recommendations = [
                Recommendation.from_dict(r) if isinstance(r, dict) else r
                for r in recommendations_data
            ]

        # Handle legacy evidence format
        evidence_data = data.get("evidence", [])
        if evidence_data and isinstance(evidence_data, dict):
            # Legacy format: dict[str, Any]
            evidence = []
            for ev_id, ev_content in evidence_data.items():
                evidence.append(
                    Evidence(
                        evidence_id=ev_id,
                        source="legacy",
                        source_family="legacy",
                        description="Legacy evidence",
                        timestamp=data.get("created_at", datetime.now(UTC).isoformat()),
                        content=ev_content,
                    )
                )
        else:
            evidence = [
                Evidence.from_dict(e) if isinstance(e, dict) else e
                for e in evidence_data
            ]

        return cls(
            assessment_id=data["assessment_id"],
            assessment_date=data["assessment_date"],
            created_at=data["created_at"],
            schema_version=data.get("schema_version", "1.0.0"),
            status=data.get("status", AssessmentStatus.UNKNOWN.value),
            overall_score=float(data.get("overall_score", 0.0)),
            dimensions=dimensions,
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            metadata=dict(data.get("metadata", data.get("run_metadata", {}))),
        )

    @classmethod
    def from_json(cls, json_str: str) -> AssessmentArtifact:
        """Create artifact from JSON string.

        Args:
            json_str: JSON-formatted string.

        Returns:
            New AssessmentArtifact instance.
        """
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def create_empty(
        cls,
        assessment_id: str,
        assessment_date: str | None = None,
    ) -> AssessmentArtifact:
        """Create an empty artifact with standard metadata.

        Args:
            assessment_id: Unique identifier for the assessment.
            assessment_date: Optional date string (defaults to today).

        Returns:
            New AssessmentArtifact with default values.
        """
        now = datetime.now(UTC)
        date_str = assessment_date or now.date().isoformat()
        return cls(
            assessment_id=assessment_id,
            assessment_date=date_str,
            created_at=now.isoformat(),
        )

    def compute_weighted_score(self) -> float:
        """Compute weighted average of dimension scores.

        Returns:
            Weighted average score, or overall_score if no dimensions.
        """
        if not self.dimensions:
            return self.overall_score

        total_weight = sum(d.weight for d in self.dimensions)
        if total_weight == 0:
            return self.overall_score

        weighted_sum = sum(d.score * d.weight for d in self.dimensions)
        return weighted_sum / total_weight

    def validate(self) -> list[str]:
        """Validate the artifact and return list of validation errors.

        Returns:
            Empty list if valid, otherwise list of error messages.
        """
        errors = []

        if not self.assessment_id:
            errors.append("assessment_id is required")

        if not self.assessment_date:
            errors.append("assessment_date is required")

        if not self.created_at:
            errors.append("created_at is required")

        if not 0.0 <= self.overall_score <= 1.0:
            errors.append(
                f"overall_score must be between 0.0 and 1.0, got {self.overall_score}"
            )

        for i, dim in enumerate(self.dimensions):
            if not 0.0 <= dim.score <= 1.0:
                errors.append(
                    f"dimensions[{i}].score must be between 0.0 and 1.0, got {dim.score}"
                )

        return errors

    def is_valid(self) -> bool:
        """Check if the artifact passes basic validation.

        Returns:
            True if valid, False otherwise.
        """
        return len(self.validate()) == 0
