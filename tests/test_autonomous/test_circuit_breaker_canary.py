"""Tests for circuit breaker canary recovery feature.

ST-SAFETY-001: Canary Recovery Enhancement
"""

from __future__ import annotations

from autonomous_control_plane.models.circuit_breaker import (
    CanaryRecoveryConfig,
    CanaryRecoveryState,
)


class TestCanaryRecoveryConfig:
    """Test CanaryRecoveryConfig class."""

    def test_default_values(self):
        """Default configuration values."""
        config = CanaryRecoveryConfig()
        assert config.enabled is False
        assert config.progression_steps == [0.01, 0.1, 0.25, 0.5, 1.0]
        assert config.success_rate_threshold == 0.95
        assert config.min_requests_per_step == 10
        assert config.step_timeout_seconds == 30.0

    def test_custom_values(self):
        """Custom configuration values."""
        config = CanaryRecoveryConfig(
            enabled=True,
            progression_steps=[0.05, 0.5, 1.0],
            success_rate_threshold=0.90,
            min_requests_per_step=20,
            step_timeout_seconds=60.0,
        )
        assert config.enabled is True
        assert config.progression_steps == [0.05, 0.5, 1.0]
        assert config.success_rate_threshold == 0.90

    def test_to_dict(self):
        """Convert to dictionary."""
        config = CanaryRecoveryConfig(enabled=True)
        data = config.to_dict()
        assert data["enabled"] is True
        assert data["progression_steps"] == [0.01, 0.1, 0.25, 0.5, 1.0]

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "enabled": True,
            "progression_steps": [0.1, 0.5, 1.0],
            "success_rate_threshold": 0.98,
        }
        config = CanaryRecoveryConfig.from_dict(data)
        assert config.enabled is True
        assert config.progression_steps == [0.1, 0.5, 1.0]
        assert config.success_rate_threshold == 0.98


class TestCanaryRecoveryState:
    """Test CanaryRecoveryState class."""

    def test_initial_state(self):
        """Initial canary state."""
        state = CanaryRecoveryState()
        assert state.current_step_index == 0
        assert state.current_step_requests == 0
        assert state.current_step_successes == 0
        assert state.promotion_history == []
        assert state.current_step_success_rate == 0.0

    def test_record_request(self):
        """Recording request increments count."""
        state = CanaryRecoveryState()
        state.record_request()
        assert state.current_step_requests == 1

    def test_record_success(self):
        """Recording success increments count."""
        state = CanaryRecoveryState()
        state.record_success()
        assert state.current_step_successes == 1

    def test_current_step_success_rate(self):
        """Success rate calculated correctly."""
        state = CanaryRecoveryState()
        assert state.current_step_success_rate == 0.0

        state.record_request()
        state.record_success()
        state.record_request()
        state.record_success()
        state.record_request()  # One failure (no success recorded)

        assert state.current_step_success_rate == 2 / 3

    def test_promote_to_next_step(self):
        """Promotion advances step and records history."""
        state = CanaryRecoveryState()
        state.record_request()
        state.record_success()

        state.promote_to_next_step()

        assert state.current_step_index == 1
        assert state.current_step_requests == 0
        assert state.current_step_successes == 0
        assert len(state.promotion_history) == 1
        assert state.promotion_history[0]["step_index"] == 0
        assert state.promotion_history[0]["success_rate"] == 1.0

    def test_reset(self):
        """Reset clears all state."""
        state = CanaryRecoveryState()
        state.record_request()
        state.record_success()
        state.promote_to_next_step()

        state.reset()

        assert state.current_step_index == 0
        assert state.current_step_requests == 0
        assert state.current_step_successes == 0
        assert state.promotion_history == []

    def test_to_dict(self):
        """Convert to dictionary."""
        state = CanaryRecoveryState()
        state.record_request()
        state.record_success()

        data = state.to_dict()
        assert data["current_step_index"] == 0
        assert data["current_step_requests"] == 1
        assert data["current_step_successes"] == 1
        assert "step_start_time" in data

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "current_step_index": 2,
            "current_step_requests": 15,
            "current_step_successes": 14,
            "step_start_time": "2026-03-12T10:00:00",
            "promotion_history": [
                {"step_index": 0, "requests": 10, "successes": 10, "success_rate": 1.0}
            ],
        }

        state = CanaryRecoveryState.from_dict(data)
        assert state.current_step_index == 2
        assert state.current_step_requests == 15
        assert state.current_step_successes == 14
        assert len(state.promotion_history) == 1


class TestCanaryRecoveryIntegration:
    """Integration tests for canary recovery flow."""

    def test_canary_progression_simulation(self):
        """Simulate full canary recovery progression."""
        config = CanaryRecoveryConfig(
            enabled=True,
            progression_steps=[0.1, 0.5, 1.0],
            success_rate_threshold=0.95,
            min_requests_per_step=10,
        )
        state = CanaryRecoveryState()

        # Simulate step 0 (10% traffic)
        for _ in range(10):
            state.record_request()
            state.record_success()

        assert state.current_step_success_rate == 1.0
        state.promote_to_next_step()
        assert state.current_step_index == 1

        # Simulate step 1 (50% traffic)
        for _ in range(10):
            state.record_request()
            state.record_success()

        state.promote_to_next_step()
        assert state.current_step_index == 2

        # Simulate step 2 (100% traffic)
        for _ in range(10):
            state.record_request()
            state.record_success()

        assert state.current_step_success_rate == 1.0

    def test_canary_failure_during_step(self):
        """Canary fails to promote with low success rate."""
        config = CanaryRecoveryConfig(
            enabled=True,
            success_rate_threshold=0.95,
            min_requests_per_step=10,
        )
        state = CanaryRecoveryState()

        # Add requests with low success rate
        for i in range(10):
            state.record_request()
            if i < 8:  # Only 8/10 successes = 80%
                state.record_success()

        assert state.current_step_success_rate == 0.8
        # Would not promote since 0.8 < 0.95 threshold

    def test_multiple_promotions_recorded(self):
        """Multiple promotions are tracked in history."""
        state = CanaryRecoveryState()

        # First promotion
        for _ in range(5):
            state.record_request()
            state.record_success()
        state.promote_to_next_step()

        # Second promotion
        for _ in range(5):
            state.record_request()
            state.record_success()
        state.promote_to_next_step()

        assert len(state.promotion_history) == 2
        assert state.promotion_history[0]["step_index"] == 0
        assert state.promotion_history[1]["step_index"] == 1
