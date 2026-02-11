"""Grafana integration for data quality monitoring.

Provides InfluxDB storage for freshness metrics and gap history,
enabling Grafana dashboards to visualize data quality.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from monitoring.data_quality import (
        DataSource,
        FreshnessMetrics,
        GapAlert,
    )

logger = logging.getLogger(__name__)


class GrafanaMetricsExporter:
    """Export data quality metrics for Grafana visualization.

    Stores metrics in InfluxDB for Grafana querying and dashboards.
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        influx_url: str = "http://localhost:8086",
        influx_token: str = "",
        influx_org: str = "chiseai",
        influx_bucket: str = "data_quality",
    ):
        """Initialize Grafana metrics exporter.

        Args:
            influx_client: Existing InfluxDB client
            influx_url: InfluxDB URL
            influx_token: InfluxDB token
            influx_org: InfluxDB organization
            influx_bucket: Bucket for data quality metrics
        """
        self.influx_client = influx_client
        self.influx_url = influx_url
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket

        self._write_api: Any | None = None
        self._owned_client = influx_client is None

    async def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if self.influx_client is None:
            try:
                from influxdb_client import InfluxDBClient

                self.influx_client = InfluxDBClient(
                    url=self.influx_url,
                    token=self.influx_token,
                    org=self.influx_org,
                )
            except ImportError:
                logger.error("influxdb-client not installed")
                raise

        return self.influx_client

    async def _get_write_api(self) -> Any:
        """Get or create write API."""
        if self._write_api is None:
            client = await self._get_client()
            self._write_api = client.write_api()
        return self._write_api

    async def export_freshness_metric(self, metrics: FreshnessMetrics) -> bool:
        """Export freshness metric to InfluxDB.

        Args:
            metrics: Freshness metrics to export

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            point = (
                Point("data_freshness")
                .tag("source", metrics.source.value)
                .tag("symbol", metrics.symbol)
                .tag("timeframe", metrics.timeframe)
                .field("data_age_seconds", metrics.data_age_seconds or -1)
                .field("threshold_seconds", metrics.threshold_seconds)
                .field("is_fresh", 1 if metrics.is_fresh else 0)
                .field("is_stale", 1 if metrics.is_stale else 0)
                .field(
                    "staleness_seconds",
                    metrics.staleness_seconds if metrics.staleness_seconds else 0,
                )
                .time(metrics.checked_at)
            )

            write_api = await self._get_write_api()
            write_api.write(
                bucket=self.influx_bucket,
                org=self.influx_org,
                record=point,
            )

            logger.debug(
                f"Exported freshness metric: {metrics.source.value}/{metrics.symbol}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export freshness metric: {e}")
            return False

    async def export_gap_alert(self, gap: GapAlert) -> bool:
        """Export gap alert to InfluxDB.

        Args:
            gap: Gap alert to export

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            point = (
                Point("data_gaps")
                .tag("source", gap.source.value)
                .tag("symbol", gap.symbol)
                .tag("timeframe", gap.timeframe)
                .tag("severity", gap.severity.value)
                .field("duration_seconds", gap.duration_seconds)
                .field("expected_candles", gap.expected_candles)
                .field("gap_start", gap.gap_start)
                .field("gap_end", gap.gap_end)
                .time(gap.detected_at)
            )

            write_api = await self._get_write_api()
            write_api.write(
                bucket=self.influx_bucket,
                org=self.influx_org,
                record=point,
            )

            logger.debug(f"Exported gap alert: {gap.source.value}/{gap.symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to export gap alert: {e}")
            return False

    async def export_batch(
        self,
        freshness_metrics: list[FreshnessMetrics] | None = None,
        gap_alerts: list[GapAlert] | None = None,
    ) -> dict[str, int]:
        """Export a batch of metrics.

        Args:
            freshness_metrics: List of freshness metrics
            gap_alerts: List of gap alerts

        Returns:
            Dictionary with export counts
        """
        results = {"freshness": 0, "gaps": 0, "errors": 0}

        if freshness_metrics:
            for metrics in freshness_metrics:
                if await self.export_freshness_metric(metrics):
                    results["freshness"] += 1
                else:
                    results["errors"] += 1

        if gap_alerts:
            for gap in gap_alerts:
                if await self.export_gap_alert(gap):
                    results["gaps"] += 1
                else:
                    results["errors"] += 1

        return results

    async def query_freshness_trends(
        self,
        source: DataSource | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Query freshness trends for Grafana panels.

        Args:
            source: Filter by source
            symbol: Filter by symbol
            timeframe: Filter by timeframe
            hours: Lookback period in hours

        Returns:
            List of trend data points
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            # Build Flux query
            flux = f'''
                from(bucket: "{self.influx_bucket}")
                    |> range(start: -{hours}h)
                    |> filter(fn: (r) => r._measurement == "data_freshness")
            '''

            if source:
                flux += f'    |> filter(fn: (r) => r.source == "{source.value}")\n'
            if symbol:
                flux += f'    |> filter(fn: (r) => r.symbol == "{symbol}")\n'
            if timeframe:
                flux += f'    |> filter(fn: (r) => r.timeframe == "{timeframe}")\n'

            flux += """
                |> pivot(
                    rowKey:["_time"],
                    columnKey: ["_field"],
                    valueColumn: "_value"
                )
            """

            tables = query_api.query(flux, org=self.influx_org)

            results = []
            for table in tables:
                for record in table.records:
                    results.append(
                        {
                            "timestamp": record.get_time().isoformat(),
                            "source": record.values.get("source"),
                            "symbol": record.values.get("symbol"),
                            "timeframe": record.values.get("timeframe"),
                            "data_age_seconds": record.values.get("data_age_seconds"),
                            "is_fresh": record.values.get("is_fresh"),
                            "is_stale": record.values.get("is_stale"),
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"Failed to query freshness trends: {e}")
            return []

    async def query_gap_history(
        self,
        source: DataSource | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Query gap history for Grafana panels.

        Args:
            source: Filter by source
            hours: Lookback period in hours

        Returns:
            List of gap data points
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            flux = f'''
                from(bucket: "{self.influx_bucket}")
                    |> range(start: -{hours}h)
                    |> filter(fn: (r) => r._measurement == "data_gaps")
            '''

            if source:
                flux += f'    |> filter(fn: (r) => r.source == "{source.value}")\n'

            flux += """
                |> pivot(
                    rowKey:["_time"],
                    columnKey: ["_field"],
                    valueColumn: "_value"
                )
            """

            tables = query_api.query(flux, org=self.influx_org)

            results = []
            for table in tables:
                for record in table.records:
                    results.append(
                        {
                            "timestamp": record.get_time().isoformat(),
                            "source": record.values.get("source"),
                            "symbol": record.values.get("symbol"),
                            "timeframe": record.values.get("timeframe"),
                            "severity": record.values.get("severity"),
                            "duration_seconds": record.values.get("duration_seconds"),
                            "expected_candles": record.values.get("expected_candles"),
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"Failed to query gap history: {e}")
            return []

    async def get_last_update_per_source(
        self,
    ) -> dict[DataSource, dict[str, Any]]:
        """Get last update timestamp per data source.

        Returns:
            Dictionary mapping source to last update info
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            flux = f'''
                from(bucket: "{self.influx_bucket}")
                    |> range(start: -7d)
                    |> filter(fn: (r) => r._measurement == "data_freshness")
                    |> filter(fn: (r) => r._field == "data_age_seconds")
                    |> last()
            '''

            tables = query_api.query(flux, org=self.influx_org)

            results = {}
            for table in tables:
                for record in table.records:
                    source_val = record.values.get("source")
                    if source_val:
                        from monitoring.data_quality import DataSource

                        try:
                            source = DataSource(source_val)
                            results[source] = {
                                "timestamp": record.get_time().isoformat(),
                                "symbol": record.values.get("symbol"),
                                "timeframe": record.values.get("timeframe"),
                                "data_age_seconds": record.values.get("_value"),
                            }
                        except ValueError:
                            continue

            return results

        except Exception as e:
            logger.error(f"Failed to get last update per source: {e}")
            return {}

    async def close(self) -> None:
        """Close the exporter connection."""
        if self._write_api:
            self._write_api.close()
            self._write_api = None
        if self._owned_client and self.influx_client:
            self.influx_client.close()
            self.influx_client = None


class GrafanaDashboardConfig:
    """Configuration for Grafana dashboard panels.

    Provides Flux queries and panel configurations for common
    data quality visualizations.
    """

    @staticmethod
    def get_freshness_panel_query(
        bucket: str = "data_quality",
        source: str | None = None,
    ) -> str:
        """Get Flux query for freshness panel.

        Args:
            bucket: InfluxDB bucket name
            source: Optional source filter

        Returns:
            Flux query string
        """
        query = f'''
from(bucket: "{bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "data_age_seconds")
'''
        if source:
            query += f'  |> filter(fn: (r) => r.source == "{source}")\n'

        query += """
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> yield(name: "mean")
"""
        return query

    @staticmethod
    def get_freshness_status_query(bucket: str = "data_quality") -> str:
        """Get Flux query for freshness status (fresh/stale counts).

        Args:
            bucket: InfluxDB bucket name

        Returns:
            Flux query string
        """
        return f'''
from(bucket: "{bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "is_stale")
  |> last()
  |> group(columns: ["source"])
  |> sum()
'''

    @staticmethod
    def get_gap_count_query(
        bucket: str = "data_quality",
        hours: int = 24,
    ) -> str:
        """Get Flux query for gap count.

        Args:
            bucket: InfluxDB bucket name
            hours: Lookback period

        Returns:
            Flux query string
        """
        return f'''
from(bucket: "{bucket}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "data_gaps")
  |> filter(fn: (r) => r._field == "expected_candles")
  |> count()
  |> group(columns: ["source", "symbol"])
'''

    @staticmethod
    def get_last_update_query(bucket: str = "data_quality") -> str:
        """Get Flux query for last update timestamp per source.

        Args:
            bucket: InfluxDB bucket name

        Returns:
            Flux query string
        """
        return f'''
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "data_age_seconds")
  |> last()
'''

    @classmethod
    def get_dashboard_json_template(cls) -> dict[str, Any]:
        """Get a template for Grafana dashboard JSON.

        Returns:
            Dashboard template dictionary
        """
        return {
            "dashboard": {
                "title": "Data Quality Monitoring",
                "tags": ["data-quality", "monitoring"],
                "timezone": "utc",
                "schemaVersion": 36,
                "refresh": "30s",
                "panels": [
                    {
                        "id": 1,
                        "title": "Data Freshness by Source",
                        "type": "timeseries",
                        "targets": [
                            {
                                "query": cls.get_freshness_panel_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    },
                    {
                        "id": 2,
                        "title": "Stale Data Sources",
                        "type": "stat",
                        "targets": [
                            {
                                "query": cls.get_freshness_status_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                    },
                    {
                        "id": 3,
                        "title": "Data Gaps (24h)",
                        "type": "table",
                        "targets": [
                            {
                                "query": cls.get_gap_count_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
                    },
                    {
                        "id": 4,
                        "title": "Last Update per Source",
                        "type": "table",
                        "targets": [
                            {
                                "query": cls.get_last_update_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
                    },
                ],
            },
            "overwrite": False,
        }
