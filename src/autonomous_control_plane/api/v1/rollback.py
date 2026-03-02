"""FastAPI routes for rollback operations.

For ST-NS-042: Rollback Coordinator with Pre-flight Validation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from autonomous_control_plane.models.rollback import (
    RollbackStatus,
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


@router.post("/validate", response_model=dict[str, Any])
async def validate_rollback(
    target_state: str,
    force: bool = False,
) -> dict[str, Any]:
    """Run pre-flight validation for rollback.

    Args:
        target_state: Target state to rollback to
        force: If True, skip validation

    Returns:
        Validation result
    """
    coordinator = get_coordinator()
    result = await coordinator.validate_rollback(target_state, force)
    return result.to_dict()


@router.post("/execute", response_model=dict[str, Any])
async def execute_rollback(
    target_state: str,
    force: bool = False,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute rollback with pre-flight validation.

    Args:
        target_state: Target state to rollback to
        force: If True, bypass validation
        initiated_by: Who initiated the rollback

    Returns:
        Rollback operation result
    """
    coordinator = get_coordinator()
    operation = await coordinator.execute_rollback(
        target_state=target_state,
        force=force,
        initiated_by=initiated_by,
    )
    return operation.to_dict()


@router.post("/emergency", response_model=dict[str, Any])
async def emergency_rollback(
    target_state: str,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute emergency rollback (bypasses validation).

    Args:
        target_state: Target state to rollback to
        initiated_by: Who initiated the rollback

    Returns:
        Rollback operation result
    """
    coordinator = get_coordinator()
    operation = await coordinator.emergency_rollback(
        target_state=target_state,
        initiated_by=initiated_by,
    )
    return operation.to_dict()


@router.get("/{operation_id}", response_model=dict[str, Any])
async def get_rollback_status(operation_id: str) -> dict[str, Any]:
    """Get rollback operation status.

    Args:
        operation_id: Operation ID

    Returns:
        Rollback operation

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

    return operation.to_dict()


@router.get("/history", response_model=list[dict[str, Any]])
async def get_rollback_history(
    target_state: str | None = None,
    status: RollbackStatus | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Get rollback history.

    Args:
        target_state: Filter by target state
        status: Filter by status
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of rollback operations
    """
    coordinator = get_coordinator()

    if target_state:
        operations = await coordinator.get_history(target_state, limit)
    else:
        operations = await coordinator.list_operations(status, limit, offset)

    return [op.to_dict() for op in operations]


@router.get("/metrics", response_model=dict[str, Any])
async def get_rollback_metrics() -> dict[str, Any]:
    """Get rollback metrics.

    Returns:
        Rollback metrics
    """
    coordinator = get_coordinator()
    metrics = await coordinator.get_metrics()
    return metrics.to_dict()
