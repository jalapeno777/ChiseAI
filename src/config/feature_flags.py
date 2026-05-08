"""Feature flags configuration for ChiseAI.

Centralized feature flags for enabling/disabling system components.
All flags support environment variable overrides and Redis-backed runtime toggling.
Flags persist across restarts via Redis storage.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# Redis key prefix for feature flags
REDIS_PREFIX = "chise:feature_flags:config"


@dataclass(frozen=True)
class FeatureFlags:
    """Feature flags for ChiseAI components.

    SAFETY-FIRST DESIGN: All safety-critical flags default to ENABLED (True).
    Missing or invalid configuration values will NOT disable safety features.

    To explicitly disable a flag, set the corresponding environment variable
    to one of: 'false', '0', 'no', 'off' (case-insensitive).

    Redis Persistence:
        All flags are stored in Redis and survive restarts.
        Priority: Redis > Environment Variable > Default

    Attributes:
        retraining_ece_trigger: Enable ECE-based retraining triggers [SAFETY]
        retraining_performance_trigger: Enable performance-based retraining triggers [SAFETY]
        retraining_scheduled_trigger: Enable scheduled retraining triggers [SAFETY]
        retraining_deduplication: Enable 24h deduplication window [SAFETY]
        retraining_pre_validation: Enable pre-training quality validation [SAFETY]
        retraining_discord_alerts: Enable Discord alerts on triggers
        launch_training_pipeline_enabled: Enable training pipeline integration [SAFETY]
        persona_regression_enabled: Enable persona regression scheduling gate [SAFETY]
    """

    # Redis key constants
    KEY_RETRAINING_ECE: ClassVar[str] = f"{REDIS_PREFIX}:retraining_ece_trigger"
    KEY_RETRAINING_PERF: ClassVar[str] = (
        f"{REDIS_PREFIX}:retraining_performance_trigger"
    )
    KEY_RETRAINING_SCHEDULED: ClassVar[str] = (
        f"{REDIS_PREFIX}:retraining_scheduled_trigger"
    )
    KEY_RETRAINING_DEDUP: ClassVar[str] = f"{REDIS_PREFIX}:retraining_deduplication"
    KEY_RETRAINING_PRE_VALIDATION: ClassVar[str] = (
        f"{REDIS_PREFIX}:retraining_pre_validation"
    )
    KEY_RETRAINING_DISCORD: ClassVar[str] = f"{REDIS_PREFIX}:retraining_discord_alerts"
    KEY_LAUNCH_PIPELINE: ClassVar[str] = (
        f"{REDIS_PREFIX}:launch_training_pipeline_enabled"
    )
    KEY_PERSONA_REGRESSION: ClassVar[str] = f"{REDIS_PREFIX}:persona_regression_enabled"

    # ST-FILL-001: Fill polling
    KEY_BYBIT_FILL_POLLING: ClassVar[str] = f"{REDIS_PREFIX}:bybit_fill_polling_enabled"
    KEY_BYBIT_FILL_POLL_TIMEOUT: ClassVar[str] = (
        f"{REDIS_PREFIX}:bybit_fill_poll_timeout_ms"
    )

    # ST-FILL-003: BybitFillListener integration
    KEY_BYBIT_FILL_LISTENER: ClassVar[str] = (
        f"{REDIS_PREFIX}:bybit_fill_listener_enabled"
    )

    # ST-FILL-004: Reconciliation monitor
    KEY_RECONCILIATION_MONITOR: ClassVar[str] = (
        f"{REDIS_PREFIX}:reconciliation_monitor_enabled"
    )
    KEY_RECONCILIATION_CHECK_INTERVAL: ClassVar[str] = (
        f"{REDIS_PREFIX}:reconciliation_check_interval_seconds"
    )
    KEY_RECONCILIATION_ALERT_THRESHOLD: ClassVar[str] = (
        f"{REDIS_PREFIX}:reconciliation_alert_threshold_hours"
    )

    # ST-FILL-007: Rollback safety
    KEY_FILL_ROLLBACK_ON_ERROR: ClassVar[str] = (
        f"{REDIS_PREFIX}:fill_rollback_on_error_enabled"
    )
    KEY_RECONCILIATION_AUTO_BACKFILL: ClassVar[str] = (
        f"{REDIS_PREFIX}:reconciliation_auto_backfill"
    )

    # PAPER-RECON-001: Force simulator mode for paper execution routing
    KEY_FORCE_SIMULATOR_MODE: ClassVar[str] = f"{REDIS_PREFIX}:force_simulator_mode"

    # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory Architecture
    KEY_MEMORY_HYBRID_ENABLED: ClassVar[str] = f"{REDIS_PREFIX}:memory_hybrid_enabled"
    KEY_MEMORY_HYBRID_CANARY_PERCENTAGE: ClassVar[str] = (
        f"{REDIS_PREFIX}:memory:canary_percentage"
    )
    KEY_MEMORY_HYBRID_ALLOWLIST: ClassVar[str] = (
        f"{REDIS_PREFIX}:memory:canary_allowlist"
    )

    # Default canary percentage (0 = off by default)
    DEFAULT_CANARY_PERCENTAGE: ClassVar[int] = 0

    # TTL for Redis flag storage (seconds) - 24 hours
    FLAG_TTL: ClassVar[int] = 86400

    # Retraining trigger flags
    retraining_ece_trigger: bool = True
    retraining_performance_trigger: bool = True
    retraining_scheduled_trigger: bool = True
    retraining_deduplication: bool = True
    retraining_pre_validation: bool = True
    retraining_discord_alerts: bool = True

    # Training pipeline integration (ST-LAUNCH-012)
    launch_training_pipeline_enabled: bool = True

    # Persona regression scheduling gate (SAFETY)
    persona_regression_enabled: bool = True

    # ST-FILL-001: Fill polling
    bybit_fill_polling_enabled: bool = True
    bybit_fill_poll_timeout_ms: int = 5000

    # ST-FILL-003: BybitFillListener integration
    bybit_fill_listener_enabled: bool = False

    # ST-FILL-004: Reconciliation monitor
    reconciliation_monitor_enabled: bool = True
    reconciliation_check_interval_seconds: int = 3600
    reconciliation_alert_threshold_hours: float = 24.0

    # ST-FILL-007: Rollback safety
    fill_rollback_on_error_enabled: bool = False
    reconciliation_auto_backfill: bool = True

    # PAPER-RECON-001: Force simulator mode
    # When True: force use of OrderSimulator even if Bybit demo credentials available
    # When False: prefer BybitDemoConnector when credentials available
    force_simulator_mode: bool = False

    # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory Architecture
    # Default False (opt-in for Phase 4)
    memory_hybrid_enabled: bool = False

    # Redis client reference (not frozen, but accessed via property)
    _redis_client: Any = field(default=None, repr=False, compare=False)

    @property
    def redis_client(self) -> Any:
        """Get Redis client, lazily initialized if needed."""
        # Use object.__setattr__ because dataclass is frozen
        if self._redis_client is None:
            client = self._get_redis_client()
            object.__setattr__(self, "_redis_client", client)
        return self._redis_client

    @staticmethod
    def _get_redis_client() -> Any:
        """Get Redis client from environment or return None for testing."""
        try:
            import redis

            redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
            redis_port = int(os.getenv("REDIS_PORT", "6380"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            redis_password = os.getenv("REDIS_PASSWORD", None)

            return redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        except Exception as e:
            logger.debug(f"Could not connect to Redis: {e}")
            return None

    def get_redis_value(self, key: str, default: bool) -> bool:
        """Get flag value from Redis with fallback to default.

        Args:
            key: Redis key for the flag
            default: Default value if not in Redis

        Returns:
            Boolean value from Redis or default
        """
        client = self.redis_client
        if client is None:
            return default
        try:
            value = client.get(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")
        except Exception as e:
            logger.warning(f"Redis error reading {key}: {e}")
            return default

    def _get_redis_set(self, key: str) -> set[str]:
        """Get a set value from Redis.

        Args:
            key: Redis key for the set

        Returns:
            Set of strings from Redis, or empty set if not found/error
        """
        client = self.redis_client
        if client is None:
            return set()
        try:
            value = client.smembers(key)
            if value is None:
                return set()
            return set(value)
        except Exception as e:
            logger.warning(f"Redis error reading set {key}: {e}")
            return set()

    def _get_int(self, key: str, default: int) -> int:
        """Get an integer value from Redis.

        Args:
            key: Redis key for the value
            default: Default value if not in Redis

        Returns:
            Integer value from Redis or default
        """
        client = self.redis_client
        if client is None:
            return default
        try:
            value = client.get(key)
            if value is None:
                return default
            return int(value)
        except Exception as e:
            logger.warning(f"Redis error reading {key}: {e}")
            return default

    def _set_int(self, key: str, value: int) -> bool:
        """Set an integer value in Redis.

        Args:
            key: Redis key for the value
            value: Integer value to set

        Returns:
            True if successfully set, False otherwise
        """
        client = self.redis_client
        if client is None:
            logger.warning("Redis not available, cannot set value")
            return False
        try:
            client.setex(key, self.FLAG_TTL, str(value))
            return True
        except Exception as e:
            logger.error(f"Redis error setting {key}: {e}")
            return False

    def set_redis_value(self, key: str, value: bool, audit_log: bool = True) -> bool:
        """Set flag value in Redis with optional audit logging.

        Args:
            key: Redis key for the flag
            value: Boolean value to set
            audit_log: Whether to log the change

        Returns:
            True if successfully set, False otherwise
        """
        client = self.redis_client
        if client is None:
            logger.warning("Redis not available, cannot set flag")
            return False
        try:
            str_value = "true" if value else "false"
            client.setex(key, self.FLAG_TTL, str_value)
            if audit_log:
                logger.info(f"Feature Flag changed: {key} = {str_value}")
            return True
        except Exception as e:
            logger.error(f"Redis error setting {key}: {e}")
            return False

    # Runtime flag checking methods (check Redis first, fallback to defaults)

    def is_retraining_ece_trigger_enabled(self) -> bool:
        """Check if ECE retraining trigger is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_ECE, self.retraining_ece_trigger
        )

    def is_retraining_performance_trigger_enabled(self) -> bool:
        """Check if performance retraining trigger is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_PERF, self.retraining_performance_trigger
        )

    def is_retraining_scheduled_trigger_enabled(self) -> bool:
        """Check if scheduled retraining trigger is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_SCHEDULED, self.retraining_scheduled_trigger
        )

    def is_retraining_deduplication_enabled(self) -> bool:
        """Check if retraining deduplication is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_DEDUP, self.retraining_deduplication
        )

    def is_retraining_pre_validation_enabled(self) -> bool:
        """Check if pre-training validation is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_PRE_VALIDATION, self.retraining_pre_validation
        )

    def is_retraining_discord_alerts_enabled(self) -> bool:
        """Check if Discord alerts on retraining triggers is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RETRAINING_DISCORD, self.retraining_discord_alerts
        )

    def is_launch_training_pipeline_enabled(self) -> bool:
        """Check if training pipeline launch is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_LAUNCH_PIPELINE, self.launch_training_pipeline_enabled
        )

    def is_persona_regression_enabled(self) -> bool:
        """Check if persona regression scheduling is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_PERSONA_REGRESSION, self.persona_regression_enabled
        )

    # ST-FILL-001: Fill polling
    def is_bybit_fill_polling_enabled(self) -> bool:
        """Check if Bybit fill polling is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_BYBIT_FILL_POLLING, self.bybit_fill_polling_enabled
        )

    def get_bybit_fill_poll_timeout_ms(self) -> int:
        """Get Bybit fill poll timeout in milliseconds."""
        client = self.redis_client
        if client is None:
            return self.bybit_fill_poll_timeout_ms
        try:
            value = client.get(self.KEY_BYBIT_FILL_POLL_TIMEOUT)
            if value is None:
                return self.bybit_fill_poll_timeout_ms
            return int(value)
        except Exception as e:
            logger.warning(
                f"Redis error reading {self.KEY_BYBIT_FILL_POLL_TIMEOUT}: {e}"
            )
            return self.bybit_fill_poll_timeout_ms

    # ST-FILL-003: BybitFillListener integration
    def is_bybit_fill_listener_enabled(self) -> bool:
        """Check if Bybit WebSocket fill listener is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_BYBIT_FILL_LISTENER, self.bybit_fill_listener_enabled
        )

    # ST-FILL-004: Reconciliation monitor
    def is_reconciliation_monitor_enabled(self) -> bool:
        """Check if reconciliation monitor is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RECONCILIATION_MONITOR, self.reconciliation_monitor_enabled
        )

    def get_reconciliation_check_interval_seconds(self) -> int:
        """Get reconciliation check interval in seconds."""
        client = self.redis_client
        if client is None:
            return self.reconciliation_check_interval_seconds
        try:
            value = client.get(self.KEY_RECONCILIATION_CHECK_INTERVAL)
            if value is None:
                return self.reconciliation_check_interval_seconds
            return int(value)
        except Exception as e:
            logger.warning(
                f"Redis error reading {self.KEY_RECONCILIATION_CHECK_INTERVAL}: {e}"
            )
            return self.reconciliation_check_interval_seconds

    def get_reconciliation_alert_threshold_hours(self) -> float:
        """Get reconciliation alert threshold in hours."""
        client = self.redis_client
        if client is None:
            return self.reconciliation_alert_threshold_hours
        try:
            value = client.get(self.KEY_RECONCILIATION_ALERT_THRESHOLD)
            if value is None:
                return self.reconciliation_alert_threshold_hours
            return float(value)
        except Exception as e:
            logger.warning(
                f"Redis error reading {self.KEY_RECONCILIATION_ALERT_THRESHOLD}: {e}"
            )
            return self.reconciliation_alert_threshold_hours

    # ST-FILL-007: Rollback safety
    def is_fill_rollback_on_error_enabled(self) -> bool:
        """Check if fill rollback on error is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_FILL_ROLLBACK_ON_ERROR, self.fill_rollback_on_error_enabled
        )

    def is_reconciliation_auto_backfill_enabled(self) -> bool:
        """Check if reconciliation auto backfill is enabled (Redis or default)."""
        return self.get_redis_value(
            self.KEY_RECONCILIATION_AUTO_BACKFILL, self.reconciliation_auto_backfill
        )

    # PAPER-RECON-001: Force simulator mode
    def is_force_simulator_mode_enabled(self) -> bool:
        """Check if force simulator mode is enabled (Redis or default).

        When True: force use of OrderSimulator even if Bybit demo credentials available.
        When False: prefer BybitDemoConnector when credentials available (default).
        """
        return self.get_redis_value(
            self.KEY_FORCE_SIMULATOR_MODE, self.force_simulator_mode
        )

    # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory Architecture
    def is_memory_hybrid_enabled(self) -> bool:
        """Check if Phase 4 hybrid memory context assembly is enabled.

        When False: uses direct Qdrant retrieval (safe fallback).
        When True: uses full Context Assembly pipeline with DomainContext.

        Default: False (opt-in for Phase 4).
        """
        return self.get_redis_value(
            self.KEY_MEMORY_HYBRID_ENABLED, self.memory_hybrid_enabled
        )

    def is_memory_hybrid_enabled_for_session(self, session_id: str) -> bool:
        """Deterministic hash-based canary routing for hybrid memory.

        - Global disabled -> False (kill switch)
        - Session in allowlist -> True (emergency override)
        - Otherwise -> hash(session_id) % 100 < percentage

        Args:
            session_id: The session ID to check routing for.

        Returns:
            True if session should use hybrid context assembly.
        """
        if not self.is_memory_hybrid_enabled():
            return False  # Kill switch

        allowlist = self._get_redis_set(self.KEY_MEMORY_HYBRID_ALLOWLIST)
        if session_id in allowlist:
            return True

        percentage = self._get_int(
            self.KEY_MEMORY_HYBRID_CANARY_PERCENTAGE,
            self.DEFAULT_CANARY_PERCENTAGE,
        )
        if percentage <= 0:
            return False
        if percentage >= 100:
            return True

        return hash(session_id) % 100 < percentage

    def set_canary_percentage(self, percentage: int) -> bool:
        """Set the canary routing percentage (0-100).

        Args:
            percentage: Percentage of sessions to route to hybrid (0-100).

        Returns:
            True if successfully set, False otherwise.
        """
        return self._set_int(self.KEY_MEMORY_HYBRID_CANARY_PERCENTAGE, percentage)

    def add_canary_allowlist(self, session_id: str) -> bool:
        """Add a session ID to the canary allowlist.

        Args:
            session_id: The session ID to add to allowlist.

        Returns:
            True if successfully added, False otherwise.
        """
        client = self.redis_client
        if client is None:
            logger.warning("Redis not available, cannot add to allowlist")
            return False
        try:
            client.sadd(self.KEY_MEMORY_HYBRID_ALLOWLIST, session_id)
            return True
        except Exception as e:
            logger.error(f"Redis error adding to allowlist: {e}")
            return False

    def get_canary_percentage(self) -> int:
        """Get the current canary routing percentage.

        Returns:
            Current canary percentage (0-100).
        """
        return self._get_int(
            self.KEY_MEMORY_HYBRID_CANARY_PERCENTAGE,
            self.DEFAULT_CANARY_PERCENTAGE,
        )

    # Runtime flag setters (write to Redis)

    def set_retraining_ece_trigger_enabled(self, enabled: bool) -> bool:
        """Enable or disable ECE retraining trigger."""
        return self.set_redis_value(self.KEY_RETRAINING_ECE, enabled)

    def set_retraining_performance_trigger_enabled(self, enabled: bool) -> bool:
        """Enable or disable performance retraining trigger."""
        return self.set_redis_value(self.KEY_RETRAINING_PERF, enabled)

    def set_retraining_scheduled_trigger_enabled(self, enabled: bool) -> bool:
        """Enable or disable scheduled retraining trigger."""
        return self.set_redis_value(self.KEY_RETRAINING_SCHEDULED, enabled)

    def set_retraining_deduplication_enabled(self, enabled: bool) -> bool:
        """Enable or disable retraining deduplication."""
        return self.set_redis_value(self.KEY_RETRAINING_DEDUP, enabled)

    def set_retraining_pre_validation_enabled(self, enabled: bool) -> bool:
        """Enable or disable pre-training validation."""
        return self.set_redis_value(self.KEY_RETRAINING_PRE_VALIDATION, enabled)

    def set_retraining_discord_alerts_enabled(self, enabled: bool) -> bool:
        """Enable or disable Discord alerts on retraining triggers."""
        return self.set_redis_value(self.KEY_RETRAINING_DISCORD, enabled)

    def set_launch_training_pipeline_enabled(self, enabled: bool) -> bool:
        """Enable or disable training pipeline launch."""
        return self.set_redis_value(self.KEY_LAUNCH_PIPELINE, enabled)

    def set_persona_regression_enabled(self, enabled: bool) -> bool:
        """Enable or disable persona regression scheduling."""
        return self.set_redis_value(self.KEY_PERSONA_REGRESSION, enabled)

    # PAPER-RECON-001: Force simulator mode
    def set_force_simulator_mode_enabled(self, enabled: bool) -> bool:
        """Enable or disable force simulator mode.

        When True: force use of OrderSimulator even if Bybit demo credentials available.
        When False: prefer BybitDemoConnector when credentials available.
        """
        return self.set_redis_value(self.KEY_FORCE_SIMULATOR_MODE, enabled)

    # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory Architecture
    def set_memory_hybrid_enabled(self, enabled: bool) -> bool:
        """Enable or disable Phase 4 hybrid memory context assembly.

        When enabling: ensures full Context Assembly pipeline with DomainContext.
        When disabling: reverts to safe direct Qdrant retrieval fallback.
        """
        return self.set_redis_value(self.KEY_MEMORY_HYBRID_ENABLED, enabled)

    @classmethod
    def from_env(cls) -> FeatureFlags:
        """Load feature flags from environment variables.

        Environment variables:
            FEATURE_RETRAINING_ECE_TRIGGER: Enable ECE triggers (default: true)
            FEATURE_RETRAINING_PERF_TRIGGER: Enable performance triggers (default: true)
            FEATURE_RETRAINING_SCHEDULED_TRIGGER: Enable scheduled triggers (default: true)
            FEATURE_RETRAINING_DEDUPLICATION: Enable deduplication (default: true)
            FEATURE_RETRAINING_PRE_VALIDATION: Enable pre-validation (default: true)
            FEATURE_RETRAINING_DISCORD_ALERTS: Enable Discord alerts (default: true)
            LAUNCH_TRAINING_PIPELINE_ENABLED: Enable training pipeline (default: true)
            FEATURE_PERSONA_REGRESSION_ENABLED: Enable persona regression (default: true)

        Returns:
            FeatureFlags instance with values from environment
        """

        def _get_bool_env(name: str, default: bool = True) -> bool:
            """Get boolean from environment variable with fail-safe defaults.

            SAFETY NOTE: All safety-critical flags default to True (enabled).
            To disable a flag, explicitly set it to 'false', '0', 'no', or 'off'.
            Invalid/malformed values will use the safe default (True).

            Args:
                name: Environment variable name
                default: Default value if env var not set (always True for safety flags)

            Returns:
                Boolean value from environment or safe default
            """
            value = os.getenv(name)
            if value is None:
                # Env var not set - use safe default (True for safety flags)
                return default

            value_lower = value.lower().strip()
            if value_lower in ("true", "1", "yes", "on"):
                return True
            if value_lower in ("false", "0", "no", "off"):
                return False
            # Any other value (including empty string, whitespace, invalid)
            # uses the safe default for safety-critical flags
            return default

        return cls(
            retraining_ece_trigger=_get_bool_env(
                "FEATURE_RETRAINING_ECE_TRIGGER", True
            ),
            retraining_performance_trigger=_get_bool_env(
                "FEATURE_RETRAINING_PERF_TRIGGER", True
            ),
            retraining_scheduled_trigger=_get_bool_env(
                "FEATURE_RETRAINING_SCHEDULED_TRIGGER", True
            ),
            retraining_deduplication=_get_bool_env(
                "FEATURE_RETRAINING_DEDUPLICATION", True
            ),
            retraining_pre_validation=_get_bool_env(
                "FEATURE_RETRAINING_PRE_VALIDATION", True
            ),
            retraining_discord_alerts=_get_bool_env(
                "FEATURE_RETRAINING_DISCORD_ALERTS", True
            ),
            launch_training_pipeline_enabled=_get_bool_env(
                "LAUNCH_TRAINING_PIPELINE_ENABLED", True
            ),
            persona_regression_enabled=_get_bool_env(
                "FEATURE_PERSONA_REGRESSION_ENABLED", True
            ),
            force_simulator_mode=_get_bool_env("FORCE_SIMULATOR_MODE", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with runtime values (consults Redis).

        Returns:
            Dictionary with current flag values (Redis-aware)
        """
        return {
            "retraining_ece_trigger": self.is_retraining_ece_trigger_enabled(),
            "retraining_performance_trigger": self.is_retraining_performance_trigger_enabled(),
            "retraining_scheduled_trigger": self.is_retraining_scheduled_trigger_enabled(),
            "retraining_deduplication": self.is_retraining_deduplication_enabled(),
            "retraining_pre_validation": self.is_retraining_pre_validation_enabled(),
            "retraining_discord_alerts": self.is_retraining_discord_alerts_enabled(),
            "launch_training_pipeline_enabled": self.is_launch_training_pipeline_enabled(),
            "persona_regression_enabled": self.is_persona_regression_enabled(),
            # ST-FILL-001: Fill polling
            "bybit_fill_polling_enabled": self.is_bybit_fill_polling_enabled(),
            "bybit_fill_poll_timeout_ms": self.get_bybit_fill_poll_timeout_ms(),
            # ST-FILL-003: BybitFillListener integration
            "bybit_fill_listener_enabled": self.is_bybit_fill_listener_enabled(),
            # ST-FILL-004: Reconciliation monitor
            "reconciliation_monitor_enabled": self.is_reconciliation_monitor_enabled(),
            "reconciliation_check_interval_seconds": self.get_reconciliation_check_interval_seconds(),
            "reconciliation_alert_threshold_hours": self.get_reconciliation_alert_threshold_hours(),
            # ST-FILL-007: Rollback safety
            "fill_rollback_on_error_enabled": self.is_fill_rollback_on_error_enabled(),
            "reconciliation_auto_backfill": self.is_reconciliation_auto_backfill_enabled(),
            # PAPER-RECON-001: Force simulator mode
            "force_simulator_mode": self.is_force_simulator_mode_enabled(),
            # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory
            "memory_hybrid_enabled": self.is_memory_hybrid_enabled(),
        }

    def to_defaults_dict(self) -> dict[str, Any]:
        """Convert to dictionary with default values (not runtime, ignores Redis).

        Returns:
            Dictionary with default flag values (ignores Redis overrides)
        """
        return {
            "retraining_ece_trigger": self.retraining_ece_trigger,
            "retraining_performance_trigger": self.retraining_performance_trigger,
            "retraining_scheduled_trigger": self.retraining_scheduled_trigger,
            "retraining_deduplication": self.retraining_deduplication,
            "retraining_pre_validation": self.retraining_pre_validation,
            "retraining_discord_alerts": self.retraining_discord_alerts,
            "launch_training_pipeline_enabled": self.launch_training_pipeline_enabled,
            "persona_regression_enabled": self.persona_regression_enabled,
            # ST-FILL-001: Fill polling
            "bybit_fill_polling_enabled": self.bybit_fill_polling_enabled,
            "bybit_fill_poll_timeout_ms": self.bybit_fill_poll_timeout_ms,
            # ST-FILL-003: BybitFillListener integration
            "bybit_fill_listener_enabled": self.bybit_fill_listener_enabled,
            # ST-FILL-004: Reconciliation monitor
            "reconciliation_monitor_enabled": self.reconciliation_monitor_enabled,
            "reconciliation_check_interval_seconds": self.reconciliation_check_interval_seconds,
            "reconciliation_alert_threshold_hours": self.reconciliation_alert_threshold_hours,
            # ST-FILL-007: Rollback safety
            "fill_rollback_on_error_enabled": self.fill_rollback_on_error_enabled,
            "reconciliation_auto_backfill": self.reconciliation_auto_backfill,
            # PAPER-RECON-001: Force simulator mode
            "force_simulator_mode": self.force_simulator_mode,
            # ST-MEMORY-CTX-002: Phase 4 Hybrid Memory
            "memory_hybrid_enabled": self.memory_hybrid_enabled,
        }


