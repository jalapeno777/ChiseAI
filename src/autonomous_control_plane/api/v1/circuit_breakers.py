"""FastAPI routes for circuit breaker management.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
ST-SAFETY-001: Circuit Breaker Enhancement - API Endpoints
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, status

from autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)
from autonomous_control_plane.models.circuit_breaker import (
    CircuitBreakerConfig,
)

router = APIRouter(prefix="/circuit-breakers", tags=["circuit-breakers"])

# Global registry instance (initialized by application)
_registry: CircuitBreakerRegistry | None = None


def set_registry(registry: CircuitBreakerRegistry) -> None:
    """Set the global circuit breaker registry instance.

    Args:
        registry: CircuitBreakerRegistry instance
    """
    global _registry
    _registry = registry


def get_registry() -> CircuitBreakerRegistry | None:
    """Get the global circuit breaker registry instance.

    Returns:
        CircuitBreakerRegistry instance or None
    """
    return _registry


def _get_registry_or_raise() -> CircuitBreakerRegistry:
    """Get the registry or raise HTTPException if not initialized.

    Returns:
        CircuitBreakerRegistry instance

    Raises:
        HTTPException: If registry not initialized
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Circuit breaker registry not initialized",
        )
    return _registry


@router.get("", response_model=dict[str, Any])
async def get_all_circuit_breakers() -> dict[str, Any]:
    """Get all circuit breaker states.

    Returns:
        Dictionary of all circuit breaker states
    """
    registry = _get_registry_or_raise()
    states = registry.get_all_states_dict()
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
    registry = _get_registry_or_raise()
    state = registry.get(name)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return cast(dict[str, Any], state.to_dict())


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
    registry = _get_registry_or_raise()
    state = registry.register(name, config or CircuitBreakerConfig())
    return cast(dict[str, Any], state.to_dict())


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_circuit_breaker(name: str) -> None:
    """Unregister a circuit breaker.

    Args:
        name: Circuit breaker name

    Raises:
        HTTPException: If circuit breaker not found
    """
    registry = _get_registry_or_raise()
    state = registry.unregister(name)
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
    registry = _get_registry_or_raise()
    success = registry.force_open(name, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = registry.get(name)
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
    registry = _get_registry_or_raise()
    success = registry.force_close(name, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = registry.get(name)
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
    registry = _get_registry_or_raise()
    success = registry.reset(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    state = registry.get(name)
    return state.to_dict() if state else {}


@router.post("/bulk/reset-all", response_model=dict[str, Any])
async def reset_all_circuit_breakers() -> dict[str, Any]:
    """Reset all circuit breakers.

    Returns:
        Status message
    """
    registry = _get_registry_or_raise()
    registry.reset_all()
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
    registry = _get_registry_or_raise()
    registry.force_open_all(reason)
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
    registry = _get_registry_or_raise()
    registry.force_close_all(reason)
    return {"message": f"All circuit breakers forced closed ({reason})"}


@router.get("/health/all", response_model=dict[str, Any])
async def get_all_health() -> dict[str, Any]:
    """Get health status for all circuit breakers.

    Returns:
        Dictionary of health statuses
    """
    registry = _get_registry_or_raise()
    health = registry.get_all_health()
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
    registry = _get_registry_or_raise()
    health = registry.get_health(name)
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return cast(dict[str, Any], health.to_dict())


@router.post("/telemetry/flush", response_model=dict[str, Any])
async def flush_telemetry() -> dict[str, Any]:
    """Manually flush telemetry for all circuit breakers.

    Returns:
        Status message
    """
    registry = _get_registry_or_raise()
    registry.flush_telemetry()
    return {"message": "Telemetry flushed"}


# ==================== Adaptive Threshold Endpoints ====================


@router.get("/{name}/adaptive", response_model=dict[str, Any])
async def get_adaptive_metrics(name: str) -> dict[str, Any]:
    """Get adaptive threshold metrics for a circuit breaker.

    Args:
        name: Circuit breaker name

    Returns:
        Adaptive threshold metrics

    Raises:
        HTTPException: If circuit breaker not found
    """
    registry = _get_registry_or_raise()
    metrics = registry.get_adaptive_metrics(name)
    if metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return metrics


# ==================== Canary Recovery Endpoints ====================


@router.get("/{name}/canary", response_model=dict[str, Any])
async def get_canary_state(name: str) -> dict[str, Any]:
    """Get canary recovery state for a circuit breaker.

    Args:
        name: Circuit breaker name

    Returns:
        Canary recovery state

    Raises:
        HTTPException: If circuit breaker not found
    """
    registry = _get_registry_or_raise()
    canary_state = registry.get_canary_state(name)
    if canary_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )

    traffic_percent = registry.get_canary_traffic_percent(name)
    return {
        **canary_state,
        "traffic_percent": traffic_percent,
    }


# ==================== Predictive Alert Endpoints ====================


@router.get("/{name}/predictive", response_model=dict[str, Any])
async def get_predictive_state(name: str) -> dict[str, Any]:
    """Get predictive alert state for a circuit breaker.

    Args:
        name: Circuit breaker name

    Returns:
        Predictive alert state

    Raises:
        HTTPException: If circuit breaker not found
    """
    registry = _get_registry_or_raise()
    predictive_state = registry.get_predictive_state(name)
    if predictive_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found",
        )
    return predictive_state


@router.get("/alerts/predictive", response_model=dict[str, Any])
async def check_predictive_alerts() -> dict[str, Any]:
    """Check predictive alerts for all circuit breakers.

    Returns:
        List of triggered alerts
    """
    registry = _get_registry_or_raise()
    alerts = registry.check_all_predictive_alerts()
    return {
        "count": len(alerts),
        "alerts": alerts,
    }


# ==================== Circuit Breaker Group Endpoints ====================


@router.post(
    "/groups", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED
)
async def create_group(
    name: str,
    member_names: list[str] | None = None,
    cascade_open: bool = True,
    cascade_close: bool = False,
) -> dict[str, Any]:
    """Create a new circuit breaker group.

    Args:
        name: Group name
        member_names: List of circuit breaker names to add
        cascade_open: Whether to cascade open operations
        cascade_close: Whether to cascade close operations

    Returns:
        Created group
    """
    registry = _get_registry_or_raise()
    group = registry.create_group(
        name=name,
        member_names=member_names,
        cascade_open=cascade_open,
        cascade_close=cascade_close,
    )
    return cast(dict[str, Any], group.to_dict())


@router.get("/groups", response_model=dict[str, Any])
async def list_groups() -> dict[str, Any]:
    """List all circuit breaker groups.

    Returns:
        List of group names
    """
    registry = _get_registry_or_raise()
    groups = registry.list_groups()
    return {
        "count": len(groups),
        "groups": groups,
    }


@router.get("/groups/{name}", response_model=dict[str, Any])
async def get_group(name: str) -> dict[str, Any]:
    """Get a circuit breaker group.

    Args:
        name: Group name

    Returns:
        Group details

    Raises:
        HTTPException: If group not found
    """
    registry = _get_registry_or_raise()
    group = registry.get_group(name)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{name}' not found",
        )
    return cast(dict[str, Any], group.to_dict())


