"""Retry management API routes.

Provides endpoints for monitoring and managing retry operations:
- GET /api/v1/retry/budgets - List all service budgets
- GET /api/v1/retry/budgets/{service} - Get specific service budget
- POST /api/v1/retry/budgets/{service}/reset - Reset budget
- GET /api/v1/retry/endpoint-budgets - List all endpoint budgets
- GET /api/v1/retry/endpoint-budgets/{service}/{endpoint} - Get endpoint budget
- POST /api/v1/retry/endpoint-patterns - Register endpoint pattern
- GET /api/v1/retry/pools - List all budget pools
- GET /api/v1/retry/pools/{pool_id} - Get specific pool
- POST /api/v1/retry/pools/{pool_id}/unlock-emergency - Unlock emergency reserve
- GET /api/v1/retry/dead-letter - List DLQ items
- POST /api/v1/retry/dead-letter/{id}/retry - Retry DLQ item
- DELETE /api/v1/retry/dead-letter/{id} - Delete DLQ item
- GET /api/v1/retry/queued - List queued operations
- DELETE /api/v1/retry/queued - Clear queued operations
- GET /api/v1/retry/metrics - Get retry metrics
- GET /api/v1/retry/analytics - Get budget analytics
- GET /api/v1/retry/circuit-breakers - Get circuit breaker states

For ST-NS-039: Retry Coordinator with Budget Management
For ST-SAFETY-002: Retry Budget Implementation
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from autonomous_control_plane.components.retry_budget_manager import RetryBudgetManager
from autonomous_control_plane.components.retry_coordinator import RetryCoordinator
from autonomous_control_plane.models.retry_policy import (
    BudgetExhaustionStrategy,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/retry", tags=["retry"])

# Global coordinator instance (initialized by application)
_coordinator: RetryCoordinator | None = None

# Global budget manager instance (initialized by application)
_budget_manager: RetryBudgetManager | None = None


# Pydantic models for request/response
class EndpointPatternRequest(BaseModel):
    """Request to register an endpoint pattern."""

    service_name: str = Field(..., description="Service identifier")
    endpoint_pattern: str = Field(
        ..., description="Endpoint pattern (e.g., api/v1/orders/*)"
    )
    limit: int | None = Field(None, description="Budget limit for this endpoint")
    exhaustion_strategy: str = Field("FAIL_FAST", description="Exhaustion strategy")


class BudgetPoolRequest(BaseModel):
    """Request to create a budget pool."""

    pool_id: str = Field(..., description="Unique pool identifier")
    name: str = Field(..., description="Human-readable pool name")
    services: list[str] = Field(..., description="List of services in the pool")
    total_budget: int = Field(1000, description="Total budget for the pool")
    priority_allocation: dict[str, int] = Field(
        default_factory=dict, description="Priority-based allocation"
    )
    emergency_reserve: int = Field(100, description="Emergency reserve amount")


class BurstConfigRequest(BaseModel):
    """Request for burst configuration."""

    burst_percentage: float = Field(
        150.0, description="Percentage of base budget for burst"
    )
    cooldown_seconds: int = Field(
        60, description="Seconds before burst can be used again"
    )
    max_bursts_per_window: int = Field(
        3, description="Maximum bursts allowed per window"
    )


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


def set_budget_manager(budget_manager: RetryBudgetManager) -> None:
    """Set the global retry budget manager instance.

    Args:
        budget_manager: RetryBudgetManager instance
    """
    global _budget_manager
    _budget_manager = budget_manager
    logger.info("Retry budget manager registered with API")


def get_budget_manager() -> RetryBudgetManager | None:
    """Get the global retry budget manager instance.

    Returns:
        RetryBudgetManager instance or None
    """
    return _budget_manager


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
        ) from e


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
        ) from e


@router.post("/budgets/{service}/reset", response_model=dict[str, Any])
async def reset_budget(
    service: str = Path(..., description="Service name"),
    endpoint_pattern: str | None = Query(None, description="Optional endpoint pattern"),
) -> dict[str, Any]:
    """Reset retry budget for a service or endpoint.

    Args:
        service: Service name
        endpoint_pattern: Optional endpoint pattern to reset

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        _coordinator.reset_budget(service, endpoint_pattern)
        message = f"Budget reset for service: {service}"
        if endpoint_pattern:
            message = f"Budget reset for endpoint: {service}:{endpoint_pattern}"
        return {
            "success": True,
            "message": message,
        }
    except Exception as e:
        logger.error(f"Failed to reset budget for {service}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset budget: {str(e)}",
        ) from e


@router.get("/endpoint-budgets", response_model=dict[str, Any])
async def list_endpoint_budgets() -> dict[str, Any]:
    """List all endpoint retry budgets.

    Returns:
        Dictionary with list of all endpoint budget statuses
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        budgets = _coordinator.get_all_endpoint_budgets()
        return {
            "success": True,
            "data": {
                "budgets": budgets,
                "count": len(budgets),
            },
        }
    except Exception as e:
        logger.error(f"Failed to list endpoint budgets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list endpoint budgets: {str(e)}",
        ) from e


@router.get(
    "/endpoint-budgets/{service}/{endpoint:path}", response_model=dict[str, Any]
)
async def get_endpoint_budget(
    service: str = Path(..., description="Service name"),
    endpoint: str = Path(..., description="Endpoint pattern"),
) -> dict[str, Any]:
    """Get retry budget for a specific endpoint.

    Args:
        service: Service name
        endpoint: Endpoint pattern

    Returns:
        Budget status for the endpoint
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        budget = _coordinator.get_endpoint_budget_status(service, endpoint)
        return {
            "success": True,
            "data": budget,
        }
    except Exception as e:
        logger.error(f"Failed to get endpoint budget for {service}:{endpoint}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get endpoint budget: {str(e)}",
        ) from e


