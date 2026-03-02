"""
Reflection artifact generation and validation.

This module handles the creation, validation, and serialization
of reflection artifacts according to the reflection policy schema.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ReflectionType(Enum):
    """Types of reflection loops."""

    MICRO = "micro"
    MESO = "meso"
    MACRO = "macro"


class FailureType(Enum):
    """Types of failures that can be observed."""

    TEST_FAILURE = "test_failure"
    CI_FAILURE = "ci_failure"
    LINT_FAILURE = "lint_failure"
    MERGE_CONFLICT = "merge_conflict"
    TIMEOUT = "timeout"


class Severity(Enum):
    """Severity levels for failures."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RootCauseCategory(Enum):
    """Categories for root cause analysis."""

    CODE_QUALITY = "code_quality"
    TEST_COVERAGE = "test_coverage"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    PROCESS = "process"
    KNOWLEDGE_GAP = "knowledge_gap"


class Priority(Enum):
    """Priority levels for automation targets."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class KPISnapshot:
    """Key performance indicator snapshot."""

    ci_pass_rate: float | None = None
    coverage: float | None = None
    cycle_time_hours: float | None = None
    test_count: int | None = None
    lines_changed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KPISnapshot:
        """Create from dictionary."""
        return cls(
            ci_pass_rate=data.get("ci_pass_rate"),
            coverage=data.get("coverage"),
            cycle_time_hours=data.get("cycle_time_hours"),
            test_count=data.get("test_count"),
            lines_changed=data.get("lines_changed"),
        )


@dataclass
class FailureObservation:
    """A single failure observation."""

    type: FailureType
    timestamp: str
    description: str
    severity: Severity

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "description": self.description,
            "severity": self.severity.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailureObservation:
        """Create from dictionary."""
        return cls(
            type=FailureType(data["type"]),
            timestamp=data["timestamp"],
            description=data["description"],
            severity=Severity(data["severity"]),
        )


@dataclass
class RootCause:
    """Root cause analysis entry."""

    category: RootCauseCategory
    description: str
    contributing_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "description": self.description,
            "contributing_factors": self.contributing_factors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RootCause:
        """Create from dictionary."""
        return cls(
            category=RootCauseCategory(data["category"]),
            description=data["description"],
            contributing_factors=data.get("contributing_factors", []),
        )


@dataclass
class AutomationTarget:
    """Suggested automation improvement."""

    target: str
    priority: Priority
    estimated_impact: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target": self.target,
            "priority": self.priority.value,
            "estimated_impact": self.estimated_impact,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationTarget:
        """Create from dictionary."""
        return cls(
            target=data["target"],
            priority=Priority(data["priority"]),
            estimated_impact=data["estimated_impact"],
        )


@dataclass
class PromotionCandidate:
    """Story recommended for promotion."""

    story_id: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "story_id": self.story_id,
            "reason": self.reason,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromotionCandidate:
        """Create from dictionary."""
        return cls(
            story_id=data["story_id"],
            reason=data["reason"],
            confidence=data["confidence"],
        )


@dataclass
class ReflectionArtifact:
    """
    Main reflection artifact data class.

    Represents a reflection at any level (micro, meso, macro)
    with associated metadata, KPIs, and analysis.
    """

    story_id: str
    reflection_type: ReflectionType
    timestamp: str
    what_changed: str
    kpi_snapshot: KPISnapshot | None = None
    failures_observed: list[FailureObservation] = field(default_factory=list)
    root_causes: list[RootCause] = field(default_factory=list)
    next_automation_targets: list[AutomationTarget] = field(default_factory=list)
    promotion_candidates: list[PromotionCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary."""
        result: dict[str, Any] = {
            "story_id": self.story_id,
            "reflection_type": self.reflection_type.value,
            "timestamp": self.timestamp,
            "what_changed": self.what_changed,
        }

        if self.kpi_snapshot:
            result["kpi_snapshot"] = self.kpi_snapshot.to_dict()
        if self.failures_observed:
            result["failures_observed"] = [f.to_dict() for f in self.failures_observed]
        if self.root_causes:
            result["root_causes"] = [r.to_dict() for r in self.root_causes]
        if self.next_automation_targets:
            result["next_automation_targets"] = [
                t.to_dict() for t in self.next_automation_targets
            ]
        if self.promotion_candidates:
            result["promotion_candidates"] = [
                p.to_dict() for p in self.promotion_candidates
            ]

        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert artifact to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflectionArtifact:
        """Create artifact from dictionary."""
        return cls(
            story_id=data["story_id"],
            reflection_type=ReflectionType(data["reflection_type"]),
            timestamp=data["timestamp"],
            what_changed=data["what_changed"],
            kpi_snapshot=(
                KPISnapshot.from_dict(data["kpi_snapshot"])
                if "kpi_snapshot" in data
                else None
            ),
            failures_observed=[
                FailureObservation.from_dict(f)
                for f in data.get("failures_observed", [])
            ],
            root_causes=[RootCause.from_dict(r) for r in data.get("root_causes", [])],
            next_automation_targets=[
                AutomationTarget.from_dict(t)
                for t in data.get("next_automation_targets", [])
            ],
            promotion_candidates=[
                PromotionCandidate.from_dict(p)
                for p in data.get("promotion_candidates", [])
            ],
        )

    @classmethod
    def from_json(cls, json_str: str) -> ReflectionArtifact:
        """Create artifact from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class ReflectionValidator:
    """Validates reflection artifacts against schema."""

    # Story ID pattern: ST-XXX-001 or ST-MACRO-{period}-{date}
    STORY_ID_PATTERN = re.compile(
        r"^ST-[A-Z]+-[0-9]+$|^ST-MACRO-(DAILY|WEEKLY)-[0-9]{8}$"
    )

    @staticmethod
    def validate_story_id(story_id: str) -> bool:
        """Validate story ID format."""
        return bool(ReflectionValidator.STORY_ID_PATTERN.match(story_id))

    @staticmethod
    def validate_reflection_type(reflection_type: str) -> bool:
        """Validate reflection type."""
        return reflection_type in [t.value for t in ReflectionType]

    @staticmethod
    def validate_timestamp(timestamp: str) -> bool:
        """Validate ISO 8601 timestamp."""
        try:
            # Must contain 'T' for ISO 8601 format (date only is not valid)
            if "T" not in timestamp:
                return False
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_kpi_snapshot(kpi: dict[str, Any]) -> list[str]:
        """Validate KPI snapshot values."""
        errors = []

        if "ci_pass_rate" in kpi:
            if not 0 <= kpi["ci_pass_rate"] <= 1:
                errors.append("ci_pass_rate must be between 0 and 1")

        if "coverage" in kpi:
            if not 0 <= kpi["coverage"] <= 1:
                errors.append("coverage must be between 0 and 1")

        if "cycle_time_hours" in kpi:
            if kpi["cycle_time_hours"] < 0:
                errors.append("cycle_time_hours must be non-negative")

        if "test_count" in kpi:
            if kpi["test_count"] < 0:
                errors.append("test_count must be non-negative")

        return errors

    @classmethod
    def validate_artifact(
        cls, artifact: ReflectionArtifact | dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Validate a reflection artifact.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Convert to dict if needed
        if isinstance(artifact, ReflectionArtifact):
            data = artifact.to_dict()
        else:
            data = artifact

        # Required fields
        required = ["story_id", "reflection_type", "timestamp", "what_changed"]
        for required_field in required:
            if required_field not in data:
                errors.append(f"Missing required field: {required_field}")

        if errors:
            return False, errors

        # Validate story_id
        if not cls.validate_story_id(data["story_id"]):
            errors.append(f"Invalid story_id format: {data['story_id']}")

        # Validate reflection_type
        if not cls.validate_reflection_type(data["reflection_type"]):
            errors.append(f"Invalid reflection_type: {data['reflection_type']}")

        # Validate timestamp
        if not cls.validate_timestamp(data["timestamp"]):
            errors.append(f"Invalid timestamp format: {data['timestamp']}")

        # Validate KPI snapshot if present
        if "kpi_snapshot" in data and data["kpi_snapshot"]:
            kpi_errors = cls.validate_kpi_snapshot(data["kpi_snapshot"])
            errors.extend(kpi_errors)

        return len(errors) == 0, errors


def create_reflection_artifact(
    story_id: str,
    reflection_type: ReflectionType,
    what_changed: str,
    kpi_snapshot: KPISnapshot | None = None,
    failures_observed: list[FailureObservation] | None = None,
    root_causes: list[RootCause] | None = None,
    next_automation_targets: list[AutomationTarget] | None = None,
    promotion_candidates: list[PromotionCandidate] | None = None,
) -> ReflectionArtifact:
    """
    Factory function to create a reflection artifact with current timestamp.

    Args:
        story_id: Story identifier (e.g., "ST-REFLECT-001")
        reflection_type: Type of reflection (micro, meso, macro)
        what_changed: Summary of what changed
        kpi_snapshot: Optional KPI metrics
        failures_observed: Optional list of failures
        root_causes: Optional list of root causes
        next_automation_targets: Optional list of automation targets
        promotion_candidates: Optional list of promotion candidates

    Returns:
        New ReflectionArtifact instance
    """
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    return ReflectionArtifact(
        story_id=story_id,
        reflection_type=reflection_type,
        timestamp=timestamp,
        what_changed=what_changed,
        kpi_snapshot=kpi_snapshot,
        failures_observed=failures_observed or [],
        root_causes=root_causes or [],
        next_automation_targets=next_automation_targets or [],
        promotion_candidates=promotion_candidates or [],
    )
