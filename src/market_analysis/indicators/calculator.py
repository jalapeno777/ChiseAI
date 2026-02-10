"""Unified indicator calculator interface.

Provides a unified interface for calculating all technical indicators
on OHLCV data with support for multiple timeframes and caching.
"""

from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from market_analysis.indicators.bollinger_bands import (
    BollingerBands,
    BollingerBandsResult,
)
from market_analysis.indicators.macd import MACD, MACDResult
from market_analysis.indicators.rsi import RSI, RSIResult

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from data_ingestion.timeframe_config import Timeframe

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe


@dataclass
class IndicatorSet:
    """Complete set of calculated indicators for a timeframe.

    Attributes:
        timeframe: The timeframe these indicators represent
        rsi: RSI calculation result
        macd: MACD calculation result
        bollinger_bands: Bollinger Bands calculation result
        timestamp: When these indicators were calculated
    """

    timeframe: "Timeframe"
    rsi: RSIResult | None = None
    macd: MACDResult | None = None
    bollinger_bands: BollingerBandsResult | None = None
    timestamp: int = field(
        default_factory=lambda: int(np.datetime64("now").astype(int))
    )


@dataclass
class IndicatorCache:
    """Cache entry for indicator calculations.

    Attributes:
        data_hash: Hash of input data for cache validation
        indicators: Calculated indicator set
    """

    data_hash: str
    indicators: IndicatorSet


