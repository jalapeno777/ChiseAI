"""Self-assessment artifact schema for autonomous cognition."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any


@dataclass
class SelfAssessmentArtifact:
    """Unified artifact for daily autonomous cognition self-assessment."""

    assessment_id: str
    assessment_date: str
    created_at: str
    schema_version: str = "1.0.0"
    status: str = "ok"
    overall_score: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    run_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize artifact to JSON."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelfAssessmentArtifact:
        """Create artifact from dictionary."""
        return cls(
            assessment_id=data["assessment_id"],
            assessment_date=data["assessment_date"],
            created_at=data["created_at"],
            schema_version=data.get("schema_version", "1.0.0"),
            status=data.get("status", "ok"),
            overall_score=float(data.get("overall_score", 0.0)),
            dimensions=dict(data.get("dimensions", {})),
            findings=list(data.get("findings", [])),
            recommendations=list(data.get("recommendations", [])),
            evidence=dict(data.get("evidence", {})),
            run_metadata=dict(data.get("run_metadata", {})),
        )

    @classmethod
    def from_json(cls, json_str: str) -> SelfAssessmentArtifact:
        """Create artifact from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def create_empty(
        cls,
        assessment_id: str,
        assessment_date: date | None = None,
    ) -> SelfAssessmentArtifact:
        """Create an empty artifact with standard metadata."""
        day = assessment_date or datetime.now(UTC).date()
        return cls(
            assessment_id=assessment_id,
            assessment_date=day.isoformat(),
            created_at=datetime.now(UTC).isoformat(),
        )
