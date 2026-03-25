"""Cumulative Volume Delta (CVD) calculator.

CVD tracks the net volume delta at tick level by classifying trades as
buy (taker buys) or sell (taker sells) and accumulating the delta over time.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np


class TradeDirection(Enum):
    """Direction of trade execution."""

    BUY = "buy"  # Taker is buying (price goes up)
    SELL = "sell"  # Taker is selling (price goes down)


@dataclass
class Trade:
    """Single trade data point.

    Attributes:
        trade_id: Unique trade identifier
        price: Trade execution price
        quantity: Trade quantity/volume
        timestamp: Trade execution timestamp
        is_buyer_maker: True if buyer was maker (seller initiated)
                        False if seller was maker (buyer initiated)
    """

    trade_id: int
    price: float
    quantity: float
    timestamp: datetime
    is_buyer_maker: bool

    @property
    def direction(self) -> TradeDirection:
        """Classify trade direction based on who initiated.

        If is_buyer_maker=True, the buyer was the maker (seller initiated),
        so the taker (aggressor) is the seller, meaning price went down.
        If is_buyer_maker=False, the seller was the maker (buyer initiated),
        so the taker is the buyer, meaning price went up.
        """
        return TradeDirection.SELL if self.is_buyer_maker else TradeDirection.BUY

    @property
    def volume_delta(self) -> float:
        """Get signed volume delta.

        Positive for buy volume, negative for sell volume.
        """
        return self.quantity if self.direction == TradeDirection.BUY else -self.quantity


@dataclass
class CVDResult:
    """Result of CVD calculation.

    Attributes:
        timestamps: List of timestamps corresponding to each CVD point
        cvd_values: Cumulative CVD values at each timestamp
        trade_count: Number of trades processed
        buy_volume: Total buy volume
        sell_volume: Total sell volume
        net_volume: Net volume (buy_volume - sell_volume)
    """

    timestamps: list[datetime]
    cvd_values: list[float]
    trade_count: int
    buy_volume: float
    sell_volume: float
    net_volume: float

    def __post_init__(self) -> None:
        """Validate and convert to numpy arrays."""
        if isinstance(self.timestamps, list):
            self.timestamps = self.timestamps
        if isinstance(self.cvd_values, list):
            self.cvd_values = self.cvd_values


class CVDCalculator:
    """Calculator for Cumulative Volume Delta (CVD).

    CVD is calculated by:
    1. Getting tick-level trades from exchange
    2. Classifying each trade as buy or sell based on price movement
    3. Accumulating the net volume delta over time
    """

    def __init__(self, name: str | None = None):
        """Initialize CVD calculator.

        Args:
            name: Optional custom name
        """
        self._name = name or "CVDCalculator"

    @property
    def name(self) -> str:
        """Get calculator name."""
        return self._name

    @property
    def description(self) -> str:
        """Get human-readable description."""
        return (
            "Cumulative Volume Delta (CVD) tracks net volume flow by "
            "accumulating tick-level buy/sell volume deltas to identify "
            "institutional buying/selling pressure."
        )

    def calculate_from_trades(self, trades: list[Trade]) -> CVDResult:
        """Calculate CVD from a list of trades.

        Args:
            trades: List of trade data points (should be time-ordered)

        Returns:
            CVDResult with cumulative CVD values
        """
        if not trades:
            return CVDResult(
                timestamps=[],
                cvd_values=[],
                trade_count=0,
                buy_volume=0.0,
                sell_volume=0.0,
                net_volume=0.0,
            )

        # Sort trades by timestamp if not already sorted
        sorted_trades = sorted(trades, key=lambda t: t.timestamp)

        timestamps = [t.timestamp for t in sorted_trades]
        deltas = np.array([t.volume_delta for t in sorted_trades])
        cvd_values = np.cumsum(deltas).tolist()

        buy_volume = sum(
            t.quantity for t in sorted_trades if t.direction == TradeDirection.BUY
        )
        sell_volume = sum(
            t.quantity for t in sorted_trades if t.direction == TradeDirection.SELL
        )

        return CVDResult(
            timestamps=timestamps,
            cvd_values=cvd_values,
            trade_count=len(trades),
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            net_volume=buy_volume - sell_volume,
        )

    def calculate_from_arrays(
        self,
        timestamps: list[datetime],
        prices: list[float],
        quantities: list[float],
        is_buyer_maker: list[bool],
    ) -> CVDResult:
        """Calculate CVD from raw arrays.

        Args:
            timestamps: List of trade timestamps
            prices: List of trade prices
            quantities: List of trade quantities
            is_buyer_maker: List of is_buyer_maker flags

        Returns:
            CVDResult with cumulative CVD values
        """
        if (
            len({len(timestamps), len(prices), len(quantities), len(is_buyer_maker)})
            != 1
        ):
            raise ValueError("All input arrays must have the same length")

        trades = [
            Trade(
                trade_id=i,
                price=prices[i],
                quantity=quantities[i],
                timestamp=timestamps[i],
                is_buyer_maker=is_buyer_maker[i],
            )
            for i in range(len(timestamps))
        ]

        return self.calculate_from_trades(trades)

    def get_cvd_rate(self, cvd_result: CVDResult, window_size: int = 10) -> list[float]:
        """Calculate rate of CVD change over a sliding window.

        Args:
            cvd_result: CVD calculation result
            window_size: Number of trades in the window

        Returns:
            List of CVD change rates
        """
        if len(cvd_result.cvd_values) < window_size:
            return [0.0] * len(cvd_result.cvd_values)

        cvd = np.array(cvd_result.cvd_values)
        rates = np.diff(cvd, prepend=cvd[0])
        return rates.tolist()

    def detect_divergence(
        self,
        cvd_values: list[float],
        prices: list[float],
        threshold: float = 0.0,
    ) -> list[tuple[int, str]]:
        """Detect basic divergence between CVD and price.

        Args:
            cvd_values: CVD values
            prices: Price values (should be same length as cvd_values)
            threshold: Minimum delta to consider divergence (default 0)

        Returns:
            List of (index, direction) tuples where divergence detected
        """
        if len(cvd_values) != len(prices) or len(cvd_values) < 3:
            return []

        divergences = []
        cvd = np.array(cvd_values)
        price = np.array(prices)

        # Calculate normalized changes
        cvd_pct = np.diff(cvd, prepend=cvd[0]) / (np.abs(cvd) + 1e-10)
        price_pct = np.diff(price, prepend=price[0]) / (np.abs(price) + 1e-10)

        # Detect divergence
        for i in range(1, len(cvd_values)):
            delta = cvd_pct[i] - price_pct[i]
            if abs(delta) > threshold:
                if cvd_pct[i] > 0 and price_pct[i] < 0:
                    divergences.append((i, "bullish"))  # CVD up, price down
                elif cvd_pct[i] < 0 and price_pct[i] > 0:
                    divergences.append((i, "bearish"))  # CVD down, price up

        return divergences
