"""Circuit breaker pattern implementation for resilient service calls.

Provides a reusable circuit breaker component that prevents cascading failures
by temporarily blocking calls to failing services.

Pattern states:
- CLOSED: Normal operation, calls pass through
- OPEN: Service failing, calls fail fast
- HALF_OPEN: Testing if service recovered

Usage:
    cb = CircuitBreaker(failure_threshold=5, timeout_seconds=60)

    # Method 1: Using call() wrapper
    result = cb.call(external_service, arg1, arg2)

    # Method 2: Manual control
    if cb.can_execute():
        try:
            result = external_service()
            cb.record_success()
        except Exception:
            cb.record_failure()
            raise

For ST-PAPER-005: Circuit Breakers Core
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Failing fast
    HALF_OPEN = auto()  # Testing recovery


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(
        self, message: str = "Circuit breaker is open", last_error: str | None = None
    ):
        super().__init__(message)
        self.last_error = last_error

    def __str__(self) -> str:
        if self.last_error:
            return f"{self.args[0]} (last error: {self.last_error})"
        return self.args[0]


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""

    failure_count: int = 0
    success_count: int = 0
    rejection_count: int = 0
    state_transition_count: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    last_state_change: float = field(default_factory=time.time)
    consecutive_successes: int = 0
    consecutive_failures: int = 0

    def record_success(self) -> None:
        """Record a successful call."""
        self.success_count += 1
        self.last_success_time = time.time()
        self.consecutive_successes += 1
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_failures += 1
        self.consecutive_successes = 0

    def record_rejection(self) -> None:
        """Record a rejected call (circuit open)."""
        self.rejection_count += 1

    def record_state_transition(self) -> None:
        """Record a state transition."""
        self.state_transition_count += 1
        self.last_state_change = time.time()
        self.consecutive_successes = 0
        self.consecutive_failures = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "rejection_count": self.rejection_count,
            "state_transition_count": self.state_transition_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change": self.last_state_change,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
        }


class CircuitBreaker:
    """Circuit breaker for resilient service calls.

    Implements the circuit breaker pattern to prevent cascading failures
    when calling external services. Tracks failures and automatically
    transitions between states based on configured thresholds.

    Thread-safe implementation using locks.

    Example:
        >>> cb = CircuitBreaker(
        ...     failure_threshold=5,
        ...     timeout_seconds=60,
        ...     half_open_max_calls=3
        ... )
        >>> try:
        ...     result = cb.call(redis_client.get, "key")
        ... except CircuitBreakerOpen:
        ...     # Handle circuit open - fail fast
        ...     result = None
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3,
        name: str = "default",
        expected_exception: type[Exception] = Exception,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Seconds to wait before trying half-open
            half_open_max_calls: Max calls allowed in half-open state
            name: Circuit breaker identifier for logging
            expected_exception: Exception type that triggers failure counting
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self.name = name
        self.expected_exception = expected_exception

        self._state = CircuitBreakerState.CLOSED
        self._metrics = CircuitBreakerMetrics()
        self._half_open_calls = 0
        self._last_error: str | None = None

        self._lock = threading.RLock()

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"threshold={failure_threshold}, timeout={timeout_seconds}s, "
            f"half_open_max={half_open_max_calls}"
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        with self._lock:
            return self._state

    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Current metrics (copy)."""
        with self._lock:
            # Return a copy to prevent external mutation
            return CircuitBreakerMetrics(
                failure_count=self._metrics.failure_count,
                success_count=self._metrics.success_count,
                rejection_count=self._metrics.rejection_count,
                state_transition_count=self._metrics.state_transition_count,
                last_failure_time=self._metrics.last_failure_time,
                last_success_time=self._metrics.last_success_time,
                last_state_change=self._metrics.last_state_change,
                consecutive_successes=self._metrics.consecutive_successes,
                consecutive_failures=self._metrics.consecutive_failures,
            )

    def can_execute(self) -> bool:
        """Check if a call can be executed.

        Returns:
            True if call should proceed, False if circuit is open
        """
        with self._lock:
            return self._can_execute()

    def _can_execute(self) -> bool:
        """Internal check without lock (caller must hold lock)."""
        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.OPEN:
            # Check if timeout has elapsed
            elapsed = time.time() - self._metrics.last_state_change
            if elapsed >= self.timeout_seconds:
                logger.info(
                    f"CircuitBreaker '{self.name}': Timeout elapsed ({elapsed:.1f}s), "
                    f"transitioning to HALF_OPEN"
                )
                self._transition_to(CircuitBreakerState.HALF_OPEN)
                # Fall through to HALF_OPEN logic
            else:
                return False

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state."""
        old_state = self._state
        if old_state != new_state:
            self._state = new_state
            self._metrics.record_state_transition()
            # Reset half_open_calls when transitioning to CLOSED or HALF_OPEN
            if new_state in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN):
                self._half_open_calls = 0
            logger.warning(
                f"CircuitBreaker '{self.name}': {old_state.name} -> {new_state.name}"
            )

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception raised by func
        """
        with self._lock:
            if not self._can_execute():
                self._metrics.record_rejection()
                logger.debug(
                    f"CircuitBreaker '{self.name}': Call rejected (state={self._state.name})"
                )
                raise CircuitBreakerOpen(
                    f"Circuit '{self.name}' is {self._state.name}",
                    last_error=self._last_error,
                )

        # Execute outside lock to minimize contention
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except self.expected_exception as e:
            self.record_failure(str(e))
            raise

    def record_success(self) -> None:
        """Record a successful call.

        Should be called when a protected call succeeds.
        """
        with self._lock:
            self._metrics.record_success()
            logger.debug(
                f"CircuitBreaker '{self.name}': Success recorded "
                f"(consecutive={self._metrics.consecutive_successes})"
            )

            if self._state == CircuitBreakerState.HALF_OPEN:
                # If we've had enough consecutive successes, close the circuit
                if self._metrics.consecutive_successes >= self.half_open_max_calls:
                    logger.info(
                        f"CircuitBreaker '{self.name}': Recovery confirmed, "
                        f"closing circuit"
                    )
                    self._transition_to(CircuitBreakerState.CLOSED)
                    self._last_error = None

    def record_failure(self, error: str | None = None) -> None:
        """Record a failed call.

        Should be called when a protected call fails.

        Args:
            error: Error message for logging
        """
        with self._lock:
            self._last_error = error
            self._metrics.record_failure()
            logger.debug(
                f"CircuitBreaker '{self.name}': Failure recorded "
                f"(consecutive={self._metrics.consecutive_failures}, error={error})"
            )

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                logger.warning(
                    f"CircuitBreaker '{self.name}': Failure in HALF_OPEN, "
                    f"re-opening circuit"
                )
                self._transition_to(CircuitBreakerState.OPEN)
            elif self._state == CircuitBreakerState.CLOSED:
                # Check if we should open the circuit
                if self._metrics.consecutive_failures >= self.failure_threshold:
                    logger.warning(
                        f"CircuitBreaker '{self.name}': Failure threshold reached "
                        f"({self.failure_threshold}), opening circuit"
                    )
                    self._transition_to(CircuitBreakerState.OPEN)

    def force_open(self, reason: str = "manual") -> None:
        """Force circuit to open state.

        Args:
            reason: Reason for forcing open
        """
        with self._lock:
            logger.warning(f"CircuitBreaker '{self.name}': Force opened ({reason})")
            self._transition_to(CircuitBreakerState.OPEN)

    def force_close(self, reason: str = "manual") -> None:
        """Force circuit to closed state.

        Args:
            reason: Reason for forcing close
        """
        with self._lock:
            logger.info(f"CircuitBreaker '{self.name}': Force closed ({reason})")
            self._transition_to(CircuitBreakerState.CLOSED)
            self._half_open_calls = 0
            self._last_error = None

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            logger.info(f"CircuitBreaker '{self.name}': Reset")
            self._state = CircuitBreakerState.CLOSED
            self._metrics = CircuitBreakerMetrics()
            self._half_open_calls = 0
            self._last_error = None

    def get_state_dict(self) -> dict[str, Any]:
        """Get current state as dictionary for monitoring.

        Returns:
            State dictionary
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.name,
                "failure_threshold": self.failure_threshold,
                "timeout_seconds": self.timeout_seconds,
                "half_open_max_calls": self.half_open_max_calls,
                "half_open_calls": self._half_open_calls,
                "last_error": self._last_error,
                "metrics": self._metrics.to_dict(),
            }

    def __enter__(self) -> CircuitBreaker:
        """Context manager entry."""
        if not self.can_execute():
            raise CircuitBreakerOpen(
                f"Circuit '{self.name}' is {self._state.name}",
                last_error=self._last_error,
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        if exc_type is None:
            self.record_success()
        elif issubclass(exc_type, self.expected_exception):
            self.record_failure(str(exc_val) if exc_val else None)


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers.

    Provides centralized management and monitoring of circuit breakers
    across the application.

    Example:
        >>> registry = CircuitBreakerRegistry()
        >>> redis_cb = registry.get_or_create("redis", failure_threshold=5)
        >>> api_cb = registry.get_or_create("external_api", timeout_seconds=30)
    """

    _instance: CircuitBreakerRegistry | None = None
    _lock = threading.Lock()

    def __new__(cls) -> CircuitBreakerRegistry:
        """Singleton pattern for global registry access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers: dict[str, CircuitBreaker] = {}
                    cls._instance._registry_lock = threading.RLock()
        return cls._instance

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3,
        expected_exception: type[Exception] = Exception,
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one.

        Args:
            name: Circuit breaker identifier
            failure_threshold: Failures before opening
            timeout_seconds: Seconds before half-open
            half_open_max_calls: Max calls in half-open
            expected_exception: Exception type to catch

        Returns:
            CircuitBreaker instance
        """
        with self._registry_lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    timeout_seconds=timeout_seconds,
                    half_open_max_calls=half_open_max_calls,
                    name=name,
                    expected_exception=expected_exception,
                )
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get circuit breaker by name.

        Args:
            name: Circuit breaker identifier

        Returns:
            CircuitBreaker or None if not found
        """
        with self._registry_lock:
            return self._breakers.get(name)

    def register(self, name: str, breaker: CircuitBreaker) -> None:
        """Register a circuit breaker.

        Args:
            name: Circuit breaker identifier
            breaker: CircuitBreaker instance
        """
        with self._registry_lock:
            self._breakers[name] = breaker

    def unregister(self, name: str) -> CircuitBreaker | None:
        """Unregister a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Removed CircuitBreaker or None
        """
        with self._registry_lock:
            return self._breakers.pop(name, None)

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get states of all registered circuit breakers.

        Returns:
            Dictionary mapping names to state dictionaries
        """
        with self._registry_lock:
            return {
                name: breaker.get_state_dict()
                for name, breaker in self._breakers.items()
            }

    def reset_all(self) -> None:
        """Reset all registered circuit breakers."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.reset()

    def force_open_all(self, reason: str = "manual") -> None:
        """Force open all registered circuit breakers.

        Args:
            reason: Reason for forcing open
        """
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.force_open(reason)

    def force_close_all(self, reason: str = "manual") -> None:
        """Force close all registered circuit breakers.

        Args:
            reason: Reason for forcing close
        """
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.force_close(reason)
