#!/usr/bin/env python3
"""Circuit breaker integration for PR pipeline operations.

Provides circuit breaker protection for Gitea API calls and Discord notifications
with automatic state management and fallback behavior.

ST-AUTO-006: EP-NS-008 Integration for PR Pipeline
"""

from __future__ import annotations

import functools
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, TypeVar

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Failing, rejecting calls
    HALF_OPEN = auto()  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker."""

    failure_count: int = 0
    success_count: int = 0
    rejection_count: int = 0
    state_transitions: int = 0
    last_failure_time: float = field(default_factory=time.time)
    last_success_time: float = field(default_factory=time.time)


class CircuitBreaker:
    """Circuit breaker for PR pipeline operations.

    Protects against cascading failures by opening the circuit
    when failures exceed threshold, and closing after recovery.

    Example:
        >>> cb = CircuitBreaker("gitea_api", CircuitBreakerConfig())
        >>> result = cb.call(lambda: make_api_request())
        >>> if cb.is_open():
        ...     print("Circuit is open, using fallback")
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
        redis_client: Any | None = None,
    ):
        """Initialize circuit breaker.

        Args:
            name: Unique identifier for this circuit breaker
            config: Circuit breaker configuration
            redis_client: Optional Redis client for distributed state
        """
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._redis = redis_client
        self._state = CircuitBreakerState.CLOSED
        self._metrics = CircuitBreakerMetrics()
        self._half_open_calls = 0
        self._consecutive_successes = 0
        self._lock = None

        # Try to import threading lock if needed
        try:
            import threading

            self._lock = threading.RLock()
        except ImportError:
            pass

        logger.info(f"CircuitBreaker '{name}' initialized in {self._state.name} state")

    @property
    def name(self) -> str:
        """Get circuit breaker name."""
        return self._name

    @property
    def state(self) -> CircuitBreakerState:
        """Get current state."""
        self._check_auto_transition()
        return self._state

    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self.state == CircuitBreakerState.OPEN

    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitBreakerState.CLOSED

    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitBreakerState.HALF_OPEN

    def call(self, func: Callable[[], T], fallback: Callable[[], T] | None = None) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            fallback: Optional fallback function if circuit is open

        Returns:
            Result from func or fallback

        Raises:
            CircuitBreakerOpenError: If circuit is open and no fallback provided
            Exception: Any exception from func (if circuit allows)
        """
        # Check if we can execute
        if not self._can_execute():
            self._metrics.rejection_count += 1
            logger.warning(f"Circuit '{self._name}' is OPEN, rejecting call")

            if fallback:
                logger.info(f"Executing fallback for '{self._name}'")
                return fallback()

            raise CircuitBreakerOpenError(f"Circuit breaker '{self._name}' is open")

        # Execute the function
        try:
            result = func()
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    async def call_async(
        self,
        func: Callable[[], Any],
        fallback: Callable[[], Any] | None = None,
    ) -> Any:
        """Execute async function with circuit breaker protection.

        Args:
            func: Async function to execute
            fallback: Optional fallback function if circuit is open

        Returns:
            Result from func or fallback
        """
        import asyncio

        if not self._can_execute():
            self._metrics.rejection_count += 1
            logger.warning(f"Circuit '{self._name}' is OPEN, rejecting async call")

            if fallback:
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                return fallback()

            raise CircuitBreakerOpenError(f"Circuit breaker '{self._name}' is open")

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func()
            else:
                result = func()
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def _can_execute(self) -> bool:
        """Check if call can be executed."""
        self._check_auto_transition()

        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.OPEN:
            return False

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self._half_open_calls < self._config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def _check_auto_transition(self) -> None:
        """Check if automatic state transition is needed."""
        if self._state != CircuitBreakerState.OPEN:
            return

        # Check if recovery timeout has passed
        time_since_failure = time.time() - self._metrics.last_failure_time
        if time_since_failure >= self._config.recovery_timeout:
            logger.info(
                f"Circuit '{self._name}' transitioning OPEN -> HALF_OPEN "
                f"after {time_since_failure:.1f}s"
            )
            self._transition_to(CircuitBreakerState.HALF_OPEN)
            self._half_open_calls = 0
            self._consecutive_successes = 0

    def _record_success(self) -> None:
        """Record a successful call."""
        self._metrics.success_count += 1
        self._metrics.last_success_time = time.time()
        self._consecutive_successes += 1

        # Check if we should close the circuit
        if (
            self._state == CircuitBreakerState.HALF_OPEN
            and self._consecutive_successes >= self._config.success_threshold
        ):
            logger.info(
                f"Circuit '{self._name}' transitioning HALF_OPEN -> CLOSED "
                f"after {self._consecutive_successes} consecutive successes"
            )
            self._transition_to(CircuitBreakerState.CLOSED)
            self._metrics.failure_count = 0

    def _record_failure(self) -> None:
        """Record a failed call."""
        self._metrics.failure_count += 1
        self._metrics.last_failure_time = time.time()
        self._consecutive_successes = 0

        # Check if we should open the circuit
        if self._state == CircuitBreakerState.CLOSED:
            if self._metrics.failure_count >= self._config.failure_threshold:
                logger.warning(
                    f"Circuit '{self._name}' transitioning CLOSED -> OPEN "
                    f"after {self._metrics.failure_count} failures"
                )
                self._transition_to(CircuitBreakerState.OPEN)

        elif self._state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open goes back to open
            logger.warning(
                f"Circuit '{self._name}' transitioning HALF_OPEN -> OPEN "
                f"due to failure during recovery test"
            )
            self._transition_to(CircuitBreakerState.OPEN)

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._metrics.state_transitions += 1

        logger.info(
            f"Circuit '{self._name}' state change: {old_state.name} -> {new_state.name}"
        )

    def force_open(self, reason: str = "manual") -> None:
        """Manually open the circuit.

        Args:
            reason: Reason for manual open
        """
        logger.warning(f"Circuit '{self._name}' manually opened: {reason}")
        self._transition_to(CircuitBreakerState.OPEN)
        self._metrics.last_failure_time = time.time()

    def force_close(self, reason: str = "manual") -> None:
        """Manually close the circuit.

        Args:
            reason: Reason for manual close
        """
        logger.info(f"Circuit '{self._name}' manually closed: {reason}")
        self._transition_to(CircuitBreakerState.CLOSED)
        self._metrics.failure_count = 0
        self._consecutive_successes = 0
        self._half_open_calls = 0

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics."""
        return {
            "name": self._name,
            "state": self._state.name,
            "failure_count": self._metrics.failure_count,
            "success_count": self._metrics.success_count,
            "rejection_count": self._metrics.rejection_count,
            "state_transitions": self._metrics.state_transitions,
            "consecutive_successes": self._consecutive_successes,
            "half_open_calls": self._half_open_calls,
            "last_failure_time": self._metrics.last_failure_time,
            "last_success_time": self._metrics.last_success_time,
        }

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        logger.info(f"Circuit '{self._name}' reset to initial state")
        self._state = CircuitBreakerState.CLOSED
        self._metrics = CircuitBreakerMetrics()
        self._half_open_calls = 0
        self._consecutive_successes = 0


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    pass


