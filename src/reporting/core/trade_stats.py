"""Trade Stats Aggregator for the core report generation engine.

Aggregates:
- Total trades, average trade duration
- Profit factor, Sharpe ratio (basic)
- Trade distribution metrics

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TradeStatsResult:
    """Result of trade statistics aggregation.

    Attributes:
        total_trades: Total number of trades
        closed_trades: Number of closed trades
        open_trades: Number of open positions
        total_pnl: Total P&L
        avg_pnl_per_trade: Average P&L per trade
        avg_trade_duration: Average trade duration
        median_trade_duration: Median trade duration
        profit_factor: Ratio of gross profits to gross losses
        sharpe_ratio: Basic Sharpe ratio
        sortino_ratio: Basic Sortino ratio
        trade_distribution: Trade size distribution metrics
        pnl_std_dev: Standard deviation of P&Ls
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
    """

    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    avg_pnl_per_trade: Decimal = Decimal("0")
    avg_trade_duration: float = 0.0
    median_trade_duration: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    pnl_std_dev: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    trade_distribution: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_trades": self.total_trades,
            "closed_trades": self.closed_trades,
            "open_trades": self.open_trades,
            "total_pnl": float(self.total_pnl),
            "avg_pnl_per_trade": float(self.avg_pnl_per_trade),
            "avg_trade_duration_hours": round(self.avg_trade_duration, 2),
            "median_trade_duration_hours": round(self.median_trade_duration, 2),
            "profit_factor": round(self.profit_factor, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "pnl_std_dev": float(self.pnl_std_dev),
            "largest_win": float(self.largest_win),
            "largest_loss": float(self.largest_loss),
            "trade_distribution": self.trade_distribution,
        }


@dataclass
class AggregatedTrade:
    """Aggregated trade data for statistics.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        pnl: Profit/loss
        entry_time: Entry timestamp
        exit_time: Exit timestamp (None if still open)
        is_closed: Whether trade is closed
    """

    trade_id: str
    symbol: str
    pnl: Decimal
    entry_time: datetime
    exit_time: datetime | None = None
    is_closed: bool = False

    @property
    def duration(self) -> timedelta | None:
        """Calculate trade duration.

        Returns:
            Duration if closed, None otherwise
        """
        if not self.exit_time:
            return None
        return self.exit_time - self.entry_time


class TradeStatsAggregator:
    """Aggregate trade statistics.

    Supports:
    - Total trades and average trade duration
    - Profit factor and Sharpe ratio (basic)
    - Trade distribution metrics

    Attributes:
        risk_free_rate: Risk-free rate for Sharpe ratio calculation
    """

    def __init__(
        self,
        risk_free_rate: float = 0.02,  # 2% annual risk-free rate
    ) -> None:
        """Initialize trade stats aggregator.

        Args:
            risk_free_rate: Annual risk-free rate for Sharpe ratio
        """
        self._risk_free_rate = risk_free_rate
        self._trades: list[AggregatedTrade] = []

        logger.info(
            f"TradeStatsAggregator initialized: risk_free_rate={risk_free_rate}"
        )

    def add_trade(
        self,
        trade_id: str,
        symbol: str,
        pnl: float | Decimal,
        entry_time: datetime,
        exit_time: datetime | None = None,
    ) -> AggregatedTrade:
        """Add a trade for aggregation.

        Args:
            trade_id: Unique trade identifier
            symbol: Trading symbol
            pnl: Profit/loss
            entry_time: Entry timestamp
            exit_time: Exit timestamp (None if still open)

        Returns:
            Created AggregatedTrade
        """
        pnl_dec = Decimal(str(pnl))
        trade = AggregatedTrade(
            trade_id=trade_id,
            symbol=symbol,
            pnl=pnl_dec,
            entry_time=entry_time,
            exit_time=exit_time,
            is_closed=exit_time is not None,
        )

        self._trades.append(trade)
        return trade

    def add_trades(
        self,
        trades: list[tuple[str, str, float | Decimal, datetime, datetime | None]],
    ) -> None:
        """Add multiple trades.

        Args:
            trades: List of (trade_id, symbol, pnl, entry_time, exit_time) tuples
        """
        for trade_id, symbol, pnl, entry_time, exit_time in trades:
            self.add_trade(trade_id, symbol, pnl, entry_time, exit_time)

    def clear(self) -> None:
        """Clear all trade data."""
        self._trades.clear()

    def calculate_stats(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> TradeStatsResult:
        """Calculate trade statistics.

        Args:
            period_start: Start of the period (optional)
            period_end: End of the period (optional)

        Returns:
            TradeStatsResult with calculated statistics
        """
        # Filter by period if dates provided
        trades = self._trades

        if period_start:
            trades = [t for t in trades if t.exit_time and t.exit_time >= period_start]

        if period_end:
            trades = [t for t in trades if t.entry_time <= period_end]

        return self._calculate_from_trades(trades)

    def _calculate_from_trades(
        self,
        trades: list[AggregatedTrade],
    ) -> TradeStatsResult:
        """Calculate statistics from a list of trades.

        Args:
            trades: List of AggregatedTrade objects

        Returns:
            TradeStatsResult with calculated statistics
        """
        if not trades:
            return TradeStatsResult()

        closed_trades = [t for t in trades if t.is_closed]
        open_trades = [t for t in trades if not t.is_closed]

        total = len(trades)
        total_pnl = sum(t.pnl for t in trades)
        avg_pnl = total_pnl / total if total > 0 else Decimal("0")

        # Calculate durations
        durations: list[float] = []
        for trade in closed_trades:
            if trade.duration:
                durations.append(
                    trade.duration.total_seconds() / 3600
                )  # Convert to hours

        avg_duration = sum(durations) / len(durations) if durations else 0.0
        median_duration = self._calculate_median(durations) if durations else 0.0

        # Calculate profit factor
        wins = [t.pnl for t in closed_trades if t.pnl > 0]
        losses = [abs(t.pnl) for t in closed_trades if t.pnl < 0]

        gross_profit = sum(wins) if wins else Decimal("0")
        gross_loss = sum(losses) if losses else Decimal("0")

        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0

        # Calculate standard deviation
        if closed_trades:
            pnls = [float(t.pnl) for t in closed_trades]
            mean_pnl = sum(pnls) / len(pnls)
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
            pnl_std_dev = Decimal(str(math.sqrt(variance)))
        else:
            pnl_std_dev = Decimal("0")

        # Calculate Sharpe ratio (simplified)
        sharpe = self._calculate_sharpe_ratio(closed_trades)

        # Calculate Sortino ratio (simplified)
        sortino = self._calculate_sortino_ratio(closed_trades)

        # Find largest win/loss
        largest_win = max((t.pnl for t in closed_trades), default=Decimal("0"))
        largest_loss = min((t.pnl for t in closed_trades), default=Decimal("0"))

        # Calculate trade distribution
        distribution = self._calculate_distribution(closed_trades)

        result = TradeStatsResult(
            total_trades=total,
            closed_trades=len(closed_trades),
            open_trades=len(open_trades),
            total_pnl=total_pnl,
            avg_pnl_per_trade=avg_pnl,
            avg_trade_duration=avg_duration,
            median_trade_duration=median_duration,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            pnl_std_dev=pnl_std_dev,
            largest_win=largest_win,
            largest_loss=abs(largest_loss),
            trade_distribution=distribution,
        )

        logger.debug(
            f"Trade stats calculated: total={total}, profit_factor={profit_factor:.2f}, "
            f"sharpe={sharpe:.2f}, avg_duration={avg_duration:.1f}h"
        )

        return result

    def _calculate_median(self, values: list[float]) -> float:
        """Calculate median of a list.

        Args:
            values: List of numbers

        Returns:
            Median value
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        n = len(sorted_values)

        if n % 2 == 0:
            return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
        else:
            return sorted_values[n // 2]

    def _calculate_sharpe_ratio(
        self,
        trades: list[AggregatedTrade],
        periods_per_year: int = 252,
    ) -> float:
        """Calculate Sharpe ratio.

        Args:
            trades: List of closed trades
            periods_per_year: Number of trading periods per year

        Returns:
            Sharpe ratio
        """
        if len(trades) < 2:
            return 0.0

        # Get daily returns (assuming each trade is one period)
        returns = [float(t.pnl) for t in trades]

        if not returns:
            return 0.0

        mean_return = sum(returns) / len(returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0

        # Annualize
        if std_dev == 0:
            return 0.0

        sharpe = (mean_return - self._risk_free_rate / periods_per_year) / std_dev
        sharpe_annualized = sharpe * math.sqrt(periods_per_year)

        return sharpe_annualized

    def _calculate_sortino_ratio(
        self,
        trades: list[AggregatedTrade],
        periods_per_year: int = 252,
    ) -> float:
        """Calculate Sortino ratio.

        Args:
            trades: List of closed trades
            periods_per_year: Number of trading periods per year

        Returns:
            Sortino ratio
        """
        if len(trades) < 2:
            return 0.0

        returns = [float(t.pnl) for t in trades]
        mean_return = sum(returns) / len(returns)

        # Calculate downside deviation (only negative returns)
        negative_returns = [r for r in returns if r < 0]

        if not negative_returns:
            return 0.0

        downside_variance = sum(r**2 for r in negative_returns) / len(returns)
        downside_dev = math.sqrt(downside_variance) if downside_variance > 0 else 1.0

        if downside_dev == 0:
            return 0.0

        sortino = (mean_return - self._risk_free_rate / periods_per_year) / downside_dev
        sortino_annualized = sortino * math.sqrt(periods_per_year)

        return sortino_annualized

    def _calculate_distribution(
        self,
        trades: list[AggregatedTrade],
    ) -> dict[str, float]:
        """Calculate trade size distribution.

        Args:
            trades: List of closed trades

        Returns:
            Dictionary with distribution metrics
        """
        if not trades:
            return {}

        pnls = [float(t.pnl) for t in trades]
        total = len(pnls)

        # Categorize trades
        big_wins = len([p for p in pnls if p > 100])  # > $100
        small_wins = len([p for p in pnls if 0 < p <= 100])
        breakeven = len([p for p in pnls if p == 0])
        small_losses = len([p for p in pnls if -100 <= p < 0])
        big_losses = len([p for p in pnls if p < -100])  # < -$100

        return {
            "big_wins_pct": round(big_wins / total * 100, 2),
            "small_wins_pct": round(small_wins / total * 100, 2),
            "breakeven_pct": round(breakeven / total * 100, 2),
            "small_losses_pct": round(small_losses / total * 100, 2),
            "big_losses_pct": round(big_losses / total * 100, 2),
        }

    def calculate_calmar_ratio(
        self,
        max_drawdown: float,
        trades: list[AggregatedTrade] | None = None,
    ) -> float:
        """Calculate Calmar ratio.

        Args:
            max_drawdown: Maximum drawdown
            trades: Optional list of trades (uses internal if not provided)

        Returns:
            Calmar ratio
        """
        if trades is None:
            trades = self._trades

        if max_drawdown <= 0:
            return 0.0

        # Calculate annual return (assuming daily trades)
        total_pnl = sum(t.pnl for t in trades)
        annual_return = float(total_pnl) * 252 / len(trades) if trades else 0.0

        calmar = annual_return / max_drawdown

        return round(calmar, 2)