@router.post("/endpoint-patterns", response_model=dict[str, Any])
async def register_endpoint_pattern(
    request: EndpointPatternRequest = Body(...),
) -> dict[str, Any]:
    """Register an endpoint pattern for budget tracking.

    Args:
        request: Endpoint pattern registration request

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        strategy = BudgetExhaustionStrategy[request.exhaustion_strategy.upper()]
        _coordinator.register_endpoint_pattern(
            service_name=request.service_name,
            endpoint_pattern=request.endpoint_pattern,
            limit=request.limit,
            exhaustion_strategy=strategy,
        )
        return {
            "success": True,
            "message": f"Registered endpoint pattern '{request.endpoint_pattern}' for service '{request.service_name}'",
            "data": {
                "service_name": request.service_name,
                "endpoint_pattern": request.endpoint_pattern,
                "exhaustion_strategy": strategy.name,
            },
        }
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid exhaustion strategy: {request.exhaustion_strategy}",
        )
    except Exception as e:
        logger.error(f"Failed to register endpoint pattern: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register endpoint pattern: {str(e)}",
        ) from e


@router.get("/pools", response_model=dict[str, Any])
async def list_budget_pools() -> dict[str, Any]:
    """List all budget pools.

    Returns:
        Dictionary with list of all budget pools
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        pools = _coordinator.get_all_pools()
        return {
            "success": True,
            "data": {
                "pools": pools,
                "count": len(pools),
            },
        }
    except Exception as e:
        logger.error(f"Failed to list budget pools: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list budget pools: {str(e)}",
        ) from e


@router.get("/pools/{pool_id}", response_model=dict[str, Any])
async def get_budget_pool(
    pool_id: str = Path(..., description="Pool ID"),
) -> dict[str, Any]:
    """Get a specific budget pool.

    Args:
        pool_id: Pool identifier

    Returns:
        Pool status
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        pool = _coordinator.get_pool_status(pool_id)
        if pool is None:
            raise HTTPException(
                status_code=404,
                detail=f"Pool not found: {pool_id}",
            )
        return {
            "success": True,
            "data": pool,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get budget pool {pool_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get budget pool: {str(e)}",
        ) from e


@router.post("/pools", response_model=dict[str, Any])
async def create_budget_pool(
    request: BudgetPoolRequest = Body(...),
) -> dict[str, Any]:
    """Create a budget pool.

    Args:
        request: Budget pool creation request

    Returns:
        Success confirmation with pool data
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        _coordinator.create_budget_pool(
            pool_id=request.pool_id,
            name=request.name,
            services=request.services,
            total_budget=request.total_budget,
            priority_allocation=request.priority_allocation,
            emergency_reserve=request.emergency_reserve,
        )
        return {
            "success": True,
            "message": f"Created budget pool '{request.name}'",
            "data": {
                "pool_id": request.pool_id,
                "name": request.name,
                "services": request.services,
                "total_budget": request.total_budget,
            },
        }
    except Exception as e:
        logger.error(f"Failed to create budget pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create budget pool: {str(e)}",
        ) from e


@router.post("/pools/{pool_id}/unlock-emergency", response_model=dict[str, Any])
async def unlock_emergency_reserve(
    pool_id: str = Path(..., description="Pool ID"),
) -> dict[str, Any]:
    """Unlock emergency reserve for a budget pool.

    Args:
        pool_id: Pool identifier

    Returns:
        Success confirmation
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        success = _coordinator.unlock_emergency_reserve(pool_id)
        if success:
            return {
                "success": True,
                "message": f"Emergency reserve unlocked for pool: {pool_id}",
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Pool not found: {pool_id}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlock emergency reserve for {pool_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unlock emergency reserve: {str(e)}",
        ) from e


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
        ) from e


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
        ) from e


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
        ) from e


@router.get("/queued", response_model=dict[str, Any])
async def list_queued_operations() -> dict[str, Any]:
    """List queued operations (for QUEUE exhaustion strategy).

    Returns:
        List of queued operations
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        operations = _coordinator.get_queued_operations()
        return {
            "success": True,
            "data": {
                "operations": operations,
                "count": len(operations),
            },
        }
    except Exception as e:
        logger.error(f"Failed to list queued operations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list queued operations: {str(e)}",
        ) from e


@router.delete("/queued", response_model=dict[str, Any])
async def clear_queued_operations() -> dict[str, Any]:
    """Clear all queued operations.

    Returns:
        Success confirmation with count cleared
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        count = _coordinator.clear_queued_operations()
        return {
            "success": True,
            "message": f"Cleared {count} queued operations",
            "data": {"cleared_count": count},
        }
    except Exception as e:
        logger.error(f"Failed to clear queued operations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear queued operations: {str(e)}",
        ) from e


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
        ) from e


@router.get("/analytics", response_model=dict[str, Any])
async def get_analytics() -> dict[str, Any]:
    """Get budget analytics.

    Returns:
        Dictionary with budget analytics
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="Retry coordinator not initialized",
        )

    try:
        analytics = _coordinator.get_analytics()
        # Get efficiency metrics for all tracked budgets
        efficiency_metrics = {}
        for budget_key in analytics._local_metrics:
            efficiency_metrics[budget_key] = analytics.get_efficiency_metrics(
                budget_key
            )

        return {
            "success": True,
            "data": {
                "efficiency_metrics": efficiency_metrics,
                "tracked_budgets": list(analytics._local_metrics.keys()),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analytics: {str(e)}",
        ) from e


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
        ) from e
