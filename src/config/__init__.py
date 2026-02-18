"""Configuration module for ChiseAI.

Provides centralized configuration loading and environment variable management.
"""

from config.bootstrap import bootstrap as bootstrap_environment
from config.bootstrap import get_bootstrap_state
from config.env_loader import (
    EnvLoader,
    diagnose_provider_availability,
    discover_kimi_config,
    discover_minimax_config,
    discover_zai_config,
    discover_zhipu_config,
    get_available_providers,
    load_discord_config,
    load_kimi_config,
)

__all__ = [
    # Core loader class
    "EnvLoader",
    # Legacy config loaders (backward compatibility)
    "load_kimi_config",
    "load_discord_config",
    # Environment bootstrap (ST-ENV-001)
    "bootstrap_environment",
    "get_bootstrap_state",
    # Provider discovery (ST-ENV-001)
    "discover_kimi_config",
    "discover_zai_config",
    "discover_zhipu_config",
    "discover_minimax_config",
    "get_available_providers",
    "diagnose_provider_availability",
]
