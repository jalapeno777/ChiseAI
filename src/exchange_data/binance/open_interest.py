"""Open interest data aggregation."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class OpenInterestData:
    """Open interest data point.

    Attributes:
        symbol: Trading pair symbol
        timestamp: Data timestamp
        open_interest: Open interest value (in contracts)
        open_interest_usd: Open interest in USD terms
        price: Reference price for USD conversion
    """

    symbol: str
    timestamp: datetime
    open_interest: float
    open_interest_usd: float = 0.0
    price: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open_interest": self.open_interest,
            "open_interest_usd": self.open_interest_usd,
            "price": self.price,
        }


@dataclass
class OIAggregation:
    """Aggregated open interest statistics.

    Attributes:
        symbol: Trading pair symbol
        window_start: Aggregation window start
        window_end: Aggregation window end
        avg_oi: Average open interest
        min_oi: Minimum open interest
        max_oi: Maximum open interest
        change_pct: Percentage change over window
        data_points: Number of data points
    """

    symbol: str
    window_start: datetime
    window_end: datetime
    avg_oi: float
    min_oi: float
    max_oi: float
    change_pct: float
    data_points: int

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "avg_oi": self.avg_oi,
            "min_oi": self.min_oi,
            "max_oi": self.max_oi,
            "change_pct": self.change_pct,
            "data_points": self.data_points,
        }


class OpenInterestAggregator:
    """Aggregate open interest data over time windows."""

    def __init__(self, window_minutes: int = 60) -> None:
        """Initialize aggregator.

        Args:
            window_minutes: Aggregation window size in minutes
        """
        self.window_minutes = window_minutes
        self._data: dict[str, list[OpenInterestData]] = {}

    def add(self, oi_data: OpenInterestData) -> None:
        """Add open interest data point.

        Args:
            oi_data: Open interest data point
        """
        symbol = oi_data.symbol
        if symbol not in self._data:
            self._data[symbol] = []

        self._data[symbol].append(oi_data)

        # Clean old data (keep 2x window)
        cutoff = datetime.utcnow() - timedelta(minutes=self.window_minutes * 2)
        self._data[symbol] = [d for d in self._data[symbol] if d.timestamp > cutoff]

    def get_aggregation(
        self, symbol: str, window_minutes: int | None = None
    ) -> OIAggregation | None:
        """Get aggregated statistics for a symbol.

        Args:
            symbol: Trading pair symbol
            window_minutes: Override default window size

        Returns:
            Aggregated statistics or None if insufficient data
        """
        data = self._data.get(symbol, [])
        if not data:
            return None

        window = window_minutes or self.window_minutes
        cutoff = datetime.utcnow() - timedelta(minutes=window)
        window_data = [d for d in data if d.timestamp >= cutoff]

        if len(window_data) < 2:
            return None

        oi_values = [d.open_interest for d in window_data]
        avg_oi = sum(oi_values) / len(oi_values)
        min_oi = min(oi_values)
        max_oi = max(oi_values)

        # Calculate change percentage
        first_oi = window_data[0].open_interest
        last_oi = window_data[-1].open_interest
        change_pct = ((last_oi - first_oi) / first_oi) * 100 if first_oi > 0 else 0

        return OIAggregation(
            symbol=symbol,
            window_start=window_data[0].timestamp,
            window_end=window_data[-1].timestamp,
            avg_oi=avg_oi,
            min_oi=min_oi,
            max_oi=max_oi,
            change_pct=change_pct,
            data_points=len(window_data),
        )

    def get_all_symbols(self) -> list[str]:
        """Get list of all symbols with data."""
        return list(self._data.keys())

    def get_latest(self, symbol: str) -> OpenInterestData | None:
        """Get most recent data point for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest data point or None
        """
        data = self._data.get(symbol, [])
        return data[-1] if data else None
