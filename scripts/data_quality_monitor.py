#!/usr/bin/env python3
"""Data Quality Monitor - Standalone execution script.

Runs data quality monitoring for freshness and gaps detection.
Can be run as a one-time check or as a continuous monitoring service.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps

Usage:
    # One-time check
    python scripts/data_quality_monitor.py --check

    # Continuous monitoring
    python scripts/data_quality_monitor.py --monitor --interval 60

    # Check specific sources
    python scripts/data_quality_monitor.py --check --sources binance,bybit

    # Export to InfluxDB
    python scripts/data_quality_monitor.py --check --export-influx

Environment Variables:
    DQ_BINANCE_SYMBOLS: Comma-separated list of Binance symbols
    DQ_BYBIT_SYMBOLS: Comma-separated list of Bybit symbols
    DQ_BITGET_SYMBOLS: Comma-separated list of Bitget symbols
    DQ_TIMEFRAMES: Comma-separated list of timeframes
    DQ_FRESHNESS_THRESHOLD_SECONDS: Freshness threshold (default 300)
    DQ_DISCORD_WEBHOOK_URL: Discord webhook URL for alerts
    DQ_INFLUX_URL: InfluxDB URL (default http://chiseai-influxdb:18087)
    DQ_INFLUX_TOKEN: InfluxDB token
    DQ_INFLUX_ORG: InfluxDB org (default chiseai)
    DQ_INFLUX_BUCKET: InfluxDB bucket (default chiseai)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap

from operations.data_quality_monitoring import (
    DataQualityMonitor,
    DataSource,
    DiscordAlertSender,
    FreshnessMetrics,
    GapAlert,
    GrafanaDashboardQueries,
    InfluxDBExporter,
    SourceConfig,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MockDataPoint:
    """Mock data point for testing."""

    def __init__(self, timestamp: int):
        self.timestamp = timestamp

    @property
    def datetime_utc(self) -> datetime:
        """Return timestamp as UTC datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=UTC)


def parse_symbols(env_var: str, default: list[str]) -> list[str]:
    """Parse comma-separated symbols from env."""
    value = os.getenv(env_var)
    if value:
        return [s.strip() for s in value.split(",")]
    return default


def parse_timeframes(env_var: str, default: list[str]) -> list[str]:
    """Parse comma-separated timeframes from env."""
    value = os.getenv(env_var)
    if value:
        return [t.strip() for t in value.split(",")]
    return default


def get_source_configs(args: argparse.Namespace) -> list[SourceConfig]:
    """Get source configurations from args and environment."""
    configs = []

    # Parse sources from args
    sources = []
    if args.sources:
        sources = [s.strip().lower() for s in args.sources.split(",")]

    # Binance
    if not sources or "binance" in sources:
        binance_symbols = parse_symbols(
            "DQ_BINANCE_SYMBOLS",
            ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        )
        if binance_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BINANCE,
                    symbols=binance_symbols,
                    timeframes=parse_timeframes(
                        "DQ_TIMEFRAMES", ["1m", "5m", "15m", "1h"]
                    ),
                    freshness_threshold_seconds=args.threshold,
                    gap_detection_enabled=True,
                    enabled=True,
                )
            )

    # Bybit
    if not sources or "bybit" in sources:
        bybit_symbols = parse_symbols(
            "DQ_BYBIT_SYMBOLS",
            ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        )
        if bybit_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BYBIT,
                    symbols=bybit_symbols,
                    timeframes=parse_timeframes(
                        "DQ_TIMEFRAMES", ["1m", "5m", "15m", "1h"]
                    ),
                    freshness_threshold_seconds=args.threshold,
                    gap_detection_enabled=True,
                    enabled=True,
                )
            )

    # Bitget
    if not sources or "bitget" in sources:
        bitget_symbols = parse_symbols(
            "DQ_BITGET_SYMBOLS",
            ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        )
        if bitget_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BITGET,
                    symbols=bitget_symbols,
                    timeframes=parse_timeframes(
                        "DQ_TIMEFRAMES", ["1m", "5m", "15m", "1h"]
                    ),
                    freshness_threshold_seconds=args.threshold,
                    gap_detection_enabled=True,
                    enabled=True,
                )
            )

    return configs


