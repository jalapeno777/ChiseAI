"""Feature flags configuration for ChiseAI.

Centralized feature flags for enabling/disabling system components.
All flags support environment variable overrides and Redis-backed runtime toggling.
Flags persist across restarts via Redis storage.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
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
