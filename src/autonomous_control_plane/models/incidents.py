"""Incident models for incident management and auto-remediation.

Provides dataclasses for incidents, remediation actions, notifications, and post-mortems.

For ST-NS-041: Incident Manager with Auto-Remediation
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, List, Protocol


class Severity(StrEnum):
    """Incident severity levels P0-P3."""

    P0 = (
        "P0"  # Critical - service down, data loss, security breach, live trading impact
    )
    P1 = "P1"  # High - major functionality impaired, performance degraded
    P2 = "P2"  # Medium - minor functionality impaired, workarounds exist
    P3 = "P3"  # Low - cosmetic issues, documentation, enhancements


class IncidentStatus(StrEnum):
    """Incident lifecycle status."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class NotificationChannel(StrEnum):
    """Notification channels for incident alerts."""

    DISCORD = "discord"
    GRAFANA_ONCALL = "grafana_oncall"
    EMAIL = "email"
    SLACK = "slack"


@dataclass
class IncidentEvent:
    """Event that triggers incident creation.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event (service_down, data_loss, etc.)
        source: Component that generated the event
        message: Event description
        timestamp: When event occurred
        severity_hint: Optional severity hint from source
        metadata: Additional structured data
    """

    event_type: str
    source: str
    message: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    severity_hint: Severity | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "severity_hint": self.severity_hint.value if self.severity_hint else None,
            "metadata": self.metadata,
        }


@dataclass
class RemediationAction:
    """Remediation action for an incident.

    Attributes:
        action_id: Unique action identifier
        action_type: Type of remediation action
        description: Human-readable description
        status: Execution status
        executed_at: When action was executed
        result: Action result (success/failure details)
        auto_executed: Whether action was auto-executed
        approved_by: Who approved the action (if manual)
    """

    action_type: str
    description: str
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"  # pending, executed, failed, rolled_back
    executed_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    auto_executed: bool = False
    approved_by: str | None = None

    def mark_executed(self, result: dict[str, Any], auto: bool = True) -> None:
        """Mark action as executed."""
        self.status = "executed" if result.get("success", False) else "failed"
        self.result = result
        self.executed_at = datetime.now(UTC)
        self.auto_executed = auto

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "description": self.description,
            "status": self.status,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "result": self.result,
            "auto_executed": self.auto_executed,
            "approved_by": self.approved_by,
        }


@dataclass
class Notification:
    """Incident notification record.

    Attributes:
        notification_id: Unique notification identifier
        channel: Notification channel used
        sent_at: When notification was sent
        content: Notification content
        acknowledged: Whether notification was acknowledged
        acknowledged_by: Who acknowledged (if applicable)
    """

    channel: NotificationChannel
    content: str
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    acknowledged_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "notification_id": self.notification_id,
            "channel": self.channel.value,
            "sent_at": self.sent_at.isoformat(),
            "content": self.content,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
        }


@dataclass
class PostMortem:
    """Post-mortem report for resolved incidents.

    Attributes:
        post_mortem_id: Unique identifier
        incident_id: Reference to parent incident
        summary: Executive summary
        timeline: Chronological event timeline
        root_cause: Root cause analysis
        impact_analysis: Impact on systems/users
        action_items: List of follow-up actions
        lessons_learned: Lessons and recommendations
        created_at: When post-mortem was created
        completed_at: When post-mortem was completed
    """

    incident_id: str
    summary: str = ""
    timeline: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str = ""
    impact_analysis: str = ""
    action_items: list[dict[str, Any]] = field(default_factory=list)
    lessons_learned: str = ""
    post_mortem_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def add_timeline_event(
        self, timestamp: datetime, event: str, actor: str = "system"
    ) -> None:
        """Add event to timeline."""
        self.timeline.append(
            {
                "timestamp": timestamp.isoformat(),
                "event": event,
                "actor": actor,
            }
        )

    def add_action_item(
        self,
        description: str,
        owner: str,
        priority: str,
        due_date: datetime | None = None,
    ) -> None:
        """Add action item."""
        self.action_items.append(
            {
                "description": description,
                "owner": owner,
                "priority": priority,
                "due_date": due_date.isoformat() if due_date else None,
                "status": "open",
            }
        )

    def complete(self) -> None:
        """Mark post-mortem as complete."""
        self.completed_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "post_mortem_id": self.post_mortem_id,
            "incident_id": self.incident_id,
            "summary": self.summary,
            "timeline": self.timeline,
            "root_cause": self.root_cause,
            "impact_analysis": self.impact_analysis,
            "action_items": self.action_items,
            "lessons_learned": self.lessons_learned,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


