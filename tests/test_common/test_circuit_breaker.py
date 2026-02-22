"""Tests for circuit breaker pattern implementation."""

from __future__ import annotations

import threading
import time

import pytest

from common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitBreakerRegistry,
    CircuitBreakerState,
)


class TestCircuitBreakerState:
    """Test circuit breaker state machine."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_state_transitions_to_open_on_failures(self):
        """Circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record failures up to threshold
        cb.record_failure("error1")
        cb.record_failure("error2")
        assert cb.state == CircuitBreakerState.CLOSED

        # Third failure opens circuit
        cb.record_failure("error3")
        assert cb.state == CircuitBreakerState.OPEN

    def test_state_transitions_to_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)
        cb.record_failure("error")
        assert cb.state == CircuitBreakerState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        # can_execute should trigger transition to HALF_OPEN
        assert cb.can_execute()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_state_closes_after_half_open_successes(self):
        """Circuit closes after successful calls in HALF_OPEN."""
        cb = CircuitBreaker(
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_max_calls=2,
        )
        cb.record_failure("error")

        # Wait for timeout
        time.sleep(0.15)

        # First call in half-open
        assert cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Second call closes circuit
        assert cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_state_reopens_on_half_open_failure(self):
        """Circuit reopens if failure occurs in HALF_OPEN."""
        cb = CircuitBreaker(
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_max_calls=3,
        )
        cb.record_failure("error1")

        # Wait for timeout
        time.sleep(0.15)

        # Enter half-open
        assert cb.can_execute()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Failure in half-open reopens circuit
        cb.record_failure("error2")
        assert cb.state == CircuitBreakerState.OPEN


class TestCircuitBreakerCanExecute:
    """Test can_execute method."""

    def test_can_execute_returns_true_when_closed(self):
        """Calls allowed when circuit is closed."""
        cb = CircuitBreaker()
        assert cb.can_execute() is True

    def test_can_execute_returns_false_when_open(self):
        """Calls blocked when circuit is open."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")
        assert cb.can_execute() is False

    def test_can_execute_returns_true_after_timeout(self):
        """Calls allowed after timeout when open."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)
        cb.record_failure("error")
        assert cb.can_execute() is False

        time.sleep(0.15)
        assert cb.can_execute() is True

    def test_half_open_limits_calls(self):
        """Limited calls allowed in half-open state."""
        cb = CircuitBreaker(
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_max_calls=2,
        )
        cb.record_failure("error")

        time.sleep(0.15)

        # First two calls allowed
        assert cb.can_execute() is True
        assert cb.can_execute() is True

        # Third call blocked
        assert cb.can_execute() is False


