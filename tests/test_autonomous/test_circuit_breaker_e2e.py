"""E2E Integration tests for circuit breaker enhancements.

ST-SAFETY-001: Circuit Breaker Enhancement - E2E Tests
"""

from __future__ import annotations

import time

import pytest

from autonomous_control_plane.models.circuit_breaker import (
    AdaptiveThresholdConfig,
    CanaryRecoveryConfig,
    CircuitBreakerConfig,
    CircuitBreakerGroup,
    PredictiveAlertConfig,
)


class TestAdaptiveThresholdsE2E:
    """E2E tests for adaptive thresholds."""

    def test_adaptive_threshold_adjustment(self):
        """Adaptive threshold adjusts based on failure patterns."""
        from autonomous_control_plane.models.circuit_breaker import (
            AdaptiveThresholdMetrics,
        )

        metrics = AdaptiveThresholdMetrics(current_threshold=5)

        # Simulate high failure rate in 15min window
        window_15min = metrics.windows[900]
        for _ in range(80):
            window_15min.record_failure()
        for _ in range(20):
            window_15min.record_success()

        # Update baseline
        metrics.update_baseline()

        # Baseline should be 80% failure rate
        assert metrics.baseline_failure_rate == 0.8

    def test_adaptive_config_integration(self):
        """Adaptive config integrates with CircuitBreakerConfig."""
        adaptive_config = AdaptiveThresholdConfig(
            enabled=True,
            baseline_multiplier=3.0,
            min_threshold=5,
            max_threshold=30,
        )

        config = CircuitBreakerConfig(
            failure_threshold=10,
            adaptive_threshold=adaptive_config,
        )

        assert config.adaptive_threshold.enabled is True
        assert config.adaptive_threshold.baseline_multiplier == 3.0

        # Serialize and deserialize
        data = config.to_dict()
        restored = CircuitBreakerConfig.from_dict(data)

        assert restored.adaptive_threshold.enabled is True
        assert restored.adaptive_threshold.min_threshold == 5


class TestCanaryRecoveryE2E:
    """E2E tests for canary recovery."""

    def test_canary_progression_flow(self):
        """Full canary progression from 1% to 100%."""
        from autonomous_control_plane.models.circuit_breaker import CanaryRecoveryState

        config = CanaryRecoveryConfig(
            enabled=True,
            progression_steps=[0.01, 0.1, 0.25, 0.5, 1.0],
            success_rate_threshold=0.95,
            min_requests_per_step=10,
        )
        state = CanaryRecoveryState()

        # Simulate progression through all steps
        for step_index in range(len(config.progression_steps)):
            # Meet success criteria for this step
            for _ in range(config.min_requests_per_step):
                state.record_request()
                state.record_success()

            # Verify success rate
            assert state.current_step_success_rate >= config.success_rate_threshold

            # Promote to next step (except last)
            if step_index < len(config.progression_steps) - 1:
                state.promote_to_next_step()

        # Should have promotion history for all steps except last
        assert len(state.promotion_history) == len(config.progression_steps) - 1

    def test_canary_config_integration(self):
        """Canary config integrates with CircuitBreakerConfig."""
        canary_config = CanaryRecoveryConfig(
            enabled=True,
            progression_steps=[0.05, 0.5, 1.0],
            success_rate_threshold=0.90,
        )

        config = CircuitBreakerConfig(
            failure_threshold=5,
            canary_recovery=canary_config,
        )

        assert config.canary_recovery.enabled is True
        assert config.canary_recovery.progression_steps == [0.05, 0.5, 1.0]

        # Serialize and deserialize
        data = config.to_dict()
        restored = CircuitBreakerConfig.from_dict(data)

        assert restored.canary_recovery.enabled is True
        assert restored.canary_recovery.success_rate_threshold == 0.90


