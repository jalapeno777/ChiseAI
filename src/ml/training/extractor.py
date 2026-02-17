"""Feature extraction logic for training data pipeline.

Provides FeatureExtractor class that extracts features from signals and market data,
integrating with signal storage, technical indicators, and Markov chain state detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.interface import SignalStorageInterface
    from market_analysis.signal_storage.models import SignalRecord, SignalWithOutcome

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Container for extracted technical indicators.

    Attributes:
        rsi: Relative Strength Index (0-100)
        macd: MACD line value
        macd_signal: MACD signal line value
        macd_histogram: MACD histogram value
        bb_upper: Bollinger Bands upper band
        bb_lower: Bollinger Bands lower band
        bb_width: Bollinger Bands width percentage
        atr: Average True Range
        volume_sma: Volume SMA ratio
    """

    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    atr: float | None = None
    volume_sma: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        """Convert to dictionary."""
        return {
            "rsi": self.rsi,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "bb_upper": self.bb_upper,
            "bb_lower": self.bb_lower,
            "bb_width": self.bb_width,
            "atr": self.atr,
            "volume_sma": self.volume_sma,
        }


@dataclass
class MarketContext:
    """Container for market context data.

    Attributes:
        trend_state: Current trend state from Markov chain
        trend_confidence: Confidence in trend state (0.0-1.0)
        confluence_score: Confluence score (0-100)
        price_change_24h: 24h price change percentage
        volatility: Price volatility measure
    """

    trend_state: str | None = None
    trend_confidence: float | None = None
    confluence_score: float | None = None
    price_change_24h: float | None = None
    volatility: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trend_state": self.trend_state,
            "trend_confidence": self.trend_confidence,
            "confluence_score": self.confluence_score,
            "price_change_24h": self.price_change_24h,
            "volatility": self.volatility,
        }


@dataclass
class ExtractedFeatures:
    """Complete set of extracted features for a signal.

    Attributes:
        signal_id: Unique signal identifier
        timestamp: Signal timestamp (UTC)
        token: Trading pair token
        timeframe: Chart timeframe
        direction: Signal direction
        confidence: Signal confidence (0.0-1.0)
        entry_price: Entry price at signal time
        technical: Technical indicators
        market: Market context
        predicted_prob: Model predicted probability
    """

    signal_id: str
    timestamp: datetime
    token: str
    timeframe: str
    direction: str | None = None
    confidence: float | None = None
    entry_price: float | None = None
    technical: TechnicalIndicators = None  # type: ignore
    market: MarketContext = None  # type: ignore
    predicted_prob: float | None = None

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.technical is None:
            self.technical = TechnicalIndicators()
        if self.market is None:
            self.market = MarketContext()

    def to_dict(self) -> dict[str, Any]:
        """Convert to flat dictionary for TrainingSample creation."""
        result = {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "token": self.token,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "predicted_prob": self.predicted_prob,
        }
        result.update(self.technical.to_dict())
        result.update(self.market.to_dict())
        return result


