"""PostgreSQL storage implementation for signal history.

Provides fallback and audit storage for signals and outcomes using
PostgreSQL with connection pooling and UPSERT support.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

from market_analysis.signal_storage.interface import SignalStorageInterface
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)

logger = logging.getLogger(__name__)


class PostgresSignalStorage(SignalStorageInterface):
    """PostgreSQL implementation of signal storage.

    Uses two tables:
        - signals: Stores signal records with unique signal_id
        - signal_outcomes: Stores outcome records linked by signal_id

    Features:
        - Connection pooling via asyncpg
        - UPSERT for idempotency (ON CONFLICT DO UPDATE)
        - Efficient indexing for queries
    """

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        dsn: str = "",
        host: str = "localhost",
        port: int = 5432,
        database: str = "chiseai",
        user: str = "",  # nosec B107
        password: str = "",  # nosec B107
    ):
        """Initialize PostgreSQL storage.

        Args:
            pool: Existing connection pool (optional)
            dsn: Full connection DSN (used if pool not provided)
            host: Database host (used if dsn not provided)
            port: Database port (used if dsn not provided)
            database: Database name (used if dsn not provided)
            user: Database user (used if dsn not provided)
            password: Database password (used if dsn not provided)
        """
        self._pool = pool
        self._dsn = dsn
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._owned_pool = pool is None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            import asyncpg

            if self._dsn:
                self._pool = await asyncpg.create_pool(self._dsn)
            else:
                self._pool = await asyncpg.create_pool(
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    user=self._user,
                    password=self._password,
                )
        return self._pool

    async def initialize_schema(self) -> None:
        """Initialize database schema (tables and indexes).

        Creates the signals and signal_outcomes tables if they don't exist.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # Create signals table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id UUID PRIMARY KEY,
                    token VARCHAR(20) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    confidence REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    score REAL NOT NULL,
                    multiplier_applied REAL,
                    indicators_used TEXT[],
                    timeframes_used TEXT[],
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)

            # Create indexes for signals table
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_token
                ON signals(token)
                """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_timestamp
                ON signals(timestamp)
                """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_direction
                ON signals(direction)
                """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_confidence
                ON signals(confidence)
                """)

            # Create signal_outcomes table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id SERIAL PRIMARY KEY,
                    signal_id UUID NOT NULL REFERENCES signals(signal_id)
                        ON DELETE CASCADE,
                    exit_timestamp BIGINT NOT NULL,
                    is_win BOOLEAN NOT NULL,
                    pnl REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    duration_hours REAL NOT NULL,
                    outcome_type VARCHAR(20) NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(signal_id)
                )
                """)

            # Create indexes for outcomes table
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcomes_signal_id
                ON signal_outcomes(signal_id)
                """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcomes_is_win
                ON signal_outcomes(is_win)
                """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcomes_exit_timestamp
                ON signal_outcomes(exit_timestamp)
                """)

        logger.info("PostgreSQL schema initialized")

    async def store_signal(self, signal: SignalRecord) -> bool:
        """Store a signal record with UPSERT.

        Args:
            signal: SignalRecord to store

        Returns:
            True if stored successfully
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signals (
                        signal_id, token, timestamp, direction, confidence,
                        entry_price, score, multiplier_applied, indicators_used,
                        timeframes_used, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (signal_id) DO UPDATE SET
                        token = EXCLUDED.token,
                        timestamp = EXCLUDED.timestamp,
                        direction = EXCLUDED.direction,
                        confidence = EXCLUDED.confidence,
                        entry_price = EXCLUDED.entry_price,
                        score = EXCLUDED.score,
                        multiplier_applied = EXCLUDED.multiplier_applied,
                        indicators_used = EXCLUDED.indicators_used,
                        timeframes_used = EXCLUDED.timeframes_used,
                        metadata = EXCLUDED.metadata
                    """,
                    signal.signal_id,
                    signal.token,
                    signal.timestamp,
                    signal.direction.value,
                    signal.confidence,
                    signal.entry_price,
                    signal.score,
                    signal.multiplier_applied,
                    signal.indicators_used,
                    signal.timeframes_used,
                    signal.metadata,
                )

            logger.debug(f"Stored signal {signal.signal_id} in PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to store signal in PostgreSQL: {e}")
            return False

    async def store_outcome(self, outcome: OutcomeRecord) -> bool:
        """Store an outcome record with UPSERT.

        Args:
            outcome: OutcomeRecord to store

        Returns:
            True if stored successfully
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signal_outcomes (
                        signal_id, exit_timestamp, is_win, pnl,
                        exit_price, duration_hours, outcome_type, note
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (signal_id) DO UPDATE SET
                        exit_timestamp = EXCLUDED.exit_timestamp,
                        is_win = EXCLUDED.is_win,
                        pnl = EXCLUDED.pnl,
                        exit_price = EXCLUDED.exit_price,
                        duration_hours = EXCLUDED.duration_hours,
                        outcome_type = EXCLUDED.outcome_type,
                        note = EXCLUDED.note
                    """,
                    outcome.signal_id,
                    outcome.exit_timestamp,
                    outcome.is_win,
                    outcome.pnl,
                    outcome.exit_price,
                    outcome.duration_hours,
                    outcome.outcome_type.value,
                    outcome.note,
                )

            logger.debug(f"Stored outcome for signal {outcome.signal_id} in PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to store outcome in PostgreSQL: {e}")
            return False

    async def query_signals(
        self,
        token: str | None = None,
        direction: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        timeframes: list[str] | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Query signals with filters.

        Args:
            token: Filter by token
            direction: Filter by direction
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used (any match)
            timeframes: Filter by timeframes used (any match)
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            limit: Maximum number of results

        Returns:
            List of SignalRecord
        """
        try:
            pool = await self._get_pool()

            # Build query dynamically
            conditions = []
            params: list[Any] = []
            param_idx = 1

            if token:
                conditions.append(f"token = ${param_idx}")
                params.append(token)
                param_idx += 1

            if direction:
                conditions.append(f"direction = ${param_idx}")
                params.append(direction)
                param_idx += 1

            if start_time:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            if min_confidence is not None:
                conditions.append(f"confidence >= ${param_idx}")
                params.append(min_confidence)
                param_idx += 1

            if max_confidence is not None:
                conditions.append(f"confidence <= ${param_idx}")
                params.append(max_confidence)
                param_idx += 1

            if indicators:
                # Check if any indicator overlaps
                conditions.append(f"indicators_used && ${param_idx}::text[]")
                params.append(indicators)
                param_idx += 1

            if timeframes:
                conditions.append(f"timeframes_used && ${param_idx}::text[]")
                params.append(timeframes)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "TRUE"

            query = f"""
                SELECT signal_id, token, timestamp, direction, confidence,
                       entry_price, score, multiplier_applied, indicators_used,
                       timeframes_used, metadata
                FROM signals
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_idx}
            """  # nosec B608
            params.append(limit)

            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [self._row_to_signal(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to query signals from PostgreSQL: {e}")
            return []

    async def get_signal_by_id(self, signal_id: str) -> SignalRecord | None:
        """Get a signal by its unique ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            SignalRecord if found, None otherwise
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT signal_id, token, timestamp, direction, confidence,
                           entry_price, score, multiplier_applied, indicators_used,
                           timeframes_used, metadata
                    FROM signals
                    WHERE signal_id = $1
                    """,
                    signal_id,
                )

            return self._row_to_signal(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get signal by ID from PostgreSQL: {e}")
            return None

    async def get_outcome_by_signal_id(self, signal_id: str) -> OutcomeRecord | None:
        """Get outcome for a signal by signal ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            OutcomeRecord if found, None otherwise
        """
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT signal_id, exit_timestamp, is_win, pnl,
                           exit_price, duration_hours, outcome_type, note
                    FROM signal_outcomes
                    WHERE signal_id = $1
                    """,
                    signal_id,
                )

            return self._row_to_outcome(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get outcome by signal ID from PostgreSQL: {e}")
            return None

    async def query_signals_with_outcomes(
        self,
        token: str | None = None,
        direction: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        timeframes: list[str] | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        resolved_only: bool = False,
        limit: int = 100,
    ) -> list[SignalWithOutcome]:
        """Query signals with their outcomes.

        Args:
            token: Filter by token
            direction: Filter by direction
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            timeframes: Filter by timeframes used
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            resolved_only: Only return signals with outcomes
            limit: Maximum number of results

        Returns:
            List of SignalWithOutcome
        """
        try:
            pool = await self._get_pool()

            # Build query with JOIN
            conditions = []
            params: list[Any] = []
            param_idx = 1

            if token:
                conditions.append(f"s.token = ${param_idx}")
                params.append(token)
                param_idx += 1

            if direction:
                conditions.append(f"s.direction = ${param_idx}")
                params.append(direction)
                param_idx += 1

            if start_time:
                conditions.append(f"s.timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"s.timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            if min_confidence is not None:
                conditions.append(f"s.confidence >= ${param_idx}")
                params.append(min_confidence)
                param_idx += 1

            if max_confidence is not None:
                conditions.append(f"s.confidence <= ${param_idx}")
                params.append(max_confidence)
                param_idx += 1

            if indicators:
                conditions.append(f"s.indicators_used && ${param_idx}::text[]")
                params.append(indicators)
                param_idx += 1

            if timeframes:
                conditions.append(f"s.timeframes_used && ${param_idx}::text[]")
                params.append(timeframes)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "TRUE"

            join_type = "INNER JOIN" if resolved_only else "LEFT JOIN"

            query = f"""
                SELECT s.signal_id, s.token, s.timestamp, s.direction, s.confidence,
                       s.entry_price, s.score, s.multiplier_applied, s.indicators_used,
                       s.timeframes_used, s.metadata,
                       o.exit_timestamp, o.is_win, o.pnl, o.exit_price,
                       o.duration_hours, o.outcome_type, o.note
                FROM signals s
                {join_type} signal_outcomes o ON s.signal_id = o.signal_id
                WHERE {where_clause}
                ORDER BY s.timestamp DESC
                LIMIT ${{param_idx}}
            """  # nosec B608
            params.append(limit)

            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            result = []
            for row in rows:
                signal = self._row_to_signal(row)
                outcome = self._row_to_outcome(row) if row["exit_timestamp"] else None
                result.append(SignalWithOutcome(signal=signal, outcome=outcome))

            return result

        except Exception as e:
            logger.error(f"Failed to query signals with outcomes from PostgreSQL: {e}")
            return []

    async def calculate_prediction_accuracy(
        self,
        signal_type: str | None = None,
        confidence_bucket: str | None = None,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
    ) -> dict[str, Any]:
        """Calculate prediction accuracy metrics.

        Args:
            signal_type: Filter by signal type
            confidence_bucket: Filter by confidence bucket
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used

        Returns:
            Dictionary with accuracy metrics
        """
        try:
            pool = await self._get_pool()

            # Build query
            conditions = ["o.signal_id IS NOT NULL"]  # Only resolved signals
            params: list[Any] = []
            param_idx = 1

            if token:
                conditions.append(f"s.token = ${param_idx}")
                params.append(token)
                param_idx += 1

            if start_time:
                conditions.append(f"s.timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"s.timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            if indicators:
                conditions.append(f"s.indicators_used && ${param_idx}::text[]")
                params.append(indicators)
                param_idx += 1

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN o.is_win THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN NOT o.is_win THEN 1 ELSE 0 END) as losses,
                    AVG(o.pnl) as avg_pnl,
                    SUM(o.pnl) as total_pnl,
                    AVG(o.duration_hours) as avg_duration_hours
                FROM signals s
                INNER JOIN signal_outcomes o ON s.signal_id = o.signal_id
                WHERE {where_clause}
            """  # nosec B608

            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)

            if not row or row["total_signals"] == 0:
                return {
                    "total_signals": 0,
                    "resolved_signals": 0,
                    "wins": 0,
                    "losses": 0,
                    "accuracy": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl": 0.0,
                    "total_pnl": 0.0,
                    "avg_duration_hours": 0.0,
                }

            total = row["total_signals"]
            wins = row["wins"] or 0
            accuracy = wins / total if total > 0 else 0.0

            return {
                "total_signals": total,
                "resolved_signals": total,
                "wins": wins,
                "losses": row["losses"] or 0,
                "accuracy": round(accuracy, 4),
                "win_rate": round(accuracy, 4),
                "avg_pnl": round(row["avg_pnl"] or 0.0, 8),
                "total_pnl": round(row["total_pnl"] or 0.0, 8),
                "avg_duration_hours": round(row["avg_duration_hours"] or 0.0, 2),
            }

        except Exception as e:
            logger.error(f"Failed to calculate accuracy from PostgreSQL: {e}")
            return {
                "total_signals": 0,
                "resolved_signals": 0,
                "wins": 0,
                "losses": 0,
                "accuracy": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "total_pnl": 0.0,
                "avg_duration_hours": 0.0,
            }

    async def get_unresolved_signals(
        self,
        before_timestamp: int | None = None,
        token: str | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Get signals that don't have outcomes yet.

        Args:
            before_timestamp: Only signals before this timestamp (ms)
            token: Filter by token
            limit: Maximum number of results

        Returns:
            List of unresolved SignalRecord
        """
        try:
            pool = await self._get_pool()

            conditions = ["o.signal_id IS NULL"]
            params: list[Any] = []
            param_idx = 1

            if before_timestamp:
                conditions.append(f"s.timestamp <= ${param_idx}")
                params.append(before_timestamp)
                param_idx += 1

            if token:
                conditions.append(f"s.token = ${param_idx}")
                params.append(token)
                param_idx += 1

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT s.signal_id, s.token, s.timestamp, s.direction, s.confidence,
                       s.entry_price, s.score, s.multiplier_applied, s.indicators_used,
                       s.timeframes_used, s.metadata
                FROM signals s
                LEFT JOIN signal_outcomes o ON s.signal_id = o.signal_id
                WHERE {where_clause}
                ORDER BY s.timestamp DESC
                LIMIT ${param_idx}
            """  # nosec B608
            params.append(limit)

            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [self._row_to_signal(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get unresolved signals from PostgreSQL: {e}")
            return []

    async def close(self) -> None:
        """Close the storage connection pool."""
        if self._owned_pool and self._pool:
            await self._pool.close()
            self._pool = None

    def _row_to_signal(self, row: asyncpg.Record) -> SignalRecord:
        """Convert database row to SignalRecord."""
        return SignalRecord(
            signal_id=str(row["signal_id"]),
            token=row["token"],
            timestamp=row["timestamp"],
            direction=SignalDirection(row["direction"]),
            confidence=row["confidence"],
            entry_price=row["entry_price"],
            score=row["score"],
            multiplier_applied=row["multiplier_applied"],
            indicators_used=(
                list(row["indicators_used"]) if row["indicators_used"] else []
            ),
            timeframes_used=(
                list(row["timeframes_used"]) if row["timeframes_used"] else []
            ),
            metadata=row["metadata"] if row["metadata"] else {},
        )

    def _row_to_outcome(self, row: asyncpg.Record) -> OutcomeRecord | None:
        """Convert database row to OutcomeRecord."""
        if row["exit_timestamp"] is None:
            return None

        outcome_type_str = row["outcome_type"] or "unknown"
        try:
            outcome_type = OutcomeType(outcome_type_str)
        except ValueError:
            outcome_type = OutcomeType.UNKNOWN

        return OutcomeRecord(
            signal_id=str(row["signal_id"]),
            exit_timestamp=row["exit_timestamp"],
            is_win=row["is_win"],
            pnl=row["pnl"],
            exit_price=row["exit_price"],
            duration_hours=row["duration_hours"],
            outcome_type=outcome_type,
            note=row["note"],
        )
