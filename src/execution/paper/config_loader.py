"""Configuration loader for market realism models.

Loads and manages configuration from YAML files with support for
per-symbol and per-exchange overrides.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from execution.paper.latency_model import LatencyConfig
from execution.paper.market_impact import MarketImpactConfig
from execution.paper.slippage_model import SlippageConfig
from execution.paper.fill_probability import FillProbabilityConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "market_realism.yaml"
)


class MarketRealismConfig:
    """Configuration manager for market realism models.

    Loads configuration from YAML and provides per-symbol/exchange
    configuration lookup with fallback to defaults.
    """

    def __init__(self, config_path: str | Path | None = None):
        """Initialize configuration loader.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            import yaml

            if not self.config_path.exists():
                logger.warning(
                    f"Config file not found: {self.config_path}, using defaults"
                )
                self._config = self._get_default_config()
                return

            with open(self.config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}

            logger.info(f"Loaded market realism config from {self.config_path}")

        except ImportError:
            logger.warning("PyYAML not installed, using default configuration")
            self._config = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            self._config = self._get_default_config()

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration when file is unavailable."""
        return {
            "defaults": {
                "slippage": {
                    "base_slippage_bps": 2.0,
                    "volatility_factor": 1.0,
                    "min_slippage_bps": 0.5,
                    "max_slippage_bps": 100.0,
                    "order_size_factor": 1.0,
                    "adv_threshold": 0.001,
                },
                "latency": {
                    "submission_mean_ms": 50.0,
                    "submission_std_ms": 15.0,
                    "fill_mean_ms": 100.0,
                    "fill_std_ms": 30.0,
                    "min_latency_ms": 5.0,
                    "network_jitter_ms": 5.0,
                },
                "market_impact": {
                    "base_coefficient": 1.0,
                    "volatility_sensitivity": 0.5,
                    "min_impact_bps": 1.0,
                    "max_impact_bps": 500.0,
                    "adv_threshold": 0.001,
                    "temporary_impact_fraction": 0.7,
                },
                "fill_probability": {
                    "market_order_fill_prob": 1.0,
                    "base_limit_fill_prob": 0.8,
                    "price_distance_factor": 2.0,
                    "depth_factor": 1.0,
                    "large_order_threshold": 0.01,
                    "large_order_penalty": 0.3,
                    "time_decay_factor": 0.95,
                },
            },
            "symbols": {},
            "exchanges": {},
            "volatility_regimes": {},
        }

    def _merge_configs(self, base: dict, override: dict) -> dict:
        """Merge override config into base config."""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get_slippage_config(self, symbol: str | None = None) -> SlippageConfig:
        """Get slippage configuration for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            SlippageConfig instance
        """
        defaults = self._config.get("defaults", {}).get("slippage", {})

        # Check for symbol-specific config
        symbol_config = {}
        symbols = self._config.get("symbols", {})

        if symbol and symbol in symbols:
            symbol_config = symbols[symbol].get("slippage", {})

        merged = self._merge_configs(defaults, symbol_config)
        return SlippageConfig(**merged)

    def get_latency_config(self, exchange: str | None = None) -> LatencyConfig:
        """Get latency configuration for an exchange.

        Args:
            exchange: Exchange name (e.g., "bybit", "binance")

        Returns:
            LatencyConfig instance
        """
        defaults = self._config.get("defaults", {}).get("latency", {})

        # Check for exchange-specific config
        exchange_config = {}
        exchanges = self._config.get("exchanges", {})

        if exchange and exchange.lower() in exchanges:
            exchange_config = exchanges[exchange.lower()].get("latency", {})
        elif "default" in exchanges:
            exchange_config = exchanges["default"].get("latency", {})

        merged = self._merge_configs(defaults, exchange_config)
        return LatencyConfig(**merged)

    def get_market_impact_config(self, symbol: str | None = None) -> MarketImpactConfig:
        """Get market impact configuration for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            MarketImpactConfig instance
        """
        defaults = self._config.get("defaults", {}).get("market_impact", {})

        # Check for symbol-specific config
        symbol_config = {}
        symbols = self._config.get("symbols", {})

        if symbol and symbol in symbols:
            symbol_config = symbols[symbol].get("market_impact", {})

        merged = self._merge_configs(defaults, symbol_config)
        return MarketImpactConfig(**merged)

    def get_fill_probability_config(self) -> FillProbabilityConfig:
        """Get fill probability configuration.

        Returns:
            FillProbabilityConfig instance
        """
        defaults = self._config.get("defaults", {}).get("fill_probability", {})
        return FillProbabilityConfig(**defaults)

    def get_volatility_regime_config(self, volatility: float) -> dict[str, Any]:
        """Get configuration adjustments for a volatility regime.

        Args:
            volatility: Current volatility as decimal

        Returns:
            Dictionary with regime-specific adjustments
        """
        regimes = self._config.get("volatility_regimes", {})

        if volatility < 0.01:
            return regimes.get("low", {})
        elif volatility < 0.05:
            return regimes.get("normal", {})
        elif volatility < 0.10:
            return regimes.get("high", {})
        else:
            return regimes.get("extreme", {})

    def get_all_symbol_configs(self) -> dict[str, dict[str, Any]]:
        """Get all symbol-specific configurations.

        Returns:
            Dictionary mapping symbols to their configs
        """
        return self._config.get("symbols", {})

    def get_all_exchange_configs(self) -> dict[str, dict[str, Any]]:
        """Get all exchange-specific configurations.

        Returns:
            Dictionary mapping exchanges to their configs
        """
        return self._config.get("exchanges", {})

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()
        logger.info("Configuration reloaded")


def load_market_realism_config(
    config_path: str | Path | None = None,
) -> MarketRealismConfig:
    """Load market realism configuration.

    Convenience function to create a MarketRealismConfig instance.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        MarketRealismConfig instance
    """
    return MarketRealismConfig(config_path)
