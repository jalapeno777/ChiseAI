"""Feature flags configuration for ChiseAI.

Centralized feature flags for enabling/disabling system components.
All flags support environment variable overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureFlags:
    """Feature flags for ChiseAI components.

    Attributes:
        retraining_ece_trigger: Enable ECE-based retraining triggers
        retraining_performance_trigger: Enable performance-based retraining triggers
        retraining_scheduled_trigger: Enable scheduled retraining triggers
        retraining_deduplication: Enable 24h deduplication window
        retraining_pre_validation: Enable pre-training quality validation
        retraining_discord_alerts: Enable Discord alerts on triggers
    """

    # Retraining trigger flags
    retraining_ece_trigger: bool = True
    retraining_performance_trigger: bool = True
    retraining_scheduled_trigger: bool = True
    retraining_deduplication: bool = True
    retraining_pre_validation: bool = True
    retraining_discord_alerts: bool = True

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

        Returns:
            FeatureFlags instance with values from environment
        """

        def _get_bool_env(name: str, default: bool = True) -> bool:
            """Get boolean from environment variable."""
            value = os.getenv(name, str(default).lower())
            return value.lower() in ("true", "1", "yes", "on")

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
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "retraining_ece_trigger": self.retraining_ece_trigger,
            "retraining_performance_trigger": self.retraining_performance_trigger,
            "retraining_scheduled_trigger": self.retraining_scheduled_trigger,
            "retraining_deduplication": self.retraining_deduplication,
            "retraining_pre_validation": self.retraining_pre_validation,
            "retraining_discord_alerts": self.retraining_discord_alerts,
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