# Global instance for convenience
_feature_flags: FeatureFlags | None = None


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance.

    Lazily initializes from environment on first call.

    Returns:
        FeatureFlags instance
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags.from_env()
    return _feature_flags


def set_feature_flags(flags: FeatureFlags) -> None:
    """Set the global feature flags instance (mainly for testing).

    Args:
        flags: FeatureFlags instance to set
    """
    global _feature_flags
    _feature_flags = flags


def reset_feature_flags() -> None:
    """Reset global feature flags to None (mainly for testing)."""
    global _feature_flags
    _feature_flags = None


# ST-FILL-007: Rollback safety
async def rollback_fill_on_error(order_id: str, reason: str) -> None:
    """Rollback fill state on unrecoverable error.

    Only used when FILL_ROLLBACK_ON_ERROR_ENABLED is True.

    Args:
        order_id: The order ID to rollback
        reason: The reason for the rollback
    """
    flags = get_feature_flags()
    if not flags.is_fill_rollback_on_error_enabled():
        return

    logger.warning(f"Rolling back fill for order_id={order_id}: {reason}")

    try:
        # Get Redis client
        client = flags.redis_client
        if client is None:
            logger.error("Redis not available, cannot rollback fill")
            return

        # Mark as rollback in Redis with 24h TTL
        redis_key = f"bybit:fill:rollback:{order_id}"
        rollback_data = json.dumps(
            {
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        client.setex(redis_key, 86400, rollback_data)
        logger.info(f"Fill rollback marked in Redis: {order_id}")

        # Publish incident
        try:
            from execution.incident_reporter import publish_execution_incident

            await publish_execution_incident(
                incident_type="fill_rollback_on_error",
                severity="P1",
                title=f"Fill rollback: {order_id}",
                message=reason,
                context={
                    "order_id": order_id,
                    "reason": reason,
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish fill rollback incident: {e}")

    except Exception as e:
        logger.error(f"Failed to rollback fill for order_id={order_id}: {e}")
