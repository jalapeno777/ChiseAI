"""Belief models for contradiction detection and revision."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class EvidenceRecord:
    """Canonical evidence item used for belief support scoring."""

    evidence_id: str
    source: str
    timestamp: str
    reliability: float
    summary: str
    source_family: str = "unknown"
    is_llm_judgment: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "reliability": self.reliability,
            "summary": self.summary,
            "source_family": self.source_family,
            "is_llm_judgment": self.is_llm_judgment,
            "metrics": self.metrics,
        }


@dataclass
class BeliefSupportScore:
    """Evidence-weighted support score for a belief."""

    belief_id: str
    support_score: float
    evidence_count: int
    avg_reliability: float
    confidence: float
    sources_quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "belief_id": self.belief_id,
            "support_score": self.support_score,
            "evidence_count": self.evidence_count,
            "avg_reliability": self.avg_reliability,
            "confidence": self.confidence,
            "sources_quality_score": self.sources_quality_score,
        }


@dataclass
class Belief:
    """Belief entity in the autonomous cognition graph."""

    belief_id: str
    statement: str
    domain: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    sources_quality_score: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "active"
    supersedes_belief_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "belief_id": self.belief_id,
            "statement": self.statement,
            "domain": self.domain,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "sources_quality_score": self.sources_quality_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "supersedes_belief_id": self.supersedes_belief_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Belief:
        return cls(
            belief_id=data["belief_id"],
            statement=data["statement"],
            domain=data["domain"],
            confidence=float(data["confidence"]),
            evidence_refs=list(data.get("evidence_refs", [])),
            sources_quality_score=float(data.get("sources_quality_score", 0.5)),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
            status=data.get("status", "active"),
            supersedes_belief_id=data.get("supersedes_belief_id"),
        )


@dataclass
class BeliefConflict:
    """Detected conflict between beliefs."""

    conflict_id: str
    belief_id_a: str
    belief_id_b: str
    similarity: float
    severity: str
    reason: str
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "belief_id_a": self.belief_id_a,
            "belief_id_b": self.belief_id_b,
            "similarity": self.similarity,
            "severity": self.severity,
            "reason": self.reason,
            "detected_at": self.detected_at,
        }


@dataclass
class BeliefRevision:
    """Belief revision with provenance and rationale."""

    revision_id: str
    old_belief_id: str
    new_belief_id: str
    reason: str
    evidence_refs: list[str]
    confidence_before: float
    confidence_after: float
    applied_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "old_belief_id": self.old_belief_id,
            "new_belief_id": self.new_belief_id,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "applied_at": self.applied_at,
        }
