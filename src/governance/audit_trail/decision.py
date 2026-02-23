"""
Decision models for audit trail.

Defines the structure and types of autonomous decisions that can be logged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DecisionType(str, Enum):
    """Types of autonomous decisions that can be logged."""

    PR_MERGE = "pr_merge"
    PR_REJECT = "pr_reject"
    BRANCH_CREATE = "branch_create"
    BRANCH_DELETE = "branch_delete"
    DEPLOY_PROMOTE = "deploy_promote"
    DEPLOY_ROLLBACK = "deploy_rollback"
    TASK_DELEGATE = "task_delegate"
    TASK_COMPLETE = "task_complete"
    OVERRIDE_APPROVE = "override_approve"
    OVERRIDE_REVOKE = "override_revoke"
    QUALITY_GATE_PASS = "quality_gate_pass"
    QUALITY_GATE_FAIL = "quality_gate_fail"
    INCIDENT_ESCALATE = "incident_escalate"
    INCIDENT_RESOLVE = "incident_resolve"
    CONSTITUTION_VIOLATION = "constitution_violation"
    CONSTITUTION_COMPLIANCE = "constitution_compliance"
    RESOURCE_ALLOCATE = "resource_allocate"
    SCHEDULE_TASK = "schedule_task"


class DecisionOutcome(str, Enum):
    """Outcome of a decision."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    DEFERRED = "deferred"


class ConstitutionPrinciple(str, Enum):
    """Constitution principles that may apply to decisions."""

    P001 = "P001"  # Human approval required for production changes
    P002 = "P002"  # No force pushes to main
    P003 = "P003"  # All changes must be reviewed
    P004 = "P004"  # Automated rollbacks on critical failures
    P005 = "P005"  # Audit all autonomous actions
    P006 = "P006"  # Rate limit autonomous operations
    P007 = "P007"  # No direct database mutations without human approval
    P008 = "P008"  # All deployments must be reversible
    P009 = "P009"  # Session isolation for parallel work
    P010 = "P010"  # Incident logging and response


@dataclass
class Decision:
    """
    Represents an autonomous decision made by an agent.

    Attributes:
        decision_id: Unique identifier for the decision
        timestamp: UTC timestamp when the decision was made
        agent_id: ID of the agent that made the decision
        decision_type: Type of decision
        context: Additional context about the decision
        rationale: Explanation of why the decision was made
        outcome: Result of the decision
        constitution_principles: List of applicable constitution principles
        story_id: Optional story/task ID this decision relates to
        metadata: Additional metadata
    """

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    agent_id: str = "unknown"
    decision_type: DecisionType = DecisionType.TASK_COMPLETE
    context: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    outcome: DecisionOutcome = DecisionOutcome.PENDING
    constitution_principles: list[ConstitutionPrinciple] = field(default_factory=list)
    story_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to dictionary for serialization."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "decision_type": self.decision_type.value,
            "context": self.context,
            "rationale": self.rationale,
            "outcome": self.outcome.value,
            "constitution_principles": [p.value for p in self.constitution_principles],
            "story_id": self.story_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        """Create decision from dictionary."""
        principles_data = data.get("constitution_principles", [])
        principles = [ConstitutionPrinciple(p) for p in principles_data]

        return cls(
            decision_id=data["decision_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data["agent_id"],
            decision_type=DecisionType(data["decision_type"]),
            context=data.get("context", {}),
            rationale=data.get("rationale", ""),
            outcome=DecisionOutcome(data.get("outcome", "pending")),
            constitution_principles=principles,
            story_id=data.get("story_id"),
            metadata=data.get("metadata", {}),
        )

    def __hash__(self) -> int:
        """Make decision hashable for use in sets."""
        return hash(self.decision_id)

    def __eq__(self, other: object) -> bool:
        """Check equality based on decision_id."""
        if not isinstance(other, Decision):
            return NotImplemented
        return self.decision_id == other.decision_id
