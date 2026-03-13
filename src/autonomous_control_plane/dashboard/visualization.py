"""Dashboard visualization layer.

Provides chart data generation for time series, gauges, and counters.
Aggregates metrics for display and trend analysis.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import ChartData, TimeRange

if TYPE_CHECKING:
    from autonomous_control_plane.automation.controller import AutomationController
    from autonomous_control_plane.components.circuit_breaker_registry import (
        CircuitBreakerRegistry,
    )
    from autonomous_control_plane.components.incident_manager import IncidentManager

logger = logging.getLogger(__name__)


class DashboardVisualization:
    """Visualization layer for dashboard charts and graphs.

    Generates chart data for various ACP metrics including:
    - Time series for incident trends
    - Gauges for health scores
    - Counters for activity metrics
    - Trend analysis data

    Example:
        >>> viz = DashboardVisualization(incident_manager=incident_mgr)
        >>> chart = await viz.generate_incident_trend_chart(hours=24)
        >>> gauge = await viz.generate_health_gauge()
    """

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        incident_manager: IncidentManager | None = None,
        automation_controller: AutomationController | None = None,
    ):
        """Initialize visualization layer.

        Args:
            circuit_breaker_registry: Circuit breaker registry
            incident_manager: Incident manager
            automation_controller: Automation controller
        """
        self._cb_registry = circuit_breaker_registry
        self._incident_manager = incident_manager
        self._automation_controller = automation_controller

    async def generate_incident_trend_chart(
        self, hours: int = 24, resolution: str = "hour"
    ) -> ChartData:
        """Generate incident trend chart data.

        Args:
            hours: Number of hours to look back
            resolution: Time resolution (hour, day)

        Returns:
            ChartData for line chart
        """
        chart = ChartData(chart_type="line")

        if self._incident_manager is None:
            return chart

        try:
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=hours)

            # Generate time buckets
            if resolution == "hour":
                buckets = self._generate_hourly_buckets(start_time, end_time)
            else:
                buckets = self._generate_daily_buckets(start_time, end_time)

            # Get incidents
            incidents = await self._incident_manager.list_incidents(
                limit=1000  # Get enough for analysis
            )

            # Count incidents per bucket
            created_counts = {bucket: 0 for bucket in buckets}
            resolved_counts = {bucket: 0 for bucket in buckets}

            for inc in incidents:
                # Created incidents
                created_bucket = self._get_time_bucket(inc.created_at, resolution)
                if created_bucket in created_counts:
                    created_counts[created_bucket] += 1

                # Resolved incidents
                if inc.resolved_at:
                    resolved_bucket = self._get_time_bucket(inc.resolved_at, resolution)
                    if resolved_bucket in resolved_counts:
                        resolved_counts[resolved_bucket] += 1

            # Build chart data
            sorted_buckets = sorted(buckets)
            chart.labels = [
                bucket.strftime("%H:%M" if resolution == "hour" else "%Y-%m-%d")
                for bucket in sorted_buckets
            ]

            chart.datasets = [
                {
                    "label": "Created",
                    "data": [created_counts[b] for b in sorted_buckets],
                    "borderColor": "#ef4444",
                    "backgroundColor": "rgba(239, 68, 68, 0.1)",
                },
                {
                    "label": "Resolved",
                    "data": [resolved_counts[b] for b in sorted_buckets],
                    "borderColor": "#22c55e",
                    "backgroundColor": "rgba(34, 197, 94, 0.1)",
                },
            ]

            chart.options = {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Incident Trend (Last {hours}h)",
                    }
                },
            }

        except Exception as e:
            logger.error(f"Error generating incident trend chart: {e}")

        return chart

    async def generate_health_gauge(self) -> ChartData:
        """Generate health score gauge chart.

        Returns:
            ChartData for gauge chart
        """
        chart = ChartData(chart_type="gauge")

        try:
            # Calculate overall health
            health_score = await self._calculate_overall_health()

            chart.datasets = [
                {
                    "data": [health_score],
                    "backgroundColor": self._get_health_color(health_score),
                    "borderWidth": 0,
                }
            ]

            chart.options = {
                "min": 0,
                "max": 100,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "System Health",
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": lambda ctx: f"{ctx.raw}%",
                        }
                    },
                },
            }

        except Exception as e:
            logger.error(f"Error generating health gauge: {e}")

        return chart

    async def generate_circuit_breaker_status_chart(self) -> ChartData:
        """Generate circuit breaker status distribution chart.

        Returns:
            ChartData for doughnut/pie chart
        """
        chart = ChartData(chart_type="doughnut")

        if self._cb_registry is None:
            return chart

        try:
            states = self._cb_registry.get_all_states_dict()

            open_count = sum(1 for s in states.values() if s.get("state") == "open")
            closed_count = sum(1 for s in states.values() if s.get("state") == "closed")
            half_open_count = sum(
                1 for s in states.values() if s.get("state") == "half_open"
            )

            chart.labels = ["Closed", "Half-Open", "Open"]
            chart.datasets = [
                {
                    "data": [closed_count, half_open_count, open_count],
                    "backgroundColor": [
                        "#22c55e",  # green
                        "#f59e0b",  # amber
                        "#ef4444",  # red
                    ],
                    "borderWidth": 0,
                }
            ]

            chart.options = {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Circuit Breaker Status",
                    },
                    "legend": {
                        "position": "bottom",
                    },
                },
            }

        except Exception as e:
            logger.error(f"Error generating CB status chart: {e}")

        return chart

    async def generate_self_healing_success_chart(self, days: int = 7) -> ChartData:
        """Generate self-healing success rate chart.

        Args:
            days: Number of days to look back

        Returns:
            ChartData for bar chart
        """
        chart = ChartData(chart_type="bar")

        if self._automation_controller is None:
            return chart

        try:
            # Generate day buckets
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=days)
            buckets = self._generate_daily_buckets(start_time, end_time)

            # For now, use aggregated data
            # In production, this would query time-series data
            status = self._automation_controller.get_status()
            stats = status.get("stats", {})

            total = stats.get("total_healing_attempts", 0)
            successful = stats.get("successful_healings", 0)
            failed = stats.get("workflows_failed", 0) + stats.get(
                "workflows_escalated", 0
            )

            chart.labels = ["Success Rate"]
            chart.datasets = [
                {
                    "label": "Successful",
                    "data": [successful],
                    "backgroundColor": "#22c55e",
                },
                {
                    "label": "Failed",
                    "data": [failed],
                    "backgroundColor": "#ef4444",
                },
            ]

            chart.options = {
                "responsive": True,
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True},
                },
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Self-Healing Activity (Last {days} days)",
                    }
                },
            }

        except Exception as e:
            logger.error(f"Error generating healing success chart: {e}")

        return chart

    async def generate_severity_distribution_chart(self) -> ChartData:
        """Generate incident severity distribution chart.

        Returns:
            ChartData for pie chart
        """
        chart = ChartData(chart_type="pie")

        if self._incident_manager is None:
            return chart

        try:
            incidents = await self._incident_manager.list_incidents(limit=1000)

            severity_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
            for inc in incidents:
                sev = inc.severity.value
                if sev in severity_counts:
                    severity_counts[sev] += 1

            chart.labels = list(severity_counts.keys())
            chart.datasets = [
                {
                    "data": list(severity_counts.values()),
                    "backgroundColor": [
                        "#dc2626",  # P0 - red
                        "#ea580c",  # P1 - orange
                        "#ca8a04",  # P2 - yellow
                        "#3b82f6",  # P3 - blue
                    ],
                    "borderWidth": 0,
                }
            ]

            chart.options = {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Incident Severity Distribution",
                    },
                    "legend": {
                        "position": "bottom",
                    },
                },
            }

        except Exception as e:
            logger.error(f"Error generating severity chart: {e}")

        return chart

    async def generate_trend_analysis(
        self, metric: str, hours: int = 24
    ) -> dict[str, Any]:
        """Generate trend analysis for a metric.

        Args:
            metric: Metric name (incidents, healing, rollbacks)
            hours: Hours to analyze

        Returns:
            Trend analysis dictionary
        """
        analysis = {
            "metric": metric,
            "time_range_hours": hours,
            "trend": "stable",
            "change_percent": 0.0,
            "current_value": 0,
            "previous_value": 0,
        }

        try:
            if metric == "incidents" and self._incident_manager:
                # Compare current period vs previous period
                now = datetime.now(UTC)
                current_start = now - timedelta(hours=hours)
                previous_start = current_start - timedelta(hours=hours)

                current_incidents = await self._incident_manager.list_incidents(
                    limit=1000
                )
                current_count = sum(
                    1 for i in current_incidents if current_start <= i.created_at <= now
                )
                previous_count = sum(
                    1
                    for i in current_incidents
                    if previous_start <= i.created_at < current_start
                )

                analysis["current_value"] = current_count
                analysis["previous_value"] = previous_count

                if previous_count > 0:
                    change = ((current_count - previous_count) / previous_count) * 100
                    analysis["change_percent"] = round(change, 2)

                    if change > 10:
                        analysis["trend"] = "increasing"
                    elif change < -10:
                        analysis["trend"] = "decreasing"
                    else:
                        analysis["trend"] = "stable"

        except Exception as e:
            logger.error(f"Error generating trend analysis: {e}")

        return analysis

    async def _calculate_overall_health(self) -> float:
        """Calculate overall system health score.

        Returns:
            Health score (0-100)
        """
        scores = []

        # Circuit breaker health
        if self._cb_registry:
            try:
                states = self._cb_registry.get_all_states_dict()
                if states:
                    open_count = sum(
                        1 for s in states.values() if s.get("state") == "open"
                    )
                    cb_health = max(0, 100 - (open_count * 20))
                    scores.append(cb_health)
            except Exception:
                pass

        # Incident health
        if self._incident_manager:
            try:
                open_incidents = await self._incident_manager.list_incidents(
                    status="open", limit=100
                )
                p0_count = sum(1 for i in open_incidents if i.severity.value == "P0")
                p1_count = sum(1 for i in open_incidents if i.severity.value == "P1")
                incident_health = max(0, 100 - (p0_count * 30) - (p1_count * 10))
                scores.append(incident_health)
            except Exception:
                pass

        # Automation health
        if self._automation_controller:
            try:
                status = self._automation_controller.get_status()
                stats = status.get("stats", {})
                total = stats.get("total_healing_attempts", 0)
                if total > 0:
                    successful = stats.get("successful_healings", 0)
                    automation_health = (successful / total) * 100
                    scores.append(automation_health)
            except Exception:
                pass

        return sum(scores) / len(scores) if scores else 100.0

    def _generate_hourly_buckets(
        self, start: datetime, end: datetime
    ) -> list[datetime]:
        """Generate hourly time buckets."""
        buckets = []
        current = start.replace(minute=0, second=0, microsecond=0)
        while current <= end:
            buckets.append(current)
            current += timedelta(hours=1)
        return buckets

    def _generate_daily_buckets(self, start: datetime, end: datetime) -> list[datetime]:
        """Generate daily time buckets."""
        buckets = []
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end:
            buckets.append(current)
            current += timedelta(days=1)
        return buckets

    def _get_time_bucket(self, dt: datetime, resolution: str) -> datetime:
        """Get time bucket for a datetime."""
        if resolution == "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        else:
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    def _get_health_color(self, score: float) -> str:
        """Get color for health score."""
        if score >= 80:
            return "#22c55e"  # green
        elif score >= 60:
            return "#f59e0b"  # amber
        elif score >= 40:
            return "#ea580c"  # orange
        else:
            return "#ef4444"  # red
