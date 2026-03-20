"""Order book imbalance analysis for market microstructure signals.

Computes bid/ask ratio and depth imbalance at multiple levels of L2
order book data. Provides configurable thresholds for signal generation
and integrates with FeatureStore for real-time caching.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from market_analysis.indicators.base import (
    BaseIndicator,
    Signal,
    SignalDirection,
)
from market_analysis.indicators.feature_store import FeatureStore

logger = logging.getLogger(__name__)


class ImbalanceLevel(Enum):
    """Classification of order book imbalance severity."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class PriceLevel:
    """Represents a single price level in the order book.

    Attributes:
        price: The price at this level.
        quantity: The total quantity (size) at this level.
    """

    price: float
    quantity: float


@dataclass
class OrderBookSnapshot:
    """Represents a snapshot of L2 order book data.

    Attributes:
        symbol: Trading pair symbol (e.g., 'BTC/USDT').
        bids: List of bid price levels, ordered best (highest price) first.
        asks: List of ask price levels, ordered best (lowest price) first.
        timestamp: Snapshot timestamp in milliseconds since epoch.
    """

    symbol: str
    bids: list[PriceLevel]
    asks: list[PriceLevel]
    timestamp: float


@dataclass
class OrderBookImbalanceResult:
    """Result of order book imbalance analysis.

    Attributes:
        bid_ask_ratio: Ratio of total bid volume to total ask volume (>1 = bullish).
        depth_imbalance: Normalized imbalance in [-1, 1] where 1 = all bids.
        bid_volume: Total bid volume across analyzed levels.
        ask_volume: Total ask volume across analyzed levels.
        level_imbalances: Per-level imbalance values.
        imbalance_level: Classified imbalance severity.
        spread: Best bid-ask spread in price units.
        mid_price: Midpoint between best bid and best ask.
        num_levels: Number of depth levels analyzed.
        timestamp: When the analysis was performed.
    """

    bid_ask_ratio: float
    depth_imbalance: float
    bid_volume: float
    ask_volume: float
    level_imbalances: dict[int, float]
    imbalance_level: ImbalanceLevel
    spread: float
    mid_price: float
    num_levels: int
    timestamp: datetime

    @property
    def is_bullish(self) -> bool:
        """Check if the imbalance is bullish (more bid pressure)."""
        return self.imbalance_level in (
            ImbalanceLevel.BUY,
            ImbalanceLevel.STRONG_BUY,
        )

    @property
    def is_bearish(self) -> bool:
        """Check if the imbalance is bearish (more ask pressure)."""
        return self.imbalance_level in (
            ImbalanceLevel.SELL,
            ImbalanceLevel.STRONG_SELL,
        )


