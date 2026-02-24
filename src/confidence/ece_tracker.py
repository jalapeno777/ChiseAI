"""ECE history tracking and trending module.

Tracks historical ECE values over time for calibration monitoring
and trend analysis. Stores data in InfluxDB for efficient time-series queries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import WriteApi

from confidence.ece import ECEResult, SignalType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ECEHistoryPoint:
    """Single ECE measurement at a point in time.

    Attributes:
        timestamp: When the ECE was calculated
        ece: ECE value
        n_bins: Number of bins used
        total_samples: Total samples in calculation
        signal_type: Signal type (if per-type calculation)
        strategy_id: Strategy identifier
    """

    timestamp: datetime
    ece: float
    n_bins: int
    total_samples: int
    signal_type: SignalType | None = None
    strategy_id: str | None = None


@dataclass(frozen=True)
class ECETrend:
    """Trend analysis for ECE over time.

    Attributes:
        strategy_id: Strategy identifier
        signal_type: Signal type (if applicable)
        points: List of historical ECE points
        trend_direction: "improving", "degrading", or "stable"
        trend_slope: Slope of linear trend (ECE change per day)
        current_ece: Most recent ECE value
        avg_ece: Average ECE over the period
        min_ece: Minimum ECE in the period
        max_ece: Maximum ECE in the period
    """

    strategy_id: str | None
    signal_type: SignalType | None
    points: list[ECEHistoryPoint]
    trend_direction: str
    trend_slope: float
    current_ece: float
    avg_ece: float
    min_ece: float
    max_ece: float


class ECEHistoryTracker:
    """Tracks historical ECE values and analyzes trends.

    Stores ECE measurements in InfluxDB for persistent time-series storage
    and efficient querying. Supports per-strategy and per-signal-type tracking.

    Schema (InfluxDB):
        measurement: ece_history
        tags: strategy_id, signal_type
        fields: ece, n_bins, total_samples
        timestamp: calculation time

    Example:
        >>> tracker = ECEHistoryTracker()
        >>> await tracker.record_ece(result, strategy_id="grid_btc_1h")
        >>> trend = await tracker.get_trend(
        ...     strategy_id="grid_btc_1h",
        ...     days=7
        ... )
        >>> print(f"Trend: {trend.trend_direction}, slope: {trend.trend_slope:.4f}")
    """

    def __init__(
        self,
        client: InfluxDBClient | None = None,
        url: str = "http://localhost:8086",
        token: str = "",  # nosec B107 - empty default for optional param
        org: str = "chiseai",
        bucket: str = "signals",
    ):
        """Initialize ECE history tracker.

        Args:
            client: Existing InfluxDB client (optional)
            url: InfluxDB URL (used if client not provided)
            token: InfluxDB token (used if client not provided)
            org: InfluxDB organization
            bucket: Bucket name for ECE data
        """
        self.org = org
        self.bucket = bucket
        self._client = client
        self._url = url
        self._token = token
        self._write_api: WriteApi | None = None
        self._owned_client = client is None

    async def _get_client(self) -> InfluxDBClient:
        """Get or create InfluxDB client."""
        if self._client is None:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(
                url=self._url,
                token=self._token,
                org=self.org,
            )
        return self._client

    async def _get_write_api(self) -> WriteApi:
        """Get or create write API."""
        if self._write_api is None:
            client = await self._get_client()
            self._write_api = client.write_api()
        return self._write_api

    async def record_ece(
        self,
        result: ECEResult,
        timestamp: datetime | None = None,
    ) -> bool:
        """Record an ECE calculation to history.

        Args:
            result: ECEResult to record
            timestamp: Optional timestamp (defaults to now)

        Returns:
            True if successfully recorded
        """
        try:
            from influxdb_client.client.write.point import Point

            write_api = await self._get_write_api()

            ts = timestamp or datetime.now(UTC)

            point = (
                Point("ece_history")
                .tag("strategy_id", result.strategy_id or "unknown")
                .tag(
                    "signal_type",
                    result.signal_type.value if result.signal_type else "all",
                )
                .field("ece", result.ece)
                .field("n_bins", result.n_bins)
                .field("total_samples", result.total_samples)
                .time(ts)
            )

            write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(
                f"Recorded ECE {result.ece:.4f} for strategy={result.strategy_id}, "
                f"signal_type={result.signal_type}"
            )
            return True

        except Exception:
            logger.exception("Failed to record ECE to InfluxDB")
            return False

    async def record_ece_batch(
        self,
        results: Sequence[ECEResult],
        timestamp: datetime | None = None,
    ) -> int:
        """Record multiple ECE calculations in batch.

        Args:
            results: List of ECEResults to record
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Number of successfully recorded results
        """
        from influxdb_client.client.write.point import Point

        try:
            write_api = await self._get_write_api()
            ts = timestamp or datetime.now(UTC)

            points: list[Point] = []
            for result in results:
                point = (
                    Point("ece_history")
                    .tag("strategy_id", result.strategy_id or "unknown")
                    .tag(
                        "signal_type",
                        result.signal_type.value if result.signal_type else "all",
                    )
                    .field("ece", result.ece)
                    .field("n_bins", result.n_bins)
                    .field("total_samples", result.total_samples)
                    .time(ts)
                )
                points.append(point)

            write_api.write(bucket=self.bucket, org=self.org, record=points)
            logger.debug(f"Recorded batch of {len(points)} ECE points")
            return len(points)

        except Exception:
            logger.exception("Failed to record ECE batch to InfluxDB")
            return 0

    async def get_history(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        days: int = 30,
    ) -> list[ECEHistoryPoint]:
        """Get ECE history for a strategy and/or signal type.

        Args:
            strategy_id: Optional strategy filter
            signal_type: Optional signal type filter
            days: Number of days to look back

        Returns:
            List of ECE history points
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            start_time = datetime.now(UTC) - timedelta(days=days)

            # Build query
            filters = []
            if strategy_id:
                filters.append(f'r.strategy_id == "{strategy_id}"')
            if signal_type:
                filters.append(f'r.signal_type == "{signal_type.value}"')

            filter_str = " and ".join(filters) if filters else "true"

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()})
                |> filter(fn: (r) => r._measurement == "ece_history")
                |> filter(fn: (r) => {filter_str})
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"], desc: false)
            """

            tables = query_api.query(query, org=self.org)

            points: list[ECEHistoryPoint] = []
            for table in tables:
                for record in table.records:
                    st_value = record.values.get("signal_type")
                    st = (
                        SignalType(st_value) if st_value and st_value != "all" else None
                    )

                    point = ECEHistoryPoint(
                        timestamp=record.get_time(),
                        ece=float(record.values.get("ece", 0)),
                        n_bins=int(record.values.get("n_bins", 10)),
                        total_samples=int(record.values.get("total_samples", 0)),
                        signal_type=st,
                        strategy_id=record.values.get("strategy_id"),
                    )
                    points.append(point)

            return points

        except Exception:
            logger.exception("Failed to query ECE history from InfluxDB")
            return []

    async def get_trend(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        days: int = 30,
    ) -> ECETrend | None:
        """Analyze ECE trend over time.

        Args:
            strategy_id: Optional strategy filter
            signal_type: Optional signal type filter
            days: Number of days to analyze

        Returns:
            ECETrend analysis or None if no data
        """
        points = await self.get_history(strategy_id, signal_type, days)

        if len(points) < 2:
            logger.warning(
                f"Insufficient data for trend analysis (need 2+ points, got {len(points)})"
            )
            return None

        # Calculate statistics
        ece_values = [p.ece for p in points]
        current_ece = ece_values[-1]
        avg_ece = sum(ece_values) / len(ece_values)
        min_ece = min(ece_values)
        max_ece = max(ece_values)

        # Simple linear trend (slope)
        # Use day index as x, ECE as y
        n = len(points)
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = avg_ece

        numerator = sum(
            (x - x_mean) * (y - y_mean)
            for x, y in zip(x_vals, ece_values, strict=False)
        )
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        slope = numerator / denominator if denominator != 0 else 0.0

        # Determine trend direction
        if slope < -0.001:
            trend_direction = "improving"
        elif slope > 0.001:
            trend_direction = "degrading"
        else:
            trend_direction = "stable"

        return ECETrend(
            strategy_id=strategy_id,
            signal_type=signal_type,
            points=points,
            trend_direction=trend_direction,
            trend_slope=slope,
            current_ece=current_ece,
            avg_ece=avg_ece,
            min_ece=min_ece,
            max_ece=max_ece,
        )

    async def get_latest_ece(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
    ) -> ECEHistoryPoint | None:
        """Get the most recent ECE value.

        Args:
            strategy_id: Optional strategy filter
            signal_type: Optional signal type filter

        Returns:
            Most recent ECE point or None
        """
        points = await self.get_history(strategy_id, signal_type, days=365)
        return points[-1] if points else None

    async def get_all_strategies(self) -> list[str]:
        """Get list of all strategy IDs with ECE history.

        Returns:
            List of strategy IDs
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "ece_history")
                |> keep(columns: ["strategy_id"])
                |> distinct(column: "strategy_id")
            """

            tables = query_api.query(query, org=self.org)

            strategies: set[str] = set()
            for table in tables:
                for record in table.records:
                    if record.values.get("strategy_id"):
                        strategies.add(record.values["strategy_id"])

            return sorted(strategies)

        except Exception:
            logger.exception("Failed to query strategies from InfluxDB")
            return []

    async def close(self) -> None:
        """Close InfluxDB connections."""
        if self._write_api:
            self._write_api.close()
            self._write_api = None

        if self._client:
            if self._owned_client:
                self._client.close()
            self._client = None
