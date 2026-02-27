"""Trading recap generator from canonical persisted outcomes.

Generates trading recaps by querying canonical persisted data from Redis,
ensuring accuracy against actual trading data.

For ST-FINAL-CLOSURE-001: G6 - Recap from Canonical Persisted Outcomes
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.persistence.outcome_persistence import OutcomePersistence

logger = logging.getLogger(__name__)


class TradingRecapGenerator:
    """Generates trading recaps from canonical persisted outcomes.

    Queries Redis for persisted outcomes and generates summary reports
    for Discord #trading channel. Ensures recaps are based on actual
    trading data, not transient or cached values.

    Attributes:
        persistence: OutcomePersistence instance for data access
    """

    def __init__(
        self,
        persistence: OutcomePersistence | None = None,
    ):
        """Initialize recap generator.

        Args:
            persistence: OutcomePersistence instance (created if None)
        """
        self._persistence = persistence

        logger.info("TradingRecapGenerator initialized")

    def _get_persistence(self) -> OutcomePersistence:
        """Get or create OutcomePersistence."""
        if self._persistence is None:
            from execution.persistence.outcome_persistence import (
                OutcomePersistence,
            )

            self._persistence = OutcomePersistence()
        return self._persistence

    async def generate_daily_recap(
        self,
        date: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate daily trading recap.

        Args:
            date: Date to generate recap for (default: today)

        Returns:
            Recap dictionary with trading summary
        """
        if date is None:
            date = datetime.now(UTC)

        # Get start/end of day
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        return await self._generate_recap_for_period(
            start_time=start_of_day,
            end_time=end_of_day,
            period_name="Daily",
        )

    async def generate_period_recap(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Generate recap for recent period.

        Args:
            hours: Number of hours to look back

        Returns:
            Recap dictionary with trading summary
        """
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)

        return await self._generate_recap_for_period(
            start_time=start_time,
            end_time=end_time,
            period_name=f"{hours}h",
        )

    async def _generate_recap_for_period(
        self,
        start_time: datetime,
        end_time: datetime,
        period_name: str,
    ) -> dict[str, Any]:
        """Generate recap for a specific time period.

        Args:
            start_time: Start of period
            end_time: End of period
            period_name: Name of period for display

        Returns:
            Recap dictionary
        """
        persistence = self._get_persistence()

        # Get all outcomes from persistence
        outcomes = persistence.get_recent_outcomes(limit=1000)

        # Filter by time range
        period_outcomes = self._filter_outcomes_by_time(outcomes, start_time, end_time)

        # Calculate statistics
        stats = self._calculate_stats(period_outcomes)

        # Build recap
        recap = {
            "period": period_name,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "data_source": "canonical_persistence",
            "outcome_count": len(period_outcomes),
            **stats,
        }

        logger.info(
            f"Generated {period_name} recap: "
            f"{stats.get('total_trades', 0)} trades, "
            f"PnL=${stats.get('total_pnl', 0):.2f}"
        )

        return recap

    def _filter_outcomes_by_time(
        self,
        outcomes: list[dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Filter outcomes by time range.

        Args:
            outcomes: List of outcome dictionaries
            start_time: Start of range
            end_time: End of range

        Returns:
            Filtered list of outcomes
        """
        filtered = []

        for outcome in outcomes:
            # Parse entry time
            entry_time_str = outcome.get("entry_time")
            if not entry_time_str:
                continue

            try:
                entry_time = datetime.fromisoformat(
                    entry_time_str.replace("Z", "+00:00")
                )
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=UTC)

                if start_time <= entry_time < end_time:
                    filtered.append(outcome)

            except (ValueError, TypeError):
                continue

        return filtered

    def _calculate_stats(
        self,
        outcomes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Calculate trading statistics from outcomes.

        Args:
            outcomes: List of outcome dictionaries

        Returns:
            Statistics dictionary
        """
        if not outcomes:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "best_trade": None,
                "worst_trade": None,
            }

        total_trades = len(outcomes)
        winning_trades = 0
        losing_trades = 0
        total_pnl = 0.0

        best_trade = None
        worst_trade = None
        best_pnl = float("-inf")
        worst_pnl = float("inf")

        symbols_traded = set()

        for outcome in outcomes:
            # Get PnL
            pnl_str = outcome.get("pnl")
            if pnl_str:
                try:
                    pnl = float(pnl_str)
                except (ValueError, TypeError):
                    pnl = 0.0
            else:
                pnl = 0.0

            total_pnl += pnl

            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1

            # Track best/worst
            if pnl > best_pnl:
                best_pnl = pnl
                best_trade = {
                    "symbol": outcome.get("symbol", ""),
                    "pnl": pnl,
                    "direction": outcome.get("direction", ""),
                }

            if pnl < worst_pnl:
                worst_pnl = pnl
                worst_trade = {
                    "symbol": outcome.get("symbol", ""),
                    "pnl": pnl,
                    "direction": outcome.get("direction", ""),
                }

            # Track symbols
            symbol = outcome.get("symbol")
            if symbol:
                symbols_traded.add(symbol)

        # Calculate win rate
        closed_trades = winning_trades + losing_trades
        win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0

        # Calculate average PnL
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(win_rate, 2),
            "avg_pnl": round(avg_pnl, 4),
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "symbols_traded": list(symbols_traded),
        }

    async def generate_position_summary(
        self,
    ) -> dict[str, Any]:
        """Generate summary of current positions.

        Returns:
            Position summary dictionary
        """
        persistence = self._get_persistence()

        # Get recent outcomes
        outcomes = persistence.get_recent_outcomes(limit=100)

        # Filter to open positions (no exit_time)
        open_positions = [
            o
            for o in outcomes
            if o.get("exit_time") is None and o.get("exit_price") is None
        ]

        # Calculate summary
        total_positions = len(open_positions)
        long_positions = sum(1 for o in open_positions if o.get("direction") == "LONG")
        short_positions = sum(
            1 for o in open_positions if o.get("direction") == "SHORT"
        )

        total_notional = sum(
            float(o.get("entry_price", 0)) * float(o.get("position_size", 0))
            for o in open_positions
        )

        symbols = list(
            set(o.get("symbol", "") for o in open_positions if o.get("symbol"))
        )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "data_source": "canonical_persistence",
            "total_open_positions": total_positions,
            "long_positions": long_positions,
            "short_positions": short_positions,
            "total_notional_value": round(total_notional, 2),
            "symbols": symbols,
            "positions": [
                {
                    "symbol": o.get("symbol"),
                    "direction": o.get("direction"),
                    "entry_price": o.get("entry_price"),
                    "position_size": o.get("position_size"),
                    "entry_time": o.get("entry_time"),
                }
                for o in open_positions[:10]  # Limit to 10 most recent
            ],
        }

    async def get_trading_history(
        self,
        limit: int = 100,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get trading history from persisted outcomes.

        Args:
            limit: Maximum number of trades to return
            symbol: Optional symbol filter

        Returns:
            List of trade history entries
        """
        persistence = self._get_persistence()
        return persistence.get_recent_outcomes(symbol=symbol, limit=limit)

    def health_check(self) -> dict[str, Any]:
        """Check recap generator health.

        Returns:
            Health status dictionary
        """
        try:
            persistence = self._get_persistence()
            persistence_health = persistence.health_check()

            return {
                "healthy": persistence_health.get("healthy", False),
                "persistence": persistence_health,
            }

        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }
