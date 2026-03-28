"""Shared fixtures for model_validator tests."""

from unittest.mock import MagicMock

import pytest

from ml.validation.model_validator import (
    ShadowModeConfig,
    ValidationGate,
    ValidationThresholds,
)


@pytest.fixture
def default_thresholds():
    """Create default validation thresholds."""
    return ValidationThresholds()


@pytest.fixture
def custom_thresholds():
    """Create custom validation thresholds with higher values."""
    return ValidationThresholds(
        accuracy_pass=0.80,
        precision_pass=0.75,
        recall_pass=0.70,
        f1_pass=0.72,
        win_rate_pass=0.75,
        accuracy_warning=0.70,
        precision_warning=0.65,
        recall_warning=0.60,
        f1_warning=0.62,
        win_rate_warning=0.65,
    )


@pytest.fixture
def mock_influx_logger():
    """Create a mock InfluxDB logger."""
    mock = MagicMock()
    mock.log_gate_result.return_value = True
    mock.log_shadow_comparison.return_value = True
    mock.log_degradation_event.return_value = True
    return mock


@pytest.fixture
def validation_gate(default_thresholds, mock_influx_logger):
    """Create a ValidationGate with default thresholds and mock logger."""
    return ValidationGate(
        thresholds=default_thresholds,
        influx_logger=mock_influx_logger,
    )


@pytest.fixture
def passing_metrics():
    """Metrics that pass all default thresholds."""
    return {
        "accuracy": 0.75,
        "precision": 0.70,
        "recall": 0.65,
        "f1": 0.67,
        "win_rate": 0.70,
    }


@pytest.fixture
def failing_metrics():
    """Metrics that fail critical thresholds."""
    return {
        "accuracy": 0.30,
        "precision": 0.25,
        "recall": 0.20,
        "f1": 0.22,
        "win_rate": 0.30,
    }


@pytest.fixture
def warning_metrics():
    """Metrics in the warning zone (between warning and pass thresholds)."""
    return {
        "accuracy": 0.57,
        "precision": 0.52,
        "recall": 0.47,
        "f1": 0.49,
        "win_rate": 0.52,
    }


@pytest.fixture
def shadow_config():
    """Create shadow mode configuration."""
    return ShadowModeConfig(
        enabled=True,
        duration_hours=24.0,
        comparison_interval_minutes=60,
        min_samples_required=100,
        route_to_both=True,
    )
