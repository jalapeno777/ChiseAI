"""Backtest KPI Writer for InfluxDB.

This module provides a dedicated writer for backtest KPIs to InfluxDB,
ensuring schema compatibility with Grafana dashboards.

The schema matches what the backtest-kpis.json dashboard expects:
- Measurement: backtest_kpis
- Fields: sharpe_ratio, max_drawdown, win_rate, trade_count, total_pnl, timestamp
- Tags: strategy_id, symbol, timeframe
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi


@dataclass
class BacktestKPIs:
    """Key performance indicators for a backtest.

    Attributes:
        strategy_id: Identifier for the strategy
        timestamp: When the backtest completed
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown: Maximum peak-to-trough decline (as decimal, e.g., 0.15 for 15%)
        win_rate: Percentage of winning trades (as decimal, e.g., 0.55 for 55%)
        trade_count: Total number of trades
        total_pnl: Total profit/loss amount
        symbol: Trading pair symbol (e.g., BTCUSDT)
        timeframe: Candle timeframe (e.g., 1h, 4h, 1d)
    """

    strategy_id: str
    timestamp: datetime
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0  # Decimal format (0.15 = 15%)
    win_rate: float = 0.0  # Decimal format (0.55 = 55%)
    trade_count: int = 0
    total_pnl: float = 0.0
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"


class BacktestKPIWriter:
    """Writer for backtest KPIs to InfluxDB.

    Persists backtest KPIs to InfluxDB with a schema that matches
    the Grafana backtest-kpis dashboard expectations.

    Usage:
        writer = BacktestKPIWriter()
        kpis = BacktestKPIs(
            strategy_id="grid_btc_usdt",
            timestamp=datetime.now(timezone.utc),
            sharpe_ratio=1.5,
            max_drawdown=0.15,
            win_rate=0.55,
            trade_count=100,
            total_pnl=500.0,
            symbol="BTCUSDT",
            timeframe="1h"
        )
        writer.write_kpis(kpis)
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        org: str | None = None,
        bucket: str | None = None,
    ) -> None:
        """Initialize InfluxDB KPI writer.

        Args:
            url: InfluxDB URL (default: from env INFLUXDB_URL)
            token: InfluxDB token (default: from env INFLUXDB_TOKEN)
            org: InfluxDB organization (default: from env INFLUXDB_ORG)
            bucket: InfluxDB bucket (default: from env INFLUXDB_BUCKET)
        """
        self.url: str = (
            url or os.getenv("INFLUXDB_URL") or "http://host.docker.internal:18087"
        )
        self.token: str = token or os.getenv("INFLUXDB_TOKEN") or "chiseai-token"
        self.org: str = org or os.getenv("INFLUXDB_ORG") or "chiseai"
        self.bucket: str = bucket or os.getenv("INFLUXDB_BUCKET") or "chiseai"

        self._client: InfluxDBClient | None = None
        self._write_api: WriteApi | None = None

    def _get_client(self) -> InfluxDBClient:
        """Get or create InfluxDB client."""
        if self._client is None:
            self._client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
            )
        return self._client

    def _get_write_api(self) -> WriteApi:
        """Get or create write API."""
        if self._write_api is None:
            self._write_api = self._get_client().write_api(write_options=SYNCHRONOUS)
        return self._write_api

    def write_kpis(
        self,
        kpis: BacktestKPIs,
    ) -> bool:
        """Write KPIs to InfluxDB.

        Args:
            kpis: Backtest KPIs to write

        Returns:
            True if written successfully
        """
        try:
            point = self._kpis_to_point(kpis)
            self._get_write_api().write(bucket=self.bucket, record=point)
            return True
        except Exception as e:
            print(f"Failed to write KPIs: {e}")
            return False

    def write_kpis_from_dict(
        self,
        strategy_id: str,
        kpis: dict[str, Any],
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        timestamp: datetime | None = None,
    ) -> bool:
        """Write KPIs from a dictionary.

        Args:
            strategy_id: Strategy identifier
            kpis: Dictionary with KPI values
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            timestamp: Optional timestamp (defaults to now)

        Returns:
            True if written successfully
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Handle both pct and decimal formats
        max_drawdown = kpis.get("max_drawdown", 0.0)
        if max_drawdown > 1.0:
            max_drawdown = max_drawdown / 100.0  # Convert from pct to decimal

        win_rate = kpis.get("win_rate", 0.0)
        if win_rate > 1.0:
            win_rate = win_rate / 100.0  # Convert from pct to decimal

        backtest_kpis = BacktestKPIs(
            strategy_id=strategy_id,
            timestamp=timestamp,
            sharpe_ratio=kpis.get("sharpe_ratio", 0.0),
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            trade_count=kpis.get("trade_count", 0),
            total_pnl=kpis.get("total_pnl", 0.0),
            symbol=symbol,
            timeframe=timeframe,
        )

        return self.write_kpis(backtest_kpis)

    def _kpis_to_point(self, kpis: BacktestKPIs) -> Point:
        """Convert KPIs to InfluxDB Point.

        Args:
            kpis: Backtest KPIs

        Returns:
            InfluxDB Point
        """
        return cast(
            Point,
            Point("backtest_kpis")
            .time(kpis.timestamp)
            .tag("strategy_id", kpis.strategy_id)
            .tag("symbol", kpis.symbol)
            .tag("timeframe", kpis.timeframe)
            .field("sharpe_ratio", float(kpis.sharpe_ratio))
            .field("max_drawdown", float(kpis.max_drawdown))
            .field("win_rate", float(kpis.win_rate))
            .field("trade_count", int(kpis.trade_count))
            .field("total_pnl", float(kpis.total_pnl))
            .field("timestamp", kpis.timestamp.isoformat()),
        )

    def query_kpis(
        self,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query KPIs from InfluxDB.

        Args:
            strategy_id: Filter by strategy ID
            start: Start time
            end: End time
            limit: Maximum number of results

        Returns:
            List of KPI dictionaries
        """
        query_api = self._get_client().query_api()

        # Build query
        time_range = "start: -7d"
        if start:
            time_range = f"start: {start.isoformat()}"
        if end:
            time_range += f", stop: {end.isoformat()}"

        filter_clause = 'r._measurement == "backtest_kpis"'
        if strategy_id:
            filter_clause += f' and r.strategy_id == "{strategy_id}"'

        query = f"""
        from(bucket: "{self.bucket}")
            |> range({time_range})
            |> filter(fn: (r) => {filter_clause})
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit})
        """

        try:
            tables = query_api.query(query)
            results = []
            for table in tables:
                for record in table.records:
                    results.append(dict(record.values))
            return results
        except Exception as e:
            print(f"Query failed: {e}")
            return []

    def close(self) -> None:
        """Close InfluxDB client connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None

    def health_check(self) -> bool:
        """Check if InfluxDB connection is healthy.

        Returns:
            True if connection is healthy
        """
        try:
            client = self._get_client()
            health = cast(dict[str, str], client.health())
            return cast(bool, health.status == "pass")
        except Exception as e:
            print(f"Health check failed: {e}")
            return False
