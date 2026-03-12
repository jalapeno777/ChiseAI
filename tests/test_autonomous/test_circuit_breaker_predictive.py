"""Tests for circuit breaker predictive alerts feature.

ST-SAFETY-001: Predictive Alert Enhancement
"""

from __future__ import annotations

import time

import pytest

from autonomous_control_plane.models.circuit_breaker import (
    PredictiveAlertConfig,
    PredictiveAlertState,
)


class TestPredictiveAlertConfig:
    """Test PredictiveAlertConfig class."""

    def test_default_values(self):
        """Default configuration values."""
        config = PredictiveAlertConfig()
        assert config.enabled is False
        assert config.velocity_threshold == 5.0
        assert config.threshold_warning_percent == 0.8
        assert config.alert_cooldown_seconds == 60.0

    def test_custom_values(self):
        """Custom configuration values."""
        config = PredictiveAlertConfig(
            enabled=True,
            velocity_threshold=10.0,
            threshold_warning_percent=0.9,
            alert_cooldown_seconds=120.0,
        )
        assert config.enabled is True
        assert config.velocity_threshold == 10.0
        assert config.threshold_warning_percent == 0.9

    def test_to_dict(self):
        """Convert to dictionary."""
        config = PredictiveAlertConfig(enabled=True)
        data = config.to_dict()
        assert data["enabled"] is True
        assert data["velocity_threshold"] == 5.0

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "enabled": True,
            "velocity_threshold": 15.0,
            "threshold_warning_percent": 0.75,
        }
        config = PredictiveAlertConfig.from_dict(data)
        assert config.enabled is True
        assert config.velocity_threshold == 15.0
        assert config.threshold_warning_percent == 0.75


class TestPredictiveAlertState:
    """Test PredictiveAlertState class."""

    def test_initial_state(self):
        """Initial predictive alert state."""
        state = PredictiveAlertState()
        assert state.failure_velocity == 0.0
        assert state.threshold_approach_percent == 0.0
        assert state.last_alert_time is None
        assert state.alert_count == 0
        assert state.failure_timestamps == []

    def test_record_failure_adds_timestamp(self):
        """Recording failure adds timestamp."""
        state = PredictiveAlertState()
        state.record_failure()
        assert len(state.failure_timestamps) == 1

    def test_velocity_calculation(self):
        """Velocity calculated from timestamps."""
        state = PredictiveAlertState()
        now = time.time()

        # Add 10 failures over 1 second
        for i in range(10):
            state.record_failure(now - 0.5 + i * 0.1)

        assert state.failure_velocity > 0
        assert len(state.failure_timestamps) == 10

    def test_old_timestamps_pruned(self):
        """Timestamps older than 60 seconds are pruned."""
        state = PredictiveAlertState()
        now = time.time()

        # Add old and new timestamps
        state.record_failure(now - 70)  # Old
        state.record_failure(now - 65)  # Old
        state.record_failure(now - 10)  # Recent
        state.record_failure(now - 5)  # Recent

        assert len(state.failure_timestamps) == 2  # Only recent ones kept

    def test_update_threshold_approach(self):
        """Threshold approach percentage updated."""
        state = PredictiveAlertState()
        state.update_threshold_approach(4, 5)
        assert state.threshold_approach_percent == 0.8

    def test_update_threshold_approach_capped(self):
        """Threshold approach capped at 100%."""
        state = PredictiveAlertState()
        state.update_threshold_approach(10, 5)
        assert state.threshold_approach_percent == 1.0

    def test_should_alert_below_threshold(self):
        """No alert when below warning threshold."""
        state = PredictiveAlertState()
        state.update_threshold_approach(3, 5)  # 60% of threshold
        assert state.should_alert(0.8, 60) is False

    def test_should_alert_above_threshold(self):
        """Alert when above warning threshold."""
        state = PredictiveAlertState()
        state.update_threshold_approach(4, 5)  # 80% of threshold
        assert state.should_alert(0.8, 60) is True

    def test_should_alert_respects_cooldown(self):
        """Alert respects cooldown period."""
        state = PredictiveAlertState()
        state.update_threshold_approach(4, 5)

        # First alert
        assert state.should_alert(0.8, 60) is True
        state.record_alert()

        # Second alert within cooldown
        assert state.should_alert(0.8, 60) is False

    def test_record_alert(self):
        """Recording alert updates state."""
        state = PredictiveAlertState()
        assert state.last_alert_time is None
        assert state.alert_count == 0

        state.record_alert()

        assert state.last_alert_time is not None
        assert state.alert_count == 1

    def test_to_dict(self):
        """Convert to dictionary."""
        state = PredictiveAlertState()
        state.failure_velocity = 10.5
        state.threshold_approach_percent = 0.85
        state.alert_count = 3

        data = state.to_dict()
        assert data["failure_velocity"] == 10.5
        assert data["threshold_approach_percent"] == 0.85
        assert data["alert_count"] == 3

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "failure_velocity": 8.5,
            "threshold_approach_percent": 0.75,
            "last_alert_time": "2026-03-12T10:00:00",
            "alert_count": 5,
            "failure_timestamps": [1234567890.0, 1234567891.0],
        }

        state = PredictiveAlertState.from_dict(data)
        assert state.failure_velocity == 8.5
        assert state.threshold_approach_percent == 0.75
        assert state.alert_count == 5
        assert len(state.failure_timestamps) == 2


class TestPredictiveAlertIntegration:
    """Integration tests for predictive alerts."""

    def test_high_velocity_detection(self):
        """Detect high failure velocity."""
        state = PredictiveAlertState()
        now = time.time()

        # Simulate 20 failures in 1 second
        for i in range(20):
            state.record_failure(now - 0.5 + i * 0.05)

        assert state.failure_velocity >= 10.0  # At least 10 failures/sec

    def test_threshold_approach_warning(self):
        """Warn when approaching threshold."""
        state = PredictiveAlertState()

        # Update with 80% of threshold reached
        state.update_threshold_approach(8, 10)

        assert state.threshold_approach_percent == 0.8
        assert state.should_alert(0.75, 60) is True  # Warn at 75%
        assert state.should_alert(0.85, 60) is False  # Don't warn at 85% threshold

    def test_cooldown_prevents_spam(self):
        """Cooldown prevents alert spam."""
        state = PredictiveAlertState()
        state.update_threshold_approach(9, 10)  # 90% of threshold

        # First alert should trigger
        assert state.should_alert(0.8, 60) is True
        state.record_alert()

        # Immediately checking again should not alert
        assert state.should_alert(0.8, 60) is False

    def test_multiple_alerts_after_cooldown(self):
        """Multiple alerts possible after cooldown."""
        state = PredictiveAlertState()
        state.update_threshold_approach(9, 10)

        # First alert
        assert state.should_alert(0.8, 0) is True  # 0 cooldown for test
        state.record_alert()

        # Can alert again immediately with 0 cooldown
        assert state.should_alert(0.8, 0) is True