class TestPredictiveAlertsE2E:
    """E2E tests for predictive alerts."""

    def test_predictive_alert_triggering(self):
        """Predictive alert triggers when threshold approached."""
        from autonomous_control_plane.models.circuit_breaker import PredictiveAlertState

        config = PredictiveAlertConfig(
            enabled=True,
            threshold_warning_percent=0.8,
            alert_cooldown_seconds=0,  # No cooldown for testing
        )
        state = PredictiveAlertState()

        # Simulate approaching threshold (80%)
        state.update_threshold_approach(8, 10)

        assert state.threshold_approach_percent == 0.8
        assert (
            state.should_alert(
                config.threshold_warning_percent, config.alert_cooldown_seconds
            )
            is True
        )

    def test_velocity_alert(self):
        """Alert triggers on high failure velocity."""
        from autonomous_control_plane.models.circuit_breaker import PredictiveAlertState

        state = PredictiveAlertState()

        # Simulate rapid failures
        now = time.time()
        for i in range(20):
            state.record_failure(now - 1.0 + i * 0.05)

        # Velocity should be high
        assert state.failure_velocity > 5.0

    def test_predictive_config_integration(self):
        """Predictive config integrates with CircuitBreakerConfig."""
        predictive_config = PredictiveAlertConfig(
            enabled=True,
            velocity_threshold=10.0,
            threshold_warning_percent=0.75,
            alert_cooldown_seconds=120.0,
        )

        config = CircuitBreakerConfig(
            failure_threshold=5,
            predictive_alerts=predictive_config,
        )

        assert config.predictive_alerts.enabled is True
        assert config.predictive_alerts.velocity_threshold == 10.0

        # Serialize and deserialize
        data = config.to_dict()
        restored = CircuitBreakerConfig.from_dict(data)

        assert restored.predictive_alerts.enabled is True
        assert restored.predictive_alerts.threshold_warning_percent == 0.75


class TestCircuitBreakerGroupsE2E:
    """E2E tests for circuit breaker groups."""

    def test_group_creation_and_management(self):
        """Create and manage a circuit breaker group."""
        group = CircuitBreakerGroup(
            name="api-services",
            member_names=["gateway", "auth", "users"],
            cascade_open=True,
            cascade_close=False,
        )

        assert group.name == "api-services"
        assert len(group.member_names) == 3
        assert group.cascade_open is True
        assert group.cascade_close is False

        # Add member
        group.add_member("payments")
        assert len(group.member_names) == 4

        # Remove member
        group.remove_member("auth")
        assert len(group.member_names) == 3
        assert "auth" not in group.member_names

    def test_group_serialization(self):
        """Group serializes and deserializes correctly."""
        group = CircuitBreakerGroup(
            name="test-group",
            member_names=["cb1", "cb2"],
            cascade_open=True,
            cascade_close=True,
        )

        # Serialize
        data = group.to_dict()
        assert data["name"] == "test-group"
        assert data["member_names"] == ["cb1", "cb2"]

        # Deserialize
        restored = CircuitBreakerGroup.from_dict(data)
        assert restored.name == "test-group"
        assert restored.member_names == ["cb1", "cb2"]
        assert restored.cascade_open is True
        assert restored.cascade_close is True


class TestFullIntegrationE2E:
    """Full integration tests combining all features."""

    def test_complete_config_with_all_features(self):
        """CircuitBreakerConfig with all enhancement features."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            timeout_seconds=60.0,
            half_open_max_calls=5,
            adaptive_threshold=AdaptiveThresholdConfig(
                enabled=True,
                baseline_multiplier=2.5,
            ),
            canary_recovery=CanaryRecoveryConfig(
                enabled=True,
                progression_steps=[0.1, 0.5, 1.0],
            ),
            predictive_alerts=PredictiveAlertConfig(
                enabled=True,
                velocity_threshold=8.0,
            ),
        )

        # Verify all features enabled
        assert config.adaptive_threshold.enabled is True
        assert config.canary_recovery.enabled is True
        assert config.predictive_alerts.enabled is True

        # Full serialization round-trip
        data = config.to_dict()
        restored = CircuitBreakerConfig.from_dict(data)

        assert restored.adaptive_threshold.enabled is True
        assert restored.adaptive_threshold.baseline_multiplier == 2.5
        assert restored.canary_recovery.enabled is True
        assert restored.canary_recovery.progression_steps == [0.1, 0.5, 1.0]
        assert restored.predictive_alerts.enabled is True
        assert restored.predictive_alerts.velocity_threshold == 8.0

    def test_metrics_with_all_features(self):
        """CircuitBreakerMetrics with all enhancement features."""
        from autonomous_control_plane.models.circuit_breaker import (
            CircuitBreakerMetrics,
        )

        metrics = CircuitBreakerMetrics()

        # Record some activity
        for _ in range(5):
            metrics.record_success()
        for _ in range(3):
            metrics.record_failure()

        # Verify basic metrics
        assert metrics.success_count == 5
        assert metrics.failure_count == 3

        # Verify adaptive metrics updated
        assert metrics.adaptive.windows[60].success_count == 5
        assert metrics.adaptive.windows[60].failure_count == 3

        # Verify predictive metrics updated
        assert len(metrics.predictive.failure_timestamps) == 3

        # Serialization round-trip
        data = metrics.to_dict()
        restored = CircuitBreakerMetrics.from_dict(data)

        assert restored.success_count == 5
        assert restored.failure_count == 3
        assert restored.adaptive.windows[60].success_count == 5
        assert len(restored.predictive.failure_timestamps) == 3
