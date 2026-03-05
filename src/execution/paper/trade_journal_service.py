"""Trade journal service with persistence support.

Provides a service wrapper that combines TradeJournal with TradeJournalRedisPersistence
for automatic persistence of trade journal entries. All persistence operations are
non-blocking to ensure trading continuity.

For PAPER-2025-BATCH3-002: Orchestrator Persistence Integration
"""

from __future__ import annotations

import logging
from typing import Any

from .trade_journal import (
    ExitReason,
    FillRecord,
    TradeJournal,
    TradeJournalEntry,
)
from .trade_journal_persistence import TradeJournalRedisPersistence
from .trade_journal_query import (
    JournalQueryFilters,
    JournalSummaryStats,
    TradeJournalQuery,
)

logger = logging.getLogger(__name__)


class TradeJournalService:
    """Service wrapper for TradeJournal with automatic persistence.

    Combines in-memory TradeJournal operations with Redis persistence.
    All persistence operations are non-blocking - trading continues even
    if persistence fails.

    Attributes:
        _journal: In-memory TradeJournal instance
        _persistence: Redis persistence layer
        _session_id: Current session ID for grouping trades
    """

    def __init__(
        self,
        session_id: str | None = None,
        persistence: TradeJournalRedisPersistence | None = None,
    ) -> None:
        """Initialize the trade journal service.

        Args:
            session_id: Optional session ID for grouping trades
            persistence: Optional persistence layer instance
        """
        self._session_id = session_id or ""
        self._journal = TradeJournal(session_id=self._session_id)
        self._persistence = persistence or TradeJournalRedisPersistence()

        logger.info(
            f"TradeJournalService initialized: session_id={self._session_id}, "
            f"persistence_healthy={self.is_persistence_healthy()}"
        )

    @property
    def journal(self) -> TradeJournal:
        """Get the underlying TradeJournal instance.

        Returns:
            The in-memory TradeJournal
        """
        return self._journal

    @property
    def session_id(self) -> str:
        """Get the session ID.

        Returns:
            Current session ID
        """
        return self._session_id

    def is_persistence_healthy(self) -> bool:
        """Check if persistence layer is healthy.

        Returns:
            True if Redis persistence is working, False otherwise
        """
        if self._persistence is None:
            return False
        return self._persistence.is_healthy()

    def create_entry(
        self,
        position: Any,
        signal: Any,
        correlation_id: str = "",
    ) -> TradeJournalEntry:
        """Create a new trade journal entry and persist it.

        Args:
            position: The position object (must have symbol, side, entry_price,
                     quantity, position_id attributes)
            signal: The signal object (must have signal_id, confidence,
                   strategy_name or strategy attributes)
            correlation_id: Correlation ID for request tracing

        Returns:
            New TradeJournalEntry

        Raises:
            ValueError: If position or signal is missing required attributes
        """
        # Create entry in memory
        entry = self._journal.create_entry(
            position=position,
            signal=signal,
            correlation_id=correlation_id,
        )

        # Persist to Redis (non-blocking)
        try:
            if self._persistence is not None:
                success = self._persistence.save_entry(self._session_id, entry)
                if success:
                    logger.debug(f"Persisted journal entry: {entry.entry_id}")
                else:
                    logger.warning(f"Failed to persist journal entry: {entry.entry_id}")
        except Exception as e:
            # Log error but don't block trading
            logger.error(f"Failed to persist journal entry: {e}")

        return entry

    def record_fill(
        self,
        entry_id: str,
        fill_event: FillRecord,
    ) -> TradeJournalEntry:
        """Record a fill for a trade entry and persist it.

        Args:
            entry_id: ID of the trade entry
            fill_event: The fill record to add

        Returns:
            Updated TradeJournalEntry

        Raises:
            KeyError: If entry_id not found
            ValueError: If the trade is already closed
        """
        # Record fill in memory
        entry = self._journal.record_fill(entry_id, fill_event)

        # Persist to Redis (non-blocking)
        try:
            if self._persistence is not None:
                success = self._persistence.save_entry(self._session_id, entry)
                if success:
                    logger.debug(f"Persisted fill for entry: {entry_id}")
                else:
                    logger.warning(f"Failed to persist fill for entry: {entry_id}")
        except Exception as e:
            # Log error but don't block trading
            logger.error(f"Failed to persist fill: {e}")

        return entry

    def close_entry(
        self,
        entry_id: str,
        exit_price: float,
        exit_reason: ExitReason,
        pnl: float,
        exit_signal_id: str | None = None,
    ) -> TradeJournalEntry:
        """Close a trade entry and persist it.

        Args:
            entry_id: ID of the trade entry to close
            exit_price: The exit price
            exit_reason: Reason for closing
            pnl: Realized profit/loss
            exit_signal_id: Optional ID of signal that triggered exit

        Returns:
            Updated TradeJournalEntry

        Raises:
            KeyError: If entry_id not found
            ValueError: If the trade is already closed
        """
        # Close entry in memory
        entry = self._journal.close_entry(
            entry_id=entry_id,
            exit_price=exit_price,
            exit_reason=exit_reason,
            pnl=pnl,
            exit_signal_id=exit_signal_id,
        )

        # Persist to Redis (non-blocking)
        try:
            if self._persistence is not None:
                success = self._persistence.save_entry(self._session_id, entry)
                if success:
                    logger.debug(f"Persisted closed entry: {entry_id}")
                else:
                    logger.warning(f"Failed to persist closed entry: {entry_id}")
        except Exception as e:
            # Log error but don't block trading
            logger.error(f"Failed to persist closed entry: {e}")

        return entry

    def get_entry(self, entry_id: str) -> TradeJournalEntry | None:
        """Get a specific trade entry by ID.

        Args:
            entry_id: ID of the trade entry

        Returns:
            TradeJournalEntry or None if not found
        """
        return self._journal.get_entry(entry_id)

    def get_open_entries(self) -> list[TradeJournalEntry]:
        """Get all open trade entries.

        Returns:
            List of open TradeJournalEntry objects
        """
        return self._journal.get_open_entries()

    def get_closed_entries(self) -> list[TradeJournalEntry]:
        """Get all closed trade entries.

        Returns:
            List of closed TradeJournalEntry objects
        """
        return self._journal.get_closed_entries()

    def get_all_entries(self) -> list[TradeJournalEntry]:
        """Get all trade entries.

        Returns:
            List of all TradeJournalEntry objects
        """
        return self._journal.get_all_entries()

    def get_stats(self) -> dict[str, Any]:
        """Get journal statistics.

        Returns:
            Dictionary with statistics
        """
        return self._journal.get_stats()

    def recover(self, session_id: str) -> bool:
        """Recover journal from Redis.

        Loads all entries from Redis and populates the in-memory journal.

        Args:
            session_id: The session ID to recover

        Returns:
            True if recovery was successful, False otherwise
        """
        try:
            if self._persistence is None:
                logger.warning("No persistence layer configured, cannot recover")
                return False

            # Check if journal exists
            if not self._persistence.journal_exists(session_id):
                logger.info(f"No journal found for session {session_id}")
                return False

            # Load journal from Redis
            loaded_journal = self._persistence.load_journal(session_id)
            if loaded_journal is None:
                logger.warning(f"Failed to load journal for session {session_id}")
                return False

            # Replace current journal with loaded one
            self._journal = loaded_journal
            self._session_id = session_id

            entry_count = len(self._journal.get_all_entries())
            open_count = len(self._journal.get_open_entries())
            closed_count = len(self._journal.get_closed_entries())

            logger.info(
                f"Recovered journal for session {session_id}: "
                f"{entry_count} entries ({open_count} open, {closed_count} closed)"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to recover journal: {e}")
            return False

    def save(self) -> bool:
        """Save current journal state to Redis.

        Returns:
            True if saved successfully, False on failure
        """
        try:
            if self._persistence is None:
                logger.warning("No persistence layer configured, cannot save")
                return False

            return self._persistence.save_journal(self._journal)

        except Exception as e:
            logger.error(f"Failed to save journal: {e}")
            return False

    def clear(self) -> None:
        """Clear all entries (for testing/reset)."""
        self._journal.clear()
        logger.debug("Journal cleared")

    def to_dict(self) -> dict[str, Any]:
        """Convert journal to dictionary for serialization.

        Returns:
            Dictionary representation of the journal
        """
        return self._journal.to_dict()

    def query_entries(
        self, filters: JournalQueryFilters | None = None
    ) -> list[TradeJournalEntry]:
        """Query trade entries with optional filters.

        Provides read-only access to journal entries with filtering
        capabilities. This operation is non-blocking and safe to
        call during trading operations.

        Args:
            filters: Optional JournalQueryFilters to apply

        Returns:
            List of matching TradeJournalEntry objects

        Example:
            >>> # Query all closed trades for BTCUSDT
            >>> filters = JournalQueryFilters(
            ...     symbol="BTCUSDT",
            ...     status="closed"
            ... )
            >>> entries = service.query_entries(filters)
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.query(filters)

    def get_summary(
        self, filters: JournalQueryFilters | None = None
    ) -> JournalSummaryStats:
        """Get summary statistics for entries matching filters.

        Computes comprehensive statistics including win rate, average PnL,
        and performance metrics. This operation is read-only and
        non-blocking.

        Args:
            filters: Optional JournalQueryFilters to apply

        Returns:
            JournalSummaryStats with computed statistics

        Example:
            >>> # Get summary for all trades in the last 24 hours
            >>> from datetime import datetime, timedelta
            >>> filters = JournalQueryFilters(
            ...     start_time=datetime.now(UTC) - timedelta(hours=24)
            ... )
            >>> stats = service.get_summary(filters)
            >>> print(f"Win rate: {stats.win_rate:.2%}")
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_summary(filters)

    def get_symbols(self) -> list[str]:
        """Get list of all unique symbols in the journal.

        Returns:
            Sorted list of unique symbol strings
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_symbols()

    def get_strategies(self) -> list[str]:
        """Get list of all unique strategies in the journal.

        Returns:
            Sorted list of unique strategy name strings
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_strategies()

    def get_pnl_by_symbol(self) -> dict[str, float]:
        """Get total PnL grouped by symbol.

        Returns:
            Dictionary mapping symbol to total net PnL
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_pnl_by_symbol()

    def get_pnl_by_strategy(self) -> dict[str, float]:
        """Get total PnL grouped by strategy.

        Returns:
            Dictionary mapping strategy name to total net PnL
        """
        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_pnl_by_strategy()

    def query_reason_distribution(
        self,
        time_range: tuple[Any, Any] | None = None,
        symbol: str | None = None,
        rejected_signals: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Query reason code distributions with optional filtering.

        Provides comprehensive analysis of both exit reasons and rejection
        reasons with optional filtering by time range and symbol.

        Args:
            time_range: Optional tuple of (start_time, end_time) for filtering
            symbol: Optional symbol to filter by
            rejected_signals: Optional list of rejected signals for reject analysis

        Returns:
            Dictionary containing exit and reject reason distributions

        Example:
            >>> from datetime import datetime, timedelta, UTC
            >>> start = datetime.now(UTC) - timedelta(days=7)
            >>> end = datetime.now(UTC)
            >>> dist = service.query_reason_distribution(
            ...     time_range=(start, end),
            ...     symbol="BTCUSDT"
            ... )
            >>> print(dist["totals"]["total_closed_trades"])
            15
        """
        # Build filters
        filters = None
        if time_range or symbol:
            filters = JournalQueryFilters(
                start_time=time_range[0] if time_range else None,
                end_time=time_range[1] if time_range else None,
                symbol=symbol,
            )

        entries = self._journal.get_all_entries()
        query = TradeJournalQuery(entries)
        return query.get_reason_summary(filters, rejected_signals)

    def export_reason_report(
        self,
        time_range: tuple[Any, Any] | None = None,
        symbol: str | None = None,
        rejected_signals: list[Any] | None = None,
        format: str = "json",
    ) -> str:
        """Export reason code analysis in specified format.

        Generates a report of exit and rejection reason distributions
        in either JSON or CSV format.

        Args:
            time_range: Optional tuple of (start_time, end_time) for filtering
            symbol: Optional symbol to filter by
            rejected_signals: Optional list of rejected signals for reject analysis
            format: Export format - "json" or "csv" (default: "json")

        Returns:
            String containing the formatted report

        Raises:
            ValueError: If format is not "json" or "csv"

        Example:
            >>> # Export as JSON
            >>> json_report = service.export_reason_report(format="json")

            >>> # Export as CSV
            >>> csv_report = service.export_reason_report(format="csv")
        """
        import csv
        import io
        import json

        # Get reason distribution data
        data = self.query_reason_distribution(time_range, symbol, rejected_signals)

        if format == "json":
            return json.dumps(data, indent=2, default=str)

        elif format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(["category", "reason", "count", "percentage"])

            # Write exit reasons
            for reason, stats in data["exit_reasons"].items():
                writer.writerow(
                    [
                        "exit",
                        reason,
                        stats["count"],
                        stats["percentage"],
                    ]
                )

            # Write reject reasons
            for reason, stats in data["reject_reasons"].items():
                writer.writerow(
                    [
                        "reject",
                        reason,
                        stats["count"],
                        stats["percentage"],
                    ]
                )

            # Write totals
            writer.writerow([])
            writer.writerow(["totals", "", "", ""])
            writer.writerow(
                ["total_closed_trades", "", data["totals"]["total_closed_trades"], ""]
            )
            writer.writerow(
                [
                    "total_rejected_signals",
                    "",
                    data["totals"]["total_rejected_signals"],
                    "",
                ]
            )
            writer.writerow(
                ["total_decisions", "", data["totals"]["total_decisions"], ""]
            )

            return output.getvalue()

        else:
            raise ValueError(f"Invalid format '{format}'. Must be 'json' or 'csv'")
