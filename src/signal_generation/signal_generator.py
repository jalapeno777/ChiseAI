"""Main signal generation orchestrator.

Generates real-time trading signals from confluence scores with
75%+ confidence threshold enforcement. Includes caching for
performance and data freshness validation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from signal_generation.models import SignalDirection

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from data_ingestion.timeframe_config import Timeframe
    from market_analysis.confluence.scorer import ConfluenceScorer
    from signal_generation.confidence_filter import ConfidenceFilter
    from signal_generation.data_freshness_check import DataFreshnessChecker
    from signal_generation.models import Signal

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class SignalGenerationConfig:
    """Configuration for signal generation.

    Attributes:
        actionable_threshold: Minimum confidence for actionable signals (0.0-1.0)
        enable_freshness_checks: Whether to validate data freshness
        max_signals_per_token_per_hour: Rate limit for signal generation
        cache_ttl_seconds: Time-to-live for signal cache
        enable_caching: Whether to enable signal caching
        enable_stop_loss_calculation: Whether to calculate stop-loss for signals
        enable_trailing_stop: Whether to calculate trailing stop for strong trends
        trailing_stop_threshold: Confidence threshold for trailing stop (0.0-1.0)
    """

    actionable_threshold: float = 0.75
    enable_freshness_checks: bool = True
    max_signals_per_token_per_hour: int = 10
    cache_ttl_seconds: float = 300.0  # 5 minutes
    enable_caching: bool = True
    enable_stop_loss_calculation: bool = True
    enable_trailing_stop: bool = True
    trailing_stop_threshold: float = 0.85  # 85% confidence for trailing stop


class SignalCache:
    """Cache for signals to avoid redundant calculations.

    Uses token+timeframe+direction as cache key to prevent
    duplicate signal generation for the same market state.
    """

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize signal cache.

        Args:
            ttl_seconds: Time-to-live for cache entries
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Signal, float]] = {}  # key -> (signal, timestamp)

    def _make_key(self, token: str, timeframe: str, direction: SignalDirection) -> str:
        """Create cache key from signal parameters.

        Args:
            token: Trading pair
            timeframe: Timeframe string
            direction: Signal direction

        Returns:
            Cache key string
        """
        return f"{token}:{timeframe}:{direction.value}"

    def get(
        self, token: str, timeframe: str, direction: SignalDirection
    ) -> Signal | None:
        """Get cached signal if not expired.

        Args:
            token: Trading pair
            timeframe: Timeframe string
            direction: Signal direction

        Returns:
            Cached signal or None if not found/expired
        """
        key = self._make_key(token, timeframe, direction)
        if key not in self._cache:
            return None

        signal, timestamp = self._cache[key]
        age = time.monotonic() - timestamp

        if age > self.ttl_seconds:
            # Expired
            del self._cache[key]
            return None

        logger.debug(f"Cache hit for {key} (age={age:.1f}s)")
        return signal

    def set(
        self, token: str, timeframe: str, direction: SignalDirection, signal: Signal
    ) -> None:
        """Cache a signal.

        Args:
            token: Trading pair
            timeframe: Timeframe string
            direction: Signal direction
            signal: Signal to cache
        """
        key = self._make_key(token, timeframe, direction)
        self._cache[key] = (signal, time.monotonic())
        logger.debug(f"Cached signal for {key}")

    def clear(self) -> None:
        """Clear all cached signals."""
        self._cache.clear()
        logger.debug("Signal cache cleared")

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        now = time.monotonic()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if now - timestamp > self.ttl_seconds
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)


class SignalGenerator:
    """Real-time signal generation orchestrator.

    Generates trading signals from confluence scores with:
    - 75%+ confidence threshold for actionable signals
    - Data freshness validation (2x timeframe interval)
    - Signal caching to avoid redundant calculations
    - End-to-end latency tracking (<1 second target)

    Integrates with:
    - ConfluenceScorer from ST-NS-005 for scoring
    - DataValidator from ST-NS-001 for freshness
    - SignalEmitter for emission (ST-NS-008, ST-NS-009)
    """

    def __init__(
        self,
        scorer: ConfluenceScorer | None = None,
        confidence_filter: ConfidenceFilter | None = None,
        freshness_checker: DataFreshnessChecker | None = None,
        config: SignalGenerationConfig | None = None,
    ):
        """Initialize signal generator.

        Args:
            scorer: ConfluenceScorer instance (created if None)
            confidence_filter: ConfidenceFilter instance (created if None)
            freshness_checker: DataFreshnessChecker instance (created if None)
            config: Signal generation configuration
        """
        self.config = config or SignalGenerationConfig()

        # Initialize or store dependencies
        self._scorer = scorer
        self._confidence_filter = confidence_filter
        self._freshness_checker = freshness_checker

        # Initialize cache
        self._cache = SignalCache(ttl_seconds=self.config.cache_ttl_seconds)

        # Rate limiting state
        self._signal_counts: dict[str, list[float]] = {}  # token -> timestamps

        logger.info(
            f"SignalGenerator initialized: "
            f"threshold={self.config.actionable_threshold:.0%}, "
            f"freshness_checks={self.config.enable_freshness_checks}, "
            f"cache_ttl={self.config.cache_ttl_seconds}s"
        )

    def _get_scorer(self) -> ConfluenceScorer:
        """Get or create ConfluenceScorer."""
        if self._scorer is None:
            from market_analysis.confluence.scorer import ConfluenceScorer

            self._scorer = ConfluenceScorer()
        return self._scorer

    def _get_confidence_filter(self) -> ConfidenceFilter:
        """Get or create ConfidenceFilter."""
        if self._confidence_filter is None:
            from signal_generation.confidence_filter import ConfidenceFilter

            self._confidence_filter = ConfidenceFilter(
                threshold=self.config.actionable_threshold
            )
        return self._confidence_filter

    def _get_freshness_checker(self) -> DataFreshnessChecker:
        """Get or create DataFreshnessChecker."""
        if self._freshness_checker is None:
            from signal_generation.data_freshness_check import DataFreshnessChecker

            self._freshness_checker = DataFreshnessChecker(
                freshness_multiplier=2.0, enable_health_alerts=True
            )
        return self._freshness_checker

    def _check_rate_limit(self, token: str) -> bool:
        """Check if token has exceeded rate limit.

        Args:
            token: Trading pair token

        Returns:
            True if under rate limit, False if exceeded
        """
        now = time.time()
        hour_ago = now - 3600

        # Get recent signals for this token
        timestamps = self._signal_counts.get(token, [])
        recent = [t for t in timestamps if t > hour_ago]

        # Update stored timestamps
        self._signal_counts[token] = recent

        under_limit = len(recent) < self.config.max_signals_per_token_per_hour

        if not under_limit:
            logger.warning(
                f"Rate limit exceeded for {token}: {len(recent)}/hour "
                f"(max {self.config.max_signals_per_token_per_hour})"
            )

        return under_limit

    def _record_signal(self, token: str) -> None:
        """Record a signal for rate limiting.

        Args:
            token: Trading pair token
        """
        if token not in self._signal_counts:
            self._signal_counts[token] = []
        self._signal_counts[token].append(time.time())

    def _map_direction(self, direction_str: str) -> SignalDirection:
        """Map confluence direction to signal direction.

        Args:
            direction_str: Direction string from confluence score

        Returns:
            SignalDirection enum value
        """
        from signal_generation.models import SignalDirection

        direction_map = {
            "LONG": SignalDirection.LONG,
            "SHORT": SignalDirection.SHORT,
            "NEUTRAL": SignalDirection.NEUTRAL,
        }
        return direction_map.get(direction_str.upper(), SignalDirection.NEUTRAL)

    def generate_signal(
        self,
        token: str,
        timeframe: Timeframe,
        ohlcv_data: list[OHLCVData],
        aggregated_signals: Any | None = None,
        key_levels: Any | None = None,
        current_price: float | None = None,
    ) -> Signal:
        """Generate a trading signal from OHLCV data.

        This is the main entry point for signal generation. It:
        1. Validates data freshness
        2. Calculates confluence score
        3. Applies confidence threshold
        4. Calculates stop-loss if enabled
        5. Returns actionable or logged-only signal

        Args:
            token: Trading pair (e.g., "BTC/USDT")
            timeframe: Timeframe for analysis
            ohlcv_data: OHLCV candle data
            aggregated_signals: Optional pre-computed aggregated signals
            key_levels: Optional key levels for stop-loss calculation
            current_price: Optional current price for stop-loss calculation

        Returns:
            Signal with status (actionable or logged_only)
        """
        from signal_generation.models import Signal, SignalStatus

        start_time = time.perf_counter()

        # Step 1: Data freshness check
        if self.config.enable_freshness_checks:
            freshness_checker = self._get_freshness_checker()
            freshness_result = freshness_checker.check_freshness(ohlcv_data, timeframe)

            if not freshness_result.is_fresh:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "Signal generation blocked: stale data for %s %s",
                    token,
                    timeframe.value,
                )
                return Signal(
                    token=token,
                    direction=self._map_direction("NEUTRAL"),
                    confidence=0.0,
                    base_score=0.0,
                    timestamp=datetime.now(UTC),
                    status=SignalStatus.STALE_DATA,
                    timeframe=timeframe.value,
                    metadata={
                        "freshness_errors": freshness_result.errors,
                        "data_age": freshness_result.data_age_seconds,
                    },
                    generation_latency_ms=latency_ms,
                )

        # Step 2: Calculate confluence score
        scorer = self._get_scorer()

        if aggregated_signals is None:
            # Need to compute aggregated signals from OHLCV data
            # This requires indicator calculation
            from market_analysis.confluence.signal_aggregator import SignalAggregator
            from market_analysis.indicators.calculator import IndicatorCalculator

            # Calculate indicators
            indicator_calc = IndicatorCalculator()
            indicator_results = indicator_calc.calculate_all(
                ohlcv_data,
                timeframe,  # type: ignore[arg-type]
            )

            # Convert IndicatorSet to list of IndicatorSignal objects
            signals_list = []
            aggregator = SignalAggregator()
            ts = int(time.time() * 1000)

            # Extract RSI signal
            if indicator_results.rsi is not None:
                rsi_signal = aggregator.from_rsi(
                    indicator_results.rsi,
                    timeframe.value,
                    timestamp=ts,
                )
                if rsi_signal is not None:
                    signals_list.append(rsi_signal)

            # Extract MACD signal
            if indicator_results.macd is not None:
                macd_signal = aggregator.from_macd(
                    indicator_results.macd,
                    timeframe.value,
                    timestamp=ts,
                )
                if macd_signal is not None:
                    signals_list.append(macd_signal)

            # Extract Bollinger Bands signal
            if (
                indicator_results.bollinger_bands is not None
                and current_price is not None
            ):
                bb_signal = aggregator.from_bollinger_bands(
                    indicator_results.bollinger_bands,
                    current_price,
                    timeframe.value,
                    timestamp=ts,
                )
                if bb_signal is not None:
                    signals_list.append(bb_signal)

            # Aggregate signals
            aggregated_signals = aggregator.aggregate(
                signals_list,
                timestamp=ts,
            )

        # Calculate confluence score
        timestamp_ms = int(time.time() * 1000)
        confluence_score = scorer.calculate_score(aggregated_signals, timestamp_ms)

        # Step 3: Map to Signal
        direction = self._map_direction(confluence_score.direction_str)

        # Check cache for duplicate signals
        if self.config.enable_caching:
            cached = self._cache.get(token, timeframe.value, direction)
            if cached is not None:
                # Update latency for cached signal
                latency_ms = (time.perf_counter() - start_time) * 1000
                cached.generation_latency_ms = latency_ms
                logger.debug(f"Returning cached signal for {token} {timeframe.value}")
                return cached

        # Create signal
        signal = Signal(
            token=token,
            direction=direction,
            confidence=confluence_score.confidence,
            base_score=confluence_score.score,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,  # Default, may change below
            timeframe=timeframe.value,
            contributing_factors=confluence_score.contributing_factors,
            signal_breakdown=confluence_score.signal_breakdown,
            metadata={
                "confluence_metadata": confluence_score.metadata,
                "multiplier_applied": confluence_score.multiplier_applied,
                "multiplier_rationale": confluence_score.multiplier_rationale,
            },
        )

        # Step 4: Calculate stop-loss if enabled and we have required data
        if (
            self.config.enable_stop_loss_calculation
            and key_levels is not None
            and current_price is not None
            and signal.direction != SignalDirection.NEUTRAL
        ):
            self._calculate_stop_loss(signal, ohlcv_data, key_levels, current_price)

        # Step 5: Apply confidence threshold
        confidence_filter = self._get_confidence_filter()
        filter_result = confidence_filter.filter(signal)

        if filter_result.is_actionable:
            # Check rate limit
            if self._check_rate_limit(token):
                signal.status = SignalStatus.ACTIONABLE
                self._record_signal(token)
                logger.info(
                    f"Actionable signal: {token} [{signal.direction_str}] "
                    f"confidence={signal.confidence:.1%}"
                )
            else:
                # Rate limited - still actionable but marked
                signal.status = SignalStatus.ACTIONABLE
                signal.metadata["rate_limited"] = True
                logger.warning(
                    "Actionable signal (rate limited): %s [%s]",
                    token,
                    signal.direction_str,
                )
        else:
            # Log non-actionable signal
            confidence_filter.log_non_actionable(signal)

        # Cache the signal
        if self.config.enable_caching:
            self._cache.set(token, timeframe.value, signal.direction, signal)

        # Record latency
        signal.generation_latency_ms = (time.perf_counter() - start_time) * 1000

        # Log latency warning if >1 second
        if signal.generation_latency_ms > 1000:
            logger.warning(
                f"Signal generation latency exceeded 1s: "
                f"{signal.generation_latency_ms:.1f}ms for {token}"
            )

        return signal

    def generate_signals_batch(
        self,
        token_data_map: dict[str, dict[Timeframe, list[OHLCVData]]],
    ) -> list[Signal]:
        """Generate signals for multiple tokens and timeframes.

        Args:
            token_data_map: Map of token -> timeframe -> OHLCV data

        Returns:
            List of generated signals
        """
        signals = []

        for token, timeframe_map in token_data_map.items():
            for timeframe, ohlcv_data in timeframe_map.items():
                try:
                    signal = self.generate_signal(token, timeframe, ohlcv_data)
                    signals.append(signal)
                except Exception as e:
                    logger.error(
                        f"Signal generation failed for {token} {timeframe.value}: {e}"
                    )

        return signals

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "cache_enabled": self.config.enable_caching,
            "cache_ttl_seconds": self.config.cache_ttl_seconds,
            "cached_entries": len(self._cache._cache),
        }

    def clear_cache(self) -> None:
        """Clear the signal cache."""
        self._cache.clear()

    def _calculate_stop_loss(
        self,
        signal: Signal,
        ohlcv_data: list[OHLCVData],
        key_levels: Any,
        current_price: float,
    ) -> None:
        """Calculate stop-loss for a signal.

        Uses the StopLossCalculator to compute optimal stop-loss
        and optionally trailing stop for strong trends.

        Args:
            signal: The signal to calculate stop-loss for
            ohlcv_data: OHLCV candle data
            key_levels: Key levels result from KeyLevelsAnalyzer
            current_price: Current market price
        """
        from portfolio_risk.stop_loss import (
            StopLossCalculator,
            TradeDirection,
        )

        try:
            # Map signal direction to trade direction
            trade_direction = (
                TradeDirection.LONG
                if signal.direction.value == "long"
                else TradeDirection.SHORT
            )

            # Calculate stop-loss
            calculator = StopLossCalculator()
            stop_result = calculator.calculate_stop_loss(
                entry_price=current_price,
                direction=trade_direction,
                ohlcv_data=ohlcv_data,
                key_levels=key_levels,
            )

            # Update signal with stop-loss information
            signal.stop_loss = stop_result.selected_stop.stop_price
            signal.stop_loss_method = stop_result.selected_stop.method.value
            signal.stop_loss_rationale = stop_result.selected_stop.rationale
            signal.risk_reward_ratio = stop_result.selected_stop.risk_reward_ratio

            # Log stop-loss calculation
            logger.debug(
                f"Stop-loss calculated for {signal.token}: "
                f"{signal.stop_loss:.2f} ({signal.stop_loss_method})"
            )

            # Calculate trailing stop for strong trends
            if (
                self.config.enable_trailing_stop
                and signal.confidence >= self.config.trailing_stop_threshold
            ):
                self._calculate_trailing_stop(signal, ohlcv_data, current_price)

        except Exception as e:
            logger.warning(f"Stop-loss calculation failed for {signal.token}: {e}")
            # Signal remains valid but without stop-loss

    def _calculate_trailing_stop(
        self,
        signal: Signal,
        ohlcv_data: list[OHLCVData],
        current_price: float,
    ) -> None:
        """Calculate trailing stop for strong trends.

        Trailing stop is calculated as a percentage of the current price,
        adjusted based on trend strength (confidence).

        Args:
            signal: The signal to calculate trailing stop for
            ohlcv_data: OHLCV candle data
            current_price: Current market price
        """
        from portfolio_risk.stop_loss import ATR

        try:
            # Calculate ATR for volatility-based trailing distance
            atr_calc = ATR(period=14)
            atr_result = atr_calc.calculate(ohlcv_data)

            # Trailing distance: 1.5x ATR for strong trends
            trailing_distance = atr_result.current * 1.5

            if signal.direction.value == "long":
                signal.trailing_stop = current_price - trailing_distance
            else:
                signal.trailing_stop = current_price + trailing_distance

            signal.trailing_stop_enabled = True

            logger.debug(
                f"Trailing stop calculated for {signal.token}: "
                f"{signal.trailing_stop:.2f} (confidence={signal.confidence:.1%})"
            )

        except Exception as e:
            logger.warning(f"Trailing stop calculation failed for {signal.token}: {e}")
