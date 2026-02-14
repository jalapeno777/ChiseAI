"""Storage interface for OHLCV data.

Provides abstraction layer for time-series data storage with
InfluxDB as primary and PostgreSQL as fallback.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuration for storage backends.

    Attributes:
        host: Database host
        port: Database port
        database: Database name
        username: Authentication username (for InfluxDB, this is the org)
        password: Authentication password or token
        token: Explicit token (preferred for InfluxDB v2)
        ssl: Whether to use SSL connection
    """

    host: str
    port: int
    database: str
    username: str | None = None
    password: str | None = None
    token: str | None = None
    ssl: bool = False


class StorageInterface(ABC):
    """Abstract base class for OHLCV storage backends."""

    @abstractmethod
    async def store(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: list[OHLCVData],
    ) -> bool:
        """Store OHLCV data.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            data: List of OHLCV data points

        Returns:
            True if storage was successful
        """
        pass

    @abstractmethod
    async def fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data from storage.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum records to return (optional)

        Returns:
            List of OHLCVData objects
        """
        pass

    @abstractmethod
    async def get_latest_timestamp(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> datetime | None:
        """Get the timestamp of the most recent data point.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum

        Returns:
            Timestamp of most recent data, or None if no data
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if storage backend is healthy.

        Returns:
            True if storage is accessible
        """
        pass


class InfluxDBStorage(StorageInterface):
    """InfluxDB storage backend for time-series OHLCV data.

    This is the primary storage backend optimized for time-series queries.
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
                # InfluxDB v2 token should be passed directly, not as username:password
                token = (
                    self.config.password if self.config.password else self.config.token
                )
                self._client = InfluxDBClient(
                    url=url,
                    token=token,
                    org=self.config.username or "-",
                )
                self._write_api = self._client.write_api()
                self._query_api = self._client.query_api()
            except ImportError:
                logger.error(
                    "influxdb-client not installed, cannot use InfluxDBStorage"
                )
                raise

        return self._client

    async def store(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: list[OHLCVData],
    ) -> bool:
        """Store OHLCV data in InfluxDB.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            data: List of OHLCV data points

        Returns:
            True if storage was successful
        """
        if not data:
            return True

        try:
            from influxdb_client import Point
            from influxdb_client.client.write_api import SYNCHRONOUS

            client = await self._get_client()
            write_api = client.write_api(write_options=SYNCHRONOUS)

            points = []
            for candle in data:
                point = (
                    Point("ohlcv")
                    .tag("symbol", symbol)
                    .tag("timeframe", timeframe.value)
                    .field("open", candle.open_price)
                    .field("high", candle.high_price)
                    .field("low", candle.low_price)
                    .field("close", candle.close_price)
                    .field("volume", candle.volume)
                    .time(candle.datetime_utc)
                )
                points.append(point)

            write_api.write(bucket=self.config.database, record=points)
            logger.debug(f"Stored {len(points)} points for {symbol} {timeframe.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to store data in InfluxDB: {e}")
            return False

    async def fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data from InfluxDB.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum records to return

        Returns:
            List of OHLCVData objects
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            # Build Flux query
            query = f"""
                from(bucket: "{self.config.database}")
                    |> range(
                        start: {start_time.isoformat() if start_time else "-30d"},
                        stop: {end_time.isoformat() if end_time else "now()"}
                    )
                    |> filter(fn: (r) => r._measurement == "ohlcv")
                    |> filter(fn: (r) => r.symbol == "{symbol}")
                    |> filter(fn: (r) => r.timeframe == "{timeframe.value}")
                    |> pivot(
                        rowKey:["_time"],
                        columnKey: ["_field"],
                        valueColumn: "_value"
                    )
            """

            if limit:
                query += f"|> limit(n: {limit})"

            tables = query_api.query(query)

            results = []
            for table in tables:
                for record in table.records:
                    results.append(
                        OHLCVData(
                            timestamp=int(record.get_time().timestamp() * 1000),
                            open_price=float(record.values.get("open", 0)),
                            high_price=float(record.values.get("high", 0)),
                            low_price=float(record.values.get("low", 0)),
                            close_price=float(record.values.get("close", 0)),
                            volume=float(record.values.get("volume", 0)),
                        )
                    )

            return results

        except Exception as e:
            logger.error(f"Failed to fetch data from InfluxDB: {e}")
            return []

    async def get_latest_timestamp(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> datetime | None:
        """Get the timestamp of the most recent data point."""
        try:
            client = await self._get_client()
            query_api = client.query_api()

            query = f"""
                from(bucket: "{self.config.database}")
                    |> range(start: -30d)
                    |> filter(fn: (r) => r._measurement == "ohlcv")
                    |> filter(fn: (r) => r.symbol == "{symbol}")
                    |> filter(fn: (r) => r.timeframe == "{timeframe.value}")
                    |> last()
            """

            tables = query_api.query(query)

            for table in tables:
                for record in table.records:
                    result: datetime | None = record.get_time()
                    return result

            return None

        except Exception as e:
            logger.error(f"Failed to get latest timestamp: {e}")
            return None

    async def health_check(self) -> bool:
        """Check InfluxDB health."""
        try:
            client = await self._get_client()
            health = client.health()
            is_healthy: bool = health.status == "pass"
            return is_healthy
        except Exception as e:
            logger.warning(f"InfluxDB health check failed: {e}")
            return False


class PostgresStorage(StorageInterface):
    """PostgreSQL storage backend for OHLCV data.

    This is the fallback storage backend when InfluxDB is unavailable.
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

                # Ensure table exists
                await self._create_table()

            except ImportError:
                logger.error("asyncpg not installed, cannot use PostgresStorage")
                raise

        return self._pool

    async def _create_table(self) -> None:
        """Create OHLCV table if it doesn't exist."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_data (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    open_price DECIMAL(18, 8) NOT NULL,
                    high_price DECIMAL(18, 8) NOT NULL,
                    low_price DECIMAL(18, 8) NOT NULL,
                    close_price DECIMAL(18, 8) NOT NULL,
                    volume DECIMAL(24, 8) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(symbol, timeframe, timestamp)
                )
            """)

            # Create indexes for efficient queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timeframe
                ON ohlcv_data(symbol, timeframe, timestamp DESC)
            """)

    async def store(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: list[OHLCVData],
    ) -> bool:
        """Store OHLCV data in PostgreSQL."""
        if not data:
            return True

        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                # Use executemany for batch insert
                records = [
                    (
                        symbol,
                        timeframe.value,
                        candle.datetime_utc,
                        candle.open_price,
                        candle.high_price,
                        candle.low_price,
                        candle.close_price,
                        candle.volume,
                    )
                    for candle in data
                ]

                await conn.executemany(
                    """
                    INSERT INTO ohlcv_data
                    (symbol, timeframe, timestamp, open_price, high_price,
                     low_price, close_price, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol, timeframe, timestamp)
                    DO UPDATE SET
                        open_price = EXCLUDED.open_price,
                        high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price,
                        close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume
                """,
                    records,
                )

            logger.debug(
                f"Stored {len(records)} records for {symbol} "
                f"{timeframe.value} in PostgreSQL"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store data in PostgreSQL: {e}")
            return False

    async def fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch OHLCV data from PostgreSQL."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                query = """
                    SELECT timestamp, open_price, high_price, low_price,
                           close_price, volume
                    FROM ohlcv_data
                    WHERE symbol = $1 AND timeframe = $2
                """
                params: list[Any] = [symbol, timeframe.value]

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
                    OHLCVData(
                        timestamp=int(row["timestamp"].timestamp() * 1000),
                        open_price=float(row["open_price"]),
                        high_price=float(row["high_price"]),
                        low_price=float(row["low_price"]),
                        close_price=float(row["close_price"]),
                        volume=float(row["volume"]),
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Failed to fetch data from PostgreSQL: {e}")
            return []

    async def get_latest_timestamp(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> datetime | None:
        """Get the timestamp of the most recent data point."""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT MAX(timestamp) as latest
                    FROM ohlcv_data
                    WHERE symbol = $1 AND timeframe = $2
                """,
                    symbol,
                    timeframe.value,
                )

                return row["latest"] if row else None

        except Exception as e:
            logger.error(f"Failed to get latest timestamp: {e}")
            return None

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


