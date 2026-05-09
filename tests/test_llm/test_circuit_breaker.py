"""Tests for LLM circuit breaker.

Tests all state transitions, thread safety, time window expiry,
and integration with the provider chain.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

import threading
import time

from llm.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    def test_initial_state_is_closed(self):
        """New circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.get_state("kimi") == CircuitState.CLOSED

    def test_is_available_when_closed(self):
        """CLOSED state allows calls."""
        cb = CircuitBreaker()
        assert cb.is_available("kimi") is True

    def test_closed_to_open_after_threshold(self):
        """Circuit trips to OPEN after exceeding failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=60.0)

        for _ in range(3):
            cb.record_failure("kimi")

        assert cb.get_state("kimi") == CircuitState.OPEN
        assert cb.is_available("kimi") is False

    def test_open_to_half_open_after_cooldown(self):
        """OPEN transitions to HALF_OPEN after cooldown."""
        cb = CircuitBreaker(
            failure_threshold=2, cooldown_seconds=0.1, failure_window_seconds=60.0
        )

        # Trip the circuit
        cb.record_failure("kimi")
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

        # Wait for cooldown
        time.sleep(0.15)

        # is_available triggers transition to HALF_OPEN
        assert cb.is_available("kimi") is True
        assert cb.get_state("kimi") == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """HALF_OPEN transitions to CLOSED on success."""
        cb = CircuitBreaker(
            failure_threshold=2, cooldown_seconds=0.1, failure_window_seconds=60.0
        )

        # Trip the circuit
        cb.record_failure("kimi")
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

        # Wait for cooldown to enter HALF_OPEN
        time.sleep(0.15)
        cb.is_available("kimi")  # Trigger transition
        assert cb.get_state("kimi") == CircuitState.HALF_OPEN

        # Record success
        cb.record_success("kimi")
        assert cb.get_state("kimi") == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """HALF_OPEN re-opens on failure."""
        cb = CircuitBreaker(
            failure_threshold=2, cooldown_seconds=0.1, failure_window_seconds=60.0
        )

        # Trip the circuit
        cb.record_failure("kimi")
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

        # Wait for cooldown
        time.sleep(0.15)
        cb.is_available("kimi")  # Trigger transition
        assert cb.get_state("kimi") == CircuitState.HALF_OPEN

        # Record failure
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

    def test_success_resets_failure_count_in_closed(self):
        """Success in CLOSED state resets failure count."""
        cb = CircuitBreaker(failure_threshold=5, failure_window_seconds=60.0)

        # Record some failures but don't trip
        for _ in range(3):
            cb.record_failure("kimi")

        assert cb.get_failure_count("kimi") == 3
        assert cb.get_state("kimi") == CircuitState.CLOSED

        # Success resets
        cb.record_success("kimi")
        assert cb.get_failure_count("kimi") == 0


class TestCircuitBreakerTimeWindow:
    """Tests for time window expiry behavior."""

    def test_old_failures_expire(self):
        """Failures outside the time window are pruned."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=0.2)

        # Record 2 failures
        cb.record_failure("kimi")
        cb.record_failure("kimi")

        # Wait for window to expire
        time.sleep(0.25)

        # Record 1 more failure - old ones should be pruned
        cb.record_failure("kimi")

        # Only 1 failure in window (not enough to trip)
        assert cb.get_state("kimi") == CircuitState.CLOSED
        assert cb.get_failure_count("kimi") == 1

    def test_failures_within_window_trip_circuit(self):
        """Failures within the time window trip the circuit."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=5.0)

        cb.record_failure("kimi")
        cb.record_failure("kimi")
        cb.record_failure("kimi")

        assert cb.get_state("kimi") == CircuitState.OPEN


class TestCircuitBreakerThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_record_failure(self):
        """Concurrent failure recordings don't cause data corruption."""
        cb = CircuitBreaker(failure_threshold=100, failure_window_seconds=60.0)
        num_threads = 10
        failures_per_thread = 10

        def record_failures():
            for _ in range(failures_per_thread):
                cb.record_failure("kimi")

        threads = [threading.Thread(target=record_failures) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All failures should be recorded
        assert cb.get_failure_count("kimi") == num_threads * failures_per_thread

    def test_concurrent_state_transitions(self):
        """Concurrent state transitions are consistent."""
        cb = CircuitBreaker(
            failure_threshold=5, failure_window_seconds=60.0, cooldown_seconds=0.05
        )

        errors = []

        def writer():
            try:
                for _ in range(50):
                    cb.record_failure("kimi")
                    cb.record_success("kimi")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    state = cb.get_state("kimi")
                    assert state in (
                        CircuitState.CLOSED,
                        CircuitState.OPEN,
                        CircuitState.HALF_OPEN,
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestCircuitBreakerMultipleProviders:
    """Tests for independent circuit tracking per provider."""

    def test_independent_provider_states(self):
        """Each provider has independent circuit state."""
        cb = CircuitBreaker(failure_threshold=2, failure_window_seconds=60.0)

        # Trip kimi's circuit
        cb.record_failure("kimi")
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

        # zai should still be CLOSED
        assert cb.get_state("zai") == CircuitState.CLOSED
        assert cb.is_available("zai") is True

    def test_reset_specific_provider(self):
        """Reset only affects the specified provider."""
        cb = CircuitBreaker(failure_threshold=2, failure_window_seconds=60.0)

        # Trip both
        cb.record_failure("kimi")
        cb.record_failure("kimi")
        cb.record_failure("zai")
        cb.record_failure("zai")

        # Reset only kimi
        cb.reset("kimi")
        assert cb.get_state("kimi") == CircuitState.CLOSED
        assert cb.get_state("zai") == CircuitState.OPEN

    def test_reset_all_providers(self):
        """Reset all resets every provider."""
        cb = CircuitBreaker(failure_threshold=2, failure_window_seconds=60.0)

        cb.record_failure("kimi")
        cb.record_failure("kimi")
        cb.record_failure("zai")
        cb.record_failure("zai")

        cb.reset_all()
        assert cb.get_state("kimi") == CircuitState.CLOSED
        assert cb.get_state("zai") == CircuitState.CLOSED


class TestCircuitBreakerGetAllStates:
    """Tests for get_all_states reporting."""

    def test_empty_when_no_providers_tracked(self):
        """No states when no providers have been checked."""
        cb = CircuitBreaker()
        assert cb.get_all_states() == {}

    def test_returns_all_tracked_providers(self):
        """Returns state info for all tracked providers."""
        cb = CircuitBreaker(failure_threshold=3, failure_window_seconds=60.0)

        cb.record_failure("kimi")
        cb.record_failure("zai")
        cb.record_failure("zai")
        cb.record_failure("zai")

        states = cb.get_all_states()
        assert "kimi" in states
        assert "zai" in states
        assert states["kimi"]["state"] == "CLOSED"
        assert states["zai"]["state"] == "OPEN"

    def test_half_open_max_attempts(self):
        """HALF_OPEN respects max attempts limit."""
        cb = CircuitBreaker(
            failure_threshold=1,
            cooldown_seconds=0.05,
            half_open_max_attempts=1,
            failure_window_seconds=60.0,
        )

        # Trip
        cb.record_failure("kimi")
        assert cb.get_state("kimi") == CircuitState.OPEN

        # Wait for cooldown
        time.sleep(0.1)
        assert cb.is_available("kimi") is True  # First probe allowed
        assert cb.get_state("kimi") == CircuitState.HALF_OPEN

        # Second call in half-open: already used the one attempt
        assert cb.is_available("kimi") is False
