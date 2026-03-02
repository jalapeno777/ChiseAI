#!/usr/bin/env python3
"""Retry coordinator integration for PR pipeline operations.

Provides retry logic for PR operations using exponential backoff with jitter
and budget management for transient failures.

ST-AUTO-006: EP-NS-008 Integration for PR Pipeline
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, TypeVar

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStatus(Enum):
    """Status of retry operation."""

    PENDING = auto()
    IN_PROGRESS = auto()
    SUCCESS = auto()
    FAILED = auto()
    BUDGET_EXCEEDED = auto()
    CIRCUIT_OPEN = auto()


@dataclass
class RetryPolicy:
    """Policy for retry operations."""

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 1.0  # seconds
    budget_limit_per_minute: int = 10
    circuit_breaker_name: str | None = None
    retryable_exceptions: tuple[type[BaseException], ...] = field(
        default_factory=lambda: (Exception,)
    )
    non_retryable_exceptions: tuple[type[BaseException], ...] = field(
        default_factory=lambda: (
            KeyboardInterrupt,
            SystemExit,
            ValueError,
            TypeError,
        )
    )


@dataclass
class RetryOperation:
    """Represents a retry operation."""

    id: str
    service_name: str
    operation_name: str
    attempt_count: int = 0
    status: RetryStatus = RetryStatus.PENDING
    last_error: str | None = None
    last_attempt_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)


class RetryBudgetManager:
    """Manages retry budgets per service.

    Tracks retry consumption and enforces budget limits to prevent
    retry storms.
    """

    def __init__(self, redis_client: Any | None = None, default_limit: int = 100):
        """Initialize budget manager.

        Args:
            redis_client: Optional Redis client for distributed tracking
            default_limit: Default budget limit per window
        """
        self._redis = redis_client
        self._default_limit = default_limit
        self._local_budgets: dict[str, dict[str, Any]] = {}
        self._window_seconds = 60  # 1 minute window

    def check_and_consume(
        self, service_name: str, limit: int | None = None
    ) -> tuple[bool, int]:
        """Check if retry is allowed and consume budget.

        Args:
            service_name: Service identifier
            limit: Budget limit (uses default if None)

        Returns:
            Tuple of (allowed, remaining)
        """
        limit = limit or self._default_limit
        window_key = self._get_window_key()
        budget_key = f"{service_name}:{window_key}"

        # Try Redis first if available
        if self._redis:
            try:
                return self._check_and_consume_redis(budget_key, limit)
            except Exception as e:
                logger.warning(f"Redis budget check failed, using local: {e}")

        # Fall back to local tracking
        return self._check_and_consume_local(budget_key, limit)

    def _get_window_key(self) -> str:
        """Get current time window key."""
        window = int(time.time() / self._window_seconds)
        return str(window)

    def _check_and_consume_redis(self, budget_key: str, limit: int) -> tuple[bool, int]:
        """Check and consume budget using Redis."""
        assert self._redis is not None
        pipe = self._redis.pipeline()

        # Get current count
        pipe.get(budget_key)
        # Increment count
        pipe.incr(budget_key)
        # Set expiry if new key
        pipe.expire(budget_key, self._window_seconds)

        results = pipe.execute()
        current_count = int(results[0] or 0)
        new_count = int(results[1])

        # Check if we're within budget
        if current_count < limit:
            remaining = limit - new_count
            return True, max(0, remaining)

        return False, 0

    def _check_and_consume_local(self, budget_key: str, limit: int) -> tuple[bool, int]:
        """Check and consume budget using local tracking."""
        now = time.time()
        window_start = now - self._window_seconds

        # Clean up old entries
        self._local_budgets = {
            k: v
            for k, v in self._local_budgets.items()
            if v["last_update"] > window_start
        }

        # Get or create budget entry
        budget = self._local_budgets.get(budget_key, {"count": 0, "last_update": now})
        budget["last_update"] = now

        current_count = budget["count"]
        budget["count"] += 1
        self._local_budgets[budget_key] = budget

        if current_count < limit:
            remaining = limit - budget["count"]
            return True, max(0, remaining)

        return False, 0

    def get_budget_status(self, service_name: str) -> dict[str, Any]:
        """Get current budget status for a service.

        Args:
            service_name: Service identifier

        Returns:
            Budget status dictionary
        """
        window_key = self._get_window_key()
        budget_key = f"{service_name}:{window_key}"

        if self._redis:
            try:
                count = int(self._redis.get(budget_key) or 0)
                ttl = self._redis.ttl(budget_key)
                return {
                    "service": service_name,
                    "current_count": count,
                    "limit": self._default_limit,
                    "remaining": max(0, self._default_limit - count),
                    "window_seconds": self._window_seconds,
                    "window_ttl": ttl,
                }
            except Exception as e:
                logger.warning(f"Redis budget status failed: {e}")

        # Local fallback
        budget = self._local_budgets.get(budget_key, {"count": 0})
        count = budget["count"]
        return {
            "service": service_name,
            "current_count": count,
            "limit": self._default_limit,
            "remaining": max(0, self._default_limit - count),
            "window_seconds": self._window_seconds,
            "window_ttl": None,
        }


class PRRetryCoordinator:
    """Retry coordinator for PR pipeline operations.

    Provides centralized retry logic with:
    - Exponential backoff with jitter
    - Per-service retry budgets
    - Circuit breaker integration
    - Metrics collection
    """

    # Default retry policies for PR operations
    DEFAULT_POLICIES: dict[str, RetryPolicy] = {
        "gitea_api_call": RetryPolicy(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0,
            circuit_breaker_name="gitea_api",
            retryable_exceptions=(ConnectionError, TimeoutError, OSError),
        ),
        "discord_notification": RetryPolicy(
            max_attempts=2,
            base_delay=0.5,
            max_delay=5.0,
            circuit_breaker_name="discord_notifications",
            retryable_exceptions=(ConnectionError, TimeoutError),
        ),
        "redis_operation": RetryPolicy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            circuit_breaker_name="redis_operations",
            retryable_exceptions=(ConnectionError, TimeoutError, OSError),
        ),
        "pr_merge": RetryPolicy(
            max_attempts=3,
            base_delay=2.0,
            max_delay=60.0,
            circuit_breaker_name="pr_merge_operations",
            retryable_exceptions=(ConnectionError, TimeoutError, OSError),
        ),
    }

    def __init__(
        self,
        redis_client: Any | None = None,
        circuit_breaker_registry: Any | None = None,
    ):
        """Initialize retry coordinator.

        Args:
            redis_client: Optional Redis client for budget tracking
            circuit_breaker_registry: Optional circuit breaker registry
        """
        self._budget_manager = RetryBudgetManager(
            redis_client=redis_client,
            default_limit=100,
        )
        self._circuit_registry = circuit_breaker_registry
        self._metrics: dict[str, Any] = {
            "attempts": {},
            "successes": {},
            "failures": {},
            "budget_exceeded": {},
        }
        self._acp_coordinator = None

        # Try to integrate with ACP RetryCoordinator
        self._init_acp_integration()

    def _init_acp_integration(self) -> None:
        """Initialize integration with ACP RetryCoordinator."""
        try:
            from autonomous_control_plane.components.retry_coordinator import (
                RetryCoordinator as ACPRetryCoordinator,
            )

            self._acp_coordinator = ACPRetryCoordinator()
            logger.info("ACP RetryCoordinator integration enabled")
        except ImportError:
            logger.debug("ACP RetryCoordinator not available, using local only")
        except Exception as e:
            logger.warning(f"Failed to initialize ACP integration: {e}")

    def execute_with_retry(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], T],
        policy: RetryPolicy | None = None,
    ) -> T:
        """Execute function with retry logic.

        Args:
            service_name: Service identifier for budget/circuit tracking
            operation_name: Human-readable operation name
            func: Function to execute
            policy: Retry policy (uses default if None)

        Returns:
            Function result

        Raises:
            MaxRetriesExceededError: If max retries exceeded
            BudgetExceededError: If retry budget exceeded
            Exception: Original exception from function
        """
        policy = policy or self.DEFAULT_POLICIES.get(service_name, RetryPolicy())

        operation_id = str(uuid.uuid4())
        operation = RetryOperation(
            id=operation_id,
            service_name=service_name,
            operation_name=operation_name,
        )

        last_exception: BaseException | None = None

        for attempt in range(1, policy.max_attempts + 1):
            operation.attempt_count = attempt
            operation.last_attempt_at = time.time()
            operation.status = RetryStatus.IN_PROGRESS

            # Check circuit breaker
            if policy.circuit_breaker_name and self._circuit_registry:
                try:
                    cb = self._circuit_registry.get_circuit_breaker(
                        policy.circuit_breaker_name
                    )
                    if cb.is_open():
                        operation.status = RetryStatus.CIRCUIT_OPEN
                        self._record_failure(service_name, "circuit_open")
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker open for {policy.circuit_breaker_name}"
                        )
                except Exception as e:
                    logger.debug(f"Circuit breaker check failed: {e}")

            try:
                # Attempt execution
                result = func()

                # Success
                operation.status = RetryStatus.SUCCESS
                self._record_success(service_name)
                logger.info(
                    f"Operation {operation_name} succeeded on attempt {attempt}"
                )
                return result

            except policy.non_retryable_exceptions as e:
                # Non-retryable exception - fail immediately
                operation.status = RetryStatus.FAILED
                operation.last_error = str(e)
                self._record_failure(service_name, "non_retryable")
                logger.error(
                    f"Operation {operation_name} failed with non-retryable error: {e}"
                )
                raise

            except policy.retryable_exceptions as e:
                last_exception = e
                operation.last_error = str(e)

                # Check if this was the last attempt
                if attempt >= policy.max_attempts:
                    break

                # Check retry budget
                allowed, remaining = self._budget_manager.check_and_consume(
                    service_name, policy.budget_limit_per_minute
                )

                if not allowed:
                    operation.status = RetryStatus.BUDGET_EXCEEDED
                    self._record_failure(service_name, "budget_exceeded")
                    raise BudgetExceededError(
                        f"Retry budget exceeded for {service_name}"
                    ) from e

                # Calculate backoff
                delay = self._calculate_backoff(attempt, policy)

                logger.warning(
                    f"Operation {operation_name} failed (attempt {attempt}), "
                    f"retrying in {delay:.2f}s: {e}"
                )

                # Wait before retry
                time.sleep(delay)

        # All attempts failed
        operation.status = RetryStatus.FAILED
        self._record_failure(service_name, "max_retries")
        raise MaxRetriesExceededError(
            f"Operation {operation_name} failed after {policy.max_attempts} attempts"
        ) from last_exception

    async def execute_with_retry_async(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], Awaitable[T]],
        policy: RetryPolicy | None = None,
    ) -> T:
        """Execute async function with retry logic.

        Args:
            service_name: Service identifier
            operation_name: Human-readable operation name
            func: Async function to execute
            policy: Retry policy

        Returns:
            Function result
        """
        policy = policy or self.DEFAULT_POLICIES.get(service_name, RetryPolicy())

        operation_id = str(uuid.uuid4())
        operation = RetryOperation(
            id=operation_id,
            service_name=service_name,
            operation_name=operation_name,
        )

        last_exception: BaseException | None = None

        for attempt in range(1, policy.max_attempts + 1):
            operation.attempt_count = attempt
            operation.last_attempt_at = time.time()
            operation.status = RetryStatus.IN_PROGRESS

            # Check circuit breaker
            if policy.circuit_breaker_name and self._circuit_registry:
                try:
                    cb = self._circuit_registry.get_circuit_breaker(
                        policy.circuit_breaker_name
                    )
                    if cb.is_open():
                        operation.status = RetryStatus.CIRCUIT_OPEN
                        self._record_failure(service_name, "circuit_open")
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker open for {policy.circuit_breaker_name}"
                        )
                except Exception as e:
                    logger.debug(f"Circuit breaker check failed: {e}")

            try:
                # Attempt execution
                result = await func()

                # Success
                operation.status = RetryStatus.SUCCESS
                self._record_success(service_name)
                logger.info(
                    f"Operation {operation_name} succeeded on attempt {attempt}"
                )
                return result

            except policy.non_retryable_exceptions as e:
                operation.status = RetryStatus.FAILED
                operation.last_error = str(e)
                self._record_failure(service_name, "non_retryable")
                raise

            except policy.retryable_exceptions as e:
                last_exception = e
                operation.last_error = str(e)

                if attempt >= policy.max_attempts:
                    break

                # Check retry budget
                allowed, remaining = self._budget_manager.check_and_consume(
                    service_name, policy.budget_limit_per_minute
                )

                if not allowed:
                    operation.status = RetryStatus.BUDGET_EXCEEDED
                    self._record_failure(service_name, "budget_exceeded")
                    raise BudgetExceededError(
                        f"Retry budget exceeded for {service_name}"
                    ) from e

                # Calculate backoff
                delay = self._calculate_backoff(attempt, policy)

                logger.warning(
                    f"Operation {operation_name} failed (attempt {attempt}), "
                    f"retrying in {delay:.2f}s: {e}"
                )

                # Async wait
                await asyncio.sleep(delay)

        # All attempts failed
        operation.status = RetryStatus.FAILED
        self._record_failure(service_name, "max_retries")
        raise MaxRetriesExceededError(
            f"Operation {operation_name} failed after {policy.max_attempts} attempts"
        ) from last_exception

    def _calculate_backoff(self, attempt: int, policy: RetryPolicy) -> float:
        """Calculate backoff delay with optional jitter.

        Args:
            attempt: Current attempt number (1-indexed)
            policy: Retry policy

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = policy.base_delay * (policy.exponential_base ** (attempt - 1))
        delay = min(delay, policy.max_delay)

        # Add jitter (not for cryptographic purposes)
        if policy.jitter:
            jitter = random.uniform(0, policy.jitter_max)  # nosec B311
            delay += jitter

        return delay

    def _record_success(self, service_name: str) -> None:
        """Record a successful operation."""
        self._metrics["successes"][service_name] = (
            self._metrics["successes"].get(service_name, 0) + 1
        )

    def _record_failure(self, service_name: str, reason: str) -> None:
        """Record a failed operation."""
        key = f"{service_name}:{reason}"
        self._metrics["failures"][key] = self._metrics["failures"].get(key, 0) + 1

    def get_metrics(self) -> dict[str, Any]:
        """Get retry metrics."""
        return {
            "attempts": self._metrics["attempts"],
            "successes": self._metrics["successes"],
            "failures": self._metrics["failures"],
            "budget_exceeded": self._metrics["budget_exceeded"],
            "budget_status": {
                service: self._budget_manager.get_budget_status(service)
                for service in self.DEFAULT_POLICIES
            },
        }


