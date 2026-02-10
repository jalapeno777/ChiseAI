"""ATR (Average True Range) indicator calculation.

Implements ATR calculation using Wilder's smoothing method
for volatility-based stop-loss calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


@dataclass
class ATRResult:
    """Result of ATR calculation.

    Attributes:
        values: Array of ATR values (same length as input data)
        current: Current (latest) ATR value
        period: The period used for calculation
    """

    values: np.ndarray
    current: float
    period: int

    def __post_init__(self) -> None:
        """Ensure current is a float."""
        self.current = float(self.current)


class ATR:
    """Average True Range indicator using Wilder's smoothing.

    ATR measures market volatility by calculating the average
    of true ranges over a specified period. Uses Wilder's smoothing
    method (RMA) for consistency with TradingView.

    Example:
        atr = ATR(period=14)
        result = atr.calculate(ohlcv_data)
        print(f"Current ATR: {result.current}")
    """

    def __init__(self, period: int = 14):
        """Initialize ATR calculator.

        Args:
            period: Period for ATR calculation (default: 14)
        """
        self.period = period

    def calculate(self, data: list["OHLCVData"]) -> ATRResult:
        """Calculate ATR for the given OHLCV data.

        Args:
            data: List of OHLCV data points

        Returns:
            ATRResult with values array and current ATR

        Raises:
            ValueError: If insufficient data points
        """
        if len(data) < self.period + 1:
            raise ValueError(
                f"ATR requires at least {self.period + 1} data points, got {len(data)}"
            )

        # Calculate true ranges
        true_ranges = self._calculate_true_ranges(data)

        # Apply Wilder's smoothing (RMA)
        atr_values = self._wilders_smoothing(true_ranges)

        return ATRResult(
            values=atr_values,
            current=float(atr_values[-1]),
            period=self.period,
        )

    def _calculate_true_ranges(self, data: list["OHLCVData"]) -> np.ndarray:
        """Calculate true range for each bar.

        True Range = max(
            high - low,
            |high - previous close|,
            |low - previous close|
        )

        Args:
            data: List of OHLCV data points

        Returns:
            Array of true range values
        """
        highs = np.array([d.high_price for d in data])
        lows = np.array([d.low_price for d in data])
        closes = np.array([d.close_price for d in data])

        # Current high - current low
        range1 = highs - lows

        # |Current high - previous close|
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]  # First bar has no previous close
        range2 = np.abs(highs - prev_closes)

        # |Current low - previous close|
        range3 = np.abs(lows - prev_closes)

        # True range is the maximum of the three
        true_ranges = np.maximum(np.maximum(range1, range2), range3)

        # First bar has no previous close, so use simple range
        true_ranges[0] = range1[0]

        return true_ranges

    def _wilders_smoothing(self, values: np.ndarray) -> np.ndarray:
        """Apply Wilder's smoothing (RMA) to values.

        Wilder's smoothing is an exponential moving average with
        alpha = 1 / period.

        Args:
            values: Array of values to smooth

        Returns:
            Array of smoothed values
        """
        alpha = 1.0 / self.period
        smoothed = np.zeros(len(values))

        # First value is simple average of first 'period' values
        smoothed[self.period - 1] = np.mean(values[: self.period])

        # Apply exponential smoothing for remaining values
        for i in range(self.period, len(values)):
            smoothed[i] = (
                smoothed[i - 1] * (self.period - 1) + values[i]
            ) / self.period

        # Fill initial values with the first calculated average
        smoothed[: self.period - 1] = smoothed[self.period - 1]

        return smoothed
