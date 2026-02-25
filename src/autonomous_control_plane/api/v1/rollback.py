"""FastAPI routes for rollback operations.

For ST-NS-042: Rollback Coordinator with Pre-flight Validation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from src.autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.rollback import (
    RollbackHistoryItem,
    RollbackHistoryResponse,
    RollbackMetricsResponse,
    RollbackRequest,
    RollbackResponse,
    RollbackScheduleRequest,
    RollbackStatus,
    RollbackValidationResponse,
    ValidationCheckItem,
)

router = APIRouter(prefix="/rollback", tags=["rollback"])

# Global coordinator instance (would be injected in production)
_coordinator: RollbackCoordinator | None = None


def get_coordinator() -> RollbackCoordinator:
    """Get the rollback coordinator instance.

    Returns:
        RollbackCoordinator

    Raises:
        HTTPException: If coordinator not initialized
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rollback coordinator not initialized",
        )
    return _coordinator


def set_coordinator(coordinator: RollbackCoordinator) -> None:
    """Set the rollback coordinator instance.

    Args:
        coordinator: RollbackCoordinator instance
    """
    global _coordinator
    _coordinator = coordinator


def _validation_result_to_response(
    result: Any, target_state: str
) -> RollbackValidationResponse:
    """Convert ValidationResult to RollbackValidationResponse.

    Args:
        result: ValidationResult from coordinator
        target_state: Target state being validated

    Returns:
        RollbackValidationResponse
    """
    checks = []
    if hasattr(result, "checks"):
        for check in result.checks:
            checks.append(
                ValidationCheckItem(
                    check_id=getattr(check, "check_id", ""),
                    name=getattr(check, "name", ""),
                    description=getattr(check, "description", ""),
                    status=getattr(check, "status", "").value
                    if hasattr(getattr(check, "status", ""), "value")
                    else str(getattr(check, "status", "")),
                    message=getattr(check, "message", ""),
                    details=getattr(check, "details", {}),
                    executed_at=getattr(check, "executed_at", None).isoformat()
                    if getattr(check, "executed_at", None)
                    else None,
                    duration_seconds=getattr(check, "duration_seconds", 0.0),
                )
            )

    can_rollback = getattr(result, "valid", False)
    errors = getattr(result, "errors", [])

    if can_rollback:
        reason = f"Rollback to {target_state} is possible"
    else:
        reason = f"Rollback to {target_state} is not possible: {', '.join(errors) if errors else 'validation failed'}"

    return RollbackValidationResponse(
        can_rollback=can_rollback,
        reason=reason,
        validation_checks=checks,
        errors=errors,
        warnings=getattr(result, "warnings", []),
        executed_at=getattr(result, "executed_at", None).isoformat()
        if getattr(result, "executed_at", None)
        else None,
        duration_seconds=getattr(result, "duration_seconds", 0.0),
    )


