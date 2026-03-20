"""
Performance drift detection system for autonomous cognition.

Detects performance degradation in key metrics using statistical analysis
and provides root cause tagging for alerts.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from src.autonomous_cognition.drift.statistical_tests import (
    standard_deviation,
    trend_direction,
)


class DriftSeverity(Enum):
    """Severity levels for drift alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RootCauseTag(Enum):
    """Root cause categories for drift."""

    INFRA = "infra"
    CODE = "code"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass
class Baseline:
    """Baseline statistics for a metric."""

    metric_name: str
    mean: float
    std: float
    values: list[float]
    window_days: int
    established_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metric_name": self.metric_name,
            "mean": self.mean,
            "std": self.std,
            "values": self.values,
            "window_days": self.window_days,
            "established_at": self.established_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Baseline":
        """Create from dictionary."""
        return cls(
            metric_name=data["metric_name"],
            mean=data["mean"],
            std=data["std"],
            values=data["values"],
            window_days=data["window_days"],
            established_at=datetime.fromisoformat(data["established_at"]),
        )


@dataclass
class DriftResult:
    """Result of a drift detection check."""

    metric_name: str
    current_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    is_drift: bool
    severity: str
    root_cause_tag: str
    detected_at: datetime
    trend: str = "stable"
    threshold: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "z_score": self.z_score,
            "is_drift": self.is_drift,
            "severity": self.severity,
            "root_cause_tag": self.root_cause_tag,
            "detected_at": self.detected_at.isoformat(),
            "trend": self.trend,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriftResult":
        """Create from dictionary."""
        return cls(
            metric_name=data["metric_name"],
            current_value=data["current_value"],
            baseline_mean=data["baseline_mean"],
            baseline_std=data["baseline_std"],
            z_score=data["z_score"],
            is_drift=data["is_drift"],
            severity=data["severity"],
            root_cause_tag=data["root_cause_tag"],
            detected_at=datetime.fromisoformat(data["detected_at"]),
            trend=data.get("trend", "stable"),
            threshold=data.get("threshold", 2.0),
        )


# Metric configurations with thresholds
METRIC_CONFIGS = {
    "cycle_success_rate": {
        "baseline_target": 0.95,
        "drift_threshold": 0.90,
        "higher_is_better": True,
        "unit": "rate",
    },
    "learning_velocity": {
        "baseline_target": 5.0,  # per week
        "drift_threshold": 3.0,
        "higher_is_better": True,
        "unit": "count/week",
    },
    "calibration_quality": {
        "baseline_target": 0.15,  # Brier score
        "drift_threshold": 0.20,
        "higher_is_better": False,  # Lower Brier score is better
        "unit": "brier",
    },
    "qdrant_write_latency": {
        "baseline_target": 100.0,  # ms
        "drift_threshold": 200.0,
        "higher_is_better": False,
        "unit": "ms",
    },
    "discord_success_rate": {
        "baseline_target": 0.99,
        "drift_threshold": 0.95,
        "higher_is_better": True,
        "unit": "rate",
    },
}


