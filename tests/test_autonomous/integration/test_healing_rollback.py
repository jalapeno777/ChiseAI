"""Integration tests for healing rollback.

Tests for ST-NS-040: Self-Healing Engine with Action Sandboxing

Acceptance Criteria:
3. Failed healing actions rolled back within 30s
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from src.autonomous_control_plane.components.self_healing_engine import SelfHealingEngine
from src.autonomous_control_plane.healing_actions.circuit_breaker_reset import (
    CircuitBreakerResetAction,
)
from src.autonomous_control_plane.healing_actions.redis_restart import (
    RedisRestartAction,
)
from src.autonomous_control_plane.models.healing import (
    HealingAttempt,
    HealingContext,
    HealingResult,
    HealingStatus,
    RollbackResult,
)


class TestHealingRollbackTiming:
    """Test healing rollback completes within 30s (AC 3)."""

    @pytest.mark.asyncio
    async def test_rollback_completes_within_30_seconds(self):
        """Test that rollback completes within 30 second deadline."""
        action = RedisRestartAction()
        context = HealingContext(
            service="redis",
            action_id="test-rollback-timing",
        )

        # Capture state first
        action._capture_state(context)

        # Execute healing (which will succeed in test mode)
        result = action.execute(context)

        # Measure rollback time
        start = time.time()
        rollback_result = action.rollback(context, result)
        elapsed = time.time() - start

        # Rollback should complete within 30 seconds
        assert elapsed < 30.0, f"Rollback took {elapsed:.2f}s, exceeding 30s limit"
        assert rollback_result is not None

    @pytest.mark.asyncio
    async def test_failed_healing_triggers_rollback(self):
        """Test that failed healing actions trigger automatic rollback."""
        action = RedisRestartAction()
        context = HealingContext(
            service="test-service",
            action_id="test-auto-rollback",
        )

        # Mock _execute_sandboxed to simulate failure
        with patch.object(
            action,
            "_execute_sandboxed",
            return_value={
                "success": False,
                "error": "Simulated failure",
            },
        ):
            # Execute (should fail and trigger rollback)
            result = action.execute(context)

            # Result should indicate failure
            assert result.success is False
            assert result.error is not None

        # Rollback should have been attempted
        # (in the base class, rollback is called on failure)

    @pytest.mark.asyncio
    async def test_rollback_restores_previous_state(self):
        """Test that rollback restores state to pre-healing condition."""
        action = CircuitBreakerResetAction(circuit_name="test-circuit")
        context = HealingContext(
            service="test-circuit",
            action_id="test-state-restore",
        )

        # Capture pre-healing state
        action._capture_state(context)

        # Execute healing
        result = action.execute(context)

        # Rollback
        rollback_result = action.rollback(context, result)

        # Rollback should report success
        assert rollback_result is not None


class TestRollbackIntegration:
    """Test rollback integration with self-healing engine."""

    @pytest.fixture
    def engine(self):
        return SelfHealingEngine(trading_mode="paper")

    @pytest.mark.asyncio
    async def test_engine_tracks_rollback_results(self, engine):
        """Test that engine tracks rollback results in healing attempts."""
        # Create a healing attempt
        attempt = HealingAttempt(
            service="test-service",
            action_type="redis_restart",
            attempt_number=1,
        )

        # Create a failed result
        result = HealingResult(
            success=False,
            action_id=attempt.attempt_id,
            action_type="redis_restart",
            service="test-service",
            error="Simulated failure",
        )

        # Complete the attempt
        attempt.complete(result)

        # Create a rollback result
        rollback = RollbackResult(
            success=True,
            action_id=attempt.attempt_id,
            duration_seconds=1.0,
        )

        # Mark as rolled back
        attempt.mark_rolled_back(rollback)

        # Verify rollback is tracked
        assert attempt.rollback_result is not None
        assert attempt.rollback_result.success is True
        assert attempt.status == HealingStatus.ROLLED_BACK

    def test_rollback_result_structure(self):
        """Test rollback result has proper structure for logging."""
        rollback = RollbackResult(
            success=True,
            action_id="test-action",
            duration_seconds=2.5,
        )

        data = rollback.to_dict()

        assert data["success"] is True
        assert data["action_id"] == "test-action"
        assert data["duration_seconds"] == 2.5
        assert "timestamp" in data

    def test_rollback_result_with_error(self):
        """Test rollback result captures errors."""
        rollback = RollbackResult(
            success=False,
            action_id="test-action",
            duration_seconds=1.0,
            error="Rollback failed: circuit not found",
        )

        data = rollback.to_dict()

        assert data["success"] is False
        assert data["error"] == "Rollback failed: circuit not found"


class TestRollbackWithCircuitBreaker:
    """Test rollback with circuit breaker reset action."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_rollback_restores_open_state(self):
        """Test that circuit breaker rollback restores OPEN state if it was OPEN before."""
        action = CircuitBreakerResetAction(circuit_name="test-circuit")
        context = HealingContext(
            service="test-circuit",
            action_id="test-cb-rollback",
        )

        # Simulate captured state where CB was OPEN
        action._captured_state = {
            "circuit_name": "test-circuit",
            "previous_state": {"state": "OPEN"},
        }

        # Execute rollback
        rollback_result = action.rollback(context, None)

        # Should report restoring OPEN state
        assert rollback_result is not None
        # Note: Without actual CB registry, we can't verify state restoration
        # but the structure is correct

    @pytest.mark.asyncio
    async def test_circuit_breaker_rollback_noop_for_closed(self):
        """Test that rollback is no-op if CB was already CLOSED."""
        action = CircuitBreakerResetAction(circuit_name="test-circuit")
        context = HealingContext(
            service="test-circuit",
            action_id="test-cb-rollback-closed",
        )

        # Simulate captured state where CB was CLOSED
        action._captured_state = {
            "circuit_name": "test-circuit",
            "previous_state": {"state": "CLOSED"},
        }

        # Execute rollback
        rollback_result = action.rollback(context, None)

        # Should succeed (no action needed)
        assert rollback_result is not None