def _operation_to_response(operation: Any) -> RollbackResponse:
    """Convert RollbackOperation to RollbackResponse.

    Args:
        operation: RollbackOperation from coordinator

    Returns:
        RollbackResponse
    """
    from src.autonomous_control_plane.models.rollback import RollbackStepItem

    steps = []
    if hasattr(operation, "steps"):
        for step in operation.steps:
            steps.append(
                RollbackStepItem(
                    step_id=getattr(step, "step_id", ""),
                    name=getattr(step, "name", ""),
                    description=getattr(step, "description", ""),
                    action=getattr(step, "action", ""),
                    status=getattr(step, "status", "").value
                    if hasattr(getattr(step, "status", ""), "value")
                    else str(getattr(step, "status", "")),
                    order=getattr(step, "order", 0),
                    started_at=getattr(step, "started_at", None).isoformat()
                    if getattr(step, "started_at", None)
                    else None,
                    completed_at=getattr(step, "completed_at", None).isoformat()
                    if getattr(step, "completed_at", None)
                    else None,
                    error_message=getattr(step, "error_message", None),
                    execution_result=getattr(step, "execution_result", {}),
                    timeout_seconds=getattr(step, "timeout_seconds", 0.0),
                    duration_seconds=getattr(step, "duration_seconds", 0.0),
                )
            )

    validation_result = None
    if hasattr(operation, "validation_result") and operation.validation_result:
        validation_result = _validation_result_to_response(
            operation.validation_result, getattr(operation, "target_state", "")
        )

    post_rollback_health = None
    if hasattr(operation, "post_rollback_health") and operation.post_rollback_health:
        health = operation.post_rollback_health
        post_rollback_health = getattr(health, "to_dict", lambda: {})()

    audit_log = []
    if hasattr(operation, "audit_log"):
        audit_log = [
            getattr(entry, "to_dict", lambda: entry)() for entry in operation.audit_log
        ]

    return RollbackResponse(
        rollback_id=getattr(operation, "operation_id", ""),
        target_state=getattr(operation, "target_state", ""),
        status=getattr(operation, "status", "").value
        if hasattr(getattr(operation, "status", ""), "value")
        else str(getattr(operation, "status", "")),
        steps=steps,
        validation_result=validation_result,
        post_rollback_health=post_rollback_health,
        created_at=getattr(operation, "created_at", None).isoformat()
        if getattr(operation, "created_at", None)
        else None,
        started_at=getattr(operation, "started_at", None).isoformat()
        if getattr(operation, "started_at", None)
        else None,
        completed_at=getattr(operation, "completed_at", None).isoformat()
        if getattr(operation, "completed_at", None)
        else None,
        duration_seconds=getattr(operation, "duration_seconds", 0.0),
        initiated_by=getattr(operation, "initiated_by", "system"),
        force=getattr(operation, "force", False),
        error_message=getattr(operation, "error_message", None),
        audit_log=audit_log,
    )


def _operation_to_history_item(operation: Any) -> RollbackHistoryItem:
    """Convert RollbackOperation to RollbackHistoryItem.

    Args:
        operation: RollbackOperation from coordinator

    Returns:
        RollbackHistoryItem
    """
    return RollbackHistoryItem(
        rollback_id=getattr(operation, "operation_id", ""),
        target_state=getattr(operation, "target_state", ""),
        status=getattr(operation, "status", "").value
        if hasattr(getattr(operation, "status", ""), "value")
        else str(getattr(operation, "status", "")),
        created_at=getattr(operation, "created_at", None).isoformat()
        if getattr(operation, "created_at", None)
        else None,
        completed_at=getattr(operation, "completed_at", None).isoformat()
        if getattr(operation, "completed_at", None)
        else None,
        duration_seconds=getattr(operation, "duration_seconds", 0.0),
        initiated_by=getattr(operation, "initiated_by", "system"),
        force=getattr(operation, "force", False),
        error_message=getattr(operation, "error_message", None),
    )


@router.post(
    "/validate",
    response_model=RollbackValidationResponse,
    summary="Validate rollback possibility",
    description="Run pre-flight validation to check if rollback to the target state is possible. Returns detailed validation results with can_rollback boolean.",
)
async def validate_rollback(
    request: RollbackRequest,
) -> RollbackValidationResponse:
    """Run pre-flight validation for rollback.

    Args:
        request: RollbackRequest with target_state and options

    Returns:
        RollbackValidationResponse with can_rollback boolean and detailed checks
    """
    coordinator = get_coordinator()

    # First check if rollback is possible (quick check)
    can_roll, reason = coordinator.can_rollback(request.target_state)

    # Run full validation
    result = await coordinator.validate_rollback(request.target_state, request.force)

    # Convert to response
    response = _validation_result_to_response(result, request.target_state)

    # Override with quick check result if it failed
    if not can_roll:
        response.can_rollback = False
        response.reason = reason

    return response


@router.post(
    "/execute",
    response_model=RollbackResponse,
    summary="Execute rollback",
    description="Execute a rollback to the target state with pre-flight validation. Returns detailed operation status and results.",
)
async def execute_rollback(
    request: RollbackRequest,
) -> RollbackResponse:
    """Execute rollback with pre-flight validation.

    Args:
        request: RollbackRequest with target_state and options

    Returns:
        RollbackResponse with operation details
    """
    coordinator = get_coordinator()

    # Check if rollback is possible first
    can_roll, reason = coordinator.can_rollback(request.target_state)
    if not can_roll:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    operation = await coordinator.execute_rollback(
        target_state=request.target_state,
        force=request.force,
        initiated_by=request.initiated_by,
        metadata=request.metadata,
    )

    return _operation_to_response(operation)