@dataclass
class Incident:
    """Main incident record.

    Attributes:
        incident_id: Unique incident identifier
        title: Incident title
        description: Detailed description
        severity: P0-P3 severity level
        status: Current lifecycle status
        source: Component that generated the incident
        created_at: When incident was created
        updated_at: When incident was last updated
        resolved_at: When incident was resolved
        closed_at: When incident was closed
        assigned_to: Current assignee
        remediation_actions: List of remediation actions taken
        notifications: List of notifications sent
        post_mortem: Post-mortem report (if resolved)
        metadata: Additional structured data
        triggered_by_event: ID of event that created this incident
        resolution_notes: Notes on how incident was resolved
    """

    title: str
    description: str
    severity: Severity
    source: str
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    assigned_to: str | None = None
    remediation_actions: list[RemediationAction] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)
    post_mortem: PostMortem | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    triggered_by_event: str | None = None
    resolution_notes: str = ""

    def update_status(self, new_status: IncidentStatus) -> None:
        """Update incident status with timestamp tracking."""
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.now(UTC)

        # Track resolution and closure times
        if new_status == IncidentStatus.RESOLVED and not self.resolved_at:
            self.resolved_at = datetime.now(UTC)
        elif new_status == IncidentStatus.CLOSED and not self.closed_at:
            self.closed_at = datetime.now(UTC)

        # Reopen: clear resolution times
        if new_status == IncidentStatus.OPEN and old_status != IncidentStatus.OPEN:
            self.resolved_at = None
            self.closed_at = None

    def assign(self, assignee: str) -> None:
        """Assign incident to someone."""
        self.assigned_to = assignee
        self.updated_at = datetime.now(UTC)

    def add_remediation_action(self, action: RemediationAction) -> None:
        """Add remediation action."""
        self.remediation_actions.append(action)
        self.updated_at = datetime.now(UTC)

    def add_notification(self, notification: Notification) -> None:
        """Add notification record."""
        self.notifications.append(notification)
        self.updated_at = datetime.now(UTC)

    def resolve(self, resolution_notes: str = "") -> None:
        """Resolve the incident."""
        self.resolution_notes = resolution_notes
        self.update_status(IncidentStatus.RESOLVED)

    def close(self) -> None:
        """Close the incident."""
        self.update_status(IncidentStatus.CLOSED)

    def reopen(self) -> None:
        """Reopen a resolved/closed incident."""
        self.update_status(IncidentStatus.OPEN)
        self.resolved_at = None
        self.closed_at = None
        self.resolution_notes = ""

    def generate_post_mortem(self) -> PostMortem:
        """Generate post-mortem report."""
        post_mortem = PostMortem(
            incident_id=self.incident_id,
            summary=f"Post-mortem for incident: {self.title}",
        )

        # Build timeline from incident lifecycle
        post_mortem.add_timeline_event(
            self.created_at, f"Incident created: {self.title}", "system"
        )

        if self.assigned_to:
            post_mortem.add_timeline_event(
                self.updated_at, f"Assigned to: {self.assigned_to}", "system"
            )

        for action in self.remediation_actions:
            if action.executed_at:
                post_mortem.add_timeline_event(
                    action.executed_at,
                    f"Remediation action: {action.action_type} ({action.status})",
                    (
                        "system"
                        if action.auto_executed
                        else (action.approved_by or "manual")
                    ),
                )

        if self.resolved_at:
            post_mortem.add_timeline_event(
                self.resolved_at,
                f"Incident resolved: {self.resolution_notes}",
                self.assigned_to or "system",
            )

        # Add template sections
        post_mortem.root_cause = "[To be filled] Root cause analysis"
        post_mortem.impact_analysis = "[To be filled] Impact on systems and users"
        post_mortem.lessons_learned = (
            "[To be filled] Lessons learned and recommendations"
        )

        # Add default action items
        post_mortem.add_action_item(
            "Complete root cause analysis",
            self.assigned_to or "incident-response-team",
            "high",
        )
        post_mortem.add_action_item(
            "Review and update monitoring/alerting",
            "sre-team",
            "medium",
        )

        self.post_mortem = post_mortem
        return post_mortem

    def get_resolution_time_seconds(self) -> float | None:
        """Get time to resolution in seconds."""
        if self.resolved_at and self.created_at:
            return (self.resolved_at - self.created_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "assigned_to": self.assigned_to,
            "remediation_actions": [a.to_dict() for a in self.remediation_actions],
            "notifications": [n.to_dict() for n in self.notifications],
            "post_mortem": self.post_mortem.to_dict() if self.post_mortem else None,
            "metadata": self.metadata,
            "triggered_by_event": self.triggered_by_event,
            "resolution_notes": self.resolution_notes,
        }


