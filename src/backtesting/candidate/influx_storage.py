"""InfluxDB storage for candidate backtest results.

Persists backtest results with full metrics to time-series database
for Grafana visualization and historical analysis.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi

from backtesting.candidate.models import CandidateResult, CandidateStatus


class CandidateResultStorage:
    """Storage for candidate backtest results in InfluxDB.

    Persists backtest metrics and ranking scores to InfluxDB for
    time-series analysis and Grafana dashboard integration.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        org: str | None = None,
        bucket: str | None = None,
    ) -> None:
        """Initialize InfluxDB storage.

        Args:
            url: InfluxDB URL (default: from env INFLUXDB_URL)
            token: InfluxDB token (default: from env INFLUXDB_TOKEN)
            org: InfluxDB organization (default: from env INFLUXDB_ORG)
            bucket: InfluxDB bucket (default: from env INFLUXDB_BUCKET)
        """
        self.url: str = url or os.getenv("INFLUXDB_URL") or "http://host.docker.internal:18087"
        self.token: str = token or os.getenv("INFLUXDB_TOKEN") or "chiseai-token"
        self.org: str = org or os.getenv("INFLUXDB_ORG") or "chiseai"
        self.bucket: str = bucket or os.getenv("INFLUXDB_BUCKET") or "chiseai"

        self._client: InfluxDBClient | None = None
        self._write_api: WriteApi | None = None

    def _get_client(self) -> InfluxDBClient:
        """Get or create InfluxDB client."""
        if self._client is None:
            token = self.token
            org = self.org
            self._client = InfluxDBClient(
                url=self.url,
                token=token,
                org=org,
            )
        return self._client

    def _get_write_api(self) -> WriteApi:
        """Get or create write API."""
        if self._write_api is None:
            self._write_api = self._get_client().write_api(write_options=SYNCHRONOUS)
        return self._write_api

    def store_result(self, result: CandidateResult) -> bool:
        """Store a candidate result in InfluxDB.

        Args:
            result: Candidate result to store

        Returns:
            True if stored successfully
        """
        try:
            points = self._result_to_points(result)
            self._get_write_api().write(bucket=self.bucket, record=points)
            return True
        except Exception as e:
            print(f"Failed to store result: {e}")
            return False

    def store_results(self, results: list[CandidateResult]) -> int:
        """Store multiple candidate results.

        Args:
            results: List of candidate results

        Returns:
            Number of results stored successfully
        """
        stored = 0
        for result in results:
            if self.store_result(result):
                stored += 1
        return stored

    def _result_to_points(self, result: CandidateResult) -> list[Point]:
        """Convert candidate result to InfluxDB points.

        Args:
            result: Candidate result

        Returns:
            List of InfluxDB points
        """
        points = []
        timestamp = result.completed_at or result.created_at

        # Main metrics point
        metrics_point = (
            Point("candidate_backtest")
            .time(timestamp)
            .tag("candidate_id", result.candidate_id)
            .tag("strategy_id", result.strategy_id)
            .tag("version", result.version)
            .tag("status", result.status.value)
            .field("sharpe_ratio", result.metrics.sharpe_ratio)
            .field("max_drawdown_pct", result.metrics.max_drawdown_pct)
            .field("win_rate_pct", result.metrics.win_rate_pct)
            .field("profit_factor", result.metrics.profit_factor)
            .field("total_return_pct", result.metrics.total_return_pct)
            .field("volatility_pct", result.metrics.volatility_pct)
            .field("calmar_ratio", result.metrics.calmar_ratio)
            .field("sortino_ratio", result.metrics.sortino_ratio)
            .field("trade_count", result.metrics.trade_count)
            .field("composite_score", result.composite_score)
            .field("rank_position", result.rank_position)
        )
        points.append(metrics_point)

        # Individual ranking scores
        for score in result.ranking_scores:
            score_point = (
                Point("candidate_ranking_score")
                .time(timestamp)
                .tag("candidate_id", result.candidate_id)
                .tag("criteria", score.criteria.value)
                .field("raw_value", score.raw_value)
                .field("normalized_score", score.normalized_score)
                .field("weight", score.weight)
                .field("weighted_score", score.weighted_score)
            )
            points.append(score_point)

        # Window information
        window_point = (
            Point("candidate_window")
            .time(timestamp)
            .tag("candidate_id", result.candidate_id)
            .field("train_start", result.window.train_start.isoformat())
            .field("train_end", result.window.train_end.isoformat())
            .field("test_start", result.window.test_start.isoformat())
            .field("test_end", result.window.test_end.isoformat())
        )
        points.append(window_point)

        return points

    def query_results(
        self,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        status: CandidateStatus | None = None,
    ) -> list[dict[str, Any]]:
        """Query stored results from InfluxDB.

        Args:
            strategy_id: Filter by strategy ID
            start: Start time
            end: End time
            status: Filter by status

        Returns:
            List of result dictionaries
        """
        query_api = self._get_client().query_api()

        # Build query
        filters = ['_measurement == "candidate_backtest"']
        if strategy_id:
            filters.append(f'strategy_id == "{strategy_id}"')
        if status:
            filters.append(f'status == "{status.value}"')

        time_filter = ""
        if start:
            time_filter += f" and _time >= '{start.isoformat()}'"
        if end:
            time_filter += f" and _time <= '{end.isoformat()}'"

        filter_clause = " and ".join(filters)

        query = f"""
        from(bucket: "{self.bucket}")
            |> range(start: -30d{time_filter})
            |> filter(fn: (r) => {filter_clause})
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
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

    def get_latest_results(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get most recent results.

        Args:
            limit: Maximum number of results

        Returns:
            List of recent result dictionaries
        """
        query_api = self._get_client().query_api()

        query = f"""
        from(bucket: "{self.bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r._measurement == "candidate_backtest")
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
