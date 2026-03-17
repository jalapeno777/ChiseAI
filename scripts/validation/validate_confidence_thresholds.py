#!/usr/bin/env python3
"""Validation script for signal confidence thresholds.

Validates that:
1. SignalGenerator uses 75% actionable threshold
2. ConfidenceFilter uses 75% default threshold
3. Confidence filtering logic works correctly

Usage:
    python scripts/validation/validate_confidence_thresholds.py
"""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Add src to path for imports
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from signal_generation.confidence_filter import ConfidenceFilter
from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_generator import SignalGenerationConfig


@dataclass
class ValidationResult:
    """Result of a validation check."""

    check_name: str
    passed: bool
    expected: Any
    actual: Any
    details: str = ""


def check_signal_generator_threshold() -> ValidationResult:
    """Verify SignalGenerationConfig has 75% actionable threshold."""
    config = SignalGenerationConfig()
    expected = 0.75
    actual = config.actionable_threshold

    passed = actual == expected
    details = (
        f"SignalGenerationConfig.actionable_threshold = {actual:.2f} "
        f"{'✓' if passed else '✗'}"
    )

    return ValidationResult(
        check_name="SignalGenerator Threshold",
        passed=passed,
        expected=expected,
        actual=actual,
        details=details,
    )


def check_confidence_filter_default_threshold() -> ValidationResult:
    """Verify ConfidenceFilter has 75% default threshold."""
    filter_instance = ConfidenceFilter()
    expected = 0.75
    actual = filter_instance.threshold

    passed = actual == expected
    details = f"ConfidenceFilter.threshold = {actual:.2f} {'✓' if passed else '✗'}"

    return ValidationResult(
        check_name="ConfidenceFilter Default Threshold",
        passed=passed,
        expected=expected,
        actual=actual,
        details=details,
    )


def check_confidence_filter_logic() -> ValidationResult:
    """Verify confidence filtering logic works correctly."""
    filter_instance = ConfidenceFilter()

    # Create test signals with correct model fields
    signal_below = Signal(
        token="BTC-USD",
        direction=SignalDirection.LONG,
        confidence=0.60,  # Below 75%
        base_score=60.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
    )

    signal_above = Signal(
        token="BTC-USD",
        direction=SignalDirection.LONG,
        confidence=0.80,  # Above 75%
        base_score=80.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
    )

    signal_exact = Signal(
        token="BTC-USD",
        direction=SignalDirection.LONG,
        confidence=0.75,  # Exact threshold
        base_score=75.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
    )

    # Test filtering
    result_below = filter_instance.filter(signal_below)
    result_above = filter_instance.filter(signal_above)
    result_exact = filter_instance.filter(signal_exact)

    checks = [
        (
            "Signal below threshold (60%) should not be actionable",
            not result_below.is_actionable,
        ),
        (
            "Signal above threshold (80%) should be actionable",
            result_above.is_actionable,
        ),
        (
            "Signal at exact threshold (75%) should be actionable",
            result_exact.is_actionable,
        ),
    ]

    failed_checks = [desc for desc, passed in checks if not passed]

    passed = len(failed_checks) == 0
    details = "\n    ".join(
        [f"{'✓' if passed else '✗'} {desc}" for desc, passed in checks]
    )

    return ValidationResult(
        check_name="Confidence Filtering Logic",
        passed=passed,
        expected="All checks pass",
        actual=f"{sum(1 for _, p in checks if p)}/{len(checks)} checks passed",
        details=details,
    )


def check_threshold_clamping() -> ValidationResult:
    """Verify threshold clamping to valid range [0.50, 0.95]."""
    # Test invalid thresholds
    filter_low = ConfidenceFilter(threshold=0.30)
    filter_high = ConfidenceFilter(threshold=1.50)

    checks = [
        ("Threshold 0.30 should clamp to 0.50", filter_low.threshold == 0.50),
        ("Threshold 1.50 should clamp to 0.95", filter_high.threshold == 0.95),
    ]

    failed_checks = [desc for desc, passed in checks if not passed]

    passed = len(failed_checks) == 0
    details = "\n    ".join(
        [f"{'✓' if passed else '✗'} {desc}" for desc, passed in checks]
    )

    return ValidationResult(
        check_name="Threshold Clamping",
        passed=passed,
        expected="Clamping to [0.50, 0.95]",
        actual=f"Low: {filter_low.threshold:.2f}, High: {filter_high.threshold:.2f}",
        details=details,
    )


def check_metrics_tracking() -> ValidationResult:
    """Verify metrics are tracked correctly."""
    filter_instance = ConfidenceFilter()

    # Create test signals with correct model fields
    signal_below = Signal(
        token="BTC-USD",
        direction=SignalDirection.LONG,
        confidence=0.60,
        base_score=60.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
    )

    signal_above = Signal(
        token="BTC-USD",
        direction=SignalDirection.LONG,
        confidence=0.80,
        base_score=80.0,
        timestamp=datetime.now(UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
    )

    # Filter signals
    filter_instance.filter(signal_below)
    filter_instance.filter(signal_above)
    filter_instance.filter(signal_above)

    metrics = filter_instance.metrics

    checks = [
        ("Total processed should be 3", metrics.total_processed == 3),
        ("Signals filtered should be 1", metrics.signals_filtered == 1),
        ("Signals passed should be 2", metrics.signals_passed == 2),
        ("Filter rate should be 1/3", abs(metrics.filter_rate - 0.333) < 0.01),
    ]

    failed_checks = [desc for desc, passed in checks if not passed]

    passed = len(failed_checks) == 0
    details = "\n    ".join(
        [f"{'✓' if passed else '✗'} {desc}" for desc, passed in checks]
    )

    return ValidationResult(
        check_name="Metrics Tracking",
        passed=passed,
        expected="Correct metrics",
        actual=(
            f"Total: {metrics.total_processed}, "
            f"Filtered: {metrics.signals_filtered}, "
            f"Passed: {metrics.signals_passed}"
        ),
        details=details,
    )


def main():
    """Run all validation checks."""
    print("=" * 70)
    print("CONFIDENCE THRESHOLD VALIDATION")
    print("=" * 70)
    print()

    # Run all checks
    checks = [
        check_signal_generator_threshold(),
        check_confidence_filter_default_threshold(),
        check_confidence_filter_logic(),
        check_threshold_clamping(),
        check_metrics_tracking(),
    ]

    # Print results
    for result in checks:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.check_name}")
        print(f"  Expected: {result.expected}")
        print(f"  Actual: {result.actual}")
        if result.details:
            print(f"  Details: {result.details}")
        print()

    # Summary
    total = len(checks)
    passed = sum(1 for c in checks if c.passed)
    failed = total - passed

    print("=" * 70)
    print(f"SUMMARY: {passed}/{total} checks passed, {failed} failed")
    print("=" * 70)

    if failed > 0:
        print("\n❌ VALIDATION FAILED")
        sys.exit(1)
    else:
        print("\n✅ VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
