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
