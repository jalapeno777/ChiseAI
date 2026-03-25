"""Synthetic OHLCV data generators for test fixtures.

Provides configurable generators for three market regimes:
- Trending: Steady directional price movement with consistent momentum
- Ranging: Sideways price action within a bounded range
- Volatile: High-amplitude price swings with irregular patterns

All generators produce data compatible with the OHLCVData dataclass
from src/data_ingestion/ohlcv_fetcher.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from data_ingestion.ohlcv_fetcher import OHLCVData


class MarketRegime(str, Enum):
    """Market regime types for synthetic data generation.

    This enum covers the four unified regime types plus direction variants.
    The unified regimes are: TRENDING, RANGING, VOLATILE, UNKNOWN.
    Direction is determined by price action context.
    """

    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"

    # Legacy aliases for backward compatibility
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"

    @classmethod
    def from_unified(cls, regime: str) -> "MarketRegime":
        """Create from unified regime string.

        Args:
            regime: Unified regime string ('trending', 'ranging', 'volatile', 'unknown')

        Returns:
            Corresponding MarketRegime value
        """
        mapping = {
            "trending": cls.TRENDING,
            "ranging": cls.RANGING,
            "volatile": cls.VOLATILE,
            "unknown": cls.UNKNOWN,
        }
        return mapping.get(regime.lower(), cls.UNKNOWN)

    @property
    def is_trending(self) -> bool:
        """Check if this regime represents trending market."""
        return self in (
            MarketRegime.TRENDING,
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
        )

    @property
    def is_ranging(self) -> bool:
        """Check if this regime represents ranging market."""
        return self == MarketRegime.RANGING

    @property
    def is_volatile(self) -> bool:
        """Check if this regime represents volatile market."""
        return self == MarketRegime.VOLATILE


@dataclass
class GeneratorConfig:
    """Configuration for synthetic OHLCV data generation.

    Attributes:
        length: Number of candles to generate
        base_price: Starting price level
        volatility: Base volatility as a fraction of price (e.g., 0.01 = 1%)
        trend_strength: Price drift per candle as fraction of price
        seed: Random seed for reproducibility (None for non-deterministic)
    """

    length: int = 100
    base_price: float = 50000.0
    volatility: float = 0.01
    trend_strength: float = 0.0
    seed: int | None = 42


def generate_trending_ohlcv(
    length: int = 100,
    base_price: float = 50000.0,
    volatility: float = 0.01,
    trend_strength: float = 0.002,
    direction: str = "up",
    seed: int = 42,
    start_timestamp: int = 1700000000000,
    interval_ms: int = 60000,
) -> list[OHLCVData]:
    """Generate trending OHLCV data.

    Produces a series of candles with consistent directional drift
    and realistic OHLC relationships.

    Args:
        length: Number of candles to generate (default: 100)
        base_price: Starting price (default: 50000.0)
        volatility: Per-candle volatility as fraction of price (default: 0.01)
        trend_strength: Per-candle drift as fraction of price (default: 0.002)
        direction: "up" or "down" (default: "up")
        seed: Random seed for reproducibility (default: 42)
        start_timestamp: Starting timestamp in ms (default: 1700000000000)
        interval_ms: Candle interval in ms (default: 60000 for 1m)

    Returns:
        List of OHLCVData objects forming a trend
    """
    rng = np.random.default_rng(seed)

    if direction == "down":
        trend_strength = -abs(trend_strength)
    else:
        trend_strength = abs(trend_strength)

    closes: list[float] = []
    price = base_price

    for _ in range(length):
        noise = rng.normal(0, volatility) * price
        drift = trend_strength * price
        price = max(price * 0.5, price + drift + noise)  # Floor at 50% of start
        closes.append(round(price, 2))

    return _build_ohlcv_from_closes(
        closes,
        rng,
        base_volume=100.0,
        volatility_factor=0.3,
        start_timestamp=start_timestamp,
        interval_ms=interval_ms,
    )


def generate_ranging_ohlcv(
    length: int = 100,
    base_price: float = 50000.0,
    volatility: float = 0.005,
    range_width: float | None = None,
    seed: int = 42,
    start_timestamp: int = 1700000000000,
    interval_ms: int = 60000,
) -> list[OHLCVData]:
    """Generate ranging (sideways) OHLCV data.

    Produces candles that oscillate within a bounded price range
    with mean-reverting behavior.

    Args:
        length: Number of candles to generate (default: 100)
        base_price: Center price for the range (default: 50000.0)
        volatility: Per-candle volatility as fraction of price (default: 0.005)
        range_width: Half-width of range as fraction of price (default: 0.03)
        seed: Random seed for reproducibility (default: 42)
        start_timestamp: Starting timestamp in ms (default: 1700000000000)
        interval_ms: Candle interval in ms (default: 60000 for 1m)

    Returns:
        List of OHLCVData objects forming a range
    """
    rng = np.random.default_rng(seed)

    if range_width is None:
        range_width = 0.03

    upper = base_price * (1 + range_width)
    lower = base_price * (1 - range_width)
    mid = base_price

    closes: list[float] = []
    price = base_price

    for _ in range(length):
        # Mean-reverting: pull toward center
        reversion_strength = 0.05
        pull = (mid - price) * reversion_strength
        noise = rng.normal(0, volatility) * price
        price = price + pull + noise

        # Soft boundary enforcement
        if price > upper:
            price = upper - abs(rng.normal(0, volatility * 0.5) * price)
        elif price < lower:
            price = lower + abs(rng.normal(0, volatility * 0.5) * price)

        price = max(lower * 0.9, min(upper * 1.1, price))
        closes.append(round(price, 2))

    return _build_ohlcv_from_closes(
        closes,
        rng,
        base_volume=80.0,
        volatility_factor=0.2,
        start_timestamp=start_timestamp,
        interval_ms=interval_ms,
    )


def generate_volatile_ohlcv(
    length: int = 100,
    base_price: float = 50000.0,
    volatility: float = 0.025,
    seed: int = 42,
    start_timestamp: int = 1700000000000,
    interval_ms: int = 60000,
) -> list[OHLCVData]:
    """Generate volatile OHLCV data.

    Produces candles with large price swings, occasional gaps,
    and irregular volume spikes.

    Args:
        length: Number of candles to generate (default: 100)
        base_price: Starting price (default: 50000.0)
        volatility: Base per-candle volatility as fraction (default: 0.025)
        seed: Random seed for reproducibility (default: 42)
        start_timestamp: Starting timestamp in ms (default: 1700000000000)
        interval_ms: Candle interval in ms (default: 60000 for 1m)

    Returns:
        List of OHLCVData objects with high volatility
    """
    rng = np.random.default_rng(seed)

    closes: list[float] = []
    price = base_price

    for i in range(length):
        # Cluster volatility: occasional calm, occasional storm
        if rng.random() < 0.15:  # 15% chance of spike
            vol_mult = rng.uniform(2.0, 5.0)
        elif rng.random() < 0.2:  # 20% chance of calm
            vol_mult = rng.uniform(0.2, 0.5)
        else:
            vol_mult = 1.0

        noise = rng.normal(0, volatility * vol_mult) * price
        price = max(price * 0.3, price + noise)
        closes.append(round(price, 2))

    return _build_ohlcv_from_closes(
        closes,
        rng,
        base_volume=150.0,
        volatility_factor=0.8,
        start_timestamp=start_timestamp,
        interval_ms=interval_ms,
    )


def generate_ohlcv_from_candles(
    candle_data: list[list[float]],
    start_timestamp: int = 1700000000000,
    interval_ms: int = 60000,
) -> list[OHLCVData]:
    """Convert raw candle arrays to OHLCVData objects.

    Each inner list should have 5 elements: [open, high, low, close, volume].

    Args:
        candle_data: List of [open, high, low, close, volume] arrays
        start_timestamp: Starting timestamp in ms
        interval_ms: Candle interval in ms

    Returns:
        List of OHLCVData objects

    Raises:
        ValueError: If any candle has fewer than 5 elements
    """
    result: list[OHLCVData] = []
    for i, candle in enumerate(candle_data):
        if len(candle) < 5:
            raise ValueError(
                f"Candle at index {i} has {len(candle)} elements, expected 5"
            )
        result.append(
            OHLCVData(
                timestamp=start_timestamp + i * interval_ms,
                open_price=float(candle[0]),
                high_price=float(candle[1]),
                low_price=float(candle[2]),
                close_price=float(candle[3]),
                volume=float(candle[4]),
            )
        )
    return result


def _build_ohlcv_from_closes(
    closes: list[float],
    rng: np.random.Generator,
    base_volume: float = 100.0,
    volatility_factor: float = 0.3,
    start_timestamp: int = 1700000000000,
    interval_ms: int = 60000,
) -> list[OHLCVData]:
    """Build OHLCVData objects from a close price series.

    Generates realistic open/high/low values around each close and
    adds proportional volume.

    Args:
        closes: Series of close prices
        rng: NumPy random generator for reproducibility
        base_volume: Base trading volume
        volatility_factor: Controls wick size relative to body
        start_timestamp: Starting timestamp in ms
        interval_ms: Candle interval in ms

    Returns:
        List of OHLCVData objects
    """
    result: list[OHLCVData] = []

    for i, close in enumerate(closes):
        timestamp = start_timestamp + i * interval_ms

        # Open: previous close with small gap, or base_price for first candle
        if i == 0:
            open_price = close * (1 + rng.normal(0, 0.001))
        else:
            gap = (close - closes[i - 1]) * rng.uniform(0.1, 0.5)
            open_price = closes[i - 1] + gap

        # Body
        body_high = max(open_price, close)
        body_low = min(open_price, close)

        # Wicks: extend beyond body by volatility_factor
        wick_range = abs(close - open_price) * volatility_factor
        wick_range = max(wick_range, close * 0.0005)  # Minimum wick

        high_price = body_high + abs(rng.normal(0, wick_range))
        low_price = body_low - abs(rng.normal(0, wick_range))

        # Ensure high >= max(open, close) and low <= min(open, close)
        high_price = max(high_price, open_price, close)
        low_price = min(low_price, open_price, close)

        # Volume: correlate with price movement magnitude
        price_change = abs(close - (closes[i - 1] if i > 0 else close))
        volume_mult = 1.0 + (price_change / close) * 10  # Amplify correlation
        volume = base_volume * volume_mult * rng.uniform(0.5, 1.5)

        result.append(
            OHLCVData(
                timestamp=timestamp,
                open_price=round(open_price, 2),
                high_price=round(high_price, 2),
                low_price=round(low_price, 2),
                close_price=round(close, 2),
                volume=round(volume, 4),
            )
        )

    return result
