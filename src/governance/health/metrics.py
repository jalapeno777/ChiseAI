"""
Health Metrics Exporter - Prometheus/Grafana Integration (ST-GOV-008).

Provides metrics export for:
- Per-agent health scores
- Aggregated swarm health
- Alert counts by severity
- Remediation success rates
- Prediction accuracy

Integration with existing governance metrics system.

Story: ST-GOV-008
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class HealthMetricPoint:
    """A single health metric data point."""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    help_text: str = ""


class HealthMetrics:
    """
    Metrics exporter for health sentinel data.

    Exports metrics in Prometheus format for Grafana dashboards.
    Integrates with existing governance metrics infrastructure.
    """

    # Metric names following Prometheus naming conventions
    METRIC_AGENT_HEALTH = "chiseai_health_agent_score"
    METRIC_SWARM_HEALTH = "chiseai_health_swarm_score"
    METRIC_ALERTS_TOTAL = "chiseai_health_alerts_total"
    METRIC_REMEDIATION_TOTAL = "chiseai_health_remediation_total"
    METRIC_REMEDIATION_SUCCESS = "chiseai_health_remediation_success"
    METRIC_PREDICTION_ACCURACY = "chiseai_health_prediction_accuracy"
    METRIC_UPDATE_LATENCY = "chiseai_health_update_latency_seconds"

    def __init__(self, namespace: str = "chiseai"):
        """Initialize health metrics exporter."""
        self.namespace = namespace
        self._metrics_buffer: list[HealthMetricPoint] = []
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}

        # Initialize counters
        self._counters[self.METRIC_ALERTS_TOTAL] = 0.0
        self._counters[self.METRIC_REMEDIATION_TOTAL] = 0.0
        self._counters[self.METRIC_REMEDIATION_SUCCESS] = 0.0

    def record_agent_health(
        self,
        agent_id: str,
        score: float,
        dimensions: Optional[dict[str, float]] = None,
    ) -> None:
        """
        Record per-agent health score.

        Args:
            agent_id: Agent identifier
            score: Overall health score (0-100)
            dimensions: Optional dimension scores (performance, quality, etc.)
        """
        labels = {"agent_id": agent_id}
        self._gauges[f"{self.METRIC_AGENT_HEALTH}_{agent_id}"] = score

        self._metrics_buffer.append(
            HealthMetricPoint(
                name=self.METRIC_AGENT_HEALTH,
                value=score,
                timestamp=datetime.utcnow(),
                labels=labels,
                help_text="Per-agent health score (0-100)",
            )
        )

        # Record dimension scores
        if dimensions:
            for dim_name, dim_score in dimensions.items():
                dim_labels = {**labels, "dimension": dim_name}
                self._metrics_buffer.append(
                    HealthMetricPoint(
                        name=f"{self.METRIC_AGENT_HEALTH}_dimension",
                        value=dim_score,
                        timestamp=datetime.utcnow(),
                        labels=dim_labels,
                        help_text=f"Health dimension score for {dim_name}",
                    )
                )

    def record_swarm_health(
        self,
        score: float,
        agent_count: int,
        healthy_count: int,
    ) -> None:
        """
        Record aggregated swarm health score.

        Args:
            score: Aggregated swarm health score (0-100)
            agent_count: Total number of agents
            healthy_count: Number of healthy agents (score >= 70)
        """
        self._gauges[self.METRIC_SWARM_HEALTH] = score

        self._metrics_buffer.append(
            HealthMetricPoint(
                name=self.METRIC_SWARM_HEALTH,
                value=score,
                timestamp=datetime.utcnow(),
                labels={
                    "agent_count": str(agent_count),
                    "healthy_count": str(healthy_count),
                },
                help_text="Aggregated swarm health score (0-100)",
            )
        )

    def record_alert(
        self,
        severity: str,
        alert_type: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Record an alert event.

        Args:
            severity: Alert severity (critical, warning, info)
            alert_type: Type of alert (degradation, prediction, etc.)
            agent_id: Optional affected agent
        """
        self._counters[self.METRIC_ALERTS_TOTAL] += 1

        labels = {"severity": severity, "alert_type": alert_type}
        if agent_id:
            labels["agent_id"] = agent_id

        self._metrics_buffer.append(
            HealthMetricPoint(
                name=self.METRIC_ALERTS_TOTAL,
                value=1.0,
                timestamp=datetime.utcnow(),
                labels=labels,
                help_text="Total number of health alerts",
            )
        )

    def record_remediation(
        self,
        success: bool,
        action_type: str,
        agent_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """
        Record a remediation attempt.

        Args:
            success: Whether remediation succeeded
            action_type: Type of remediation action
            agent_id: Optional affected agent
            duration_ms: Time taken for remediation
        """
        self._counters[self.METRIC_REMEDIATION_TOTAL] += 1
        if success:
            self._counters[self.METRIC_REMEDIATION_SUCCESS] += 1

        labels = {
            "success": str(success).lower(),
            "action_type": action_type,
        }
        if agent_id:
            labels["agent_id"] = agent_id

        self._metrics_buffer.append(
            HealthMetricPoint(
                name=self.METRIC_REMEDIATION_TOTAL,
                value=1.0,
                timestamp=datetime.utcnow(),
                labels=labels,
                help_text="Total remediation attempts",
            )
        )

        if duration_ms is not None:
            self._record_latency(duration_ms / 1000.0)

    def record_prediction_accuracy(
        self,
        accuracy: float,
        prediction_horizon_minutes: int = 15,
    ) -> None:
        """
        Record prediction accuracy metric.

        Args:
            accuracy: Accuracy percentage (0-100)
            prediction_horizon_minutes: Prediction horizon in minutes
        """
        self._gauges[self.METRIC_PREDICTION_ACCURACY] = accuracy

        self._metrics_buffer.append(
            HealthMetricPoint(
                name=self.METRIC_PREDICTION_ACCURACY,
                value=accuracy,
                timestamp=datetime.utcnow(),
                labels={"horizon_minutes": str(prediction_horizon_minutes)},
                help_text="Health prediction accuracy percentage",
            )
        )

    def _record_latency(self, latency_seconds: float) -> None:
        """Record update latency."""
        if self.METRIC_UPDATE_LATENCY not in self._histograms:
            self._histograms[self.METRIC_UPDATE_LATENCY] = []
        self._histograms[self.METRIC_UPDATE_LATENCY].append(latency_seconds)

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        # Export counters
        for metric_name, value in self._counters.items():
            lines.append(f"# HELP {metric_name} Total count")
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {value}")

        # Export gauges
        for metric_key, value in self._gauges.items():
            metric_name = metric_key.split("_agent")[0].split("_swarm")[0]
            if "agent" in metric_key and "_dimension" not in metric_key:
                agent_id = metric_key.split("_")[-1]
                lines.append(
                    f'{self.METRIC_AGENT_HEALTH}{{agent_id="{agent_id}"}} {value}'
                )
            elif "dimension" in metric_key:
                continue  # Handled separately
            else:
                lines.append(f"{metric_name} {value}")

        # Export histograms
        for metric_name, values in self._histograms.items():
            if values:
                lines.append(f"# HELP {metric_name} Latency histogram")
                lines.append(f"# TYPE {metric_name} histogram")
                avg = sum(values) / len(values)
                lines.append(f"{metric_name}_avg {avg:.6f}")

        return "\n".join(lines)

    def get_metrics_summary(self) -> dict:
        """
        Get a summary of current metrics.

        Returns:
            Dictionary with metric summaries
        """
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "buffer_size": len(self._metrics_buffer),
            "histogram_counts": {k: len(v) for k, v in self._histograms.items()},
        }

    def flush_buffer(self) -> list[HealthMetricPoint]:
        """
        Flush and return the metrics buffer.

        Returns:
            List of metric points from buffer
        """
        buffer = self._metrics_buffer.copy()
        self._metrics_buffer.clear()
        return buffer

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics_buffer.clear()
        self._counters = {
            self.METRIC_ALERTS_TOTAL: 0.0,
            self.METRIC_REMEDIATION_TOTAL: 0.0,
            self.METRIC_REMEDIATION_SUCCESS: 0.0,
        }
        self._gauges.clear()
        self._histograms.clear()


# Singleton instance for convenience
_metrics_instance: Optional[HealthMetrics] = None


def get_health_metrics() -> HealthMetrics:
    """Get or create the singleton HealthMetrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = HealthMetrics()
    return _metrics_instance
