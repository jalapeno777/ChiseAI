"""OutcomeStore - SQLite-backed outcome persistence and querying.

Provides a database-backed store for signal outcomes with CRUD operations
and query methods for historical analysis.

For ST-ICT-P1: Signal Outcome Database Backend
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from execution.outcomes.models import dict_to_row, init_db, row_to_signal_outcome
from ml.models.signal_outcome import OutcomeType, SignalOutcome, SignalOutcomeStatus

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class QueryFilters:
    """Filters for outcome queries."""

    signal_id: str | None = None
    symbol: str | None = None
    outcome_type: OutcomeType | None = None
    status: SignalOutcomeStatus | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_test: bool | None = None
    execution_venue: str | None = None
    execution_mode: str | None = None
    limit: int = 100
    offset: int = 0


class OutcomeStore:
    """SQLite-backed outcome store with query capabilities.

    Provides persistent storage for signal outcomes with indexed queries
    by signal_id, timestamp range, and outcome type.

    Attributes:
        db_path: Path to SQLite database file
        conn: Active database connection
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        in_memory: bool = False,
    ):
        """Initialize OutcomeStore.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.chiseai/outcomes.db
            in_memory: If True, use in-memory SQLite database (for testing)
        """
        if in_memory:
            self._db_path = ":memory:"
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        elif db_path:
            self._db_path = str(db_path)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        else:
            # Default location
            home = os.path.expanduser("~")
            db_dir = os.path.join(home, ".chiseai")
            os.makedirs(db_dir, exist_ok=True)
            self._db_path = os.path.join(db_dir, "outcomes.db")
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)

        self._conn.row_factory = sqlite3.Row
        init_db(self._conn)

        logger.info(
            f"OutcomeStore initialized: db_path={self._db_path}, in_memory={in_memory}"
        )

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("OutcomeStore connection closed")

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def create(self, outcome: SignalOutcome) -> str:
        """Create a new outcome record.

        Args:
            outcome: SignalOutcome to persist

        Returns:
            The outcome_id of the created record

        Raises:
            ValueError: If outcome with same outcome_id already exists
        """
        row = dict_to_row(outcome.to_dict())

        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO signal_outcomes (
                    outcome_id, signal_id, order_id, symbol, token, side, direction,
                    fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                    status, created_at, metadata, entry_price, exit_price, entry_time,
                    exit_time, leverage, entry_reason, position_size, execution_venue,
                    execution_mode, execution_source, venue_metadata, confidence_score,
                    signal_type, is_test
                ) VALUES (
                    :outcome_id, :signal_id, :order_id, :symbol, :token, :side, :direction,
                    :fill_price, :fill_quantity, :fill_timestamp, :outcome_type, :pnl, :fee,
                    :status, :created_at, :metadata, :entry_price, :exit_price, :entry_time,
                    :exit_time, :leverage, :entry_reason, :position_size, :execution_venue,
                    :execution_mode, :execution_source, :venue_metadata, :confidence_score,
                    :signal_type, :is_test
                )
                """,
                row,
            )

        logger.debug(f"Created outcome: outcome_id={outcome.outcome_id}")
        return str(outcome.outcome_id)

    def create_many(self, outcomes: list[SignalOutcome]) -> list[str]:
        """Create multiple outcome records in a batch.

        Args:
            outcomes: List of SignalOutcome objects to persist

        Returns:
            List of outcome_ids for the created records
        """
        if not outcomes:
            return []

        outcome_ids = []
        with self._transaction() as conn:
            for outcome in outcomes:
                row = dict_to_row(outcome.to_dict())
                conn.execute(
                    """
                    INSERT INTO signal_outcomes (
                        outcome_id, signal_id, order_id, symbol, token, side, direction,
                        fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                        status, created_at, metadata, entry_price, exit_price, entry_time,
                        exit_time, leverage, entry_reason, position_size, execution_venue,
                        execution_mode, execution_source, venue_metadata, confidence_score,
                        signal_type, is_test
                    ) VALUES (
                        :outcome_id, :signal_id, :order_id, :symbol, :token, :side, :direction,
                        :fill_price, :fill_quantity, :fill_timestamp, :outcome_type, :pnl, :fee,
                        :status, :created_at, :metadata, :entry_price, :exit_price, :entry_time,
                        :exit_time, :leverage, :entry_reason, :position_size, :execution_venue,
                        :execution_mode, :execution_source, :venue_metadata, :confidence_score,
                        :signal_type, :is_test
                    )
                    """,
                    row,
                )
                outcome_ids.append(str(outcome.outcome_id))

        logger.debug(f"Created {len(outcomes)} outcomes in batch")
        return outcome_ids

    def read(self, outcome_id: str) -> SignalOutcome | None:
        """Read an outcome by ID.

        Args:
            outcome_id: The outcome_id to look up

        Returns:
            SignalOutcome if found, None otherwise
        """
        cursor = self._conn.execute(
            "SELECT * FROM signal_outcomes WHERE outcome_id = ?",
            (outcome_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return row_to_signal_outcome(dict(row))

    def update(self, outcome: SignalOutcome) -> bool:
        """Update an existing outcome record.

        Args:
            outcome: SignalOutcome with updated data

        Returns:
            True if updated, False if not found
        """
        row = dict_to_row(outcome.to_dict())

        with self._transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE signal_outcomes SET
                    signal_id = :signal_id,
                    order_id = :order_id,
                    symbol = :symbol,
                    token = :token,
                    side = :side,
                    direction = :direction,
                    fill_price = :fill_price,
                    fill_quantity = :fill_quantity,
                    fill_timestamp = :fill_timestamp,
                    outcome_type = :outcome_type,
                    pnl = :pnl,
                    fee = :fee,
                    status = :status,
                    metadata = :metadata,
                    entry_price = :entry_price,
                    exit_price = :exit_price,
                    entry_time = :entry_time,
                    exit_time = :exit_time,
                    leverage = :leverage,
                    entry_reason = :entry_reason,
                    position_size = :position_size,
                    execution_venue = :execution_venue,
                    execution_mode = :execution_mode,
                    execution_source = :execution_source,
                    venue_metadata = :venue_metadata,
                    confidence_score = :confidence_score,
                    signal_type = :signal_type,
                    is_test = :is_test
                WHERE outcome_id = :outcome_id
                """,
                row,
            )

        if cursor.rowcount == 0:
            logger.warning(f"Outcome not found for update: {outcome.outcome_id}")
            return False

        logger.debug(f"Updated outcome: outcome_id={outcome.outcome_id}")
        return True

    def delete(self, outcome_id: str) -> bool:
        """Delete an outcome by ID.

        Args:
            outcome_id: The outcome_id to delete

        Returns:
            True if deleted, False if not found
        """
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM signal_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            )

        if cursor.rowcount == 0:
            logger.warning(f"Outcome not found for delete: {outcome_id}")
            return False

        logger.debug(f"Deleted outcome: outcome_id={outcome_id}")
        return True

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    def by_signal_id(self, signal_id: str) -> list[SignalOutcome]:
        """Query outcomes by signal_id.

        Args:
            signal_id: The signal UUID or string to query

        Returns:
            List of SignalOutcome matching the signal_id
        """
        cursor = self._conn.execute(
            """
            SELECT * FROM signal_outcomes
            WHERE signal_id = ?
            ORDER BY created_at DESC
            """,
            (signal_id,),
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    def by_timerange(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[SignalOutcome]:
        """Query outcomes by time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            symbol: Optional symbol filter
            limit: Maximum number of results

        Returns:
            List of SignalOutcome within the time range
        """
        conditions = []
        params: list[Any] = []

        if start_time is not None:
            conditions.append("created_at >= ?")
            params.append(start_time.isoformat())

        if end_time is not None:
            conditions.append("created_at <= ?")
            params.append(end_time.isoformat())

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = self._conn.execute(
            f"""
            SELECT * FROM signal_outcomes
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    def by_result_type(
        self,
        outcome_type: OutcomeType,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[SignalOutcome]:
        """Query outcomes by result/ outcome type.

        Args:
            outcome_type: The OutcomeType to filter by (tp_hit, sl_hit, etc.)
            start_time: Optional start of time range
            end_time: Optional end of time range
            symbol: Optional symbol filter
            limit: Maximum number of results

        Returns:
            List of SignalOutcome matching the outcome type
        """
        conditions = ["outcome_type = ?"]
        params: list[Any] = [
            outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type)
        ]

        if start_time is not None:
            conditions.append("created_at >= ?")
            params.append(start_time.isoformat())

        if end_time is not None:
            conditions.append("created_at <= ?")
            params.append(end_time.isoformat())

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        where_clause = " AND ".join(conditions)

        cursor = self._conn.execute(
            f"""
            SELECT * FROM signal_outcomes
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    def by_symbol(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[SignalOutcome]:
        """Query outcomes by symbol.

        Args:
            symbol: The trading pair symbol (e.g., "BTCUSDT")
            start_time: Optional start of time range
            end_time: Optional end of time range
            limit: Maximum number of results

        Returns:
            List of SignalOutcome for the symbol
        """
        conditions = ["symbol = ?"]
        params: list[Any] = [symbol]

        if start_time is not None:
            conditions.append("created_at >= ?")
            params.append(start_time.isoformat())

        if end_time is not None:
            conditions.append("created_at <= ?")
            params.append(end_time.isoformat())

        where_clause = " AND ".join(conditions)

        cursor = self._conn.execute(
            f"""
            SELECT * FROM signal_outcomes
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    def by_status(
        self,
        status: SignalOutcomeStatus,
        limit: int = 100,
    ) -> list[SignalOutcome]:
        """Query outcomes by status.

        Args:
            status: The SignalOutcomeStatus to filter by
            limit: Maximum number of results

        Returns:
            List of SignalOutcome with the given status
        """
        status_value = status.value if hasattr(status, "value") else str(status)

        cursor = self._conn.execute(
            """
            SELECT * FROM signal_outcomes
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status_value, limit),
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    def query(self, filters: QueryFilters) -> list[SignalOutcome]:
        """Query outcomes with flexible filters.

        Args:
            filters: QueryFilters object with all filter criteria

        Returns:
            List of SignalOutcome matching the filters
        """
        conditions = []
        params: list[Any] = []

        if filters.signal_id is not None:
            conditions.append("signal_id = ?")
            params.append(filters.signal_id)

        if filters.symbol is not None:
            conditions.append("symbol = ?")
            params.append(filters.symbol)

        if filters.outcome_type is not None:
            conditions.append("outcome_type = ?")
            params.append(
                filters.outcome_type.value
                if hasattr(filters.outcome_type, "value")
                else str(filters.outcome_type)
            )

        if filters.status is not None:
            conditions.append("status = ?")
            params.append(
                filters.status.value
                if hasattr(filters.status, "value")
                else str(filters.status)
            )

        if filters.start_time is not None:
            conditions.append("created_at >= ?")
            params.append(filters.start_time.isoformat())

        if filters.end_time is not None:
            conditions.append("created_at <= ?")
            params.append(filters.end_time.isoformat())

        if filters.is_test is not None:
            conditions.append("is_test = ?")
            params.append(1 if filters.is_test else 0)

        if filters.execution_venue is not None:
            conditions.append("execution_venue = ?")
            params.append(filters.execution_venue)

        if filters.execution_mode is not None:
            conditions.append("execution_mode = ?")
            params.append(filters.execution_mode)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = self._conn.execute(
            f"""
            SELECT * FROM signal_outcomes
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, filters.limit, filters.offset],
        )

        return [row_to_signal_outcome(dict(row)) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def count(self, filters: QueryFilters | None = None) -> int:
        """Count outcomes matching filters.

        Args:
            filters: Optional QueryFilters for counting

        Returns:
            Number of matching outcomes
        """
        if filters is None:
            cursor = self._conn.execute("SELECT COUNT(*) as count FROM signal_outcomes")
            return cursor.fetchone()["count"]

        conditions = []
        params: list[Any] = []

        if filters.signal_id is not None:
            conditions.append("signal_id = ?")
            params.append(filters.signal_id)

        if filters.symbol is not None:
            conditions.append("symbol = ?")
            params.append(filters.symbol)

        if filters.outcome_type is not None:
            conditions.append("outcome_type = ?")
            params.append(
                filters.outcome_type.value
                if hasattr(filters.outcome_type, "value")
                else str(filters.outcome_type)
            )

        if filters.status is not None:
            conditions.append("status = ?")
            params.append(
                filters.status.value
                if hasattr(filters.status, "value")
                else str(filters.status)
            )

        if filters.start_time is not None:
            conditions.append("created_at >= ?")
            params.append(filters.start_time.isoformat())

        if filters.end_time is not None:
            conditions.append("created_at <= ?")
            params.append(filters.end_time.isoformat())

        if filters.is_test is not None:
            conditions.append("is_test = ?")
            params.append(1 if filters.is_test else 0)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = self._conn.execute(
            f"SELECT COUNT(*) as count FROM signal_outcomes WHERE {where_clause}",
            params,
        )
        return cursor.fetchone()["count"]

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about stored outcomes.

        Returns:
            Dictionary with outcome statistics
        """
        cursor = self._conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count,
                COUNT(CASE WHEN status = 'error' THEN 1 END) as error_count,
                COUNT(CASE WHEN outcome_type = 'tp_hit' THEN 1 END) as tp_hit_count,
                COUNT(CASE WHEN outcome_type = 'sl_hit' THEN 1 END) as sl_hit_count,
                COUNT(CASE WHEN outcome_type = 'manual_close' THEN 1 END) as manual_close_count,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                COUNT(DISTINCT symbol) as unique_symbols
            FROM signal_outcomes
            """)
        row = cursor.fetchone()
        return dict(row) if row else {}

    def health_check(self) -> dict[str, Any]:
        """Check database health.

        Returns:
            Health status dictionary
        """
        try:
            cursor = self._conn.execute("SELECT 1")
            cursor.fetchone()
            return {
                "healthy": True,
                "db_path": self._db_path,
                "stats": self.get_stats(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "db_path": self._db_path,
                "error": str(e),
            }

    def __enter__(self) -> OutcomeStore:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
