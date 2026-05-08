"""ICT Feature flags configuration.

ICT (Inner Circle Trader) signals feature flags with Redis-backed runtime configuration.
Supports CVD, FVG, Order Block, and BOS/CHoCH signal toggling.

BOS/CHoCH re-enabled (accuracy fix applied) - defaults to True.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# Redis key prefixes for ICT feature flags
REDIS_PREFIX = "ict:feature_flags"


@dataclass(frozen=True)
class ICTFeatureFlags:
    """Feature flags for ICT signals.

    SAFETY-FIRST DESIGN:
    - CVD, FVG, Order Block: Default to ENABLED (True) - validated signals
    - BOS/CHoCH: Default to ENABLED (True) - re-enabled after accuracy fix

    All flags support Redis-backed runtime toggling with environment variable overrides.

    Attributes:
        ict_cvd_enabled: Enable ICT CVD (Change of Character) signals [default: True]
        ict_fvg_enabled: Enable ICT FVG (Fair Value Gap) signals [default: True]
        ict_order_block_enabled: Enable ICT Order Block signals [default: True]
        ict_bos_choch_enabled: Enable ICT BOS/CHoCH signals [default: True - re-enabled]
        ict_integration_enabled: Master flag for all ICT integration [default: True]
    """

    # Redis key constants
    KEY_CVD: ClassVar[str] = f"{REDIS_PREFIX}:cvd"
    KEY_FVG: ClassVar[str] = f"{REDIS_PREFIX}:fvg"
    KEY_ORDER_BLOCK: ClassVar[str] = f"{REDIS_PREFIX}:order_block"
    KEY_BOS_CHOCH: ClassVar[str] = f"{REDIS_PREFIX}:bos_choch"
    KEY_INTEGRATION: ClassVar[str] = f"{REDIS_PREFIX}:integration"

    # TTL for Redis flag storage (seconds)
    FLAG_TTL: ClassVar[int] = 3600

    # Default values - ENABLED signals (validated)
    ict_cvd_enabled: bool = True
    ict_fvg_enabled: bool = True
    ict_order_block_enabled: bool = True

    # Default value - ENABLED signal (re-enabled after accuracy fix)
    ict_bos_choch_enabled: bool = True

    # Master integration flag
    ict_integration_enabled: bool = True

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
            redis_db = int(os.getenv("REDIS_DB", "1"))
            return redis.Redis(
                host=redis_host, port=redis_port, db=redis_db, decode_responses=True
            )
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            return None

    @classmethod
    def from_env(cls) -> ICTFeatureFlags:
        """Load feature flags from environment variables with Redis overrides.

        Priority: Redis > Environment Variable > Default

        Environment variables:
            ICT_CVD_ENABLED: Enable CVD signals (default: true)
            ICT_FVG_ENABLED: Enable FVG signals (default: true)
            ICT_ORDER_BLOCK_ENABLED: Enable Order Block signals (default: true)
            ICT_BOS_CHOCH_ENABLED: Enable BOS/CHoCH signals (default: false)
            ICT_INTEGRATION_ENABLED: Master ICT integration (default: true)

        Returns:
            ICTFeatureFlags instance with values from Redis/env
        """

        def _get_bool_env(name: str, default: bool = True) -> bool:
            """Get boolean from environment variable with fail-safe defaults."""
            value = os.getenv(name)
            if value is None:
                return default
            value_lower = value.lower().strip()
            return value_lower not in ("false", "0", "no", "off")

        return cls(
            ict_cvd_enabled=_get_bool_env("ICT_CVD_ENABLED", True),
            ict_fvg_enabled=_get_bool_env("ICT_FVG_ENABLED", True),
            ict_order_block_enabled=_get_bool_env("ICT_ORDER_BLOCK_ENABLED", True),
            ict_bos_choch_enabled=_get_bool_env(
                "ICT_BOS_CHOCH_ENABLED", True
            ),  # Re-enabled after accuracy fix
            ict_integration_enabled=_get_bool_env("ICT_INTEGRATION_ENABLED", True),
        )

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
                logger.info(f"ICT Feature Flag changed: {key} = {str_value}")
            return True
        except Exception as e:
            logger.error(f"Redis error setting {key}: {e}")
            return False

    def is_cvd_enabled(self) -> bool:
        """Check if CVD signals are enabled (Redis or default)."""
        return self.get_redis_value(self.KEY_CVD, self.ict_cvd_enabled)

    def is_fvg_enabled(self) -> bool:
        """Check if FVG signals are enabled (Redis or default)."""
        return self.get_redis_value(self.KEY_FVG, self.ict_fvg_enabled)

    def is_order_block_enabled(self) -> bool:
        """Check if Order Block signals are enabled (Redis or default)."""
        return self.get_redis_value(self.KEY_ORDER_BLOCK, self.ict_order_block_enabled)

    def is_bos_choch_enabled(self) -> bool:
        """Check if BOS/CHoCH signals are enabled (Redis or default).

        BOS/CHoCH is now enabled by default (accuracy fix applied).
        """
        return self.get_redis_value(self.KEY_BOS_CHOCH, self.ict_bos_choch_enabled)

    def is_integration_enabled(self) -> bool:
        """Check if ICT integration is enabled (Redis or default)."""
        return self.get_redis_value(self.KEY_INTEGRATION, self.ict_integration_enabled)

    def set_cvd_enabled(self, enabled: bool) -> bool:
        """Enable or disable CVD signals."""
        return self.set_redis_value(self.KEY_CVD, enabled)

    def set_fvg_enabled(self, enabled: bool) -> bool:
        """Enable or disable FVG signals."""
        return self.set_redis_value(self.KEY_FVG, enabled)

    def set_order_block_enabled(self, enabled: bool) -> bool:
        """Enable or disable Order Block signals."""
        return self.set_redis_value(self.KEY_ORDER_BLOCK, enabled)

    def set_bos_choch_enabled(self, enabled: bool) -> bool:
        """Enable or disable BOS/CHoCH signals.

        BOS/CHoCH is now enabled by default after accuracy fix.
        """
        if not enabled:
            logger.warning("Disabling BOS/CHoCH signals via explicit override")
        return self.set_redis_value(self.KEY_BOS_CHOCH, enabled)

    def set_integration_enabled(self, enabled: bool) -> bool:
        """Enable or disable ICT integration master switch."""
        return self.set_redis_value(self.KEY_INTEGRATION, enabled)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with runtime values."""
        return {
            "ict_cvd_enabled": self.is_cvd_enabled(),
            "ict_fvg_enabled": self.is_fvg_enabled(),
            "ict_order_block_enabled": self.is_order_block_enabled(),
            "ict_bos_choch_enabled": self.is_bos_choch_enabled(),
            "ict_integration_enabled": self.is_integration_enabled(),
        }

    def to_defaults_dict(self) -> dict[str, Any]:
        """Convert to dictionary with default values (not runtime)."""
        return {
            "ict_cvd_enabled": self.ict_cvd_enabled,
            "ict_fvg_enabled": self.ict_fvg_enabled,
            "ict_order_block_enabled": self.ict_order_block_enabled,
            "ict_bos_choch_enabled": self.ict_bos_choch_enabled,
            "ict_integration_enabled": self.ict_integration_enabled,
        }


# Global instance for convenience
_ict_feature_flags: ICTFeatureFlags | None = None


def get_ict_feature_flags() -> ICTFeatureFlags:
    """Get the global ICT feature flags instance.

    Lazily initializes from environment on first call.

    Returns:
        ICTFeatureFlags instance
    """
    global _ict_feature_flags
    if _ict_feature_flags is None:
        _ict_feature_flags = ICTFeatureFlags.from_env()
    return _ict_feature_flags


def set_ict_feature_flags(flags: ICTFeatureFlags) -> None:
    """Set the global ICT feature flags instance (mainly for testing).

    Args:
        flags: ICTFeatureFlags instance to set
    """
    global _ict_feature_flags
    _ict_feature_flags = flags


def reset_ict_feature_flags() -> None:
    """Reset global ICT feature flags to None (mainly for testing)."""
    global _ict_feature_flags
    _ict_feature_flags = None
