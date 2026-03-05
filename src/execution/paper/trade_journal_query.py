"""Trade journal query and reporting API.

Provides read-only query operations over persisted journal entries
with filtering and summary statistics.

For ST-JOURNAL-QUERY-001: Trade Journal Query/Reporting Surface
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .reason_codes import RejectReason
from .trade_journal import ExitReason, TradeJournalEntry


@dataclass
class JournalQueryFilters:
    """Query filters for journal entries."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    symbol: str | None = None
    status: str | None = None  # "open" or "closed"
    exit_reason: ExitReason | None = None
    strategy: str | None = None


@dataclass
class JournalSummaryStats:
    """Summary statistics for journal entries."""

    total_trades: int
    open_trades: int
    closed_trades: int
    total_pnl: float
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    max_win: float
    max_loss: float


class TradeJournalQuery:
    """Query interface for trade journal entries.

    Provides read-only access to journal data with filtering
    and summary statistics. All operations are non-blocking.
    """

    def __init__(self, journal_entries: list[TradeJournalEntry]) -> None:
        """Initialize with list of entries to query.

        Args:
            journal_entries: List of TradeJournalEntry objects to query
        """
        self._entries = journal_entries

    def query(
        self, filters: JournalQueryFilters | None = None
    ) -> list[TradeJournalEntry]:
        """Query entries with optional filters.

        Args:
            filters: Optional JournalQueryFilters to apply

        Returns:
            List of matching TradeJournalEntry objects
        """
        if filters is None:
            return list(self._entries)

        entries = self._entries

        # Apply time range filters
        if filters.start_time is not None:
            entries = [
                e
                for e in entries
                if e.entry_time >= filters.start_time
                or (e.exit_time is not None and e.exit_time >= filters.start_time)
            ]

        if filters.end_time is not None:
            entries = [
                e
                for e in entries
                if e.entry_time <= filters.end_time
                or (e.exit_time is not None and e.exit_time <= filters.end_time)
            ]

        # Apply symbol filter
        if filters.symbol is not None:
            entries = [e for e in entries if e.symbol.upper() == filters.symbol.upper()]

        # Apply status filter
        if filters.status is not None:
            status_lower = filters.status.lower()
            if status_lower == "open":
                entries = [e for e in entries if e.is_open]
            elif status_lower == "closed":
                entries = [e for e in entries if e.is_closed]

        # Apply exit reason filter
        if filters.exit_reason is not None:
            entries = [e for e in entries if e.exit_reason == filters.exit_reason]

        # Apply strategy filter
        if filters.strategy is not None:
            entries = [e for e in entries if e.signal_strategy == filters.strategy]

        return entries

    def get_summary(
        self, filters: JournalQueryFilters | None = None
    ) -> JournalSummaryStats:
        """Get summary statistics for entries matching filters.

        Args:
            filters: Optional JournalQueryFilters to apply

        Returns:
            JournalSummaryStats with computed statistics
        """
        entries = self.query(filters)

        total_trades = len(entries)
        open_trades = len([e for e in entries if e.is_open])
        closed_trades = len([e for e in entries if e.is_closed])

        # Only compute PnL stats for closed trades
        closed_entries = [e for e in entries if e.is_closed]

        if not closed_entries:
            return JournalSummaryStats(
                total_trades=total_trades,
                open_trades=open_trades,
                closed_trades=closed_trades,
                total_pnl=0.0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                avg_pnl=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                max_win=0.0,
                max_loss=0.0,
            )

        # Calculate PnL statistics
        pnls = [e.net_pnl for e in closed_entries]
        total_pnl = sum(pnls)

        winning_trades = len([p for p in pnls if p > 0])
        losing_trades = len([p for p in pnls if p < 0])
        win_rate = winning_trades / len(closed_entries) if closed_entries else 0.0

        avg_pnl = total_pnl / len(closed_entries) if closed_entries else 0.0

        # Calculate average win/loss
        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]

        avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0.0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0.0

        # Calculate max win/loss
        max_win = max(winning_pnls) if winning_pnls else 0.0
        max_loss = min(losing_pnls) if losing_pnls else 0.0

        return JournalSummaryStats(
            total_trades=total_trades,
            open_trades=open_trades,
            closed_trades=closed_trades,
            total_pnl=total_pnl,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_win=max_win,
            max_loss=max_loss,
        )

    def get_symbols(self) -> list[str]:
        """Get list of all unique symbols in the journal.

        Returns:
            Sorted list of unique symbol strings
        """
        symbols = {e.symbol.upper() for e in self._entries}
        return sorted(list(symbols))

    def get_strategies(self) -> list[str]:
        """Get list of all unique strategies in the journal.

        Returns:
            Sorted list of unique strategy name strings
        """
        strategies = {e.signal_strategy for e in self._entries}
        return sorted(list(strategies))

    def get_exit_reasons(self) -> list[ExitReason]:
        """Get list of all exit reasons used in closed trades.

        Returns:
            List of unique ExitReason values
        """
        reasons = {e.exit_reason for e in self._entries if e.exit_reason is not None}
        return sorted(list(reasons), key=lambda r: r.value)

    def get_time_range(self) -> tuple[datetime | None, datetime | None]:
        """Get the time range covered by journal entries.

        Returns:
            Tuple of (earliest_entry_time, latest_exit_time) or (None, None) if no entries
        """
        if not self._entries:
            return (None, None)

        entry_times = [e.entry_time for e in self._entries]
        exit_times = [e.exit_time for e in self._entries if e.exit_time is not None]

        earliest = min(entry_times)
        latest = max(exit_times) if exit_times else max(entry_times)

        return (earliest, latest)

    def get_pnl_by_symbol(self) -> dict[str, float]:
        """Get total PnL grouped by symbol.

        Returns:
            Dictionary mapping symbol to total net PnL
        """
        result: dict[str, float] = {}
        for entry in self._entries:
            if entry.is_closed:
                symbol = entry.symbol.upper()
                result[symbol] = result.get(symbol, 0.0) + entry.net_pnl
        return result

    def get_pnl_by_strategy(self) -> dict[str, float]:
        """Get total PnL grouped by strategy.

        Returns:
            Dictionary mapping strategy name to total net PnL
        """
        result: dict[str, float] = {}
        for entry in self._entries:
            if entry.is_closed:
                strategy = entry.signal_strategy
                result[strategy] = result.get(strategy, 0.0) + entry.net_pnl
        return result

    def get_pnl_by_exit_reason(self) -> dict[ExitReason, float]:
        """Get total PnL grouped by exit reason.

        Returns:
            Dictionary mapping ExitReason to total net PnL
        """
        result: dict[ExitReason, float] = {}
        for entry in self._entries:
            if entry.is_closed and entry.exit_reason is not None:
                reason = entry.exit_reason
                result[reason] = result.get(reason, 0.0) + entry.net_pnl
        return result

    def get_exit_reason_distribution(
        self, filters: JournalQueryFilters | None = None
    ) -> dict[ExitReason, dict[str, Any]]:
        """Get distribution of exit reasons for closed trades.

        Calculates the count and percentage of each exit reason across
        all closed trades matching the filters.

        Args:
            filters: Optional JournalQueryFilters to apply

        Returns:
            Dictionary mapping ExitReason to {"count": int, "percentage": float}

        Example:
            >>> query = TradeJournalQuery(entries)
            >>> dist = query.get_exit_reason_distribution()
            >>> print(dist[ExitReason.STOP_LOSS_HIT])
            {"count": 10, "percentage": 25.0}
        """
        entries = self.query(filters)
        closed_entries = [
            e for e in entries if e.is_closed and e.exit_reason is not None
        ]

        if not closed_entries:
            return {}

        # Count occurrences of each exit reason
        reason_counts: dict[ExitReason, int] = {}
        for entry in closed_entries:
            reason = entry.exit_reason
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        total = len(closed_entries)

        # Calculate distribution with counts and percentages
        distribution: dict[ExitReason, dict[str, Any]] = {}
        for reason, count in reason_counts.items():
            percentage = (count / total) * 100.0
            distribution[reason] = {
                "count": count,
                "percentage": round(percentage, 2),
            }

        return distribution

    def get_reject_reason_distribution(
        self, rejected_signals: list[Any] | None = None
    ) -> dict[RejectReason, dict[str, Any]]:
        """Get distribution of rejection reasons from rejected signals.

        NOTE: This method currently requires rejected_signals to be provided.
        Future implementation may integrate with provenance tracking system.

        Args:
            rejected_signals: Optional list of rejected signal objects with
                            reject_reason attribute. If None, returns empty dict.

        Returns:
            Dictionary mapping RejectReason to {"count": int, "percentage": float}

        Example:
            >>> # When rejected signals are available
            >>> rejected = [...]  # List of rejected signal objects
            >>> dist = query.get_reject_reason_distribution(rejected)
            >>> print(dist[RejectReason.RISK_VIOLATION])
            {"count": 5, "percentage": 20.0}
        """
        if not rejected_signals:
            return {}

        # Count occurrences of each reject reason
        reason_counts: dict[RejectReason, int] = {}
        for signal in rejected_signals:
            if hasattr(signal, "reject_reason") and signal.reject_reason is not None:
                reason = signal.reject_reason
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if not reason_counts:
            return {}

        total = sum(reason_counts.values())

        # Calculate distribution with counts and percentages
        distribution: dict[RejectReason, dict[str, Any]] = {}
        for reason, count in reason_counts.items():
            percentage = (count / total) * 100.0
            distribution[reason] = {
                "count": count,
                "percentage": round(percentage, 2),
            }

        return distribution

    def get_reason_summary(
        self,
        filters: JournalQueryFilters | None = None,
        rejected_signals: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Get combined summary of exit and reject reason distributions.

        Provides a comprehensive view of both closed trade exit reasons
        and signal rejection reasons in a single summary structure.

        Args:
            filters: Optional JournalQueryFilters to apply to exit reasons
            rejected_signals: Optional list of rejected signals for reject analysis

        Returns:
            Dictionary with:
                - exit_reasons: Distribution of exit reasons
                - reject_reasons: Distribution of rejection reasons
                - totals: Combined counts and statistics

        Example:
            >>> summary = query.get_reason_summary(filters, rejected_signals)
            >>> print(summary["totals"])
            {
                "total_closed_trades": 50,
                "total_rejected_signals": 20,
                "total_decisions": 70
            }
        """
        exit_dist = self.get_exit_reason_distribution(filters)
        reject_dist = self.get_reject_reason_distribution(rejected_signals)

        # Calculate totals
        total_closed_trades = sum(d["count"] for d in exit_dist.values())
        total_rejected_signals = sum(d["count"] for d in reject_dist.values())
        total_decisions = total_closed_trades + total_rejected_signals

        return {
            "exit_reasons": {
                reason.value: stats for reason, stats in exit_dist.items()
            },
            "reject_reasons": {
                reason.value: stats for reason, stats in reject_dist.items()
            },
            "totals": {
                "total_closed_trades": total_closed_trades,
                "total_rejected_signals": total_rejected_signals,
                "total_decisions": total_decisions,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert query interface state to dictionary.

        Returns:
            Dictionary with entry count and available filters
        """
        start_time, end_time = self.get_time_range()

        return {
            "entry_count": len(self._entries),
            "symbols": self.get_symbols(),
            "strategies": self.get_strategies(),
            "exit_reasons": [r.value for r in self.get_exit_reasons()],
            "time_range": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
            },
        }
