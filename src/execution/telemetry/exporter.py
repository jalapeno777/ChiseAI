"""Execution telemetry exporter for InfluxDB.

For ST-EX-001: Export execution metrics to InfluxDB for Grafana dashboards.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import WriteApi

    from execution.telemetry.metrics import ExecutionMetrics, OrderEvent, PositionEvent

logger = logging.getLogger(__name__)


class ExecutionTelemetryExporter:
    """Exporter for execution telemetry to InfluxDB.

    Writes KPIs, order events, and position events to InfluxDB
    for real-time Grafana dashboards.

    Schema:
        execution_kpis:
            - measurement: execution_kpis
            - tags: environment, portfolio_id
            - fields: total_pnl, realized_pnl, unrealized_pnl, max_drawdown_pct,
                      win_rate, trade_count, sharpe_ratio
            - timestamp: epoch_ns

        order_events:
            - measurement: order_events
            - tags: environment, symbol, side, status
            - fields: quantity, price, order_id, filled_quantity
            - timestamp: epoch_ns

        position_events:
            - measurement: position_events
            - tags: environment, symbol, side
            - fields: entry_price, current_price, quantity, unrealized_pnl, leverage
            - timestamp: epoch_ns
    """

    FLUSH_INTERVAL = 5.0  # seconds

    def __init__(
        self,
        influxdb_client: InfluxDBClient | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
        url: str = "http://localhost:8086",
        token: str = "",  # nosec B107 - empty default for optional param
    ):
        """Initialize telemetry exporter.

        Args:
            influxdb_client: Existing InfluxDB client (optional)
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            url: InfluxDB URL (used if client not provided)
            token: InfluxDB token (used if client not provided)
        """
        self.bucket = bucket
        self.org = org
        self._client = influxdb_client
        self._url = url
        self._token = token
        self._write_api: WriteApi | None = None
        self._owned_client = influxdb_client is None

        # Batch buffer for high-frequency writes
        self._batch_buffer: list[Any] = []
        self._batch_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._running = False

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

    async def start(self) -> None:
        """Start the exporter and periodic flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("ExecutionTelemetryExporter started")

    async def stop(self) -> None:
        """Stop the exporter and flush remaining data."""
        self._running = False

        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_batch()

        # Close write API
        if self._write_api:
            self._write_api.close()
            self._write_api = None

        # Close client if we own it
        if self._owned_client and self._client:
            self._client.close()
            self._client = None

        logger.info("ExecutionTelemetryExporter stopped")

    async def _flush_loop(self) -> None:
        """Periodic flush loop for batch writes."""
        while self._running:
            try:
                await asyncio.sleep(self.FLUSH_INTERVAL)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush_batch(self) -> None:
        """Flush batched points to InfluxDB."""
        async with self._batch_lock:
            if not self._batch_buffer:
                return

            points = self._batch_buffer.copy()
            self._batch_buffer.clear()

        try:
            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=points)
            logger.debug(f"Flushed {len(points)} points to InfluxDB")
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}")
            # Re-add points to buffer for retry
            async with self._batch_lock:
                self._batch_buffer.extend(points)

    async def write_metrics(
        self,
        metrics: ExecutionMetrics,
        portfolio_id: str = "default",
    ) -> bool:
        """Write execution KPIs to InfluxDB.

        Args:
            metrics: ExecutionMetrics to write
            portfolio_id: Portfolio identifier for tagging

        Returns:
            True if successfully queued
        """
        try:
            from influxdb_client import Point

            point = (
                Point("execution_kpis")
                .tag("environment", metrics.environment)
                .tag("portfolio_id", portfolio_id)
                .field("total_pnl", metrics.total_pnl)
                .field("realized_pnl", metrics.realized_pnl)
                .field("unrealized_pnl", metrics.unrealized_pnl)
                .field("max_drawdown_pct", metrics.max_drawdown_pct)
                .field("win_rate", metrics.win_rate)
                .field("trade_count", metrics.trade_count)
                .field("win_count", metrics.win_count)
                .field("loss_count", metrics.loss_count)
                .field("sharpe_ratio", metrics.sharpe_ratio)
                .time(metrics.timestamp)
            )

            async with self._batch_lock:
                self._batch_buffer.append(point)

            logger.debug(f"Queued metrics for {metrics.environment}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue metrics: {e}")
            return False

    async def write_order_event(self, order: OrderEvent) -> bool:
        """Write order lifecycle event to InfluxDB.

        Args:
            order: OrderEvent to write

        Returns:
            True if successfully queued
        """
        try:
            from influxdb_client import Point

            point = (
                Point("order_events")
                .tag("environment", order.environment)
                .tag("symbol", order.symbol)
                .tag("side", order.side.value)
                .tag("status", order.status.value)
                .field("order_id", order.order_id)
                .field("quantity", order.quantity)
                .field("price", order.price)
                .field("filled_quantity", order.filled_quantity)
                .time(order.timestamp)
            )

            async with self._batch_lock:
                self._batch_buffer.append(point)

            logger.debug(f"Queued order event: {order.order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue order event: {e}")
            return False

    async def write_position_event(self, position: PositionEvent) -> bool:
        """Write position update event to InfluxDB.

        Args:
            position: PositionEvent to write

        Returns:
            True if successfully queued
        """
        try:
            from influxdb_client import Point

            point = (
                Point("position_events")
                .tag("environment", position.environment)
                .tag("symbol", position.symbol)
                .tag("side", position.side.value)
                .field("position_id", position.position_id)
                .field("entry_price", position.entry_price)
                .field("current_price", position.current_price)
                .field("quantity", position.quantity)
                .field("unrealized_pnl", position.unrealized_pnl)
                .field("leverage", position.leverage)
                .time(position.timestamp)
            )

            async with self._batch_lock:
                self._batch_buffer.append(point)

            logger.debug(f"Queued position event: {position.position_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue position event: {e}")
            return False

    async def write_test_point(self) -> bool:
        """Write a test point to verify connectivity.

        Returns:
            True if write successful
        """
        try:
            from influxdb_client import Point
            from datetime import UTC, datetime

            point = (
                Point("test")
                .tag("source", "execution_telemetry")
                .field("value", 1.0)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info("Test point written successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to write test point: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get exporter statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "running": self._running,
            "bucket": self.bucket,
            "org": self.org,
            "batch_size": len(self._batch_buffer),
            "flush_interval": self.FLUSH_INTERVAL,
        }
