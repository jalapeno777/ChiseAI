"""Retry policy models for the autonomous control plane.

Provides dataclasses and enums for configuring retry behavior,
budget management, and dead letter queue operations.

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Backoff strategies for retry delays."""

    EXPONENTIAL = auto()  # Exponential: delay = base * (2 ** attempt)
    LINEAR = auto()  # Linear: delay = base * attempt
    FIXED = auto()  # Fixed: delay = base (constant)


class JitterType(Enum):
    """Jitter algorithms for preventing thundering herd."""

    NONE = auto()  # No jitter
    FULL = auto()  # Full jitter: random(0, calculated_delay)
    EQUAL = auto()  # Equal jitter: delay/2 + random(0, delay/2)
    DECORRELATED = auto()  # Decorrelated: random(base, delay * 3)


class RetryStatus(Enum):
    """Status of a retry operation."""

    PENDING = auto()  # Waiting to be processed
    IN_PROGRESS = auto()  # Currently being retried
    SUCCESS = auto()  # Succeeded
    FAILED = auto()  # Failed (max retries exceeded)
    BUDGET_EXCEEDED = auto()  # Retry budget exceeded
    CIRCUIT_OPEN = auto()  # Circuit breaker is open
    DLQ = auto()  # Moved to dead letter queue


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay_ms: Base delay in milliseconds (default: 100)
        max_delay_ms: Maximum delay cap in milliseconds (default: 30000)
        jitter_factor: Jitter factor 0.0-1.0 (default: 0.1)
        budget_limit_per_minute: Max retries per minute per service (default: 100)
        circuit_breaker_name: Optional circuit breaker to check
        backoff_strategy: Backoff calculation strategy
        jitter_type: Jitter algorithm to use
        retryable_exceptions: Tuple of exception types to retry on
        non_retryable_exceptions: Tuple of exception types to not retry
    """

    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 30000
    jitter_factor: float = 0.1
    budget_limit_per_minute: int = 100
    circuit_breaker_name: str | None = None
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    jitter_type: JitterType = JitterType.FULL
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )
    non_retryable_exceptions: tuple[type[Exception], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_ms < 0:
            raise ValueError("base_delay_ms must be >= 0")
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be >= base_delay_ms")
        if not 0.0 <= self.jitter_factor <= 1.0:
            raise ValueError("jitter_factor must be between 0.0 and 1.0")
        if self.budget_limit_per_minute < 1:
            raise ValueError("budget_limit_per_minute must be >= 1")

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt in milliseconds.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in milliseconds
        """
        import random

        # Calculate base delay based on strategy
        if self.backoff_strategy == BackoffStrategy.FIXED:
            base_delay = self.base_delay_ms
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            base_delay = self.base_delay_ms * attempt
        else:  # EXPONENTIAL
            base_delay = self.base_delay_ms * (2 ** (attempt - 1))

        # Cap at max delay
        base_delay = min(base_delay, self.max_delay_ms)

        # Apply jitter
        if self.jitter_type == JitterType.NONE:
            return base_delay
        elif self.jitter_type == JitterType.FULL:
            # Full jitter: random(0, base_delay)
            return random.uniform(0, base_delay)
        elif self.jitter_type == JitterType.EQUAL:
            # Equal jitter: base_delay/2 + random(0, base_delay/2)
            half = base_delay / 2
            return half + random.uniform(0, half)
        else:  # DECORRELATED
            # Decorrelated: random(base_delay_ms, base_delay * 3)
            return random.uniform(self.base_delay_ms, base_delay * 3)

    def to_dict(self) -> dict[str, Any]:
        """Convert policy to dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "base_delay_ms": self.base_delay_ms,
            "max_delay_ms": self.max_delay_ms,
            "jitter_factor": self.jitter_factor,
            "budget_limit_per_minute": self.budget_limit_per_minute,
            "circuit_breaker_name": self.circuit_breaker_name,
            "backoff_strategy": self.backoff_strategy.name,
            "jitter_type": self.jitter_type.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        """Create policy from dictionary."""
        return cls(
            max_attempts=data.get("max_attempts", 3),
            base_delay_ms=data.get("base_delay_ms", 100),
            max_delay_ms=data.get("max_delay_ms", 30000),
            jitter_factor=data.get("jitter_factor", 0.1),
            budget_limit_per_minute=data.get("budget_limit_per_minute", 100),
            circuit_breaker_name=data.get("circuit_breaker_name"),
            backoff_strategy=BackoffStrategy[
                data.get("backoff_strategy", "EXPONENTIAL")
            ],
            jitter_type=JitterType[data.get("jitter_type", "FULL")],
        )


@dataclass
class RetryBudget:
    """Budget tracking for per-service retry limits.

    Attributes:
        service_name: Name of the service
        current_count: Current retry count for the window
        window_start: Start of the current minute window
        limit: Maximum retries allowed per minute
        is_exceeded: Whether budget has been exceeded
    """

    service_name: str
    current_count: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    limit: int = 100
    is_exceeded: bool = False

    def record_attempt(self) -> bool:
        """Record a retry attempt.

        Returns:
            True if attempt is allowed, False if budget exceeded
        """
        now = datetime.utcnow()
        window_minute = now.replace(second=0, microsecond=0)

        # Reset if we're in a new minute window
        if window_minute > self.window_start:
            self.current_count = 0
            self.window_start = window_minute
            self.is_exceeded = False

        # Check if budget exceeded
        if self.current_count >= self.limit:
            self.is_exceeded = True
            return False

        self.current_count += 1
        # Set is_exceeded if we've now reached the limit
        if self.current_count >= self.limit:
            self.is_exceeded = True
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert budget to dictionary."""
        return {
            "service_name": self.service_name,
            "current_count": self.current_count,
            "window_start": self.window_start.isoformat(),
            "limit": self.limit,
            "is_exceeded": self.is_exceeded,
            "remaining": max(0, self.limit - self.current_count),
        }


