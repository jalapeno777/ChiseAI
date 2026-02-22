"""Circuit breaker data models for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery

    def __str__(self) -> str:
        return self.value


class StateTransitionReason(Enum):
    """Reasons for state transitions."""

    FAILURE_THRESHOLD = "failure_threshold"
    TIMEOUT_ELAPSED = "timeout_elapsed"
    RECOVERY_CONFIRMED = "recovery_confirmed"
    MANUAL_FORCE = "manual_force"
    MANUAL_RESET = "manual_reset"


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3
    expected_exception: str = "Exception"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds,
            "half_open_max_calls": self.half_open_max_calls,
            "expected_exception": self.expected_exception,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerConfig:
        """Create from dictionary."""
        return cls(
            failure_threshold=data.get("failure_threshold", 5),
            timeout_seconds=data.get("timeout_seconds", 60.0),
            half_open_max_calls=data.get("half_open_max_calls", 3),
            expected_exception=data.get("expected_exception", "Exception"),
        )


@dataclass
class CircuitBreakerMetrics:
    """Metrics for a circuit breaker."""

    failure_count: int = 0
    success_count: int = 0
    rejection_count: int = 0
    state_transition_count: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None
    last_state_change: datetime = field(default_factory=datetime.utcnow)
    consecutive_successes: int = 0
    consecutive_failures: int = 0

    def record_success(self) -> None:
        """Record a successful call."""
        self.success_count += 1
        self.last_success_time = datetime.utcnow()
        self.consecutive_successes += 1
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.consecutive_failures += 1
        self.consecutive_successes = 0

    def record_rejection(self) -> None:
        """Record a rejected call (circuit open)."""
        self.rejection_count += 1

    def record_state_transition(self) -> None:
        """Record a state transition."""
        self.state_transition_count += 1
        self.last_state_change = datetime.utcnow()
        self.consecutive_successes = 0
        self.consecutive_failures = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "rejection_count": self.rejection_count,
            "state_transition_count": self.state_transition_count,
            "last_failure_time": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
            "last_success_time": (
                self.last_success_time.isoformat() if self.last_success_time else None
            ),
            "last_state_change": self.last_state_change.isoformat(),
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerMetrics:
        """Create from dictionary."""
        return cls(
            failure_count=data.get("failure_count", 0),
            success_count=data.get("success_count", 0),
            rejection_count=data.get("rejection_count", 0),
            state_transition_count=data.get("state_transition_count", 0),
            last_failure_time=(
                datetime.fromisoformat(data["last_failure_time"])
                if data.get("last_failure_time")
                else None
            ),
            last_success_time=(
                datetime.fromisoformat(data["last_success_time"])
                if data.get("last_success_time")
                else None
            ),
            last_state_change=datetime.fromisoformat(
                data.get("last_state_change", datetime.utcnow().isoformat())
            ),
            consecutive_successes=data.get("consecutive_successes", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
        )


@dataclass
class CircuitBreakerStateModel:
    """Full state model for a circuit breaker."""

    name: str
    state: CircuitBreakerState
    config: CircuitBreakerConfig
    metrics: CircuitBreakerMetrics
    half_open_calls: int = 0
    last_error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "config": self.config.to_dict(),
            "metrics": self.metrics.to_dict(),
            "half_open_calls": self.half_open_calls,
            "last_error": self.last_error,
            "created_at": (
                self.created_at.isoformat()
                if isinstance(self.created_at, datetime)
                else str(self.created_at)
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if isinstance(self.updated_at, datetime)
                else str(self.updated_at)
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerStateModel:
        """Create from dictionary."""

        def parse_datetime(value) -> datetime:
            if isinstance(value, str):
                return datetime.fromisoformat(value)
            elif isinstance(value, (int, float)):
                return datetime.utcfromtimestamp(value)
            return datetime.utcnow()

        return cls(
            name=data["name"],
            state=CircuitBreakerState(data["state"]),
            config=CircuitBreakerConfig.from_dict(data["config"]),
            metrics=CircuitBreakerMetrics.from_dict(data["metrics"]),
            half_open_calls=data.get("half_open_calls", 0),
            last_error=data.get("last_error"),
            created_at=parse_datetime(data.get("created_at")),
            updated_at=parse_datetime(data.get("updated_at")),
        )


@dataclass
class StateChangeEvent:
    """Event emitted when circuit breaker state changes."""

    circuit_breaker_name: str
    previous_state: CircuitBreakerState
    new_state: CircuitBreakerState
    reason: StateTransitionReason
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "circuit_breaker_name": self.circuit_breaker_name,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "reason": self.reason.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class CircuitBreakerHealth:
    """Health status for a circuit breaker."""

    name: str
    state: CircuitBreakerState
    is_healthy: bool
    failure_rate: float
    rejection_rate: float
    last_error: str | None = None
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "is_healthy": self.is_healthy,
            "failure_rate": self.failure_rate,
            "rejection_rate": self.rejection_rate,
            "last_error": self.last_error,
            "recommendation": self.recommendation,
        }