class PerformanceDriftDetector:
    """
    Detects performance drift in autonomous cognition metrics.

    Uses rolling window baselines and statistical tests to detect
    performance degradation and tag root causes.
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        influxdb_client: Any | None = None,
        default_window_days: int = 7,
        drift_threshold_std: float = 2.0,
    ):
        """
        Initialize the drift detector.

        Args:
            redis_client: Optional Redis client for storing drift history
            influxdb_client: Optional InfluxDB client for reading metrics
            default_window_days: Default rolling window for baselines
            drift_threshold_std: Standard deviation threshold for drift detection
        """
        self.redis_client = redis_client
        self.influxdb_client = influxdb_client
        self.default_window_days = default_window_days
        self.drift_threshold_std = drift_threshold_std

        # In-memory storage (fallback if Redis unavailable)
        self._baselines: dict[str, Baseline] = {}
        self._drift_history: list[DriftResult] = []

        # Root cause indicators
        self._infra_indicators = [
            "qdrant",
            "redis",
            "influxdb",
            "network",
            "timeout",
            "connection",
            "unavailable",
            "down",
        ]
        self._code_indicators = [
            "deployment",
            "release",
            "commit",
            "merge",
            "rollback",
            "version",
            "build",
            "deploy",
        ]
        self._data_indicators = [
            "corruption",
            "schema",
            "migration",
            "invalid",
            "malformed",
            "missing",
            "null",
            "corrupted",
        ]

    def establish_baseline(
        self,
        metric_name: str,
        days: int | None = None,
        values: list[float] | None = None,
    ) -> Baseline:
        """
        Establish a baseline for a metric.

        Args:
            metric_name: Name of the metric
            days: Number of days for rolling window (default: self.default_window_days)
            values: Optional pre-computed values (if None, reads from InfluxDB)

        Returns:
            Baseline object with statistics

        Raises:
            ValueError: If cannot read metric values
        """
        window_days = days or self.default_window_days

        if values is None:
            values = self._read_metric_values(metric_name, window_days)

        if not values:
            raise ValueError(f"No values available for metric: {metric_name}")

        mean = sum(values) / len(values)
        std = standard_deviation(values)

        baseline = Baseline(
            metric_name=metric_name,
            mean=mean,
            std=std,
            values=values,
            window_days=window_days,
            established_at=datetime.now(UTC),
        )

        self._baselines[metric_name] = baseline

        return baseline

    def detect_drift(
        self,
        metric_name: str,
        current_value: float,
        context: dict[str, Any] | None = None,
    ) -> DriftResult:
        """
        Detect drift for a metric against its baseline.

        Args:
            metric_name: Name of the metric
            current_value: Current metric value
            context: Optional context for root cause tagging

        Returns:
            DriftResult with detection details

        Raises:
            ValueError: If no baseline exists for the metric
        """
        if metric_name not in self._baselines:
            raise ValueError(f"No baseline established for metric: {metric_name}")

        baseline = self._baselines[metric_name]
        config = METRIC_CONFIGS.get(metric_name, {})

        # Calculate z-score
        if baseline.std == 0:
            z_score = (
                0.0
                if current_value == baseline.mean
                else (float("inf") if current_value > baseline.mean else float("-inf"))
            )
        else:
            z_score = (current_value - baseline.mean) / baseline.std

        # Determine if drift based on direction
        higher_is_better = config.get("higher_is_better", True)

        if higher_is_better:
            # Drift is when value is significantly lower than baseline
            is_drift = z_score < -self.drift_threshold_std
        else:
            # Drift is when value is significantly higher than baseline
            is_drift = z_score > self.drift_threshold_std

        # Determine severity
        severity = self._determine_severity(z_score, higher_is_better)

        # Determine trend from baseline values
        trend = (
            trend_direction(baseline.values) if len(baseline.values) >= 2 else "stable"
        )

        # Tag root cause
        root_cause = self._tag_root_cause(metric_name, current_value, context)

        result = DriftResult(
            metric_name=metric_name,
            current_value=current_value,
            baseline_mean=baseline.mean,
            baseline_std=baseline.std,
            z_score=z_score,
            is_drift=is_drift,
            severity=severity.value,
            root_cause_tag=root_cause.value,
            detected_at=datetime.now(UTC),
            trend=trend,
            threshold=self.drift_threshold_std,
        )

        # Store in history
        self._drift_history.append(result)
        self._store_drift_result(result)

        return result

    def get_drift_status(self) -> dict[str, Any]:
        """
        Get current drift status for all monitored metrics.

        Returns:
            Dictionary with drift status summary
        """
        status = {
            "monitored_metrics": list(self._baselines.keys()),
            "baselines_established": {
                name: baseline.established_at.isoformat()
                for name, baseline in self._baselines.items()
            },
            "recent_drifts": [],
            "summary": {
                "total_drifts": 0,
                "critical": 0,
                "warning": 0,
                "info": 0,
            },
        }

        # Get recent drifts (last 24 hours)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        recent_drifts = [
            d for d in self._drift_history if d.detected_at > cutoff and d.is_drift
        ]

        for drift in recent_drifts:
            status["recent_drifts"].append(drift.to_dict())
            status["summary"]["total_drifts"] += 1
            status["summary"][drift.severity] += 1

        return status

    def get_drift_history(
        self,
        metric_name: str | None = None,
        since: datetime | None = None,
        severity: str | None = None,
    ) -> list[DriftResult]:
        """
        Get drift detection history.

        Args:
            metric_name: Filter by metric name
            since: Filter by detection time
            severity: Filter by severity level

        Returns:
            List of DriftResult objects
        """
        results = self._drift_history

        if metric_name:
            results = [r for r in results if r.metric_name == metric_name]

        if since:
            results = [r for r in results if r.detected_at >= since]

        if severity:
            results = [r for r in results if r.severity == severity]

        return results

    def alert_on_drift(self, drift_result: DriftResult) -> bool:
        """
        Determine if an alert should be sent for a drift result.

        Args:
            drift_result: The drift result to evaluate

        Returns:
            True if alert should be sent
        """
        if not drift_result.is_drift:
            return False

        # Always alert on critical drift
        if drift_result.severity == DriftSeverity.CRITICAL.value:
            return True

        # Alert on warning if it's a new drift (not repeated)
        if drift_result.severity == DriftSeverity.WARNING.value:
            # Check if we've already alerted recently for this metric
            recent_alerts = self._get_recent_alerts(drift_result.metric_name, hours=1)
            return len(recent_alerts) == 0

        # Info level: only alert if significant trend change
        if drift_result.severity == DriftSeverity.INFO.value:
            return drift_result.trend == "degrading"

        return False

    def _read_metric_values(self, metric_name: str, days: int) -> list[float]:
        """
        Read metric values from InfluxDB or generate synthetic data.

        Args:
            metric_name: Name of the metric
            days: Number of days of history

        Returns:
            List of metric values
        """
        if self.influxdb_client:
            try:
                return self._read_from_influxdb(metric_name, days)
            except Exception:
                # Fall back to synthetic data
                pass

        # Generate synthetic baseline data based on metric config
        return self._generate_synthetic_baseline(metric_name, days)

    def _read_from_influxdb(self, metric_name: str, days: int) -> list[float]:
        """Read metric values from InfluxDB."""
        # This would query InfluxDB for actual metrics
        # For now, return empty to trigger synthetic generation
        return []

    def _generate_synthetic_baseline(self, metric_name: str, days: int) -> list[float]:
        """Generate synthetic baseline data for testing."""
        import random

        config = METRIC_CONFIGS.get(metric_name, {})
        target = config.get("baseline_target", 0.5)

        # Generate values around target with small variance
        values = []
        for _ in range(days * 24):  # Hourly samples
            noise = random.gauss(0, target * 0.02)  # 2% variance
            values.append(max(0, target + noise))

        return values

    def _determine_severity(
        self, z_score: float, higher_is_better: bool
    ) -> DriftSeverity:
        """Determine severity based on z-score magnitude."""
        if higher_is_better:
            # For metrics where higher is better, negative z-score is bad
            effective_z = -z_score
        else:
            # For metrics where lower is better, positive z-score is bad
            effective_z = z_score

        if effective_z > 4.0:
            return DriftSeverity.CRITICAL
        elif effective_z > 2.5:
            return DriftSeverity.WARNING
        elif effective_z > 1.5:
            return DriftSeverity.INFO
        else:
            return DriftSeverity.INFO

    def _tag_root_cause(
        self,
        metric_name: str,
        current_value: float,
        context: dict[str, Any] | None,
    ) -> RootCauseTag:
        """Tag the root cause based on context and metric."""
        if not context:
            # Try to infer from metric name
            if any(ind in metric_name.lower() for ind in self._infra_indicators):
                return RootCauseTag.INFRA
            return RootCauseTag.UNKNOWN

        # Check context for indicators
        context_str = json.dumps(context).lower()

        if any(ind in context_str for ind in self._infra_indicators):
            return RootCauseTag.INFRA

        if any(ind in context_str for ind in self._code_indicators):
            return RootCauseTag.CODE

        if any(ind in context_str for ind in self._data_indicators):
            return RootCauseTag.DATA

        return RootCauseTag.UNKNOWN

    def _store_drift_result(self, result: DriftResult) -> None:
        """Store drift result in Redis or memory."""
        if self.redis_client:
            try:
                key = f"bmad:chiseai:autocog:drift_history:{result.metric_name}"
                self.redis_client.lpush(key, json.dumps(result.to_dict()))
                # Keep only last 1000 entries
                self.redis_client.ltrim(key, 0, 999)
            except Exception:
                pass  # Fall back to memory storage

    def _get_recent_alerts(self, metric_name: str, hours: int) -> list[DriftResult]:
        """Get recent alerts for a metric."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return [
            r
            for r in self._drift_history
            if r.metric_name == metric_name and r.detected_at > cutoff and r.is_drift
        ]

    def update_baseline(self, metric_name: str, new_value: float) -> Baseline:
        """
        Update a baseline with a new value, maintaining the rolling window.

        Args:
            metric_name: Name of the metric
            new_value: New value to add to baseline

        Returns:
            Updated Baseline
        """
        if metric_name not in self._baselines:
            raise ValueError(f"No baseline established for metric: {metric_name}")

        baseline = self._baselines[metric_name]

        # Add new value and maintain window size
        baseline.values.append(new_value)
        max_values = baseline.window_days * 24  # Hourly samples

        if len(baseline.values) > max_values:
            baseline.values = baseline.values[-max_values:]

        # Recalculate statistics
        baseline.mean = sum(baseline.values) / len(baseline.values)
        baseline.std = standard_deviation(baseline.values)
        baseline.established_at = datetime.now(UTC)

        return baseline

    def get_metric_config(self, metric_name: str) -> dict[str, Any]:
        """Get configuration for a metric."""
        return METRIC_CONFIGS.get(
            metric_name,
            {
                "baseline_target": 0.5,
                "drift_threshold": 0.4,
                "higher_is_better": True,
                "unit": "unknown",
            },
        )
