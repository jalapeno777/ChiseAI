"""Win Rate Calculator for the core report generation engine.

Calculates:
- Win/loss counts by period
- Win rate percentages
- Average win/loss sizes
- Win/loss streaks

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WinRateResult:
    """Result of win rate calculation.

    Attributes:
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Win rate as percentage
        loss_rate: Loss rate as percentage
        avg_win: Average win size
        avg_loss: Average loss size
        avg_win_loss_ratio: Ratio of avg win to avg loss
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        best_streak: Longest winning streak
        worst_streak: Longest losing streak
    """

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    avg_win_loss_ratio: float = 0.0
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    best_streak: int = 0
    worst_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "loss_rate": round(self.loss_rate, 2),
            "avg_win": float(self.avg_win),
            "avg_loss": float(self.avg_loss),
            "avg_win_loss_ratio": round(self.avg_win_loss_ratio, 2),
            "largest_win": float(self.largest_win),
            "largest_loss": float(self.largest_loss),
            "best_streak": self.best_streak,
            "worst_streak": self.worst_streak,
        }


@dataclass
class TradeResult:
    """Result of a single trade for win rate analysis.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        pnl: Profit/loss from the trade
        timestamp: Trade close timestamp
        is_win: Whether the trade was a win
    """

    trade_id: str
    symbol: str
    pnl: Decimal
    timestamp: datetime | None = None
    is_win: bool = False

    def __post_init__(self) -> None:
        """Set is_win based on pnl."""
        self.is_win = self.pnl > 0


@dataclass
class WinRateBreakdown:
    """Win rate breakdown by category.

    Attributes:
        category: Category name (e.g., symbol, direction)
        value: Category value
        total_trades: Number of trades
        win_rate: Win rate percentage
        avg_pnl: Average P&L
    """

    category: str = ""
    value: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: Decimal = Decimal("0")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category,
            "value": self.value,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 2),
            "avg_pnl": float(self.avg_pnl),
        }


class WinRateCalculator:
    """Calculate win rate statistics.

    Supports:
    - Overall win rate calculation
    - Win rate by symbol, direction, etc.
    - Win/loss streaks
    - Average win/loss sizes

    Attributes:
        min_trade_count: Minimum trades for reliable statistics
    """

    def __init__(
        self,
        min_trade_count: int = 5,
    ) -> None:
        """Initialize win rate calculator.

        Args:
            min_trade_count: Minimum trades for reliable statistics
        """
        self._min_trade_count = min_trade_count
        self._trades: list[TradeResult] = []

        logger.info(f"WinRateCalculator initialized: min_trades={min_trade_count}")

    def add_trade(
        self,
        trade_id: str,
        symbol: str,
        pnl: float | Decimal,
        timestamp: datetime | None = None,
    ) -> TradeResult:
        """Add a trade result.

        Args:
            trade_id: Unique trade identifier
            symbol: Trading symbol
            pnl: Profit/loss from the trade
            timestamp: Trade close timestamp

        Returns:
            Created TradeResult
        """
        pnl_dec = Decimal(str(pnl))
        trade = TradeResult(
            trade_id=trade_id,
            symbol=symbol,
            pnl=pnl_dec,
            timestamp=timestamp,
            is_win=pnl_dec > 0,
        )

        self._trades.append(trade)
        return trade

    def add_trades(
        self,
        trades: list[tuple[str, str, float | Decimal, datetime | None]],
    ) -> None:
        """Add multiple trades.

        Args:
            trades: List of (trade_id, symbol, pnl, timestamp) tuples
        """
        for trade_id, symbol, pnl, timestamp in trades:
            self.add_trade(trade_id, symbol, pnl, timestamp)

    def clear(self) -> None:
        """Clear all trade data."""
        self._trades.clear()

    def calculate_win_rate(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> WinRateResult:
        """Calculate win rate statistics.

        Args:
            period_start: Start of the period (optional)
            period_end: End of the period (optional)

        Returns:
            WinRateResult with calculated statistics
        """
        # Filter by period if dates provided
        trades = self._trades

        if period_start:
            trades = [t for t in trades if t.timestamp and t.timestamp >= period_start]

        if period_end:
            trades = [t for t in trades if t.timestamp and t.timestamp <= period_end]

        return self._calculate_from_trades(trades)

    def _calculate_from_trades(
        self,
        trades: list[TradeResult],
    ) -> WinRateResult:
        """Calculate win rate from a list of trades.

        Args:
            trades: List of TradeResult objects

        Returns:
            WinRateResult with calculated statistics
        """
        if not trades:
            return WinRateResult()

        winning_trades = [t for t in trades if t.is_win]
        losing_trades = [t for t in trades if not t.is_win]

        total = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = (win_count / total * 100) if total > 0 else 0.0
        loss_rate = (loss_count / total * 100) if total > 0 else 0.0

        # Calculate average win/loss
        avg_win = Decimal("0")
        avg_loss = Decimal("0")

        if winning_trades:
            avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades)

        if losing_trades:
            avg_loss = abs(sum(t.pnl for t in losing_trades) / len(losing_trades))

        # Calculate win/loss ratio
        avg_ratio = float(avg_win / avg_loss) if avg_loss > 0 else 0.0

        # Find largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=Decimal("0"))
        largest_loss = min((t.pnl for t in losing_trades), default=Decimal("0"))

        # Calculate streaks
        best_streak, worst_streak = self._calculate_streaks(trades)

        result = WinRateResult(
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_loss_ratio=avg_ratio,
            largest_win=largest_win,
            largest_loss=abs(largest_loss),
            best_streak=best_streak,
            worst_streak=worst_streak,
        )

        logger.debug(
            f"Win rate calculated: {win_rate:.1f}% ({win_count}/{total}), "
            f"avg_win=${avg_win}, avg_loss=${avg_loss}"
        )

        return result

    def _calculate_streaks(self, trades: list[TradeResult]) -> tuple[int, int]:
        """Calculate winning and losing streaks.

        Args:
            trades: List of trades in chronological order

        Returns:
            Tuple of (best_streak, worst_streak)
        """
        if not trades:
            return 0, 0

        # Sort by timestamp if available
        sorted_trades = sorted(
            trades,
            key=lambda t: t.timestamp or datetime.min,
        )

        best_streak = 0
        worst_streak = 0
        current_streak = 0
        is_current_win = False

        for trade in sorted_trades:
            if trade.is_win == is_current_win:
                current_streak += 1
            else:
                if is_current_win:
                    best_streak = max(best_streak, current_streak)
                else:
                    worst_streak = max(worst_streak, current_streak)
                current_streak = 1
                is_current_win = trade.is_win

        # Don't forget the last streak
        if is_current_win:
            best_streak = max(best_streak, current_streak)
        else:
            worst_streak = max(worst_streak, current_streak)

        return best_streak, worst_streak

    def calculate_by_symbol(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[WinRateBreakdown]:
        """Calculate win rate breakdown by symbol.

        Args:
            period_start: Start of the period (optional)
            period_end: End of the period (optional)

        Returns:
            List of WinRateBreakdown by symbol
        """
        # Filter by period if dates provided
        trades = self._trades

        if period_start:
            trades = [t for t in trades if t.timestamp and t.timestamp >= period_start]

        if period_end:
            trades = [t for t in trades if t.timestamp and t.timestamp <= period_end]

        # Group by symbol
        by_symbol: dict[str, list[TradeResult]] = {}
        for trade in trades:
            if trade.symbol not in by_symbol:
                by_symbol[trade.symbol] = []
            by_symbol[trade.symbol].append(trade)

        # Calculate breakdown for each symbol
        breakdowns: list[WinRateBreakdown] = []

        for symbol, symbol_trades in by_symbol.items():
            if len(symbol_trades) < self._min_trade_count:
                continue

            winning = len([t for t in symbol_trades if t.is_win])
            total = len(symbol_trades)
            win_rate = (winning / total * 100) if total > 0 else 0.0
            avg_pnl = sum(t.pnl for t in symbol_trades) / total

            breakdown = WinRateBreakdown(
                category="symbol",
                value=symbol,
                total_trades=total,
                win_rate=win_rate,
                avg_pnl=avg_pnl,
            )
            breakdowns.append(breakdown)

        # Sort by win rate descending
        breakdowns.sort(key=lambda b: b.win_rate, reverse=True)

        return breakdowns

    def calculate_by_direction(
        self,
        trades: list[tuple[str, str, float | Decimal, datetime | None, str]],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[WinRateBreakdown]:
        """Calculate win rate breakdown by direction.

        Args:
            trades: List of (trade_id, symbol, pnl, timestamp, direction) tuples
            period_start: Start of the period (optional)
            period_end: End of the period (optional)

        Returns:
            List of WinRateBreakdown by direction
        """
        # Filter by period
        filtered_trades = trades

        if period_start:
            filtered_trades = [
                t for t in filtered_trades if t[3] and t[3] >= period_start
            ]

        if period_end:
            filtered_trades = [
                t for t in filtered_trades if t[3] and t[3] <= period_end
            ]

        # Group by direction
        by_direction: dict[str, list[TradeResult]] = {}

        for trade_id, symbol, pnl, timestamp, direction in filtered_trades:
            pnl_dec = Decimal(str(pnl))
            trade = TradeResult(
                trade_id=trade_id,
                symbol=symbol,
                pnl=pnl_dec,
                timestamp=timestamp,
                is_win=pnl_dec > 0,
            )

            if direction not in by_direction:
                by_direction[direction] = []
            by_direction[direction].append(trade)

        # Calculate breakdown for each direction
        breakdowns: list[WinRateBreakdown] = []

        for direction, direction_trades in by_direction.items():
            if len(direction_trades) < self._min_trade_count:
                continue

            winning = len([t for t in direction_trades if t.is_win])
            total = len(direction_trades)
            win_rate = (winning / total * 100) if total > 0 else 0.0
            avg_pnl = sum(t.pnl for t in direction_trades) / total

            breakdown = WinRateBreakdown(
                category="direction",
                value=direction,
                total_trades=total,
                win_rate=win_rate,
                avg_pnl=avg_pnl,
            )
            breakdowns.append(breakdown)

        return breakdowns

    def get_expectancy(self) -> float:
        """Calculate trade expectancy.

        Returns:
            Expectancy per trade (win_rate * avg_win - loss_rate * avg_loss)
        """
        if not self._trades:
            return 0.0

        result = self._calculate_from_trades(self._trades)

        win_prob = result.win_rate / 100
        loss_prob = result.loss_rate / 100

        expectancy = win_prob * float(result.avg_win) - loss_prob * float(
            result.avg_loss
        )

        return round(expectancy, 4)
