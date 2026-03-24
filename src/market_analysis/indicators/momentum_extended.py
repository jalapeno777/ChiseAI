"""Extended momentum indicators: MFI, StochRSI, Williams %R."""

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from market_analysis.indicators.base import BaseIndicator, Signal, SignalDirection


@dataclass
class MFIResult:
    """Money Flow Index result."""

    values: np.ndarray
    overbought: np.ndarray
    oversold: np.ndarray

    @property
    def current(self) -> float | None:
        """Return the most recent non-NaN MFI value, or None."""
        valid = self.values[~np.isnan(self.values)]
        return float(valid[-1]) if len(valid) > 0 else None


@dataclass
class StochRSIResult:
    """Stochastic RSI result."""

    k: np.ndarray  # %K line
    d: np.ndarray  # %D line
    overbought: np.ndarray
    oversold: np.ndarray

    @property
    def current_k(self) -> float | None:
        """Return the most recent non-NaN %K value, or None."""
        valid = self.k[~np.isnan(self.k)]
        return float(valid[-1]) if len(valid) > 0 else None

    @property
    def current_d(self) -> float | None:
        """Return the most recent non-NaN %D value, or None."""
        valid = self.d[~np.isnan(self.d)]
        return float(valid[-1]) if len(valid) > 0 else None


@dataclass
class WilliamsRResult:
    """Williams %R result."""

    values: np.ndarray
    overbought: np.ndarray
    oversold: np.ndarray

    @property
    def current(self) -> float | None:
        """Return the most recent non-NaN Williams %R value, or None."""
        valid = self.values[~np.isnan(self.values)]
        return float(valid[-1]) if len(valid) > 0 else None


class MFI(BaseIndicator):
    """Money Flow Index indicator.

    MFI combines price and volume to measure buying/selling pressure.
    Range: 0-100 (similar to RSI but volume-weighted).
    """

    def __init__(
        self,
        period: int = 14,
        overbought_threshold: float = 80.0,
        oversold_threshold: float = 20.0,
        name: str = "MFI",
    ):
        super().__init__(name)
        self.period = period
        self.overbought_threshold = overbought_threshold
        self.oversold_threshold = oversold_threshold

    @property
    def description(self) -> str:
        return f"Money Flow Index ({self.period})"

    @property
    def parameters(self) -> dict:
        return {
            "period": self.period,
            "overbought_threshold": self.overbought_threshold,
            "oversold_threshold": self.oversold_threshold,
        }

    def validate(self, data: list) -> bool:
        return len(data) >= self.period + 1

    def compute(self, data: list) -> MFIResult:
        """Calculate MFI.

        Args:
            data: List of OHLCVData points (needs period+1 minimum).

        Returns:
            MFIResult with values, overbought, and oversold boolean arrays.

        Raises:
            ValueError: If insufficient data points.
        """
        if not self.validate(data):
            raise ValueError(f"Need {self.period + 1} data points, got {len(data)}")

        highs = np.array([d.high_price for d in data])
        lows = np.array([d.low_price for d in data])
        closes = np.array([d.close_price for d in data])
        volumes = np.array([d.volume for d in data])

        # Typical price
        typical_prices = (highs + lows + closes) / 3.0

        # Raw money flow
        raw_money_flow = typical_prices * volumes

        # Money flow sign based on typical price change
        money_flow_sign = np.diff(typical_prices)
        positive_flow = np.where(money_flow_sign > 0, raw_money_flow[1:], 0.0)
        negative_flow = np.where(money_flow_sign < 0, raw_money_flow[1:], 0.0)

        # Calculate running sums using RMA
        positive_sum = _calculate_rma(positive_flow, self.period)
        negative_sum = _calculate_rma(negative_flow, self.period)

        mfi_values = np.full(len(data), np.nan)
        for i in range(self.period - 1, len(positive_sum)):
            if negative_sum[i] == 0:
                mfi_values[i + 1] = 100.0
            else:
                money_ratio = positive_sum[i] / negative_sum[i]
                mfi_values[i + 1] = 100.0 - (100.0 / (1.0 + money_ratio))

        overbought = mfi_values > self.overbought_threshold
        oversold = mfi_values < self.oversold_threshold

        return MFIResult(
            values=mfi_values,
            overbought=overbought,
            oversold=oversold,
        )

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: MFIResult) -> Signal:
        """Convert MFI result to trading signal.

        Args:
            result: MFIResult from compute().

        Returns:
            Signal with BUY/SELL/HOLD direction based on overbought/oversold.
        """
        current = result.current
        if current is None:
            return Signal(
                direction=SignalDirection.HOLD,
                confidence=0.5,
                timestamp=datetime.now(UTC),
                metadata={},
            )

        if current > self.overbought_threshold:
            direction = SignalDirection.SELL
            confidence = min((current - self.overbought_threshold) / 20.0, 1.0)
        elif current < self.oversold_threshold:
            direction = SignalDirection.BUY
            confidence = min((self.oversold_threshold - current) / 20.0, 1.0)
        else:
            direction = SignalDirection.HOLD
            confidence = 0.5

        return Signal(
            direction=direction,
            confidence=confidence,
            timestamp=datetime.now(UTC),
            metadata={"mfi": current},
        )


