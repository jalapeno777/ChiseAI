"""Feature extraction logic for training data pipeline.

Provides FeatureExtractor class that extracts features from signals and market data,
integrating with signal storage, technical indicators, and Markov chain state detection.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.interface import SignalStorageInterface
    from market_analysis.signal_storage.models import SignalRecord

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
        bb_percent_b: %B indicator (position within bands)
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
    bb_percent_b: float | None = None
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
            "bb_percent_b": self.bb_percent_b,
            "atr": self.atr,
            "volume_sma": self.volume_sma,
        }

    def to_normalized_dict(self) -> dict[str, float]:
        """Convert indicators to normalized [0, 1] range.

        Returns:
            Dictionary with normalized indicator values
        """
        return {
            "rsi_norm": self._normalize_rsi(self.rsi),
            "macd_norm": self._normalize_macd(self.macd),
            "macd_signal_norm": self._normalize_macd(self.macd_signal),
            "macd_histogram_norm": self._normalize_macd(self.macd_histogram),
            "bb_position_norm": self._normalize_bb_position(self.bb_percent_b),
            "bb_width_norm": self._normalize_bb_width(self.bb_width),
            "atr_norm": self._normalize_atr(self.atr),
            "volume_sma_norm": self._normalize_volume(self.volume_sma),
        }

    @staticmethod
    def _normalize_rsi(rsi: float | None) -> float:
        """Normalize RSI to [0, 1] range."""
        if rsi is None:
            return 0.5
        return max(0.0, min(1.0, rsi / 100.0))

    @staticmethod
    def _normalize_macd(macd: float | None) -> float:
        """Normalize MACD to [0, 1] range."""
        if macd is None:
            return 0.5
        # Scale MACD values typically in range [-5, 5] to [0, 1]
        return max(0.0, min(1.0, (macd + 5.0) / 10.0))

    @staticmethod
    def _normalize_bb_position(percent_b: float | None) -> float:
        """Normalize %B to [0, 1] range."""
        if percent_b is None:
            return 0.5
        return max(0.0, min(1.0, percent_b))

    @staticmethod
    def _normalize_bb_width(width: float | None) -> float:
        """Normalize BB width to [0, 1] range."""
        if width is None:
            return 0.5
        # Width typically 0-10%, scale to [0, 1]
        return max(0.0, min(1.0, width / 0.1))

    @staticmethod
    def _normalize_atr(atr: float | None) -> float:
        """Normalize ATR to [0, 1] range."""
        if atr is None:
            return 0.5
        # ATR typically 0-5%, scale to [0, 1]
        return max(0.0, min(1.0, atr / 0.05))

    @staticmethod
    def _normalize_volume(volume: float | None) -> float:
        """Normalize volume to [0, 1] range."""
        if volume is None:
            return 0.5
        # Use sigmoid-like scaling for volume
        return max(0.0, min(1.0, volume / 2.0))


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

    def to_normalized_dict(self) -> dict[str, float]:
        """Convert market context to normalized [0, 1] range."""
        return {
            "trend_confidence_norm": self.trend_confidence or 0.5,
            "confluence_score_norm": (self.confluence_score or 50.0) / 100.0,
            "price_change_24h_norm": self._normalize_price_change(
                self.price_change_24h
            ),
            "volatility_norm": self._normalize_volatility(self.volatility),
            "trend_bullish": 1.0 if self.trend_state == "bullish" else 0.0,
            "trend_bearish": 1.0 if self.trend_state == "bearish" else 0.0,
            "trend_neutral": 1.0 if self.trend_state == "neutral" else 0.0,
            "trend_transitional": 1.0 if self.trend_state == "transitional" else 0.0,
        }

    @staticmethod
    def _normalize_price_change(change: float | None) -> float:
        """Normalize price change to [0, 1] range."""
        if change is None:
            return 0.5
        # Scale -10% to +10% to [0, 1]
        return max(0.0, min(1.0, (change + 10.0) / 20.0))

    @staticmethod
    def _normalize_volatility(vol: float | None) -> float:
        """Normalize volatility to [0, 1] range."""
        if vol is None:
            return 0.5
        # Scale 0-50% volatility to [0, 1]
        return max(0.0, min(1.0, vol / 0.5))


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

    def to_normalized_feature_vector(self) -> dict[str, float]:
        """Convert to normalized feature vector for ML training.

        Returns:
            Dictionary with all features normalized to [0, 1] range
        """
        features: dict[str, float] = {}

        # Signal features
        features["confidence_norm"] = self.confidence or 0.5
        features["direction_long"] = 1.0 if self.direction == "long" else 0.0
        features["direction_short"] = 1.0 if self.direction == "short" else 0.0
        features["direction_neutral"] = 1.0 if self.direction == "neutral" else 0.0

        # Technical indicators (normalized)
        features.update(self.technical.to_normalized_dict())

        # Market context (normalized)
        features.update(self.market.to_normalized_dict())

        return features

    def get_feature_count(self) -> int:
        """Get total number of features."""
        return len(self.to_normalized_feature_vector())


class FeatureCache:
    """Redis-backed cache for extracted features.

    Provides TTL-based caching with hit rate tracking.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes
    REDIS_KEY_PREFIX = "ml:features"

    def __init__(
        self,
        redis_client: Any | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        """Initialize feature cache.

        Args:
            redis_client: Optional Redis client instance
            ttl_seconds: Cache TTL in seconds
        """
        self._redis = redis_client
        self.ttl_seconds = ttl_seconds
        self._local_cache: dict[str, tuple[Any, datetime]] = {}
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any | None:
        """Get cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        # Try local cache first
        if key in self._local_cache:
            value, expiry = self._local_cache[key]
            if datetime.now(UTC) < expiry:
                self._hits += 1
                return value
            else:
                del self._local_cache[key]

        # Try Redis if available
        if self._redis is not None:
            try:
                cached = await self._redis.get(f"{self.REDIS_KEY_PREFIX}:{key}")
                if cached:
                    self._hits += 1
                    value = json.loads(cached)
                    # Store in local cache
                    self._local_cache[key] = (
                        value,
                        datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
                    )
                    return value
            except Exception as e:
                logger.debug(f"Redis cache get failed: {e}")

        self._misses += 1
        return None

    async def set(self, key: str, value: Any) -> bool:
        """Cache value with TTL.

        Args:
            key: Cache key
            value: Value to cache

        Returns:
            True if cached successfully
        """
        # Store in local cache
        self._local_cache[key] = (
            value,
            datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )

        # Store in Redis if available
        if self._redis is not None:
            try:
                serialized = json.dumps(value, default=str)
                await self._redis.setex(
                    f"{self.REDIS_KEY_PREFIX}:{key}",
                    self.ttl_seconds,
                    serialized,
                )
                return True
            except Exception as e:
                logger.debug(f"Redis cache set failed: {e}")

        return True

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Hit rate as percentage (0-100)
        """
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return (self._hits / total) * 100.0

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.get_hit_rate(),
            "local_cache_size": len(self._local_cache),
        }

    def clear(self) -> None:
        """Clear local cache."""
        self._local_cache.clear()
        self._hits = 0
        self._misses = 0