async def run_check(args: argparse.Namespace) -> int:
    """Run a one-time data quality check.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 = success, 1 = issues found)
    """
    logger.info("Running data quality check...")

    # Create monitor
    source_configs = get_source_configs(args)
    monitor = DataQualityMonitor(
        source_configs=source_configs,
        freshness_cooldown_seconds=args.cooldown,
    )

    # Set up Discord alert handler if webhook provided
    discord_sender: DiscordAlertSender | None = None
    webhook_url = args.discord_webhook or os.getenv("DQ_DISCORD_WEBHOOK_URL")
    if webhook_url:
        discord_sender = DiscordAlertSender(webhook_url=webhook_url)

        async def discord_handler(
            alert_type: str,
            source: DataSource,
            message: str,
            severity: str,
            metrics: dict,
        ) -> None:
            """Send alerts to Discord."""
            if alert_type == "freshness":
                await discord_sender.send_freshness_alert(
                    source=source,
                    symbol=metrics.get("symbol", "unknown"),
                    timeframe=metrics.get("timeframe", "unknown"),
                    data_age_seconds=metrics.get("data_age_seconds"),
                    threshold_seconds=metrics.get("threshold_seconds", 300.0),
                )
            elif alert_type == "gap":
                gap = GapAlert(
                    source=source,
                    symbol=metrics.get("symbol", "unknown"),
                    timeframe=metrics.get("timeframe", "unknown"),
                    gap_start=metrics.get("gap_start", 0),
                    gap_end=metrics.get("gap_end", 0),
                    expected_candles=metrics.get("expected_candles", 0),
                )
                await discord_sender.send_gap_alert(gap)

        monitor.add_alert_handler(discord_handler)

    # Set up InfluxDB exporter if requested
    influx_exporter: InfluxDBExporter | None = None
    if args.export_influx:
        influx_exporter = InfluxDBExporter(
            influx_url=os.getenv("DQ_INFLUX_URL", "http://chiseai-influxdb:18087"),
            influx_token=os.getenv("DQ_INFLUX_TOKEN", ""),
            influx_org=os.getenv("DQ_INFLUX_ORG", "chiseai"),
            influx_bucket=os.getenv("DQ_INFLUX_BUCKET", "chiseai"),
        )

    # Run checks with mock data (in production, this would fetch real data)
    issues_found = 0
    now = datetime.now(UTC)

    for config in source_configs:
        for symbol in config.symbols:
            for timeframe in config.timeframes:
                # Create mock data for demonstration
                # In production, this would fetch from actual data sources
                if args.mock_data:
                    # Simulate stale data for testing
                    age_seconds = args.mock_age if args.mock_age else 0
                    mock_timestamp = int(
                        (
                            now - __import__("datetime").timedelta(seconds=age_seconds)
                        ).timestamp()
                        * 1000
                    )
                    mock_data = [MockDataPoint(mock_timestamp)]
                else:
                    # No data - will trigger freshness alert
                    mock_data = []

                # Check freshness
                freshness = await monitor.check_data_freshness(
                    source=config.source,
                    symbol=symbol,
                    timeframe=timeframe,
                    data=mock_data,
                )

                # Export to InfluxDB if configured
                if influx_exporter:
                    influx_exporter.export_freshness_metric(freshness)

                # Check for issues
                if freshness.is_stale:
                    issues_found += 1
                    logger.warning(
                        f"Stale data: {config.source.value}/{symbol}/{timeframe} "
                        f"(age: {freshness.data_age_seconds}s)"
                    )
                    await monitor.send_freshness_alert(
                        source=config.source,
                        symbol=symbol,
                        timeframe=timeframe,
                        data_age_seconds=freshness.data_age_seconds,
                        threshold_seconds=freshness.threshold_seconds,
                    )
                else:
                    logger.info(
                        f"Fresh data: {config.source.value}/{symbol}/{timeframe} "
                        f"(age: {freshness.data_age_seconds}s)"
                    )

    # Get summary
    summary = monitor.get_all_metrics()

    # Output results
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n" + "=" * 60)
        print("DATA QUALITY CHECK SUMMARY")
        print("=" * 60)
        print(f"Total monitored: {summary['freshness']['total_monitored']}")
        print(f"Stale sources: {summary['freshness']['stale_count']}")
        print(f"Active gaps: {summary['gaps']['active_count']}")
        print("=" * 60)

    # Clean up
    if influx_exporter:
        influx_exporter.close()

    if issues_found > 0:
        logger.warning(f"Found {issues_found} data quality issues")
        return 1

    logger.info("All data quality checks passed")
    return 0


