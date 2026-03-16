#!/usr/bin/env python3
"""
Demonstration script for performance drift detection system.

Shows how to:
1. Establish baselines for metrics
2. Detect drift in performance metrics
3. View drift status and history
4. Test root cause tagging
"""

import random
from datetime import datetime, timedelta
from src.autonomous_cognition.drift import (
    PerformanceDriftDetector,
    DriftSeverity,
    RootCauseTag,
)


def demo_baseline_establishment():
    """Demonstrate baseline establishment."""
    print("=" * 60)
    print("DEMO 1: Baseline Establishment")
    print("=" * 60)

    detector = PerformanceDriftDetector()

    # Establish baseline for cycle success rate
    random.seed(42)
    baseline_values = [0.95 + random.gauss(0, 0.01) for _ in range(168)]
    baseline = detector.establish_baseline(
        metric_name="cycle_success_rate",
        values=baseline_values,
    )

    print(f"Metric: {baseline.metric_name}")
    print(f"Baseline Mean: {baseline.mean:.4f}")
    print(f"Baseline Std: {baseline.std:.4f}")
    print(f"Window Days: {baseline.window_days}")
    print(f"Established At: {baseline.established_at}")
    print()


def demo_drift_detection():
    """Demonstrate drift detection."""
    print("=" * 60)
    print("DEMO 2: Drift Detection")
    print("=" * 60)

    detector = PerformanceDriftDetector()

    # Establish baselines for multiple metrics
    random.seed(42)

    # Cycle success rate baseline
    detector.establish_baseline(
        metric_name="cycle_success_rate",
        values=[0.95 + random.gauss(0, 0.01) for _ in range(168)],
    )

    # Learning velocity baseline
    detector.establish_baseline(
        metric_name="learning_velocity",
        values=[5.0 + random.gauss(0, 0.5) for _ in range(168)],
    )

    # Calibration quality baseline (Brier score, lower is better)
    detector.establish_baseline(
        metric_name="calibration_quality",
        values=[0.15 + random.gauss(0, 0.02) for _ in range(168)],
    )

    # Test cases
    test_cases = [
        ("cycle_success_rate", 0.95, "Normal operation"),
        ("cycle_success_rate", 0.85, "Significant degradation"),
        ("learning_velocity", 3.0, "Below threshold"),
        ("calibration_quality", 0.25, "Worse Brier score"),
    ]

    for metric_name, current_value, description in test_cases:
        result = detector.detect_drift(metric_name, current_value)
        print(f"\n{description}:")
        print(f"  Metric: {result.metric_name}")
        print(f"  Current Value: {result.current_value:.4f}")
        print(f"  Baseline Mean: {result.baseline_mean:.4f}")
        print(f"  Z-Score: {result.z_score:.2f}")
        print(f"  Is Drift: {result.is_drift}")
        print(f"  Severity: {result.severity}")
        print(f"  Trend: {result.trend}")


def demo_root_cause_tagging():
    """Demonstrate root cause tagging."""
    print("\n" + "=" * 60)
    print("DEMO 3: Root Cause Tagging")
    print("=" * 60)

    detector = PerformanceDriftDetector()

    # Establish baseline
    random.seed(42)
    detector.establish_baseline(
        metric_name="qdrant_write_latency",
        values=[100.0 + random.gauss(0, 10) for _ in range(168)],
    )

    # Test different contexts
    contexts = [
        ({}, "No context"),
        ({"error": "qdrant connection timeout"}, "Infrastructure error"),
        ({"event": "deployment completed"}, "Code deployment"),
        ({"error": "data corruption detected"}, "Data issue"),
    ]

    for context, description in contexts:
        result = detector.detect_drift(
            "qdrant_write_latency",
            500.0,  # High latency
            context=context,
        )
        print(f"\n{description}:")
        print(f"  Root Cause Tag: {result.root_cause_tag}")


