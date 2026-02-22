"""OHLCV data loader from InfluxDB.

Provides efficient loading of OHLCV data with freshness validation
and missing data handling for feature extraction pipeline.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class OHLCVLoadResult:
    """Result of OHLCV data loading operation.

    Attributes:
        data: List of OHLCV data points
        is_fresh: Whether data meets freshness requirements
        freshness_seconds: Actual data age in seconds
        missing_count: Number of missing candles detected
        source: Data source identifier
    """

    data: list[OHLCVData]
    is_fresh: bool
    freshness_seconds: float
    missing_count: int
    source: str


class OHLCVLoader:
    """Load OHLCV data from InfluxDB with freshness validation.

    Provides efficient querying of historical OHLCV data with
    configurable freshness thresholds and gap detection.

    Attributes:
        freshness_threshold_seconds: Maximum acceptable data age
        bucket: InfluxDB bucket name
        org: InfluxDB organization
    """

    DEFAULT_FRESHNESS_SECONDS = 300  # 5 minutes
    DEFAULT_BUCKET = "chiseai"
    DEFAULT_ORG = "chiseai"

    def __init__(
        self,
        influxdb_client: Any | None = None,
        freshness_threshold_seconds: float = DEFAULT_FRESHNESS_SECONDS,
        bucket: str | None = None,
        org: str | None = None,
    ) -> None:
        """Initialize OHLCV loader.

        Args:
            influxdb_client: Optional InfluxDB client instance
            freshness_threshold_seconds: Maximum acceptable data age
            bucket: InfluxDB bucket name (defaults to env or 'chiseai')
            org: InfluxDB organization (defaults to env or 'chiseai')
        """
        self._client = influxdb_client
        self.freshness_threshold_seconds = freshness_threshold_seconds
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", self.DEFAULT_BUCKET)
        self.org = org or os.getenv("INFLUXDB_ORG", self.DEFAULT_ORG)
        self._query_api: Any | None = None

    async def load(
        self,
        symbol: str,
        timeframe: Timeframe,
        lookback_periods: int = 100,
        end_time: datetime | None = None,
    ) -> OHLCVLoadResult:
        """Load OHLCV data from InfluxDB.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe enum
            lookback_periods: Number of candles to fetch
            end_time: End timestamp (defaults to now)

        Returns:
            OHLCVLoadResult with data and metadata
        """
        try:
            client = await self._get_client()
            if client is None:
                return self._create_empty_result("no_client")

            query_api = await self._get_query_api()

            # Build time range based on lookback periods
            end = end_time or datetime.now(UTC)
            timeframe_minutes = self._timeframe_to_minutes(timeframe)
            lookback_minutes = lookback_periods * timeframe_minutes
            start = end - timedelta(minutes=lookback_minutes * 2)  # Extra buffer

            # Build Flux query
            query = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: {start.isoformat()}, stop: {end.isoformat()})
                    |> filter(fn: (r) => r._measurement == "ohlcv")
                    |> filter(fn: (r) => r.symbol == "{symbol}")
                    |> filter(fn: (r) => r.timeframe == "{timeframe.value}")
                    |> pivot(
                        rowKey:["_time"],
                        columnKey: ["_field"],
                        valueColumn: "_value"
                    )
                    |> sort(columns: ["_time"], desc: false)
                    |> limit(n: {lookback_periods})
            """

            tables = query_api.query(query, org=self.org)

            # Parse results
            data = self._parse_query_results(tables)

            if not data:
                logger.warning(f"No OHLCV data found for {symbol} {timeframe.value}")
                return self._create_empty_result("empty_query")

            # Calculate freshness
            latest_timestamp = datetime.fromtimestamp(data[-1].timestamp / 1000, tz=UTC)
            now = datetime.now(UTC)
            freshness_seconds = (now - latest_timestamp).total_seconds()
            is_fresh = freshness_seconds <= self.freshness_threshold_seconds

            # Detect missing data
            missing_count = self._detect_missing_candles(data, timeframe)

            if not is_fresh:
                logger.warning(
                    f"OHLCV data for {symbol} is stale: "
                    f"{freshness_seconds:.0f}s old (threshold: {self.freshness_threshold_seconds}s)"
                )

            if missing_count > 0:
                logger.warning(
                    f"Detected {missing_count} missing candles for {symbol} {timeframe.value}"
                )

            return OHLCVLoadResult(
                data=data,
                is_fresh=is_fresh,
                freshness_seconds=freshness_seconds,
                missing_count=missing_count,
                source="influxdb",
            )

        except Exception as e:
            logger.error(f"Failed to load OHLCV data for {symbol}: {e}")
            return self._create_empty_result("error")

    async def load_latest(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> OHLCVLoadResult:
        """Load only the most recent OHLCV candle.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum

        Returns:
            OHLCVLoadResult with single candle
        """
        result = await self.load(symbol, timeframe, lookback_periods=1)
        if result.data:
            result.data = [result.data[-1]]  # Keep only latest
        return result

    async def validate_freshness(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[bool, float]:
        """Check if data is fresh without loading full dataset.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe enum

        Returns:
            Tuple of (is_fresh, freshness_seconds)
        """
        try:
            client = await self._get_client()
            if client is None:
                return False, float("inf")

            query_api = await self._get_query_api()

            query = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: -1h)
                    |> filter(fn: (r) => r._measurement == "ohlcv")
                    |> filter(fn: (r) => r.symbol == "{symbol}")
                    |> filter(fn: (r) => r.timeframe == "{timeframe.value}")
                    |> filter(fn: (r) => r._field == "close")
                    |> last()
            """

            tables = query_api.query(query, org=self.org)

            for table in tables:
                for record in table.records:
                    latest_time = record.get_time()
                    if latest_time:
                        now = datetime.now(UTC)
                        freshness_seconds = (
                            now - latest_time.replace(tzinfo=UTC)
                        ).total_seconds()
                        is_fresh = freshness_seconds <= self.freshness_threshold_seconds
                        return is_fresh, freshness_seconds

            return False, float("inf")

        except Exception as e:
            logger.error(f"Failed to validate freshness for {symbol}: {e}")
            return False, float("inf")

    async def _get_client(self) -> Any | None:
        """Get or create InfluxDB client."""
        if self._client is not None:
            return self._client

        try:
            from influxdb_client.client.influxdb_client import InfluxDBClient

            url = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
            token = os.getenv("INFLUXDB_TOKEN", "chiseai-token")
            org = os.getenv("INFLUXDB_ORG", self.DEFAULT_ORG)

            self._client = InfluxDBClient(url=url, token=token, org=org)
            return self._client

        except ImportError:
            logger.error("influxdb-client not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to create InfluxDB client: {e}")
            return None

    async def _get_query_api(self) -> Any:
        """Get or create query API."""
        if self._query_api is None:
            client = await self._get_client()
            if client:
                self._query_api = client.query_api()
        return self._query_api

    def _parse_query_results(self, tables: Any) -> list[OHLCVData]:
        """Parse Flux query results into OHLCVData objects.

        Args:
            tables: Query result tables from InfluxDB

        Returns:
            List of OHLCVData objects
        """
        from data_ingestion.ohlcv_fetcher import OHLCVData

        results = []
        for table in tables:
            for record in table.records:
                try:
                    timestamp = int(record.get_time().timestamp() * 1000)
                    results.append(
                        OHLCVData(
                            timestamp=timestamp,
                            open_price=float(record.values.get("open", 0)),
                            high_price=float(record.values.get("high", 0)),
                            low_price=float(record.values.get("low", 0)),
                            close_price=float(record.values.get("close", 0)),
                            volume=float(record.values.get("volume", 0)),
                        )
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse OHLCV record: {e}")
                    continue

        return results

    def _detect_missing_candles(
        self,
        data: list[OHLCVData],
        timeframe: Timeframe,
    ) -> int:
        """Detect gaps in OHLCV data.

        Args:
            data: List of OHLCV data points
            timeframe: Timeframe enum

        Returns:
            Number of missing candles detected
        """
        if len(data) < 2:
            return 0

        timeframe_ms = self._timeframe_to_minutes(timeframe) * 60 * 1000
        missing_count = 0

        for i in range(1, len(data)):
            expected_ts = data[i - 1].timestamp + timeframe_ms
            actual_ts = data[i].timestamp
            gap = actual_ts - expected_ts

            if gap > timeframe_ms * 1.5:  # Allow 50% tolerance
                missing = int(gap / timeframe_ms) - 1
                missing_count += max(0, missing)

        return missing_count

    def _timeframe_to_minutes(self, timeframe: Timeframe) -> int:
        """Convert timeframe to minutes.

        Args:
            timeframe: Timeframe enum

        Returns:
            Minutes per candle
        """
        mapping = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "6h": 360,
            "8h": 480,
            "12h": 720,
            "1d": 1440,
            "3d": 4320,
            "1w": 10080,
        }
        return mapping.get(timeframe.value, 60)

    def _create_empty_result(self, source: str) -> OHLCVLoadResult:
        """Create an empty result for error cases.

        Args:
            source: Source identifier for the error

        Returns:
            Empty OHLCVLoadResult
        """
        return OHLCVLoadResult(
            data=[],
            is_fresh=False,
            freshness_seconds=float("inf"),
            missing_count=0,
            source=source,
        )

    async def close(self) -> None:
        """Close InfluxDB client connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing InfluxDB client: {e}")
            finally:
                self._client = None
                self._query_api = None
