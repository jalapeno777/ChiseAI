"""Tests for circuit breaker adaptive threshold feature.

ST-SAFETY-001: Adaptive Threshold Enhancement
"""

from __future__ import annotations

from autonomous_control_plane.models.circuit_breaker import (
    AdaptiveThresholdConfig,
    AdaptiveThresholdMetrics,
    CircuitBreakerConfig,
    FailureRateWindow,
)


class TestFailureRateWindow:
    """Test FailureRateWindow class."""

    def test_initial_state(self):
        """Window starts with zero counts."""
        window = FailureRateWindow(window_seconds=60)
        assert window.window_seconds == 60
        assert window.failure_count == 0
        assert window.success_count == 0
        assert window.total_calls == 0
        assert window.failure_rate == 0.0

    def test_record_failure(self):
        """Recording failure increments count."""
        window = FailureRateWindow(window_seconds=60)
        window.record_failure()
        assert window.failure_count == 1
        assert window.success_count == 0
        assert window.total_calls == 1
        assert window.failure_rate == 1.0

    def test_record_success(self):
        """Recording success increments count."""
        window = FailureRateWindow(window_seconds=60)
        window.record_success()
        assert window.failure_count == 0
        assert window.success_count == 1
        assert window.total_calls == 1
        assert window.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        """Failure rate calculated correctly."""
        window = FailureRateWindow(window_seconds=60)
        window.record_failure()
        window.record_failure()
        window.record_success()
        window.record_success()

        assert window.total_calls == 4
        assert window.failure_rate == 0.5

    def test_to_dict(self):
        """Convert to dictionary."""
        window = FailureRateWindow(window_seconds=60)
        window.record_failure()
        window.record_success()

        data = window.to_dict()
        assert data["window_seconds"] == 60
        assert data["failure_count"] == 1
        assert data["success_count"] == 1
        assert "last_updated" in data

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "window_seconds": 120,
            "failure_count": 5,
            "success_count": 10,
            "last_updated": "2026-03-12T10:00:00",
        }

        window = FailureRateWindow.from_dict(data)
        assert window.window_seconds == 120
        assert window.failure_count == 5
        assert window.success_count == 10


class TestAdaptiveThresholdMetrics:
    """Test AdaptiveThresholdMetrics class."""

    def test_initialization_creates_windows(self):
        """Initialization creates default time windows."""
        metrics = AdaptiveThresholdMetrics()
        assert 60 in metrics.windows
        assert 300 in metrics.windows
        assert 900 in metrics.windows
        assert metrics.current_threshold == 5
        assert metrics.baseline_failure_rate == 0.0

    def test_record_failure_updates_all_windows(self):
        """Recording failure updates all windows."""
        metrics = AdaptiveThresholdMetrics()
        metrics.record_failure()

        for window in metrics.windows.values():
            assert window.failure_count == 1

    def test_record_success_updates_all_windows(self):
        """Recording success updates all windows."""
        metrics = AdaptiveThresholdMetrics()
        metrics.record_success()

        for window in metrics.windows.values():
            assert window.success_count == 1

    def test_update_baseline_with_sufficient_data(self):
        """Baseline updates when sufficient data available."""
        metrics = AdaptiveThresholdMetrics()

        # Add 100 calls to 15min window
        for _ in range(50):
            metrics.windows[900].record_failure()
        for _ in range(50):
            metrics.windows[900].record_success()

        metrics.update_baseline()
        assert metrics.baseline_failure_rate == 0.5

    def test_update_baseline_insufficient_data(self):
        """Baseline not updated with insufficient data."""
        metrics = AdaptiveThresholdMetrics()
        metrics.windows[900].record_failure()
        metrics.update_baseline()
        assert metrics.baseline_failure_rate == 0.0

    def test_to_dict(self):
        """Convert to dictionary."""
        metrics = AdaptiveThresholdMetrics()
        metrics.current_threshold = 10
        metrics.baseline_failure_rate = 0.25
        metrics.adjustment_count = 3

        data = metrics.to_dict()
        assert data["current_threshold"] == 10
        assert data["baseline_failure_rate"] == 0.25
        assert data["adjustment_count"] == 3
        assert "windows" in data

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "current_threshold": 8,
            "baseline_failure_rate": 0.3,
            "windows": {
                "60": {
                    "window_seconds": 60,
                    "failure_count": 5,
                    "success_count": 5,
                    "last_updated": "2026-03-12T10:00:00",
                },
            },
            "adjustment_count": 2,
        }

        metrics = AdaptiveThresholdMetrics.from_dict(data)
        assert metrics.current_threshold == 8
        assert metrics.baseline_failure_rate == 0.3
        assert metrics.adjustment_count == 2
        assert 60 in metrics.windows


class TestAdaptiveThresholdConfig:
    """Test AdaptiveThresholdConfig class."""

    def test_default_values(self):
        """Default configuration values."""
        config = AdaptiveThresholdConfig()
        assert config.enabled is False
        assert config.time_windows == [60, 300, 900]
        assert config.baseline_multiplier == 2.0
        assert config.min_threshold == 3
        assert config.max_threshold == 20
        assert config.adjustment_cooldown_seconds == 60.0

    def test_custom_values(self):
        """Custom configuration values."""
        config = AdaptiveThresholdConfig(
            enabled=True,
            time_windows=[30, 120],
            baseline_multiplier=3.0,
            min_threshold=5,
            max_threshold=50,
            adjustment_cooldown_seconds=120.0,
        )
        assert config.enabled is True
        assert config.time_windows == [30, 120]
        assert config.baseline_multiplier == 3.0

    def test_to_dict(self):
        """Convert to dictionary."""
        config = AdaptiveThresholdConfig(enabled=True)
        data = config.to_dict()
        assert data["enabled"] is True
        assert data["time_windows"] == [60, 300, 900]

    def test_from_dict(self):
        """Create from dictionary."""
        data = {"enabled": True, "min_threshold": 10, "max_threshold": 100}
        config = AdaptiveThresholdConfig.from_dict(data)
        assert config.enabled is True
        assert config.min_threshold == 10
        assert config.max_threshold == 100


class TestCircuitBreakerConfigWithAdaptive:
    """Test CircuitBreakerConfig with adaptive threshold integration."""

    def test_default_adaptive_config(self):
        """Default adaptive config is disabled."""
        config = CircuitBreakerConfig()
        assert config.adaptive_threshold.enabled is False

    def test_adaptive_config_in_to_dict(self):
        """Adaptive config included in dict output."""
        config = CircuitBreakerConfig()
        data = config.to_dict()
        assert "adaptive_threshold" in data
        assert data["adaptive_threshold"]["enabled"] is False

    def test_adaptive_config_from_dict(self):
        """Adaptive config parsed from dict."""
        data = {
            "failure_threshold": 10,
            "adaptive_threshold": {"enabled": True, "min_threshold": 5},
        }
        config = CircuitBreakerConfig.from_dict(data)
        assert config.failure_threshold == 10
        assert config.adaptive_threshold.enabled is True
        assert config.adaptive_threshold.min_threshold == 5
