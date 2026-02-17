"""Retry handler with exponential backoff for transient failures.

Provides retry utilities for handling transient failures in kill-switch
operations, including circuit breaker integration and jitter.

For ST-PAPER-006: Kill-Switch Edge Case Handling
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failure threshold reached, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class RetryStrategy(Enum):
    """Retry strategies."""

    FIXED = "fixed"  # Fixed delay between retries
    EXPONENTIAL = "exponential"  # Exponential backoff
    EXPONENTIAL_JITTER = "exponential_jitter"  # Exponential with jitter


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay_seconds: Base delay between retries (default: 1.0)
        max_delay_seconds: Maximum delay cap (default: 30.0)
        strategy: Retry strategy to use
        retryable_exceptions: Tuple of exception types to retry on
        on_retry_callback: Optional callback on each retry attempt
        on_max_retries_callback: Optional callback when max retries exceeded
    """

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )
    on_retry_callback: Callable[[int, Exception], None] | None = None
    on_max_retries_callback: Callable[[Exception], None] | None = None


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout_seconds: Time before attempting recovery
        half_open_max_calls: Max calls allowed in half-open state
        success_threshold: Successes needed to close circuit
    """

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


class CircuitBreaker:
    """Circuit breaker for preventing cascade failures.

    Implements the circuit breaker pattern to prevent repeated
    calls to failing services. Tracks failures and opens the
    circuit when threshold is reached.

    Example:
        breaker = CircuitBreaker(name="redis", config=CircuitBreakerConfig())

        if breaker.can_execute():
            try:
                result = await redis_operation()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            raise CircuitBreakerOpenError("Redis circuit is open")
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker identifier
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    async def can_execute(self) -> bool:
        """Check if execution is allowed.

        Returns:
            True if execution should proceed, False if circuit is open
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self._last_failure_time is not None:
                    elapsed = asyncio.get_event_loop().time() - self._last_failure_time
                    if elapsed >= self.config.recovery_timeout_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        logger.info(
                            f"Circuit breaker '{self.name}' entering half-open state"
                        )
                        return True
                return False

            # HALF_OPEN state
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record a successful execution."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._reset()
                    logger.info(f"Circuit breaker '{self.name}' closed (recovered)")
            else:
                # In CLOSED state, just reset failure count on success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed execution."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = asyncio.get_event_loop().time()

            if self._state == CircuitState.HALF_OPEN:
                # Back to OPEN state
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(
                    f"Circuit breaker '{self.name}' reopened after half-open failure"
                )
            elif self._failure_count >= self.config.failure_threshold:
                if self._state != CircuitState.OPEN:
                    self._state = CircuitState.OPEN
                    logger.error(
                        f"Circuit breaker '{self.name}' opened after "
                        f"{self._failure_count} failures"
                    )

    def _reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None

    def get_metrics(self) -> dict[str, Any]:
        """Get circuit breaker metrics.

        Returns:
            Dictionary with current state and counts
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "half_open_calls": self._half_open_calls,
            "last_failure_time": self._last_failure_time,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


async def retry_with_backoff(
    func: Callable[[], Coroutine[Any, Any, T]],
    config: RetryConfig | None = None,
    operation_name: str = "operation",
) -> T:
    """Execute function with retry and exponential backoff.

    Args:
        func: Async function to execute
        config: Retry configuration
        operation_name: Name of operation for logging

    Returns:
        Result from function execution

    Raises:
        Exception: The last exception if all retries fail

    Example:
        config = RetryConfig(max_attempts=3, base_delay_seconds=1.0)
        result = await retry_with_backoff(
            lambda: redis_client.get("key"),
            config,
            "redis_get"
        )
    """
    config = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func()
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt == config.max_attempts:
                logger.error(
                    f"{operation_name} failed after {config.max_attempts} attempts: {e}"
                )
                if config.on_max_retries_callback:
                    config.on_max_retries_callback(e)
                raise

            # Calculate delay
            delay = _calculate_delay(attempt, config)

            logger.warning(
                f"{operation_name} attempt {attempt} failed: {e}. "
                f"Retrying in {delay:.2f}s..."
            )

            if config.on_retry_callback:
                config.on_retry_callback(attempt, e)

            await asyncio.sleep(delay)

    # Should never reach here
    raise last_exception or Exception(f"{operation_name} failed")


