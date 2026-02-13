"""KPI calculator for execution telemetry.

For ST-EX-001: Calculate Sharpe ratio, max drawdown, win rate, etc.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.telemetry.metrics import Trade

logger = logging.getLogger(__name__)


class KPICalculator:
    """Calculator for trading KPIs and performance metrics."""

    @staticmethod
    def calculate_sharpe(
        returns: list[float],
        risk_free_rate: float = 0.02,
        periods_per_year: int = 365,
    ) -> float:
        """Calculate annualized Sharpe ratio.

        Formula: (mean_return - risk_free_rate) / std_return

        Args:
            returns: List of period returns (as decimals, e.g., 0.01 for 1%)
            risk_free_rate: Annual risk-free rate (default 2%)
            periods_per_year: Number of periods in a year (default 365 for daily)

        Returns:
            Annualized Sharpe ratio, or 0.0 if insufficient data
        """
        if len(returns) < 2:
            return 0.0

        # Filter out invalid values
        valid_returns = [r for r in returns if not (math.isnan(r) or math.isinf(r))]

        if len(valid_returns) < 2:
            return 0.0

        # Calculate mean and std of returns
        mean_return = sum(valid_returns) / len(valid_returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in valid_returns) / (
            len(valid_returns) - 1
        )
        std_return = math.sqrt(variance) if variance > 0 else 0.0

        if std_return == 0:
            return 0.0

        # Annualize the returns and Sharpe ratio
        # Convert daily mean to annual: mean * periods
        # Convert daily std to annual: std * sqrt(periods)
        annual_mean = mean_return * periods_per_year
        annual_std = std_return * math.sqrt(periods_per_year)

        sharpe = (annual_mean - risk_free_rate) / annual_std

        # Clamp extreme values
        return max(-10.0, min(10.0, sharpe))

    @staticmethod
    def calculate_max_drawdown(equity_curve: list[float]) -> float:
        """Calculate maximum drawdown percentage.

        Args:
            equity_curve: List of equity values over time

        Returns:
            Maximum drawdown as percentage (0-100), or 0.0 if insufficient data
        """
        if len(equity_curve) < 2:
            return 0.0

        max_drawdown = 0.0
        peak = equity_curve[0]

        for equity in equity_curve[1:]:
            if equity > peak:
                peak = equity
            elif peak > 0:
                drawdown = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    @staticmethod
    def calculate_win_rate(trades: list[Trade]) -> float:
        """Calculate win rate percentage.

        Args:
            trades: List of completed trades

        Returns:
            Win rate as percentage (0-100), or 0.0 if no trades
        """
        if not trades:
            return 0.0

        wins = sum(1 for trade in trades if trade.is_win)
        return (wins / len(trades)) * 100

    @staticmethod
    def calculate_profit_factor(trades: list[Trade]) -> float:
        """Calculate profit factor (gross profit / gross loss).

        Args:
            trades: List of completed trades

        Returns:
            Profit factor, or 0.0 if no losing trades
        """
        if not trades:
            return 0.0

        gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in trades if trade.pnl < 0))

        if gross_loss == 0:
            return gross_profit > 0 if gross_profit else 0.0

        return gross_profit / gross_loss

    @staticmethod
    def calculate_average_trade(trades: list[Trade]) -> float:
        """Calculate average PnL per trade.

        Args:
            trades: List of completed trades

        Returns:
            Average PnL, or 0.0 if no trades
        """
        if not trades:
            return 0.0

        return sum(trade.pnl for trade in trades) / len(trades)

    @staticmethod
    def calculate_expectancy(trades: list[Trade]) -> float:
        """Calculate trade expectancy.

        Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)

        Args:
            trades: List of completed trades

        Returns:
            Expectancy value, or 0.0 if no trades
        """
        if not trades:
            return 0.0

        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl < 0]

        if not wins and not losses:
            return 0.0

        win_rate = len(wins) / len(trades) if trades else 0
        loss_rate = len(losses) / len(trades) if trades else 0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0

        return (win_rate * avg_win) - (loss_rate * avg_loss)

    @staticmethod
    def calculate_returns_from_trades(trades: list[Trade]) -> list[float]:
        """Calculate period returns from trades.

        Args:
            trades: List of completed trades

        Returns:
            List of returns as decimals
        """
        if not trades:
            return []

        returns = []
        for trade in trades:
            # Calculate return as PnL / (entry_price * quantity)
            if trade.entry_price > 0 and trade.quantity > 0:
                invested = trade.entry_price * trade.quantity
                trade_return = trade.pnl / invested
                returns.append(trade_return)

        return returns

    @staticmethod
    def calculate_equity_curve(
        trades: list[Trade], initial_equity: float = 10000.0
    ) -> list[float]:
        """Calculate equity curve from trades.

        Args:
            trades: List of completed trades
            initial_equity: Starting equity value

        Returns:
            List of equity values after each trade
        """
        if not trades:
            return [initial_equity]

        equity = initial_equity
        equity_curve = [equity]

        for trade in trades:
            equity += trade.pnl
            equity_curve.append(equity)

        return equity_curve
