"""Configuration module for ChiseAI.

Provides centralized configuration loading and environment variable management.
"""

from src.config.bootstrap import get_bootstrap_state
from src.config.env_loader import (
    EnvLoader,
    bootstrap_environment,
    discord_loader,
    kimi_loader,
    load_discord_config,
    load_discord_config_with_ids,
    load_kimi_config,
)
from src.config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    set_feature_flags,
)
from src.config.ict_feature_flags import (
    ICTFeatureFlags,
    get_ict_feature_flags,
    reset_ict_feature_flags,
    set_ict_feature_flags,
)
from src.config.trading_mode import (
    ModuleStatus,
    ModuleType,
    TradingMode,
    TradingModeConfig,
)

__all__ = [
    "bootstrap_environment",
    "get_bootstrap_state",
    "EnvLoader",
    "discord_loader",
    "kimi_loader",
    "load_discord_config",
    "load_discord_config_with_ids",
    "load_kimi_config",
    "FeatureFlags",
    "get_feature_flags",
    "reset_feature_flags",
    "set_feature_flags",
    "ICTFeatureFlags",
    "get_ict_feature_flags",
    "reset_ict_feature_flags",
    "set_ict_feature_flags",
    "ModuleStatus",
    "ModuleType",
    "TradingMode",
    "TradingModeConfig",
]
