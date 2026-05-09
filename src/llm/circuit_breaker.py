"""Circuit breaker for LLM provider fault tolerance.

Provides proactive failure detection by tracking provider failures and
preventing calls to providers that are known to be down.

Three states:
- CLOSED: Provider is healthy, calls allowed normally
- OPEN: Provider has failed too many times, calls are skipped
- HALF_OPEN: Testing recovery, allowing one probe call

Thread-safe implementation using threading.Lock for use from both
sync and async contexts.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()  # Healthy - calls flow normally
    OPEN = auto()  # Failed - calls are rejected
    HALF_OPEN = auto()  # Testing recovery - one probe allowed


@dataclass
class CircuitRecord:
    """Per-provider circuit breaker state."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0
    half_open_attempts: int = 0
    failure_timestamps: list[float] = field(default_factory=list)


class CircuitBreaker:
    """Circuit breaker for LLM providers.

    Tracks failure counts per provider within a configurable time window.
    When failures exceed the threshold, the circuit opens and calls to that
    provider are skipped. After a cooldown period, the circuit transitions
    to half-open and allows one test call. If it succeeds, the circuit closes.
    If it fails, the circuit re-opens.

    Thread safety: All state mutations are protected by a threading.Lock.

    Usage:
        cb = CircuitBreaker()
        if cb.is_available("kimi"):
            try:
                result = await call_provider("kimi")
                cb.record_success("kimi")
            except Exception:
                cb.record_failure("kimi")
        else:
            logger.info("Skipping kimi: circuit is open")
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        failure_window_seconds: float = 60.0,
        cooldown_seconds: float = 30.0,
        half_open_max_attempts: int = 1,
    ):
        """Initialize the circuit breaker.

        Args:
            failure_threshold: Number of failures within window to trip the circuit
            failure_window_seconds: Time window in seconds for counting failures
            cooldown_seconds: Time to wait before transitioning OPEN -> HALF_OPEN
            half_open_max_attempts: Number of probe calls allowed in HALF_OPEN state
        """
        self._failure_threshold = failure_threshold
        self._failure_window_seconds = failure_window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._half_open_max_attempts = half_open_max_attempts
        self._circuits: dict[str, CircuitRecord] = {}
        self._lock = threading.RLock()

    def _get_or_create_circuit(self, provider: str) -> CircuitRecord:
        """Get or create a circuit record for a provider.

        Args:
            provider: Provider name

        Returns:
            CircuitRecord for the provider
        """
        if provider not in self._circuits:
            self._circuits[provider] = CircuitRecord()
        return self._circuits[provider]

    def _prune_old_failures(self, record: CircuitRecord) -> None:
        """Remove failure timestamps outside the current window.

        Args:
            record: CircuitRecord to prune
        """
        cutoff = time.monotonic() - self._failure_window_seconds
        record.failure_timestamps = [
            ts for ts in record.failure_timestamps if ts > cutoff
        ]
        record.failure_count = len(record.failure_timestamps)

    def is_available(self, provider: str) -> bool:
        """Check if a provider is available for calls.

        CLOSED -> available
        HALF_OPEN -> available (probe call allowed)
        OPEN -> unavailable (unless cooldown expired -> transitions to HALF_OPEN)

        Args:
            provider: Provider name

        Returns:
            True if the provider can be called
        """
        with self._lock:
            record = self._get_or_create_circuit(provider)

            if record.state == CircuitState.CLOSED:
                return True

            if record.state == CircuitState.OPEN:
                # Check if cooldown has elapsed
                elapsed = time.monotonic() - record.opened_at
                if elapsed >= self._cooldown_seconds:
                    old_state = record.state
                    record.state = CircuitState.HALF_OPEN
                    record.half_open_attempts = 0
                    logger.info(
                        "Circuit breaker for %s: %s -> %s (cooldown elapsed after %.1fs)",
                        provider,
                        old_state.name,
                        record.state.name,
                        elapsed,
                    )
                    return True
                return False

            if record.state == CircuitState.HALF_OPEN:
                # Allow limited probe calls
                if record.half_open_attempts < self._half_open_max_attempts:
                    record.half_open_attempts += 1
                    return True
                return False

            return True

    def record_success(self, provider: str) -> None:
        """Record a successful call to a provider.

        If the circuit was HALF_OPEN, this transitions it to CLOSED.
        If the circuit was CLOSED, this resets the failure count.

        Args:
            provider: Provider name
        """
        with self._lock:
            record = self._get_or_create_circuit(provider)
            record.last_success_time = time.monotonic()

            if record.state == CircuitState.HALF_OPEN:
                old_state = record.state
                record.state = CircuitState.CLOSED
                record.failure_count = 0
                record.failure_timestamps.clear()
                record.half_open_attempts = 0
                logger.info(
                    "Circuit breaker for %s: %s -> %s (probe call succeeded)",
                    provider,
                    old_state.name,
                    record.state.name,
                )
            elif record.state == CircuitState.CLOSED:
                # Reset failure tracking on success
                record.failure_count = 0
                record.failure_timestamps.clear()

    def record_failure(self, provider: str) -> None:
        """Record a failed call to a provider.

        If the circuit was CLOSED and failures exceed threshold, trips to OPEN.
        If the circuit was HALF_OPEN, re-opens the circuit.

        Args:
            provider: Provider name
        """
        with self._lock:
            record = self._get_or_create_circuit(provider)
            now = time.monotonic()

            if record.state == CircuitState.HALF_OPEN:
                # Probe call failed, re-open
                old_state = record.state
                record.state = CircuitState.OPEN
                record.opened_at = now
                record.failure_count += 1
                record.failure_timestamps.append(now)
                logger.info(
                    "Circuit breaker for %s: %s -> %s (probe call failed)",
                    provider,
                    old_state.name,
                    record.state.name,
                )
                return

            if record.state == CircuitState.CLOSED:
                record.failure_timestamps.append(now)
                self._prune_old_failures(record)
                record.last_failure_time = now

                if record.failure_count >= self._failure_threshold:
                    old_state = record.state
                    record.state = CircuitState.OPEN
                    record.opened_at = now
                    logger.info(
                        "Circuit breaker for %s: %s -> %s "
                        "(%d failures in %.0fs window, threshold=%d)",
                        provider,
                        old_state.name,
                        record.state.name,
                        record.failure_count,
                        self._failure_window_seconds,
                        self._failure_threshold,
                    )

    def get_state(self, provider: str) -> CircuitState:
        """Get the current circuit state for a provider.

        Also triggers OPEN -> HALF_OPEN transition if cooldown has elapsed.

        Args:
            provider: Provider name

        Returns:
            Current CircuitState
        """
        # is_available handles the state transition check
        self.is_available(provider)
        with self._lock:
            record = self._get_or_create_circuit(provider)
            return record.state

    def get_failure_count(self, provider: str) -> int:
        """Get the current failure count for a provider.

        Args:
            provider: Provider name

        Returns:
            Number of failures in the current window
        """
        with self._lock:
            record = self._get_or_create_circuit(provider)
            self._prune_old_failures(record)
            return record.failure_count

    def reset(self, provider: str) -> None:
        """Manually reset a provider's circuit to CLOSED.

        Args:
            provider: Provider name
        """
        with self._lock:
            if provider in self._circuits:
                old_state = self._circuits[provider].state
                self._circuits[provider] = CircuitRecord()
                logger.info(
                    "Circuit breaker for %s: %s -> CLOSED (manual reset)",
                    provider,
                    old_state.name,
                )

    def reset_all(self) -> None:
        """Reset all provider circuits to CLOSED."""
        with self._lock:
            for provider in list(self._circuits.keys()):
                old_state = self._circuits[provider].state
                self._circuits[provider] = CircuitRecord()
                logger.info(
                    "Circuit breaker for %s: %s -> CLOSED (reset all)",
                    provider,
                    old_state.name,
                )

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get states of all tracked providers.

        Returns:
            Dictionary mapping provider names to their circuit state info
        """
        with self._lock:
            result = {}
            for provider, record in self._circuits.items():
                self._prune_old_failures(record)
                result[provider] = {
                    "state": record.state.name,
                    "failure_count": record.failure_count,
                    "last_failure_time": record.last_failure_time,
                    "last_success_time": record.last_success_time,
                    "opened_at": record.opened_at,
                }
            return result


__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "CircuitRecord",
]