def demo_drift_status():
    """Demonstrate drift status reporting."""
    print("\n" + "=" * 60)
    print("DEMO 4: Drift Status")
    print("=" * 60)

    detector = PerformanceDriftDetector()

    # Establish baselines
    random.seed(42)
    detector.establish_baseline(
        "cycle_success_rate",
        values=[0.95 + random.gauss(0, 0.01) for _ in range(168)],
    )
    detector.establish_baseline(
        "learning_velocity",
        values=[5.0 + random.gauss(0, 0.5) for _ in range(168)],
    )

    # Trigger some drifts
    detector.detect_drift("cycle_success_rate", 0.85)
    detector.detect_drift("learning_velocity", 2.0)

    # Get status
    status = detector.get_drift_status()
    print(f"\nMonitored Metrics: {status['monitored_metrics']}")
    print(f"Recent Drifts: {status['summary']['total_drifts']}")
    print(f"  Critical: {status['summary']['critical']}")
    print(f"  Warning: {status['summary']['warning']}")
    print(f"  Info: {status['summary']['info']}")


def demo_alert_logic():
    """Demonstrate alert logic."""
    print("\n" + "=" * 60)
    print("DEMO 5: Alert Logic")
    print("=" * 60)

    detector = PerformanceDriftDetector()

    random.seed(42)
    detector.establish_baseline(
        "cycle_success_rate",
        values=[0.95 + random.gauss(0, 0.01) for _ in range(168)],
    )

    # Test different scenarios
    test_values = [
        (0.95, "Normal - no alert expected"),
        (0.90, "Slight degradation - may alert"),
        (0.85, "Significant degradation - should alert"),
        (0.80, "Critical degradation - must alert"),
    ]

    for value, description in test_values:
        result = detector.detect_drift("cycle_success_rate", value)
        should_alert = detector.alert_on_drift(result)
        print(f"\n{description}")
        print(f"  Value: {value}")
        print(f"  Is Drift: {result.is_drift}")
        print(f"  Severity: {result.severity}")
        print(f"  Should Alert: {should_alert}")


def demo_statistical_tests():
    """Demonstrate statistical test functions."""
    print("\n" + "=" * 60)
    print("DEMO 6: Statistical Tests")
    print("=" * 60)

    from src.autonomous_cognition.drift.statistical_tests import (
        z_score_test,
        moving_average,
        standard_deviation,
        detect_anomaly,
        trend_direction,
        calculate_brier_score,
    )

    # Z-score test
    baseline = [10.0, 12.0, 11.0, 13.0, 12.0]
    current = [15.0]
    z_score = z_score_test(current, baseline)
    print(f"\nZ-Score Test:")
    print(f"  Baseline: {baseline}")
    print(f"  Current: {current[0]}")
    print(f"  Z-Score: {z_score:.2f}")

    # Moving average
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    ma = moving_average(values, 3)
    print(f"\nMoving Average (window=3):")
    print(f"  Input: {values}")
    print(f"  Result: {ma}")

    # Standard deviation
    std = standard_deviation([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    print(f"\nStandard Deviation:")
    print(f"  Input: [2, 4, 4, 4, 5, 5, 7, 9]")
    print(f"  Std: {std:.2f}")

    # Anomaly detection
    is_anomaly = detect_anomaly(15.0, 10.0, 2.0, 2.0)
    print(f"\nAnomaly Detection:")
    print(f"  Value: 15.0, Mean: 10.0, Std: 2.0, Threshold: 2.0")
    print(f"  Is Anomaly: {is_anomaly}")

    # Trend direction
    trend = trend_direction([1.0, 2.0, 3.0, 4.0, 5.0])
    print(f"\nTrend Direction:")
    print(f"  Input: [1, 2, 3, 4, 5]")
    print(f"  Trend: {trend}")

    # Brier score
    brier = calculate_brier_score([0.8, 0.3, 0.9], [True, False, True])
    print(f"\nBrier Score:")
    print(f"  Predictions: [0.8, 0.3, 0.9]")
    print(f"  Outcomes: [True, False, True]")
    print(f"  Brier Score: {brier:.4f}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("PERFORMANCE DRIFT DETECTION SYSTEM DEMONSTRATION")
    print("=" * 60)

    demo_baseline_establishment()
    demo_drift_detection()
    demo_root_cause_tagging()
    demo_drift_status()
    demo_alert_logic()
    demo_statistical_tests()

    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
