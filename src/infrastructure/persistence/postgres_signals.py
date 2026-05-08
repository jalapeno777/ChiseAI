"""Postgres Signals Persistence.

Provides PostgreSQL storage for trading signals with automatic table creation.
This module bridges Redis signal consumption to Postgres for long-term storage
and auditability.

Tables:
    - signals: Stores all trading signals with metadata

Part of PAPER-002: Paper Docker Service
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Table creation SQL
CREATE_SIGNALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id VARCHAR(255) PRIMARY KEY,
    token VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    base_score DECIMAL(10, 4) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'logged_only',
    timeframe VARCHAR(20) NOT NULL DEFAULT '1h',
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    processed_at TIMESTAMPTZ,
    order_id VARCHAR(255),
    execution_price DECIMAL(20, 8),
    execution_status VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_signals_token ON signals(token);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);
"""


class PostgresSignalsPersistence:
    """PostgreSQL persistence layer for trading signals.

    This class manages the signals table lifecycle, providing methods to:
    - Initialize the table schema (auto-creates if not exists)
    - Store new signals
    - Update signal status and execution info
    - Query signals by various criteria

    Attributes:
        host: PostgreSQL host address
        port: PostgreSQL port
        user: Database user
        password: Database password
        database: Database name
        _pool: Connection pool (lazily initialized)
        _initialized: Whether the table schema has been created
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        """Initialize PostgresSignalsPersistence.

        Args:
            host: PostgreSQL host (default: from env POSTGRES_HOST or localhost)
            port: PostgreSQL port (default: from env POSTGRES_PORT or 5432)
            user: Database user (default: from env POSTGRES_USER or postgres)
            password: Database password (default: from env POSTGRES_PASSWORD)
            database: Database name (default: from env POSTGRES_DB or chiseai_trading)
        """
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self.user = user or os.getenv("POSTGRES_USER", "postgres")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "")
        self.database = database or os.getenv("POSTGRES_DB", "chiseai_trading")
        self._pool: asyncpg.Pool | None = None
        self._initialized = False

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create the connection pool.

        Returns:
            asyncpg.Pool: The connection pool
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=2,
                max_size=10,
            )
        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def initialize(self) -> None:
        """Initialize the signals table if it doesn't exist.

        This method is idempotent - safe to call multiple times.
        """
        if self._initialized:
            return

        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(CREATE_SIGNALS_TABLE_SQL)
            self._initialized = True
            logger.info("Signals table initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize signals table: {e}")
            raise

    async def store_signal(
        self,
        signal_id: str,
        token: str,
        direction: str,
        confidence: float,
        base_score: float,
        status: str = "logged_only",
        timeframe: str = "1h",
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a new signal in the database.

        Args:
            signal_id: Unique signal identifier
            token: Trading pair symbol (e.g., 'BTC/USDT')
            direction: Signal direction ('long', 'short', 'neutral')
            confidence: Signal confidence (0.0 to 1.0)
            base_score: Base score (0.0 to 100.0)
            status: Signal status (default: 'logged_only')
            timeframe: Signal timeframe (default: '1h')
            timestamp: Signal timestamp (default: now)
            metadata: Additional metadata as JSON

        Returns:
            True if stored successfully, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        metadata_json = json.dumps(metadata or {})

        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signals 
                    (signal_id, token, direction, confidence, base_score, status, timeframe, timestamp, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (signal_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = NOW(),
                        metadata = EXCLUDED.metadata
                    """,
                    signal_id,
                    token,
                    direction,
                    confidence,
                    base_score,
                    status,
                    timeframe,
                    timestamp,
                    metadata_json,
                )
            logger.debug(f"Stored signal {signal_id} for {token}")
            return True
        except Exception as e:
            logger.error(f"Failed to store signal {signal_id}: {e}")
            return False

    async def update_signal_execution(
        self,
        signal_id: str,
        execution_status: str,
        order_id: str | None = None,
        execution_price: float | None = None,
        processed_at: datetime | None = None,
    ) -> bool:
        """Update signal execution information.

        Args:
            signal_id: Signal identifier
            execution_status: Execution status (e.g., 'submitted', 'filled', 'rejected')
            order_id: Associated order ID
            execution_price: Price at which signal was executed
            processed_at: When the signal was processed

        Returns:
            True if updated successfully, False otherwise
        """
        if processed_at is None:
            processed_at = datetime.now(UTC)

        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE signals 
                    SET execution_status = $2,
                        order_id = $3,
                        execution_price = $4,
                        processed_at = $5,
                        updated_at = NOW()
                    WHERE signal_id = $1
                    """,
                    signal_id,
                    execution_status,
                    order_id,
                    execution_price,
                    processed_at,
                )
            logger.debug(
                f"Updated execution for signal {signal_id}: {execution_status}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update signal execution {signal_id}: {e}")
            return False

    async def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        """Retrieve a signal by ID.

        Args:
            signal_id: Signal identifier

        Returns:
            Signal data as dictionary or None if not found
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM signals WHERE signal_id = $1", signal_id
                )
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get signal {signal_id}: {e}")
            return None

    async def get_signals_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get signals by status.

        Args:
            status: Signal status to filter by
            limit: Maximum number of signals to return

        Returns:
            List of signal dictionaries
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM signals 
                    WHERE status = $1 
                    ORDER BY timestamp DESC 
                    LIMIT $2
                    """,
                    status,
                    limit,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get signals by status {status}: {e}")
            return []

    async def get_signals_by_token(
        self,
        token: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get signals for a specific trading pair.

        Args:
            token: Trading pair symbol
            start_time: Filter start time
            end_time: Filter end time
            limit: Maximum number of signals to return

        Returns:
            List of signal dictionaries
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                if start_time and end_time:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM signals 
                        WHERE token = $1 AND timestamp BETWEEN $2 AND $3
                        ORDER BY timestamp DESC 
                        LIMIT $4
                        """,
                        token,
                        start_time,
                        end_time,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM signals 
                        WHERE token = $1 
                        ORDER BY timestamp DESC 
                        LIMIT $2
                        """,
                        token,
                        limit,
                    )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get signals for {token}: {e}")
            return []

    async def count_signals_by_status(self) -> dict[str, int]:
        """Count signals grouped by status.

        Returns:
            Dictionary mapping status to count
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT status, COUNT(*) as count FROM signals GROUP BY status"
                )
                return {row["status"]: row["count"] for row in rows}
        except Exception as e:
            logger.error(f"Failed to count signals by status: {e}")
            return {}

    async def table_exists(self) -> bool:
        """Check if the signals table exists.

        Returns:
            True if table exists, False otherwise
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'signals'
                    )
                    """)
                return result or False
        except Exception as e:
            logger.error(f"Failed to check if signals table exists: {e}")
            return False


@asynccontextmanager
async def get_postgres_signals():
    """Context manager for PostgresSignalsPersistence.

    Usage:
        async with get_postgres_signals() as persistence:
            await persistence.store_signal(...)

    Yields:
        PostgresSignalsPersistence: The persistence instance
    """
    persistence = PostgresSignalsPersistence()
    try:
        await persistence.initialize()
        yield persistence
    finally:
        await persistence.close()
