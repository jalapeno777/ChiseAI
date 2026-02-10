"""Relative Strength Index (RSI) indicator implementation.

RSI is a momentum oscillator that measures the speed and magnitude of
recent price changes to evaluate overbought or oversold conditions.
Uses Wilder's smoothing method for calculation.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


@dataclass
class RSIResult:
    """Result of RSI calculation.

    Attributes:
        values: Array of RSI values (0-100)
        overbought: Boolean array indicating overbought conditions (>70)
        oversold: Boolean array indicating oversold conditions (<30)
        timestamps: Array of corresponding timestamps
    """

    values: np.ndarray
    overbought: np.ndarray
    oversold: np.ndarray
    timestamps: np.ndarray

    @property
    def current(self) -> float | None:
        """Get the most recent RSI value."""
        if len(self.values) > 0:
            return float(self.values[-1])
        return None

    @property
    def is_overbought(self) -> bool:
        """Check if current RSI indicates overbought condition."""
        if len(self.overbought) > 0:
            return bool(self.overbought[-1])
        return False

    @property
    def is_oversold(self) -> bool:
        """Check if current RSI indicates oversold condition."""
        if len(self.oversold) > 0:
            return bool(self.oversold[-1])
        return False


class RSI:
    """Relative Strength Index calculator using Wilder's smoothing method.

    Standard period is 14, with overbought threshold at 70 and
    oversold threshold at 30.

    Reference:
        Welles Wilder, "New Concepts in Technical Trading Systems" (1978)
    """

    def __init__(
        self,
        period: int = 14,
        overbought_threshold: float = 70.0,
        oversold_threshold: float = 30.0,
    ):
        """Initialize RSI calculator.

        Args:
            period: RSI calculation period (default: 14)
            overbought_threshold: Level above which is considered overbought (default: 70)
            oversold_threshold: Level below which is considered oversold (default: 30)
        """
        self.period = period
        self.overbought_threshold = overbought_threshold
        self.oversold_threshold = oversold_threshold

    def _calculate_rma(self, values: np.ndarray) -> np.ndarray:
        """Calculate Running Moving Average (RMA) using TradingView's method.

        TradingView's RMA (also known as SMMA - Smoothed Moving Average) uses:
        - alpha = 1 / length
        - First value: alpha * x[0] (not SMA of first 'length' values)
        - Subsequent: alpha * x[i] + (1 - alpha) * prev_rma

        Args:
            values: Array of values to smooth

        Returns:
            Array of RMA values
        """
        alpha = 1.0 / self.period
        result = np.full(len(values), np.nan)

        # First value: alpha * x[0] (TradingView initialization)
        rma = alpha * values[0]
        result[0] = rma

        # Subsequent values: alpha * x[i] + (1 - alpha) * prev_rma
        for i in range(1, len(values)):
            rma = alpha * values[i] + (1 - alpha) * rma
            result[i] = rma

        return result

    def calculate(self, data: list["OHLCVData"]) -> RSIResult:
        """Calculate RSI from OHLCV data.

        Uses Wilder's smoothing method (RMA/SMMA) matching TradingView's implementation.

        Args:
            data: List of OHLCV data points

        Returns:
            RSIResult containing RSI values and signals

        Raises:
            ValueError: If insufficient data points for calculation
        """
        if len(data) < self.period + 1:
            raise ValueError(
                f"RSI requires at least {self.period + 1} data points, got {len(data)}"
            )

        # Extract close prices
        closes = np.array([d.close_price for d in data])
        timestamps = np.array([d.timestamp for d in data])

        # Calculate price changes
        deltas = np.diff(closes)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate RMA (Running Moving Average) of gains and losses
        # This matches TradingView's rsi() implementation
        avg_gains = self._calculate_rma(gains)
        avg_losses = self._calculate_rma(losses)

        # Initialize RSI array
        rsi_values = np.full(len(data), np.nan)

        # Calculate RSI values starting from period-1 (index of first valid RMA)
        for i in range(self.period - 1, len(deltas)):
            avg_gain = avg_gains[i]
            avg_loss = avg_losses[i]

            if avg_loss == 0:
                rsi_values[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_values[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        # Clip to valid range [0, 100] but preserve NaN values
        rsi_values = np.clip(rsi_values, 0.0, 100.0)

        # Handle infinite values (keep NaN as is)
        rsi_values = np.where(
            np.isinf(rsi_values), np.where(rsi_values > 0, 100.0, 0.0), rsi_values
        )

        # Determine overbought/oversold conditions (NaN values are neither)
        overbought = rsi_values > self.overbought_threshold
        oversold = rsi_values < self.oversold_threshold

        return RSIResult(
            values=rsi_values,
            overbought=overbought,
            oversold=oversold,
            timestamps=timestamps,
        )

    def calculate_from_prices(self, prices: np.ndarray) -> np.ndarray:
        """Calculate RSI directly from price array.

        Uses TradingView's RMA (Running Moving Average) method for smoothing.

        Args:
            prices: Array of price values

        Returns:
            Array of RSI values
        """
        if len(prices) < self.period + 1:
            raise ValueError(
                f"RSI requires at least {self.period + 1} prices, got {len(prices)}"
            )

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate RMA (Running Moving Average) of gains and losses
        avg_gains = self._calculate_rma(gains)
        avg_losses = self._calculate_rma(losses)

        # Initialize RSI array
        rsi_values = np.full(len(prices), np.nan)

        # Calculate RSI values starting from period-1 (index of first valid RMA)
        for i in range(self.period - 1, len(deltas)):
            avg_gain = avg_gains[i]
            avg_loss = avg_losses[i]

            if avg_loss == 0:
                rsi_values[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_values[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        # Clip to valid range [0, 100] but preserve NaN values
        rsi_values = np.clip(rsi_values, 0.0, 100.0)

        # Handle infinite values (keep NaN as is)
        rsi_values = np.where(
            np.isinf(rsi_values), np.where(rsi_values > 0, 100.0, 0.0), rsi_values
        )

        return rsi_values