@router.delete("/groups/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(name: str) -> None:
    """Delete a circuit breaker group.

    Args:
        name: Group name

    Raises:
        HTTPException: If group not found
    """
    registry = _get_registry_or_raise()
    success = registry.delete_group(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{name}' not found",
        )


@router.post(
    "/groups/{name}/members/{circuit_breaker_name}",
    response_model=dict[str, Any],
)
async def add_to_group(name: str, circuit_breaker_name: str) -> dict[str, Any]:
    """Add a circuit breaker to a group.

    Args:
        name: Group name
        circuit_breaker_name: Circuit breaker name

    Returns:
        Updated group

    Raises:
        HTTPException: If group not found
    """
    registry = _get_registry_or_raise()
    success = registry.add_to_group(name, circuit_breaker_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{name}' not found",
        )

    group = registry.get_group(name)
    return cast(dict[str, Any], group.to_dict()) if group else {}


@router.delete(
    "/groups/{name}/members/{circuit_breaker_name}",
    response_model=dict[str, Any],
)
async def remove_from_group(name: str, circuit_breaker_name: str) -> dict[str, Any]:
    """Remove a circuit breaker from a group.

    Args:
        name: Group name
        circuit_breaker_name: Circuit breaker name

    Returns:
        Updated group

    Raises:
        HTTPException: If group not found
    """
    registry = _get_registry_or_raise()
    success = registry.remove_from_group(name, circuit_breaker_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{name}' or member '{circuit_breaker_name}' not found",
        )

    group = registry.get_group(name)
    return cast(dict[str, Any], group.to_dict()) if group else {}


@router.get("/groups/{name}/metrics", response_model=dict[str, Any])
async def get_group_metrics(name: str) -> dict[str, Any]:
    """Get aggregated metrics for a circuit breaker group.

    Args:
        name: Group name

    Returns:
        Group metrics

    Raises:
        HTTPException: If group not found
    """
    registry = _get_registry_or_raise()
    metrics = registry.get_group_metrics(name)
    if metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{name}' not found",
        )
    return cast(dict[str, Any], metrics.to_dict())