async def run_monitor(args: argparse.Namespace) -> int:
    """Run continuous monitoring.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    logger.info(f"Starting continuous monitoring (interval={args.interval}s)...")

    # Create monitor
    source_configs = get_source_configs(args)
    monitor = DataQualityMonitor(
        source_configs=source_configs,
        freshness_cooldown_seconds=args.cooldown,
    )

    # Set up Discord alert handler if webhook provided
    webhook_url = args.discord_webhook or os.getenv("DQ_DISCORD_WEBHOOK_URL")
    if webhook_url:
        discord_sender = DiscordAlertSender(webhook_url=webhook_url)

        async def discord_handler(
            alert_type: str,
            source: DataSource,
            message: str,
            severity: str,
            metrics: dict,
        ) -> None:
            """Send alerts to Discord."""
            if alert_type == "freshness":
                await discord_sender.send_freshness_alert(
                    source=source,
                    symbol=metrics.get("symbol", "unknown"),
                    timeframe=metrics.get("timeframe", "unknown"),
                    data_age_seconds=metrics.get("data_age_seconds"),
                    threshold_seconds=metrics.get("threshold_seconds", 300.0),
                )
            elif alert_type == "gap":
                gap = GapAlert(
                    source=source,
                    symbol=metrics.get("symbol", "unknown"),
                    timeframe=metrics.get("timeframe", "unknown"),
                    gap_start=metrics.get("gap_start", 0),
                    gap_end=metrics.get("gap_end", 0),
                    expected_candles=metrics.get("expected_candles", 0),
                )
                await discord_sender.send_gap_alert(gap)

        monitor.add_alert_handler(discord_handler)
        logger.info("Discord alerts enabled")

    # Set up InfluxDB exporter if requested
    influx_exporter: InfluxDBExporter | None = None
    if args.export_influx:
        influx_exporter = InfluxDBExporter(
            influx_url=os.getenv("DQ_INFLUX_URL", "http://chiseai-influxdb:18087"),
            influx_token=os.getenv("DQ_INFLUX_TOKEN", ""),
            influx_org=os.getenv("DQ_INFLUX_ORG", "chiseai"),
            influx_bucket=os.getenv("DQ_INFLUX_BUCKET", "chiseai"),
        )
        logger.info("InfluxDB export enabled")

    # Start monitoring
    await monitor.start_monitoring(interval_seconds=args.interval)

    try:
        # Run indefinitely
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await monitor.stop_monitoring()
        if influx_exporter:
            influx_exporter.close()

    return 0


def generate_dashboard(args: argparse.Namespace) -> int:
    """Generate Grafana dashboard JSON.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    queries = GrafanaDashboardQueries()
    dashboard = queries.get_dashboard_json_template()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(dashboard, f, indent=2)
        logger.info(f"Dashboard saved to {args.output}")
    else:
        print(json.dumps(dashboard, indent=2))

    return 0


def main() -> int:
    """Main entry point."""
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Data Quality Monitor for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run a one-time check
    python data_quality_monitor.py --check

    # Run with Discord alerts
    python data_quality_monitor.py --check --discord-webhook URL

    # Continuous monitoring
    python data_quality_monitor.py --monitor --interval 60

    # Generate Grafana dashboard
    python data_quality_monitor.py --dashboard --output dashboard.json
        """,
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Run a one-time data quality check",
    )
    mode_group.add_argument(
        "--monitor",
        action="store_true",
        help="Run continuous monitoring",
    )
    mode_group.add_argument(
        "--dashboard",
        action="store_true",
        help="Generate Grafana dashboard JSON",
    )

    # Source configuration
    parser.add_argument(
        "--sources",
        type=str,
        help="Comma-separated list of sources to monitor (binance,bybit,bitget)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=300.0,
        help="Freshness threshold in seconds (default: 300 = 5 minutes)",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=60.0,
        help="Alert cooldown in seconds (default: 60)",
    )

    # Monitoring options
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="Monitoring interval in seconds (default: 60)",
    )

    # Alerting options
    parser.add_argument(
        "--discord-webhook",
        type=str,
        help="Discord webhook URL for alerts",
    )

    # Export options
    parser.add_argument(
        "--export-influx",
        action="store_true",
        help="Export metrics to InfluxDB",
    )

    # Output options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for dashboard JSON",
    )

    # Testing options
    parser.add_argument(
        "--mock-data",
        action="store_true",
        help="Use mock data for testing",
    )
    parser.add_argument(
        "--mock-age",
        type=float,
        help="Mock data age in seconds (for testing stale detection)",
    )

    args = parser.parse_args()

    # Run appropriate mode
    if args.dashboard:
        return generate_dashboard(args)
    elif args.monitor:
        return asyncio.run(run_monitor(args))
    else:
        return asyncio.run(run_check(args))


if __name__ == "__main__":
    sys.exit(main())
