"""Health monitoring API router.

Provides endpoints for unified health monitoring:
- GET /api/v1/health: Current health status
- GET /api/v1/health/components: Per-component health
- GET /api/v1/health/history: Health history
- GET /api/v1/health/trend: Health trend analysis

For PAPER-003-001: Unified Health Monitoring System
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.health.monitor import HealthMonitor

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/health", tags=["health"])

# Global monitor instance (initialized by application)
_monitor: HealthMonitor | None = None
_discord_initializer: Any | None = None


def set_discord_initializer(initializer: Any) -> None:
    """Set the global Discord initializer instance.

    Args:
        initializer: DiscordInitializer instance
    """
    global _discord_initializer
    _discord_initializer = initializer


def set_health_monitor(monitor: HealthMonitor) -> None:
    """Set the global health monitor instance.

    Args:
        monitor: HealthMonitor instance
    """
    global _monitor
    _monitor = monitor
    logger.info("Health monitor registered with API")


def get_health_monitor() -> HealthMonitor | None:
    """Get the global health monitor instance.

    Returns:
        HealthMonitor instance or None
    """
    return _monitor


@router.get("", response_model=dict[str, Any])
async def get_health() -> dict[str, Any]:
    """Get current system health.

    Returns:
        Dictionary with overall health score, status, and component breakdown
    """
    if _monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Health monitor not initialized",
        )

    try:
        status = await _monitor.get_status()
        return {
            "success": True,
            "data": status,
        }
    except Exception as e:
        logger.error(f"Failed to get health status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health status: {str(e)}",
        )


@router.get("/summary")
async def get_health_summary() -> dict[str, Any]:
    """Get quick health summary.

    Returns:
        Simplified health status for quick checks
    """
    if _monitor is None:
        return {
            "success": False,
            "status": "unknown",
            "score": 0,
            "healthy": False,
        }

    try:
        health = _monitor.get_health_sync()
        return {
            "success": True,
            "status": health.status.value,
            "score": round(health.overall_score, 2),
            "healthy": _monitor.is_healthy(),
            "critical": _monitor.is_critical(),
        }
    except Exception as e:
        logger.error(f"Failed to get health summary: {e}")
        return {
            "success": False,
            "status": "error",
            "score": 0,
            "healthy": False,
            "error": str(e),
        }


@router.get("/components")
async def get_component_health(
    component: str | None = Query(None, description="Filter by component name"),
) -> dict[str, Any]:
    """Get per-component health scores.

    Args:
        component: Optional component name to filter by

    Returns:
        Dictionary with component health details
    """
    if _monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Health monitor not initialized",
        )

    try:
        health = await _monitor.get_health()

        if component:
            # Find specific component
            from src.health import ComponentType

            try:
                comp_type = ComponentType(component)
                comp_score = health.get_component_score(comp_type)
                if comp_score:
                    return {
                        "success": True,
                        "data": comp_score.to_dict(),
                    }
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Component '{component}' not found",
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid component: '{component}'",
                )

        # Return all components
        return {
            "success": True,
            "data": {
                "components": [cs.to_dict() for cs in health.component_scores],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get component health: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get component health: {str(e)}",
        )


@router.get("/history")
async def get_health_history(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to retrieve"),
    component: str | None = Query(None, description="Filter by component"),
) -> dict[str, Any]:
    """Get health history.

    Args:
        hours: Number of hours of history (1-168)
        component: Optional component to filter by

    Returns:
        Dictionary with health history snapshots
    """
    if _monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Health monitor not initialized",
        )

    try:
        history = await _monitor.history.get_recent_history(
            minutes=hours * 60,
            component=component,
        )

        return {
            "success": True,
            "data": {
                "hours": hours,
                "component": component,
                "snapshots": [h.to_dict() for h in history],
                "count": len(history),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get health history: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health history: {str(e)}",
        )


@router.get("/trend")
async def get_health_trend(
    hours: int = Query(24, ge=1, le=168, description="Hours for trend analysis"),
    component: str | None = Query(None, description="Component to analyze"),
) -> dict[str, Any]:
    """Get health trend analysis.

    Args:
        hours: Number of hours to analyze (1-168)
        component: Optional component to analyze

    Returns:
        Dictionary with trend analysis
    """
    if _monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Health monitor not initialized",
        )

    try:
        trend = await _monitor.history.calculate_trend(
            hours=hours,
            component=component,
        )

        if trend is None:
            return {
                "success": True,
                "data": {
                    "hours": hours,
                    "component": component,
                    "message": "Insufficient data for trend analysis",
                    "trend": None,
                },
            }

        return {
            "success": True,
            "data": {
                "hours": hours,
                "component": component,
                "trend": trend.to_dict(),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get health trend: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health trend: {str(e)}",
        )


@router.get("/alerts")
async def get_alert_history(
    hours: int = Query(24, ge=1, le=168, description="Hours of alerts to retrieve"),
    severity: str | None = Query(None, description="Filter by severity"),
    component: str | None = Query(None, description="Filter by component"),
) -> dict[str, Any]:
    """Get alert history.

    Args:
        hours: Number of hours of alert history
        severity: Filter by severity (info, warning, critical)
        component: Filter by component

    Returns:
        Dictionary with alert history
    """
    if _monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Health monitor not initialized",
        )

    try:
        alerts = await _monitor.history.get_alert_history(
            hours=hours,
            severity=severity,
            component=component,
        )

        return {
            "success": True,
            "data": {
                "hours": hours,
                "severity": severity,
                "component": component,
                "alerts": alerts,
                "count": len(alerts),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get alert history: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get alert history: {str(e)}",
        )
