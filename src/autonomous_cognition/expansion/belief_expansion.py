"""Belief Expansion Module for Autonomous Cognition.

Provides timeboxed belief expansion that processes existing beliefs,
generates new insights, and stores results in Qdrant with proper metadata.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Default time limit in seconds (5 minutes)
DEFAULT_TIME_LIMIT_SECONDS = 300

# Default quality thresholds
DEFAULT_MIN_RELEVANCE_SCORE = 0.6
DEFAULT_MIN_CONFIDENCE = 0.5

# Qdrant collection for expanded beliefs
BELIEF_EXPANSION_COLLECTION = "autocog_belief_expansion"


class ExpansionType(Enum):
    """Types of belief expansion operations."""

    DERIVATION = "derivation"
    GENERALIZATION = "generalization"
    SPECIALIZATION = "specialization"
    ANALOGY = "analogy"
    INFERENCE = "inference"


@dataclass
class ExpandedBelief:
    """A belief generated from expansion of an existing belief."""

    belief_id: str
    statement: str
    domain: str
    confidence: float
    source_belief_id: str
    expansion_type: ExpansionType
    relevance_score: float
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "belief_id": self.belief_id,
            "statement": self.statement,
            "domain": self.domain,
            "confidence": self.confidence,
            "source_belief_id": self.source_belief_id,
            "expansion_type": self.expansion_type.value,
            "relevance_score": self.relevance_score,
            "evidence_refs": self.evidence_refs,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpandedBelief:
        return cls(
            belief_id=data["belief_id"],
            statement=data["statement"],
            domain=data["domain"],
            confidence=float(data["confidence"]),
            source_belief_id=data["source_belief_id"],
            expansion_type=ExpansionType(data["expansion_type"]),
            relevance_score=float(data["relevance_score"]),
            evidence_refs=list(data.get("evidence_refs", [])),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ExpansionConfig:
    """Configuration for belief expansion."""

    time_limit_seconds: float = DEFAULT_TIME_LIMIT_SECONDS
    min_relevance_score: float = DEFAULT_MIN_RELEVANCE_SCORE
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    max_expansions_per_belief: int = 10
    batch_size: int = 5
    qdrant_collection: str = BELIEF_EXPANSION_COLLECTION


@dataclass
class ExpansionProgress:
    """Tracks progress of belief expansion operation."""

    total_beliefs: int = 0
    processed_beliefs: int = 0
    expansions_generated: int = 0
    expansions_stored: int = 0
    expansions_filtered: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    timed_out: bool = False
    error_message: str | None = None

    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def is_within_time_limit(self, config: ExpansionConfig) -> bool:
        """Check if we're still within the time limit."""
        return self.elapsed_seconds() < config.time_limit_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_beliefs": self.total_beliefs,
            "processed_beliefs": self.processed_beliefs,
            "expansions_generated": self.expansions_generated,
            "expansions_stored": self.expansions_stored,
            "expansions_filtered": self.expansions_filtered,
            "elapsed_seconds": self.elapsed_seconds(),
            "timed_out": self.timed_out,
            "error_message": self.error_message,
        }


@dataclass
class ExpansionResult:
    """Result of a belief expansion operation."""

    success: bool
    progress: ExpansionProgress
    expanded_beliefs: list[ExpandedBelief] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "progress": self.progress.to_dict(),
            "expanded_belief_count": len(self.expanded_beliefs),
            "error": self.error,
        }
