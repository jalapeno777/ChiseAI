"""Inference engine for trend state detection from price data.

Analyzes OHLCV data and technical indicators to classify market state
as bullish, bearish, neutral, or transitional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from data_ingestion.ohlcv_fetcher import OHLCVData

from market_analysis.markov.state_model import TrendState

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Container for calculated technical indicators.

    Attributes:
        rsi: Relative Strength Index (0-100)
        macd_line: MACD line value
        macd_signal: MACD signal line value
        macd_histogram: MACD histogram (macd_line - macd_signal)
        sma_short: Short-term simple moving average
        sma_long: Long-term simple moving average
        volatility: Price volatility (standard deviation of returns)
        volume_sma: Volume simple moving average
        price_change_pct: Price change percentage over window
    """

    rsi: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    sma_short: float | None = None
    sma_long: float | None = None
    volatility: float | None = None
    volume_sma: float | None = None
    price_change_pct: float | None = None

    @property
    def macd_bullish(self) -> bool | None:
        """Check if MACD shows bullish crossover."""
        if self.macd_line is None or self.macd_signal is None:
            return None
        return self.macd_line > self.macd_signal

    @property
    def macd_bearish(self) -> bool | None:
        """Check if MACD shows bearish crossover."""
        if self.macd_line is None or self.macd_signal is None:
            return None
        return self.macd_line < self.macd_signal

    @property
    def price_above_sma(self) -> bool | None:
        """Check if price is above short-term SMA."""
        if self.sma_short is None:
            return None
        # This will be compared with current price externally
        return None


@dataclass
class InferenceResult:
    """Result of trend state inference.

    Attributes:
        state: The inferred trend state
        confidence: Confidence score (0.0-1.0)
        indicators: Calculated technical indicators
        timestamp: Timestamp of the inference (ms)
        price_change_pct: Price change percentage
        volume_trend: Volume trend indicator
        signal_strength: Overall signal strength score
    """

    state: TrendState
    confidence: float
    indicators: TechnicalIndicators
    timestamp: int
    price_change_pct: float
    volume_trend: float
    signal_strength: float

    def is_high_confidence(self, threshold: float = 0.7) -> bool:
        """Check if inference meets confidence threshold."""
        return self.confidence >= threshold