class BudgetExceededError(Exception):
    """Exception raised when retry budget is exceeded."""

    pass


class MaxRetriesExceededError(Exception):
    """Exception raised when max retries are exceeded."""

    pass


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    pass


def with_retry(
    service_name: str,
    operation_name: str | None = None,
    policy: RetryPolicy | None = None,
    coordinator: PRRetryCoordinator | None = None,
) -> Callable:
    """Decorator to add retry logic to a function.

    Args:
        service_name: Service identifier
        operation_name: Human-readable operation name (uses function name if None)
        policy: Retry policy
        coordinator: Optional coordinator instance

    Returns:
        Decorated function
    """
    _coordinator = coordinator or PRRetryCoordinator()

    def decorator(func: Callable) -> Callable:
        _operation_name = operation_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _coordinator.execute_with_retry(
                service_name=service_name,
                operation_name=_operation_name,
                func=lambda: func(*args, **kwargs),
                policy=policy,
            )

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _coordinator.execute_with_retry_async(
                service_name=service_name,
                operation_name=_operation_name,
                func=lambda: func(*args, **kwargs),
                policy=policy,
            )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# Global coordinator instance
_global_coordinator: PRRetryCoordinator | None = None


def get_global_coordinator() -> PRRetryCoordinator:
    """Get global retry coordinator."""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = PRRetryCoordinator()
    return _global_coordinator
