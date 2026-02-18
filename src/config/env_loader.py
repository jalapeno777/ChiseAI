"""Centralized environment variable loader.

Provides consistent environment variable loading with validation
and default value support across the codebase.

For CH-KIMI-DISCORD-001: Fix KIMI env loading
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class EnvLoader:
    """Centralized environment variable loader.

    Provides consistent loading of environment variables with
    type conversion, validation, and default values.

    Attributes:
        prefix: Optional prefix for environment variables
        strict: If True, raises error on missing required vars
    """

    def __init__(self, prefix: str | None = None, strict: bool = False) -> None:
        """Initialize env loader.

        Args:
            prefix: Optional prefix for env vars (e.g., "KIMI_")
            strict: If True, missing required vars raise error
        """
        self.prefix = prefix
        self.strict = strict

    def _get_key(self, key: str) -> str:
        """Get full key with prefix.

        Args:
            key: Base environment variable name

        Returns:
            Full key with prefix if set
        """
        if self.prefix:
            return f"{self.prefix}{key}"
        return key

    def get(
        self,
        key: str,
        default: Any = None,
        required: bool = False,
        var_type: type = str,
    ) -> Any:
        """Get environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set
            var_type: Type to convert value to (str, int, float, bool)

        Returns:
            Environment variable value or default

        Raises:
            ValueError: If required variable is not set and strict mode
        """
        full_key = self._get_key(key)
        value = os.getenv(full_key)

        if value is None or value == "":
            if required and self.strict:
                raise ValueError(f"Required environment variable {full_key} not set")
            return default

        # Type conversion
        if var_type is bool:
            return value.lower() in ("true", "1", "yes", "on")
        elif var_type is int:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Could not convert {full_key} to int, using default")
                return default
        elif var_type is float:
            try:
                return float(value)
            except ValueError:
                logger.warning(f"Could not convert {full_key} to float, using default")
                return default

        return value

    def get_str(
        self, key: str, default: str | None = None, required: bool = False
    ) -> str | None:
        """Get string environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            String value or default
        """
        return self.get(key, default, required, str)

    def get_int(
        self, key: str, default: int | None = None, required: bool = False
    ) -> int | None:
        """Get integer environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Integer value or default
        """
        return self.get(key, default, required, int)

    def get_float(
        self, key: str, default: float | None = None, required: bool = False
    ) -> float | None:
        """Get float environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Float value or default
        """
        return self.get(key, default, required, float)

    def get_bool(self, key: str, default: bool = False, required: bool = False) -> bool:
        """Get boolean environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Boolean value or default
        """
        return self.get(key, default, required, bool)


# Global loader instances for common prefixes
kimi_loader = EnvLoader(prefix="KIMI_", strict=False)
discord_loader = EnvLoader(prefix="DISCORD_", strict=False)


def load_kimi_config() -> dict[str, Any]:
    """Load KIMI configuration from environment.

    Returns:
        Dictionary with KIMI config values
    """
    return {
        "api_key": kimi_loader.get_str("API_KEY"),
        "base_url": kimi_loader.get_str("BASE_URL", "https://api.kimi.com/coding/v1"),
        "model": kimi_loader.get_str("MODEL", "k2p5"),
        "timeout": kimi_loader.get_float("TIMEOUT", 30.0),
        "max_retries": kimi_loader.get_int("MAX_RETRIES", 3),
        "retry_delay": kimi_loader.get_float("RETRY_DELAY", 1.0),
    }


def load_discord_config() -> dict[str, Any]:
    """Load Discord configuration from environment.

    Returns:
        Dictionary with Discord config values
    """
    return {
        "bot_token": discord_loader.get_str("BOT_TOKEN"),
        "webhook_url": discord_loader.get_str("WEBHOOK_URL"),
        "default_channel": discord_loader.get_str("DEFAULT_CHANNEL", "trading-signals"),
        "guild_id": discord_loader.get_str("GUILD_ID"),  # Guild restriction
    }