@dataclass
class IncidentMetrics:
    """Metrics for incident tracking.

    Attributes:
        total_incidents: Total incidents created
        by_severity: Breakdown by severity
        by_status: Breakdown by status
        creation_rate: Incidents per hour
        avg_resolution_time: Average time to resolution
        escalation_rate: Rate of escalations
    """

    total_incidents: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    creation_rate: float = 0.0  # per hour
    avg_resolution_time: float = 0.0  # seconds
    escalation_rate: float = 0.0  # percentage

    def record_incident(self, incident: Incident) -> None:
        """Record a new incident."""
        self.total_incidents += 1

        # Track by severity
        severity = incident.severity.value
        self.by_severity[severity] = self.by_severity.get(severity, 0) + 1

        # Track by status
        status = incident.status.value
        self.by_status[status] = self.by_status.get(status, 0) + 1

    def update_status_counts(self, incidents: list[Incident]) -> None:
        """Update status counts from incident list."""
        self.by_status = {}
        for incident in incidents:
            status = incident.status.value
            self.by_status[status] = self.by_status.get(status, 0) + 1

    def calculate_resolution_stats(self, incidents: list[Incident]) -> None:
        """Calculate resolution time statistics."""
        resolved = [i for i in incidents if i.resolved_at]
        if resolved:
            raw_times = [i.get_resolution_time_seconds() for i in resolved]
            times = [t for t in raw_times if t is not None]
            if times:
                self.avg_resolution_time = sum(times) / len(times)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_incidents": self.total_incidents,
            "by_severity": self.by_severity,
            "by_status": self.by_status,
            "creation_rate": self.creation_rate,
            "avg_resolution_time_seconds": self.avg_resolution_time,
            "escalation_rate": self.escalation_rate,
        }


# Severity classification rules
P0_EVENT_TYPES = {
    "service_down",
    "data_loss",
    "security_breach",
    "trading_failure",
    "critical_error",
    "system_crash",
    "database_corruption",
}

P1_EVENT_TYPES = {
    "performance_degraded",
    "high_error_rate",
    "api_failure",
    "database_slow",
    "memory_high",
    "disk_full",
}

P2_EVENT_TYPES = {
    "service_unhealthy",
    "cache_miss_high",
    "queue_backlog",
    "retry_exhausted",
    "timeout_increased",
}

P3_EVENT_TYPES = {
    "deprecated_api_usage",
    "minor_error",
    "cleanup_needed",
}


class IncidentStore(Protocol):
    """Protocol for incident storage backends."""

    async def save(self, incident: Incident) -> None:
        """Save or update an incident."""
        ...

    async def get(self, incident_id: str) -> Incident | None:
        """Get incident by ID."""
        ...

    async def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> List[Incident]:
        """List incidents with optional filtering."""
        ...

    async def delete(self, incident_id: str) -> bool:
        """Delete an incident."""
        ...

    async def get_all(self) -> List[Incident]:
        """Get all incidents."""
        ...