class TrendInferenceEngine:
    """Engine for inferring trend states from OHLCV data.

    Analyzes price action, volume, and technical indicators to classify
    market state into one of four categories: bullish, bearish, neutral,
    or transitional.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        sma_short_period: int = 20,
        sma_long_period: int = 50,
        volatility_period: int = 20,
        volume_period: int = 20,
        rsi_bullish_threshold: float = 55.0,
        rsi_bearish_threshold: float = 45.0,
        volatility_threshold: float = 0.02,
    ):
        """Initialize inference engine.

        Args:
            rsi_period: Period for RSI calculation
            macd_fast: Fast EMA period for MACD
            macd_slow: Slow EMA period for MACD
            macd_signal: Signal line period for MACD
            sma_short_period: Short-term SMA period
            sma_long_period: Long-term SMA period
            volatility_period: Period for volatility calculation
            volume_period: Period for volume SMA
            rsi_bullish_threshold: RSI level above which is bullish
            rsi_bearish_threshold: RSI level below which is bearish
            volatility_threshold: Volatility threshold for transitional state
        """
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.sma_short_period = sma_short_period
        self.sma_long_period = sma_long_period
        self.volatility_period = volatility_period
        self.volume_period = volume_period
        self.rsi_bullish_threshold = rsi_bullish_threshold
        self.rsi_bearish_threshold = rsi_bearish_threshold
        self.volatility_threshold = volatility_threshold

    def infer_state(
        self,
        ohlcv_data: Sequence[OHLCVData],
        current_timestamp: int | None = None,
    ) -> InferenceResult:
        """Infer trend state from OHLCV data.

        Args:
            ohlcv_data: Sequence of OHLCV candles
            current_timestamp: Optional timestamp for the inference

        Returns:
            InferenceResult with state classification and confidence
        """
        if not ohlcv_data:
            raise ValueError("OHLCV data cannot be empty")

        # Calculate indicators
        indicators = self._calculate_indicators(ohlcv_data)

        # Get current price and timestamp
        current_candle = ohlcv_data[-1]
        current_price = current_candle.close_price
        timestamp = current_timestamp or current_candle.timestamp

        # Calculate price change over the window
        if len(ohlcv_data) >= 2:
            first_price = ohlcv_data[0].open_price
            price_change_pct = (current_price - first_price) / first_price
        else:
            price_change_pct = 0.0

        # Calculate volume trend
        volume_trend = self._calculate_volume_trend(ohlcv_data)

        # Classify state based on indicators
        state, confidence, signal_strength = self._classify_state(
            current_price, indicators, price_change_pct, volume_trend
        )

        return InferenceResult(
            state=state,
            confidence=confidence,
            indicators=indicators,
            timestamp=timestamp,
            price_change_pct=price_change_pct,
            volume_trend=volume_trend,
            signal_strength=signal_strength,
        )

    def _calculate_indicators(
        self, ohlcv_data: Sequence[OHLCVData]
    ) -> TechnicalIndicators:
        """Calculate technical indicators from OHLCV data.

        Args:
            ohlcv_data: Sequence of OHLCV candles

        Returns:
            TechnicalIndicators with calculated values
        """
        closes = [c.close_price for c in ohlcv_data]
        volumes = [c.volume for c in ohlcv_data]

        indicators = TechnicalIndicators()

        # Calculate RSI
        if len(closes) >= self.rsi_period + 1:
            indicators.rsi = self._calculate_rsi(closes)

        # Calculate MACD
        if len(closes) >= self.macd_slow + self.macd_signal:
            macd_line, macd_signal, macd_hist = self._calculate_macd(closes)
            indicators.macd_line = macd_line
            indicators.macd_signal = macd_signal
            indicators.macd_histogram = macd_hist

        # Calculate SMAs
        if len(closes) >= self.sma_short_period:
            indicators.sma_short = self._calculate_sma(closes, self.sma_short_period)

        if len(closes) >= self.sma_long_period:
            indicators.sma_long = self._calculate_sma(closes, self.sma_long_period)

        # Calculate volatility
        if len(closes) >= self.volatility_period + 1:
            indicators.volatility = self._calculate_volatility(closes)

        # Calculate volume SMA
        if len(volumes) >= self.volume_period:
            indicators.volume_sma = self._calculate_sma(volumes, self.volume_period)

        # Price change percentage
        if len(closes) >= 2:
            indicators.price_change_pct = (closes[-1] - closes[0]) / closes[0]

        return indicators

    def _calculate_rsi(self, prices: list[float]) -> float:
        """Calculate RSI (Relative Strength Index).

        Args:
            prices: List of closing prices

        Returns:
            RSI value (0-100)
        """
        if len(prices) < self.rsi_period + 1:
            return 50.0  # Neutral default

        # Calculate price changes
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        # Get gains and losses
        gains = [max(0, d) for d in deltas[-self.rsi_period :]]
        losses = [abs(min(0, d)) for d in deltas[-self.rsi_period :]]

        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(self, prices: list[float]) -> tuple[float, float, float]:
        """Calculate MACD indicator.

        Args:
            prices: List of closing prices

        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        # Calculate EMAs
        ema_fast = self._calculate_ema(prices, self.macd_fast)
        ema_slow = self._calculate_ema(prices, self.macd_slow)

        # MACD line
        macd_line = ema_fast - ema_slow

        # Signal line (EMA of MACD line)
        # We need historical MACD values, approximate with current
        macd_values = [macd_line] * self.macd_signal
        signal_line = sum(macd_values) / len(macd_values)

        # For a more accurate signal line, we'd need historical MACD values
        # This is a simplified calculation

        # Histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _calculate_ema(self, prices: list[float], period: int) -> float:
        """Calculate Exponential Moving Average.

        Args:
            prices: List of prices
            period: EMA period

        Returns:
            EMA value
        """
        if len(prices) < period:
            return prices[-1] if prices else 0.0

        # Use most recent 'period' prices
        recent_prices = prices[-period:]

        multiplier = 2 / (period + 1)
        ema = recent_prices[0]

        for price in recent_prices[1:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_sma(self, values: list[float], period: int) -> float:
        """Calculate Simple Moving Average.

        Args:
            values: List of values
            period: SMA period

        Returns:
            SMA value
        """
        if len(values) < period:
            return sum(values) / len(values) if values else 0.0

        recent = values[-period:]
        return sum(recent) / period

    def _calculate_volatility(self, prices: list[float]) -> float:
        """Calculate price volatility (standard deviation of returns).

        Args:
            prices: List of closing prices

        Returns:
            Volatility as standard deviation of returns
        """
        if len(prices) < 2:
            return 0.0

        # Calculate returns
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]

        # Use recent returns
        recent_returns = returns[-self.volatility_period :]

        if not recent_returns:
            return 0.0

        mean_return = sum(recent_returns) / len(recent_returns)
        variance = sum((r - mean_return) ** 2 for r in recent_returns) / len(
            recent_returns
        )

        return float(variance**0.5)

    def _calculate_volume_trend(self, ohlcv_data: Sequence[OHLCVData]) -> float:
        """Calculate volume trend indicator.

        Args:
            ohlcv_data: Sequence of OHLCV candles

        Returns:
            Volume trend score (-1.0 to 1.0)
        """
        if len(ohlcv_data) < 2:
            return 0.0

        volumes = [c.volume for c in ohlcv_data]
        mid = len(volumes) // 2

        recent_avg = sum(volumes[mid:]) / len(volumes[mid:]) if volumes[mid:] else 0
        earlier_avg = sum(volumes[:mid]) / len(volumes[:mid]) if volumes[:mid] else 0

        if earlier_avg == 0:
            return 0.0

        trend = (recent_avg - earlier_avg) / earlier_avg
        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, trend))

    def _classify_state(
        self,
        current_price: float,
        indicators: TechnicalIndicators,
        price_change_pct: float,
        volume_trend: float,
    ) -> tuple[TrendState, float, float]:
        """Classify market state based on indicators.

        Args:
            current_price: Current price
            indicators: Calculated technical indicators
            price_change_pct: Price change percentage
            volume_trend: Volume trend indicator

        Returns:
            Tuple of (state, confidence, signal_strength)
        """
        # Initialize scores for each state
        bullish_score = 0.0
        bearish_score = 0.0
        neutral_score = 0.0
        transitional_score = 0.0

        # RSI analysis
        if indicators.rsi is not None:
            if indicators.rsi > self.rsi_bullish_threshold:
                bullish_score += 0.25
            elif indicators.rsi < self.rsi_bearish_threshold:
                bearish_score += 0.25
            else:
                neutral_score += 0.25

        # MACD analysis
        if indicators.macd_bullish:
            bullish_score += 0.25
        elif indicators.macd_bearish:
            bearish_score += 0.25

        # Price trend analysis
        if price_change_pct > 0.01:  # > 1% up
            bullish_score += 0.2
            if volume_trend > 0:
                bullish_score += 0.1  # Volume confirming
        elif price_change_pct < -0.01:  # > 1% down
            bearish_score += 0.2
            if volume_trend > 0:
                bearish_score += 0.1  # Volume confirming
        else:
            neutral_score += 0.2

        # SMA analysis
        if indicators.sma_short is not None and indicators.sma_long is not None:
            if current_price > indicators.sma_short > indicators.sma_long:
                bullish_score += 0.2
            elif current_price < indicators.sma_short < indicators.sma_long:
                bearish_score += 0.2
            elif (
                abs(current_price - indicators.sma_short) / current_price < 0.005
                and abs(indicators.sma_short - indicators.sma_long)
                / indicators.sma_long
                < 0.005
            ):
                neutral_score += 0.2

        # Volatility analysis for transitional state
        if (
            indicators.volatility is not None
            and indicators.volatility > self.volatility_threshold
        ):
            transitional_score += 0.3
            # High volatility reduces confidence in trend signals
            bullish_score *= 0.7
            bearish_score *= 0.7
            neutral_score *= 0.7

        # Check for conflicting signals (transitional)
        if bullish_score > 0.3 and bearish_score > 0.3:
            transitional_score += 0.3
            bullish_score *= 0.5
            bearish_score *= 0.5

        # Determine state
        scores = {
            TrendState.BULLISH: bullish_score,
            TrendState.BEARISH: bearish_score,
            TrendState.NEUTRAL: neutral_score,
            TrendState.TRANSITIONAL: transitional_score,
        }

        max_state = max(scores.items(), key=lambda x: x[1])[0]
        max_score = scores[max_state]

        # Calculate confidence based on score dominance
        sorted_scores = sorted(scores.values(), reverse=True)
        if sorted_scores[0] > 0:
            confidence = sorted_scores[0] / (sorted_scores[0] + sorted_scores[1] * 0.5)
            confidence = min(1.0, confidence)
        else:
            confidence = 0.5

        # Signal strength is the raw score
        signal_strength = max_score

        return max_state, confidence, signal_strength
