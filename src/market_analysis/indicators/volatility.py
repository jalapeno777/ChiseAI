"""Volatility indicators including ATR and ATR-based volatility bands.

ATR (Average True Range) measures market volatility by decomposing the entire
range of an asset price for a given period. ATR-based volatility bands provide
trailing stop levels that adapt to market volatility.

Reference:
    J. Welles Wilder Jr., "New Concepts in Technical Trading Systems" (1978)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.base import (
    BaseIndicator,
    Signal,
    SignalDirection,
)


@dataclass
class ATRResult:
    """Result of ATR calculation with volatility bands.

    Attributes:
        atr: Average True Range values (NaN for initial period)
        upper_band: Upper volatility band (close + ATR * multiplier)
        lower_band: Lower volatility band (close - ATR * multiplier)
        trailing_stop: ATR-based trailing stop level
    """

    atr: np.ndarray
    upper_band: np.ndarray
    lower_band: np.ndarray
    trailing_stop: np.ndarray

    @property
    def current_atr(self) -> float | None:
        """Get the most recent ATR value."""
        valid = self.atr[~np.isnan(self.atr)]
        return float(valid[-1]) if len(valid) > 0 else None

    @property
    def current_trailing_stop(self) -> float | None:
        """Get the most recent trailing stop level."""
        valid = self.trailing_stop[~np.isnan(self.trailing_stop)]
        return float(valid[-1]) if len(valid) > 0 else None

    @property
    def current_upper_band(self) -> float | None:
        """Get the most recent upper band value."""
        valid = self.upper_band[~np.isnan(self.upper_band)]
        return float(valid[-1]) if len(valid) > 0 else None

    @property
    def current_lower_band(self) -> float | None:
        """Get the most recent lower band value."""
        valid = self.lower_band[~np.isnan(self.lower_band)]
        return float(valid[-1]) if len(valid) > 0 else None


class ATR(BaseIndicator[ATRResult]):
    """Average True Range indicator with volatility bands and trailing stop.

    ATR measures market volatility by decomposing the entire range of an
    asset price for a given period. The trailing stop ratchets upward in
    an uptrend and stays flat when price pulls back.

    Args:
        period: Lookback period for ATR calculation (default 14).
        multiplier: Band/trailing-stop multiplier (default 2.0).
        name: Indicator name used in the plugin registry.
    """

    def __init__(
        self,
        period: int = 14,
        multiplier: float = 2.0,
        name: str = "ATR",
    ) -> None:
        if period < 2:
            raise ValueError("period must be at least 2")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")

        super().__init__(name)
        self.period = period
        self.multiplier = multiplier

    @property
    def description(self) -> str:
        return f"Average True Range ({self.period}) with {self.multiplier}x volatility bands"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"period": self.period, "multiplier": self.multiplier}

    def validate(self, data: list[OHLCVData]) -> bool:
        """Return True when enough data points exist for ATR computation."""
        return len(data) >= self.period + 1

    def compute(self, data: list[OHLCVData]) -> ATRResult:
        """Calculate ATR, volatility bands, and trailing stop.

        Args:
            data: List of OHLCV data points (minimum ``period + 1``).

        Returns:
            ATRResult containing ATR, bands, and trailing stop arrays
            aligned to the input data length.

        Raises:
            ValueError: If insufficient data for the configured period.
        """
        if not self.validate(data):
            raise ValueError(
                f"Need {self.period + 1} data points for ATR({self.period}), "
                f"got {len(data)}"
            )

        highs = np.array([d.high_price for d in data], dtype=np.float64)
        lows = np.array([d.low_price for d in data], dtype=np.float64)
        closes = np.array([d.close_price for d in data], dtype=np.float64)

        # --- True Range ---
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        true_range = np.maximum(np.maximum(tr1, tr2), tr3)

        # --- Wilder's RMA of True Range ---
        atr_rma = self._calculate_rma(true_range, self.period)

        # Pad to align with input data length.
        # atr_rma has len(data)-1 entries; valid values start at index period-1
        # which corresponds to data index period.
        atr_padded = np.full(len(data), np.nan, dtype=np.float64)
        atr_padded[self.period :] = atr_rma[self.period - 1 :]

        # --- Volatility Bands ---
        upper_band = closes + atr_padded * self.multiplier
        lower_band = closes - atr_padded * self.multiplier

        # --- Trailing Stop ---
        trailing_stop = self._calculate_trailing_stop(closes, atr_padded)

        return ATRResult(
            atr=atr_padded,
            upper_band=upper_band,
            lower_band=lower_band,
            trailing_stop=trailing_stop,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_rma(values: np.ndarray, period: int) -> np.ndarray:
        """Running Moving Average (Wilder's smoothing).

        The first valid value is the simple average of the first *period*
        values. Subsequent values use exponential smoothing with
        ``alpha = 1 / period``.

        Args:
            values: Input array.
            period: Smoothing period.

        Returns:
            Array of the same length as *values*; NaN before index
            ``period - 1``.
        """
        alpha = 1.0 / period
        result = np.full(len(values), np.nan, dtype=np.float64)

        if len(values) < period:
            return result

        # Seed with SMA of first `period` values
        rma = float(np.mean(values[:period]))
        result[period - 1] = rma

        for i in range(period, len(values)):
            rma = alpha * values[i] + (1.0 - alpha) * rma
            result[i] = rma

        return result

    def _calculate_trailing_stop(
        self,
        closes: np.ndarray,
        atr: np.ndarray,
    ) -> np.ndarray:
        """ATR-based trailing stop (long-only ratchet).

        The stop is initialised at ``close[period] - atr[period] * multiplier``
        and only ever moves *up* — it stays flat when price pulls back.

        Args:
            closes: Close price array (same length as input data).
            atr: Padded ATR array (NaN before index ``period``).

        Returns:
            Array of trailing-stop levels; NaN before index ``period``.
        """
        n = len(closes)
        trailing_stop = np.full(n, np.nan, dtype=np.float64)

        # Initialise at the first valid ATR index
        trailing_stop[self.period] = (
            closes[self.period] - atr[self.period] * self.multiplier
        )

        for i in range(self.period + 1, n):
            new_stop = closes[i] - atr[i] * self.multiplier
            trailing_stop[i] = max(new_stop, trailing_stop[i - 1])

        return trailing_stop

    # ------------------------------------------------------------------
    # BaseIndicator interface
    # ------------------------------------------------------------------

    def get_metadata(self) -> dict[str, Any]:
        """Return indicator metadata for serialisation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: ATRResult) -> Signal:
        """Convert ATR result to a standardised Signal.

        Higher ATR → higher volatility → lower confidence (cautious stance).
        The direction is always HOLD because ATR is a volatility measure,
        not directional.

        Args:
            result: ATR computation result.

        Returns:
            Signal with confidence inversely proportional to ATR.
        """
        current_atr = result.current_atr
        if current_atr is None:
            return Signal(
                direction=SignalDirection.HOLD,
                confidence=0.5,
                timestamp=datetime.utcnow(),
                metadata={"atr": None, "reason": "insufficient_data"},
            )

        # Inverse relationship: low ATR → high confidence, high ATR → low confidence
        # ATR of 0  → confidence 1.0
        # ATR of 10+ → confidence 0.3 (floor)
        confidence = max(0.3, 1.0 - min(current_atr / 10.0, 0.7))

        return Signal(
            direction=SignalDirection.HOLD,
            confidence=confidence,
            timestamp=datetime.utcnow(),
            metadata={
                "atr": round(current_atr, 6),
                "trailing_stop": (
                    round(result.current_trailing_stop, 6)
                    if result.current_trailing_stop is not None
                    else None
                ),
            },
        )
