#!/usr/bin/env python3
"""Script to run data source health monitoring.

Usage:
    python3 scripts/run_datasource_health_monitor.py [--interval SECONDS]

For ST-OPS-008: Grafana Data Source Health Monitoring
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from monitoring.datasource_health import (
    DataSourceHealthMonitor,
    DatasourceHealthAlert,
    create_default_monitor,
)
from monitoring.datasource_health_discord import create_discord_alert_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO timestamp into timezone-aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _build_metrics_points(metrics_rows: list[dict[str, object]]) -> list[Point]:
    """Convert monitor metrics into InfluxDB points."""
    points: list[Point] = []
    for row in metrics_rows:
        ts = _parse_timestamp(str(row["timestamp"]))
        point = (
            Point("datasource_health")
            .tag("source_type", str(row["source_type"]))
            .tag("source_name", str(row["source_name"]))
            .field("is_connected", int(row["is_connected"]))
            .field("is_healthy", int(row["is_healthy"]))
            .field("disconnect_count", int(row["disconnect_count"]))
            .field("reconnect_attempts", int(row["reconnect_attempts"]))
            .field("uptime_seconds", float(row["uptime_seconds"]))
            .field("downtime_seconds", float(row["downtime_seconds"]))
            .field("availability_percentage", float(row["availability_percentage"]))
            .field("response_time_ms", float(row["response_time_ms"]))
            .field("status", str(row["status"]))
            .time(ts, WritePrecision.NS)
        )
        points.append(point)
    return points


async def main():
    # Bootstrap environment first
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(description="Run data source health monitoring")
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Check interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--discord-webhook",
        type=str,
        default=os.environ.get("DISCORD_WEBHOOK_URL"),
        help="Discord webhook URL for alerts",
    )
    parser.add_argument(
        "--influxdb-token",
        type=str,
        default=os.environ.get("INFLUXDB_TOKEN"),
        help="InfluxDB token",
    )
    parser.add_argument(
        "--influxdb-url",
        type=str,
        default=os.environ.get("DQ_INFLUX_URL", "http://chiseai-influxdb:18087"),
        help="InfluxDB URL",
    )
    parser.add_argument(
        "--influxdb-org",
        type=str,
        default=os.environ.get("DQ_INFLUX_ORG", "chiseai"),
        help="InfluxDB organization",
    )
    parser.add_argument(
        "--influxdb-bucket",
        type=str,
        default=os.environ.get("DQ_INFLUX_BUCKET", "chiseai"),
        help="InfluxDB bucket",
    )
    parser.add_argument(
        "--postgres-user",
        type=str,
        default=os.environ.get("POSTGRES_USER", "chiseai"),
        help="PostgreSQL username",
    )
    parser.add_argument(
        "--postgres-password",
        type=str,
        default=os.environ.get("POSTGRES_PASSWORD"),
        help="PostgreSQL password",
    )
    args = parser.parse_args()

    # Create monitor with default ChiseAI configuration
    monitor = create_default_monitor(
        influxdb_token=args.influxdb_token,
        postgres_username=args.postgres_user,
        postgres_password=args.postgres_password,
    )

    # Configure optional Influx export for Grafana datasource health dashboards.
    influx_client = None
    write_api = None
    if args.influxdb_token:
        influx_client = InfluxDBClient(
            url=args.influxdb_url,
            token=args.influxdb_token,
            org=args.influxdb_org,
        )
        write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        logger.info(
            "Influx export enabled: url=%s org=%s bucket=%s",
            args.influxdb_url,
            args.influxdb_org,
            args.influxdb_bucket,
        )
    else:
        logger.warning(
            "Influx export disabled because no INFLUXDB_TOKEN was provided; "
            "datasource health dashboards will remain empty."
        )

    async def export_alert_handler(alert: DatasourceHealthAlert):
        """Persist alert events to Influx for datasource-health dashboard table."""
        if write_api is None:
            return
        alert_point = (
            Point("datasource_alerts")
            .tag("source_type", alert.source_type.value)
            .field("alert_type", alert.alert_type)
            .field("source_name", alert.source_name)
            .field("severity", alert.severity.value)
            .field("message", alert.message)
            .time(alert.created_at, WritePrecision.NS)
        )
        try:
            write_api.write(bucket=args.influxdb_bucket, record=[alert_point])
        except Exception:
            logger.exception("Failed to export datasource alert to InfluxDB")

    # Add Discord alert handler if webhook provided
    if args.discord_webhook:
        logger.info("Adding Discord alert handler")
        discord_handler = create_discord_alert_handler(
            webhook_url=args.discord_webhook,
            alerts_channel="alerts",
        )
        monitor.add_alert_handler(discord_handler)
    else:
        # Add console alert handler for testing
        async def console_handler(alert):
            logger.warning(f"ALERT [{alert.severity.value.upper()}]: {alert.message}")

        monitor.add_alert_handler(console_handler)

    monitor.add_alert_handler(export_alert_handler)

    # Handle shutdown gracefully
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start monitoring
    logger.info("Starting data source health monitoring...")
    logger.info(f"Monitoring InfluxDB (30s interval) and PostgreSQL (60s interval)")

    await monitor.start_monitoring()

    async def export_metrics_loop() -> None:
        if write_api is None:
            return
        while not shutdown_event.is_set():
            try:
                metrics_rows = monitor.get_metrics_for_grafana()
                points = _build_metrics_points(metrics_rows)
                if points:
                    write_api.write(bucket=args.influxdb_bucket, record=points)
            except Exception:
                logger.exception(
                    "Failed to export datasource health metrics to InfluxDB"
                )
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=max(args.interval, 5.0)
                )
            except TimeoutError:
                continue

    exporter_task = asyncio.create_task(export_metrics_loop())

    # Wait for shutdown
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    # Stop monitoring
    exporter_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await exporter_task
    logger.info("Stopping data source health monitoring...")
    await monitor.stop_monitoring()
    if influx_client is not None:
        influx_client.close()
    logger.info("Monitoring stopped")


if __name__ == "__main__":
    asyncio.run(main())
