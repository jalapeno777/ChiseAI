"""Bollinger Bands indicator implementation.

Bollinger Bands are a volatility-based indicator that consists of a middle
band (SMA) and two outer bands (standard deviations from the middle band).
They help identify overbought/oversold conditions and volatility changes.

Repainting safeguards:
    - Uses only historical data (no lookahead)
    - SMA and rolling std are causal calculations
    - %B calculation uses only current and past prices
    - Validated by RepaintingDetector with 0% tolerance
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.safety import check_indicator


@dataclass
class BollingerBandsResult:
    """Result of Bollinger Bands calculation.

    Attributes:
        middle_band: Array of middle band (SMA) values
        upper_band: Array of upper band values
        lower_band: Array of lower band values
        band_width: Array of band width values (upper - lower)
        percent_b: Array of %B values (price position within bands)
        timestamps: Array of corresponding timestamps
    """

    middle_band: np.ndarray
    upper_band: np.ndarray
    lower_band: np.ndarray
    band_width: np.ndarray
    percent_b: np.ndarray
    timestamps: np.ndarray

    @property
    def current_middle(self) -> float | None:
        """Get the most recent middle band value."""
        if len(self.middle_band) > 0:
            return float(self.middle_band[-1])
        return None

    @property
    def current_upper(self) -> float | None:
        """Get the most recent upper band value."""
        if len(self.upper_band) > 0:
            return float(self.upper_band[-1])
        return None

    @property
    def current_lower(self) -> float | None:
        """Get the most recent lower band value."""
        if len(self.lower_band) > 0:
            return float(self.lower_band[-1])
        return None

    @property
    def current_band_width(self) -> float | None:
        """Get the most recent band width value."""
        if len(self.band_width) > 0:
            return float(self.band_width[-1])
        return None

    @property
    def current_percent_b(self) -> float | None:
        """Get the most recent %B value."""
        if len(self.percent_b) > 0:
            return float(self.percent_b[-1])
        return None


class BollingerBands:
    """Bollinger Bands calculator.

    Standard parameters:
        - Period: 20
        - Standard deviations: 2

    Middle Band = SMA(close, period)
    Upper Band = Middle Band + (std_dev * standard deviations)
    Lower Band = Middle Band - (std_dev * standard deviations)
    Band Width = Upper Band - Lower Band
    %B = (close - Lower Band) / (Upper Band - Lower Band)

    Reference:
        John Bollinger, "Bollinger on Bollinger Bands" (2001)
    """

    def __init__(
        self,
        period: int = 20,
        num_std_dev: float = 2.0,
    ):
        """Initialize Bollinger Bands calculator.

        Args:
            period: SMA period (default: 20)
            num_std_dev: Number of standard deviations (default: 2.0)

        Raises:
            ValueError: If period is less than 2 or num_std_dev is not positive
        """
        if period < 2:
            raise ValueError("Period must be at least 2")
        if num_std_dev <= 0:
            raise ValueError("Number of standard deviations must be positive")

        self.period = period
        self.num_std_dev = num_std_dev

    def calculate(self, data: list[OHLCVData]) -> BollingerBandsResult:
        """Calculate Bollinger Bands from OHLCV data.

        Args:
            data: List of OHLCV data points

        Returns:
            BollingerBandsResult containing all band values and metrics

        Raises:
            ValueError: If insufficient data points for calculation
        """
        if len(data) < self.period:
            raise ValueError(
                f"Bollinger Bands require at least {self.period} data points, "
                f"got {len(data)}"
            )

        # Extract close prices
        closes = np.array([d.close_price for d in data])
        timestamps = np.array([d.timestamp for d in data])

        # Calculate middle band (SMA)
        middle_band = self._calculate_sma(closes, self.period)

        # Calculate standard deviation
        std_dev = self._calculate_rolling_std(closes, self.period)

        # Calculate upper and lower bands
        upper_band = middle_band + (self.num_std_dev * std_dev)
        lower_band = middle_band - (self.num_std_dev * std_dev)

        # Calculate band width
        band_width = upper_band - lower_band

        # Calculate %B (percent bandwidth)
        percent_b = self._calculate_percent_b(closes, upper_band, lower_band)

        return BollingerBandsResult(
            middle_band=middle_band,
            upper_band=upper_band,
            lower_band=lower_band,
            band_width=band_width,
            percent_b=percent_b,
            timestamps=timestamps,
        )

    def _calculate_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Simple Moving Average.

        Args:
            data: Input data array
            period: SMA period

        Returns:
            Array of SMA values (NaN for first period-1 values)
        """
        sma = np.full(len(data), np.nan)

        for i in range(period - 1, len(data)):
            sma[i] = np.mean(data[i - period + 1 : i + 1])

        return sma

    def _calculate_rolling_std(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate rolling standard deviation.

        Args:
            data: Input data array
            period: Rolling window period

        Returns:
            Array of standard deviation values (NaN for first period-1 values)
        """
        std = np.full(len(data), np.nan)

        for i in range(period - 1, len(data)):
            window = data[i - period + 1 : i + 1]
            std[i] = np.std(window, ddof=1)  # Sample standard deviation

        return std

    def _calculate_percent_b(
        self,
        closes: np.ndarray,
        upper_band: np.ndarray,
        lower_band: np.ndarray,
    ) -> np.ndarray:
        """Calculate %B (percent bandwidth).

        %B = (close - lower) / (upper - lower)

        Values:
            - %B > 1: Price above upper band
            - %B = 1: Price at upper band
            - %B = 0.5: Price at middle band
            - %B = 0: Price at lower band
            - %B < 0: Price below lower band

        Args:
            closes: Array of close prices
            upper_band: Array of upper band values
            lower_band: Array of lower band values

        Returns:
            Array of %B values
        """
        band_width = upper_band - lower_band

        # Avoid division by zero
        percent_b = np.full(len(closes), np.nan)
        valid_mask = ~np.isnan(band_width) & (band_width > 0)

        percent_b[valid_mask] = (
            closes[valid_mask] - lower_band[valid_mask]
        ) / band_width[valid_mask]

        # Handle cases where band_width is 0 (flat prices)
        zero_width_mask = ~np.isnan(band_width) & (band_width == 0)
        percent_b[zero_width_mask] = 0.5  # Price is at middle when bands are flat

        return percent_b

    def calculate_from_prices(
        self, prices: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands directly from price array.

        Args:
            prices: Array of price values

        Returns:
            Tuple of (middle_band, upper_band, lower_band, band_width) arrays
        """
        if len(prices) < self.period:
            raise ValueError(
                f"Bollinger Bands require at least {self.period} prices, "
                f"got {len(prices)}"
            )

        # Calculate middle band
        middle_band = self._calculate_sma(prices, self.period)

        # Calculate standard deviation
        std_dev = self._calculate_rolling_std(prices, self.period)

        # Calculate bands
        upper_band = middle_band + (self.num_std_dev * std_dev)
        lower_band = middle_band - (self.num_std_dev * std_dev)

        # Calculate band width
        band_width = upper_band - lower_band

        return middle_band, upper_band, lower_band, band_width

    def is_price_near_upper(self, percent_b: float, threshold: float = 0.95) -> bool:
        """Check if price is near the upper band.

        Args:
            percent_b: Current %B value
            threshold: Threshold for "near upper" (default: 0.95)

        Returns:
            True if price is near or above upper band
        """
        return percent_b >= threshold

    def is_price_near_lower(self, percent_b: float, threshold: float = 0.05) -> bool:
        """Check if price is near the lower band.

        Args:
            percent_b: Current %B value
            threshold: Threshold for "near lower" (default: 0.05)

        Returns:
            True if price is near or below lower band
        """
        return percent_b <= threshold
