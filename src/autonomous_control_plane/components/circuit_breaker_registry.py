"""Circuit Breaker Registry with Redis persistence.

Provides centralized management of circuit breakers across all services
with automatic state persistence and telemetry emission.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
ST-SAFETY-001: Circuit Breaker Enhancement - Adaptive Thresholds, Canary Recovery, Groups
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from autonomous_control_plane.config.settings import settings
from autonomous_control_plane.models.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerGroup,
    CircuitBreakerGroupMetrics,
    CircuitBreakerHealth,
    CircuitBreakerMetrics,
    CircuitBreakerState,
    CircuitBreakerStateModel,
    StateChangeEvent,
    StateTransitionReason,
)

if TYPE_CHECKING:
    import redis
    from influxdb_client.client.influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)


class CircuitBreakerRegistry:
    """Centralized registry for circuit breaker management.

    Provides CRUD operations, automatic state transitions, persistence
    in Redis with PostgreSQL backup, and telemetry emission to InfluxDB.

    Example:
        >>> registry = CircuitBreakerRegistry()
        >>> cb = registry.register("redis_service", CircuitBreakerConfig())
        >>> states = registry.get_all_states()
        >>> registry.force_open("redis_service", "manual_intervention")
    """

    _instance: CircuitBreakerRegistry | None = None
    _lock = threading.Lock()

    def __new__(
        cls,
        redis_client: redis.Redis | None = None,
        influxdb_client: InfluxDBClient | None = None,
    ) -> CircuitBreakerRegistry:
        """Singleton pattern for global registry access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    instance._pending_redis = redis_client
                    instance._pending_influxdb = influxdb_client
                    cls._instance = instance
        return cls._instance

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        influxdb_client: InfluxDBClient | None = None,
    ):
        """Initialize the registry.

        Args:
            redis_client: Optional Redis client (creates new if not provided)
            influxdb_client: Optional InfluxDB client for telemetry
        """
        if self._initialized:
            return

        self._initialized = True
        self._registry: dict[str, CircuitBreakerStateModel] = {}
        self._event_handlers: list[Callable[[StateChangeEvent], None]] = []
        self._lock = threading.RLock()

        # Use pending values from __new__ if available, otherwise use parameters
        self._redis = getattr(self, "_pending_redis", None) or redis_client
        self._influxdb = getattr(self, "_pending_influxdb", None) or influxdb_client
        self._key_prefix = settings.cb_registry_key_prefix

        # Initialize Redis if not provided
        if self._redis is None:
            try:
                import redis as redis_lib

                self._redis = redis_lib.Redis(
                    host=settings.redis.host,
                    port=settings.redis.port,
                    db=settings.redis.db,
                    password=settings.redis.password,
                    socket_timeout=settings.redis.socket_timeout,
                    socket_connect_timeout=settings.redis.socket_connect_timeout,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
                logger.info("CircuitBreakerRegistry: Redis connection established")
            except Exception as e:
                logger.warning(
                    f"CircuitBreakerRegistry: Redis unavailable ({e}), running in memory-only mode"
                )
                self._redis = None

        # Initialize InfluxDB if not provided
        if self._influxdb is None and settings.telemetry.enabled:
            try:
                from influxdb_client.client.influxdb_client import InfluxDBClient

                self._influxdb = InfluxDBClient(
                    url=settings.influxdb.url,
                    token=settings.influxdb.token,
                    org=settings.influxdb.org,
                )
                logger.info("CircuitBreakerRegistry: InfluxDB connection established")
            except Exception as e:
                logger.warning(
                    f"CircuitBreakerRegistry: InfluxDB unavailable ({e}), telemetry disabled"
                )
                self._influxdb = None

        # Load existing state from Redis
        self._load_from_redis()

    def _get_redis_key(self, name: str) -> str:
        """Get Redis key for a circuit breaker."""
        return f"{self._key_prefix}{name}"

    def _load_from_redis(self) -> None:
        """Load circuit breaker states from Redis."""
        if self._redis is None:
            return

        try:
            pattern = f"{self._key_prefix}*"
            keys = self._redis.keys(pattern)

            # keys() returns either list or awaitable, but we're in sync context
            # type: ignore[union-attr] - We know we're in sync context here
            for key in cast(list, keys) if keys else []:
                try:
                    data = self._redis.get(key)
                    if data:
                        state_dict = json.loads(data)
                        state = CircuitBreakerStateModel.from_dict(state_dict)
                        name = key.replace(self._key_prefix, "")
                        self._registry[name] = state
                        logger.debug(f"Loaded circuit breaker '{name}' from Redis")
                except Exception as e:
                    logger.warning(
                        f"Failed to load circuit breaker from key {key}: {e}"
                    )

            logger.info(f"Loaded {len(self._registry)} circuit breakers from Redis")
        except Exception as e:
            logger.warning(f"Failed to load from Redis: {e}")

    def _persist_to_redis(self, name: str, state: CircuitBreakerStateModel) -> None:
        """Persist a circuit breaker state to Redis."""
        if self._redis is None:
            return

        try:
            key = self._get_redis_key(name)
            data = json.dumps(state.to_dict())
            self._redis.set(key, data)
            logger.debug(f"Persisted circuit breaker '{name}' to Redis")
        except Exception as e:
            logger.warning(f"Failed to persist circuit breaker '{name}' to Redis: {e}")

    def _emit_telemetry(self, name: str, state: CircuitBreakerStateModel) -> None:
        """Emit telemetry to InfluxDB."""
        if self._influxdb is None or not settings.telemetry.enabled:
            return

        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self._influxdb.write_api(write_options=SYNCHRONOUS)

            point = {
                "measurement": settings.cb_telemetry_measurement,
                "tags": {
                    "service_name": name,
                    "state": state.state.value,
                },
                "fields": {
                    "failure_count": state.metrics.failure_count,
                    "success_count": state.metrics.success_count,
                    "rejection_count": state.metrics.rejection_count,
                    "state_transition_count": state.metrics.state_transition_count,
                    "consecutive_successes": state.metrics.consecutive_successes,
                    "consecutive_failures": state.metrics.consecutive_failures,
                    "half_open_calls": state.half_open_calls,
                },
                "time": int(time.time() * 1e9),  # Nanoseconds
            }

            write_api.write(
                bucket=settings.influxdb.bucket,
                org=settings.influxdb.org,
                record=point,
            )

            logger.debug(f"Emitted telemetry for circuit breaker '{name}'")
        except Exception as e:
            logger.warning(f"Failed to emit telemetry for '{name}': {e}")

    def _emit_state_change_event(
        self,
        name: str,
        previous_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
        reason: StateTransitionReason,
    ) -> None:
        """Emit a state change event."""
        event = StateChangeEvent(
            circuit_breaker_name=name,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
        )

        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Event handler failed: {e}")

    def register_event_handler(
        self, handler: Callable[[StateChangeEvent], None]
    ) -> None:
        """Register an event handler for state changes.

        Args:
            handler: Callable that receives StateChangeEvent
        """
        self._event_handlers.append(handler)

    def unregister_event_handler(
        self, handler: Callable[[StateChangeEvent], None]
    ) -> None:
        """Unregister an event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def register(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreakerStateModel:
        """Register a new circuit breaker.

        Args:
            name: Unique identifier for the circuit breaker
            config: Configuration (uses defaults if not provided)

        Returns:
            CircuitBreakerStateModel for the registered breaker
        """
        with self._lock:
            if name in self._registry:
                logger.debug(f"Circuit breaker '{name}' already registered")
                return self._registry[name]

            config = config or CircuitBreakerConfig()
            state = CircuitBreakerStateModel(
                name=name,
                state=CircuitBreakerState.CLOSED,
                config=config,
                metrics=CircuitBreakerMetrics(),
            )

            self._registry[name] = state
            self._persist_to_redis(name, state)
            self._emit_telemetry(name, state)

            logger.info(f"Registered circuit breaker '{name}'")
            return state

    def get(self, name: str) -> CircuitBreakerStateModel | None:
        """Get a circuit breaker by name.

        Args:
            name: Circuit breaker identifier

        Returns:
            CircuitBreakerStateModel or None if not found
        """
        with self._lock:
            return self._registry.get(name)

    def unregister(self, name: str) -> CircuitBreakerStateModel | None:
        """Unregister a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Removed CircuitBreakerStateModel or None
        """
        with self._lock:
            state = self._registry.pop(name, None)

            if state and self._redis:
                try:
                    key = self._get_redis_key(name)
                    self._redis.delete(key)
                except Exception as e:
                    logger.warning(
                        f"Failed to delete circuit breaker '{name}' from Redis: {e}"
                    )

            if state:
                logger.info(f"Unregistered circuit breaker '{name}'")

            return state

    def get_all_states(self) -> dict[str, CircuitBreakerStateModel]:
        """Get all circuit breaker states.

        Returns:
            Dictionary mapping names to CircuitBreakerStateModel
        """
        with self._lock:
            return dict(self._registry)

    def get_all_states_dict(self) -> dict[str, dict[str, Any]]:
        """Get all circuit breaker states as dictionaries.

        Returns:
            Dictionary mapping names to state dictionaries
        """
        with self._lock:
            return {name: state.to_dict() for name, state in self._registry.items()}

    def record_success(self, name: str) -> None:
        """Record a successful call for a circuit breaker.

        Args:
            name: Circuit breaker identifier
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(
                    f"Cannot record success for unknown circuit breaker '{name}'"
                )
                return

            previous_state = state.state
            state.metrics.record_success()

            # Check for state transition from HALF_OPEN to CLOSED
            if (
                state.state == CircuitBreakerState.HALF_OPEN
                and state.metrics.consecutive_successes
                >= state.config.half_open_max_calls
            ):
                state.state = CircuitBreakerState.CLOSED
                state.last_error = None
                state.half_open_calls = 0
                state.metrics.record_state_transition()
                state.updated_at = datetime.now(UTC)

                self._emit_state_change_event(
                    name,
                    previous_state,
                    state.state,
                    StateTransitionReason.RECOVERY_CONFIRMED,
                )
                logger.info(
                    f"Circuit breaker '{name}': HALF_OPEN -> CLOSED (recovery confirmed)"
                )

            self._persist_to_redis(name, state)
            self._emit_telemetry(name, state)

    def record_failure(self, name: str, error: str | None = None) -> None:
        """Record a failed call for a circuit breaker.

        Args:
            name: Circuit breaker identifier
            error: Optional error message
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(
                    f"Cannot record failure for unknown circuit breaker '{name}'"
                )
                return

            previous_state = state.state
            state.last_error = error
            state.metrics.record_failure()

            # Check for state transition
            if state.state == CircuitBreakerState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately opens circuit
                state.state = CircuitBreakerState.OPEN
                state.metrics.record_state_transition()
                state.updated_at = datetime.now(UTC)

                self._emit_state_change_event(
                    name,
                    previous_state,
                    state.state,
                    StateTransitionReason.FAILURE_THRESHOLD,
                )
                logger.warning(
                    f"Circuit breaker '{name}': HALF_OPEN -> OPEN (failure in half-open)"
                )

            elif (
                state.state == CircuitBreakerState.CLOSED
                and state.metrics.consecutive_failures >= state.config.failure_threshold
            ):
                state.state = CircuitBreakerState.OPEN
                state.metrics.record_state_transition()
                state.updated_at = datetime.now(UTC)

                self._emit_state_change_event(
                    name,
                    previous_state,
                    state.state,
                    StateTransitionReason.FAILURE_THRESHOLD,
                )
                logger.warning(
                    f"Circuit breaker '{name}': CLOSED -> OPEN "
                    f"(threshold={state.config.failure_threshold})"
                )

            self._persist_to_redis(name, state)
            self._emit_telemetry(name, state)

    def record_rejection(self, name: str) -> None:
        """Record a rejected call (circuit open) for a circuit breaker.

        Args:
            name: Circuit breaker identifier
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return

            state.metrics.record_rejection()
            self._persist_to_redis(name, state)
            self._emit_telemetry(name, state)

    def can_execute(self, name: str) -> bool:
        """Check if a call can be executed for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            True if call should proceed, False if circuit is open
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(
                    f"Circuit breaker '{name}' not found, allowing execution"
                )
                return True

            if state.state == CircuitBreakerState.CLOSED:
                return True

            if state.state == CircuitBreakerState.OPEN:
                # Check if timeout has elapsed
                elapsed = time.time() - state.metrics.last_state_change.timestamp()
                if elapsed >= state.config.timeout_seconds:
                    previous_state = state.state
                    state.state = CircuitBreakerState.HALF_OPEN
                    state.metrics.record_state_transition()
                    state.half_open_calls = 0
                    state.updated_at = datetime.now(UTC)

                    self._emit_state_change_event(
                        name,
                        previous_state,
                        state.state,
                        StateTransitionReason.TIMEOUT_ELAPSED,
                    )
                    logger.info(
                        f"Circuit breaker '{name}': OPEN -> HALF_OPEN (timeout elapsed)"
                    )

                    self._persist_to_redis(name, state)
                    self._emit_telemetry(name, state)

                    # Allow this call in HALF_OPEN state
                    state.half_open_calls += 1
                    return True

                return False

            if state.state == CircuitBreakerState.HALF_OPEN:
                if state.half_open_calls < state.config.half_open_max_calls:
                    state.half_open_calls += 1
                    return True
                return False

            return False

    def force_open(self, name: str, reason: str = "manual") -> bool:
        """Force a circuit breaker to open state.

        Args:
            name: Circuit breaker identifier
            reason: Reason for forcing open

        Returns:
            True if successful, False if circuit breaker not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(f"Cannot force open unknown circuit breaker '{name}'")
                return False

            if state.state != CircuitBreakerState.OPEN:
                previous_state = state.state
                state.state = CircuitBreakerState.OPEN
                state.metrics.record_state_transition()
                state.updated_at = datetime.now(UTC)

                self._emit_state_change_event(
                    name,
                    previous_state,
                    state.state,
                    StateTransitionReason.MANUAL_FORCE,
                )
                logger.warning(f"Circuit breaker '{name}': Forced OPEN ({reason})")

                self._persist_to_redis(name, state)
                self._emit_telemetry(name, state)

            return True

    def force_close(self, name: str, reason: str = "manual") -> bool:
        """Force a circuit breaker to closed state.

        Args:
            name: Circuit breaker identifier
            reason: Reason for forcing close

        Returns:
            True if successful, False if circuit breaker not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(f"Cannot force close unknown circuit breaker '{name}'")
                return False

            if state.state != CircuitBreakerState.CLOSED:
                previous_state = state.state
                state.state = CircuitBreakerState.CLOSED
                state.last_error = None
                state.half_open_calls = 0
                state.metrics.record_state_transition()
                state.updated_at = datetime.now(UTC)

                self._emit_state_change_event(
                    name,
                    previous_state,
                    state.state,
                    StateTransitionReason.MANUAL_FORCE,
                )
                logger.info(f"Circuit breaker '{name}': Forced CLOSED ({reason})")

                self._persist_to_redis(name, state)
                self._emit_telemetry(name, state)

            return True

    def reset(self, name: str) -> bool:
        """Reset a circuit breaker to initial state.

        Args:
            name: Circuit breaker identifier

        Returns:
            True if successful, False if circuit breaker not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                logger.warning(f"Cannot reset unknown circuit breaker '{name}'")
                return False

            previous_state = state.state
            state.state = CircuitBreakerState.CLOSED
            state.metrics = CircuitBreakerMetrics()
            state.half_open_calls = 0
            state.last_error = None
            state.updated_at = datetime.now(UTC)

            self._emit_state_change_event(
                name, previous_state, state.state, StateTransitionReason.MANUAL_RESET
            )
            logger.info(f"Circuit breaker '{name}': Reset")

            self._persist_to_redis(name, state)
            self._emit_telemetry(name, state)

            return True

    def reset_all(self) -> None:
        """Reset all registered circuit breakers."""
        with self._lock:
            for name in list(self._registry.keys()):
                self.reset(name)
            logger.info("All circuit breakers reset")

    def force_open_all(self, reason: str = "manual") -> None:
        """Force open all registered circuit breakers.

        Args:
            reason: Reason for forcing open
        """
        with self._lock:
            for name in list(self._registry.keys()):
                self.force_open(name, reason)
            logger.warning(f"All circuit breakers forced OPEN ({reason})")

    def force_close_all(self, reason: str = "manual") -> None:
        """Force close all registered circuit breakers.

        Args:
            reason: Reason for forcing close
        """
        with self._lock:
            for name in list(self._registry.keys()):
                self.force_close(name, reason)
            logger.info(f"All circuit breakers forced CLOSED ({reason})")

    def get_health(self, name: str) -> CircuitBreakerHealth | None:
        """Get health status for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            CircuitBreakerHealth or None if not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return None

            total_calls = (
                state.metrics.success_count
                + state.metrics.failure_count
                + state.metrics.rejection_count
            )

            failure_rate = (
                state.metrics.failure_count / total_calls if total_calls > 0 else 0.0
            )
            rejection_rate = (
                state.metrics.rejection_count / total_calls if total_calls > 0 else 0.0
            )

            is_healthy = (
                state.state == CircuitBreakerState.CLOSED and failure_rate < 0.1
            )

            recommendation = ""
            if state.state == CircuitBreakerState.OPEN:
                recommendation = (
                    "Investigate service failure; manual intervention may be required"
                )
            elif state.state == CircuitBreakerState.HALF_OPEN:
                recommendation = "Service recovering; monitor closely"
            elif failure_rate > 0.05:
                recommendation = "Elevated failure rate; consider investigation"
            else:
                recommendation = "Healthy"

            return CircuitBreakerHealth(
                name=name,
                state=state.state,
                is_healthy=is_healthy,
                failure_rate=failure_rate,
                rejection_rate=rejection_rate,
                last_error=state.last_error,
                recommendation=recommendation,
            )

    def get_all_health(self) -> dict[str, CircuitBreakerHealth]:
        """Get health status for all circuit breakers.

        Returns:
            Dictionary mapping names to CircuitBreakerHealth
        """
        with self._lock:
            result = {}
            for name in self._registry:
                health = self.get_health(name)
                if health is not None:
                    result[name] = health
            return result

    def flush_telemetry(self) -> None:
        """Manually flush telemetry for all circuit breakers."""
        with self._lock:
            for name, state in self._registry.items():
                self._emit_telemetry(name, state)
        logger.info("Telemetry flushed for all circuit breakers")

    # ==================== Adaptive Threshold Methods ====================

    def _check_and_adjust_adaptive_threshold(
        self, name: str, state: CircuitBreakerStateModel
    ) -> None:
        """Check and adjust adaptive threshold based on failure patterns.

        Args:
            name: Circuit breaker identifier
            state: Current circuit breaker state
        """
        if not state.config.adaptive_threshold.enabled:
            return

        config = state.config.adaptive_threshold
        metrics = state.metrics.adaptive

        # Check cooldown
        if metrics.last_adjustment_time is not None:
            elapsed = (datetime.now(UTC) - metrics.last_adjustment_time).total_seconds()
            if elapsed < config.adjustment_cooldown_seconds:
                return

        # Update baseline from 15min window
        metrics.update_baseline()

        # Calculate new threshold based on baseline
        if metrics.baseline_failure_rate > 0:
            # Estimate calls in a typical window (use 1min window total as proxy)
            window_1min = metrics.windows.get(60)
            if window_1min and window_1min.total_calls > 0:
                estimated_calls_per_minute = window_1min.total_calls
                baseline_failures = (
                    metrics.baseline_failure_rate * estimated_calls_per_minute
                )
                new_threshold = int(baseline_failures * config.baseline_multiplier)

                # Clamp to min/max
                new_threshold = max(
                    config.min_threshold, min(config.max_threshold, new_threshold)
                )

                if new_threshold != metrics.current_threshold:
                    old_threshold = metrics.current_threshold
                    metrics.current_threshold = new_threshold
                    metrics.last_adjustment_time = datetime.now(UTC)
                    metrics.adjustment_count += 1

                    logger.info(
                        f"Circuit breaker '{name}': Adaptive threshold adjusted "
                        f"{old_threshold} -> {new_threshold} "
                        f"(baseline_rate={metrics.baseline_failure_rate:.2%})"
                    )

                    # Update the config threshold as well
                    state.config.failure_threshold = new_threshold

    def get_adaptive_metrics(self, name: str) -> dict[str, Any] | None:
        """Get adaptive threshold metrics for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Adaptive metrics dictionary or None if not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return None
            return state.metrics.adaptive.to_dict()

    # ==================== Canary Recovery Methods ====================

    def _check_canary_promotion(
        self, name: str, state: CircuitBreakerStateModel
    ) -> bool:
        """Check if canary recovery should promote to next step or close.

        Args:
            name: Circuit breaker identifier
            state: Current circuit breaker state

        Returns:
            True if circuit should be closed (fully recovered)
        """
        if not state.config.canary_recovery.enabled:
            # Default behavior: close after consecutive successes
            return (
                state.metrics.consecutive_successes >= state.config.half_open_max_calls
            )

        config = state.config.canary_recovery
        canary = state.metrics.canary

        # Record this success in canary state
        canary.record_success()

        # Check if we've met criteria for current step
        if canary.current_step_requests >= config.min_requests_per_step:
            if canary.current_step_success_rate >= config.success_rate_threshold:
                # Promote to next step
                steps = config.progression_steps
                if canary.current_step_index + 1 >= len(steps):
                    # Fully recovered
                    logger.info(
                        f"Circuit breaker '{name}': Canary recovery complete, "
                        f"closing circuit"
                    )
                    return True
                else:
                    canary.promote_to_next_step()
                    logger.info(
                        f"Circuit breaker '{name}': Canary promoted to step "
                        f"{canary.current_step_index} ({steps[canary.current_step_index]:.0%} traffic)"
                    )
                    self._emit_state_change_event(
                        name,
                        state.state,
                        state.state,
                        StateTransitionReason.CANARY_PROMOTION,
                    )

        return False

    def get_canary_state(self, name: str) -> dict[str, Any] | None:
        """Get canary recovery state for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Canary state dictionary or None if not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return None
            return state.metrics.canary.to_dict()

    def get_canary_traffic_percent(self, name: str) -> float:
        """Get the current canary traffic percentage for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Traffic percentage (0.0 - 1.0) or 0.0 if not in canary mode
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return 0.0

            if not state.config.canary_recovery.enabled:
                return 1.0 if state.state == CircuitBreakerState.CLOSED else 0.0

            if state.state != CircuitBreakerState.HALF_OPEN:
                return 1.0 if state.state == CircuitBreakerState.CLOSED else 0.0

            steps = state.config.canary_recovery.progression_steps
            step_index = state.metrics.canary.current_step_index
            return steps[min(step_index, len(steps) - 1)]

    # ==================== Predictive Alert Methods ====================

    def _check_predictive_alert(
        self, name: str, state: CircuitBreakerStateModel
    ) -> dict[str, Any] | None:
        """Check if a predictive alert should be triggered.

        Args:
            name: Circuit breaker identifier
            state: Current circuit breaker state

        Returns:
            Alert data if triggered, None otherwise
        """
        if not state.config.predictive_alerts.enabled:
            return None

        config = state.config.predictive_alerts
        predictive = state.metrics.predictive

        # Update threshold approach
        predictive.update_threshold_approach(
            state.metrics.consecutive_failures, state.config.failure_threshold
        )

        # Check for velocity alert
        velocity_alert = predictive.failure_velocity >= config.velocity_threshold

        # Check for threshold approach alert
        threshold_alert = predictive.should_alert(
            config.threshold_warning_percent, config.alert_cooldown_seconds
        )

        if velocity_alert or threshold_alert:
            predictive.record_alert()

            alert_data = {
                "circuit_breaker": name,
                "timestamp": datetime.now(UTC).isoformat(),
                "velocity": predictive.failure_velocity,
                "threshold_approach": predictive.threshold_approach_percent,
                "velocity_alert": velocity_alert,
                "threshold_alert": threshold_alert,
                "message": self._generate_alert_message(
                    name, state, velocity_alert, threshold_alert
                ),
            }

            logger.warning(
                f"Circuit breaker '{name}': Predictive alert triggered - "
                f"velocity={predictive.failure_velocity:.2f}/s, "
                f"threshold_at={predictive.threshold_approach_percent:.0%}"
            )

            return alert_data

        return None

    def _generate_alert_message(
        self,
        name: str,
        state: CircuitBreakerStateModel,
        velocity_alert: bool,
        threshold_alert: bool,
    ) -> str:
        """Generate human-readable alert message."""
        messages = []
        if velocity_alert:
            messages.append(
                f"High failure velocity detected ({state.metrics.predictive.failure_velocity:.2f} failures/sec)"
            )
        if threshold_alert:
            messages.append(
                f"Approaching failure threshold ({state.metrics.predictive.threshold_approach_percent:.0%})"
            )
        return f"Circuit breaker '{name}': {'; '.join(messages)}"

    def get_predictive_state(self, name: str) -> dict[str, Any] | None:
        """Get predictive alert state for a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Predictive state dictionary or None if not found
        """
        with self._lock:
            state = self._registry.get(name)
            if state is None:
                return None
            return state.metrics.predictive.to_dict()

    def check_all_predictive_alerts(self) -> list[dict[str, Any]]:
        """Check predictive alerts for all circuit breakers.

        Returns:
            List of alert data for triggered alerts
        """
        alerts = []
        with self._lock:
            for name, state in self._registry.items():
                alert = self._check_predictive_alert(name, state)
                if alert:
                    alerts.append(alert)
        return alerts

    # ==================== Circuit Breaker Group Methods ====================

    def create_group(
        self,
        name: str,
        member_names: list[str] | None = None,
        cascade_open: bool = True,
        cascade_close: bool = False,
    ) -> CircuitBreakerGroup:
        """Create a new circuit breaker group.

        Args:
            name: Group name
            member_names: List of circuit breaker names to add
            cascade_open: Whether to cascade open operations
            cascade_close: Whether to cascade close operations

        Returns:
            Created CircuitBreakerGroup
        """
        with self._lock:
            group = CircuitBreakerGroup(
                name=name,
                member_names=member_names or [],
                cascade_open=cascade_open,
                cascade_close=cascade_close,
            )

            # Persist to Redis
            if self._redis:
                try:
                    key = f"{self._key_prefix}group:{name}"
                    self._redis.set(key, json.dumps(group.to_dict()))
                except Exception as e:
                    logger.warning(f"Failed to persist group '{name}' to Redis: {e}")

            logger.info(
                f"Created circuit breaker group '{name}' with {len(group.member_names)} members"
            )
            return group

    def get_group(self, name: str) -> CircuitBreakerGroup | None:
        """Get a circuit breaker group by name.

        Args:
            name: Group name

        Returns:
            CircuitBreakerGroup or None if not found
        """
        with self._lock:
            # Try to load from Redis
            if self._redis:
                try:
                    key = f"{self._key_prefix}group:{name}"
                    data = self._redis.get(key)
                    if data:
                        return CircuitBreakerGroup.from_dict(json.loads(data))
                except Exception as e:
                    logger.warning(f"Failed to load group '{name}' from Redis: {e}")

            return None

    def delete_group(self, name: str) -> bool:
        """Delete a circuit breaker group.

        Args:
            name: Group name

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if self._redis:
                try:
                    key = f"{self._key_prefix}group:{name}"
                    result = self._redis.delete(key)
                    if result:
                        logger.info(f"Deleted circuit breaker group '{name}'")
                        return True
                except Exception as e:
                    logger.warning(f"Failed to delete group '{name}' from Redis: {e}")

            return False

    def add_to_group(self, group_name: str, circuit_breaker_name: str) -> bool:
        """Add a circuit breaker to a group.

        Args:
            group_name: Group name
            circuit_breaker_name: Circuit breaker name

        Returns:
            True if added successfully
        """
        with self._lock:
            group = self.get_group(group_name)
            if group is None:
                logger.warning(f"Cannot add to unknown group '{group_name}'")
                return False

            group.add_member(circuit_breaker_name)

            # Persist updated group
            if self._redis:
                try:
                    key = f"{self._key_prefix}group:{group_name}"
                    self._redis.set(key, json.dumps(group.to_dict()))
                except Exception as e:
                    logger.warning(
                        f"Failed to update group '{group_name}' in Redis: {e}"
                    )

            return True

    def remove_from_group(self, group_name: str, circuit_breaker_name: str) -> bool:
        """Remove a circuit breaker from a group.

        Args:
            group_name: Group name
            circuit_breaker_name: Circuit breaker name

        Returns:
            True if removed successfully
        """
        with self._lock:
            group = self.get_group(group_name)
            if group is None:
                return False

            result = group.remove_member(circuit_breaker_name)

            if result and self._redis:
                try:
                    key = f"{self._key_prefix}group:{group_name}"
                    self._redis.set(key, json.dumps(group.to_dict()))
                except Exception as e:
                    logger.warning(
                        f"Failed to update group '{group_name}' in Redis: {e}"
                    )

            return result

    def _cascade_to_group(
        self, name: str, operation: str, reason: str = "cascade"
    ) -> list[str]:
        """Cascade an operation to all members of a circuit breaker's groups.

        Args:
            name: Circuit breaker that triggered the cascade
            operation: 'open' or 'close'
            reason: Reason for the cascade

        Returns:
            List of affected circuit breaker names
        """
        affected = []

        # Find all groups containing this circuit breaker
        # Note: In a production system, we'd maintain an index for efficiency
        # For now, we scan (this is a simplification)

        if self._redis:
            try:
                pattern = f"{self._key_prefix}group:*"
                keys = self._redis.keys(pattern)
                for key in cast(list, keys) if keys else []:
                    try:
                        data = self._redis.get(key)
                        if data:
                            group = CircuitBreakerGroup.from_dict(json.loads(data))
                            if name in group.member_names:
                                # Cascade to other members
                                for member_name in group.member_names:
                                    if member_name != name:
                                        if operation == "open" and group.cascade_open:
                                            if self.force_open(
                                                member_name, f"{reason} from {name}"
                                            ):
                                                affected.append(member_name)
                                        elif (
                                            operation == "close" and group.cascade_close
                                        ):
                                            if self.force_close(
                                                member_name, f"{reason} from {name}"
                                            ):
                                                affected.append(member_name)
                    except Exception as e:
                        logger.warning(f"Failed to process group key {key}: {e}")
            except Exception as e:
                logger.warning(f"Failed to cascade operation: {e}")

        return affected

    def get_group_metrics(self, group_name: str) -> CircuitBreakerGroupMetrics | None:
        """Get aggregated metrics for a circuit breaker group.

        Args:
            group_name: Group name

        Returns:
            CircuitBreakerGroupMetrics or None if group not found
        """
        with self._lock:
            group = self.get_group(group_name)
            if group is None:
                return None

            metrics = CircuitBreakerGroupMetrics(group_name=group_name)
            metrics.total_members = len(group.member_names)

            for member_name in group.member_names:
                state = self._registry.get(member_name)
                if state:
                    health = self.get_health(member_name)
                    if health:
                        metrics.member_health[member_name] = health

                        # Count states
                        if state.state == CircuitBreakerState.OPEN:
                            metrics.open_count += 1
                        elif state.state == CircuitBreakerState.CLOSED:
                            metrics.closed_count += 1
                        elif state.state == CircuitBreakerState.HALF_OPEN:
                            metrics.half_open_count += 1

                        # Aggregate metrics
                        metrics.total_failures += state.metrics.failure_count
                        metrics.total_successes += state.metrics.success_count
                        metrics.total_rejections += state.metrics.rejection_count

            # Calculate overall health
            if metrics.total_members > 0:
                healthy_count = sum(
                    1 for h in metrics.member_health.values() if h.is_healthy
                )
                metrics.overall_health_percent = (
                    healthy_count / metrics.total_members
                ) * 100

            return metrics

    def list_groups(self) -> list[str]:
        """List all circuit breaker group names.

        Returns:
            List of group names
        """
        groups = []

        if self._redis:
            try:
                pattern = f"{self._key_prefix}group:*"
                keys = self._redis.keys(pattern)
                for key in cast(list, keys) if keys else []:
                    # Extract group name from key
                    name = key.replace(f"{self._key_prefix}group:", "")
                    groups.append(name)
            except Exception as e:
                logger.warning(f"Failed to list groups: {e}")

        return groups
