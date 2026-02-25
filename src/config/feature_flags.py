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

    SAFETY-FIRST DESIGN: All safety-critical flags default to ENABLED (True).
    Missing or invalid configuration values will NOT disable safety features.

    To explicitly disable a flag, set the corresponding environment variable
    to one of: 'false', '0', 'no', 'off' (case-insensitive).

    Attributes:
        retraining_ece_trigger: Enable ECE-based retraining triggers [SAFETY]
        retraining_performance_trigger: Enable performance-based retraining triggers [SAFETY]
        retraining_scheduled_trigger: Enable scheduled retraining triggers [SAFETY]
        retraining_deduplication: Enable 24h deduplication window [SAFETY]
        retraining_pre_validation: Enable pre-training quality validation [SAFETY]
        retraining_discord_alerts: Enable Discord alerts on triggers
        launch_training_pipeline_enabled: Enable training pipeline integration [SAFETY]
    """

    # Retraining trigger flags
    retraining_ece_trigger: bool = True
    retraining_performance_trigger: bool = True
    retraining_scheduled_trigger: bool = True
    retraining_deduplication: bool = True
    retraining_pre_validation: bool = True
    retraining_discord_alerts: bool = True

    # Training pipeline integration (ST-LAUNCH-012)
    launch_training_pipeline_enabled: bool = True

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
        """Convert to dictionary."""
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
