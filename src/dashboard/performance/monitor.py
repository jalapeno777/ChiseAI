"""Performance monitoring for dashboard components.

Tracks load times, identifies slow panels, and generates alerts
when performance thresholds are exceeded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dashboard.performance.cache import CacheStats

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class PerformanceThresholds:
    """Performance thresholds for alerting.

    Attributes:
        load_time_warning_ms: Warning threshold for load time (ms)
        load_time_critical_ms: Critical threshold for load time (ms)
        cache_hit_rate_warning: Warning threshold for cache hit rate (%)
        cache_hit_rate_critical: Critical threshold for cache hit rate (%)
        slow_query_count_warning: Warning threshold for slow query count
        slow_query_count_critical: Critical threshold for slow query count
    """

    load_time_warning_ms: float = 2000.0  # 2 seconds
    load_time_critical_ms: float = 3000.0  # 3 seconds
    cache_hit_rate_warning: float = 70.0  # 70%
    cache_hit_rate_critical: float = 50.0  # 50%
    slow_query_count_warning: int = 10
    slow_query_count_critical: int = 25

    @classmethod
    def default(cls) -> PerformanceThresholds:
        """Get default thresholds."""
        return cls()

    @classmethod
    def strict(cls) -> PerformanceThresholds:
        """Get stricter thresholds for production."""
        return cls(
            load_time_warning_ms=1500.0,
            load_time_critical_ms=2500.0,
            cache_hit_rate_warning=80.0,
            cache_hit_rate_critical=60.0,
            slow_query_count_warning=5,
            slow_query_count_critical=15,
        )


@dataclass
class LoadTimeMetric:
    """Metric for a single load time measurement.

    Attributes:
        component: Dashboard component name
        load_time_ms: Load time in milliseconds
        timestamp: When the measurement was taken
        cached: Whether the result was cached
        query_count: Number of queries executed
        error: Error message if load failed
    """

    component: str
    load_time_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    cached: bool = False
    query_count: int = 0
    error: str | None = None

    def is_slow(self, thresholds: PerformanceThresholds | None = None) -> bool:
        """Check if load time is slow.

        Args:
            thresholds: Performance thresholds to use

        Returns:
            True if load time exceeds warning threshold
        """
        threshold = (thresholds or PerformanceThresholds.default()).load_time_warning_ms
        return self.load_time_ms > threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "component": self.component,
            "load_time_ms": round(self.load_time_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "cached": self.cached,
            "query_count": self.query_count,
            "error": self.error,
            "is_slow": self.is_slow(),
        }


@dataclass
class PerformanceAlert:
    """Performance alert for dashboard monitoring.

    Attributes:
        alert_id: Unique alert identifier
        severity: Alert severity level
        component: Component that triggered the alert
        message: Alert message
        metric_value: Actual metric value
        threshold: Threshold that was exceeded
        timestamp: When the alert was triggered
        resolved: Whether the alert has been resolved
        resolved_at: When the alert was resolved
    """

    alert_id: str
    severity: AlertSeverity
    component: str
    message: str
    metric_value: float
    threshold: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolved_at: datetime | None = None

    def resolve(self) -> None:
        """Mark alert as resolved."""
        self.resolved = True
        self.resolved_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "component": self.component,
            "message": self.message,
            "metric_value": round(self.metric_value, 2),
            "threshold": round(self.threshold, 2),
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class PerformanceMonitor:
    """Monitor for dashboard performance tracking.

    Tracks load times, cache performance, and generates alerts
    when thresholds are exceeded.

    Example:
        monitor = PerformanceMonitor()
        monitor.record_load_time("signal_list", 1500, cached=True)
        metrics = monitor.get_component_metrics("signal_list")
        alerts = monitor.check_alerts()
    """

    def __init__(
        self,
        thresholds: PerformanceThresholds | None = None,
        history_size: int = 1000,
    ):
        """Initialize performance monitor.

        Args:
            thresholds: Performance thresholds for alerting
            history_size: Maximum number of metrics to keep per component
        """
        self.thresholds = thresholds or PerformanceThresholds.default()
        self.history_size = history_size
        self._metrics: dict[str, list[LoadTimeMetric]] = {}
        self._alerts: list[PerformanceAlert] = []
        self._alert_counter = 0

    def record_load_time(
        self,
        component: str,
        load_time_ms: float,
        cached: bool = False,
        query_count: int = 0,
        error: str | None = None,
    ) -> LoadTimeMetric:
        """Record a load time measurement.

        Args:
            component: Dashboard component name
            load_time_ms: Load time in milliseconds
            cached: Whether the result was cached
            query_count: Number of queries executed
            error: Error message if load failed

        Returns:
            Recorded LoadTimeMetric
        """
        metric = LoadTimeMetric(
            component=component,
            load_time_ms=load_time_ms,
            cached=cached,
            query_count=query_count,
            error=error,
        )

        if component not in self._metrics:
            self._metrics[component] = []

        self._metrics[component].append(metric)

        # Trim history if needed
        if len(self._metrics[component]) > self.history_size:
            self._metrics[component] = self._metrics[component][-self.history_size :]

        # Log slow loads
        if metric.is_slow(self.thresholds):
            logger.warning(
                f"Slow load detected: {component} took {load_time_ms:.0f}ms "
                f"(threshold: {self.thresholds.load_time_warning_ms}ms)"
            )

        return metric

    def get_component_metrics(
        self,
        component: str,
        since: datetime | None = None,
    ) -> list[LoadTimeMetric]:
        """Get metrics for a specific component.

        Args:
            component: Dashboard component name
            since: Only return metrics after this time

        Returns:
            List of LoadTimeMetric for the component
        """
        metrics = self._metrics.get(component, [])

        if since:
            metrics = [m for m in metrics if m.timestamp >= since]

        return metrics

    def get_all_metrics(
        self, since: datetime | None = None
    ) -> dict[str, list[LoadTimeMetric]]:
        """Get all metrics grouped by component.

        Args:
            since: Only return metrics after this time

        Returns:
            Dictionary of component -> metrics
        """
        result = {}
        for component in self._metrics:
            result[component] = self.get_component_metrics(component, since)
        return result

    def check_alerts(
        self, cache_stats: CacheStats | None = None
    ) -> list[PerformanceAlert]:
        """Check for performance alerts.

        Args:
            cache_stats: Optional cache statistics to check

        Returns:
            List of new PerformanceAlert instances
        """
        new_alerts: list[PerformanceAlert] = []

        # Check load time alerts for each component
        for component, metrics in self._metrics.items():
            if not metrics:
                continue

            # Check recent average load time
            recent = [
                m
                for m in metrics
                if m.timestamp >= datetime.now(UTC) - timedelta(minutes=5)
            ]
            if not recent:
                continue

            avg_load_time = sum(m.load_time_ms for m in recent) / len(recent)

            if avg_load_time >= self.thresholds.load_time_critical_ms:
                alert = self._create_alert(
                    component=component,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Average load time {avg_load_time:.0f}ms exceeds critical threshold",
                    metric_value=avg_load_time,
                    threshold=self.thresholds.load_time_critical_ms,
                )
                new_alerts.append(alert)

            elif avg_load_time >= self.thresholds.load_time_warning_ms:
                alert = self._create_alert(
                    component=component,
                    severity=AlertSeverity.WARNING,
                    message=f"Average load time {avg_load_time:.0f}ms exceeds warning threshold",
                    metric_value=avg_load_time,
                    threshold=self.thresholds.load_time_warning_ms,
                )
                new_alerts.append(alert)

        # Check cache hit rate if provided
        if cache_stats:
            hit_rate = cache_stats.hit_rate

            if hit_rate <= self.thresholds.cache_hit_rate_critical:
                alert = self._create_alert(
                    component="cache",
                    severity=AlertSeverity.CRITICAL,
                    message=f"Cache hit rate {hit_rate:.1f}% is critically low",
                    metric_value=hit_rate,
                    threshold=self.thresholds.cache_hit_rate_critical,
                )
                new_alerts.append(alert)

            elif hit_rate <= self.thresholds.cache_hit_rate_warning:
                alert = self._create_alert(
                    component="cache",
                    severity=AlertSeverity.WARNING,
                    message=f"Cache hit rate {hit_rate:.1f}% is below target",
                    metric_value=hit_rate,
                    threshold=self.thresholds.cache_hit_rate_warning,
                )
                new_alerts.append(alert)

        self._alerts.extend(new_alerts)
        return new_alerts

    def _create_alert(
        self,
        component: str,
        severity: AlertSeverity,
        message: str,
        metric_value: float,
        threshold: float,
    ) -> PerformanceAlert:
        """Create a new performance alert.

        Args:
            component: Component that triggered the alert
            severity: Alert severity
            message: Alert message
            metric_value: Actual metric value
            threshold: Threshold that was exceeded

        Returns:
            New PerformanceAlert instance
        """
        self._alert_counter += 1
        alert_id = f"perf-{self._alert_counter:06d}"

        return PerformanceAlert(
            alert_id=alert_id,
            severity=severity,
            component=component,
            message=message,
            metric_value=metric_value,
            threshold=threshold,
        )

    def get_active_alerts(self) -> list[PerformanceAlert]:
        """Get all unresolved alerts.

        Returns:
            List of unresolved PerformanceAlert instances
        """
        return [a for a in self._alerts if not a.resolved]

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert.

        Args:
            alert_id: ID of alert to resolve

        Returns:
            True if alert was found and resolved
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.resolved:
                alert.resolve()
                return True
        return False

    def get_summary(self) -> dict[str, Any]:
        """Get performance summary.

        Returns:
            Dictionary with performance summary
        """
        component_summaries = {}

        for component, metrics in self._metrics.items():
            if not metrics:
                continue

            recent = [
                m
                for m in metrics
                if m.timestamp >= datetime.now(UTC) - timedelta(minutes=5)
            ]

            if recent:
                load_times = [m.load_time_ms for m in recent]
                component_summaries[component] = {
                    "count": len(recent),
                    "avg_ms": round(sum(load_times) / len(load_times), 2),
                    "max_ms": round(max(load_times), 2),
                    "p95_ms": (
                        round(sorted(load_times)[int(len(load_times) * 0.95)], 2)
                        if len(recent) > 20
                        else round(max(load_times), 2)
                    ),
                    "cache_hit_rate": round(
                        sum(1 for m in recent if m.cached) / len(recent) * 100, 2
                    ),
                }

        active_alerts = self.get_active_alerts()

        return {
            "components": component_summaries,
            "active_alerts": len(active_alerts),
            "critical_alerts": sum(
                1 for a in active_alerts if a.severity == AlertSeverity.CRITICAL
            ),
            "warning_alerts": sum(
                1 for a in active_alerts if a.severity == AlertSeverity.WARNING
            ),
            "thresholds": {
                "load_time_warning_ms": self.thresholds.load_time_warning_ms,
                "load_time_critical_ms": self.thresholds.load_time_critical_ms,
                "cache_hit_rate_warning": self.thresholds.cache_hit_rate_warning,
                "cache_hit_rate_critical": self.thresholds.cache_hit_rate_critical,
            },
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result
        """
        summary = self.get_summary()
        active_alerts = self.get_active_alerts()

        # Determine health status
        if any(a.severity == AlertSeverity.CRITICAL for a in active_alerts):
            status = "unhealthy"
        elif any(a.severity == AlertSeverity.WARNING for a in active_alerts):
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": summary,
            "active_alerts": [a.to_dict() for a in active_alerts[:5]],  # Latest 5
        }


async def track_performance(
    monitor: PerformanceMonitor,
    component: str,
) -> Any:
    """Context manager for tracking component performance.

    Args:
        monitor: Performance monitor instance
        component: Component name to track

    Returns:
        Async context manager

    Example:
        async with track_performance(monitor, "signal_list"):
            # ... component loading logic ...
    """
    start_time = datetime.now(UTC)

    class PerformanceTracker:
        def __init__(self, mon: PerformanceMonitor, comp: str):
            self.monitor = mon
            self.component = comp
            self.start_time = start_time
            self.cached = False
            self.query_count = 0
            self.error: str | None = None

        def mark_cached(self) -> None:
            self.cached = True

        def set_query_count(self, count: int) -> None:
            self.query_count = count

        def set_error(self, error: str) -> None:
            self.error = error

        async def __aenter__(self) -> PerformanceTracker:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            end_time = datetime.now(UTC)
            load_time_ms = (end_time - self.start_time).total_seconds() * 1000

            if exc_val:
                self.error = str(exc_val)

            self.monitor.record_load_time(
                component=self.component,
                load_time_ms=load_time_ms,
                cached=self.cached,
                query_count=self.query_count,
                error=self.error,
            )

    return PerformanceTracker(monitor, component)
