"""Market summary calculations for pre-market briefing.

Calculates overnight market movements, volume changes, volatility metrics,
and identifies top movers for dashboard display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


@dataclass
class TokenMetrics:
    """Metrics for a single token.

    Attributes:
        token: Trading pair (e.g., "BTC/USDT")
        current_price: Current price
        price_change_24h: 24-hour price change percentage
        price_change_7d: 7-day price change percentage
        volume_24h: 24-hour volume
        volume_change: Volume change vs 24h average (percentage)
        volatility_24h: 24-hour volatility (ATR as % of price)
        price_range_24h: 24-hour price range (high - low)
        high_24h: 24-hour high
        low_24h: 24-hour low
    """

    token: str
    current_price: float
    price_change_24h: float
    price_change_7d: float
    volume_24h: float
    volume_change: float
    volatility_24h: float
    price_range_24h: float
    high_24h: float
    low_24h: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "token": self.token,
            "current_price": round(self.current_price, 2),
            "price_change_24h": round(self.price_change_24h, 2),
            "price_change_7d": round(self.price_change_7d, 2),
            "volume_24h": round(self.volume_24h, 2),
            "volume_change": round(self.volume_change, 2),
            "volatility_24h": round(self.volatility_24h, 2),
            "price_range_24h": round(self.price_range_24h, 2),
            "high_24h": round(self.high_24h, 2),
            "low_24h": round(self.low_24h, 2),
        }


@dataclass
class MarketSummary:
    """Complete market summary for pre-market briefing.

    Attributes:
        timestamp: When the summary was generated
        tokens: List of token metrics
        top_gainers: Top 5 gaining tokens by 24h change
        top_losers: Top 5 losing tokens by 24h change
        top_volume: Top 5 tokens by volume
        most_volatile: Top 5 most volatile tokens
        overall_sentiment: Overall market sentiment (bullish/bearish/neutral)
        avg_price_change_24h: Average 24h price change across all tokens
        total_volume_24h: Total 24h volume across all tokens
    """

    timestamp: datetime
    tokens: list[TokenMetrics] = field(default_factory=list)
    top_gainers: list[TokenMetrics] = field(default_factory=list)
    top_losers: list[TokenMetrics] = field(default_factory=list)
    top_volume: list[TokenMetrics] = field(default_factory=list)
    most_volatile: list[TokenMetrics] = field(default_factory=list)
    overall_sentiment: str = "neutral"
    avg_price_change_24h: float = 0.0
    total_volume_24h: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_sentiment": self.overall_sentiment,
            "avg_price_change_24h": round(self.avg_price_change_24h, 2),
            "total_volume_24h": round(self.total_volume_24h, 2),
            "top_gainers": [t.to_dict() for t in self.top_gainers],
            "top_losers": [t.to_dict() for t in self.top_losers],
            "top_volume": [t.to_dict() for t in self.top_volume],
            "most_volatile": [t.to_dict() for t in self.most_volatile],
            "token_count": len(self.tokens),
        }


class MarketSummaryCalculator:
    """Calculator for market summary metrics.

    Calculates overnight market summary from OHLCV data including:
    - Price changes (24h, 7d)
    - Volume changes vs average
    - Volatility metrics (ATR, price range)
    - Top movers identification
    """

    def __init__(self, atr_period: int = 14):
        """Initialize calculator.

        Args:
            atr_period: Period for ATR calculation (default: 14)
        """
        self.atr_period = atr_period

    def calculate_summary(
        self,
        token_data_map: dict[str, list[OHLCVData]],
    ) -> MarketSummary:
        """Calculate market summary from token data.

        Args:
            token_data_map: Map of token -> OHLCV data list

        Returns:
            MarketSummary with all calculated metrics
        """
        timestamp = datetime.now(UTC)
        token_metrics: list[TokenMetrics] = []

        for token, data in token_data_map.items():
            if not data or len(data) < 2:
                continue

            metrics = self._calculate_token_metrics(token, data)
            if metrics:
                token_metrics.append(metrics)

        # Calculate aggregates
        avg_change = (
            np.mean([m.price_change_24h for m in token_metrics])
            if token_metrics
            else 0.0
        )
        total_volume = sum(m.volume_24h for m in token_metrics)

        # Determine overall sentiment
        if avg_change > 2.0:
            sentiment = "bullish"
        elif avg_change < -2.0:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Sort for top lists
        sorted_by_change = sorted(
            token_metrics,
            key=lambda x: x.price_change_24h,
            reverse=True,
        )
        sorted_by_volume = sorted(
            token_metrics,
            key=lambda x: x.volume_24h,
            reverse=True,
        )
        sorted_by_volatility = sorted(
            token_metrics,
            key=lambda x: x.volatility_24h,
            reverse=True,
        )

        return MarketSummary(
            timestamp=timestamp,
            tokens=token_metrics,
            top_gainers=sorted_by_change[:5],
            top_losers=sorted_by_change[-5:][::-1],  # Reverse to show worst first
            top_volume=sorted_by_volume[:5],
            most_volatile=sorted_by_volatility[:5],
            overall_sentiment=sentiment,
            avg_price_change_24h=avg_change,
            total_volume_24h=total_volume,
        )

    def _calculate_token_metrics(
        self,
        token: str,
        data: list[OHLCVData],
    ) -> TokenMetrics | None:
        """Calculate metrics for a single token.

        Args:
            token: Trading pair
            data: OHLCV data list

        Returns:
            TokenMetrics or None if insufficient data
        """
        if len(data) < 24:  # Need at least 24 candles for 24h metrics
            return None

        # Current price (latest close)
        current_price = data[-1].close_price

        # 24h price change (assuming hourly data, use last 24 candles)
        price_24h_ago = (
            data[-24].close_price if len(data) >= 24 else data[0].close_price
        )
        price_change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100

        # 7d price change (assuming hourly data, use last 168 candles)
        if len(data) >= 168:
            price_7d_ago = data[-168].close_price
            price_change_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
        else:
            # Use earliest available data
            price_7d_ago = data[0].close_price
            price_change_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

        # 24h volume and change
        recent_volume = sum(c.volume for c in data[-24:])

        # Calculate average volume over all available data
        if len(data) > 24:
            avg_volume = sum(c.volume for c in data[:-24]) / (len(data) - 24)
            volume_change = (
                ((recent_volume - avg_volume) / avg_volume) * 100
                if avg_volume > 0
                else 0.0
            )
        else:
            volume_change = 0.0

        # 24h high/low and range
        recent_data = data[-24:]
        high_24h = max(c.high_price for c in recent_data)
        low_24h = min(c.low_price for c in recent_data)
        price_range_24h = high_24h - low_24h

        # Calculate ATR for volatility
        atr = self._calculate_atr(data[-24:])
        volatility_24h = (atr / current_price) * 100 if current_price > 0 else 0.0

        return TokenMetrics(
            token=token,
            current_price=current_price,
            price_change_24h=price_change_24h,
            price_change_7d=price_change_7d,
            volume_24h=recent_volume,
            volume_change=volume_change,
            volatility_24h=volatility_24h,
            price_range_24h=price_range_24h,
            high_24h=high_24h,
            low_24h=low_24h,
        )

    def _calculate_atr(self, data: list[OHLCVData]) -> float:
        """Calculate Average True Range.

        Args:
            data: OHLCV data list

        Returns:
            ATR value
        """
        if len(data) < 2:
            return 0.0

        true_ranges: list[float] = []
        for i in range(1, len(data)):
            high = data[i].high_price
            low = data[i].low_price
            prev_close = data[i - 1].close_price

            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)

            true_ranges.append(max(tr1, tr2, tr3))

        return float(np.mean(true_ranges)) if true_ranges else 0.0

    def calculate_overnight_summary(
        self,
        token_data_map: dict[str, list[OHLCVData]],
        hours_ago: int = 8,
    ) -> dict[str, Any]:
        """Calculate overnight market summary.

        Args:
            token_data_map: Map of token -> OHLCV data list
            hours_ago: Number of hours to look back (default: 8 for overnight)

        Returns:
            Dictionary with overnight summary
        """
        timestamp = datetime.now(UTC)
        overnight_changes: list[dict[str, Any]] = []

        for token, data in token_data_map.items():
            if len(data) < hours_ago:
                continue

            current_price = data[-1].close_price
            past_price = data[-hours_ago].close_price
            change_pct = ((current_price - past_price) / past_price) * 100

            # Calculate volume during overnight period
            overnight_volume = sum(c.volume for c in data[-hours_ago:])

            overnight_changes.append(
                {
                    "token": token,
                    "current_price": round(current_price, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": round(overnight_volume, 2),
                }
            )

        # Sort by absolute change
        overnight_changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

        # Calculate overall overnight sentiment
        avg_change = (
            np.mean([c["change_pct"] for c in overnight_changes])
            if overnight_changes
            else 0.0
        )

        return {
            "timestamp": timestamp.isoformat(),
            "period_hours": hours_ago,
            "avg_change_pct": round(avg_change, 2),
            "sentiment": (
                "bullish"
                if avg_change > 1.0
                else "bearish" if avg_change < -1.0 else "neutral"
            ),
            "top_movers": overnight_changes[:10],
            "token_count": len(overnight_changes),
        }