class OrderBookImbalance(BaseIndicator[OrderBookImbalanceResult]):
    """Order book imbalance indicator for microstructure signal generation.

    Computes bid/ask ratio and depth imbalance at multiple L2 depth levels.
    Uses configurable thresholds to classify imbalance severity and generate
    trading signals. Integrates with FeatureStore for real-time caching of
    computed results.

    Thresholds:
        strong_buy_threshold: bid_ask_ratio above this triggers STRONG_BUY (default: 1.5)
        buy_threshold: bid_ask_ratio above this triggers BUY (default: 1.2)
        sell_threshold: bid_ask_ratio below this triggers SELL (default: 0.8)
        strong_sell_threshold: bid_ask_ratio below this triggers STRONG_SELL (default: 0.5)

    Args:
        num_levels: Number of order book depth levels to analyze (default: 10).
        strong_buy_threshold: Threshold for strong buy signal (default: 1.5).
        buy_threshold: Threshold for buy signal (default: 1.2).
        sell_threshold: Threshold for sell signal (default: 0.8).
        strong_sell_threshold: Threshold for strong sell signal (default: 0.5).
        feature_store: Optional FeatureStore for caching results.
        cache_ttl: Cache TTL in seconds (default: 60).
    """

    MAX_RATIO = 1e9  # Cap for bid/ask ratio to avoid infinity propagation

    def __init__(
        self,
        num_levels: int = 10,
        strong_buy_threshold: float = 1.5,
        buy_threshold: float = 1.2,
        sell_threshold: float = 0.8,
        strong_sell_threshold: float = 0.5,
        feature_store: FeatureStore | None = None,
        cache_ttl: int = 60,
        name: str | None = None,
    ):
        """Initialize OrderBookImbalance indicator.

        Args:
            num_levels: Number of order book depth levels to analyze.
            strong_buy_threshold: Bid/ask ratio threshold for strong buy.
            buy_threshold: Bid/ask ratio threshold for buy.
            sell_threshold: Bid/ask ratio threshold for sell.
            strong_sell_threshold: Bid/ask ratio threshold for strong sell.
            feature_store: Optional FeatureStore for caching.
            cache_ttl: Cache TTL in seconds.
            name: Optional custom indicator name.

        Raises:
            ValueError: If thresholds are inconsistent or num_levels < 1.
        """
        super().__init__(name=name)
        if num_levels < 1:
            raise ValueError(f"num_levels must be >= 1, got {num_levels}")
        if strong_buy_threshold <= buy_threshold:
            raise ValueError(
                f"strong_buy_threshold ({strong_buy_threshold}) must be > "
                f"buy_threshold ({buy_threshold})"
            )
        if sell_threshold <= strong_sell_threshold:
            raise ValueError(
                f"sell_threshold ({sell_threshold}) must be > "
                f"strong_sell_threshold ({strong_sell_threshold})"
            )
        if buy_threshold <= sell_threshold:
            raise ValueError(
                f"buy_threshold ({buy_threshold}) must be > "
                f"sell_threshold ({sell_threshold})"
            )
        self.num_levels = num_levels
        self.strong_buy_threshold = strong_buy_threshold
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.strong_sell_threshold = strong_sell_threshold
        self._feature_store = feature_store
        self._cache_ttl = cache_ttl

    @property
    def description(self) -> str:
        """Get human-readable description."""
        return (
            "Order book imbalance analysis computing bid/ask ratio and "
            "depth imbalance at multiple L2 depth levels with configurable "
            "thresholds for signal generation."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Get current parameter configuration."""
        return {
            "num_levels": self.num_levels,
            "strong_buy_threshold": self.strong_buy_threshold,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "strong_sell_threshold": self.strong_sell_threshold,
            "cache_ttl": self._cache_ttl,
        }

    def _cache_key(self, symbol: str) -> str:
        """Generate cache key for a symbol's imbalance result.

        Args:
            symbol: Trading pair symbol.

        Returns:
            Cache key string.
        """
        return f"ob_imbalance:{symbol}:{self.num_levels}"

    def _get_cached(self, symbol: str) -> dict[str, Any] | None:
        """Retrieve cached imbalance result for a symbol.

        Args:
            symbol: Trading pair symbol.

        Returns:
            Cached result dict or None.
        """
        if self._feature_store is None:
            return None
        cached = self._feature_store.get(self._cache_key(symbol))
        return cached if isinstance(cached, dict) else None

    def _set_cached(self, symbol: str, result: OrderBookImbalanceResult) -> bool:
        """Cache an imbalance result for a symbol.

        Args:
            symbol: Trading pair symbol.
            result: The result to cache.

        Returns:
            True if caching succeeded.
        """
        if self._feature_store is None:
            return False
        cache_data = {
            "bid_ask_ratio": result.bid_ask_ratio,
            "depth_imbalance": result.depth_imbalance,
            "bid_volume": result.bid_volume,
            "ask_volume": result.ask_volume,
            "imbalance_level": result.imbalance_level.value,
            "spread": result.spread,
            "mid_price": result.mid_price,
            "num_levels": result.num_levels,
            "level_imbalances": result.level_imbalances,
            "timestamp": result.timestamp.isoformat(),
        }
        stored = self._feature_store.set(
            self._cache_key(symbol), cache_data, ttl=self._cache_ttl
        )
        return bool(stored)

    @staticmethod
    def _total_volume(levels: list[PriceLevel]) -> float:
        """Sum the quantity across price levels.

        Args:
            levels: List of PriceLevel entries.

        Returns:
            Total volume at the given levels.
        """
        return sum(lvl.quantity for lvl in levels)

    @staticmethod
    def _bid_ask_ratio(bid_volume: float, ask_volume: float) -> float:
        """Compute the bid/ask volume ratio.

        When ask_volume is zero the ratio is capped at MAX_RATIO (extreme bullish).
        When bid_volume is zero the ratio is 0.0 (extreme bearish).

        Args:
            bid_volume: Total bid volume.
            ask_volume: Total ask volume.

        Returns:
            bid_volume / ask_volume (capped at MAX_RATIO).
        """
        if ask_volume <= 0:
            return OrderBookImbalance.MAX_RATIO if bid_volume > 0 else 1.0
        return bid_volume / ask_volume

    @staticmethod
    def _depth_imbalance(bid_volume: float, ask_volume: float) -> float:
        """Compute normalized depth imbalance in [-1, 1].

        +1 means all volume is on the bid side.
        -1 means all volume is on the ask side.
        0 means perfectly balanced.

        Args:
            bid_volume: Total bid volume.
            ask_volume: Total ask volume.

        Returns:
            Normalized imbalance in [-1, 1].
        """
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        return (bid_volume - ask_volume) / total

    @staticmethod
    def _classify_imbalance(
        ratio: float,
        strong_buy_threshold: float,
        buy_threshold: float,
        sell_threshold: float,
        strong_sell_threshold: float,
    ) -> ImbalanceLevel:
        """Classify imbalance severity from bid/ask ratio.

        Args:
            ratio: Bid/ask volume ratio.
            strong_buy_threshold: Strong buy threshold.
            buy_threshold: Buy threshold.
            sell_threshold: Sell threshold.
            strong_sell_threshold: Strong sell threshold.

        Returns:
            ImbalanceLevel classification.
        """
        if ratio >= strong_buy_threshold:
            return ImbalanceLevel.STRONG_BUY
        if ratio >= buy_threshold:
            return ImbalanceLevel.BUY
        if ratio <= strong_sell_threshold:
            return ImbalanceLevel.STRONG_SELL
        if ratio <= sell_threshold:
            return ImbalanceLevel.SELL
        return ImbalanceLevel.NEUTRAL

    @staticmethod
    def _per_level_imbalances(
        bids: list[PriceLevel],
        asks: list[PriceLevel],
        num_levels: int,
    ) -> dict[int, float]:
        """Compute cumulative depth imbalance at each level.

        At level *n* the imbalance uses the first *n* bid and ask
        price levels.  Returns a dict mapping level index (1-based)
        to the normalized imbalance value.

        Args:
            bids: Bid price levels.
            asks: Ask price levels.
            num_levels: Number of levels to compute.

        Returns:
            Dict mapping level number to imbalance value.
        """
        result: dict[int, float] = {}
        for level in range(1, num_levels + 1):
            bid_vol = OrderBookImbalance._total_volume(bids[:level])
            ask_vol = OrderBookImbalance._total_volume(asks[:level])
            result[level] = OrderBookImbalance._depth_imbalance(bid_vol, ask_vol)
        return result

    def compute(self, data: list[OrderBookSnapshot]) -> OrderBookImbalanceResult:
        """Compute order book imbalance from a list of snapshots.

        Uses the **most recent** snapshot in the list.  This signature
        matches ``BaseIndicator.compute`` which expects a list.

        Args:
            data: List of OrderBookSnapshot (latest is used).

        Returns:
            OrderBookImbalanceResult for the latest snapshot.

        Raises:
            ValueError: If data is empty or levels are insufficient.
        """
        if not data:
            raise ValueError("No order book snapshots provided")
        snapshot = data[-1]
        return self.analyze(snapshot)

    def analyze(self, snapshot: OrderBookSnapshot) -> OrderBookImbalanceResult:
        """Analyze a single order book snapshot for imbalance.

        Checks cache first (if FeatureStore is configured), then computes
        bid/ask ratio, depth imbalance, per-level imbalances, spread,
        and mid-price.

        Args:
            snapshot: OrderBookSnapshot to analyze.

        Returns:
            OrderBookImbalanceResult.

        Raises:
            ValueError: If snapshot has insufficient depth levels.
        """
        # Check cache
        cached = self._get_cached(snapshot.symbol)
        if cached is not None:
            return OrderBookImbalanceResult(
                bid_ask_ratio=cached["bid_ask_ratio"],
                depth_imbalance=cached["depth_imbalance"],
                bid_volume=cached["bid_volume"],
                ask_volume=cached["ask_volume"],
                level_imbalances=cached["level_imbalances"],
                imbalance_level=ImbalanceLevel(cached["imbalance_level"]),
                spread=cached["spread"],
                mid_price=cached["mid_price"],
                num_levels=cached["num_levels"],
                timestamp=datetime.fromisoformat(cached["timestamp"]),
            )

        # Validate depth
        if len(snapshot.bids) < self.num_levels:
            raise ValueError(
                f"Snapshot has {len(snapshot.bids)} bid levels, "
                f"need at least {self.num_levels}"
            )
        if len(snapshot.asks) < self.num_levels:
            raise ValueError(
                f"Snapshot has {len(snapshot.asks)} ask levels, "
                f"need at least {self.num_levels}"
            )

        # Truncate to requested depth
        bids = snapshot.bids[: self.num_levels]
        asks = snapshot.asks[: self.num_levels]

        # Compute volumes
        bid_volume = self._total_volume(bids)
        ask_volume = self._total_volume(asks)

        # Compute ratios
        ratio = self._bid_ask_ratio(bid_volume, ask_volume)
        imbalance = self._depth_imbalance(bid_volume, ask_volume)
        level_imb = self._per_level_imbalances(
            snapshot.bids, snapshot.asks, self.num_levels
        )

        # Classify
        level = self._classify_imbalance(
            ratio,
            self.strong_buy_threshold,
            self.buy_threshold,
            self.sell_threshold,
            self.strong_sell_threshold,
        )

        # Spread & mid
        spread = asks[0].price - bids[0].price
        mid_price = (asks[0].price + bids[0].price) / 2.0

        result = OrderBookImbalanceResult(
            bid_ask_ratio=ratio,
            depth_imbalance=imbalance,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            level_imbalances=level_imb,
            imbalance_level=level,
            spread=spread,
            mid_price=mid_price,
            num_levels=self.num_levels,
            timestamp=datetime.now(UTC),
        )

        # Cache result
        self._set_cached(snapshot.symbol, result)

        return result

    def validate(self, data: list[OrderBookSnapshot]) -> bool:
        """Validate that data is sufficient for calculation.

        Args:
            data: List of OrderBookSnapshot.

        Returns:
            True if the latest snapshot has enough depth levels.
        """
        if not data:
            return False
        snapshot = data[-1]
        return (
            len(snapshot.bids) >= self.num_levels
            and len(snapshot.asks) >= self.num_levels
        )

    def get_metadata(self) -> dict[str, Any]:
        """Get indicator metadata for serialization.

        Returns:
            Dictionary with name, description, and parameters.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_signal(self, result: OrderBookImbalanceResult) -> Signal:
        """Convert imbalance result to standardized Signal.

        Maps imbalance levels to signal directions and computes
        confidence from the depth imbalance magnitude.

        Args:
            result: OrderBookImbalanceResult to convert.

        Returns:
            Standardized Signal with direction and confidence.
        """
        direction_map: dict[ImbalanceLevel, tuple[SignalDirection, float]] = {
            ImbalanceLevel.STRONG_BUY: (
                SignalDirection.BUY,
                min(0.95, 0.6 + abs(result.depth_imbalance) * 0.35),
            ),
            ImbalanceLevel.BUY: (
                SignalDirection.BUY,
                min(0.8, 0.5 + abs(result.depth_imbalance) * 0.3),
            ),
            ImbalanceLevel.NEUTRAL: (SignalDirection.HOLD, 0.5),
            ImbalanceLevel.SELL: (
                SignalDirection.SELL,
                min(0.8, 0.5 + abs(result.depth_imbalance) * 0.3),
            ),
            ImbalanceLevel.STRONG_SELL: (
                SignalDirection.SELL,
                min(0.95, 0.6 + abs(result.depth_imbalance) * 0.35),
            ),
        }

        direction, confidence = direction_map.get(
            result.imbalance_level, (SignalDirection.HOLD, 0.5)
        )

        return Signal(
            direction=direction,
            confidence=confidence,
            timestamp=result.timestamp,
            metadata={
                "indicator": self.name,
                "bid_ask_ratio": result.bid_ask_ratio,
                "depth_imbalance": result.depth_imbalance,
                "imbalance_level": result.imbalance_level.value,
                "spread": result.spread,
                "mid_price": result.mid_price,
                "num_levels": result.num_levels,
            },
        )
