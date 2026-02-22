"""Circuit Breaker Registry with Redis persistence.

Provides centralized management of circuit breakers across all services
with automatic state persistence and telemetry emission.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from autonomous_control_plane.config.settings import settings
from autonomous_control_plane.models.circuit_breaker import (
    CircuitBreakerConfig,
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
                state.updated_at = datetime.utcnow()

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
                state.updated_at = datetime.utcnow()

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
                state.updated_at = datetime.utcnow()

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
                    state.updated_at = datetime.utcnow()

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
                state.updated_at = datetime.utcnow()

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
                state.updated_at = datetime.utcnow()

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
            state.updated_at = datetime.utcnow()

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
            for name in self._registry.keys():
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