def _calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for retry attempt.

    Args:
        attempt: Current attempt number (1-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    if config.strategy == RetryStrategy.FIXED:
        delay = config.base_delay_seconds
    elif config.strategy == RetryStrategy.EXPONENTIAL:
        delay = config.base_delay_seconds * (2 ** (attempt - 1))
    else:  # EXPONENTIAL_JITTER
        # Exponential backoff with full jitter
        exp_delay = config.base_delay_seconds * (2 ** (attempt - 1))
        delay = random.uniform(0, exp_delay)

    # Cap at max delay
    return min(delay, config.max_delay_seconds)


class RetryHandler:
    """Handler for retry operations with circuit breaker integration.

    Combines retry logic with circuit breaker pattern for robust
    handling of transient failures.

    Example:
        handler = RetryHandler()

        # Register circuit breakers
        handler.register_circuit_breaker("redis", CircuitBreakerConfig())
        handler.register_circuit_breaker("influxdb", CircuitBreakerConfig())

        # Execute with retry and circuit breaker
        result = await handler.execute_with_retry(
            "redis",
            lambda: redis_client.get("key"),
            RetryConfig(max_attempts=3),
        )
    """

    def __init__(self):
        """Initialize retry handler."""
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def register_circuit_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Register a circuit breaker.

        Args:
            name: Circuit breaker identifier
            config: Circuit breaker configuration

        Returns:
            The registered circuit breaker
        """
        breaker = CircuitBreaker(name, config)
        self._circuit_breakers[name] = breaker
        return breaker

    def get_circuit_breaker(self, name: str) -> CircuitBreaker | None:
        """Get a registered circuit breaker.

        Args:
            name: Circuit breaker name

        Returns:
            Circuit breaker if found, None otherwise
        """
        return self._circuit_breakers.get(name)

    async def execute_with_retry(
        self,
        circuit_name: str,
        func: Callable[[], Coroutine[Any, Any, T]],
        retry_config: RetryConfig | None = None,
        operation_name: str = "operation",
    ) -> T:
        """Execute function with circuit breaker and retry.

        Args:
            circuit_name: Name of circuit breaker to use
            func: Async function to execute
            retry_config: Retry configuration
            operation_name: Name of operation for logging

        Returns:
            Result from function execution

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If all retries fail
        """
        breaker = self._circuit_breakers.get(circuit_name)

        if breaker is None:
            # No circuit breaker, just retry
            return await retry_with_backoff(func, retry_config, operation_name)

        # Check circuit state
        if not await breaker.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker '{circuit_name}' is open")

        try:
            result = await retry_with_backoff(func, retry_config, operation_name)
            await breaker.record_success()
            return result
        except Exception:
            await breaker.record_failure()
            raise

    def get_all_metrics(self) -> dict[str, Any]:
        """Get metrics for all circuit breakers.

        Returns:
            Dictionary mapping breaker names to their metrics
        """
        return {
            name: breaker.get_metrics()
            for name, breaker in self._circuit_breakers.items()
        }


def with_retry(
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator for adding retry logic to async functions.

    Args:
        max_attempts: Maximum retry attempts
        base_delay_seconds: Base delay between retries
        retryable_exceptions: Exception types to retry on

    Returns:
        Decorated function

    Example:
        @with_retry(max_attempts=3, base_delay_seconds=1.0)
        async def fetch_data():
            return await api.get_data()
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay_seconds=base_delay_seconds,
                retryable_exceptions=retryable_exceptions,
            )
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                config,
                func.__name__,
            )

        return wrapper

    return decorator
