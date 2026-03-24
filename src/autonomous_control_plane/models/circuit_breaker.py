"""Circuit breaker data models for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
ST-SAFETY-001: Circuit Breaker Enhancement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
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
    ADAPTIVE_THRESHOLD = "adaptive_threshold"
    CANARY_PROMOTION = "canary_promotion"
    GROUP_CASCADE = "group_cascade"


@dataclass
class AdaptiveThresholdConfig:
    """Configuration for adaptive failure thresholds."""

    enabled: bool = False
    time_windows: list[int] = field(
        default_factory=lambda: [60, 300, 900]
    )  # 1min, 5min, 15min
    baseline_multiplier: float = 2.0
    min_threshold: int = 3
    max_threshold: int = 20
    adjustment_cooldown_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "time_windows": self.time_windows,
            "baseline_multiplier": self.baseline_multiplier,
            "min_threshold": self.min_threshold,
            "max_threshold": self.max_threshold,
            "adjustment_cooldown_seconds": self.adjustment_cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdaptiveThresholdConfig:
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            time_windows=data.get("time_windows", [60, 300, 900]),
            baseline_multiplier=data.get("baseline_multiplier", 2.0),
            min_threshold=data.get("min_threshold", 3),
            max_threshold=data.get("max_threshold", 20),
            adjustment_cooldown_seconds=data.get("adjustment_cooldown_seconds", 60.0),
        )


@dataclass
class CanaryRecoveryConfig:
    """Configuration for graduated canary recovery in half-open state."""

    enabled: bool = False
    progression_steps: list[float] = field(
        default_factory=lambda: [0.01, 0.1, 0.25, 0.5, 1.0]
    )
    success_rate_threshold: float = 0.95
    min_requests_per_step: int = 10
    step_timeout_seconds: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "progression_steps": self.progression_steps,
            "success_rate_threshold": self.success_rate_threshold,
            "min_requests_per_step": self.min_requests_per_step,
            "step_timeout_seconds": self.step_timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanaryRecoveryConfig:
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            progression_steps=data.get(
                "progression_steps", [0.01, 0.1, 0.25, 0.5, 1.0]
            ),
            success_rate_threshold=data.get("success_rate_threshold", 0.95),
            min_requests_per_step=data.get("min_requests_per_step", 10),
            step_timeout_seconds=data.get("step_timeout_seconds", 30.0),
        )


@dataclass
class PredictiveAlertConfig:
    """Configuration for predictive failure detection."""

    enabled: bool = False
    velocity_threshold: float = 5.0  # failures per second
    threshold_warning_percent: float = 0.8  # 80% of threshold
    alert_cooldown_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "velocity_threshold": self.velocity_threshold,
            "threshold_warning_percent": self.threshold_warning_percent,
            "alert_cooldown_seconds": self.alert_cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PredictiveAlertConfig:
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            velocity_threshold=data.get("velocity_threshold", 5.0),
            threshold_warning_percent=data.get("threshold_warning_percent", 0.8),
            alert_cooldown_seconds=data.get("alert_cooldown_seconds", 60.0),
        )


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3
    expected_exception: str = "Exception"
    adaptive_threshold: AdaptiveThresholdConfig = field(
        default_factory=AdaptiveThresholdConfig
    )
    canary_recovery: CanaryRecoveryConfig = field(default_factory=CanaryRecoveryConfig)
    predictive_alerts: PredictiveAlertConfig = field(
        default_factory=PredictiveAlertConfig
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds,
            "half_open_max_calls": self.half_open_max_calls,
            "expected_exception": self.expected_exception,
            "adaptive_threshold": self.adaptive_threshold.to_dict(),
            "canary_recovery": self.canary_recovery.to_dict(),
            "predictive_alerts": self.predictive_alerts.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerConfig:
        """Create from dictionary."""
        return cls(
            failure_threshold=data.get("failure_threshold", 5),
            timeout_seconds=data.get("timeout_seconds", 60.0),
            half_open_max_calls=data.get("half_open_max_calls", 3),
            expected_exception=data.get("expected_exception", "Exception"),
            adaptive_threshold=AdaptiveThresholdConfig.from_dict(
                data.get("adaptive_threshold", {})
            ),
            canary_recovery=CanaryRecoveryConfig.from_dict(
                data.get("canary_recovery", {})
            ),
            predictive_alerts=PredictiveAlertConfig.from_dict(
                data.get("predictive_alerts", {})
            ),
        )


@dataclass
class FailureRateWindow:
    """Failure rate over a specific time window."""

    window_seconds: int
    failure_count: int = 0
    success_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def record_failure(self) -> None:
        """Record a failure in this window."""
        self.failure_count += 1
        self.last_updated = datetime.now(UTC)

    def record_success(self) -> None:
        """Record a success in this window."""
        self.success_count += 1
        self.last_updated = datetime.now(UTC)

    @property
    def total_calls(self) -> int:
        """Total calls in this window."""
        return self.failure_count + self.success_count

    @property
    def failure_rate(self) -> float:
        """Failure rate as a percentage (0.0 - 1.0)."""
        total = self.total_calls
        return self.failure_count / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "window_seconds": self.window_seconds,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailureRateWindow:
        """Create from dictionary."""
        return cls(
            window_seconds=data.get("window_seconds", 60),
            failure_count=data.get("failure_count", 0),
            success_count=data.get("success_count", 0),
            last_updated=datetime.fromisoformat(
                data.get("last_updated", datetime.now(UTC).isoformat())
            ),
        )


@dataclass
class AdaptiveThresholdMetrics:
    """Metrics for adaptive threshold tracking."""

    current_threshold: int = 5
    baseline_failure_rate: float = 0.0
    windows: dict[int, FailureRateWindow] = field(default_factory=dict)
    last_adjustment_time: datetime | None = None
    adjustment_count: int = 0

    def __post_init__(self) -> None:
        """Initialize windows if empty."""
        if not self.windows:
            self.windows = {
                60: FailureRateWindow(window_seconds=60),
                300: FailureRateWindow(window_seconds=300),
                900: FailureRateWindow(window_seconds=900),
            }

    def record_failure(self) -> None:
        """Record a failure across all windows."""
        for window in self.windows.values():
            window.record_failure()

    def record_success(self) -> None:
        """Record a success across all windows."""
        for window in self.windows.values():
            window.record_success()

    def update_baseline(self) -> None:
        """Update baseline failure rate from 15min window."""
        window_15min = self.windows.get(900)
        if window_15min and window_15min.total_calls >= 100:
            self.baseline_failure_rate = window_15min.failure_rate

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_threshold": self.current_threshold,
            "baseline_failure_rate": self.baseline_failure_rate,
            "windows": {str(k): v.to_dict() for k, v in self.windows.items()},
            "last_adjustment_time": (
                self.last_adjustment_time.isoformat()
                if self.last_adjustment_time
                else None
            ),
            "adjustment_count": self.adjustment_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdaptiveThresholdMetrics:
        """Create from dictionary."""
        windows_data = data.get("windows", {})
        windows = {}
        for k, v in windows_data.items():
            try:
                key = int(k)
                windows[key] = FailureRateWindow.from_dict(v)
            except (ValueError, TypeError):
                continue

        last_adjustment = data.get("last_adjustment_time")
        return cls(
            current_threshold=data.get("current_threshold", 5),
            baseline_failure_rate=data.get("baseline_failure_rate", 0.0),
            windows=windows,
            last_adjustment_time=(
                datetime.fromisoformat(last_adjustment) if last_adjustment else None
            ),
            adjustment_count=data.get("adjustment_count", 0),
        )


@dataclass
class CanaryRecoveryState:
    """State for graduated canary recovery."""

    current_step_index: int = 0
    current_step_requests: int = 0
    current_step_successes: int = 0
    step_start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    promotion_history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current_step_success_rate(self) -> float:
        """Success rate for current step."""
        if self.current_step_requests == 0:
            return 0.0
        return self.current_step_successes / self.current_step_requests

    def record_request(self) -> None:
        """Record a request in current step."""
        self.current_step_requests += 1

    def record_success(self) -> bool:
        """Record a success, returns True if step should promote."""
        self.current_step_successes += 1
        return False  # Actual promotion logic handled by caller

    def promote_to_next_step(self) -> bool:
        """Promote to next step, returns True if fully recovered."""
        self.promotion_history.append(
            {
                "step_index": self.current_step_index,
                "requests": self.current_step_requests,
                "successes": self.current_step_successes,
                "success_rate": self.current_step_success_rate,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self.current_step_index += 1
        self.current_step_requests = 0
        self.current_step_successes = 0
        self.step_start_time = datetime.now(UTC)
        return False  # Caller determines if fully recovered

    def reset(self) -> None:
        """Reset canary state."""
        self.current_step_index = 0
        self.current_step_requests = 0
        self.current_step_successes = 0
        self.step_start_time = datetime.now(UTC)
        self.promotion_history = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_step_index": self.current_step_index,
            "current_step_requests": self.current_step_requests,
            "current_step_successes": self.current_step_successes,
            "step_start_time": self.step_start_time.isoformat(),
            "promotion_history": self.promotion_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanaryRecoveryState:
        """Create from dictionary."""
        return cls(
            current_step_index=data.get("current_step_index", 0),
            current_step_requests=data.get("current_step_requests", 0),
            current_step_successes=data.get("current_step_successes", 0),
            step_start_time=datetime.fromisoformat(
                data.get("step_start_time", datetime.now(UTC).isoformat())
            ),
            promotion_history=data.get("promotion_history", []),
        )


@dataclass
class PredictiveAlertState:
    """State for predictive failure detection."""

    failure_velocity: float = 0.0  # failures per second
    threshold_approach_percent: float = 0.0  # how close to threshold
    last_alert_time: datetime | None = None
    alert_count: int = 0
    failure_timestamps: list[float] = field(default_factory=list)

    def record_failure(self, timestamp: float | None = None) -> None:
        """Record a failure timestamp for velocity calculation."""
        if timestamp is None:
            timestamp = datetime.now(UTC).timestamp()
        self.failure_timestamps.append(timestamp)
        # Keep only last 60 seconds of timestamps
        cutoff = timestamp - 60
        self.failure_timestamps = [t for t in self.failure_timestamps if t > cutoff]
        self._calculate_velocity(timestamp)

    def _calculate_velocity(self, current_time: float) -> None:
        """Calculate failure velocity (failures per second)."""
        if len(self.failure_timestamps) < 2:
            self.failure_velocity = 0.0
            return

        time_span = current_time - min(self.failure_timestamps)
        if time_span > 0:
            self.failure_velocity = len(self.failure_timestamps) / time_span
        else:
            self.failure_velocity = 0.0

    def update_threshold_approach(self, current_failures: int, threshold: int) -> None:
        """Update how close we are to the threshold."""
        if threshold > 0:
            self.threshold_approach_percent = min(current_failures / threshold, 1.0)
        else:
            self.threshold_approach_percent = 0.0

    def should_alert(self, warning_percent: float, cooldown_seconds: float) -> bool:
        """Check if an alert should be triggered."""
        if self.threshold_approach_percent < warning_percent:
            return False

        if self.last_alert_time is not None:
            elapsed = (datetime.now(UTC) - self.last_alert_time).total_seconds()
            if elapsed < cooldown_seconds:
                return False

        return True

    def record_alert(self) -> None:
        """Record that an alert was triggered."""
        self.last_alert_time = datetime.now(UTC)
        self.alert_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_velocity": self.failure_velocity,
            "threshold_approach_percent": self.threshold_approach_percent,
            "last_alert_time": (
                self.last_alert_time.isoformat() if self.last_alert_time else None
            ),
            "alert_count": self.alert_count,
            "failure_timestamps": self.failure_timestamps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PredictiveAlertState:
        """Create from dictionary."""
        last_alert = data.get("last_alert_time")
        return cls(
            failure_velocity=data.get("failure_velocity", 0.0),
            threshold_approach_percent=data.get("threshold_approach_percent", 0.0),
            last_alert_time=datetime.fromisoformat(last_alert) if last_alert else None,
            alert_count=data.get("alert_count", 0),
            failure_timestamps=data.get("failure_timestamps", []),
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
    last_state_change: datetime = field(default_factory=lambda: datetime.now(UTC))
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    adaptive: AdaptiveThresholdMetrics = field(default_factory=AdaptiveThresholdMetrics)
    canary: CanaryRecoveryState = field(default_factory=CanaryRecoveryState)
    predictive: PredictiveAlertState = field(default_factory=PredictiveAlertState)

    def record_success(self) -> None:
        """Record a successful call."""
        self.success_count += 1
        self.last_success_time = datetime.now(UTC)
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.adaptive.record_success()

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(UTC)
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.adaptive.record_failure()
        self.predictive.record_failure()

    def record_rejection(self) -> None:
        """Record a rejected call (circuit open)."""
        self.rejection_count += 1

    def record_state_transition(self) -> None:
        """Record a state transition."""
        self.state_transition_count += 1
        self.last_state_change = datetime.now(UTC)
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
            "adaptive": self.adaptive.to_dict(),
            "canary": self.canary.to_dict(),
            "predictive": self.predictive.to_dict(),
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
                data.get("last_state_change", datetime.now(UTC).isoformat())
            ),
            consecutive_successes=data.get("consecutive_successes", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
            adaptive=AdaptiveThresholdMetrics.from_dict(data.get("adaptive", {})),
            canary=CanaryRecoveryState.from_dict(data.get("canary", {})),
            predictive=PredictiveAlertState.from_dict(data.get("predictive", {})),
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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

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

        def parse_datetime(value: Any) -> datetime:
            if isinstance(value, str):
                return datetime.fromisoformat(value)
            elif isinstance(value, (int, float)):
                return datetime.utcfromtimestamp(value)
            return datetime.now(UTC)

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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
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


@dataclass
class CircuitBreakerGroup:
    """Group of related circuit breakers for cascade operations.

    Allows managing multiple circuit breakers as a unit, with
    cascade open/close operations across all group members.
    """

    name: str
    member_names: list[str] = field(default_factory=list)
    cascade_open: bool = True
    cascade_close: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_member(self, circuit_breaker_name: str) -> None:
        """Add a circuit breaker to the group."""
        if circuit_breaker_name not in self.member_names:
            self.member_names.append(circuit_breaker_name)
            self.updated_at = datetime.now(UTC)

    def remove_member(self, circuit_breaker_name: str) -> bool:
        """Remove a circuit breaker from the group."""
        if circuit_breaker_name in self.member_names:
            self.member_names.remove(circuit_breaker_name)
            self.updated_at = datetime.now(UTC)
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "member_names": self.member_names,
            "cascade_open": self.cascade_open,
            "cascade_close": self.cascade_close,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerGroup:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            member_names=data.get("member_names", []),
            cascade_open=data.get("cascade_open", True),
            cascade_close=data.get("cascade_close", False),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now(UTC).isoformat())
            ),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", datetime.now(UTC).isoformat())
            ),
        )


@dataclass
class CircuitBreakerGroupMetrics:
    """Aggregated metrics for a circuit breaker group."""

    group_name: str
    total_members: int = 0
    open_count: int = 0
    closed_count: int = 0
    half_open_count: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejections: int = 0
    overall_health_percent: float = 100.0
    member_health: dict[str, CircuitBreakerHealth] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "group_name": self.group_name,
            "total_members": self.total_members,
            "open_count": self.open_count,
            "closed_count": self.closed_count,
            "half_open_count": self.half_open_count,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "total_rejections": self.total_rejections,
            "overall_health_percent": self.overall_health_percent,
            "member_health": {
                name: health.to_dict() for name, health in self.member_health.items()
            },
        }
