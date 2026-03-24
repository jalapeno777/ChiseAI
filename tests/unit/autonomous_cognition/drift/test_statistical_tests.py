"""
Unit tests for statistical_tests.py
"""


import pytest
from src.autonomous_cognition.drift.statistical_tests import (
    calculate_brier_score,
    calculate_percentile,
    detect_anomaly,
    detect_sequential_anomaly,
    moving_average,
    standard_deviation,
    trend_direction,
    z_score_test,
)


class TestZScoreTest:
    """Tests for z_score_test function."""

    def test_z_score_basic(self):
        """Test basic z-score calculation."""
        baseline = [10.0, 12.0, 11.0, 13.0, 12.0]
        values = [15.0]  # Current value

        z = z_score_test(values, baseline)

        # Mean = 11.6, values around 11.6 with some variance
        # 15 is above mean, so z should be positive
        assert z > 0
        assert isinstance(z, float)

    def test_z_score_negative(self):
        """Test z-score for value below mean."""
        baseline = [10.0, 12.0, 11.0, 13.0, 12.0]
        values = [5.0]  # Well below mean

        z = z_score_test(values, baseline)

        assert z < 0

    def test_z_score_at_mean(self):
        """Test z-score for value at mean."""
        baseline = [10.0, 10.0, 10.0, 10.0, 10.0]
        values = [10.0]

        z = z_score_test(values, baseline)

        # With zero std, value at mean should give 0
        assert z == 0.0

    def test_z_score_empty_baseline(self):
        """Test error on empty baseline."""
        with pytest.raises(ValueError, match="Baseline cannot be empty"):
            z_score_test([1.0], [])

    def test_z_score_empty_values(self):
        """Test error on empty values."""
        with pytest.raises(ValueError, match="Values cannot be empty"):
            z_score_test([], [1.0, 2.0, 3.0])

    def test_z_score_zero_std(self):
        """Test z-score with zero standard deviation."""
        baseline = [5.0, 5.0, 5.0, 5.0]
        values = [7.0]  # Above constant baseline

        z = z_score_test(values, baseline)

        assert z == float("inf")

    def test_z_score_zero_std_below(self):
        """Test z-score with zero std and value below."""
        baseline = [5.0, 5.0, 5.0, 5.0]
        values = [3.0]  # Below constant baseline

        z = z_score_test(values, baseline)

        assert z == float("-inf")


class TestMovingAverage:
    """Tests for moving_average function."""

    def test_moving_average_basic(self):
        """Test basic moving average."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        window = 3

        result = moving_average(values, window)

        assert result == [2.0, 3.0, 4.0]  # (1+2+3)/3, (2+3+4)/3, (3+4+5)/3

    def test_moving_average_window_2(self):
        """Test moving average with window size 2."""
        values = [1.0, 2.0, 3.0, 4.0]
        window = 2

        result = moving_average(values, window)

        assert result == [1.5, 2.5, 3.5]

    def test_moving_average_single_value(self):
        """Test moving average returns single value when window equals length."""
        values = [1.0, 2.0, 3.0]
        window = 3

        result = moving_average(values, window)

        assert result == [2.0]

    def test_moving_average_window_too_large(self):
        """Test error when window larger than values."""
        with pytest.raises(ValueError, match="Window cannot be larger"):
            moving_average([1.0, 2.0], 3)

    def test_moving_average_zero_window(self):
        """Test error with zero window."""
        with pytest.raises(ValueError, match="Window must be positive"):
            moving_average([1.0, 2.0, 3.0], 0)

    def test_moving_average_negative_window(self):
        """Test error with negative window."""
        with pytest.raises(ValueError, match="Window must be positive"):
            moving_average([1.0, 2.0, 3.0], -1)


class TestStandardDeviation:
    """Tests for standard_deviation function."""

    def test_standard_deviation_basic(self):
        """Test basic standard deviation calculation."""
        values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]

        std = standard_deviation(values)

        # Population std of these values ≈ 2
        assert 1.8 < std < 2.2

    def test_standard_deviation_constant(self):
        """Test std of constant values is zero."""
        values = [5.0, 5.0, 5.0, 5.0]

        std = standard_deviation(values)

        assert std == 0.0

    def test_standard_deviation_single_value(self):
        """Test std of single value is zero."""
        std = standard_deviation([42.0])

        assert std == 0.0

    def test_standard_deviation_empty(self):
        """Test error on empty list."""
        with pytest.raises(ValueError, match="Cannot calculate standard deviation"):
            standard_deviation([])

    def test_standard_deviation_two_values(self):
        """Test std with two values."""
        values = [0.0, 10.0]

        std = standard_deviation(values)

        # Mean = 5, variance = ((0-5)² + (10-5)²) / 2 = 25, std = 5
        assert std == 5.0


class TestDetectAnomaly:
    """Tests for detect_anomaly function."""

    def test_detect_anomaly_positive(self):
        """Test detection of anomalous value."""
        # Mean = 10, std = 2, threshold = 2
        # Anomaly if value is outside [6, 14]
        assert detect_anomaly(15.0, 10.0, 2.0, 2.0) is True
        assert detect_anomaly(5.0, 10.0, 2.0, 2.0) is True

    def test_detect_anomaly_negative(self):
        """Test non-detection of normal value."""
        assert detect_anomaly(11.0, 10.0, 2.0, 2.0) is False
        assert detect_anomaly(13.0, 10.0, 2.0, 2.0) is False  # Exactly at threshold

    def test_detect_anomaly_at_threshold(self):
        """Test boundary at exactly threshold."""
        # At exactly 2 std, should NOT be anomaly (strict inequality)
        assert detect_anomaly(14.0, 10.0, 2.0, 2.0) is False

    def test_detect_anomaly_zero_std(self):
        """Test anomaly detection with zero std."""
        # With zero std, any deviation is an anomaly
        assert detect_anomaly(11.0, 10.0, 0.0, 2.0) is True
        assert detect_anomaly(10.0, 10.0, 0.0, 2.0) is False

    def test_detect_anomaly_negative_std(self):
        """Test error with negative std."""
        with pytest.raises(ValueError, match="Standard deviation cannot be negative"):
            detect_anomaly(10.0, 10.0, -1.0, 2.0)

    def test_detect_anomaly_invalid_threshold(self):
        """Test error with invalid threshold."""
        with pytest.raises(ValueError, match="Threshold must be positive"):
            detect_anomaly(10.0, 10.0, 2.0, 0.0)


class TestTrendDirection:
    """Tests for trend_direction function."""

    def test_trend_improving(self):
        """Test detecting improving trend."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        trend = trend_direction(values)

        assert trend == "improving"

    def test_trend_degrading(self):
        """Test detecting degrading trend."""
        values = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]

        trend = trend_direction(values)

        assert trend == "degrading"

    def test_trend_stable(self):
        """Test detecting stable trend."""
        # Use perfectly constant values to ensure stable detection
        values = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]

        trend = trend_direction(values)

        assert trend == "stable"

    def test_trend_insufficient_data(self):
        """Test error with insufficient data."""
        with pytest.raises(ValueError, match="Need at least 2 values"):
            trend_direction([5.0])

    def test_trend_flat(self):
        """Test perfectly flat trend."""
        values = [5.0, 5.0, 5.0, 5.0, 5.0]

        trend = trend_direction(values)

        assert trend == "stable"