class TestCircuitBreakerCall:
    """Test call method wrapper."""

    def test_call_executes_function_when_closed(self):
        """Function executed normally when circuit closed."""
        cb = CircuitBreaker()

        def add(a, b):
            return a + b

        result = cb.call(add, 2, 3)
        assert result == 5

    def test_call_raises_when_open(self):
        """CircuitBreakerOpen raised when circuit open."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")

        with pytest.raises(CircuitBreakerOpen):
            cb.call(lambda: "success")

    def test_call_records_success(self):
        """Successful call recorded."""
        cb = CircuitBreaker()

        cb.call(lambda: "success")

        assert cb.metrics.success_count == 1

    def test_call_records_failure(self):
        """Failed call recorded."""
        cb = CircuitBreaker(expected_exception=ValueError)

        def raise_error():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            cb.call(raise_error)

        assert cb.metrics.failure_count == 1

    def test_call_ignores_unexpected_exceptions(self):
        """Unexpected exceptions don't count as failures."""
        cb = CircuitBreaker(expected_exception=ValueError)

        def raise_type_error():
            raise TypeError("unexpected")

        with pytest.raises(TypeError):
            cb.call(raise_type_error)

        assert cb.metrics.failure_count == 0

    def test_call_includes_last_error_in_exception(self):
        """CircuitBreakerOpen includes last error message."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("connection refused")

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            cb.call(lambda: "success")

        assert "connection refused" in str(exc_info.value)


class TestCircuitBreakerMetrics:
    """Test metrics tracking."""

    def test_metrics_track_successes(self):
        """Success count tracked correctly."""
        cb = CircuitBreaker()

        cb.record_success()
        cb.record_success()

        assert cb.metrics.success_count == 2

    def test_metrics_track_failures(self):
        """Failure count tracked correctly."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()

        assert cb.metrics.failure_count == 2

    def test_metrics_track_rejections(self):
        """Rejection count tracked when circuit open."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")

        try:
            cb.call(lambda: "success")
        except CircuitBreakerOpen:
            pass

        assert cb.metrics.rejection_count == 1

    def test_metrics_track_state_transitions(self):
        """State transitions tracked."""
        cb = CircuitBreaker(
            failure_threshold=1, timeout_seconds=0.1, half_open_max_calls=1
        )

        # CLOSED -> OPEN
        cb.record_failure("error")
        assert cb.metrics.state_transition_count == 1

        # OPEN -> HALF_OPEN
        time.sleep(0.15)
        cb.can_execute()
        assert cb.metrics.state_transition_count == 2

        # HALF_OPEN -> CLOSED
        cb.record_success()
        assert cb.metrics.state_transition_count == 3

    def test_metrics_consecutive_tracking(self):
        """Consecutive success/failure tracking."""
        cb = CircuitBreaker()

        cb.record_success()
        cb.record_success()
        assert cb.metrics.consecutive_successes == 2
        assert cb.metrics.consecutive_failures == 0

        cb.record_failure()
        assert cb.metrics.consecutive_successes == 0
        assert cb.metrics.consecutive_failures == 1


class TestCircuitBreakerForceOperations:
    """Test force open/close operations."""

    def test_force_open_transitions_state(self):
        """Force open changes state to OPEN."""
        cb = CircuitBreaker()
        cb.force_open("test reason")
        assert cb.state == CircuitBreakerState.OPEN

    def test_force_close_transitions_state(self):
        """Force close changes state to CLOSED."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")
        assert cb.state == CircuitBreakerState.OPEN

        cb.force_close("test reason")
        assert cb.state == CircuitBreakerState.CLOSED

    def test_reset_clears_all_state(self):
        """Reset returns to initial state."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")
        cb.record_success()

        cb.reset()

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.success_count == 0


class TestCircuitBreakerContextManager:
    """Test context manager usage."""

    def test_context_manager_success(self):
        """Context manager records success on exit."""
        cb = CircuitBreaker()

        with cb:
            result = "success"

        assert cb.metrics.success_count == 1
        assert result == "success"

    def test_context_manager_failure(self):
        """Context manager records failure on exception."""
        cb = CircuitBreaker()

        with pytest.raises(ValueError), cb:
            raise ValueError("test")

        assert cb.metrics.failure_count == 1

    def test_context_manager_raises_when_open(self):
        """Context manager raises when circuit open."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("error")

        with pytest.raises(CircuitBreakerOpen), cb:
            pass


