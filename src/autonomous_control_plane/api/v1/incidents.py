"""API routes for incident management.

FastAPI routes for incident lifecycle management:
- GET /api/v1/incidents - List incidents
- GET /api/v1/incidents/{id} - Get incident details
- POST /api/v1/incidents - Create incident (manual)
- PUT /api/v1/incidents/{id}/status - Update status
- POST /api/v1/incidents/{id}/assign - Assign incident
- POST /api/v1/incidents/{id}/resolve - Resolve incident
- GET /api/v1/incidents/{id}/post-mortem - Get post-mortem
- GET /api/v1/incidents/metrics - Get incident metrics

For ST-NS-041: Incident Manager with Auto-Remediation
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException, Query, status

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

    # Create dummy classes for type checking
    class APIRouter:
        def get(self, *args, **kwargs):
            def decorator(f):
                return f

            return decorator

        def post(self, *args, **kwargs):
            def decorator(f):
                return f

            return decorator

        def put(self, *args, **kwargs):
            def decorator(f):
                return f

            return decorator

    class HTTPException(Exception):
        pass

    class Query:
        def __init__(self, *args, **kwargs):
            pass


from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.models.incidents import (
    IncidentEvent,
    IncidentStatus,
    Severity,
)

# Global manager instance (initialized by dependency injection in production)
_manager: IncidentManager | None = None

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def set_manager(manager: IncidentManager) -> None:
    """Set the global manager instance."""
    global _manager
    _manager = manager


def get_manager() -> IncidentManager:
    """Get the global manager instance."""
    if _manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Incident manager not initialized",
        )
    return _manager


@router.get("")
async def list_incidents(
    status: str | None = Query(None, description="Filter by status"),
    severity: str | None = Query(None, description="Filter by severity (P0-P3)"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> dict[str, Any]:
    """List incidents with optional filtering.

    Args:
        status: Filter by status (open, investigating, mitigated, resolved, closed)
        severity: Filter by severity (P0, P1, P2, P3)
        source: Filter by source component
        limit: Maximum number of results

    Returns:
        List of incidents
    """
    manager = get_manager()

    # Parse filters
    status_filter = None
    if status:
        try:
            status_filter = IncidentStatus(status.lower())
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}",
            ) from e

    severity_filter = None
    if severity:
        try:
            severity_filter = Severity(severity.upper())
        except ValueError as e:
            # Use integer status code directly since status module might not be available
            raise HTTPException(
                status_code=400,  # HTTP_400_BAD_REQUEST
                detail=f"Invalid severity: {severity}",
            ) from e

    incidents = await manager.list_incidents(
        status=status_filter,
        severity=severity_filter,
        source=source,
        limit=limit,
    )

    return {
        "incidents": [incident.to_dict() for incident in incidents],
        "count": len(incidents),
        "filters": {
            "status": status,
            "severity": severity,
            "source": source,
        },
    }


@router.get("/{incident_id}")
async def get_incident(incident_id: str) -> dict[str, Any]:
    """Get incident details.

    Args:
        incident_id: ID of incident to retrieve

    Returns:
        Incident details
    """
    manager = get_manager()
    incident = await manager.get_incident(incident_id)

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident.to_dict()


@router.post("")
async def create_incident(request: dict[str, Any]) -> dict[str, Any]:
    """Create a new incident (manual).

    Args:
        request: Incident creation request with:
            - event_type: Type of event
            - source: Component source
            - message: Incident description
            - severity_hint: Optional severity override (P0-P3)
            - metadata: Optional additional data

    Returns:
        Created incident
    """
    manager = get_manager()

    # Validate request
    required_fields = ["event_type", "source", "message"]
    for field in required_fields:
        if field not in request:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required field: {field}",
            )

    # Parse severity hint if provided
    severity_hint = None
    if "severity_hint" in request:
        try:
            severity_hint = Severity(request["severity_hint"].upper())
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity: {request['severity_hint']}",
            ) from e

    # Create event
    event = IncidentEvent(
        event_type=request["event_type"],
        source=request["source"],
        message=request["message"],
        severity_hint=severity_hint,
        metadata=request.get("metadata", {}),
    )

    # Create incident
    incident = await manager.create_incident(event)

    return incident.to_dict()


@router.put("/{incident_id}/status")
async def update_incident_status(
    incident_id: str, request: dict[str, Any]
) -> dict[str, Any]:
    """Update incident status.

    Args:
        incident_id: ID of incident to update
        request: Status update with:
            - status: New status (open, investigating, mitigated, resolved, closed)

    Returns:
        Updated incident
    """
    manager = get_manager()

    # Validate request
    if "status" not in request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: status",
        )

    # Parse status
    try:
        new_status = IncidentStatus(request["status"].lower())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request['status']}",
        ) from e

    # Update status
    incident = await manager.transition_status(incident_id, new_status)

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident.to_dict()


@router.post("/{incident_id}/assign")
async def assign_incident(incident_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Assign incident to someone.

    Args:
        incident_id: ID of incident to assign
        request: Assignment with:
            - assignee: Person to assign to

    Returns:
        Updated incident
    """
    manager = get_manager()

    # Validate request
    if "assignee" not in request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: assignee",
        )

    # Assign incident
    incident = await manager.assign_incident(incident_id, request["assignee"])

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident.to_dict()


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Resolve an incident.

    Args:
        incident_id: ID of incident to resolve
        request: Resolution with:
            - resolution_notes: Notes on how incident was resolved

    Returns:
        Updated incident with post-mortem
    """
    manager = get_manager()

    # Validate request
    if "resolution_notes" not in request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: resolution_notes",
        )

    # Resolve incident
    incident = await manager.resolve_incident(incident_id, request["resolution_notes"])

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident.to_dict()


@router.post("/{incident_id}/reopen")
async def reopen_incident(incident_id: str) -> dict[str, Any]:
    """Reopen a resolved/closed incident.

    Args:
        incident_id: ID of incident to reopen

    Returns:
        Updated incident
    """
    manager = get_manager()

    # Reopen incident
    incident = await manager.reopen_incident(incident_id)

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident.to_dict()


@router.get("/{incident_id}/post-mortem")
async def get_post_mortem(incident_id: str) -> dict[str, Any]:
    """Get post-mortem for an incident.

    Args:
        incident_id: ID of incident

    Returns:
        Post-mortem report
    """
    manager = get_manager()

    post_mortem = await manager.get_post_mortem(incident_id)

    if not post_mortem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post-mortem for incident {incident_id} not found",
        )

    return post_mortem.to_dict()


@router.get("/metrics/overview")
async def get_incident_metrics() -> dict[str, Any]:
    """Get incident metrics overview.

    Returns:
        Incident metrics including:
        - total_incidents
        - by_severity breakdown
        - by_status breakdown
        - creation_rate (per hour)
        - avg_resolution_time (seconds)
        - escalation_rate (percentage)
    """
    manager = get_manager()
    metrics = await manager.get_metrics()

    return metrics.to_dict()


@router.post("/{incident_id}/remediation/{action_id}/approve")
async def approve_remediation(
    incident_id: str, action_id: str, request: dict[str, Any]
) -> dict[str, Any]:
    """Approve and execute a pending remediation action.

    Args:
        incident_id: ID of incident
        action_id: ID of remediation action to approve
        request: Approval with:
            - approved_by: Who is approving the action

    Returns:
        Updated remediation action
    """
    manager = get_manager()

    # Validate request
    if "approved_by" not in request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: approved_by",
        )

    # Approve remediation
    action = await manager.approve_remediation(
        incident_id, action_id, request["approved_by"]
    )

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending remediation action {action_id} not found for incident {incident_id}",
        )

    return action.to_dict()
