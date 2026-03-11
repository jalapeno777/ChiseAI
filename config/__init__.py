"""Configuration package for ChiseAI.

This package provides configuration management for the trading system.
This is a compatibility shim that re-exports from src.config.
"""

import sys
from pathlib import Path

# Add src to path to ensure we can import from src.config
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

# Re-export all config modules from src.config
from config.bootstrap import bootstrap
from config.bootstrap import get_bootstrap_state
from config.env_loader import (
    EnvLoader,
    kimi_loader,
    load_discord_config,
    load_kimi_config,
)
from config.feature_flags import (
    FeatureFlags,
    reset_feature_flags,
    set_feature_flags,
)
from config.trading_mode import (
    ModuleStatus,
    ModuleType,
    TradingMode,
    TradingModeConfig,
)

__all__ = [
    "bootstrap",
    "get_bootstrap_state",
    "EnvLoader",
    "kimi_loader",
    "load_discord_config",
    "load_kimi_config",
    "FeatureFlags",
    "reset_feature_flags",
    "set_feature_flags",
    "ModuleStatus",
    "ModuleType",
    "TradingMode",
    "TradingModeConfig",
]
