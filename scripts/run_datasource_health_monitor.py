#!/usr/bin/env python3
"""Script to run data source health monitoring.

Usage:
    python3 scripts/run_datasource_health_monitor.py [--interval SECONDS]

For ST-OPS-008: Grafana Data Source Health Monitoring
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from monitoring.datasource_health import (
    DataSourceHealthMonitor,
    create_default_monitor,
)
from monitoring.datasource_health_discord import create_discord_alert_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
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

    # Wait for shutdown
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    # Stop monitoring
    logger.info("Stopping data source health monitoring...")
    await monitor.stop_monitoring()
    logger.info("Monitoring stopped")


if __name__ == "__main__":
    asyncio.run(main())
