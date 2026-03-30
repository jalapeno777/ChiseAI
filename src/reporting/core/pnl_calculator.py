"""PnL Calculator for the core report generation engine.

Calculates daily/weekly/monthly P&L with support for:
- Realized and unrealized P&L
- Currency conversion
- Period-over-period comparisons

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PnLResult:
    """Result of P&L calculation.

    Attributes:
        realized_pnl: Realized profit/loss
        unrealized_pnl: Unrealized profit/loss
        total_pnl: Total P&L (realized + unrealized)
        currency: Currency of the P&L
        period_start: Start of the period
        period_end: End of the period
        trade_count: Number of trades in the period
    """

    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    currency: str = "USD"
    period_start: datetime | None = None
    period_end: datetime | None = None
    trade_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "total_pnl": float(self.total_pnl),
            "currency": self.currency,
            "period_start": (
                self.period_start.isoformat() if self.period_start else None
            ),
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "trade_count": self.trade_count,
        }


@dataclass
class PnLSummary:
    """Summary of P&L across multiple periods.

    Attributes:
        current_period: P&L for current period
        previous_period: P&L for previous period
        period_over_period_change: Change between periods
        period_over_period_pct: Percentage change
    """

    current_period: PnLResult = field(default_factory=PnLResult)
    previous_period: PnLResult = field(default_factory=PnLResult)
    period_over_period_change: Decimal = Decimal("0")
    period_over_period_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_period": self.current_period.to_dict(),
            "previous_period": self.previous_period.to_dict(),
            "period_over_period_change": float(self.period_over_period_change),
            "period_over_period_pct": round(self.period_over_period_pct, 2),
        }


@dataclass
class TradePnL:
    """P&L data for a single trade.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Position quantity
        realized_pnl: Realized P&L (for closed trades)
        unrealized_pnl: Unrealized P&L (for open positions)
        fees: Trading fees
        direction: Trade direction (long/short)
    """

    trade_id: str
    symbol: str
    direction: str = "long"
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    entry_price: Decimal = Decimal("0")
    exit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    is_closed: bool = False

    def calculate_total_pnl(self) -> Decimal:
        """Calculate total P&L for this trade.

        Returns:
            Total P&L (realized + unrealized)
        """
        if self.is_closed:
            return self.realized_pnl - self.fees
        return self.unrealized_pnl - self.fees


class PnLCalculator:
    """Calculate P&L for various time periods.

    Supports:
    - Realized and unrealized P&L
    - Daily/weekly/monthly periods
    - Currency conversion
    - Period comparisons

    Attributes:
        default_currency: Default currency for calculations
        use_decimal: Whether to use Decimal for precision
    """

    def __init__(
        self,
        default_currency: str = "USD",
        use_decimal: bool = True,
    ) -> None:
        """Initialize PnL calculator.

        Args:
            default_currency: Default currency code (default: USD)
            use_decimal: Whether to use Decimal for precision (default: True)
        """
        self._default_currency = default_currency
        self._use_decimal = use_decimal
        self._exchange_rates: dict[str, Decimal] = {"USD": Decimal("1")}

        logger.info(f"PnLCalculator initialized: currency={default_currency}")

    def set_exchange_rate(self, currency: str, rate: float | Decimal) -> None:
        """Set exchange rate for a currency.

        Args:
            currency: Currency code
            rate: Exchange rate to USD
        """
        if isinstance(rate, float):
            self._exchange_rates[currency] = Decimal(str(rate))
        else:
            self._exchange_rates[currency] = rate
        logger.debug(
            f"Set exchange rate: {currency} = {self._exchange_rates[currency]}"
        )

    def convert_to_default(
        self,
        amount: Decimal | float,
        currency: str,
    ) -> Decimal:
        """Convert amount to default currency.

        Args:
            amount: Amount to convert
            currency: Source currency

        Returns:
            Amount in default currency
        """
        if currency == self._default_currency:
            return Decimal(str(amount)) if self._use_decimal else Decimal(str(amount))

        rate = self._exchange_rates.get(currency, Decimal("1"))
        result = Decimal(str(amount)) * rate
        return result

    def calculate_trade_pnl(
        self,
        entry_price: float | Decimal,
        exit_price: float | Decimal,
        quantity: float | Decimal,
        direction: str = "long",
        fees: float | Decimal = 0,
    ) -> TradePnL:
        """Calculate P&L for a single trade.

        Args:
            entry_price: Entry price per unit
            exit_price: Exit price per unit
            quantity: Number of units
            direction: "long" or "short"
            fees: Trading fees

        Returns:
            TradePnL with calculated values
        """
        entry = Decimal(str(entry_price))
        exit = Decimal(str(exit_price))
        qty = Decimal(str(quantity))
        fee = Decimal(str(fees))

        if direction.lower() == "long":
            pnl_per_unit = exit - entry
        else:  # short
            pnl_per_unit = entry - exit

        gross_pnl = pnl_per_unit * qty
        net_pnl = gross_pnl - fee

        trade = TradePnL(
            trade_id="",
            symbol="",
            direction=direction,
            entry_price=entry,
            exit_price=exit,
            quantity=qty,
            realized_pnl=net_pnl,
            unrealized_pnl=Decimal("0"),
            fees=fee,
            is_closed=True,
        )

        return trade

    def calculate_daily_pnl(
        self,
        trades: list[TradePnL],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> PnLResult:
        """Calculate P&L for a day.

        Args:
            trades: List of trades to include
            period_start: Start of the period
            period_end: End of the period

        Returns:
            PnLResult with calculated values
        """
        realized = Decimal("0")
        unrealized = Decimal("0")
        closed_count = 0

        for trade in trades:
            if trade.is_closed:
                realized += trade.realized_pnl
                closed_count += 1
            else:
                unrealized += trade.unrealized_pnl

        total = realized + unrealized

        result = PnLResult(
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=total,
            currency=self._default_currency,
            period_start=period_start,
            period_end=period_end,
            trade_count=len(trades),
        )

        logger.debug(
            f"Daily PnL calculated: total={total}, trades={len(trades)}, "
            f"realized={realized}, unrealized={unrealized}"
        )

        return result

    def calculate_weekly_pnl(
        self,
        trades: list[TradePnL],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> PnLResult:
        """Calculate P&L for a week.

        Args:
            trades: List of trades to include
            period_start: Start of the period
            period_end: End of the period

        Returns:
            PnLResult with calculated values
        """
        # Same calculation as daily, just different period
        return self.calculate_daily_pnl(trades, period_start, period_end)

    def calculate_monthly_pnl(
        self,
        trades: list[TradePnL],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> PnLResult:
        """Calculate P&L for a month.

        Args:
            trades: List of trades to include
            period_start: Start of the period
            period_end: End of the period

        Returns:
            PnLResult with calculated values
        """
        # Same calculation as daily, just different period
        return self.calculate_daily_pnl(trades, period_start, period_end)

    def calculate_period_pnl(
        self,
        trades: list[TradePnL],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> PnLResult:
        """Calculate P&L for an arbitrary period.

        Args:
            trades: List of trades to include
            period_start: Start of the period
            period_end: End of the period

        Returns:
            PnLResult with calculated values
        """
        # Filter trades by period if dates provided
        filtered_trades = trades

        if period_start:
            filtered_trades = [
                t
                for t in filtered_trades
                if t.exit_time and t.exit_time >= period_start
            ]

        if period_end:
            filtered_trades = [
                t
                for t in filtered_trades
                if t.entry_time and t.entry_time <= period_end
            ]

        realized = Decimal("0")
        unrealized = Decimal("0")

        for trade in filtered_trades:
            if trade.is_closed:
                realized += trade.realized_pnl
            else:
                unrealized += trade.unrealized_pnl

        total = realized + unrealized

        return PnLResult(
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=total,
            currency=self._default_currency,
            period_start=period_start,
            period_end=period_end,
            trade_count=len(filtered_trades),
        )

    def compare_periods(
        self,
        current: PnLResult,
        previous: PnLResult,
    ) -> PnLSummary:
        """Compare P&L between two periods.

        Args:
            current: Current period P&L
            previous: Previous period P&L

        Returns:
            PnLSummary with comparison
        """
        change = current.total_pnl - previous.total_pnl

        # Calculate percentage change
        if previous.total_pnl != 0:
            pct_change = (change / abs(previous.total_pnl)) * 100
        elif current.total_pnl != 0:
            pct_change = 100.0 if current.total_pnl > 0 else -100.0
        else:
            pct_change = 0.0

        summary = PnLSummary(
            current_period=current,
            previous_period=previous,
            period_over_period_change=change,
            period_over_period_pct=float(pct_change),
        )

        logger.debug(f"Period comparison: change={change}, pct={pct_change:.2f}%")

        return summary

    def aggregate_trades(
        self,
        trades: list[TradePnL],
    ) -> dict[str, Any]:
        """Aggregate trades into a summary.

        Args:
            trades: List of trades to aggregate

        Returns:
            Dictionary with aggregated metrics
        """
        if not trades:
            return {
                "total_trades": 0,
                "closed_trades": 0,
                "open_trades": 0,
                "total_realized_pnl": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_pnl": 0.0,
                "avg_pnl_per_trade": 0.0,
                "best_trade": None,
                "worst_trade": None,
            }

        closed_trades = [t for t in trades if t.is_closed]
        open_trades = [t for t in trades if not t.is_closed]

        total_realized = sum(t.realized_pnl for t in trades)
        total_unrealized = sum(t.unrealized_pnl for t in trades)
        total_pnl = total_realized + total_unrealized

        best_trade = (
            max(closed_trades, key=lambda t: t.realized_pnl) if closed_trades else None
        )
        worst_trade = (
            min(closed_trades, key=lambda t: t.realized_pnl) if closed_trades else None
        )

        avg_pnl = total_pnl / len(trades) if trades else Decimal("0")

        return {
            "total_trades": len(trades),
            "closed_trades": len(closed_trades),
            "open_trades": len(open_trades),
            "total_realized_pnl": float(total_realized),
            "total_unrealized_pnl": float(total_unrealized),
            "total_pnl": float(total_pnl),
            "avg_pnl_per_trade": float(avg_pnl),
            "best_trade": (
                {
                    "trade_id": best_trade.trade_id,
                    "symbol": best_trade.symbol,
                    "pnl": float(best_trade.realized_pnl),
                }
                if best_trade
                else None
            ),
            "worst_trade": (
                {
                    "trade_id": worst_trade.trade_id,
                    "symbol": worst_trade.symbol,
                    "pnl": float(worst_trade.realized_pnl),
                }
                if worst_trade
                else None
            ),
        }
