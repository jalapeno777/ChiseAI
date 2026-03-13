"""Dashboard data models.

Provides dataclasses for dashboard state, panels, and metrics.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class PanelType(StrEnum):
    """Types of dashboard panels."""

    CIRCUIT_BREAKERS = "circuit_breakers"
    INCIDENTS = "incidents"
    SELF_HEALING = "self_healing"
    ROLLBACKS = "rollbacks"
    SYSTEM_HEALTH = "system_health"


class HealthStatus(StrEnum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthScore:
    """System health score with breakdown.

    Attributes:
        overall_score: Overall health score (0-100)
        status: Health status level
        circuit_breaker_score: Circuit breaker health contribution (0-100)
        incident_score: Incident health contribution (0-100)
        healing_score: Self-healing health contribution (0-100)
        rollback_score: Rollback health contribution (0-100)
        last_updated: When health score was last calculated
    """

    overall_score: float = 100.0
    status: HealthStatus = HealthStatus.HEALTHY
    circuit_breaker_score: float = 100.0
    incident_score: float = 100.0
    healing_score: float = 100.0
    rollback_score: float = 100.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_score": round(self.overall_score, 2),
            "status": self.status.value,
            "circuit_breaker_score": round(self.circuit_breaker_score, 2),
            "incident_score": round(self.incident_score, 2),
            "healing_score": round(self.healing_score, 2),
            "rollback_score": round(self.rollback_score, 2),
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class CircuitBreakerPanelData:
    """Data for circuit breaker status panel.

    Attributes:
        total_count: Total number of circuit breakers
        open_count: Number of open circuit breakers
        closed_count: Number of closed circuit breakers
        half_open_count: Number of half-open circuit breakers
        breakers: List of circuit breaker states
        groups: List of circuit breaker groups
    """

    total_count: int = 0
    open_count: int = 0
    closed_count: int = 0
    half_open_count: int = 0
    breakers: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_count": self.total_count,
            "open_count": self.open_count,
            "closed_count": self.closed_count,
            "half_open_count": self.half_open_count,
            "breakers": self.breakers,
            "groups": self.groups,
        }


@dataclass
class IncidentPanelData:
    """Data for incident timeline panel.

    Attributes:
        total_incidents: Total number of incidents
        open_incidents: Number of open incidents
        by_severity: Breakdown by severity (P0-P3)
        by_status: Breakdown by status
        recent_incidents: List of recent incidents
        avg_resolution_time: Average time to resolution in seconds
    """

    total_incidents: int = 0
    open_incidents: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    recent_incidents: list[dict[str, Any]] = field(default_factory=list)
    avg_resolution_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_incidents": self.total_incidents,
            "open_incidents": self.open_incidents,
            "by_severity": self.by_severity,
            "by_status": self.by_status,
            "recent_incidents": self.recent_incidents,
            "avg_resolution_time": round(self.avg_resolution_time, 2),
        }


@dataclass
class SelfHealingPanelData:
    """Data for self-healing activity panel.

    Attributes:
        total_attempts: Total number of healing attempts
        successful: Number of successful healings
        failed: Number of failed healings
        pending_approval: Number pending approval
        success_rate: Success rate as percentage
        recent_actions: List of recent healing actions
        active_workflows: Number of active remediation workflows
    """

    total_attempts: int = 0
    successful: int = 0
    failed: int = 0
    pending_approval: int = 0
    success_rate: float = 0.0
    recent_actions: list[dict[str, Any]] = field(default_factory=list)
    active_workflows: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_attempts": self.total_attempts,
            "successful": self.successful,
            "failed": self.failed,
            "pending_approval": self.pending_approval,
            "success_rate": round(self.success_rate, 2),
            "recent_actions": self.recent_actions,
            "active_workflows": self.active_workflows,
        }


@dataclass
class RollbackPanelData:
    """Data for rollback history panel.

    Attributes:
        total_executions: Total number of rollbacks executed
        successful: Number of successful rollbacks
        failed: Number of failed rollbacks
        in_progress: Number of rollbacks in progress
        success_rate: Success rate as percentage
        recent_rollbacks: List of recent rollbacks
    """

    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    in_progress: int = 0
    success_rate: float = 0.0
    recent_rollbacks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_executions": self.total_executions,
            "successful": self.successful,
            "failed": self.failed,
            "in_progress": self.in_progress,
            "success_rate": round(self.success_rate, 2),
            "recent_rollbacks": self.recent_rollbacks,
        }


@dataclass
class SystemHealthPanelData:
    """Data for system health overview panel.

    Attributes:
        health_score: Overall health score
        uptime_seconds: System uptime in seconds
        version: ACP version
        active_connections: Number of active dashboard connections
        last_update: Last update timestamp
        alerts: List of active alerts
    """

    health_score: HealthScore = field(default_factory=HealthScore)
    uptime_seconds: float = 0.0
    version: str = "1.0.0"
    active_connections: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(UTC))
    alerts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "health_score": self.health_score.to_dict(),
            "uptime_seconds": self.uptime_seconds,
            "version": self.version,
            "active_connections": self.active_connections,
            "last_update": self.last_update.isoformat(),
            "alerts": self.alerts,
        }


@dataclass
class DashboardState:
    """Complete dashboard state snapshot.

    Attributes:
        timestamp: When state was captured
        circuit_breakers: Circuit breaker panel data
        incidents: Incident panel data
        self_healing: Self-healing panel data
        rollbacks: Rollback panel data
        system_health: System health panel data
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    circuit_breakers: CircuitBreakerPanelData = field(
        default_factory=CircuitBreakerPanelData
    )
    incidents: IncidentPanelData = field(default_factory=IncidentPanelData)
    self_healing: SelfHealingPanelData = field(default_factory=SelfHealingPanelData)
    rollbacks: RollbackPanelData = field(default_factory=RollbackPanelData)
    system_health: SystemHealthPanelData = field(default_factory=SystemHealthPanelData)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "circuit_breakers": self.circuit_breakers.to_dict(),
            "incidents": self.incidents.to_dict(),
            "self_healing": self.self_healing.to_dict(),
            "rollbacks": self.rollbacks.to_dict(),
            "system_health": self.system_health.to_dict(),
        }


@dataclass
class TimeRange:
    """Time range for historical queries.

    Attributes:
        start: Start datetime
        end: End datetime
    """

    start: datetime = field(default_factory=lambda: datetime.now(UTC))
    end: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


@dataclass
class ChartData:
    """Chart data for visualization.

    Attributes:
        chart_type: Type of chart (line, bar, gauge, etc.)
        labels: X-axis labels
        datasets: Chart datasets
        options: Chart options
    """

    chart_type: str = "line"
    labels: list[str] = field(default_factory=list)
    datasets: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chart_type": self.chart_type,
            "labels": self.labels,
            "datasets": self.datasets,
            "options": self.options,
        }
