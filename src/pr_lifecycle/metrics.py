"""PR Lifecycle Metrics - Metric definitions for PR pipeline monitoring.

This module provides:
- Metric definitions for Prometheus/Grafana
- Export functions for metrics collection
- Dashboard query helpers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PRMetric:
    """Base class for PR pipeline metrics."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    description: str = ""
    metric_type: str = "gauge"  # gauge, counter, histogram

    def to_prometheus(self) -> str:
        """Export as Prometheus format."""
        label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        if label_str:
            return f"{name}{{{label_str}}} {self.value}"
        return f"{self.name} {self.value}"

    def to_influxdb_line(self) -> str:
        """Export as InfluxDB line protocol."""
        tag_str = ",".join(f"{k}={v}" for k, v in self.labels.items())
        if tag_str:
            return f"{self.name},{tag_str} value={self.value}"
        return f"{self.name} value={self.value}"


@dataclass
class PRPipelineMetrics:
    """Complete set of PR pipeline metrics."""

    # Volume metrics
    total_prs: int = 0
    active_prs: int = 0
    merged_prs: int = 0
    rejected_prs: int = 0
    rolled_back_prs: int = 0

    # Success rates (0-100)
    auto_merge_success_rate: float = 0.0
    review_accuracy: float = 0.0
    overall_success_rate: float = 0.0

    # Time metrics (minutes)
    avg_time_to_merge: float = 0.0
    p50_time_to_merge: float = 0.0
    p95_time_to_merge: float = 0.0
    p99_time_to_merge: float = 0.0
    max_time_to_merge: float = 0.0

    # Auto-approval metrics
    auto_approved_count: int = 0
    auto_approved_rolled_back: int = 0
    auto_approved_success_rate: float = 0.0

    # Manual review metrics
    manual_review_count: int = 0
    manual_review_rolled_back: int = 0
    manual_review_success_rate: float = 0.0

    # State distribution
    prs_by_state: dict[str, int] = field(default_factory=dict)

    # Error metrics
    ci_failures: int = 0
    merge_conflicts: int = 0
    stuck_prs: int = 0
    escalated_prs: int = 0

    # Retry metrics
    total_retries: int = 0
    successful_retries: int = 0
    retry_success_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_prs": self.total_prs,
            "active_prs": self.active_prs,
            "merged_prs": self.merged_prs,
            "rejected_prs": self.rejected_prs,
            "rolled_back_prs": self.rolled_back_prs,
            "auto_merge_success_rate": self.auto_merge_success_rate,
            "review_accuracy": self.review_accuracy,
            "overall_success_rate": self.overall_success_rate,
            "avg_time_to_merge": self.avg_time_to_merge,
            "p50_time_to_merge": self.p50_time_to_merge,
            "p95_time_to_merge": self.p95_time_to_merge,
            "p99_time_to_merge": self.p99_time_to_merge,
            "max_time_to_merge": self.max_time_to_merge,
            "auto_approved_count": self.auto_approved_count,
            "auto_approved_rolled_back": self.auto_approved_rolled_back,
            "auto_approved_success_rate": self.auto_approved_success_rate,
            "manual_review_count": self.manual_review_count,
            "manual_review_rolled_back": self.manual_review_rolled_back,
            "manual_review_success_rate": self.manual_review_success_rate,
            "prs_by_state": self.prs_by_state,
            "ci_failures": self.ci_failures,
            "merge_conflicts": self.merge_conflicts,
            "stuck_prs": self.stuck_prs,
            "escalated_prs": self.escalated_prs,
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
            "retry_success_rate": self.retry_success_rate,
        }

    def to_prometheus_metrics(self) -> list[PRMetric]:
        """Convert to list of Prometheus metrics."""
        metrics = []

        # Volume metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_total_prs",
                value=self.total_prs,
                description="Total number of PRs",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_active_prs",
                value=self.active_prs,
                description="Number of active PRs",
                metric_type="gauge",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_merged_prs",
                value=self.merged_prs,
                description="Number of merged PRs",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_rejected_prs",
                value=self.rejected_prs,
                description="Number of rejected PRs",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_rolled_back_prs",
                value=self.rolled_back_prs,
                description="Number of rolled back PRs",
                metric_type="counter",
            )
        )

        # Success rate metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_auto_merge_success_rate",
                value=self.auto_merge_success_rate,
                description="Auto-merge success rate percentage",
                metric_type="gauge",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_review_accuracy",
                value=self.review_accuracy,
                description="Review accuracy percentage",
                metric_type="gauge",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_overall_success_rate",
                value=self.overall_success_rate,
                description="Overall success rate percentage",
                metric_type="gauge",
            )
        )

        # Time metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_avg_time_to_merge_minutes",
                value=self.avg_time_to_merge,
                description="Average time to merge in minutes",
                metric_type="gauge",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_p95_time_to_merge_minutes",
                value=self.p95_time_to_merge,
                description="P95 time to merge in minutes",
                metric_type="gauge",
            )
        )

        # Auto-approval metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_auto_approved_count",
                value=self.auto_approved_count,
                description="Number of auto-approved PRs",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_auto_approved_success_rate",
                value=self.auto_approved_success_rate,
                description="Auto-approval success rate percentage",
                metric_type="gauge",
            )
        )

        # Error metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_ci_failures",
                value=self.ci_failures,
                description="Number of CI failures",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_merge_conflicts",
                value=self.merge_conflicts,
                description="Number of merge conflicts",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_stuck_prs",
                value=self.stuck_prs,
                description="Number of stuck PRs",
                metric_type="gauge",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_escalated_prs",
                value=self.escalated_prs,
                description="Number of escalated PRs",
                metric_type="counter",
            )
        )

        # Retry metrics
        metrics.append(
            PRMetric(
                name="pr_pipeline_total_retries",
                value=self.total_retries,
                description="Total number of retries",
                metric_type="counter",
            )
        )
        metrics.append(
            PRMetric(
                name="pr_pipeline_retry_success_rate",
                value=self.retry_success_rate,
                description="Retry success rate percentage",
                metric_type="gauge",
            )
        )

        return metrics

    def to_prometheus_export(self) -> str:
        """Export all metrics as Prometheus exposition format."""
        lines = ["# PR Pipeline Metrics"]

        for metric in self.to_prometheus_metrics():
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {metric.metric_type}")
            lines.append(metric.to_prometheus())
            lines.append("")

        return "\n".join(lines)

    def to_influxdb_lines(self) -> list[str]:
        """Export all metrics as InfluxDB line protocol."""
        lines = []

        # Volume metrics
        lines.append(f"pr_pipeline_volume,metric=total value={self.total_prs}i")
        lines.append(f"pr_pipeline_volume,metric=active value={self.active_prs}i")
        lines.append(f"pr_pipeline_volume,metric=merged value={self.merged_prs}i")
        lines.append(f"pr_pipeline_volume,metric=rejected value={self.rejected_prs}i")
        lines.append(
            f"pr_pipeline_volume,metric=rolled_back value={self.rolled_back_prs}i"
        )

        # Success rates
        lines.append(
            f"pr_pipeline_success,metric=auto_merge value={self.auto_merge_success_rate}"
        )
        lines.append(
            f"pr_pipeline_success,metric=review_accuracy value={self.review_accuracy}"
        )
        lines.append(
            f"pr_pipeline_success,metric=overall value={self.overall_success_rate}"
        )

        # Time metrics
        lines.append(f"pr_pipeline_time,metric=avg value={self.avg_time_to_merge}")
        lines.append(f"pr_pipeline_time,metric=p50 value={self.p50_time_to_merge}")
        lines.append(f"pr_pipeline_time,metric=p95 value={self.p95_time_to_merge}")
        lines.append(f"pr_pipeline_time,metric=p99 value={self.p99_time_to_merge}")

        # Auto-approval
        lines.append(
            f"pr_pipeline_auto_approval,metric=count value={self.auto_approved_count}i"
        )
        lines.append(
            f"pr_pipeline_auto_approval,metric=success_rate value={self.auto_approved_success_rate}"
        )

        # Errors
        lines.append(f"pr_pipeline_errors,metric=ci_failures value={self.ci_failures}i")
        lines.append(
            f"pr_pipeline_errors,metric=merge_conflicts value={self.merge_conflicts}i"
        )
        lines.append(f"pr_pipeline_errors,metric=stuck value={self.stuck_prs}i")
        lines.append(f"pr_pipeline_errors,metric=escalated value={self.escalated_prs}i")

        # Retries
        lines.append(f"pr_pipeline_retries,metric=total value={self.total_retries}i")
        lines.append(
            f"pr_pipeline_retries,metric=success_rate value={self.retry_success_rate}"
        )

        return lines