class FallbackStorage(StorageInterface):
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
        self.primary = InfluxDBStorage(influx_config)
        self.fallback = PostgresStorage(postgres_config)
        self._using_fallback = False

    async def store(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: list[OHLCVData],
    ) -> bool:
        """Store data, falling back to PostgreSQL if InfluxDB fails."""
        # Try primary first
        if not self._using_fallback:
            success = await self.primary.store(symbol, timeframe, data)
            if success:
                return True

            logger.warning("Primary storage failed, switching to fallback")
            self._using_fallback = True

        # Use fallback
        return await self.fallback.store(symbol, timeframe, data)

    async def fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVData]:
        """Fetch data from primary or fallback."""
        if not self._using_fallback:
            try:
                results = await self.primary.fetch(
                    symbol, timeframe, start_time, end_time, limit
                )
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Primary fetch failed: {e}")
                self._using_fallback = True

        return await self.fallback.fetch(symbol, timeframe, start_time, end_time, limit)

    async def get_latest_timestamp(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> datetime | None:
        """Get latest timestamp from primary or fallback."""
        if not self._using_fallback:
            try:
                result = await self.primary.get_latest_timestamp(symbol, timeframe)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Primary timestamp fetch failed: {e}")
                self._using_fallback = True

        return await self.fallback.get_latest_timestamp(symbol, timeframe)

    async def health_check(self) -> bool:
        """Check health of both storage backends."""
        primary_healthy = await self.primary.health_check()
        fallback_healthy = await self.fallback.health_check()

        if not primary_healthy and not self._using_fallback:
            logger.warning("Primary storage unhealthy, will use fallback")
            self._using_fallback = True

        return primary_healthy or fallback_healthy
