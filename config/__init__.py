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
from src.config.bootstrap import bootstrap, get_bootstrap_state  # noqa: E402
from src.config.env_loader import (  # noqa: E402
    EnvLoader,
    kimi_loader,
    load_discord_config,
    load_kimi_config,
)
from src.config.feature_flags import (  # noqa: E402
    FeatureFlags,
    reset_feature_flags,
    set_feature_flags,
)
from src.config.trading_mode import (  # noqa: E402
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
