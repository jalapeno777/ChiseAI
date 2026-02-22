"""FastAPI routes for circuit breaker management.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)
from autonomous_control_plane.models.circuit_breaker import CircuitBreakerConfig

router = APIRouter(prefix="/circuit-breakers", tags=["circuit-breakers"])

# Get singleton registry instance
_registry = CircuitBreakerRegistry()


@router.get("", response_model=dict[str, Any])
async def get_all_circuit_breakers() -> dict[str, Any]:
    """Get all circuit breaker states.

    Returns:
        Dictionary of all circuit breaker states
    """
    states = _registry.get_all_states_dict()
    return {
        "count": len(states),
        "circuit_breakers": states,
    }


@router.get("/{name}", response_model=dict[str, Any])
async def get_circuit_breaker(name: str) -> dict[str, Any]:
    """Get a specific circuit breaker state.

    Args:
        name: Circuit breaker name

    Returns:
        Circuit breaker state

    Raises:
        HTTPException: If circuit breaker not found
    """
    state = _registry.get(name)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return state.to_dict()


@router.post(
    "/{name}", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED
)
async def create_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> dict[str, Any]:
    """Register a new circuit breaker.

    Args:
        name: Circuit breaker name
        config: Optional configuration

    Returns:
        Created circuit breaker state
    """
    state = _registry.register(name, config or CircuitBreakerConfig())
    return state.to_dict()


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_circuit_breaker(name: str) -> None:
    """Unregister a circuit breaker.

    Args:
        name: Circuit breaker name

    Raises:
        HTTPException: If circuit breaker not found
    """
    state = _registry.unregister(name)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )


@router.post("/{name}/force-open", response_model=dict[str, Any])
async def force_open_circuit_breaker(
    name: str,
    reason: str = "manual",
) -> dict[str, Any]:
    """Force a circuit breaker to open state.

    Args:
        name: Circuit breaker name
        reason: Reason for forcing open

    Returns:
        Updated circuit breaker state

    Raises:
        HTTPException: If circuit breaker not found
    """
    success = _registry.force_open(name, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = _registry.get(name)
    return state.to_dict() if state else {}


@router.post("/{name}/force-close", response_model=dict[str, Any])
async def force_close_circuit_breaker(
    name: str,
    reason: str = "manual",
) -> dict[str, Any]:
    """Force a circuit breaker to closed state.

    Args:
        name: Circuit breaker name
        reason: Reason for forcing close

    Returns:
        Updated circuit breaker state

    Raises:
        HTTPException: If circuit breaker not found
    """
    success = _registry.force_close(name, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = _registry.get(name)
    return state.to_dict() if state else {}


@router.post("/{name}/reset", response_model=dict[str, Any])
async def reset_circuit_breaker(name: str) -> dict[str, Any]:
    """Reset a circuit breaker to initial state.

    Args:
        name: Circuit breaker name

    Returns:
        Reset circuit breaker state

    Raises:
        HTTPException: If circuit breaker not found
    """
    success = _registry.reset(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = _registry.get(name)
    return state.to_dict() if state else {}


@router.post("/bulk/reset-all", response_model=dict[str, Any])
async def reset_all_circuit_breakers() -> dict[str, Any]:
    """Reset all circuit breakers.

    Returns:
        Status message
    """
    _registry.reset_all()
    return {"message": "All circuit breakers reset"}


@router.post("/bulk/force-open-all", response_model=dict[str, Any])
async def force_open_all_circuit_breakers(
    reason: str = "manual",
) -> dict[str, Any]:
    """Force open all circuit breakers.

    Args:
        reason: Reason for forcing open

    Returns:
        Status message
    """
    _registry.force_open_all(reason)
    return {"message": f"All circuit breakers forced open ({reason})"}


@router.post("/bulk/force-close-all", response_model=dict[str, Any])
async def force_close_all_circuit_breakers(
    reason: str = "manual",
) -> dict[str, Any]:
    """Force close all circuit breakers.

    Args:
        reason: Reason for forcing close

    Returns:
        Status message
    """
    _registry.force_close_all(reason)
    return {"message": f"All circuit breakers forced closed ({reason})"}


@router.get("/health/all", response_model=dict[str, Any])
async def get_all_health() -> dict[str, Any]:
    """Get health status for all circuit breakers.

    Returns:
        Dictionary of health statuses
    """
    health = _registry.get_all_health()
    return {
        "count": len(health),
        "overall_healthy": all(h.is_healthy for h in health.values()),
        "circuit_breakers": {name: h.to_dict() for name, h in health.items()},
    }


@router.get("/health/{name}", response_model=dict[str, Any])
async def get_circuit_breaker_health(name: str) -> dict[str, Any]:
    """Get health status for a specific circuit breaker.

    Args:
        name: Circuit breaker name

    Returns:
        Health status

    Raises:
        HTTPException: If circuit breaker not found
    """
    health = _registry.get_health(name)
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return health.to_dict()


@router.post("/telemetry/flush", response_model=dict[str, Any])
async def flush_telemetry() -> dict[str, Any]:
    """Manually flush telemetry for all circuit breakers.

    Returns:
        Status message
    """
    _registry.flush_telemetry()
    return {"message": "Telemetry flushed"}
