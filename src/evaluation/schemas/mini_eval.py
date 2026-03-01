"""Mini BrainEval schema definitions.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides dataclasses for Mini BrainEval results, issues, and mitigations.
Results are stored in Redis and InfluxDB for persistence and analysis.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class IssueCategory(Enum):
    """Categories of issues that can be detected during evaluation."""

    FILE_ACCESS = "file_access"
    DB_CONNECTIVITY = "db_connectivity"
    ENV_SLOWDOWN = "env_slowdown"
    TOOL_ERROR = "tool_error"
    OTHER = "other"


class IssueSeverity(Enum):
    """Severity levels for issues."""

    P0 = "P0"  # Critical - blocks evaluation
    P1 = "P1"  # High - significantly impacts evaluation
    P2 = "P2"  # Medium - minor impact
    P3 = "P3"  # Low - informational


class MitigationResult(Enum):
    """Result status of a mitigation action."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class Issue:
    """Represents an issue detected during evaluation.

    Attributes:
        issue_id: Unique identifier for the issue
        category: Category of the issue
        severity: Severity level (P0-P3)
        description: Human-readable description
        source: Where the issue was detected
        timestamp: ISO timestamp when issue was detected
    """

    issue_id: str
    category: str
    severity: str
    description: str
    source: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate issue fields."""
        # Validate category
        try:
            IssueCategory(self.category)
        except ValueError as err:
            valid_categories = [c.value for c in IssueCategory]
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of: {valid_categories}"
            ) from err

        # Validate severity
        try:
            IssueSeverity(self.severity)
        except ValueError as err:
            valid_severities = [s.value for s in IssueSeverity]
            raise ValueError(
                f"Invalid severity '{self.severity}'. "
                f"Must be one of: {valid_severities}"
            ) from err

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "source": self.source,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        """Create from dictionary."""
        return cls(
            issue_id=data["issue_id"],
            category=data["category"],
            severity=data["severity"],
            description=data["description"],
            source=data["source"],
            timestamp=data["timestamp"],
        )

    @classmethod
    def create(
        cls,
        category: IssueCategory,
        severity: IssueSeverity,
        description: str,
        source: str,
    ) -> Issue:
        """Create a new issue with auto-generated ID and timestamp."""
        return cls(
            issue_id=str(uuid.uuid4()),
            category=category.value,
            severity=severity.value,
            description=description,
            source=source,
            timestamp=datetime.now(UTC).isoformat(),
        )


@dataclass
class Mitigation:
    """Represents a mitigation action taken for an issue.

    Attributes:
        mitigation_id: Unique identifier for the mitigation
        issue_id: Reference to the issue being mitigated
        action: Description of what was done
        result: Success/failure/partial status
        timestamp: ISO timestamp when mitigation was applied
    """

    mitigation_id: str
    issue_id: str
    action: str
    result: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate mitigation fields."""
        # Validate result
        try:
            MitigationResult(self.result)
        except ValueError as err:
            valid_results = [r.value for r in MitigationResult]
            raise ValueError(
                f"Invalid result '{self.result}'. Must be one of: {valid_results}"
            ) from err

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mitigation_id": self.mitigation_id,
            "issue_id": self.issue_id,
            "action": self.action,
            "result": self.result,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mitigation:
        """Create from dictionary."""
        return cls(
            mitigation_id=data["mitigation_id"],
            issue_id=data["issue_id"],
            action=data["action"],
            result=data["result"],
            timestamp=data["timestamp"],
        )

    @classmethod
    def create(
        cls,
        issue_id: str,
        action: str,
        result: MitigationResult,
    ) -> Mitigation:
        """Create a new mitigation with auto-generated ID and timestamp."""
        return cls(
            mitigation_id=str(uuid.uuid4()),
            issue_id=issue_id,
            action=action,
            result=result.value,
            timestamp=datetime.now(UTC).isoformat(),
        )


@dataclass
class MiniEvalResult:
    """Result of a mini brain evaluation run.

    Attributes:
        eval_id: Unique identifier for the evaluation
        timestamp: ISO timestamp when evaluation was run
        cadence: Evaluation cadence ("6h", "daily", "weekly")
        kpis: Dictionary of measured KPI values
        proxies: Dictionary of proxy metrics when KPIs unavailable
        data_freshness: Dictionary of freshness per data source
        issues: List of issues encountered
        mitigations: List of mitigations applied
    """

    eval_id: str
    timestamp: str
    cadence: str
    kpis: dict[str, Any] = field(default_factory=dict)
    proxies: dict[str, Any] = field(default_factory=dict)
    data_freshness: dict[str, str] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    mitigations: list[Mitigation] = field(default_factory=list)

    # Valid cadence values
    VALID_CADENCES = {"6h", "daily", "weekly"}

    def __post_init__(self) -> None:
        """Validate cadence value."""
        if self.cadence not in self.VALID_CADENCES:
            raise ValueError(
                f"Invalid cadence '{self.cadence}'. "
                f"Must be one of: {self.VALID_CADENCES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "eval_id": self.eval_id,
            "timestamp": self.timestamp,
            "cadence": self.cadence,
            "kpis": self.kpis,
            "proxies": self.proxies,
            "data_freshness": self.data_freshness,
            "issues": [issue.to_dict() for issue in self.issues],
            "mitigations": [mit.to_dict() for mit in self.mitigations],
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MiniEvalResult:
        """Create from dictionary."""
        issues = [Issue.from_dict(i) for i in data.get("issues", [])]
        mitigations = [Mitigation.from_dict(m) for m in data.get("mitigations", [])]

        return cls(
            eval_id=data["eval_id"],
            timestamp=data["timestamp"],
            cadence=data["cadence"],
            kpis=data.get("kpis", {}),
            proxies=data.get("proxies", {}),
            data_freshness=data.get("data_freshness", {}),
            issues=issues,
            mitigations=mitigations,
        )

    @classmethod
    def from_json(cls, json_str: str) -> MiniEvalResult:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def create(
        cls,
        cadence: str,
        kpis: dict[str, Any] | None = None,
        proxies: dict[str, Any] | None = None,
        data_freshness: dict[str, str] | None = None,
    ) -> MiniEvalResult:
        """Create a new evaluation result with auto-generated ID and timestamp."""
        return cls(
            eval_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            cadence=cadence,
            kpis=kpis or {},
            proxies=proxies or {},
            data_freshness=data_freshness or {},
        )

    def add_issue(self, issue: Issue) -> None:
        """Add an issue to the result."""
        self.issues.append(issue)

    def add_mitigation(self, mitigation: Mitigation) -> None:
        """Add a mitigation to the result."""
        self.mitigations.append(mitigation)

    def has_critical_issues(self) -> bool:
        """Check if there are any P0 (critical) issues."""
        return any(issue.severity == IssueSeverity.P0.value for issue in self.issues)

    def get_issues_by_severity(self, severity: IssueSeverity) -> list[Issue]:
        """Get all issues of a specific severity."""
        return [issue for issue in self.issues if issue.severity == severity.value]

    def get_issues_by_category(self, category: IssueCategory) -> list[Issue]:
        """Get all issues of a specific category."""
        return [issue for issue in self.issues if issue.category == category.value]

    def get_mitigations_for_issue(self, issue_id: str) -> list[Mitigation]:
        """Get all mitigations for a specific issue."""
        return [mit for mit in self.mitigations if mit.issue_id == issue_id]