@router.post(
    "/emergency",
    response_model=RollbackResponse,
    summary="Execute emergency rollback",
    description="Execute an emergency rollback that bypasses pre-flight validation. Use with caution.",
)
async def emergency_rollback(
    request: RollbackRequest,
) -> RollbackResponse:
    """Execute emergency rollback (bypasses validation).

    Args:
        request: RollbackRequest with target_state and options

    Returns:
        RollbackResponse with operation details
    """
    coordinator = get_coordinator()
    operation = await coordinator.emergency_rollback(
        target_state=request.target_state,
        initiated_by=request.initiated_by,
        metadata=request.metadata,
    )
    return _operation_to_response(operation)


@router.get(
    "/{operation_id}",
    response_model=RollbackResponse,
    summary="Get rollback status",
    description="Get the status and details of a specific rollback operation by ID.",
)
async def get_rollback_status(operation_id: str) -> RollbackResponse:
    """Get rollback operation status.

    Args:
        operation_id: Operation ID

    Returns:
        RollbackResponse with operation details

    Raises:
        HTTPException: If operation not found
    """
    coordinator = get_coordinator()
    operation = await coordinator.get_operation(operation_id)

    if not operation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rollback operation {operation_id} not found",
        )

    return _operation_to_response(operation)


@router.get(
    "/history",
    response_model=RollbackHistoryResponse,
    summary="Get rollback history",
    description="Get a paginated list of rollback operations with optional filtering by target state and status.",
)
async def get_rollback_history(
    target_state: str | None = None,
    status: RollbackStatus | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> RollbackHistoryResponse:
    """Get rollback history.

    Args:
        target_state: Filter by target state
        status: Filter by status
        limit: Maximum results
        offset: Pagination offset

    Returns:
        RollbackHistoryResponse with list of operations
    """
    coordinator = get_coordinator()

    if target_state:
        operations = await coordinator.get_rollback_history(target_state, limit)
    else:
        operations = await coordinator.list_operations(status, limit, offset)

    history_items = [_operation_to_history_item(op) for op in operations]

    return RollbackHistoryResponse(
        operations=history_items,
        total=len(history_items),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/schedule",
    response_model=RollbackResponse,
    summary="Schedule a rollback",
    description="Schedule a rollback operation for future execution.",
)
async def schedule_rollback(
    request: RollbackScheduleRequest,
) -> RollbackResponse:
    """Schedule a rollback for future execution.

    Args:
        request: RollbackScheduleRequest with target_state and scheduled time

    Returns:
        RollbackResponse with scheduled operation details
    """
    from datetime import datetime

    coordinator = get_coordinator()

    # Parse scheduled_at timestamp
    try:
        scheduled_at = datetime.fromisoformat(request.scheduled_at)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scheduled_at timestamp: {e}",
        )

    operation = await coordinator.schedule_rollback(
        target_state=request.target_state,
        scheduled_at=scheduled_at,
        force=request.force,
        initiated_by=request.initiated_by,
        metadata=request.metadata,
    )

    return _operation_to_response(operation)


@router.get(
    "/metrics",
    response_model=RollbackMetricsResponse,
    summary="Get rollback metrics",
    description="Get aggregated metrics for rollback operations including success rates and duration statistics.",
)
async def get_rollback_metrics() -> RollbackMetricsResponse:
    """Get rollback metrics.

    Returns:
        RollbackMetricsResponse with aggregated metrics
    """
    coordinator = get_coordinator()
    metrics = await coordinator.get_metrics()

    return RollbackMetricsResponse(
        total_operations=getattr(metrics, "total_operations", 0),
        successful=getattr(metrics, "successful", 0),
        failed=getattr(metrics, "failed", 0),
        avg_duration_seconds=getattr(metrics, "avg_duration_seconds", 0.0),
        p95_duration_seconds=getattr(metrics, "p95_duration_seconds", 0.0),
        by_target_state=getattr(metrics, "by_target_state", {}),
    )
