"""API routes for healing operations.

FastAPI routes for healing management:
- GET /api/v1/healing/status - Engine status
- GET /api/v1/healing/actions - List healing actions
- POST /api/v1/healing/actions/{id}/approve - Approve pending action
- POST /api/v1/healing/disable - Disable healing
- GET /api/v1/healing/history - Healing history

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException, status

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

    class HTTPException(Exception):
        pass


from src.autonomous_control_plane.components.self_healing_engine import (
    SelfHealingEngine,
)

# Global engine instance (initialized by dependency injection in production)
_engine: SelfHealingEngine | None = None

router = APIRouter(prefix="/api/v1/healing", tags=["healing"])


def set_engine(engine: SelfHealingEngine) -> None:
    """Set the global engine instance."""
    global _engine
    _engine = engine


def get_engine() -> SelfHealingEngine:
    """Get the global engine instance."""
    if _engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Self-healing engine not initialized",
        )
    return _engine


@router.get("/status")
async def get_healing_status() -> dict[str, Any]:
    """Get self-healing engine status.

    Returns:
        Engine status including enabled state, stats, and pending approvals
    """
    engine = get_engine()
    return engine.get_status()


@router.get("/actions")
async def get_healing_actions() -> dict[str, Any]:
    """Get available healing actions and pending approvals.

    Returns:
        List of healing actions and pending approvals
    """
    engine = get_engine()
    return {
        "available_actions": [
            {
                "type": "redis_restart",
                "priority": "P2",
                "description": "Restart Redis connection pool",
            },
            {
                "type": "api_retry",
                "priority": "P2",
                "description": "Retry failed API calls",
            },
            {
                "type": "circuit_breaker_reset",
                "priority": "P2",
                "description": "Reset circuit breaker to CLOSED",
            },
        ],
        "pending_approvals": [
            attempt.to_dict() for attempt in engine.get_pending_approvals()
        ],
    }


@router.post("/actions/{attempt_id}/approve")
async def approve_healing_action(attempt_id: str) -> dict[str, Any]:
    """Approve a pending healing action.

    Args:
        attempt_id: ID of the healing attempt to approve

    Returns:
        Updated healing attempt
    """
    engine = get_engine()
    # In production, get user from auth context
    approved_by = "admin"

    attempt = engine.approve_healing(attempt_id, approved_by)
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending healing action {attempt_id} not found",
        )

    return attempt.to_dict()


@router.post("/actions/{attempt_id}/reject")
async def reject_healing_action(attempt_id: str) -> dict[str, Any]:
    """Reject a pending healing action.

    Args:
        attempt_id: ID of the healing attempt to reject

    Returns:
        Updated healing attempt
    """
    engine = get_engine()
    # In production, get user from auth context
    rejected_by = "admin"

    attempt = engine.reject_healing(attempt_id, rejected_by)
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending healing action {attempt_id} not found",
        )

    return attempt.to_dict()


@router.post("/disable")
async def disable_healing() -> dict[str, Any]:
    """Disable self-healing engine.

    Returns:
        Updated status
    """
    engine = get_engine()
    engine.disable()
    return {"message": "Self-healing engine disabled", "status": engine.get_status()}


@router.post("/enable")
async def enable_healing() -> dict[str, Any]:
    """Enable self-healing engine.

    Returns:
        Updated status
    """
    engine = get_engine()
    engine.enable()
    return {"message": "Self-healing engine enabled", "status": engine.get_status()}


@router.get("/history")
async def get_healing_history(
    service: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """Get healing history.

    Args:
        service: Filter by service name (optional)
        limit: Maximum number of results (default: 100)

    Returns:
        List of healing attempts
    """
    engine = get_engine()
    history = engine.get_healing_history(service=service, limit=limit)

    return {
        "history": [attempt.to_dict() for attempt in history],
        "count": len(history),
        "service_filter": service,
    }


@router.get("/services/{service}")
async def get_service_healing_stats(service: str) -> dict[str, Any]:
    """Get healing stats for a specific service.

    Args:
        service: Service name

    Returns:
        Service healing statistics
    """
    engine = get_engine()
    return engine.get_service_stats(service)
