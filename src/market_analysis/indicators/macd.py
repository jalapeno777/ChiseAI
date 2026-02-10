"""Moving Average Convergence Divergence (MACD) indicator implementation.

MACD is a trend-following momentum indicator that shows the relationship
between two moving averages of a security's price. It consists of the
MACD line, signal line, and histogram.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


class MACDSignal(Enum):
    """MACD signal types for crossover detection."""

    NONE = "none"
    BULLISH_CROSSOVER = "bullish_crossover"  # MACD crosses above signal
    BEARISH_CROSSOVER = "bearish_crossover"  # MACD crosses below signal


@dataclass
class MACDResult:
    """Result of MACD calculation.

    Attributes:
        macd_line: Array of MACD line values
        signal_line: Array of signal line values
        histogram: Array of histogram values (MACD - Signal)
        crossovers: Array of MACDSignal indicating crossovers
        timestamps: Array of corresponding timestamps
    """

    macd_line: np.ndarray
    signal_line: np.ndarray
    histogram: np.ndarray
    crossovers: np.ndarray
    timestamps: np.ndarray

    @property
    def current_macd(self) -> float | None:
        """Get the most recent MACD line value."""
        if len(self.macd_line) > 0:
            return float(self.macd_line[-1])
        return None

    @property
    def current_signal(self) -> float | None:
        """Get the most recent signal line value."""
        if len(self.signal_line) > 0:
            return float(self.signal_line[-1])
        return None

    @property
    def current_histogram(self) -> float | None:
        """Get the most recent histogram value."""
        if len(self.histogram) > 0:
            return float(self.histogram[-1])
        return None

    @property
    def latest_crossover(self) -> MACDSignal:
        """Get the most recent crossover signal."""
        # Filter out NONE signals and get the last one
        non_none = self.crossovers[self.crossovers != MACDSignal.NONE]
        if len(non_none) > 0:
            return non_none[-1]  # type: ignore[no-any-return]
        return MACDSignal.NONE


class MACD:
    """Moving Average Convergence Divergence calculator.

    Standard parameters:
        - Fast EMA period: 12
        - Slow EMA period: 26
        - Signal line period: 9

    MACD Line = Fast EMA - Slow EMA
    Signal Line = EMA(MACD Line, signal_period)
    Histogram = MACD Line - Signal Line

    Reference:
        Gerald Appel, "Technical Analysis: Power Tools for Active Investors" (2005)
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ):
        """Initialize MACD calculator.

        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)

        Raises:
            ValueError: If periods are invalid
        """
        if fast_period >= slow_period:
            raise ValueError("Fast period must be less than slow period")
        if signal_period < 1:
            raise ValueError("Signal period must be positive")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate(self, data: list["OHLCVData"]) -> MACDResult:
        """Calculate MACD from OHLCV data.

        Args:
            data: List of OHLCV data points

        Returns:
            MACDResult containing MACD line, signal line, histogram, and crossovers

        Raises:
            ValueError: If insufficient data points for calculation
        """
        min_required = self.slow_period + self.signal_period
        if len(data) < min_required:
            raise ValueError(
                f"MACD requires at least {min_required} data points, got {len(data)}"
            )

        # Extract close prices
        closes = np.array([d.close_price for d in data])
        timestamps = np.array([d.timestamp for d in data])

        # Calculate EMAs
        fast_ema = self._calculate_ema(closes, self.fast_period)
        slow_ema = self._calculate_ema(closes, self.slow_period)

        # Calculate MACD line
        macd_line = fast_ema - slow_ema

        # Calculate signal line (EMA of MACD line)
        signal_line = self._calculate_ema(macd_line, self.signal_period)

        # Calculate histogram
        histogram = macd_line - signal_line

        # Detect crossovers
        crossovers = self._detect_crossovers(macd_line, signal_line)

        return MACDResult(
            macd_line=macd_line,
            signal_line=signal_line,
            histogram=histogram,
            crossovers=crossovers,
            timestamps=timestamps,
        )

    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average.

        Uses the standard EMA formula with smoothing factor alpha = 2/(period+1).

        Args:
            data: Input data array
            period: EMA period

        Returns:
            Array of EMA values
        """
        alpha = 2.0 / (period + 1)

        # Initialize EMA array
        ema = np.full(len(data), np.nan)

        # Find first valid index (where we have enough non-NaN values for SMA)
        valid_mask = ~np.isnan(data)
        valid_indices = np.where(valid_mask)[0]

        if len(valid_indices) < period:
            return ema  # Not enough valid data

        first_valid_idx = valid_indices[0]
        sma_start_idx = first_valid_idx
        sma_end_idx = first_valid_idx + period

        # Check if we have enough consecutive valid values for initial SMA
        if sma_end_idx > len(data) or not np.all(valid_mask[sma_start_idx:sma_end_idx]):
            # Find first position with `period` consecutive valid values
            for i in range(len(data) - period + 1):
                if np.all(valid_mask[i : i + period]):
                    sma_start_idx = i
                    sma_end_idx = i + period
                    break
            else:
                return ema  # No valid window found

        # First EMA value is SMA of first `period` valid values
        first_ema_idx = sma_end_idx - 1
        ema[first_ema_idx] = np.mean(data[sma_start_idx:sma_end_idx])

        # Calculate subsequent EMA values
        for i in range(first_ema_idx + 1, len(data)):
            if not np.isnan(data[i]):
                ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
            else:
                ema[i] = ema[i - 1]  # Carry forward last valid EMA

        return ema

    def _detect_crossovers(
        self, macd_line: np.ndarray, signal_line: np.ndarray
    ) -> np.ndarray:
        """Detect MACD signal line crossovers.

        A bullish crossover occurs when MACD crosses above the signal line.
        A bearish crossover occurs when MACD crosses below the signal line.

        Args:
            macd_line: Array of MACD line values
            signal_line: Array of signal line values

        Returns:
            Array of MACDSignal values
        """
        crossovers = np.full(len(macd_line), MACDSignal.NONE, dtype=object)

        # Calculate difference
        diff = macd_line - signal_line

        # Detect crossovers (sign change in difference)
        for i in range(1, len(diff)):
            if np.isnan(diff[i]) or np.isnan(diff[i - 1]):
                continue

            if diff[i - 1] <= 0 and diff[i] > 0:
                # MACD crossed above signal (bullish)
                crossovers[i] = MACDSignal.BULLISH_CROSSOVER
            elif diff[i - 1] >= 0 and diff[i] < 0:
                # MACD crossed below signal (bearish)
                crossovers[i] = MACDSignal.BEARISH_CROSSOVER

        return crossovers

    def calculate_from_prices(
        self, prices: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate MACD directly from price array.

        Args:
            prices: Array of price values

        Returns:
            Tuple of (macd_line, signal_line, histogram) arrays
        """
        min_required = self.slow_period + self.signal_period
        if len(prices) < min_required:
            raise ValueError(
                f"MACD requires at least {min_required} prices, got {len(prices)}"
            )

        # Calculate EMAs
        fast_ema = self._calculate_ema(prices, self.fast_period)
        slow_ema = self._calculate_ema(prices, self.slow_period)

        # Calculate MACD line
        macd_line = fast_ema - slow_ema

        # Calculate signal line
        signal_line = self._calculate_ema(macd_line, self.signal_period)

        # Calculate histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram
