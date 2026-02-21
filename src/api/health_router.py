"""Health monitoring API router.

Provides endpoints for unified health monitoring:
- GET /api/v1/health: Current health status
- GET /api/v1/health/components: Per-component health
- GET /api/v1/health/history: Health history
- GET /api/v1/health/trend: Health trend analysis
- GET /api/v1/health/acp: ACP component health status
- GET /api/v1/health/acp/components: Detailed ACP component breakdown
- GET /api/v1/health/acp/budget: Healing budget details

For PAPER-003-001: Unified Health Monitoring System
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.health.monitor import HealthMonitor

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/health", tags=["health"])

# Global monitor instance (initialized by application)
_monitor: HealthMonitor | None = None

# Global ACP container and Discord initializer (set by startup.py)
_acp_container: Any | None = None
_discord_initializer: Any | None = None


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


def set_acp_container(container: Any) -> None:
    """Set the global ACP container.

    Args:
        container: ACPContainer instance
    """
    global _acp_container
    _acp_container = container
    logger.info("ACP container registered with health API")


def set_discord_initializer(initializer: Any) -> None:
    """Set the global Discord initializer.

    Args:
        initializer: DiscordInitializer instance
    """
    global _discord_initializer
    _discord_initializer = initializer
    logger.info("Discord initializer registered with health API")


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


@router.get("/acp")
async def get_acp_health() -> dict[str, Any]:
    """Get comprehensive ACP health status.

    Returns:
        Dictionary with status of all ACP components including:
        - SelfHealingEngine status
        - LogMonitor status
        - HealingTriggerService status
        - RollbackCoordinator status
        - CircuitBreakerRegistry status
        - Discord status
        - IncidentManager status
        - DashboardSyncServer status
        - Kill switch status
        - Global healing budget status
    """
    if _acp_container is None:
        return {
            "success": False,
            "error": "ACP container not initialized",
        }

    try:
        status = {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }

        # SelfHealingEngine
        try:
            engine = _acp_container.self_healing_engine
            status["components"]["healing_engine"] = {
                "status": "healthy" if engine.is_enabled() else "disabled",
                "enabled": engine.is_enabled(),
                "pattern_count": engine.get_status().get("pattern_count", 0),
                "pending_approvals": len(engine.get_pending_approvals()),
            }
        except Exception as e:
            status["components"]["healing_engine"] = {
                "status": "error",
                "error": str(e),
            }

        # LogMonitor
        try:
            monitor = _acp_container.log_monitor
            status["components"]["log_monitor"] = {
                "status": "running" if monitor._running else "stopped",
                "watchers": len(monitor._watchers),
            }
        except Exception as e:
            status["components"]["log_monitor"] = {"status": "error", "error": str(e)}

        # TriggerService
        try:
            trigger = _acp_container.trigger_service
            status["components"]["trigger_service"] = {
                "status": "running" if trigger._running else "stopped",
                "triggers_last_minute": trigger.get_stats()["triggers_last_minute"],
            }
        except Exception as e:
            status["components"]["trigger_service"] = {
                "status": "error",
                "error": str(e),
            }

        # RollbackCoordinator
        try:
            rollback = _acp_container.rollback_coordinator
            # Check for in-progress operations by listing with EXECUTING status
            from src.autonomous_control_plane.models.rollback import RollbackStatus

            operations = await rollback.list_operations(
                status=RollbackStatus.EXECUTING, limit=10
            )
            in_progress = len(operations) > 0
            status["components"]["rollback_coordinator"] = {
                "status": "busy" if in_progress else "ready",
                "rollback_in_progress": in_progress,
                "operations_in_progress": len(operations),
            }
        except Exception as e:
            status["components"]["rollback_coordinator"] = {
                "status": "error",
                "error": str(e),
            }

        # CircuitBreakerRegistry
        try:
            cb_registry = _acp_container.circuit_breaker_registry
            breaker_states = cb_registry.get_all_states()
            status["components"]["circuit_breakers"] = {
                "status": "healthy",
                "breaker_count": len(breaker_states),
                "breakers": breaker_states,
            }
        except Exception as e:
            status["components"]["circuit_breakers"] = {
                "status": "error",
                "error": str(e),
            }

        # Discord
        if _discord_initializer:
            try:
                discord_health = _discord_initializer.get_health()
                status["components"]["discord"] = {
                    "status": "connected"
                    if discord_health.get("connected")
                    else "disconnected",
                    **discord_health,
                }
            except Exception as e:
                status["components"]["discord"] = {"status": "error", "error": str(e)}
        else:
            status["components"]["discord"] = {"status": "not_configured"}

        # IncidentManager
        try:
            incident_manager = _acp_container.incident_manager
            # Get basic incident stats
            all_incidents = await incident_manager.get_all_incidents()
            open_incidents = [
                i for i in all_incidents if i.status.value in ("open", "investigating")
            ]
            status["components"]["incident_manager"] = {
                "status": "healthy",
                "total_incidents": len(all_incidents),
                "open_incidents": len(open_incidents),
            }
        except Exception as e:
            status["components"]["incident_manager"] = {
                "status": "error",
                "error": str(e),
            }

        # DashboardSyncServer
        try:
            dashboard_sync = _acp_container.dashboard_sync
            status["components"]["dashboard_sync"] = {
                "status": "running" if dashboard_sync._running else "stopped",
                "connected_clients": len(dashboard_sync._clients),
            }
        except Exception as e:
            status["components"]["dashboard_sync"] = {
                "status": "error",
                "error": str(e),
            }

        # Global budget
        try:
            engine = _acp_container.self_healing_engine
            budget = engine.get_global_budget_status()
            status["global_budget"] = budget
        except Exception as e:
            status["global_budget"] = {"status": "error", "error": str(e)}

        return status

    except Exception as e:
        logger.error(f"Failed to get ACP health: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/acp/components")
async def get_acp_components() -> dict[str, Any]:
    """Get detailed ACP component breakdown.

    Returns:
        Dictionary with detailed status for each ACP component
    """
    if _acp_container is None:
        return {
            "success": False,
            "error": "ACP container not initialized",
        }

    try:
        components = {}

        # SelfHealingEngine details
        try:
            engine = _acp_container.self_healing_engine
            engine_status = engine.get_status()
            components["healing_engine"] = {
                "status": "healthy" if engine.is_enabled() else "disabled",
                "enabled": engine.is_enabled(),
                "pattern_count": engine_status.get("pattern_count", 0),
                "patterns": engine_status.get("patterns", []),
                "pending_approvals": len(engine.get_pending_approvals()),
                "approval_details": [
                    {
                        "attempt_id": a.attempt_id,
                        "pattern_name": a.pattern_name,
                        "created_at": a.created_at.isoformat()
                        if hasattr(a, "created_at")
                        else None,
                    }
                    for a in engine.get_pending_approvals()
                ],
            }
        except Exception as e:
            components["healing_engine"] = {"status": "error", "error": str(e)}

        # LogMonitor details
        try:
            monitor = _acp_container.log_monitor
            stats = monitor.get_stats()
            components["log_monitor"] = {
                "status": "running" if monitor._running else "stopped",
                "watchers_count": len(monitor._watchers),
                "watchers": list(monitor._watchers.keys()),
                "total_entries": stats.get("total_entries", 0),
                "error_entries": stats.get("error_entries", 0),
            }
        except Exception as e:
            components["log_monitor"] = {"status": "error", "error": str(e)}

        # TriggerService details
        try:
            trigger = _acp_container.trigger_service
            stats = trigger.get_stats()
            components["trigger_service"] = {
                "status": "running" if trigger._running else "stopped",
                "triggers_last_minute": stats.get("triggers_last_minute", 0),
                "max_triggers_per_minute": stats.get("max_triggers_per_minute", 0),
                "total_entries_received": stats.get("total_entries_received", 0),
                "entries_filtered": stats.get("entries_filtered", 0),
                "triggers_attempted": stats.get("triggers_attempted", 0),
                "triggers_rate_limited": stats.get("triggers_rate_limited", 0),
                "triggers_failed": stats.get("triggers_failed", 0),
                "last_trigger_time": stats.get("last_trigger_time"),
            }
        except Exception as e:
            components["trigger_service"] = {"status": "error", "error": str(e)}

        # RollbackCoordinator details
        try:
            rollback = _acp_container.rollback_coordinator
            from src.autonomous_control_plane.models.rollback import RollbackStatus

            all_ops = await rollback.list_operations(limit=100)
            executing_ops = [o for o in all_ops if o.status == RollbackStatus.EXECUTING]
            pending_ops = [o for o in all_ops if o.status == RollbackStatus.PENDING]
            failed_ops = [o for o in all_ops if o.status == RollbackStatus.FAILED]

            components["rollback_coordinator"] = {
                "status": "busy" if executing_ops else "ready",
                "total_operations": len(all_ops),
                "executing": len(executing_ops),
                "pending": len(pending_ops),
                "failed": len(failed_ops),
                "recent_operations": [
                    {
                        "operation_id": o.operation_id,
                        "status": o.status.value,
                        "target_state": o.target_state,
                        "created_at": o.created_at.isoformat()
                        if hasattr(o, "created_at")
                        else None,
                    }
                    for o in all_ops[:10]
                ],
            }
        except Exception as e:
            components["rollback_coordinator"] = {"status": "error", "error": str(e)}

        # CircuitBreakerRegistry details
        try:
            cb_registry = _acp_container.circuit_breaker_registry
            breaker_states = cb_registry.get_all_states()
            components["circuit_breakers"] = {
                "status": "healthy",
                "breaker_count": len(breaker_states),
                "breakers": breaker_states,
                "open_breakers": [
                    name for name, state in breaker_states.items() if state == "open"
                ],
            }
        except Exception as e:
            components["circuit_breakers"] = {"status": "error", "error": str(e)}

        # Discord details
        if _discord_initializer:
            try:
                discord_health = _discord_initializer.get_health()
                components["discord"] = {
                    "status": "connected"
                    if discord_health.get("connected")
                    else "disconnected",
                    **discord_health,
                }
            except Exception as e:
                components["discord"] = {"status": "error", "error": str(e)}
        else:
            components["discord"] = {"status": "not_configured"}

        # IncidentManager details
        try:
            incident_manager = _acp_container.incident_manager
            all_incidents = await incident_manager.get_all_incidents()

            # Count by severity
            p0_count = sum(1 for i in all_incidents if i.severity.value == "P0")
            p1_count = sum(1 for i in all_incidents if i.severity.value == "P1")
            p2_count = sum(1 for i in all_incidents if i.severity.value == "P2")
            p3_count = sum(1 for i in all_incidents if i.severity.value == "P3")

            # Count by status
            open_count = sum(
                1 for i in all_incidents if i.status.value in ("open", "investigating")
            )
            resolved_count = sum(
                1 for i in all_incidents if i.status.value == "resolved"
            )

            components["incident_manager"] = {
                "status": "healthy",
                "total_incidents": len(all_incidents),
                "by_severity": {
                    "P0": p0_count,
                    "P1": p1_count,
                    "P2": p2_count,
                    "P3": p3_count,
                },
                "by_status": {
                    "open": open_count,
                    "resolved": resolved_count,
                },
            }
        except Exception as e:
            components["incident_manager"] = {"status": "error", "error": str(e)}

        # DashboardSyncServer details
        try:
            dashboard_sync = _acp_container.dashboard_sync
            components["dashboard_sync"] = {
                "status": "running" if dashboard_sync._running else "stopped",
                "connected_clients": len(dashboard_sync._clients),
                "client_count": len(dashboard_sync._clients),
            }
        except Exception as e:
            components["dashboard_sync"] = {"status": "error", "error": str(e)}

        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "components": components,
        }

    except Exception as e:
        logger.error(f"Failed to get ACP components: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/acp/budget")
async def get_acp_budget() -> dict[str, Any]:
    """Get healing budget details.

    Returns:
        Dictionary with detailed healing budget information
    """
    if _acp_container is None:
        return {
            "success": False,
            "error": "ACP container not initialized",
        }

    try:
        engine = _acp_container.self_healing_engine
        budget = engine.get_global_budget_status()

        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget,
        }

    except Exception as e:
        logger.error(f"Failed to get ACP budget: {e}")
        return {
            "success": False,
            "error": str(e),
        }
