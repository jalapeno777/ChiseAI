"""Retry management API routes.

Provides endpoints for monitoring and managing retry operations:
- GET /api/v1/retry/budgets - List all service budgets
- GET /api/v1/retry/budgets/{service} - Get specific service budget
- POST /api/v1/retry/budgets/{service}/reset - Reset budget
- GET /api/v1/retry/dead-letter - List DLQ items
- POST /api/v1/retry/dead-letter/{id}/retry - Retry DLQ item
- DELETE /api/v1/retry/dead-letter/{id} - Delete DLQ item
- GET /api/v1/retry/metrics - Get retry metrics
- GET /api/v1/retry/circuit-breakers - Get circuit breaker states

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query

from src.autonomous_control_plane.components.retry_coordinator import RetryCoordinator

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/retry", tags=["retry"])

# Global coordinator instance (initialized by application)
_coordinator: RetryCoordinator | None = None


def set_retry_coordinator(coordinator: RetryCoordinator) -> None:
    """Set the global retry coordinator instance.

    Args:
        coordinator: RetryCoordinator instance
    """
    global _coordinator
    _coordinator = coordinator
    logger.info("Retry coordinator registered with API")


def get_retry_coordinator() -> RetryCoordinator | None:
    """Get the global retry coordinator instance.

    Returns:
        RetryCoordinator instance or None
    """
    return _coordinator


@router.get("/budgets", response_model=dict[str, Any])
async def list_budgets() -> dict[str, Any]:
    """List all service retry budgets.

    Returns:
        Dictionary with list of all budget statuses
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        budgets = _coordinator.get_all_budgets()
        return {
            "success": True,
            "data": {
                "budgets": budgets,
                "count": len(budgets),
            },
        }
    except Exception as e:
        logger.error(f"Failed to list budgets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list budgets: {str(e)}",
        )


@router.get("/budgets/{service}", response_model=dict[str, Any])
async def get_budget(
    service: str = Path(..., description="Service name"),
) -> dict[str, Any]:
    """Get retry budget for a specific service.

    Args:
        service: Service name

    Returns:
        Budget status for the service
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        budget = _coordinator.get_budget_status(service)
        return {
            "success": True,
            "data": budget,
        }
    except Exception as e:
        logger.error(f"Failed to get budget for {service}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get budget: {str(e)}",
        )


@router.post("/budgets/{service}/reset", response_model=dict[str, Any])
async def reset_budget(
    service: str = Path(..., description="Service name"),
) -> dict[str, Any]:
    """Reset retry budget for a service.

    Args:
        service: Service name

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        _coordinator.reset_budget(service)
        return {
            "success": True,
            "message": f"Budget reset for service: {service}",
        }
    except Exception as e:
        logger.error(f"Failed to reset budget for {service}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset budget: {str(e)}",
        )


@router.get("/dead-letter", response_model=dict[str, Any])
async def list_dead_letter_items(
    service: str | None = Query(None, description="Filter by service"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return"),
) -> dict[str, Any]:
    """List dead letter queue items.

    Args:
        service: Optional service filter
        limit: Maximum items to return

    Returns:
        List of DLQ items
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        items = _coordinator.get_dlq_items(service_name=service, limit=limit)
        return {
            "success": True,
            "data": {
                "items": items,
                "count": len(items),
                "service_filter": service,
            },
        }
    except Exception as e:
        logger.error(f"Failed to list DLQ items: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list DLQ items: {str(e)}",
        )


@router.post("/dead-letter/{item_id}/retry", response_model=dict[str, Any])
async def retry_dead_letter_item(
    item_id: str = Path(..., description="DLQ item ID"),
) -> dict[str, Any]:
    """Mark a DLQ item for retry.

    Args:
        item_id: DLQ item identifier

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        success = _coordinator.retry_dlq_item(item_id)
        if success:
            return {
                "success": True,
                "message": f"Item {item_id} marked for retry",
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"DLQ item not found: {item_id}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry DLQ item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retry DLQ item: {str(e)}",
        )


@router.delete("/dead-letter/{item_id}", response_model=dict[str, Any])
async def delete_dead_letter_item(
    item_id: str = Path(..., description="DLQ item ID"),
) -> dict[str, Any]:
    """Delete a DLQ item.

    Args:
        item_id: DLQ item identifier

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        success = _coordinator.delete_dlq_item(item_id)
        if success:
            return {
                "success": True,
                "message": f"Item {item_id} deleted",
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"DLQ item not found: {item_id}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete DLQ item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete DLQ item: {str(e)}",
        )


@router.get("/metrics", response_model=dict[str, Any])
async def get_metrics() -> dict[str, Any]:
    """Get retry metrics.

    Returns:
        Dictionary with retry metrics
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        metrics = _coordinator.get_metrics()
        return {
            "success": True,
            "data": metrics,
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics: {str(e)}",
        )


@router.get("/circuit-breakers", response_model=dict[str, Any])
async def get_circuit_breaker_states() -> dict[str, Any]:
    """Get all circuit breaker states.

    Returns:
        Dictionary with circuit breaker states
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        states = _coordinator.get_circuit_breaker_states()
        return {
            "success": True,
            "data": {
                "circuit_breakers": states,
                "count": len(states),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get circuit breaker states: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get circuit breaker states: {str(e)}",
        )
