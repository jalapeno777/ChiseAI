"""
Statistical tests for performance drift detection.

Provides statistical functions for detecting anomalies and trends
in performance metrics.
"""

from typing import List, Optional
import math
from datetime import datetime


def z_score_test(values: List[float], baseline: List[float]) -> float:
    """
    Calculate the z-score of the most recent value against a baseline.

    Args:
        values: Current values (last element is the value to test)
        baseline: Baseline values for comparison

    Returns:
        Z-score (number of standard deviations from baseline mean)

    Raises:
        ValueError: If baseline is empty or has zero standard deviation
    """
    if not baseline:
        raise ValueError("Baseline cannot be empty")

    if not values:
        raise ValueError("Values cannot be empty")

    baseline_mean = sum(baseline) / len(baseline)
    baseline_std = standard_deviation(baseline)

    if baseline_std == 0:
        # All baseline values are the same
        current_value = values[-1]
        if current_value == baseline_mean:
            return 0.0
        return float("inf") if current_value > baseline_mean else float("-inf")

    current_value = values[-1]
    z_score = (current_value - baseline_mean) / baseline_std

    return z_score


def moving_average(values: List[float], window: int) -> List[float]:
    """
    Calculate the moving average of a list of values.

    Args:
        values: List of numeric values
        window: Size of the moving window

    Returns:
        List of moving averages (length = len(values) - window + 1)

    Raises:
        ValueError: If window is larger than values or <= 0
    """
    if window <= 0:
        raise ValueError("Window must be positive")

    if window > len(values):
        raise ValueError("Window cannot be larger than values list")

    result = []
    for i in range(len(values) - window + 1):
        window_values = values[i : i + window]
        avg = sum(window_values) / window
        result.append(avg)

    return result


def standard_deviation(values: List[float]) -> float:
    """
    Calculate the standard deviation of a list of values.

    Args:
        values: List of numeric values

    Returns:
        Standard deviation

    Raises:
        ValueError: If values is empty
    """
    if not values:
        raise ValueError("Cannot calculate standard deviation of empty list")

    if len(values) == 1:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)

    return math.sqrt(variance)


def detect_anomaly(
    value: float, baseline_mean: float, baseline_std: float, threshold_std: float = 2.0
) -> bool:
    """
    Detect if a value is anomalous based on baseline statistics.

    Args:
        value: The value to test
        baseline_mean: Mean of the baseline distribution
        baseline_std: Standard deviation of the baseline distribution
        threshold_std: Number of standard deviations for anomaly threshold (default: 2.0)

    Returns:
        True if the value is anomalous (outside threshold_std standard deviations)

    Raises:
        ValueError: If baseline_std is negative or threshold_std is not positive
    """
    if baseline_std < 0:
        raise ValueError("Standard deviation cannot be negative")

    if threshold_std <= 0:
        raise ValueError("Threshold must be positive")

    if baseline_std == 0:
        # All baseline values are the same
        return abs(value - baseline_mean) > 0

    z_score = abs(value - baseline_mean) / baseline_std

    return z_score > threshold_std


def trend_direction(values: List[float]) -> str:
    """
    Determine the trend direction of a series of values.

    Uses linear regression slope to determine trend.

    Args:
        values: List of numeric values in chronological order

    Returns:
        One of: "improving", "stable", "degrading"

    Raises:
        ValueError: If values has fewer than 2 elements
    """
    if len(values) < 2:
        raise ValueError("Need at least 2 values to determine trend")

    # Simple linear regression
    n = len(values)
    x_values = list(range(n))

    mean_x = sum(x_values) / n
    mean_y = sum(values) / n

    # Calculate slope
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, values))
    denominator = sum((x - mean_x) ** 2 for x in x_values)

    if denominator == 0:
        return "stable"

    slope = numerator / denominator

    # Determine direction based on slope magnitude
    # Using a small threshold to account for noise
    threshold = (
        0.001 * (max(values) - min(values)) if max(values) != min(values) else 0.01
    )

    if abs(slope) < threshold:
        return "stable"
    elif slope > 0:
        return "improving"
    else:
        return "degrading"


def calculate_percentile(values: List[float], percentile: float) -> float:
    """
    Calculate the given percentile of a list of values.

    Args:
        values: List of numeric values
        percentile: Percentile to calculate (0-100)

    Returns:
        The percentile value

    Raises:
        ValueError: If values is empty or percentile is invalid
    """
    if not values:
        raise ValueError("Cannot calculate percentile of empty list")

    if not 0 <= percentile <= 100:
        raise ValueError("Percentile must be between 0 and 100")

    sorted_values = sorted(values)
    n = len(sorted_values)

    # Linear interpolation
    index = (percentile / 100) * (n - 1)
    lower_idx = int(index)
    upper_idx = min(lower_idx + 1, n - 1)
    fraction = index - lower_idx

    return sorted_values[lower_idx] + fraction * (
        sorted_values[upper_idx] - sorted_values[lower_idx]
    )


def detect_sequential_anomaly(
    values: List[float], window_size: int = 5, threshold_std: float = 2.0
) -> List[bool]:
    """
    Detect anomalies in a time series using a rolling window approach.

    Args:
        values: Time series values
        window_size: Size of the rolling window for baseline calculation
        threshold_std: Number of standard deviations for anomaly threshold

    Returns:
        List of booleans indicating anomaly status for each value
        (first window_size values are always False)
    """
    if len(values) < window_size + 1:
        return [False] * len(values)

    results = [False] * window_size  # First window_size values can't be tested

    for i in range(window_size, len(values)):
        baseline = values[i - window_size : i]
        current_value = values[i]

        baseline_mean = sum(baseline) / len(baseline)
        baseline_std = standard_deviation(baseline)

        is_anomaly = detect_anomaly(
            current_value, baseline_mean, baseline_std, threshold_std
        )
        results.append(is_anomaly)

    return results


def calculate_brier_score(predictions: List[float], outcomes: List[bool]) -> float:
    """
    Calculate the Brier score for probabilistic predictions.

    The Brier score measures the accuracy of probabilistic predictions.
    Lower is better (0 = perfect, 1 = worst).

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (True/False)

    Returns:
        Brier score

    Raises:
        ValueError: If predictions and outcomes have different lengths
    """
    if len(predictions) != len(outcomes):
        raise ValueError("Predictions and outcomes must have the same length")

    if not predictions:
        return 0.0

    # Convert boolean outcomes to 0/1
    outcome_values = [1.0 if o else 0.0 for o in outcomes]

    # Calculate mean squared error
    squared_errors = [(p - o) ** 2 for p, o in zip(predictions, outcome_values)]
    brier_score = sum(squared_errors) / len(squared_errors)

    return brier_score
