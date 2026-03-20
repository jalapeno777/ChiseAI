"""Benchmark comparison and regression detection for ML evaluation.

Provides tools for comparing model performance against benchmarks and detecting
performance regressions across model versions.

Acceptance Criteria:
- Benchmark comparison with statistical significance
- Regression detection with configurable thresholds
- Evaluation reporting with structured output

Example:
>>> from ml.evaluation.reporting import (
...     compare_to_benchmark,
...     detect_regression,
...     RegressionThresholds,
... )
>>> baseline = {"accuracy": 0.95, "f1": 0.92}
>>> current = {"accuracy": 0.93, "f1": 0.91}
>>> comparison = compare_to_benchmark(current, baseline)
>>> print(f"Regressions: {len(comparison.regressions)}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class RegressionSeverity(Enum):
    """Severity levels for performance regressions."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RegressionThresholds:
    """Thresholds for detecting performance regressions.

    Attributes:
        low_threshold: 2% drop threshold (default 0.02)
        medium_threshold: 5% drop threshold (default 0.05)
        high_threshold: 10% drop threshold (default 0.10)
        critical_threshold: 20% drop threshold (default 0.20)
    """

    low_threshold: float = 0.02
    medium_threshold: float = 0.05
    high_threshold: float = 0.10
    critical_threshold: float = 0.20


@dataclass(frozen=True)
class RegressionResult:
    """Result of a regression detection for a single metric.

    Attributes:
        metric_name: Name of the metric
        baseline_value: Baseline metric value
        current_value: Current metric value
        delta: Absolute change (current - baseline)
        delta_pct: Percentage change
        severity: Regression severity level
        is_regression: Whether this is a regression
    """

    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    delta_pct: float
    severity: RegressionSeverity
    is_regression: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
            "severity": self.severity.value,
            "is_regression": self.is_regression,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegressionResult:
        """Create from dictionary."""
        return cls(
            metric_name=data["metric_name"],
            baseline_value=data["baseline_value"],
            current_value=data["current_value"],
            delta=data["delta"],
            delta_pct=data["delta_pct"],
            severity=RegressionSeverity(data["severity"]),
            is_regression=data["is_regression"],
        )


