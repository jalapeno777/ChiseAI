"""Risk classification enums and classes."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    """Risk levels for PR path classification."""

    SAFE = "safe"  # Auto-approval eligible
    MEDIUM_RISK = "medium_risk"  # Requires GitReviewBot review
    COMPLEX = "complex"  # Requires human approval

    def __str__(self) -> str:
        return self.value

    @property
    def priority(self) -> int:
        """Higher number = higher risk priority."""
        priorities = {
            RiskLevel.SAFE: 0,
            RiskLevel.MEDIUM_RISK: 1,
            RiskLevel.COMPLEX: 2,
        }
        return priorities[self]

    @classmethod
    def from_highest(cls, levels: List["RiskLevel"]) -> "RiskLevel":
        """Return the highest risk level from a list."""
        if not levels:
            return cls.COMPLEX  # Default to most conservative
        return max(levels, key=lambda x: x.priority)


@dataclass(frozen=True)
class FileClassification:
    """Classification for a single file."""

    path: str
    risk_level: RiskLevel
    confidence: float
    pattern_matched: Optional[str] = None
    semantic_flags: List[str] = None

    def __post_init__(self):
        if self.semantic_flags is None:
            object.__setattr__(self, "semantic_flags", [])


@dataclass(frozen=True)
class RiskClassification:
    """Complete risk classification result for a PR."""

    risk_level: RiskLevel
    confidence: float
    files: List[str]
    file_classifications: List[FileClassification]
    reasoning: str
    pr_number: Optional[int] = None
    commit_sha: Optional[str] = None
    timestamp: Optional[str] = None
    analysis_duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "files": self.files,
            "file_classifications": [
                {
                    "path": fc.path,
                    "risk_level": fc.risk_level.value,
                    "confidence": fc.confidence,
                    "pattern_matched": fc.pattern_matched,
                    "semantic_flags": fc.semantic_flags,
                }
                for fc in self.file_classifications
            ],
            "reasoning": self.reasoning,
            "pr_number": self.pr_number,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp,
            "analysis_duration_ms": self.analysis_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskClassification":
        """Create from dictionary."""
        file_classifications = [
            FileClassification(
                path=fc["path"],
                risk_level=RiskLevel(fc["risk_level"]),
                confidence=fc["confidence"],
                pattern_matched=fc.get("pattern_matched"),
                semantic_flags=fc.get("semantic_flags", []),
            )
            for fc in data.get("file_classifications", [])
        ]

        return cls(
            risk_level=RiskLevel(data["risk_level"]),
            confidence=data["confidence"],
            files=data["files"],
            file_classifications=file_classifications,
            reasoning=data["reasoning"],
            pr_number=data.get("pr_number"),
            commit_sha=data.get("commit_sha"),
            timestamp=data.get("timestamp"),
            analysis_duration_ms=data.get("analysis_duration_ms"),
        )
