"""Technical indicator calculator for feature extraction.

Provides standardized calculation of RSI, MACD, and Bollinger Bands
with reference implementation matching market_analysis indicators.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData

logger = logging.getLogger(__name__)


@dataclass
class IndicatorValues:
    """Container for calculated indicator values.

    Attributes:
        rsi: Relative Strength Index (0-100)
        macd: MACD line value
        macd_signal: MACD signal line value
        macd_histogram: MACD histogram (macd - signal)
        bb_upper: Bollinger Bands upper band
        bb_middle: Bollinger Bands middle band (SMA)
        bb_lower: Bollinger Bands lower band
        bb_width: Bollinger Bands width percentage
        bb_percent_b: %B indicator (position within bands)
    """

    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    bb_percent_b: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        """Convert to dictionary."""
        return {
            "rsi": self.rsi,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "bb_upper": self.bb_upper,
            "bb_middle": self.bb_middle,
            "bb_lower": self.bb_lower,
            "bb_width": self.bb_width,
            "bb_percent_b": self.bb_percent_b,
        }

    def to_normalized_dict(self) -> dict[str, float]:
        """Convert to normalized dictionary [0, 1] range.

        Returns:
            Dictionary with normalized values (0.5 for None)
        """
        return {
            "rsi_norm": self._normalize_rsi(self.rsi),
            "macd_norm": self._normalize_macd(self.macd),
            "macd_signal_norm": self._normalize_macd(self.macd_signal),
            "macd_histogram_norm": self._normalize_macd(self.macd_histogram),
            "bb_position_norm": self._normalize_bb_position(self.bb_percent_b),
            "bb_width_norm": self._normalize_bb_width(self.bb_width),
        }

    @staticmethod
    def _normalize_rsi(rsi: float | None) -> float:
        """Normalize RSI to [0, 1] range."""
        if rsi is None:
            return 0.5
        return max(0.0, min(1.0, rsi / 100.0))

    @staticmethod
    def _normalize_macd(macd: float | None) -> float:
        """Normalize MACD to [0, 1] range using sigmoid-like scaling."""
        if macd is None:
            return 0.5
        # Scale MACD values typically in range [-5, 5] to [0, 1]
        return max(0.0, min(1.0, (macd + 5.0) / 10.0))

    @staticmethod
    def _normalize_bb_position(percent_b: float | None) -> float:
        """Normalize %B to [0, 1] range."""
        if percent_b is None:
            return 0.5
        # %B typically ranges [0, 1], but can exceed
        return max(0.0, min(1.0, percent_b))

    @staticmethod
    def _normalize_bb_width(width: float | None) -> float:
        """Normalize BB width to [0, 1] range."""
        if width is None:
            return 0.5
        # Width typically 0-10%, scale to [0, 1]
        return max(0.0, min(1.0, width / 0.1))


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data.

    Implements standard technical analysis indicators:
    - RSI(14): Relative Strength Index
    - MACD(12,26,9): Moving Average Convergence Divergence
    - Bollinger Bands(20,2): Volatility bands

    Matches reference implementations in market_analysis.indicators.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
    ):
        """Initialize calculator with indicator parameters.

        Args:
            rsi_period: Period for RSI calculation (default: 14)
            macd_fast: Fast EMA period for MACD (default: 12)
            macd_slow: Slow EMA period for MACD (default: 26)
            macd_signal: Signal line period for MACD (default: 9)
            bb_period: Period for Bollinger Bands (default: 20)
            bb_std_dev: Standard deviation multiplier (default: 2.0)
        """
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev

    def calculate_all(self, data: list[OHLCVData]) -> IndicatorValues:
        """Calculate all indicators from OHLCV data.

        Args:
            data: List of OHLCV data points (minimum 50 recommended)

        Returns:
            IndicatorValues with all calculated indicators
        """
        if not data or len(data) < self.macd_slow + self.macd_signal:
            logger.warning(
                f"Insufficient data for indicators: {len(data)} points, "
                f"need at least {self.macd_slow + self.macd_signal}"
            )
            return IndicatorValues()

        closes = [c.close_price for c in data]

        return IndicatorValues(
            rsi=self.calculate_rsi(closes),
            macd=self.calculate_macd(closes)[0],
            macd_signal=self.calculate_macd(closes)[1],
            macd_histogram=self.calculate_macd(closes)[2],
            bb_upper=self.calculate_bollinger_bands(closes)[0],
            bb_middle=self.calculate_bollinger_bands(closes)[1],
            bb_lower=self.calculate_bollinger_bands(closes)[2],
            bb_width=self.calculate_bollinger_bands(closes)[3],
            bb_percent_b=self.calculate_bollinger_bands(closes)[4],
        )

    def calculate_rsi(self, prices: list[float]) -> float | None:
        """Calculate RSI (Relative Strength Index).

        Formula: RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss

        Args:
            prices: List of closing prices

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < self.rsi_period + 1:
            return None

        # Calculate price changes
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        # Get gains and losses for the RSI period
        gains = [max(0, d) for d in deltas[-self.rsi_period :]]
        losses = [abs(min(0, d)) for d in deltas[-self.rsi_period :]]

        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_macd(
        self, prices: list[float]
    ) -> tuple[float | None, float | None, float | None]:
        """Calculate MACD (Moving Average Convergence Divergence).

        Formula:
        - MACD Line = EMA(12) - EMA(26)
        - Signal Line = EMA(9) of MACD Line
        - Histogram = MACD Line - Signal Line

        Args:
            prices: List of closing prices

        Returns:
            Tuple of (macd_line, signal_line, histogram) or None if insufficient data
        """
        min_periods = self.macd_slow + self.macd_signal
        if len(prices) < min_periods:
            return None, None, None

        # Calculate EMAs
        ema_fast = self._calculate_ema(prices, self.macd_fast)
        ema_slow = self._calculate_ema(prices, self.macd_slow)

        if ema_fast is None or ema_slow is None:
            return None, None, None

        # MACD line
        macd_line = ema_fast - ema_slow

        # Calculate historical MACD values for signal line
        macd_values = []
        for i in range(self.macd_signal, 0, -1):
            if len(prices) >= self.macd_slow + i:
                fast = self._calculate_ema(prices[:-i], self.macd_fast)
                slow = self._calculate_ema(prices[:-i], self.macd_slow)
                if fast is not None and slow is not None:
                    macd_values.append(fast - slow)

        # Add current MACD
        macd_values.append(macd_line)

        # Signal line is EMA of MACD values
        if len(macd_values) >= self.macd_signal:
            signal_line = self._calculate_ema_from_values(macd_values, self.macd_signal)
        else:
            signal_line = (
                sum(macd_values) / len(macd_values) if macd_values else macd_line
            )

        # Histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_bollinger_bands(
        self, prices: list[float]
    ) -> tuple[float | None, float | None, float | None, float | None, float | None]:
        """Calculate Bollinger Bands.

        Formula:
        - Middle Band = SMA(20)
        - Upper Band = Middle + (2 * StdDev)
        - Lower Band = Middle - (2 * StdDev)
        - Width = (Upper - Lower) / Middle
        - %B = (Price - Lower) / (Upper - Lower)

        Args:
            prices: List of closing prices

        Returns:
            Tuple of (upper, middle, lower, width, percent_b) or None if insufficient data
        """
        if len(prices) < self.bb_period:
            return None, None, None, None, None

        # Calculate SMA (middle band)
        recent_prices = prices[-self.bb_period :]
        middle = sum(recent_prices) / len(recent_prices)

        # Calculate standard deviation
        variance = sum((p - middle) ** 2 for p in recent_prices) / len(recent_prices)
        std_dev = variance**0.5

        # Calculate bands
        upper = middle + (self.bb_std_dev * std_dev)
        lower = middle - (self.bb_std_dev * std_dev)

        # Calculate width percentage
        width = (upper - lower) / middle if middle != 0 else 0

        # Calculate %B
        current_price = prices[-1]
        band_range = upper - lower
        percent_b = (current_price - lower) / band_range if band_range != 0 else 0.5

        return upper, middle, lower, width, percent_b

    def _calculate_ema(self, prices: list[float], period: int) -> float | None:
        """Calculate Exponential Moving Average.

        Args:
            prices: List of prices
            period: EMA period

        Returns:
            EMA value or None if insufficient data
        """
        if len(prices) < period:
            return None

        recent_prices = prices[-period:]
        multiplier = 2 / (period + 1)

        # Start with SMA
        ema = sum(recent_prices[:period]) / period

        # Apply EMA formula
        for price in recent_prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_ema_from_values(self, values: list[float], period: int) -> float:
        """Calculate EMA from a list of values.

        Args:
            values: List of values
            period: EMA period

        Returns:
            EMA value
        """
        if len(values) == 0:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)

        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period

        for value in values[period:]:
            ema = (value - ema) * multiplier + ema

        return ema

    def get_feature_count(self) -> int:
        """Get the number of features this calculator produces.

        Returns:
            Number of features (raw + normalized)
        """
        return 14  # 8 raw + 6 normalized
