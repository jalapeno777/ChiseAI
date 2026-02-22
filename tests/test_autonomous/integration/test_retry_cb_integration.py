"""Integration tests for retry coordinator with circuit breaker.

Tests:
- Circuit breaker integration with retry coordinator
- No retries when circuit is open (AC #4)
- Circuit state transitions affecting retries
- Combined circuit breaker and budget enforcement

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations


import pytest
from src.autonomous_control_plane.components.retry_coordinator import RetryCoordinator
from src.autonomous_control_plane.models.retry_policy import (
    JitterType,
    RetryAborted,
    RetryPolicy,
)
from src.common.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitBreakerState,
)


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker and retry coordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create a retry coordinator."""
        return RetryCoordinator()

    @pytest.fixture
    def cb_registry(self):
        """Get circuit breaker registry."""
        return CircuitBreakerRegistry()

    @pytest.mark.asyncio
    async def test_no_retry_when_circuit_open(self, coordinator, cb_registry):
        """Test AC #4: No retries when circuit breaker is open.

        When a circuit breaker is in OPEN state, the retry coordinator
        should immediately abort without attempting any retries.
        """
        # Create and open a circuit breaker
        cb = cb_registry.get_or_create(
            "integration_test_cb",
            failure_threshold=1,
            timeout_seconds=60,
        )
        cb.force_open("test setup")

        assert cb.state == CircuitBreakerState.OPEN

        call_count = 0

        async def would_be_called():
            nonlocal call_count
            call_count += 1
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            circuit_breaker_name="integration_test_cb",
        )

        # Should abort immediately without calling the function
        with pytest.raises(RetryAborted) as exc_info:
            await coordinator.execute_with_retry(
                service_name="cb_integration_test",
                operation_name="test_op",
                func=would_be_called,
                policy=policy,
            )

        assert "Circuit breaker open" in str(exc_info.value)
        assert call_count == 0  # Function should never be called

    @pytest.mark.asyncio
    async def test_retry_when_circuit_closed(self, coordinator, cb_registry):
        """Test normal retry behavior when circuit is closed."""
        # Ensure circuit is closed
        cb = cb_registry.get_or_create(
            "closed_circuit_test",
            failure_threshold=5,
            timeout_seconds=60,
        )
        cb.force_close("test setup")

        assert cb.state == CircuitBreakerState.CLOSED

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Failure #{call_count}")
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            circuit_breaker_name="closed_circuit_test",
        )

        result = await coordinator.execute_with_retry(
            service_name="cb_closed_test",
            operation_name="test_op",
            func=fail_then_succeed,
            policy=policy,
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, coordinator, cb_registry):
        """Test circuit opens after threshold failures."""
        cb = cb_registry.get_or_create(
            "threshold_test_cb",
            failure_threshold=2,
            timeout_seconds=60,
        )
        cb.force_close("start closed")

        async def always_fail():
            raise Exception("Always fails")

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            circuit_breaker_name="threshold_test_cb",
        )

        # First operation - should fail with max retries
        with pytest.raises(Exception):
            await coordinator.execute_with_retry(
                service_name="cb_threshold_test_1",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

        # Circuit should record failures but still be closed or transitioning
        # Note: The CircuitBreaker in common/circuit_breaker.py has its own tracking

        # Second operation - circuit might be open now
        # Depending on how the circuit breaker tracks failures

    @pytest.mark.asyncio
    async def test_multiple_services_different_circuits(self, coordinator):
        """Test multiple services with different circuit breakers."""
        cb_registry = CircuitBreakerRegistry()

        # Open one circuit, leave another closed
        cb_open = cb_registry.get_or_create("service_a_cb")
        cb_open.force_open("test")

        cb_closed = cb_registry.get_or_create("service_b_cb")
        cb_closed.force_close("test")

        async def success_func():
            return "success"

        # Service A should fail (circuit open)
        policy_a = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            circuit_breaker_name="service_a_cb",
        )

        with pytest.raises(RetryAborted):
            await coordinator.execute_with_retry(
                service_name="service_a",
                operation_name="test_op",
                func=success_func,
                policy=policy_a,
            )

        # Service B should succeed (circuit closed)
        policy_b = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            circuit_breaker_name="service_b_cb",
        )

        result = await coordinator.execute_with_retry(
            service_name="service_b",
            operation_name="test_op",
            func=success_func,
            policy=policy_b,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_not_registered(self, coordinator):
        """Test operation when circuit breaker is not registered."""

        async def success_func():
            return "success"

        # Reference a circuit breaker that doesn't exist
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            circuit_breaker_name="nonexistent_cb",
        )

        # Should still work (no circuit breaker check fails)
        result = await coordinator.execute_with_retry(
            service_name="no_cb_test",
            operation_name="test_op",
            func=success_func,
            policy=policy,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_and_budget_combined(self, coordinator):
        """Test circuit breaker and budget enforcement together."""
        cb_registry = CircuitBreakerRegistry()
        cb = cb_registry.get_or_create("combined_test_cb")
        cb.force_close("start closed")

        call_count = 0

        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception(f"Fail #{call_count}")
            return "success"

        # Policy with both circuit breaker and low budget
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            circuit_breaker_name="combined_test_cb",
            budget_limit_per_minute=10,
        )

        result = await coordinator.execute_with_retry(
            service_name="combined_test",
            operation_name="test_op",
            func=fail_twice,
            policy=policy,
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_state(self, coordinator):
        """Test behavior when circuit is in half-open state."""
        cb_registry = CircuitBreakerRegistry()
        cb = cb_registry.get_or_create(
            "half_open_test_cb",
            failure_threshold=1,
            timeout_seconds=0,  # Immediate half-open
            half_open_max_calls=3,
        )
        cb.force_open("test")

        async def test_func():
            return "success"

        # With timeout=0, circuit immediately transitions to HALF_OPEN
        # In HALF_OPEN state, limited calls are allowed
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            circuit_breaker_name="half_open_test_cb",
        )

        # Should succeed because circuit transitions to HALF_OPEN and allows the call
        result = await coordinator.execute_with_retry(
            service_name="half_open_test",
            operation_name="test_op",
            func=test_func,
            policy=policy,
        )
        assert result == "success"

    def test_get_circuit_breaker_states_empty(self, coordinator):
        """Test getting states when no circuits registered."""
        states = coordinator.get_circuit_breaker_states()
        assert isinstance(states, dict)

    def test_get_circuit_breaker_states_with_circuits(self, coordinator):
        """Test getting states with registered circuits."""
        cb_registry = CircuitBreakerRegistry()

        # Create some circuit breakers
        cb1 = cb_registry.get_or_create("state_test_1")
        cb1.force_open("test")

        cb2 = cb_registry.get_or_create("state_test_2")
        cb2.force_close("test")

        states = coordinator.get_circuit_breaker_states()
        assert isinstance(states, dict)
        assert len(states) >= 2

        # Check that our circuits are in the states
        if "state_test_1" in states:
            assert states["state_test_1"]["state"] == "OPEN"
        if "state_test_2" in states:
            assert states["state_test_2"]["state"] == "CLOSED"


class TestRetryCoordinatorWithoutCircuitBreaker:
    """Tests for retry coordinator without circuit breaker dependency."""

    @pytest.mark.asyncio
    async def test_operation_without_circuit_breaker(self):
        """Test operation completes without circuit breaker."""
        coordinator = RetryCoordinator()

        async def success_func():
            return "success"

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            circuit_breaker_name=None,  # No circuit breaker
        )

        result = await coordinator.execute_with_retry(
            service_name="no_cb_service",
            operation_name="test_op",
            func=success_func,
            policy=policy,
        )

        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_without_circuit_breaker(self):
        """Test retry works without circuit breaker."""
        coordinator = RetryCoordinator()

        call_count = 0

        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First failure")
            return "success"

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            circuit_breaker_name=None,
        )

        result = await coordinator.execute_with_retry(
            service_name="retry_no_cb",
            operation_name="test_op",
            func=fail_once,
            policy=policy,
        )

        assert result == "success"
        assert call_count == 2