class PRCircuitBreakerRegistry:
    """Registry for PR pipeline circuit breakers.

    Manages circuit breakers for different PR operations with
    integration to the ACP CircuitBreakerRegistry when available.
    """

    # Default circuit breaker configurations for PR operations
    DEFAULT_CONFIGS: dict[str, CircuitBreakerConfig] = {
        "gitea_api": CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=3,
            success_threshold=2,
        ),
        "discord_notifications": CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            half_open_max_calls=2,
            success_threshold=1,
        ),
        "redis_operations": CircuitBreakerConfig(
            failure_threshold=10,
            recovery_timeout=30.0,
            half_open_max_calls=5,
            success_threshold=3,
        ),
        "pr_merge_operations": CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=120.0,
            half_open_max_calls=2,
            success_threshold=1,
        ),
    }

    def __init__(self, redis_client: Any | None = None):
        """Initialize PR circuit breaker registry.

        Args:
            redis_client: Optional Redis client for distributed state
        """
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._redis = redis_client
        self._acp_registry = None

        # Try to integrate with ACP CircuitBreakerRegistry
        self._init_acp_integration()

    def _init_acp_integration(self) -> None:
        """Initialize integration with ACP CircuitBreakerRegistry."""
        try:
            from autonomous_control_plane.components.circuit_breaker_registry import (
                CircuitBreakerRegistry as ACPCircuitBreakerRegistry,
            )

            self._acp_registry = ACPCircuitBreakerRegistry()
            logger.info("ACP CircuitBreakerRegistry integration enabled")
        except ImportError:
            logger.debug("ACP CircuitBreakerRegistry not available, using local only")
        except Exception as e:
            logger.warning(f"Failed to initialize ACP integration: {e}")

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker.

        Args:
            name: Circuit breaker name

        Returns:
            CircuitBreaker instance
        """
        if name not in self._circuit_breakers:
            config = self.DEFAULT_CONFIGS.get(name, CircuitBreakerConfig())
            self._circuit_breakers[name] = CircuitBreaker(
                name=name,
                config=config,
                redis_client=self._redis,
            )
            logger.debug(f"Created circuit breaker '{name}'")

        return self._circuit_breakers[name]

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get states of all circuit breakers.

        Returns:
            Dictionary mapping names to state dictionaries
        """
        return {name: cb.get_metrics() for name, cb in self._circuit_breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for name, cb in self._circuit_breakers.items():
            logger.info(f"Resetting circuit breaker '{name}'")
            cb.reset()

    def force_open(self, name: str, reason: str = "manual") -> None:
        """Manually open a circuit breaker.

        Args:
            name: Circuit breaker name
            reason: Reason for opening
        """
        cb = self.get_circuit_breaker(name)
        cb.force_open(reason)

    def force_close(self, name: str, reason: str = "manual") -> None:
        """Manually close a circuit breaker.

        Args:
            name: Circuit breaker name
            reason: Reason for closing
        """
        cb = self.get_circuit_breaker(name)
        cb.force_close(reason)


def with_circuit_breaker(
    circuit_name: str,
    registry: PRCircuitBreakerRegistry | None = None,
    fallback: Callable[[], T] | None = None,
) -> Callable:
    """Decorator to wrap function with circuit breaker.

    Args:
        circuit_name: Name of the circuit breaker to use
        registry: Optional registry instance (creates default if None)
        fallback: Optional fallback function

    Returns:
        Decorated function
    """
    _registry = registry or PRCircuitBreakerRegistry()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = _registry.get_circuit_breaker(circuit_name)
            return cb.call(lambda: func(*args, **kwargs), fallback)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = _registry.get_circuit_breaker(circuit_name)
            return await cb.call_async(lambda: func(*args, **kwargs), fallback)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# Global registry instance
_global_registry: PRCircuitBreakerRegistry | None = None


def get_global_registry() -> PRCircuitBreakerRegistry:
    """Get global PR circuit breaker registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = PRCircuitBreakerRegistry()
    return _global_registry