class TestCalculateBrierScore:
    """Tests for calculate_brier_score function."""

    def test_brier_score_perfect(self):
        """Test Brier score with perfect predictions."""
        predictions = [1.0, 0.0, 1.0, 0.0]
        outcomes = [True, False, True, False]

        score = calculate_brier_score(predictions, outcomes)

        assert score == 0.0

    def test_brier_score_worst(self):
        """Test Brier score with worst predictions."""
        predictions = [0.0, 1.0, 0.0, 1.0]
        outcomes = [True, False, True, False]

        score = calculate_brier_score(predictions, outcomes)

        assert score == 1.0

    def test_brier_score_uncertain(self):
        """Test Brier score with uncertain predictions."""
        predictions = [0.5, 0.5, 0.5, 0.5]
        outcomes = [True, False, True, False]

        score = calculate_brier_score(predictions, outcomes)

        # Brier score = (0.5-1)² + (0.5-0)² + (0.5-1)² + (0.5-0)² / 4 = 0.25
        assert score == 0.25

    def test_brier_score_empty(self):
        """Test Brier score with empty lists."""
        score = calculate_brier_score([], [])

        assert score == 0.0

    def test_brier_score_mismatched(self):
        """Test error with mismatched lengths."""
        with pytest.raises(ValueError, match="must have the same length"):
            calculate_brier_score([0.5, 0.5], [True])


class TestCalculatePercentile:
    """Tests for calculate_percentile function."""

    def test_percentile_median(self):
        """Test 50th percentile (median)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        p50 = calculate_percentile(values, 50)

        assert p50 == 3.0

    def test_percentile_min(self):
        """Test 0th percentile (min)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        p0 = calculate_percentile(values, 0)

        assert p0 == 1.0

    def test_percentile_max(self):
        """Test 100th percentile (max)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        p100 = calculate_percentile(values, 100)

        assert p100 == 5.0

    def test_percentile_empty(self):
        """Test error with empty list."""
        with pytest.raises(ValueError, match="Cannot calculate percentile"):
            calculate_percentile([], 50)

    def test_percentile_invalid(self):
        """Test error with invalid percentile."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            calculate_percentile([1.0, 2.0], 150)


class TestDetectSequentialAnomaly:
    """Tests for detect_sequential_anomaly function."""

    def test_sequential_no_anomalies(self):
        """Test with no anomalies."""
        # Use constant values to ensure no anomalies detected
        values = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]

        result = detect_sequential_anomaly(values, window_size=3, threshold_std=2.0)

        # First 3 values are False (no baseline), rest should be False (no anomaly)
        assert all(not r for r in result)

    def test_sequential_with_anomaly(self):
        """Test with one anomaly."""
        values = [10.0, 10.0, 10.0, 10.0, 50.0]  # Last value is anomaly

        result = detect_sequential_anomaly(values, window_size=3, threshold_std=2.0)

        assert result == [False, False, False, False, True]

    def test_sequential_insufficient_data(self):
        """Test with insufficient data."""
        values = [10.0, 20.0]

        result = detect_sequential_anomaly(values, window_size=3)

        assert result == [False, False]