class IndicatorCalculator:
    """Unified calculator for all technical indicators.

    Provides a single interface for calculating RSI, MACD, and Bollinger Bands
    with support for multiple timeframes and optional caching.

    Example:
        calculator = IndicatorCalculator()

        # Calculate all indicators for single timeframe
        indicators = calculator.calculate_all(data, Timeframe.MINUTE_5)

        # Calculate for multiple timeframes
        results = calculator.calculate_multiple_timeframes(data_map)
    """

    def __init__(self, use_cache: bool = True):
        """Initialize indicator calculator.

        Args:
            use_cache: Whether to cache calculation results (default: True)
        """
        self.use_cache = use_cache
        self._cache: dict[str, IndicatorCache] = {}

        # Initialize indicator calculators with default parameters
        self._rsi = RSI(period=14)
        self._macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        self._bb = BollingerBands(period=20, num_std_dev=2.0)

    def calculate_rsi(self, data: list[OHLCVData]) -> RSIResult:
        """Calculate RSI for the given data.

        Args:
            data: List of OHLCV data points

        Returns:
            RSI calculation result
        """
        return self._rsi.calculate(data)

    def calculate_macd(self, data: list[OHLCVData]) -> MACDResult:
        """Calculate MACD for the given data.

        Args:
            data: List of OHLCV data points

        Returns:
            MACD calculation result
        """
        return self._macd.calculate(data)

    def calculate_bollinger_bands(self, data: list[OHLCVData]) -> BollingerBandsResult:
        """Calculate Bollinger Bands for the given data.

        Args:
            data: List of OHLCV data points

        Returns:
            Bollinger Bands calculation result
        """
        return self._bb.calculate(data)

    def calculate_all(
        self,
        data: list[OHLCVData],
        timeframe: Timeframe,
    ) -> IndicatorSet:
        """Calculate all indicators for the given data.

        Args:
            data: List of OHLCV data points
            timeframe: The timeframe of the data

        Returns:
            IndicatorSet containing all calculated indicators
        """
        if not data:
            return IndicatorSet(timeframe=timeframe)

        # Check cache if enabled
        if self.use_cache:
            cache_key = self._generate_cache_key(data, timeframe)
            cached = self._get_from_cache(cache_key, data)
            if cached:
                return cached

        # Calculate all indicators
        indicators = IndicatorSet(timeframe=timeframe)

        # RSI requires period + 1 data points
        if len(data) > self._rsi.period:
            with suppress(ValueError):
                indicators.rsi = self.calculate_rsi(data)

        # MACD requires slow_period + signal_period data points
        min_macd = self._macd.slow_period + self._macd.signal_period
        if len(data) >= min_macd:
            with suppress(ValueError):
                indicators.macd = self.calculate_macd(data)

        # Bollinger Bands requires period data points
        if len(data) >= self._bb.period:
            with suppress(ValueError):
                indicators.bollinger_bands = self.calculate_bollinger_bands(data)

        # Store in cache if enabled
        if self.use_cache:
            self._store_in_cache(cache_key, data, indicators)

        return indicators

    def calculate_multiple_timeframes(
        self,
        data_map: dict[Timeframe, list[OHLCVData]],
    ) -> dict[Timeframe, IndicatorSet]:
        """Calculate indicators for multiple timeframes.

        Args:
            data_map: Dictionary mapping timeframe to OHLCV data

        Returns:
            Dictionary mapping timeframe to IndicatorSet
        """
        results: dict[Timeframe, IndicatorSet] = {}

        for timeframe, data in data_map.items():
            results[timeframe] = self.calculate_all(data, timeframe)

        return results

    def get_latest_values(
        self,
        indicators: IndicatorSet,
    ) -> dict[str, float | None]:
        """Get the latest values from an indicator set.

        Args:
            indicators: IndicatorSet to extract values from

        Returns:
            Dictionary of latest indicator values
        """
        return {
            "rsi": indicators.rsi.current if indicators.rsi else None,
            "rsi_overbought": indicators.rsi.is_overbought if indicators.rsi else None,
            "rsi_oversold": indicators.rsi.is_oversold if indicators.rsi else None,
            "macd": indicators.macd.current_macd if indicators.macd else None,
            "macd_signal": indicators.macd.current_signal if indicators.macd else None,
            "macd_histogram": (
                indicators.macd.current_histogram if indicators.macd else None
            ),
            "bb_middle": (
                indicators.bollinger_bands.current_middle
                if indicators.bollinger_bands
                else None
            ),
            "bb_upper": (
                indicators.bollinger_bands.current_upper
                if indicators.bollinger_bands
                else None
            ),
            "bb_lower": (
                indicators.bollinger_bands.current_lower
                if indicators.bollinger_bands
                else None
            ),
            "bb_width": (
                indicators.bollinger_bands.current_band_width
                if indicators.bollinger_bands
                else None
            ),
            "bb_percent_b": (
                indicators.bollinger_bands.current_percent_b
                if indicators.bollinger_bands
                else None
            ),
        }

    def clear_cache(self) -> None:
        """Clear the indicator calculation cache."""
        self._cache.clear()

    def _generate_cache_key(self, data: list[OHLCVData], timeframe: Timeframe) -> str:
        """Generate a cache key for the given data and timeframe.

        Args:
            data: List of OHLCV data points
            timeframe: The timeframe of the data

        Returns:
            Cache key string
        """
        if not data:
            return f"{timeframe.value}:empty"

        # Use first and last timestamp plus length as simple hash
        first_ts = data[0].timestamp
        last_ts = data[-1].timestamp
        return f"{timeframe.value}:{first_ts}:{last_ts}:{len(data)}"

    def _get_from_cache(
        self, cache_key: str, data: list[OHLCVData]
    ) -> IndicatorSet | None:
        """Retrieve cached indicators if valid.

        Args:
            cache_key: Cache key to look up
            data: Current data to validate against

        Returns:
            Cached IndicatorSet if valid, None otherwise
        """
        if cache_key not in self._cache:
            return None

        cached = self._cache[cache_key]
        current_hash = self._hash_data(data)

        if cached.data_hash == current_hash:
            return cached.indicators

        return None

    def _store_in_cache(
        self,
        cache_key: str,
        data: list[OHLCVData],
        indicators: IndicatorSet,
    ) -> None:
        """Store indicators in cache.

        Args:
            cache_key: Cache key
            data: Input data for hash
            indicators: Calculated indicators to cache
        """
        data_hash = self._hash_data(data)
        self._cache[cache_key] = IndicatorCache(
            data_hash=data_hash,
            indicators=indicators,
        )

    def _hash_data(self, data: list[OHLCVData]) -> str:
        """Generate a simple hash of the data for cache validation.

        Args:
            data: List of OHLCV data points

        Returns:
            Hash string
        """
        if not data:
            return "empty"

        # Simple hash based on first/last timestamps and close prices
        first = data[0]
        last = data[-1]
        return (
            f"{first.timestamp}:{first.close_price}:"
            f"{last.timestamp}:{last.close_price}:{len(data)}"
        )
