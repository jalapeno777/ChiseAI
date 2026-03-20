"""Test fixtures for ChiseAI indicator tests.

Provides synthetic OHLCV data generators, real market data snapshots,
and validated indicator expectations for deterministic test data.
"""

from tests.fixtures.ohlcv_generators import (
    MarketRegime,
    generate_ohlcv_from_candles,
    generate_ranging_ohlcv,
    generate_trending_ohlcv,
    generate_volatile_ohlcv,
)

__all__ = [
    "MarketRegime",
    "generate_trending_ohlcv",
    "generate_ranging_ohlcv",
    "generate_volatile_ohlcv",
    "generate_ohlcv_from_candles",
]
