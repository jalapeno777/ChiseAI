"""Pre-market briefing generator for dashboard.

Aggregates market summary, key levels, active signals, and regime detection
into a comprehensive pre-market briefing. Updates automatically every 5 minutes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dashboard.key_levels import KeyLevelsResult
    from dashboard.market_summary import MarketSummary
    from dashboard.regime_detector import MarketRegime
    from dashboard.signal_list import SignalListResult
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from signal_generation.models import Signal


@dataclass
class PreMarketBriefing:
    """Complete pre-market briefing for dashboard display.

    Attributes:
        timestamp: When the briefing was generated
        market_summary: Market summary with overnight data
        key_levels: Key support/resistance levels by token
        active_signals: Active signals meeting 75% threshold
        market_regimes: Market regime detection by token
        briefing_text: Human-readable briefing summary
        update_interval_minutes: How often briefing updates
        next_update_time: When the next update will occur
        generation_time_ms: Time taken to generate briefing
    """

    timestamp: datetime
    market_summary: MarketSummary | None = None
    key_levels: dict[str, KeyLevelsResult] = field(default_factory=dict)
    active_signals: SignalListResult | None = None
    market_regimes: dict[str, MarketRegime] = field(default_factory=dict)
    briefing_text: str = ""
    update_interval_minutes: int = 5
    next_update_time: datetime | None = None
    generation_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "market_summary": (
                self.market_summary.to_dict() if self.market_summary else None
            ),
            "key_levels": {
                token: levels.to_dict() for token, levels in self.key_levels.items()
            },
            "active_signals": (
                self.active_signals.to_dict() if self.active_signals else None
            ),
            "market_regimes": {
                token: regime.to_dict() for token, regime in self.market_regimes.items()
            },
            "briefing_text": self.briefing_text,
            "update_interval_minutes": self.update_interval_minutes,
            "next_update_time": (
                self.next_update_time.isoformat() if self.next_update_time else None
            ),
            "generation_time_ms": round(self.generation_time_ms, 2),
        }

    @property
    def is_fresh(self) -> bool:
        """Check if briefing is fresh (within update interval)."""
        if not self.next_update_time:
            return False
        return datetime.now(UTC) < self.next_update_time

    def get_token_briefing(self, token: str) -> dict[str, Any]:
        """Get briefing subset for a specific token.

        Args:
            token: Trading pair

        Returns:
            Token-specific briefing data
        """
        token_signals = []
        if self.active_signals:
            token_signals = [s for s in self.active_signals.signals if s.token == token]

        return {
            "token": token,
            "timestamp": self.timestamp.isoformat(),
            "key_levels": (
                self.key_levels.get(token, {}).to_dict()  # type: ignore[union-attr]
                if token in self.key_levels
                else None
            ),
            "regime": (
                self.market_regimes.get(token, {}).to_dict()  # type: ignore[union-attr]
                if token in self.market_regimes
                else None
            ),
            "active_signals": [s.to_dict() for s in token_signals],
            "briefing_text": self._generate_token_text(token),
        }

    def _generate_token_text(self, token: str) -> str:
        """Generate briefing text for a specific token."""
        parts = [f"**{token} Briefing**"]

        # Add regime info
        if token in self.market_regimes:
            regime = self.market_regimes[token]
            parts.append(f"Regime: {regime.description}")

        # Add key levels
        if token in self.key_levels:
            levels = self.key_levels[token]
            if levels.nearest_support:
                parts.append(f"Support: ${levels.nearest_support.price:,.2f}")
            if levels.nearest_resistance:
                parts.append(f"Resistance: ${levels.nearest_resistance.price:,.2f}")

        # Add signals
        if self.active_signals:
            token_signals = [s for s in self.active_signals.signals if s.token == token]
            if token_signals:
                signal = token_signals[0]
                parts.append(
                    f"Signal: {signal.emoji} {signal.direction.upper()} "
                    f"({signal.confidence:.1f}%)"
                )

        return "\n".join(parts)


class PreMarketBriefingGenerator:
    """Generator for pre-market briefings.

    Aggregates all components:
    - Market summary (overnight moves, volume, volatility)
    - Key levels (support/resistance from multiple timeframes)
    - Active signals (75%+ threshold)
    - Market regime (trending/ranging)

    Updates automatically every 5 minutes with caching.
    """

    def __init__(
        self,
        update_interval_minutes: int = 5,
        confidence_threshold: float = 75.0,
    ):
        """Initialize briefing generator.

        Args:
            update_interval_minutes: How often to update (default: 5)
            confidence_threshold: Signal confidence threshold (default: 75.0)
        """
        self.update_interval_minutes = update_interval_minutes
        self.confidence_threshold = confidence_threshold

        # Initialize component calculators
        from dashboard.key_levels import KeyLevelsAnalyzer
        from dashboard.market_summary import MarketSummaryCalculator
        from dashboard.regime_detector import RegimeDetector
        from dashboard.signal_list import SignalListBuilder

        self._summary_calculator = MarketSummaryCalculator()
        self._levels_analyzer = KeyLevelsAnalyzer()
        self._regime_detector = RegimeDetector()
        self._signal_builder = SignalListBuilder(confidence_threshold)

        # Cache
        self._cached_briefing: PreMarketBriefing | None = None
        self._last_update: datetime | None = None

    def generate(
        self,
        token_data_map: dict[str, dict[str, list[OHLCVData]]],
        signals: list[Signal] | None = None,
        force_refresh: bool = False,
    ) -> PreMarketBriefing:
        """Generate pre-market briefing.

        Args:
            token_data_map: Map of token -> timeframe -> OHLCV data
            signals: Optional list of generated signals
            force_refresh: Force refresh even if cache is valid

        Returns:
            PreMarketBriefing with all components
        """
        start_time = time.perf_counter()

        # Check cache
        if not force_refresh and self._is_cache_valid():
            return self._cached_briefing  # type: ignore[return-value]

        timestamp = datetime.now(UTC)

        # Extract all timeframe data for market summary
        summary_data_map: dict[str, list[OHLCVData]] = {}
        for token, tf_data in token_data_map.items():
            # Use the finest timeframe for summary (usually 1h or 15m)
            finest_tf = min(tf_data.keys(), key=lambda x: len(x)) if tf_data else None
            if finest_tf and tf_data[finest_tf]:
                summary_data_map[token] = tf_data[finest_tf]

        # Calculate market summary
        market_summary = self._summary_calculator.calculate_summary(summary_data_map)

        # Calculate overnight summary
        overnight_summary = self._summary_calculator.calculate_overnight_summary(
            summary_data_map, hours_ago=8
        )

        # Analyze key levels for each token
        key_levels: dict[str, KeyLevelsResult] = {}
        for token, tf_data in token_data_map.items():
            current_price = self._get_current_price(tf_data)
            if current_price > 0:
                levels = self._levels_analyzer.analyze(token, tf_data, current_price)
                key_levels[token] = levels

        # Detect market regimes
        market_regimes: dict[str, MarketRegime] = {}
        for token, tf_data in token_data_map.items():
            # Use primary timeframe (1h) for regime detection
            if "1h" in tf_data and tf_data["1h"]:
                regime = self._regime_detector.detect(tf_data["1h"])
                market_regimes[token] = regime

        # Build active signals list
        active_signals = None
        if signals:
            active_signals = self._signal_builder.build(signals)

        # Generate briefing text
        briefing_text = self._generate_briefing_text(
            market_summary,
            overnight_summary,
            active_signals,
            market_regimes,
        )

        # Calculate next update time
        next_update = timestamp + timedelta(minutes=self.update_interval_minutes)

        # Calculate generation time
        generation_time_ms = (time.perf_counter() - start_time) * 1000

        briefing = PreMarketBriefing(
            timestamp=timestamp,
            market_summary=market_summary,
            key_levels=key_levels,
            active_signals=active_signals,
            market_regimes=market_regimes,
            briefing_text=briefing_text,
            update_interval_minutes=self.update_interval_minutes,
            next_update_time=next_update,
            generation_time_ms=generation_time_ms,
        )

        # Update cache
        self._cached_briefing = briefing
        self._last_update = timestamp

        return briefing

    def _is_cache_valid(self) -> bool:
        """Check if cached briefing is still valid."""
        if not self._cached_briefing or not self._last_update:
            return False

        elapsed = datetime.now(UTC) - self._last_update
        return elapsed < timedelta(minutes=self.update_interval_minutes)

    def _get_current_price(
        self,
        tf_data: dict[str, list[OHLCVData]],
    ) -> float:
        """Get current price from timeframe data.

        Args:
            tf_data: Map of timeframe -> OHLCV data

        Returns:
            Current price or 0 if not available
        """
        # Try to get from finest timeframe
        for tf in sorted(tf_data.keys()):
            if tf_data[tf] and len(tf_data[tf]) > 0:
                return float(tf_data[tf][-1].close_price)
        return 0.0

    def _generate_briefing_text(
        self,
        market_summary: MarketSummary,
        overnight_summary: dict[str, Any],
        active_signals: SignalListResult | None,
        market_regimes: dict[str, MarketRegime],
    ) -> str:
        """Generate human-readable briefing text.

        Args:
            market_summary: Market summary
            overnight_summary: Overnight summary data
            active_signals: Active signals result
            market_regimes: Market regimes by token

        Returns:
            Briefing text
        """
        lines = [
            "📊 **Pre-Market Briefing**",
            f"Generated: {market_summary.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Market Overview",
            f"Overall Sentiment: **{market_summary.overall_sentiment.upper()}**",
            f"Avg 24h Change: {market_summary.avg_price_change_24h:+.2f}%",
            f"Overnight Change: {overnight_summary.get('avg_change_pct', 0):+.2f}%",
            "",
        ]

        # Add top movers
        if market_summary.top_gainers:
            lines.append("### Top Gainers (24h)")
            for token in market_summary.top_gainers[:3]:
                lines.append(f"  • {token.token}: {token.price_change_24h:+.2f}%")
            lines.append("")

        if market_summary.top_losers:
            lines.append("### Top Losers (24h)")
            for token in market_summary.top_losers[:3]:
                lines.append(f"  • {token.token}: {token.price_change_24h:+.2f}%")
            lines.append("")

        # Add active signals summary
        if active_signals and active_signals.signals:
            total = len(active_signals.signals)
            long_cnt = active_signals.long_count
            short_cnt = active_signals.short_count
            lines.append(f"Total: {total} | Long: {long_cnt} | Short: {short_cnt}")
            lines.append("")

            # Show top 5 signals
            for signal in active_signals.signals[:5]:
                direction = signal.direction.upper()
                conf_pct = signal.confidence
                emoji = "🟢" if signal.direction.lower() == "long" else "🔴"
                lines.append(
                    f"{emoji} **{signal.token}** {direction} ({conf_pct:.1f}%)"
                )
            lines.append("")

        # Add regime summary
        trending_count = sum(1 for r in market_regimes.values() if r.is_trending)
        ranging_count = sum(1 for r in market_regimes.values() if r.is_ranging)
        total = len(market_regimes)

        lines.append("## Market Regimes")
        lines.append(
            f"Trending: {trending_count} | Ranging: {ranging_count} | Total: {total}"
        )
        lines.append("")

        # Add update info
        lines.append(f"_Updates every {self.update_interval_minutes} minutes_")

        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        """Invalidate the cached briefing."""
        self._cached_briefing = None
        self._last_update = None

    def get_cache_status(self) -> dict[str, Any]:
        """Get cache status information.

        Returns:
            Dictionary with cache status
        """
        if not self._cached_briefing or not self._last_update:
            return {
                "cached": False,
                "age_seconds": None,
                "valid": False,
            }

        age = datetime.now(UTC) - self._last_update
        valid = age < timedelta(minutes=self.update_interval_minutes)

        return {
            "cached": True,
            "age_seconds": age.total_seconds(),
            "valid": valid,
            "next_update": (
                self._cached_briefing.next_update_time.isoformat()
                if self._cached_briefing.next_update_time
                else None
            ),
        }
