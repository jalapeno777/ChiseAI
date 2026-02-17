"""Health monitoring for connection pools.

Tracks pool health, connection lifecycle, and performance metrics.

For ST-NS-026: Connection Pooling for Exchange APIs
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from data.exchange.pooling.connection_pool import ExchangeConnectionPool, PoolMetrics

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check.

    Attributes:
        healthy: Whether the pool is healthy
        timestamp: When the check was performed
        latency_ms: Health check latency
        pool_metrics: Current pool metrics
        errors: List of any errors encountered
        recommendations: List of recommendations
    """

    healthy: bool
    timestamp: float
    latency_ms: float
    pool_metrics: PoolMetrics
    errors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ConnectionLifecycleEvent:
    """Event in a connection's lifecycle.

    Attributes:
        event_type: Type of event (created, acquired, released, closed)
        timestamp: When the event occurred
        connection_id: Unique connection identifier
        duration_ms: Duration for this event (if applicable)
    """

    event_type: str
    timestamp: float
    connection_id: str
    duration_ms: float | None = None


class PoolHealthMonitor:
    """Monitor health of exchange connection pools.

    Tracks pool metrics, performs health checks, and provides
    alerts when pools are unhealthy.

    Example:
        monitor = PoolHealthMonitor()
        monitor.add_pool(bybit_pool)

        # Start monitoring
        await monitor.start()

        # Get health status
        health = await monitor.check_health()
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        max_history: int = 1000,
    ) -> None:
        """Initialize health monitor.

        Args:
            check_interval: Seconds between health checks
            max_history: Maximum number of events to retain
        """
        self.check_interval = check_interval
        self.max_history = max_history

        self._pools: dict[str, ExchangeConnectionPool] = {}
        self._history: dict[str, deque[HealthCheckResult]] = {}
        self._lifecycle_events: dict[str, deque[ConnectionLifecycleEvent]] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._alert_callbacks: list[Callable[[str, HealthCheckResult], None]] = []

        # Thresholds
        self._latency_threshold_ms = 1000.0  # 1 second
        self._utilization_threshold = 90.0  # 90%
        self._error_rate_threshold = 10.0  # 10%

    def add_pool(self, name: str, pool: ExchangeConnectionPool) -> None:
        """Add a pool to monitor.

        Args:
            name: Pool identifier
            pool: Connection pool to monitor
        """
        self._pools[name] = pool
        self._history[name] = deque(maxlen=self.max_history)
        self._lifecycle_events[name] = deque(maxlen=self.max_history)
        logger.info(f"Added pool '{name}' to health monitor")

    def remove_pool(self, name: str) -> None:
        """Remove a pool from monitoring.

        Args:
            name: Pool identifier
        """
        if name in self._pools:
            del self._pools[name]
            del self._history[name]
            del self._lifecycle_events[name]
            logger.info(f"Removed pool '{name}' from health monitor")

    def on_alert(self, callback: Callable[[str, HealthCheckResult], None]) -> None:
        """Register an alert callback.

        Args:
            callback: Function called with (pool_name, health_result)
        """
        self._alert_callbacks.append(callback)

    async def start(self) -> None:
        """Start continuous health monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Pool health monitoring started")

    async def stop(self) -> None:
        """Stop health monitoring."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Pool health monitoring stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                for name in self._pools:
                    result = await self._check_pool_health(name)
                    self._history[name].append(result)

                    if not result.healthy:
                        await self._trigger_alerts(name, result)

                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)  # Short delay on error

    async def _check_pool_health(self, name: str) -> HealthCheckResult:
        """Check health of a specific pool.

        Args:
            name: Pool identifier

        Returns:
            Health check result
        """
        pool = self._pools[name]
        start_time = time.monotonic()
        errors = []
        recommendations = []

        try:
            # Get pool metrics
            metrics = pool.get_metrics()

            # Perform health check
            health = await pool.health_check()

            # Check for issues
            if not health.get("healthy", False):
                errors.append("Pool health check failed")
                recommendations.append("Check network connectivity to exchange")

            # Check latency
            if metrics.avg_response_time_ms > self._latency_threshold_ms:
                errors.append(
                    f"High latency: {metrics.avg_response_time_ms:.0f}ms "
                    f"(threshold: {self._latency_threshold_ms:.0f}ms)"
                )
                recommendations.append(
                    "Consider increasing pool size or checking network"
                )

            # Check utilization
            if metrics.pool_utilization > self._utilization_threshold:
                errors.append(
                    f"High pool utilization: {metrics.pool_utilization:.1f}% "
                    f"(threshold: {self._utilization_threshold:.1f}%)"
                )
                recommendations.append("Consider increasing pool size")

            # Check error rate
            if metrics.total_requests > 0:
                error_rate = (metrics.failed_requests / metrics.total_requests) * 100
                if error_rate > self._error_rate_threshold:
                    errors.append(
                        f"High error rate: {error_rate:.1f}% "
                        f"(threshold: {self._error_rate_threshold:.1f}%)"
                    )
                    recommendations.append("Check API credentials and rate limits")

            # Check rate limit hits
            if metrics.rate_limit_hits > 0:
                errors.append(f"Rate limit hits: {metrics.rate_limit_hits}")
                recommendations.append(
                    "Consider reducing request rate or increasing rate limit config"
                )

            latency_ms = (time.monotonic() - start_time) * 1000

            return HealthCheckResult(
                healthy=len(errors) == 0,
                timestamp=time.time(),
                latency_ms=latency_ms,
                pool_metrics=metrics,
                errors=errors,
                recommendations=recommendations,
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            return HealthCheckResult(
                healthy=False,
                timestamp=time.time(),
                latency_ms=latency_ms,
                pool_metrics=pool.get_metrics(),
                errors=[f"Health check exception: {e}"],
                recommendations=["Check pool configuration and connectivity"],
            )

    async def _trigger_alerts(self, name: str, result: HealthCheckResult) -> None:
        """Trigger alert callbacks.

        Args:
            name: Pool identifier
            result: Health check result
        """
        logger.warning(f"Pool '{name}' health alert: {result.errors}")

        for callback in self._alert_callbacks:
            try:
                callback(name, result)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    async def check_health(
        self, name: str | None = None
    ) -> dict[str, HealthCheckResult]:
        """Perform health check(s).

        Args:
            name: Specific pool to check, or None for all

        Returns:
            Dictionary of pool name to health result
        """
        results = {}

        pools_to_check = [name] if name else list(self._pools.keys())

        for pool_name in pools_to_check:
            if pool_name in self._pools:
                result = await self._check_pool_health(pool_name)
                results[pool_name] = result
                self._history[pool_name].append(result)

        return results

    def get_metrics(self, name: str | None = None) -> dict[str, Any]:
        """Get current metrics for pool(s).

        Args:
            name: Specific pool, or None for all

        Returns:
            Dictionary of metrics
        """
        results = {}

        pools_to_check = [name] if name else list(self._pools.keys())

        for pool_name in pools_to_check:
            if pool_name in self._pools:
                results[pool_name] = {
                    "current": self._pools[pool_name].get_metrics(),
                    "history_size": len(self._history.get(pool_name, [])),
                }

        return results

    def get_history(self, name: str, limit: int = 100) -> list[HealthCheckResult]:
        """Get health check history for a pool.

        Args:
            name: Pool identifier
            limit: Maximum number of results

        Returns:
            List of health check results
        """
        if name not in self._history:
            return []

        history = list(self._history[name])
        return history[-limit:] if limit else history

    def record_lifecycle_event(
        self, pool_name: str, event: ConnectionLifecycleEvent
    ) -> None:
        """Record a connection lifecycle event.

        Args:
            pool_name: Pool identifier
            event: Lifecycle event to record
        """
        if pool_name in self._lifecycle_events:
            self._lifecycle_events[pool_name].append(event)

    def get_lifecycle_stats(self, name: str) -> dict[str, Any]:
        """Get lifecycle statistics for a pool.

        Args:
            name: Pool identifier

        Returns:
            Dictionary of lifecycle statistics
        """
        if name not in self._lifecycle_events:
            return {}

        events = list(self._lifecycle_events[name])

        # Count by type
        event_counts = {}
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        # Calculate average durations
        durations = {
            event.event_type: [] for event in events if event.duration_ms is not None
        }
        for event in events:
            if event.duration_ms is not None:
                durations[event.event_type].append(event.duration_ms)

        avg_durations = {
            event_type: sum(times) / len(times) if times else 0
            for event_type, times in durations.items()
        }

        return {
            "total_events": len(events),
            "event_counts": event_counts,
            "average_durations_ms": avg_durations,
        }

    def set_thresholds(
        self,
        latency_ms: float | None = None,
        utilization: float | None = None,
        error_rate: float | None = None,
    ) -> None:
        """Update health check thresholds.

        Args:
            latency_ms: New latency threshold in milliseconds
            utilization: New utilization threshold (percentage)
            error_rate: New error rate threshold (percentage)
        """
        if latency_ms is not None:
            self._latency_threshold_ms = latency_ms
        if utilization is not None:
            self._utilization_threshold = utilization
        if error_rate is not None:
            self._error_rate_threshold = error_rate

        logger.info(
            f"Updated thresholds: latency={self._latency_threshold_ms}ms, "
            f"utilization={self._utilization_threshold}%, "
            f"error_rate={self._error_rate_threshold}%"
        )


class HealthReporter:
    """Generate health reports for pools.

    Creates formatted reports suitable for logging,
    monitoring systems, or dashboards.
    """

    @staticmethod
    def format_text_report(pool_name: str, result: HealthCheckResult) -> str:
        """Format a health check result as text.

        Args:
            pool_name: Pool identifier
            result: Health check result

        Returns:
            Formatted text report
        """
        lines = [
            f"=== Pool Health Report: {pool_name} ===",
            f"Status: {'HEALTHY' if result.healthy else 'UNHEALTHY'}",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result.timestamp))}",
            f"Check Latency: {result.latency_ms:.2f}ms",
            "",
            "Pool Metrics:",
            f"  Pool Size: {result.pool_metrics.pool_size}",
            f"  Active Connections: {result.pool_metrics.active_connections}",
            f"  Idle Connections: {result.pool_metrics.idle_connections}",
            f"  Total Requests: {result.pool_metrics.total_requests}",
            f"  Success Rate: {result.pool_metrics.success_rate:.1f}%",
            f"  Avg Response Time: {result.pool_metrics.avg_response_time_ms:.2f}ms",
            f"  Pool Utilization: {result.pool_metrics.pool_utilization:.1f}%",
            f"  Rate Limit Hits: {result.pool_metrics.rate_limit_hits}",
        ]

        if result.errors:
            lines.extend(["", "Errors:"])
            for error in result.errors:
                lines.append(f"  - {error}")

        if result.recommendations:
            lines.extend(["", "Recommendations:"])
            for rec in result.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)

    @staticmethod
    def format_json_report(pool_name: str, result: HealthCheckResult) -> dict[str, Any]:
        """Format a health check result as JSON/dict.

        Args:
            pool_name: Pool identifier
            result: Health check result

        Returns:
            Dictionary representation
        """
        return {
            "pool_name": pool_name,
            "healthy": result.healthy,
            "timestamp": result.timestamp,
            "latency_ms": result.latency_ms,
            "metrics": {
                "pool_size": result.pool_metrics.pool_size,
                "active_connections": result.pool_metrics.active_connections,
                "idle_connections": result.pool_metrics.idle_connections,
                "total_requests": result.pool_metrics.total_requests,
                "successful_requests": result.pool_metrics.successful_requests,
                "failed_requests": result.pool_metrics.failed_requests,
                "success_rate": result.pool_metrics.success_rate,
                "avg_response_time_ms": result.pool_metrics.avg_response_time_ms,
                "pool_utilization": result.pool_metrics.pool_utilization,
                "rate_limit_hits": result.pool_metrics.rate_limit_hits,
            },
            "errors": result.errors,
            "recommendations": result.recommendations,
        }