@dataclass
class DeadLetterQueueItem:
    """Item in the dead letter queue.

    Attributes:
        id: Unique identifier
        service_name: Service that failed
        operation: Operation description
        payload: Operation payload (serialized)
        error_message: Error that caused failure
        retry_count: Number of retry attempts made
        created_at: When item was added to DLQ
        status: Current status
        last_error: Last error details
    """

    id: str
    service_name: str
    operation: str
    payload: dict[str, Any]
    error_message: str
    retry_count: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: RetryStatus = RetryStatus.DLQ
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert DLQ item to dictionary."""
        return {
            "id": self.id,
            "service_name": self.service_name,
            "operation": self.operation,
            "payload": self.payload,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "status": self.status.name,
            "last_error": self.last_error,
        }


@dataclass
class RetryOperation:
    """Represents a retryable operation.

    Attributes:
        id: Unique operation identifier
        service_name: Target service
        operation_name: Operation name
        func: Async function to execute
        policy: Retry policy configuration
        created_at: When operation was created
        status: Current status
        attempt_count: Number of attempts made
        last_attempt_at: Last attempt timestamp
        last_error: Last error message
    """

    id: str
    service_name: str
    operation_name: str
    func: Callable[[], Awaitable[Any]] = field(repr=False)
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: RetryStatus = RetryStatus.PENDING
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert operation to dictionary (excluding func)."""
        return {
            "id": self.id,
            "service_name": self.service_name,
            "operation_name": self.operation_name,
            "policy": self.policy.to_dict(),
            "created_at": self.created_at.isoformat(),
            "status": self.status.name,
            "attempt_count": self.attempt_count,
            "last_attempt_at": (
                self.last_attempt_at.isoformat() if self.last_attempt_at else None
            ),
            "last_error": self.last_error,
        }


class RetryAborted(Exception):
    """Raised when retry is aborted (e.g., circuit breaker open)."""

    pass


class BudgetExceededError(Exception):
    """Raised when retry budget is exceeded."""

    pass


class MaxRetriesExceededError(Exception):
    """Raised when maximum retry attempts are exceeded."""

    pass