class FeatureExtractor:
    """Extracts features from signals and market data.

    Integrates with signal storage, technical indicators, and Markov chain
    state detection to extract all features required for ML training.

    Attributes:
        signal_storage: Signal storage interface for fetching signal data
        ohlcv_loader: OHLCV data loader from InfluxDB
        indicator_calculator: Technical indicator calculator
        cache: Feature cache with TTL
    """

    def __init__(
        self,
        signal_storage: SignalStorageInterface | None = None,
        ohlcv_loader: Any | None = None,
        indicator_calculator: Any | None = None,
        redis_client: Any | None = None,
        use_cache: bool = True,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize feature extractor.

        Args:
            signal_storage: Signal storage interface
            ohlcv_loader: Optional OHLCV loader (creates default if None)
            indicator_calculator: Optional indicator calculator
            redis_client: Optional Redis client for caching
            use_cache: Whether to enable caching
            cache_ttl_seconds: Cache TTL in seconds
        """
        self.signal_storage = signal_storage
        self._ohlcv_loader = ohlcv_loader
        self._indicator_calculator = indicator_calculator
        self._cache = (
            FeatureCache(
                redis_client=redis_client if use_cache else None,
                ttl_seconds=cache_ttl_seconds,
            )
            if use_cache
            else None
        )
        self._cache_ttl_seconds = cache_ttl_seconds

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

        # Check cache first
        cache_key = f"features:{signal_id}"
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for signal {signal_id}")
                return self._deserialize_features(cached)

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

        # Cache result
        if self._cache is not None:
            await self._cache.set(cache_key, self._serialize_features(features))

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
            cached = await self._cache.get(cache_key)
            if cached is not None and isinstance(cached, dict):
                return self._deserialize_technical_indicators(cached)

        indicators = TechnicalIndicators()

        try:
            # Load OHLCV data
            ohlcv_data = await self._load_ohlcv_data(token, timeframe)

            if ohlcv_data:
                # Calculate indicators
                indicator_values = await self._calculate_indicators(ohlcv_data)

                # Map to TechnicalIndicators
                indicators = TechnicalIndicators(
                    rsi=indicator_values.get("rsi"),
                    macd=indicator_values.get("macd"),
                    macd_signal=indicator_values.get("macd_signal"),
                    macd_histogram=indicator_values.get("macd_histogram"),
                    bb_upper=indicator_values.get("bb_upper"),
                    bb_lower=indicator_values.get("bb_lower"),
                    bb_width=indicator_values.get("bb_width"),
                    bb_percent_b=indicator_values.get("bb_percent_b"),
                )

        except Exception as e:
            logger.warning(f"Failed to extract technical indicators: {e}")

        # Cache result
        if self._cache is not None:
            await self._cache.set(
                cache_key, self._serialize_technical_indicators(indicators)
            )

        return indicators

    async def _load_ohlcv_data(
        self,
        token: str,
        timeframe: str,
    ) -> list[Any]:
        """Load OHLCV data for indicator calculation.

        Args:
            token: Trading pair token
            timeframe: Chart timeframe

        Returns:
            List of OHLCV data points
        """
        try:
            # Lazy import to avoid circular dependencies
            from data_ingestion.timeframe_config import Timeframe
            from ml.features.ohlcv_loader import OHLCVLoader

            # Get or create loader
            if self._ohlcv_loader is None:
                self._ohlcv_loader = OHLCVLoader()

            # Map timeframe string to enum
            tf_map = {
                "1m": Timeframe.MINUTE_1,
                "5m": Timeframe.MINUTE_5,
                "15m": Timeframe.MINUTE_15,
                "1h": Timeframe.HOUR_1,
                "4h": Timeframe.HOUR_4,
                "1d": Timeframe.DAY_1,
            }
            tf_enum = tf_map.get(timeframe, Timeframe.HOUR_1)

            # Load data
            result = await self._ohlcv_loader.load(
                symbol=f"{token}/USDT",
                timeframe=tf_enum,
                lookback_periods=100,
            )

            return result.data if result.is_fresh or len(result.data) >= 50 else []

        except Exception as e:
            logger.warning(f"Failed to load OHLCV data: {e}")
            return []

    async def _calculate_indicators(
        self,
        ohlcv_data: list[Any],
    ) -> dict[str, float | None]:
        """Calculate technical indicators from OHLCV data.

        Args:
            ohlcv_data: List of OHLCV data points

        Returns:
            Dictionary of indicator values
        """
        try:
            # Lazy import to avoid circular dependencies
            from ml.features.indicator_calculator import IndicatorCalculator

            # Get or create calculator
            if self._indicator_calculator is None:
                self._indicator_calculator = IndicatorCalculator()

            # Calculate indicators
            values = self._indicator_calculator.calculate_all(ohlcv_data)

            return values.to_dict()

        except Exception as e:
            logger.warning(f"Indicator calculation failed: {e}")
            return {}

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
        trend_state, trend_confidence = await self.extract_markov_state(
            token, timestamp
        )
        context.trend_state = trend_state
        context.trend_confidence = trend_confidence

        # Extract confluence score from signal if available
        if signal is not None:
            context.confluence_score = signal.score

        # Extract price change and volatility from OHLCV data
        try:
            ohlcv_data = await self._load_ohlcv_data(token, "1h")
            if ohlcv_data and len(ohlcv_data) >= 24:
                # Calculate 24h price change
                price_24h_ago = ohlcv_data[-24].close_price
                current_price = ohlcv_data[-1].close_price
                context.price_change_24h = (
                    (current_price - price_24h_ago) / price_24h_ago
                ) * 100

                # Calculate volatility (std dev of returns)
                returns = []
                for i in range(1, min(len(ohlcv_data), 24)):
                    ret = (
                        ohlcv_data[-i].close_price - ohlcv_data[-i - 1].close_price
                    ) / ohlcv_data[-i - 1].close_price
                    returns.append(ret)

                if returns:
                    mean_ret = sum(returns) / len(returns)
                    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
                    context.volatility = variance**0.5
        except Exception as e:
            logger.debug(f"Failed to calculate price metrics: {e}")

        return context

    async def extract_markov_state(
        self,
        token: str,
        timestamp: datetime,
    ) -> tuple[str | None, float | None]:
        """Get trend state from Markov chain inference.

        Args:
            token: Trading pair token
            timestamp: Target timestamp

        Returns:
            Tuple of (trend_state, confidence) or (None, None)
        """
        try:
            # Lazy import to avoid circular dependencies
            from market_analysis.markov.inference_engine import TrendInferenceEngine
            from market_analysis.markov.state_model import TrendState

            # Load OHLCV data
            ohlcv_data = await self._load_ohlcv_data(token, "1h")

            if not ohlcv_data or len(ohlcv_data) < 50:
                return None, None

            # Create inference engine and infer state
            engine = TrendInferenceEngine()
            result = engine.infer_state(ohlcv_data)

            # Map TrendState to string
            state_map = {
                TrendState.BULLISH: "bullish",
                TrendState.BEARISH: "bearish",
                TrendState.NEUTRAL: "neutral",
                TrendState.TRANSITIONAL: "transitional",
            }

            state_str = state_map.get(result.state)
            return state_str, result.confidence

        except Exception as e:
            logger.debug(f"Markov state extraction failed: {e}")
            return None, None

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

    def get_cache_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        if self._cache is None:
            return {"enabled": 0, "size": 0, "hit_rate": 0.0}
        return self._cache.get_stats()

    def clear_cache(self) -> None:
        """Clear the feature cache."""
        if self._cache is not None:
            self._cache.clear()

    def _serialize_features(self, features: ExtractedFeatures) -> dict[str, Any]:
        """Serialize features to dictionary."""
        return features.to_dict()

    def _deserialize_features(self, data: dict[str, Any]) -> ExtractedFeatures:
        """Deserialize features from dictionary."""
        return ExtractedFeatures(
            signal_id=data.get("signal_id", ""),
            timestamp=data.get("timestamp", datetime.now(UTC)),
            token=data.get("token", ""),
            timeframe=data.get("timeframe", "1h"),
            direction=data.get("direction"),
            confidence=data.get("confidence"),
            entry_price=data.get("entry_price"),
            technical=self._deserialize_technical_indicators(data),
            market=self._deserialize_market_context(data),
            predicted_prob=data.get("predicted_prob"),
        )

    def _serialize_technical_indicators(
        self, indicators: TechnicalIndicators
    ) -> dict[str, Any]:
        """Serialize technical indicators to dictionary."""
        return indicators.to_dict()

    def _deserialize_technical_indicators(
        self, data: dict[str, Any]
    ) -> TechnicalIndicators:
        """Deserialize technical indicators from dictionary."""
        return TechnicalIndicators(
            rsi=data.get("rsi"),
            macd=data.get("macd"),
            macd_signal=data.get("macd_signal"),
            macd_histogram=data.get("macd_histogram"),
            bb_upper=data.get("bb_upper"),
            bb_lower=data.get("bb_lower"),
            bb_width=data.get("bb_width"),
            bb_percent_b=data.get("bb_percent_b"),
            atr=data.get("atr"),
            volume_sma=data.get("volume_sma"),
        )

    def _deserialize_market_context(self, data: dict[str, Any]) -> MarketContext:
        """Deserialize market context from dictionary."""
        return MarketContext(
            trend_state=data.get("trend_state"),
            trend_confidence=data.get("trend_confidence"),
            confluence_score=data.get("confluence_score"),
            price_change_24h=data.get("price_change_24h"),
            volatility=data.get("volatility"),
        )
