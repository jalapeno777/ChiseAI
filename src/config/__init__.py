"""Configuration module for ChiseAI.

Provides centralized configuration loading and environment variable management.
"""

from src.config.env_loader import (
    EnvLoader,
    bootstrap_environment,
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
    # Provider discovery (ST-ENV-001)
    "discover_kimi_config",
    "discover_zai_config",
    "discover_zhipu_config",
    "discover_minimax_config",
    "get_available_providers",
    "diagnose_provider_availability",
]
