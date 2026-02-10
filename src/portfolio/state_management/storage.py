"""Storage backends for portfolio state persistence.

Provides InfluxDB and PostgreSQL storage implementations with
fallback support for fault tolerance.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    PortfolioState,
    Position,
)
from portfolio.state_management.tracker import PortfolioStorageInterface

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuration for storage backends.

    Attributes:
        host: Database host
        port: Database port
        database: Database name
        username: Authentication username
        password: Authentication password
        ssl: Whether to use SSL connection
    """

    host: str
    port: int
    database: str
    username: str | None = None
    password: str | None = None
    ssl: bool = False


class InfluxDBPortfolioStorage(PortfolioStorageInterface):
    """InfluxDB storage backend for portfolio snapshots.

    Stores time-series snapshot data optimized for trend analysis.
    """

    def __init__(self, config: StorageConfig):
        """Initialize InfluxDB storage.

        Args:
            config: Storage configuration
        """
        self.config = config
        self._client: Any | None = None
        self._write_api: Any | None = None
        self._query_api: Any | None = None

    async def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if self._client is None:
            try:
                from influxdb_client import InfluxDBClient

                url = f"http://{self.config.host}:{self.config.port}"
                self._client = InfluxDBClient(
                    url=url,
                    token=f"{self.config.username}:{self.config.password}",
                    org="-",
                )
                self._write_api = self._client.write_api()
                self._query_api = self._client.query_api()
            except ImportError:
                logger.error(
                    "influxdb-client not installed, cannot use InfluxDBPortfolioStorage"
                )
                raise

        return self._client

    async def store_state(self, state: PortfolioState) -> bool:
        """Store portfolio state (stored as snapshot)."""
        # InfluxDB is optimized for snapshots, not full state
        snapshot = PortfolioSnapshot.from_portfolio_state(
            snapshot_id=state.portfolio_id + "_state",
            state=state,
        )
        return await self.store_snapshot(snapshot)

    async def store_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        """Store portfolio snapshot in InfluxDB."""
        try:
            from influxdb_client import Point
            from influxdb_client.client.write_api import SYNCHRONOUS

            client = await self._get_client()
            write_api = client.write_api(write_options=SYNCHRONOUS)

            # Create point for portfolio metrics
            point = (
                Point("portfolio_snapshot")
                .tag("portfolio_id", snapshot.portfolio_id)
                .tag("snapshot_id", snapshot.snapshot_id)
                .field("total_equity", snapshot.total_equity)
                .field("available_equity", snapshot.available_equity)
                .field("margin_used", snapshot.margin_used)
                .field("unrealized_pnl", snapshot.unrealized_pnl)
                .field("realized_pnl", snapshot.realized_pnl)
                .field("position_count", snapshot.position_count)
                .field("balance_summary", json.dumps(snapshot.balance_summary))
                .time(snapshot.timestamp)
            )

            write_api.write(bucket=self.config.database, record=point)
            logger.debug(f"Stored snapshot {snapshot.snapshot_id} in InfluxDB")
            return True

        except Exception as e:
            logger.error(f"Failed to store snapshot in InfluxDB: {e}")
            return False

    async def get_latest_state(self, portfolio_id: str) -> PortfolioState | None:
        """Get latest portfolio state from InfluxDB."""
        # InfluxDB stores snapshots, reconstruct latest state
        snapshots = await self.get_snapshots(portfolio_id, limit=1)
        if not snapshots:
            return None

        # Reconstruct state from latest snapshot
        snapshot = snapshots[0]
        return PortfolioState(
            portfolio_id=portfolio_id,
            total_equity=snapshot.total_equity,
            available_equity=snapshot.available_equity,
            margin_used=snapshot.margin_used,
            unrealized_pnl=snapshot.unrealized_pnl,
            realized_pnl=snapshot.realized_pnl,
            timestamp=snapshot.timestamp,
        )

    async def get_snapshots(
        self,
        portfolio_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """Get historical snapshots from InfluxDB."""
        try:
            client = await self._get_client()
            query_api = client.query_api()

            from datetime import datetime, timezone

            start_str = "-30d"
            if start_time:
                start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
                start_str = start_dt.isoformat()

            stop_str = "now()"
            if end_time:
                end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
                stop_str = end_dt.isoformat()

            query = f"""
                from(bucket: "{self.config.database}")
                    |> range(start: {start_str}, stop: {stop_str})
                    |> filter(fn: (r) => r._measurement == "portfolio_snapshot")
                    |> filter(fn: (r) => r.portfolio_id == "{portfolio_id}")
                    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                    |> sort(columns: ["_time"], desc: true)
                    |> limit(n: {limit})
            """

            tables = query_api.query(query)

            results = []
            for table in tables:
                for record in tables[table]:
                    balance_summary = {}
                    try:
                        balance_summary = json.loads(
                            record.values.get("balance_summary", "{}")
                        )
                    except json.JSONDecodeError:
                        pass

                    results.append(
                        PortfolioSnapshot(
                            snapshot_id=record.values.get("snapshot_id", ""),
                            portfolio_id=portfolio_id,
                            timestamp=int(record.get_time().timestamp() * 1000),
                            total_equity=float(record.values.get("total_equity", 0)),
                            available_equity=float(
                                record.values.get("available_equity", 0)
                            ),
                            margin_used=float(record.values.get("margin_used", 0)),
                            unrealized_pnl=float(
                                record.values.get("unrealized_pnl", 0)
                            ),
                            realized_pnl=float(record.values.get("realized_pnl", 0)),
                            position_count=int(record.values.get("position_count", 0)),
                            balance_summary=balance_summary,
                        )
                    )

            return results

        except Exception as e:
            logger.error(f"Failed to fetch snapshots from InfluxDB: {e}")
            return []

    async def health_check(self) -> bool:
        """Check InfluxDB health."""
        try:
            client = await self._get_client()
            health = client.health()
            return health.status == "pass"
        except Exception as e:
            logger.warning(f"InfluxDB health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close InfluxDB connection."""
        if self._client:
            self._client.close()
            self._client = None


class PostgresPortfolioStorage(PortfolioStorageInterface):
    """PostgreSQL storage backend for portfolio state.

    Stores full portfolio state including positions and balances.
    """

    def __init__(self, config: StorageConfig):
        """Initialize PostgreSQL storage.

        Args:
            config: Storage configuration
        """
        self.config = config
        self._pool: Any | None = None

    async def _get_pool(self) -> Any:
        """Get or create database connection pool."""
        if self._pool is None:
            try:
                import asyncpg

                self._pool = await asyncpg.create_pool(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.username,
                    password=self.config.password,
                    ssl=self.config.ssl,
                    min_size=1,
                    max_size=10,
                )

                await self._create_tables()

            except ImportError:
                logger.error(
                    "asyncpg not installed, cannot use PostgresPortfolioStorage"
                )
                raise

        return self._pool

    async def _create_tables(self) -> None:
        """Create necessary tables if they don't exist."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # Portfolio states table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_states (
                    id SERIAL PRIMARY KEY,
                    portfolio_id VARCHAR(100) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    total_equity DECIMAL(24, 8) NOT NULL,
                    available_equity DECIMAL(24, 8) NOT NULL,
                    margin_used DECIMAL(24, 8) NOT NULL,
                    unrealized_pnl DECIMAL(24, 8) NOT NULL,
                    realized_pnl DECIMAL(24, 8) NOT NULL,
                    positions JSONB,
                    balances JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(portfolio_id, timestamp)
                )
            """)

            # Portfolio snapshots table (for historical trend analysis)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id SERIAL PRIMARY KEY,
                    snapshot_id VARCHAR(100) UNIQUE NOT NULL,
                    portfolio_id VARCHAR(100) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    total_equity DECIMAL(24, 8) NOT NULL,
                    available_equity DECIMAL(24, 8) NOT NULL,
                    margin_used DECIMAL(24, 8) NOT NULL,
                    unrealized_pnl DECIMAL(24, 8) NOT NULL,
                    realized_pnl DECIMAL(24, 8) NOT NULL,
                    position_count INTEGER NOT NULL,
                    balance_summary JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_portfolio_states_portfolio_id
                ON portfolio_states(portfolio_id, timestamp DESC)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_portfolio_id
                ON portfolio_snapshots(portfolio_id, timestamp DESC)
            """)

    async def store_state(self, state: PortfolioState) -> bool:
        """Store portfolio state in PostgreSQL."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO portfolio_states
                    (portfolio_id, timestamp, total_equity, available_equity,
                     margin_used, unrealized_pnl, realized_pnl, positions, balances)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (portfolio_id, timestamp)
                    DO UPDATE SET
                        total_equity = EXCLUDED.total_equity,
                        available_equity = EXCLUDED.available_equity,
                        margin_used = EXCLUDED.margin_used,
                        unrealized_pnl = EXCLUDED.unrealized_pnl,
                        realized_pnl = EXCLUDED.realized_pnl,
                        positions = EXCLUDED.positions,
                        balances = EXCLUDED.balances
                """,
                    state.portfolio_id,
                    state.last_update,
                    state.total_equity,
                    state.available_equity,
                    state.margin_used,
                    state.unrealized_pnl,
                    state.realized_pnl,
                    json.dumps({k: v.to_dict() for k, v in state.positions.items()}),
                    json.dumps({k: v.to_dict() for k, v in state.balances.items()}),
                )

            logger.debug(f"Stored state for {state.portfolio_id} in PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to store state in PostgreSQL: {e}")
            return False

    async def store_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        """Store portfolio snapshot in PostgreSQL."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO portfolio_snapshots
                    (snapshot_id, portfolio_id, timestamp, total_equity,
                     available_equity, margin_used, unrealized_pnl, realized_pnl,
                     position_count, balance_summary)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (snapshot_id)
                    DO UPDATE SET
                        total_equity = EXCLUDED.total_equity,
                        available_equity = EXCLUDED.available_equity,
                        margin_used = EXCLUDED.margin_used,
                        unrealized_pnl = EXCLUDED.unrealized_pnl,
                        realized_pnl = EXCLUDED.realized_pnl,
                        position_count = EXCLUDED.position_count,
                        balance_summary = EXCLUDED.balance_summary
                """,
                    snapshot.snapshot_id,
                    snapshot.portfolio_id,
                    snapshot.timestamp,
                    snapshot.total_equity,
                    snapshot.available_equity,
                    snapshot.margin_used,
                    snapshot.unrealized_pnl,
                    snapshot.realized_pnl,
                    snapshot.position_count,
                    json.dumps(snapshot.balance_summary),
                )

            logger.debug(f"Stored snapshot {snapshot.snapshot_id} in PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to store snapshot in PostgreSQL: {e}")
            return False

    async def get_latest_state(self, portfolio_id: str) -> PortfolioState | None:
        """Get latest portfolio state from PostgreSQL."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM portfolio_states
                    WHERE portfolio_id = $1
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    portfolio_id,
                )

                if not row:
                    return None

                # Reconstruct positions
                positions_data = (
                    json.loads(row["positions"]) if row["positions"] else {}
                )
                positions = {
                    k: Position.from_dict(v) for k, v in positions_data.items()
                }

                # Reconstruct balances
                balances_data = json.loads(row["balances"]) if row["balances"] else {}
                balances = {k: Balance.from_dict(v) for k, v in balances_data.items()}

                return PortfolioState(
                    portfolio_id=portfolio_id,
                    positions=positions,
                    balances=balances,
                    total_equity=float(row["total_equity"]),
                    available_equity=float(row["available_equity"]),
                    margin_used=float(row["margin_used"]),
                    unrealized_pnl=float(row["unrealized_pnl"]),
                    realized_pnl=float(row["realized_pnl"]),
                    timestamp=row["timestamp"],
                    last_update=row["timestamp"],
                )

        except Exception as e:
            logger.error(f"Failed to get latest state from PostgreSQL: {e}")
            return None

    async def get_snapshots(
        self,
        portfolio_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """Get historical snapshots from PostgreSQL."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                query = """
                    SELECT * FROM portfolio_snapshots
                    WHERE portfolio_id = $1
                """
                params: list[Any] = [portfolio_id]

                if start_time:
                    query += f" AND timestamp >= ${len(params) + 1}"
                    params.append(start_time)

                if end_time:
                    query += f" AND timestamp <= ${len(params) + 1}"
                    params.append(end_time)

                query += " ORDER BY timestamp DESC"

                if limit:
                    query += f" LIMIT ${len(params) + 1}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                return [
                    PortfolioSnapshot(
                        snapshot_id=row["snapshot_id"],
                        portfolio_id=row["portfolio_id"],
                        timestamp=row["timestamp"],
                        total_equity=float(row["total_equity"]),
                        available_equity=float(row["available_equity"]),
                        margin_used=float(row["margin_used"]),
                        unrealized_pnl=float(row["unrealized_pnl"]),
                        realized_pnl=float(row["realized_pnl"]),
                        position_count=row["position_count"],
                        balance_summary=(
                            json.loads(row["balance_summary"])
                            if row["balance_summary"]
                            else {}
                        ),
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Failed to fetch snapshots from PostgreSQL: {e}")
            return []

    async def health_check(self) -> bool:
        """Check PostgreSQL health."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"PostgreSQL health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close PostgreSQL connection."""
        if self._pool:
            await self._pool.close()
            self._pool = None


class FallbackPortfolioStorage(PortfolioStorageInterface):
    """Storage wrapper that falls back to PostgreSQL if InfluxDB fails."""

    def __init__(
        self,
        influx_config: StorageConfig,
        postgres_config: StorageConfig,
    ):
        """Initialize fallback storage.

        Args:
            influx_config: InfluxDB configuration
            postgres_config: PostgreSQL configuration
        """
        self.primary = InfluxDBPortfolioStorage(influx_config)
        self.fallback = PostgresPortfolioStorage(postgres_config)
        self._using_fallback = False

    async def store_state(self, state: PortfolioState) -> bool:
        """Store state, falling back to PostgreSQL if InfluxDB fails."""
        if not self._using_fallback:
            success = await self.primary.store_state(state)
            if success:
                return True
            logger.warning("Primary storage failed, switching to fallback")
            self._using_fallback = True

        return await self.fallback.store_state(state)

    async def store_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        """Store snapshot, falling back to PostgreSQL if InfluxDB fails."""
        if not self._using_fallback:
            success = await self.primary.store_snapshot(snapshot)
            if success:
                return True
            logger.warning("Primary storage failed, switching to fallback")
            self._using_fallback = True

        return await self.fallback.store_snapshot(snapshot)

    async def get_latest_state(self, portfolio_id: str) -> PortfolioState | None:
        """Get latest state from primary or fallback."""
        if not self._using_fallback:
            try:
                result = await self.primary.get_latest_state(portfolio_id)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Primary get_latest_state failed: {e}")
                self._using_fallback = True

        return await self.fallback.get_latest_state(portfolio_id)

    async def get_snapshots(
        self,
        portfolio_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """Get snapshots from primary or fallback."""
        if not self._using_fallback:
            try:
                results = await self.primary.get_snapshots(
                    portfolio_id, start_time, end_time, limit
                )
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Primary get_snapshots failed: {e}")
                self._using_fallback = True

        return await self.fallback.get_snapshots(
            portfolio_id, start_time, end_time, limit
        )

    async def health_check(self) -> bool:
        """Check health of both storage backends."""
        primary_healthy = await self.primary.health_check()
        fallback_healthy = await self.fallback.health_check()

        if not primary_healthy and not self._using_fallback:
            logger.warning("Primary storage unhealthy, will use fallback")
            self._using_fallback = True

        return primary_healthy or fallback_healthy

    async def close(self) -> None:
        """Close both storage connections."""
        await self.primary.close()
        await self.fallback.close()