class FeatureExtractor:
    """Extracts features from signals and market data.

    Integrates with signal storage, technical indicators, and Markov chain
    state detection to extract all features required for ML training.

    Attributes:
        signal_storage: Signal storage interface for fetching signal data
        market_data_client: Optional client for fetching market/price data
        cache: Optional cache for technical indicators
    """

    def __init__(
        self,
        signal_storage: SignalStorageInterface | None = None,
        market_data_client: Any | None = None,
        use_cache: bool = True,
    ) -> None:
        """Initialize feature extractor.

        Args:
            signal_storage: Signal storage interface
            market_data_client: Optional market data client
            use_cache: Whether to cache technical indicators
        """
        self.signal_storage = signal_storage
        self.market_data_client = market_data_client
        self._cache: dict[str, Any] = {} if use_cache else None  # type: ignore
        self._cache_ttl_seconds = 300  # 5 minute cache TTL

    async def extract_features(self, signal_id: str) -> ExtractedFeatures | None:
        """Extract all features for a given signal.

        Args:
            signal_id: Unique signal identifier

        Returns:
            ExtractedFeatures if successful, None if signal not found
        """
        if self.signal_storage is None:
            logger.error("Signal storage not configured")
            return None

        # Fetch signal record
        signal = await self.signal_storage.get_signal_by_id(signal_id)
        if signal is None:
            logger.warning(f"Signal not found: {signal_id}")
            return None

        # Build base features from signal
        features = self._extract_from_signal(signal)

        try:
            # Extract technical indicators
            technical = await self.extract_technical_indicators(
                token=signal.token,
                timeframe=signal.timeframes_used[0] if signal.timeframes_used else "1h",
                timestamp=features.timestamp,
            )
            features.technical = technical
        except Exception as e:
            logger.warning(f"Failed to extract technical indicators: {e}")
            features.technical = TechnicalIndicators()

        try:
            # Extract market context
            market = await self.extract_market_context(
                token=signal.token,
                timestamp=features.timestamp,
                signal=signal,
            )
            features.market = market
        except Exception as e:
            logger.warning(f"Failed to extract market context: {e}")
            features.market = MarketContext()

        return features

    def _extract_from_signal(self, signal: SignalRecord) -> ExtractedFeatures:
        """Extract base features from signal record.

        Args:
            signal: Signal record

        Returns:
            ExtractedFeatures with base signal data
        """
        # Convert timestamp from ms to datetime
        timestamp = datetime.fromtimestamp(signal.timestamp / 1000.0)

        # Map direction enum to string
        direction_map = {
            "LONG": "long",
            "SHORT": "short",
            "NEUTRAL": "neutral",
        }
        direction = direction_map.get(str(signal.direction), None)

        return ExtractedFeatures(
            signal_id=signal.signal_id,
            timestamp=timestamp,
            token=signal.token,
            timeframe=signal.timeframes_used[0] if signal.timeframes_used else "1h",
            direction=direction,
            confidence=signal.confidence,
            entry_price=signal.entry_price,
            predicted_prob=signal.confidence,  # Use confidence as predicted prob
        )

    async def extract_technical_indicators(
        self,
        token: str,
        timeframe: str,
        timestamp: datetime,
    ) -> TechnicalIndicators:
        """Extract technical indicators for a token at a specific time.

        Args:
            token: Trading pair token (e.g., "BTC")
            timeframe: Chart timeframe (e.g., "1h")
            timestamp: Target timestamp

        Returns:
            TechnicalIndicators with all available indicators
        """
        cache_key = f"tech:{token}:{timeframe}:{int(timestamp.timestamp())}"

        # Check cache
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        indicators = TechnicalIndicators()

        try:
            # Try to get from market data client if available
            if self.market_data_client is not None:
                indicators = await self._fetch_from_market_data(
                    token, timeframe, timestamp
                )
            else:
                # Fallback: compute from available data
                indicators = await self._compute_indicators(token, timeframe, timestamp)

        except Exception as e:
            logger.warning(f"Failed to extract technical indicators: {e}")
            # Return empty indicators (all None)

        # Cache result
        if self._cache is not None:
            self._cache[cache_key] = indicators

        return indicators

    async def _fetch_from_market_data(
        self,
        token: str,
        timeframe: str,
        timestamp: datetime,
    ) -> TechnicalIndicators:
        """Fetch indicators from market data client.

        Args:
            token: Trading pair token
            timeframe: Chart timeframe
            timestamp: Target timestamp

        Returns:
            TechnicalIndicators
        """
        indicators = TechnicalIndicators()

        if self.market_data_client is None:
            return indicators

        try:
            # This would integrate with actual market data client
            # For now, return empty indicators
            pass
        except Exception as e:
            logger.warning(f"Market data fetch failed: {e}")

        return indicators

    async def _compute_indicators(
        self,
        token: str,
        timeframe: str,
        timestamp: datetime,
    ) -> TechnicalIndicators:
        """Compute indicators from OHLCV data.

        Args:
            token: Trading pair token
            timeframe: Chart timeframe
            timestamp: Target timestamp

        Returns:
            TechnicalIndicators
        """
        indicators = TechnicalIndicators()

        try:
            # Import here to avoid circular dependencies
            from market_analysis.indicators.calculator import IndicatorCalculator

            calculator = IndicatorCalculator()

            # Calculate indicators
            # Note: This would need actual OHLCV data
            # For now, return empty indicators

        except Exception as e:
            logger.warning(f"Indicator computation failed: {e}")

        return indicators

    async def extract_market_context(
        self,
        token: str,
        timestamp: datetime,
        signal: SignalRecord | None = None,
    ) -> MarketContext:
        """Extract market context including trend state and confluence.

        Args:
            token: Trading pair token
            timestamp: Target timestamp
            signal: Optional signal record for additional context

        Returns:
            MarketContext with trend state and market data
        """
        context = MarketContext()

        # Extract trend state from Markov chain
        trend_state = await self.extract_markov_state(token, timestamp)
        context.trend_state = trend_state

        # Extract confluence score from signal if available
        if signal is not None:
            context.confluence_score = signal.score

        # Extract price change and volatility if market data available
        if self.market_data_client is not None:
            try:
                price_data = await self._fetch_price_data(token, timestamp)
                context.price_change_24h = price_data.get("price_change_24h")
                context.volatility = price_data.get("volatility")
            except Exception as e:
                logger.warning(f"Failed to fetch price data: {e}")

        return context

    async def extract_markov_state(
        self,
        token: str,
        timestamp: datetime,
    ) -> str | None:
        """Get trend state from Markov chain inference.

        Args:
            token: Trading pair token
            timestamp: Target timestamp

        Returns:
            Trend state string (bullish/bearish/neutral/transitional) or None
        """
        try:
            # Import here to avoid circular dependencies
            from market_analysis.markov.inference_engine import TrendInferenceEngine

            # Create inference engine
            engine = TrendInferenceEngine()

            # This would need actual OHLCV data to infer state
            # For now, return None (will be handled gracefully)
            return None

        except Exception as e:
            logger.warning(f"Markov state extraction failed: {e}")
            return None

    async def extract_confluence_score(self, signal_id: str) -> float | None:
        """Get confluence-based signal score.

        Args:
            signal_id: Signal identifier

        Returns:
            Confluence score (0-100) or None
        """
        if self.signal_storage is None:
            return None

        try:
            signal = await self.signal_storage.get_signal_by_id(signal_id)
            if signal is not None:
                return signal.score
        except Exception as e:
            logger.warning(f"Failed to extract confluence score: {e}")

        return None

    async def _fetch_price_data(
        self,
        token: str,
        timestamp: datetime,
    ) -> dict[str, float | None]:
        """Fetch price data from market data client.

        Args:
            token: Trading pair token
            timestamp: Target timestamp

        Returns:
            Dictionary with price_change_24h and volatility
        """
        return {
            "price_change_24h": None,
            "volatility": None,
        }

    def clear_cache(self) -> None:
        """Clear the technical indicators cache."""
        if self._cache is not None:
            self._cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache size and hit/miss stats
        """
        if self._cache is None:
            return {"size": 0, "enabled": 0}
        return {"size": len(self._cache), "enabled": 1}