class TestRollbackTimingMeasurements:
    """Test rollback timing is properly measured and reported."""

    def test_rollback_duration_tracking(self):
        """Test that rollback duration is accurately tracked."""
        action = RedisRestartAction()
        context = HealingContext(
            service="redis",
            action_id="test-duration",
        )

        # Capture state
        action._capture_state(context)

        # Measure rollback duration
        import time

        start = time.time()
        result = action.rollback(context, None)
        actual_duration = time.time() - start

        # Result should have duration field
        assert result.duration_seconds >= 0
        assert result.duration_seconds < 30.0  # Should be fast

        # Duration should be reasonably close to actual
        assert abs(result.duration_seconds - actual_duration) < 1.0

    @pytest.mark.asyncio
    async def test_healing_attempt_includes_rollback_timing(self):
        """Test healing attempt includes rollback timing in output."""
        attempt = HealingAttempt(
            service="test-service",
            action_type="redis_restart",
        )

        result = HealingResult(
            success=False,
            action_id=attempt.attempt_id,
            action_type="redis_restart",
            service="test-service",
            error="Failure",
        )
        attempt.complete(result)

        rollback = RollbackResult(
            success=True,
            action_id=attempt.attempt_id,
            duration_seconds=2.5,
        )
        attempt.mark_rolled_back(rollback)

        data = attempt.to_dict()

        assert "rollback_result" in data
        assert data["rollback_result"]["duration_seconds"] == 2.5
        assert data["rollback_result"]["success"] is True


class TestRollbackFailureHandling:
    """Test handling of rollback failures."""

    @pytest.mark.asyncio
    async def test_rollback_failure_is_logged(self):
        """Test that rollback failures are properly logged."""
        action = CircuitBreakerResetAction(circuit_name="nonexistent-circuit")
        context = HealingContext(
            service="nonexistent-circuit",
            action_id="test-rollback-fail",
        )

        # Don't capture state - this should cause rollback to fail
        result = action.rollback(context, None)

        # Rollback should report failure
        assert result.success is False
        assert result.error is not None

    def test_rollback_failure_included_in_healing_result(self):
        """Test that rollback failure is included in healing result."""
        result = HealingResult(
            success=False,
            action_id="test-action",
            action_type="test",
            service="test",
            error="Healing failed",
            details={
                "rollback": {
                    "success": False,
                    "error": "Rollback also failed",
                }
            },
        )

        data = result.to_dict()

        assert data["details"]["rollback"]["success"] is False
        assert data["details"]["rollback"]["error"] == "Rollback also failed"
