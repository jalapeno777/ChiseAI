#!/usr/bin/env python3
"""
Start Metrics Exporters for Governance Features.

This script initializes and starts all governance metrics exporters,
registering them with the metrics registry.

Story: ST-GOV-004

Usage:
    python scripts/governance/start_metrics_exporters.py [--interval SECONDS]
"""

import argparse
import logging
import os
import signal
import sys
import time
from typing import Any

# Add project root to path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_redis_client() -> Any | None:
    """Get Redis client if available."""
    try:
        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))

        client = redis.Redis(host=host, port=port, decode_responses=True)
        client.ping()  # Test connection
        logger.info(f"Connected to Redis at {host}:{port}")
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def get_influx_client() -> Any | None:
    """Get InfluxDB client if available."""
    try:
        from influxdb_client import InfluxDBClient

        url = os.getenv("INFLUX_URL", "http://host.docker.internal:18087")
        token = os.getenv("INFLUX_TOKEN", "chiseai-admin-token")
        org = os.getenv("INFLUX_ORG", "chiseai")

        client = InfluxDBClient(url=url, token=token, org=org)
        # Test connection
        health = client.health()
        if health.status == "pass":
            logger.info(f"Connected to InfluxDB at {url}")
            return client
    except Exception as e:
        logger.warning(f"InfluxDB not available: {e}")
        return None


def register_exporters(redis_client: Any | None, influx_client: Any | None) -> None:
    """Register all governance metrics exporters."""
    from src.governance.constitution.metrics_exporter import ConstitutionMetricsExporter
    from src.governance.memory.metrics_exporter import MemoryMetricsExporter
    from src.governance.metrics.registry import get_registry
    from src.governance.sentinel.metrics_exporter import SentinelMetricsExporter

    registry = get_registry()
    registry.clear()

    # Set InfluxDB client if available
    if influx_client:
        registry.set_influx_client(influx_client)

    # Register exporters
    exporters = [
        ConstitutionMetricsExporter(
            influx_client=influx_client, redis_client=redis_client
        ),
        SentinelMetricsExporter(influx_client=influx_client, redis_client=redis_client),
        MemoryMetricsExporter(influx_client=influx_client, redis_client=redis_client),
    ]

    for exporter in exporters:
        registry.register(exporter)
        logger.info(f"Registered exporter: {exporter.feature_name}")

    return registry


def run_collection_loop(interval: int = 15) -> None:
    """Run metrics collection loop."""
    from src.governance.metrics.registry import get_registry

    registry = get_registry()
    running = True

    def signal_handler(signum, frame):
        nonlocal running
        logger.info("Received shutdown signal")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Starting metrics collection loop (interval: {interval}s)")

    while running:
        try:
            # Collect metrics from all exporters
            points = registry.collect_all()
            logger.debug(f"Collected {len(points)} metric points")

            # Export to InfluxDB
            results = registry.export_all(bucket="governance")

            success_count = sum(1 for r in results.values() if r.success)
            total_points = sum(r.points_exported for r in results.values())

            logger.info(
                f"Export complete: {success_count}/{len(results)} exporters, "
                f"{total_points} points"
            )

            # Log any errors
            for name, result in results.items():
                if result.errors:
                    logger.error(f"Exporter {name} errors: {result.errors}")

        except Exception as e:
            logger.exception(f"Error during collection: {e}")

        # Wait for next interval
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    logger.info("Metrics collection stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Start governance metrics exporters")
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Collection interval in seconds (default: 15)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect once and exit",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    # Get clients
    redis_client = get_redis_client()
    influx_client = get_influx_client()

    # Register exporters
    register_exporters(redis_client, influx_client)

    if args.once:
        # Single collection
        from src.governance.metrics.registry import get_registry

        registry = get_registry()
        points = registry.collect_all()
        print(f"Collected {len(points)} metric points")
        for p in points:
            print(f"  {p.name}: {p.value}")
    else:
        # Run loop
        run_collection_loop(args.interval)


if __name__ == "__main__":
    main()