class MetricsExporter:
    """Helper class for exporting metrics to various backends."""

    @staticmethod
    def export_prometheus_format(metrics: PRPipelineMetrics) -> str:
        """Export metrics in Prometheus exposition format."""
        return metrics.to_prometheus_export()

    @staticmethod
    def export_influxdb_format(metrics: PRPipelineMetrics) -> str:
        """Export metrics in InfluxDB line protocol format."""
        return "\n".join(metrics.to_influxdb_lines())

    @staticmethod
    def export_json(metrics: PRPipelineMetrics) -> dict[str, Any]:
        """Export metrics as JSON."""
        return metrics.to_dict()


# Grafana dashboard query helpers
GRAFANA_QUERIES = {
    "total_prs": 'SELECT sum("value") FROM "pr_pipeline_volume" WHERE "metric" = \'total\' AND $timeFilter',
    "merged_prs": 'SELECT sum("value") FROM "pr_pipeline_volume" WHERE "metric" = \'merged\' AND $timeFilter',
    "success_rate": 'SELECT mean("value") FROM "pr_pipeline_success" WHERE "metric" = \'overall\' AND $timeFilter',
    "auto_merge_success_rate": 'SELECT mean("value") FROM "pr_pipeline_success" WHERE "metric" = \'auto_merge\' AND $timeFilter',
    "avg_time_to_merge": 'SELECT mean("value") FROM "pr_pipeline_time" WHERE "metric" = \'avg\' AND $timeFilter',
    "p95_time_to_merge": 'SELECT mean("value") FROM "pr_pipeline_time" WHERE "metric" = \'p95\' AND $timeFilter',
    "rolled_back_prs": 'SELECT sum("value") FROM "pr_pipeline_volume" WHERE "metric" = \'rolled_back\' AND $timeFilter',
    "ci_failures": 'SELECT sum("value") FROM "pr_pipeline_errors" WHERE "metric" = \'ci_failures\' AND $timeFilter',
    "active_prs": 'SELECT last("value") FROM "pr_pipeline_volume" WHERE "metric" = \'active\' AND $timeFilter',
}


def get_grafana_query(metric_name: str) -> str:
    """Get Grafana query for a specific metric."""
    return GRAFANA_QUERIES.get(metric_name, "")


def get_all_grafana_queries() -> dict[str, str]:
    """Get all Grafana queries."""
    return GRAFANA_QUERIES.copy()