class StochRSI(BaseIndicator):
    """Stochastic RSI indicator.

    Applies Stochastic oscillator formula to RSI values.
    More sensitive than regular RSI.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_period: int = 3,
        d_period: int = 3,
        overbought_threshold: float = 80.0,
        oversold_threshold: float = 20.0,
        name: str = "StochRSI",
    ):
        super().__init__(name)
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_period = k_period
        self.d_period = d_period
        self.overbought_threshold = overbought_threshold
        self.oversold_threshold = oversold_threshold

    @property
    def description(self) -> str:
        return (
            f"Stochastic RSI "
            f"({self.rsi_period},{self.stoch_period},{self.k_period},{self.d_period})"
        )

    @property
    def parameters(self) -> dict:
        return {
            "rsi_period": self.rsi_period,
            "stoch_period": self.stoch_period,
            "k_period": self.k_period,
            "d_period": self.d_period,
            "overbought_threshold": self.overbought_threshold,
            "oversold_threshold": self.oversold_threshold,
        }

    def validate(self, data: list) -> bool:
        return len(data) >= self.rsi_period + self.stoch_period + self.k_period

    def compute(self, data: list) -> StochRSIResult:
        """Calculate StochRSI.

        Args:
            data: List of OHLCVData points.

        Returns:
            StochRSIResult with %K, %D, overbought, and oversold arrays.

        Raises:
            ValueError: If insufficient data points.
        """
        min_required = self.rsi_period + self.stoch_period + self.k_period
        if not self.validate(data):
            raise ValueError(f"Need {min_required} data points, got {len(data)}")

        closes = np.array([d.close_price for d in data])

        # Step 1: Calculate RSI
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gains = _calculate_rma(gains, self.rsi_period)
        avg_losses = _calculate_rma(losses, self.rsi_period)

        rsi = np.full(len(data), np.nan)
        for i in range(self.rsi_period - 1, len(avg_gains)):
            if avg_losses[i] == 0:
                rsi[i + 1] = 100.0
            else:
                rs = avg_gains[i] / avg_losses[i]
                rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        # Step 2: Apply Stochastic formula to RSI
        stoch_rsi = np.full(len(data), np.nan)
        for i in range(self.rsi_period + self.stoch_period - 2, len(rsi)):
            window = rsi[i - self.stoch_period + 1 : i + 1]
            valid_window = window[~np.isnan(window)]
            if len(valid_window) > 0:
                min_rsi = np.min(valid_window)
                max_rsi = np.max(valid_window)
                if max_rsi != min_rsi:
                    stoch_rsi[i] = (rsi[i] - min_rsi) / (max_rsi - min_rsi) * 100.0

        # Step 3: Smooth %K
        k = _calculate_sma(stoch_rsi, self.k_period)

        # Step 4: Calculate %D (SMA of %K)
        d = _calculate_sma(k, self.d_period)

        overbought = k > self.overbought_threshold
        oversold = k < self.oversold_threshold

        return StochRSIResult(
            k=k,
            d=d,
            overbought=overbought,
            oversold=oversold,
        )

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: StochRSIResult) -> Signal:
        """Convert StochRSI result to trading signal.

        Args:
            result: StochRSIResult from compute().

        Returns:
            Signal with BUY/SELL/HOLD direction based on %K overbought/oversold.
        """
        current_k = result.current_k
        if current_k is None:
            return Signal(
                direction=SignalDirection.HOLD,
                confidence=0.5,
                timestamp=datetime.now(UTC),
                metadata={},
            )

        if current_k > self.overbought_threshold:
            direction = SignalDirection.SELL
            confidence = min((current_k - self.overbought_threshold) / 20.0, 1.0)
        elif current_k < self.oversold_threshold:
            direction = SignalDirection.BUY
            confidence = min((self.oversold_threshold - current_k) / 20.0, 1.0)
        else:
            direction = SignalDirection.HOLD
            confidence = 0.5

        return Signal(
            direction=direction,
            confidence=confidence,
            timestamp=datetime.now(UTC),
            metadata={"stoch_rsi_k": current_k},
        )


class WilliamsR(BaseIndicator):
    """Williams %R indicator.

    Momentum oscillator that measures overbought/oversold levels.
    Range: -100 to 0 (similar to Stochastic but inverted).
    """

    def __init__(
        self,
        period: int = 14,
        overbought_threshold: float = -20.0,
        oversold_threshold: float = -80.0,
        name: str = "WilliamsR",
    ):
        super().__init__(name)
        self.period = period
        self.overbought_threshold = overbought_threshold
        self.oversold_threshold = oversold_threshold

    @property
    def description(self) -> str:
        return f"Williams %R ({self.period})"

    @property
    def parameters(self) -> dict:
        return {
            "period": self.period,
            "overbought_threshold": self.overbought_threshold,
            "oversold_threshold": self.oversold_threshold,
        }

    def validate(self, data: list) -> bool:
        return len(data) >= self.period

    def compute(self, data: list) -> WilliamsRResult:
        """Calculate Williams %R.

        Args:
            data: List of OHLCVData points (needs period minimum).

        Returns:
            WilliamsRResult with values, overbought, and oversold boolean arrays.

        Raises:
            ValueError: If insufficient data points.
        """
        if not self.validate(data):
            raise ValueError(f"Need {self.period} data points, got {len(data)}")

        highs = np.array([d.high_price for d in data])
        lows = np.array([d.low_price for d in data])
        closes = np.array([d.close_price for d in data])

        williams_r = np.full(len(data), np.nan)

        for i in range(self.period - 1, len(data)):
            highest_high = np.max(highs[i - self.period + 1 : i + 1])
            lowest_low = np.min(lows[i - self.period + 1 : i + 1])

            if highest_high != lowest_low:
                williams_r[i] = (
                    (highest_high - closes[i]) / (highest_high - lowest_low) * -100.0
                )

        overbought = williams_r > self.overbought_threshold
        oversold = williams_r < self.oversold_threshold

        return WilliamsRResult(
            values=williams_r,
            overbought=overbought,
            oversold=oversold,
        )

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: WilliamsRResult) -> Signal:
        """Convert Williams %R result to trading signal.

        Args:
            result: WilliamsRResult from compute().

        Returns:
            Signal with BUY/SELL/HOLD direction based on overbought/oversold.
            Note: Williams %R is inverted (-100 to 0), so overbought is near 0
            and oversold is near -100.
        """
        current = result.current
        if current is None:
            return Signal(
                direction=SignalDirection.HOLD,
                confidence=0.5,
                timestamp=datetime.now(UTC),
                metadata={},
            )

        # Williams %R is inverted: > -20 is overbought, < -80 is oversold
        if current > self.overbought_threshold:
            direction = SignalDirection.SELL
            confidence = min((current - self.overbought_threshold) / 20.0, 1.0)
        elif current < self.oversold_threshold:
            direction = SignalDirection.BUY
            confidence = min((self.oversold_threshold - current) / 20.0, 1.0)
        else:
            direction = SignalDirection.HOLD
            confidence = 0.5

        return Signal(
            direction=direction,
            confidence=confidence,
            timestamp=datetime.now(UTC),
            metadata={"williams_r": current},
        )


# ---------------------------------------------------------------------------
# Module-level helper functions (shared across indicators)
# ---------------------------------------------------------------------------


def _calculate_rma(values: np.ndarray, period: int) -> np.ndarray:
    """Calculate Running Moving Average (Wilder's smoothing).

    Args:
        values: Input array of values.
        period: Smoothing period.

    Returns:
        Array with RMA values (NaN before period is complete).
    """
    alpha = 1.0 / period
    result = np.full(len(values), np.nan)

    if len(values) < period:
        return result

    rma = float(np.mean(values[:period]))
    result[period - 1] = rma

    for i in range(period, len(values)):
        rma = alpha * values[i] + (1.0 - alpha) * rma
        result[i] = rma

    return result


def _calculate_sma(values: np.ndarray, period: int) -> np.ndarray:
    """Calculate Simple Moving Average ignoring NaN values.

    Args:
        values: Input array of values (may contain NaN).
        period: Window period.

    Returns:
        Array with SMA values (NaN where insufficient non-NaN data).
    """
    result = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        valid_window = window[~np.isnan(window)]
        if len(valid_window) > 0:
            result[i] = float(np.mean(valid_window))
    return result
