"""
Performance drift detection for autonomous cognition.

This module provides statistical detection of performance degradation
in key metrics with root cause tagging and alerting.
"""

from src.autonomous_cognition.drift.performance_drift import (
    PerformanceDriftDetector,
    Baseline,
    DriftResult,
    DriftSeverity,
    RootCauseTag,
    METRIC_CONFIGS,
)

from src.autonomous_cognition.drift.statistical_tests import (
    z_score_test,
    moving_average,
    standard_deviation,
    detect_anomaly,
    trend_direction,
    calculate_brier_score,
    calculate_percentile,
    detect_sequential_anomaly,
)

__all__ = [
    # Main detector
    "PerformanceDriftDetector",
    "Baseline",
    "DriftResult",
    "DriftSeverity",
    "RootCauseTag",
    "METRIC_CONFIGS",
    # Statistical tests
    "z_score_test",
    "moving_average",
    "standard_deviation",
    "detect_anomaly",
    "trend_direction",
    "calculate_brier_score",
    "calculate_percentile",
    "detect_sequential_anomaly",
]
