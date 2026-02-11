"""Liquidity metrics calculation."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from exchange_data.binance.orderbook import OrderBookSnapshot


@dataclass
class LiquidityMetrics:
    """Liquidity metrics for a trading pair.

    Attributes:
        symbol: Trading pair symbol
        timestamp: Metrics timestamp
        bid_ask_spread: Absolute bid-ask spread
        bid_ask_spread_pct: Spread as percentage of mid price
        bid_depth_1pct: Total bid quantity within 1% of best bid
        ask_depth_1pct: Total ask quantity within 1% of best ask
        bid_depth_5pct: Total bid quantity within 5% of best bid
        ask_depth_5pct: Total ask quantity within 5% of best ask
        bid_depth_10pct: Total bid quantity within 10% of best bid
        ask_depth_10pct: Total ask quantity within 10% of best ask
        imbalance_ratio: Bid depth / Ask depth (1.0 = balanced)
        slippage_1000usd: Estimated slippage for $1000 order
        slippage_10000usd: Estimated slippage for $10000 order
    """

    symbol: str
    timestamp: str
    bid_ask_spread: float
    bid_ask_spread_pct: float
    bid_depth_1pct: float
    ask_depth_1pct: float
    bid_depth_5pct: float
    ask_depth_5pct: float
    bid_depth_10pct: float
    ask_depth_10pct: float
    imbalance_ratio: float
    slippage_1000usd: float
    slippage_10000usd: float

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "bid_ask_spread": self.bid_ask_spread,
            "bid_ask_spread_pct": self.bid_ask_spread_pct,
            "bid_depth_1pct": self.bid_depth_1pct,
            "ask_depth_1pct": self.ask_depth_1pct,
            "bid_depth_5pct": self.bid_depth_5pct,
            "ask_depth_5pct": self.ask_depth_5pct,
            "bid_depth_10pct": self.bid_depth_10pct,
            "ask_depth_10pct": self.ask_depth_10pct,
            "imbalance_ratio": self.imbalance_ratio,
            "slippage_1000usd": self.slippage_1000usd,
            "slippage_10000usd": self.slippage_10000usd,
        }


class LiquidityCalculator:
    """Calculate liquidity metrics from order book data."""

    def __init__(self) -> None:
        """Initialize calculator."""
        self.depth_thresholds = [0.01, 0.05, 0.10]  # 1%, 5%, 10%

    def calculate(self, snapshot: OrderBookSnapshot) -> Optional[LiquidityMetrics]:
        """Calculate liquidity metrics from order book snapshot.

        Args:
            snapshot: Order book snapshot

        Returns:
            Liquidity metrics or None if snapshot is invalid
        """
        if not snapshot.bids or not snapshot.asks:
            return None

        mid_price = snapshot.mid_price
        if mid_price is None or mid_price <= 0:
            return None

        best_bid = snapshot.best_bid
        best_ask = snapshot.best_ask
        if best_bid is None or best_ask is None:
            return None

        spread = best_ask - best_bid
        spread_pct = (spread / mid_price) * 100 if mid_price > 0 else 0

        # Calculate depth at various thresholds
        bid_depths = []
        ask_depths = []

        for threshold in self.depth_thresholds:
            bid_threshold = best_bid * (1 - threshold)
            ask_threshold = best_ask * (1 + threshold)

            bid_depth = snapshot.get_bid_depth(bid_threshold)
            ask_depth = snapshot.get_ask_depth(ask_threshold)

            bid_depths.append(bid_depth)
            ask_depths.append(ask_depth)

        # Calculate imbalance ratio
        total_bid_depth = bid_depths[1]  # Use 5% depth for imbalance
        total_ask_depth = ask_depths[1]
        imbalance = (
            total_bid_depth / total_ask_depth if total_ask_depth > 0 else float("inf")
        )

        # Estimate slippage
        slippage_1k = self._estimate_slippage(snapshot, 1000.0, mid_price)
        slippage_10k = self._estimate_slippage(snapshot, 10000.0, mid_price)

        return LiquidityMetrics(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp.isoformat(),
            bid_ask_spread=spread,
            bid_ask_spread_pct=spread_pct,
            bid_depth_1pct=bid_depths[0],
            ask_depth_1pct=ask_depths[0],
            bid_depth_5pct=bid_depths[1],
            ask_depth_5pct=ask_depths[1],
            bid_depth_10pct=bid_depths[2],
            ask_depth_10pct=ask_depths[2],
            imbalance_ratio=imbalance,
            slippage_1000usd=slippage_1k,
            slippage_10000usd=slippage_10k,
        )

    def _estimate_slippage(
        self, snapshot: OrderBookSnapshot, order_value_usd: float, mid_price: float
    ) -> float:
        """Estimate slippage for a given order size.

        Args:
            snapshot: Order book snapshot
            order_value_usd: Order value in USD
            mid_price: Current mid price

        Returns:
            Estimated slippage as percentage
        """
        if mid_price <= 0:
            return 0.0

        # Calculate quantity needed
        quantity_needed = order_value_usd / mid_price

        # Walk the book to find average execution price
        total_quantity = 0.0
        total_cost = 0.0

        # Use asks for buy order simulation
        for level in snapshot.asks:
            qty = min(level.quantity, quantity_needed - total_quantity)
            total_cost += qty * level.price
            total_quantity += qty

            if total_quantity >= quantity_needed:
                break

        if total_quantity <= 0:
            return 0.0

        avg_price = total_cost / total_quantity
        slippage = ((avg_price - mid_price) / mid_price) * 100

        return max(0.0, slippage)

    def calculate_depth_imbalance(
        self, snapshot: OrderBookSnapshot, threshold_pct: float = 0.05
    ) -> float:
        """Calculate bid/ask depth imbalance at given threshold.

        Args:
            snapshot: Order book snapshot
            threshold_pct: Price threshold percentage

        Returns:
            Imbalance ratio (bid_depth / ask_depth, 1.0 = balanced)
        """
        mid_price = snapshot.mid_price
        if mid_price is None or mid_price <= 0:
            return 1.0

        best_bid = snapshot.best_bid
        best_ask = snapshot.best_ask
        if best_bid is None or best_ask is None:
            return 1.0

        bid_threshold = best_bid * (1 - threshold_pct)
        ask_threshold = best_ask * (1 + threshold_pct)

        bid_depth = snapshot.get_bid_depth(bid_threshold)
        ask_depth = snapshot.get_ask_depth(ask_threshold)

        if ask_depth <= 0:
            return float("inf") if bid_depth > 0 else 1.0

        return bid_depth / ask_depth

    def get_liquidity_score(self, metrics: LiquidityMetrics) -> float:
        """Calculate overall liquidity score (0-100).

        Higher score indicates better liquidity.

        Args:
            metrics: Liquidity metrics

        Returns:
            Liquidity score from 0-100
        """
        # Factors (lower is better for most)
        spread_score = max(0, 100 - metrics.bid_ask_spread_pct * 10)  # <0.1% = 100
        depth_score = min(100, (metrics.bid_depth_5pct + metrics.ask_depth_5pct) / 100)
        slippage_score = max(0, 100 - metrics.slippage_10000usd * 100)  # <1% = 100

        # Weighted average
        score = spread_score * 0.4 + depth_score * 0.3 + slippage_score * 0.3
        return min(100, max(0, score))
