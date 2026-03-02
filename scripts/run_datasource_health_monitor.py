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

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from config.bootstrap import bootstrap
from monitoring.datasource_health import (
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

    def _to_int(value: object, default: int = 0) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    def _to_float(value: object, default: float = 0.0) -> float:
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return default

    points: list[Point] = []
    for row in metrics_rows:
        ts = _parse_timestamp(str(row["timestamp"]))
        point = (
            Point("datasource_health")
            .tag("source_type", str(row["source_type"]))
            .tag("source_name", str(row["source_name"]))
            .field("is_connected", _to_int(row["is_connected"]))
            .field("is_healthy", _to_int(row["is_healthy"]))
            .field("disconnect_count", _to_int(row["disconnect_count"]))
            .field("reconnect_attempts", _to_int(row["reconnect_attempts"]))
            .field("uptime_seconds", _to_float(row["uptime_seconds"]))
            .field("downtime_seconds", _to_float(row["downtime_seconds"]))
            .field("availability_percentage", _to_float(row["availability_percentage"]))
            .field("response_time_ms", _to_float(row["response_time_ms"]))
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
        default=os.environ.get("POSTGRES_USER"),
        help="PostgreSQL username (overrides POSTGRES_USER env var)",
    )
    parser.add_argument(
        "--postgres-password",
        type=str,
        default=os.environ.get("POSTGRES_PASSWORD"),
        help="PostgreSQL password (overrides POSTGRES_PASSWORD env var)",
    )
    parser.add_argument(
        "--postgres-host",
        type=str,
        default=os.environ.get("POSTGRES_HOST"),
        help="PostgreSQL host (overrides POSTGRES_HOST env var)",
    )
    parser.add_argument(
        "--postgres-port",
        type=int,
        default=int(os.environ.get("POSTGRES_PORT", "5434")),
        help="PostgreSQL port (overrides POSTGRES_PORT env var)",
    )
    parser.add_argument(
        "--postgres-db",
        type=str,
        default=os.environ.get("POSTGRES_DB"),
        help="PostgreSQL database name (overrides POSTGRES_DB env var)",
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="Run health check once and exit (for testing)",
    )
    args = parser.parse_args()

    # Build PostgreSQL config from environment + CLI overrides
    pg_config = {}
    if args.postgres_host:
        pg_config["host"] = args.postgres_host
    if args.postgres_port:
        pg_config["port"] = args.postgres_port
    if args.postgres_db:
        pg_config["database"] = args.postgres_db
    if args.postgres_user:
        pg_config["username"] = args.postgres_user
    if args.postgres_password:
        pg_config["password"] = args.postgres_password

    # Create monitor with default ChiseAI configuration
    monitor = create_default_monitor(
        influxdb_token=args.influxdb_token,
        postgres_username=pg_config.get("username"),
        postgres_password=pg_config.get("password"),
    )

    # Override PostgreSQL config if CLI args provided
    if pg_config:
        from monitoring.datasource_health import (
            DatasourceConfig,
            DataSourceType,
            PostgreSQLHealthChecker,
        )

        # Get current config and update with overrides
        current_cfg = monitor.datasource_configs.get(DataSourceType.POSTGRESQL)
        if current_cfg:
            new_cfg = DatasourceConfig(
                source_type=DataSourceType.POSTGRESQL,
                source_name=current_cfg.source_name,
                host=pg_config.get("host", current_cfg.host),
                port=pg_config.get("port", current_cfg.port),
                database=pg_config.get("database", current_cfg.database),
                username=pg_config.get("username", current_cfg.username),
                password=pg_config.get("password", current_cfg.password),
                check_interval_seconds=current_cfg.check_interval_seconds,
                enabled=current_cfg.enabled,
                reconnect_backoff_seconds=current_cfg.reconnect_backoff_seconds,
                max_reconnect_attempts=current_cfg.max_reconnect_attempts,
            )
            monitor.datasource_configs[DataSourceType.POSTGRESQL] = new_cfg
            monitor._checkers[DataSourceType.POSTGRESQL] = PostgreSQLHealthChecker(
                new_cfg
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
    logger.info("Monitoring InfluxDB (30s interval) and PostgreSQL (60s interval)")

    # Check-once mode for testing
    if args.check_once:
        logger.info("Running single health check (check-once mode)...")
        await monitor.check_now()

        # Print results
        metrics = monitor.get_all_metrics()
        for source_type, source_metrics in metrics["datasources"].items():
            status = "✓" if source_metrics["is_connected"] else "✗"
            logger.info(
                f"{status} {source_type}: {source_metrics['status']} "
                f"(response_time={source_metrics.get('response_time_ms', 'N/A')}ms)"
            )

        # Exit with appropriate code
        all_healthy = all(m["is_healthy"] for m in metrics["datasources"].values())
        if all_healthy:
            logger.info("All data sources are healthy!")
            return 0
        else:
            logger.error("Some data sources are unhealthy!")
            return 1

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
    with contextlib.suppress(asyncio.CancelledError):
        await shutdown_event.wait()

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
