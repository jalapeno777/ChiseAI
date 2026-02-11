"""Order book snapshot and tracking."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OrderBookLevel:
    """Single price level in order book.

    Attributes:
        price: Price level
        quantity: Quantity at this price
    """

    price: float
    quantity: float


@dataclass
class OrderBookSnapshot:
    """Order book snapshot at a point in time.

    Attributes:
        symbol: Trading pair symbol
        timestamp: Snapshot timestamp
        last_update_id: Last update ID from exchange
        bids: List of bid levels (price, quantity), sorted descending by price
        asks: List of ask levels (price, quantity), sorted ascending by price
        latency_ms: Request latency in milliseconds
    """

    symbol: str
    timestamp: datetime
    last_update_id: int
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def best_bid(self) -> float | None:
        """Get best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Get best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> float | None:
        """Calculate mid price between best bid and ask."""
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> float | None:
        """Calculate bid-ask spread."""
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> float | None:
        """Calculate bid-ask spread as percentage of mid price."""
        mid = self.mid_price
        spread = self.spread
        if mid is not None and spread is not None and mid > 0:
            return (spread / mid) * 100
        return None

    def get_bid_depth(self, price_threshold: float) -> float:
        """Calculate total bid quantity above price threshold.

        Args:
            price_threshold: Minimum price to include

        Returns:
            Total quantity of bids at or above threshold
        """
        return sum(
            level.quantity for level in self.bids if level.price >= price_threshold
        )

    def get_ask_depth(self, price_threshold: float) -> float:
        """Calculate total ask quantity below price threshold.

        Args:
            price_threshold: Maximum price to include

        Returns:
            Total quantity of asks at or below threshold
        """
        return sum(
            level.quantity for level in self.asks if level.price <= price_threshold
        )

    def to_dict(self) -> dict:
        """Convert snapshot to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "last_update_id": self.last_update_id,
            "bids": [(level.price, level.quantity) for level in self.bids],
            "asks": [(level.price, level.quantity) for level in self.asks],
            "latency_ms": self.latency_ms,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid_price": self.mid_price,
            "spread_pct": self.spread_pct,
        }


class OrderBookTracker:
    """Track order book snapshots for multiple symbols.

    Maintains recent order book history and provides
    gap detection for data quality monitoring.
    """

    def __init__(self, max_history: int = 1000) -> None:
        """Initialize tracker.

        Args:
            max_history: Maximum snapshots to retain per symbol
        """
        self.max_history = max_history
        self._snapshots: dict[str, list[OrderBookSnapshot]] = {}
        self._last_update_ids: dict[str, int] = {}

    def add_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Add a new snapshot to tracking.

        Args:
            snapshot: Order book snapshot to add
        """
        symbol = snapshot.symbol
        if symbol not in self._snapshots:
            self._snapshots[symbol] = []

        self._snapshots[symbol].append(snapshot)
        self._last_update_ids[symbol] = snapshot.last_update_id

        # Trim history if needed
        if len(self._snapshots[symbol]) > self.max_history:
            self._snapshots[symbol] = self._snapshots[symbol][-self.max_history :]

    def get_latest(self, symbol: str) -> OrderBookSnapshot | None:
        """Get most recent snapshot for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest snapshot or None if no data
        """
        snapshots = self._snapshots.get(symbol, [])
        return snapshots[-1] if snapshots else None

    def get_history(self, symbol: str, count: int = 100) -> list[OrderBookSnapshot]:
        """Get recent snapshot history for a symbol.

        Args:
            symbol: Trading pair symbol
            count: Number of snapshots to retrieve

        Returns:
            List of recent snapshots (newest last)
        """
        snapshots = self._snapshots.get(symbol, [])
        return snapshots[-count:] if snapshots else []

    def detect_gaps(self, symbol: str, max_gap_sec: float = 5.0) -> list[dict]:
        """Detect gaps in order book data.

        Args:
            symbol: Trading pair symbol
            max_gap_sec: Maximum acceptable gap in seconds

        Returns:
            List of detected gaps with start/end times
        """
        snapshots = self._snapshots.get(symbol, [])
        gaps = []

        for i in range(1, len(snapshots)):
            prev = snapshots[i - 1]
            curr = snapshots[i]
            gap_sec = (curr.timestamp - prev.timestamp).total_seconds()

            if gap_sec > max_gap_sec:
                gaps.append(
                    {
                        "start": prev.timestamp.isoformat(),
                        "end": curr.timestamp.isoformat(),
                        "duration_sec": gap_sec,
                        "symbol": symbol,
                    }
                )

        return gaps

    def has_duplicates(self, symbol: str) -> bool:
        """Check for duplicate update IDs (indicates data issues).

        Args:
            symbol: Trading pair symbol

        Returns:
            True if duplicate update IDs found
        """
        snapshots = self._snapshots.get(symbol, [])
        update_ids = [s.last_update_id for s in snapshots]
        return len(update_ids) != len(set(update_ids))

    def get_all_symbols(self) -> list[str]:
        """Get list of all tracked symbols."""
        return list(self._snapshots.keys())