@dataclass(frozen=True)
class BenchmarkComparison:
    """Comparison between current and baseline model metrics.

    Attributes:
        model_id: Identifier for the model being evaluated
        baseline_metrics: Baseline metric values
        current_metrics: Current metric values
        regressions: List of detected regressions
        overall_severity: Highest severity among all regressions
        timestamp: When the comparison was made
    """

    model_id: str
    baseline_metrics: dict[str, float]
    current_metrics: dict[str, float]
    regressions: list[RegressionResult]
    overall_severity: RegressionSeverity
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "baseline_metrics": self.baseline_metrics,
            "current_metrics": self.current_metrics,
            "regressions": [r.to_dict() for r in self.regressions],
            "overall_severity": self.overall_severity.value,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkComparison:
        """Create from dictionary."""
        return cls(
            model_id=data["model_id"],
            baseline_metrics=data["baseline_metrics"],
            current_metrics=data["current_metrics"],
            regressions=[RegressionResult.from_dict(r) for r in data["regressions"]],
            overall_severity=RegressionSeverity(data["overall_severity"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


def detect_regression(
    baseline: float,
    current: float,
    metric_name: str,
    thresholds: RegressionThresholds,
    higher_is_better: bool = True,
) -> RegressionResult:
    """Detect regression between baseline and current metric values.

    Args:
        baseline: Baseline metric value
        current: Current metric value
        metric_name: Name of the metric
        thresholds: Regression thresholds to use
        higher_is_better: Whether higher values are better for this metric

    Returns:
        RegressionResult with detection details
    """
    delta = current - baseline

    # Calculate percentage change, handle division by zero
    if baseline == 0:
        delta_pct = 0.0 if current == 0 else (1.0 if current > 0 else -1.0)
    else:
        delta_pct = delta / abs(baseline)

    # Determine if this is a regression based on direction
    if higher_is_better:
        # For metrics where higher is better, a drop is a regression
        is_regression = delta < 0
        # Use negative delta_pct for severity (more negative = worse)
        severity_delta = -delta_pct
    else:
        # For metrics where lower is better (like loss), an increase is regression
        is_regression = delta > 0
        severity_delta = delta_pct

    # Determine severity based on absolute percentage change
    abs_delta_pct = abs(severity_delta)

    if abs_delta_pct >= thresholds.critical_threshold:
        severity = RegressionSeverity.CRITICAL
    elif abs_delta_pct >= thresholds.high_threshold:
        severity = RegressionSeverity.HIGH
    elif abs_delta_pct >= thresholds.medium_threshold:
        severity = RegressionSeverity.MEDIUM
    elif abs_delta_pct >= thresholds.low_threshold:
        severity = RegressionSeverity.LOW
    else:
        severity = RegressionSeverity.NONE
        is_regression = False

    return RegressionResult(
        metric_name=metric_name,
        baseline_value=baseline,
        current_value=current,
        delta=delta,
        delta_pct=delta_pct,
        severity=severity,
        is_regression=is_regression,
    )


def compare_to_benchmark(
    current_metrics: dict[str, float],
    baseline_metrics: dict[str, float],
    thresholds: RegressionThresholds | None = None,
    model_id: str = "current",
) -> BenchmarkComparison:
    """Compare current metrics against baseline benchmark.

    Args:
        current_metrics: Current model metrics
        baseline_metrics: Baseline/benchmark metrics
        thresholds: Regression thresholds (uses defaults if None)
        model_id: Identifier for the model

    Returns:
        BenchmarkComparison with all regression results
    """
    if thresholds is None:
        thresholds = RegressionThresholds()

    regressions: list[RegressionResult] = []
    all_severities: list[RegressionSeverity] = [RegressionSeverity.NONE]

    # Compare all metrics in baseline
    for metric_name, baseline_value in baseline_metrics.items():
        current_value = current_metrics.get(metric_name, baseline_value)

        # Determine if higher is better based on common metric conventions
        higher_is_better = _is_higher_better(metric_name)

        result = detect_regression(
            baseline=baseline_value,
            current=current_value,
            metric_name=metric_name,
            thresholds=thresholds,
            higher_is_better=higher_is_better,
        )

        regressions.append(result)

        if result.is_regression:
            all_severities.append(result.severity)

    # Determine overall severity (highest severity among regressions)
    overall_severity = max(all_severities, key=lambda s: s.value)

    return BenchmarkComparison(
        model_id=model_id,
        baseline_metrics=baseline_metrics,
        current_metrics=current_metrics,
        regressions=regressions,
        overall_severity=overall_severity,
    )


def generate_comparison_report(comparison: BenchmarkComparison) -> str:
    """Generate a human-readable comparison report.

    Args:
        comparison: The benchmark comparison to report

    Returns:
        Human-readable report string
    """
    lines = [
        f"Benchmark Comparison Report",
        f"=" * 50,
        f"Model: {comparison.model_id}",
        f"Timestamp: {comparison.timestamp.isoformat()}",
        f"Overall Severity: {comparison.overall_severity.value.upper()}",
        f"",
        f"Regressions Detected: {len([r for r in comparison.regressions if r.is_regression])}",
        f"",
    ]

    # Add regression details
    regression_list = [r for r in comparison.regressions if r.is_regression]

    if regression_list:
        lines.append("Regression Details:")
        lines.append("-" * 50)
        for r in regression_list:
            lines.append(
                f"  {r.metric_name}: {r.baseline_value:.4f} -> {r.current_value:.4f} "
                f"({r.delta_pct:+.2%}, {r.severity.value})"
            )
    else:
        lines.append("No regressions detected.")

    # Add summary of all metrics
    lines.append("")
    lines.append("Metric Summary:")
    lines.append("-" * 50)
    for r in comparison.regressions:
        status = "REGRESSION" if r.is_regression else "OK"
        lines.append(
            f"  {r.metric_name}: {r.current_value:.4f} "
            f"(baseline: {r.baseline_value:.4f}, {status})"
        )

    return "\n".join(lines)


def detect_regressions_across_versions(
    version_metrics: list[dict[str, float]],
    thresholds: RegressionThresholds | None = None,
) -> list[RegressionResult]:
    """Detect regressions across a chain of model versions.

    Compares each version to its predecessor and returns all detected regressions.

    Args:
        version_metrics: List of metric dictionaries, one per version
                        (oldest first)
        thresholds: Regression thresholds (uses defaults if None)

    Returns:
        List of all regression results across version transitions
    """
    if thresholds is None:
        thresholds = RegressionThresholds()

    if len(version_metrics) < 2:
        return []

    all_regressions: list[RegressionResult] = []

    # Compare each version to its predecessor
    for i in range(1, len(version_metrics)):
        baseline = version_metrics[i - 1]
        current = version_metrics[i]

        # Compare all metrics
        for metric_name, baseline_value in baseline.items():
            current_value = current.get(metric_name, baseline_value)
            higher_is_better = _is_higher_better(metric_name)

            result = detect_regression(
                baseline=baseline_value,
                current=current_value,
                metric_name=metric_name,
                thresholds=thresholds,
                higher_is_better=higher_is_better,
            )

            if result.is_regression:
                all_regressions.append(result)

    return all_regressions


def _is_higher_better(metric_name: str) -> bool:
    """Determine if higher values are better for a given metric.

    Args:
        metric_name: Name of the metric

    Returns:
        True if higher values are better, False otherwise
    """
    # Metrics where lower is better
    lower_is_better = {
        "log_loss",
        "calibration_error",
        "brier_score",
        "max_drawdown",
        "mae",
        "mse",
        "rmse",
        "loss",
    }

    return metric_name.lower() not in lower_is_better
