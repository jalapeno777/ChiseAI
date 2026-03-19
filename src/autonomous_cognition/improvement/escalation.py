"""Escalation management for autonomous improvement cycles.

This module provides the EscalationManager class which handles escalation events,
boundary approvals, emergency stop handling, and escalation history. It integrates
with the existing ApprovalGates for human-in-the-loop decisions.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EscalationType(str, Enum):
    """Types of escalation events."""

    BOUNDARY_VIOLATION = "boundary_violation"
    RISK_EXCEEDED = "risk_exceeded"
    SCOPE_EXCEEDED = "scope_exceeded"
    EMERGENCY_STOP = "emergency_stop"
    APPROVAL_REQUIRED = "approval_required"
    VALIDATION_FAILED = "validation_failed"


class EscalationStatus(str, Enum):
    """Status of an escalation event."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    TIMEOUT = "timeout"


@dataclass
class EscalationEvent:
    """An escalation event requiring attention.

    Attributes:
        event_id: Unique identifier for this event
        escalation_type: Type of escalation
        status: Current status
        description: Human-readable description
        severity: Severity level (low/medium/high/critical)
        proposal_id: ID of the proposal that triggered escalation
        created_at: When the event was created
        resolved_at: When the event was resolved (if applicable)
        resolved_by: Who resolved the event
        metadata: Additional context
    """

    event_id: str
    escalation_type: EscalationType
    status: EscalationStatus = EscalationStatus.PENDING
    description: str = ""
    severity: str = "medium"
    proposal_id: str = ""
    created_at: str = ""
    resolved_at: str = ""
    resolved_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_id": self.event_id,
            "escalation_type": self.escalation_type.value,
            "status": self.status.value,
            "description": self.description,
            "severity": self.severity,
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "metadata": self.metadata,
        }


class EscalationManager:
    """Manages escalation events for autonomous improvement cycles.

    This manager handles:
    - Creating escalation events from boundary violations
    - Routing to approval gates for human-in-the-loop decisions
    - Emergency stop handling
    - Escalation history tracking

    Example:
        >>> manager = EscalationManager(approval_gates=gates)
        >>> event = manager.create_escalation(
        ...     EscalationType.BOUNDARY_VIOLATION,
        ...     "Blocked path detected",
        ...     severity="critical"
        ... )
        >>> manager.request_boundary_approval(event)
    """

    def __init__(self, approval_gates: Any | None = None):
        """Initialize the escalation manager.

        Args:
            approval_gates: Optional ApprovalGates instance for human-in-the-loop.
                If None, escalations are logged but not routed to approval.
        """
        self._approval_gates = approval_gates
        self._events: dict[str, EscalationEvent] = {}
        self._history: list[EscalationEvent] = []
        self._emergency_stop_handlers: list[Any] = []

    def create_escalation(
        self,
        escalation_type: EscalationType,
        description: str,
        severity: str = "medium",
        proposal_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EscalationEvent:
        """Create a new escalation event.

        Args:
            escalation_type: Type of escalation
            description: Human-readable description
            severity: Severity level
            proposal_id: ID of the proposal that triggered this
            metadata: Additional context

        Returns:
            The created EscalationEvent
        """
        event = EscalationEvent(
            event_id=str(uuid.uuid4()),
            escalation_type=escalation_type,
            description=description,
            severity=severity,
            proposal_id=proposal_id,
            metadata=metadata or {},
        )
        self._events[event.event_id] = event
        logger.info(
            "Escalation created: id=%s type=%s severity=%s",
            event.event_id,
            escalation_type.value,
            severity,
        )
        return event

    def request_boundary_approval(self, event: EscalationEvent) -> str | None:
        """Request human approval for a boundary violation.

        Args:
            event: The escalation event requiring approval

        Returns:
            Approval request ID if approval gates available, None otherwise
        """
        if not self._approval_gates:
            logger.warning(
                "No approval gates configured — escalation %s logged but not routed",
                event.event_id,
            )
            return None

        decision = {
            "action": "boundary_override",
            "description": event.description,
            "risk_level": event.severity,
            "escalation_id": event.event_id,
            "proposal_id": event.proposal_id,
        }

        result = self._approval_gates.request_approval(decision)
        logger.info(
            "Boundary approval requested: escalation=%s request=%s",
            event.event_id,
            result.request_id,
        )
        return result.request_id

    def handle_emergency_stop(
        self,
        reason: str,
        proposal_id: str = "",
    ) -> EscalationEvent:
        """Handle an emergency stop event.

        Args:
            reason: Reason for the emergency stop
            proposal_id: ID of the proposal that triggered the stop

        Returns:
            The created EscalationEvent
        """
        event = self.create_escalation(
            EscalationType.EMERGENCY_STOP,
            f"Emergency stop: {reason}",
            severity="critical",
            proposal_id=proposal_id,
        )

        # Notify all registered handlers
        for handler in self._emergency_stop_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error("Emergency stop handler failed: %s", e)

        logger.critical("Emergency stop handled: %s", event.event_id)
        return event

    def register_emergency_stop_handler(self, handler: Any) -> None:
        """Register a handler for emergency stop events.

        Args:
            handler: Callable that takes an EscalationEvent
        """
        self._emergency_stop_handlers.append(handler)

    def resolve_escalation(
        self,
        event_id: str,
        resolved_by: str,
        status: EscalationStatus = EscalationStatus.RESOLVED,
    ) -> EscalationEvent | None:
        """Resolve an escalation event.

        Args:
            event_id: ID of the event to resolve
            resolved_by: Who resolved the event
            status: Resolution status

        Returns:
            The resolved event, or None if not found
        """
        event = self._events.get(event_id)
        if not event:
            logger.warning("Cannot resolve: escalation %s not found", event_id)
            return None

        event.status = status
        event.resolved_at = datetime.now(UTC).isoformat()
        event.resolved_by = resolved_by

        # Move to history
        self._history.append(event)
        del self._events[event_id]

        logger.info(
            "Escalation resolved: id=%s by=%s status=%s",
            event_id,
            resolved_by,
            status.value,
        )
        return event

    def get_pending_escalations(self) -> list[EscalationEvent]:
        """Get all pending escalation events."""
        return [
            e for e in self._events.values() if e.status == EscalationStatus.PENDING
        ]

    def get_escalation_history(
        self,
        limit: int = 100,
        escalation_type: EscalationType | None = None,
    ) -> list[EscalationEvent]:
        """Get escalation history with optional filtering.

        Args:
            limit: Maximum number of events to return
            escalation_type: Filter by escalation type

        Returns:
            List of historical EscalationEvents
        """
        history = self._history
        if escalation_type:
            history = [e for e in history if e.escalation_type == escalation_type]
        return history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get escalation statistics."""
        total = len(self._history) + len(self._events)
        pending = len(self.get_pending_escalations())

        type_counts: dict[str, int] = {}
        for event in list(self._events.values()) + self._history:
            key = event.escalation_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        return {
            "total_events": total,
            "pending": pending,
            "resolved": len(self._history),
            "by_type": type_counts,
        }
