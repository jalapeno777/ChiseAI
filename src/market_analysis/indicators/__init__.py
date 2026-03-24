"""Technical indicators package for market analysis.

Provides standardized technical indicator calculations including RSI, MACD,
and Bollinger Bands for signal generation across multiple timeframes.
"""

# Base classes (new plugin system)
from market_analysis.indicators.base import (
    BaseIndicator,
    Signal,
    SignalDirection,
)

# Existing indicators (backward compatible)
from market_analysis.indicators.bollinger_bands import (
    BollingerBands,
    BollingerBandsResult,
)
from market_analysis.indicators.calculator import IndicatorCalculator
from market_analysis.indicators.feature_store import FeatureStore
from market_analysis.indicators.macd import MACD, MACDResult
from market_analysis.indicators.registry import PluginRegistry, get_registry
from market_analysis.indicators.rsi import RSI, RSIResult
from market_analysis.indicators.volatility import ATR, ATRResult
from market_analysis.indicators.volume_profile import VolumeProfile, VolumeProfileResult

__all__ = [
    # Plugin system (new)
    "BaseIndicator",
    "FeatureStore",
    "PluginRegistry",
    "VolumeProfile",
    "VolumeProfileResult",
    "get_registry",
    "Signal",
    "SignalDirection",
    # Existing indicators (backward compatible)
    "RSI",
    "RSIResult",
    "MACD",
    "MACDResult",
    "BollingerBands",
    "BollingerBandsResult",
    "ATR",
    "ATRResult",
    "IndicatorCalculator",
]


def _auto_load_plugins() -> None:
    """Auto-load indicator plugins on module import."""
    try:
        registry = get_registry()
        registry.load_entry_points()
        registry.load_module("market_analysis.indicators")
    except Exception:
        pass  # Fail silently if plugin loading fails


# Auto-load plugins
_auto_load_plugins()