class TestCircuitBreakerThreadSafety:
    """Test thread safety."""

    def test_concurrent_calls_handled_safely(self):
        """Multiple threads can use circuit breaker safely."""
        cb = CircuitBreaker(failure_threshold=100)
        errors = []

        def worker():
            try:
                for _ in range(10):
                    cb.call(lambda: "success")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.metrics.success_count == 50

    def test_concurrent_state_transitions(self):
        """State transitions are thread-safe."""
        cb = CircuitBreaker(failure_threshold=10)

        def success_worker():
            for _ in range(20):
                cb.record_success()

        def failure_worker():
            for _ in range(20):
                cb.record_failure()

        threads = [
            threading.Thread(target=success_worker),
            threading.Thread(target=failure_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have recorded all operations
        assert cb.metrics.success_count == 20
        assert cb.metrics.failure_count == 20


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry."""

    def test_registry_is_singleton(self):
        """Registry is a singleton."""
        r1 = CircuitBreakerRegistry()
        r2 = CircuitBreakerRegistry()
        assert r1 is r2

    def test_get_or_create_creates_new(self):
        """Creates new circuit breaker if not exists."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()  # Clean state

        cb = registry.get_or_create("test")
        assert cb.name == "test"
        assert cb.state == CircuitBreakerState.CLOSED

    def test_get_or_create_returns_existing(self):
        """Returns existing circuit breaker."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        cb1 = registry.get_or_create("test")
        cb1.record_failure("error")

        cb2 = registry.get_or_create("test")
        assert cb1 is cb2
        assert cb2.metrics.failure_count == 1

    def test_get_returns_none_if_not_exists(self):
        """Get returns None for unknown circuit breaker."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        assert registry.get("unknown") is None

    def test_unregister_removes_circuit_breaker(self):
        """Unregister removes circuit breaker."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        cb = registry.get_or_create("test")
        removed = registry.unregister("test")

        assert removed is cb
        assert registry.get("test") is None

    def test_get_all_states_returns_all(self):
        """Returns states of all circuit breakers."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        registry.get_or_create("cb1")
        registry.get_or_create("cb2")

        states = registry.get_all_states()
        assert "cb1" in states
        assert "cb2" in states

    def test_reset_all_resets_all(self):
        """Reset all circuit breakers."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        cb1 = registry.get_or_create("cb1")
        cb2 = registry.get_or_create("cb2")
        cb1.record_failure("error")
        cb2.record_failure("error")

        registry.reset_all()

        assert cb1.state == CircuitBreakerState.CLOSED
        assert cb2.state == CircuitBreakerState.CLOSED

    def test_force_open_all(self):
        """Force open all circuit breakers."""
        registry = CircuitBreakerRegistry()
        registry._breakers.clear()

        cb1 = registry.get_or_create("cb1")
        cb2 = registry.get_or_create("cb2")

        registry.force_open_all("emergency")

        assert cb1.state == CircuitBreakerState.OPEN
        assert cb2.state == CircuitBreakerState.OPEN


class TestCircuitBreakerConfiguration:
    """Test configuration options."""

    def test_custom_failure_threshold(self):
        """Custom failure threshold respected."""
        cb = CircuitBreaker(failure_threshold=10)

        for i in range(9):
            cb.record_failure(f"error{i}")

        assert cb.state == CircuitBreakerState.CLOSED

        cb.record_failure("final")
        assert cb.state == CircuitBreakerState.OPEN

    def test_custom_timeout(self):
        """Custom timeout respected."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record_failure("error")

        assert cb.can_execute() is False

        time.sleep(0.06)
        assert cb.can_execute() is True

    def test_custom_half_open_max_calls(self):
        """Custom half-open max calls respected."""
        cb = CircuitBreaker(
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_max_calls=5,
        )
        cb.record_failure("error")

        time.sleep(0.15)

        # Allow up to 5 calls
        for _ in range(5):
            assert cb.can_execute() is True

        # 6th call blocked
        assert cb.can_execute() is False

    def test_custom_expected_exception(self):
        """Custom expected exception type respected."""
        cb = CircuitBreaker(expected_exception=ConnectionError)

        # ValueError should not count as failure
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("test")))

        assert cb.metrics.failure_count == 0

        # ConnectionError should count
        def raise_connection_error():
            raise ConnectionError("test")

        with pytest.raises(ConnectionError):
            cb.call(raise_connection_error)

        assert cb.metrics.failure_count == 1


class TestCircuitBreakerGetStateDict:
    """Test get_state_dict method."""

    def test_state_dict_contains_all_fields(self):
        """State dict includes all expected fields."""
        cb = CircuitBreaker(
            name="test_cb",
            failure_threshold=5,
            timeout_seconds=30,
            half_open_max_calls=3,
        )
        cb.record_failure("error")

        state = cb.get_state_dict()

        assert state["name"] == "test_cb"
        assert state["state"] == "CLOSED"
        assert state["failure_threshold"] == 5
        assert state["timeout_seconds"] == 30
        assert state["half_open_max_calls"] == 3
        assert state["last_error"] == "error"
        assert "metrics" in state

    def test_state_dict_metrics(self):
        """State dict includes metrics."""
        cb = CircuitBreaker()
        cb.record_success()
        cb.record_failure("err")

        state = cb.get_state_dict()
        metrics = state["metrics"]

        assert metrics["success_count"] == 1
        assert metrics["failure_count"] == 1
        assert "last_success_time" in metrics
        assert "last_failure_time" in metrics


class TestCircuitBreakerOpenException:
    """Test CircuitBreakerOpen exception."""

    def test_exception_message(self):
        """Exception includes message."""
        exc = CircuitBreakerOpen("custom message")
        assert "custom message" in str(exc)

    def test_exception_with_last_error(self):
        """Exception includes last error when provided."""
        exc = CircuitBreakerOpen("circuit open", last_error="connection refused")
        assert "connection refused" in str(exc)

    def test_exception_without_last_error(self):
        """Exception works without last error."""
        exc = CircuitBreakerOpen("circuit open")
        assert "circuit open" in str(exc)
