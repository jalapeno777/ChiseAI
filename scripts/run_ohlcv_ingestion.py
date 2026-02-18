#!/usr/bin/env python3
"""OHLCV Ingestion Runner - Continuous market data ingestion for ChiseAI.

Usage:
    python3 scripts/run_ohlcv_ingestion.py --run      # Continuous
    python3 scripts/run_ohlcv_ingestion.py --check    # Dry-run
    python3 scripts/run_ohlcv_ingestion.py --once     # One-time
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap

# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)

from data_ingestion.ohlcv_fetcher import CCXTAdapter, OHLCVFetcher
from data_ingestion.storage import InfluxDBStorage, StorageConfig
from data_ingestion.timeframe_config import Timeframe, timeframe_from_string

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def get_env_var(name: str, default: str | None = None, required: bool = False) -> str:
    """Get environment variable with optional default and required check."""
    value = os.getenv(name, default)
    if required and not value:
        logger.error(f"Required environment variable {name} is not set")
        sys.exit(1)
    return value or ""


def load_config() -> dict:
    """Load configuration from environment variables."""
    # Determine if running in container
    in_container = os.path.exists("/.dockerenv") or os.getenv("KUBERNETES_SERVICE_HOST")

    # Default host depends on environment
    default_influx_host = "chiseai-influxdb" if in_container else "host.docker.internal"

    config = {
        "influxdb_host": get_env_var("INFLUXDB_HOST", default_influx_host),
        "influxdb_port": int(get_env_var("INFLUXDB_PORT", "18087")),
        "influxdb_token": get_env_var("INFLUXDB_TOKEN", required=True),
        "influxdb_org": get_env_var("INFLUXDB_ORG", "chiseai"),
        "influxdb_bucket": get_env_var("INFLUXDB_BUCKET", "chiseai"),
        "exchange_id": get_env_var("EXCHANGE_ID", "binance"),
        "symbols": [
            s.strip()
            for s in get_env_var("SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")
        ],
        "timeframes": [
            timeframe_from_string(tf.strip())
            for tf in get_env_var("TIMEFRAMES", "1m,5m,15m,1h").split(",")
        ],
        "ingest_interval_seconds": int(get_env_var("INGEST_INTERVAL_SECONDS", "60")),
        "fetch_limit": int(get_env_var("FETCH_LIMIT", "100")),
    }

    return config


def create_storage(config: dict) -> InfluxDBStorage:
    """Create InfluxDB storage instance from config."""
    storage_config = StorageConfig(
        host=config["influxdb_host"],
        port=config["influxdb_port"],
        database=config["influxdb_bucket"],
        username=config["influxdb_org"],
        password=config["influxdb_token"],
    )
    return InfluxDBStorage(storage_config)


def create_fetcher(config: dict) -> OHLCVFetcher:
    """Create OHLCV fetcher instance from config."""
    adapter = CCXTAdapter(exchange_id=config["exchange_id"])
    return OHLCVFetcher(exchange_adapter=adapter)


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    _shutdown_requested = True


async def check_connections(config: dict) -> bool:
    """Check if all connections are healthy (dry-run mode).

    Returns:
        True if all connections are healthy
    """
    logger.info("Running connection check (dry-run mode)...")

    all_healthy = True

    # Check InfluxDB connection
    try:
        storage = create_storage(config)
        influx_healthy = await storage.health_check()
        if influx_healthy:
            host_port = f"{config['influxdb_host']}:{config['influxdb_port']}"
            logger.info(f"✓ InfluxDB connection healthy ({host_port})")
        else:
            host_port = f"{config['influxdb_host']}:{config['influxdb_port']}"
            logger.error(f"✗ InfluxDB connection failed ({host_port})")
            all_healthy = False
    except Exception as e:
        logger.error(f"✗ InfluxDB connection error: {e}")
        all_healthy = False

    # Check Exchange connection
    try:
        fetcher = create_fetcher(config)
        exchange_healthy = await fetcher.exchange_adapter.check_health()
        if exchange_healthy:
            logger.info(f"✓ Exchange connection healthy ({config['exchange_id']})")
        else:
            logger.error(f"✗ Exchange connection failed ({config['exchange_id']})")
            all_healthy = False
    except Exception as e:
        logger.error(f"✗ Exchange connection error: {e}")
        all_healthy = False

    # Log configuration
    logger.info("Configuration:")
    logger.info(f"  - Exchange: {config['exchange_id']}")
    logger.info(f"  - Symbols: {', '.join(config['symbols'])}")
    logger.info(f"  - Timeframes: {', '.join(tf.value for tf in config['timeframes'])}")
    logger.info(f"  - Ingest interval: {config['ingest_interval_seconds']}s")
    logger.info(f"  - Fetch limit: {config['fetch_limit']}")

    if all_healthy:
        logger.info("All connections healthy - ready for ingestion")
    else:
        logger.error("Some connections failed - check configuration and services")

    return all_healthy


async def fetch_and_store(
    fetcher: OHLCVFetcher,
    storage: InfluxDBStorage,
    symbol: str,
    timeframe: Timeframe,
    limit: int,
) -> int:
    """Fetch OHLCV data and store it, using incremental fetching.

    Args:
        fetcher: OHLCV fetcher instance
        storage: Storage instance
        symbol: Trading pair symbol
        timeframe: Timeframe enum
        limit: Maximum candles to fetch

    Returns:
        Number of data points stored
    """
    try:
        # Get the latest timestamp to fetch only new data
        latest_ts = await storage.get_latest_timestamp(symbol, timeframe)

        since_ms: int | None = None
        if latest_ts:
            # Start from the next candle after the latest stored
            since_ms = int(latest_ts.timestamp() * 1000) + 1
            logger.debug(
                f"Fetching {symbol} {timeframe.value} since {latest_ts.isoformat()}"
            )
        else:
            msg = f"No existing data for {symbol} {timeframe.value}"
            logger.debug(f"{msg}, fetching last {limit} candles")

        # Fetch data
        data = await fetcher.fetch(symbol, timeframe, since=since_ms, limit=limit)

        if not data:
            logger.debug(f"No new data for {symbol} {timeframe.value}")
            return 0

        # Store data
        success = await storage.store(symbol, timeframe, data)

        if success:
            logger.info(f"Stored {len(data)} candles for {symbol} {timeframe.value}")
            return len(data)
        else:
            logger.error(f"Failed to store data for {symbol} {timeframe.value}")
            return 0

    except Exception as e:
        logger.error(f"Error fetching/storing {symbol} {timeframe.value}: {e}")
        return 0


async def run_ingestion_cycle(
    fetcher: OHLCVFetcher,
    storage: InfluxDBStorage,
    config: dict,
) -> dict:
    """Run a single ingestion cycle for all symbols and timeframes.

    Returns:
        Statistics dict with counts per symbol/timeframe
    """
    stats = {"total_stored": 0, "symbols": {}}

    for symbol in config["symbols"]:
        if _shutdown_requested:
            break

        symbol_stats = {}

        for timeframe in config["timeframes"]:
            if _shutdown_requested:
                break

            count = await fetch_and_store(
                fetcher, storage, symbol, timeframe, config["fetch_limit"]
            )
            symbol_stats[timeframe.value] = count
            stats["total_stored"] += count

        stats["symbols"][symbol] = symbol_stats

    return stats


async def run_once(config: dict) -> bool:
    """Run one-time ingestion cycle.

    Returns:
        True if successful
    """
    logger.info("Running one-time ingestion...")

    storage = create_storage(config)
    fetcher = create_fetcher(config)

    # Check health first
    if not await storage.health_check():
        logger.error("InfluxDB health check failed")
        return False

    if not await fetcher.exchange_adapter.check_health():
        logger.error("Exchange health check failed")
        return False

    # Run ingestion
    stats = await run_ingestion_cycle(fetcher, storage, config)

    logger.info(
        f"One-time ingestion complete: {stats['total_stored']} total candles stored"
    )
    for symbol, tf_stats in stats["symbols"].items():
        for tf, count in tf_stats.items():
            if count > 0:
                logger.info(f"  - {symbol} {tf}: {count} candles")

    return stats["total_stored"] >= 0  # True even if 0 (no new data is not an error)


async def run_continuous(config: dict) -> None:
    """Run continuous ingestion loop."""
    logger.info("Starting continuous OHLCV ingestion...")

    storage = create_storage(config)
    fetcher = create_fetcher(config)

    # Initial health check
    if not await storage.health_check():
        logger.error("InfluxDB health check failed - cannot start")
        return

    if not await fetcher.exchange_adapter.check_health():
        logger.error("Exchange health check failed - cannot start")
        return

    symbol_count = len(config["symbols"])
    tf_count = len(config["timeframes"])
    logger.info(f"Ingestion started for {symbol_count} symbols, {tf_count} timeframes")
    logger.info(f"Interval: {config['ingest_interval_seconds']}s")
    logger.info("Press Ctrl+C to stop gracefully")

    cycle_count = 0

    while not _shutdown_requested:
        cycle_start = datetime.now(UTC)
        cycle_count += 1

        logger.debug(f"Starting ingestion cycle #{cycle_count}")

        try:
            stats = await run_ingestion_cycle(fetcher, storage, config)

            if stats["total_stored"] > 0:
                logger.info(
                    f"Cycle #{cycle_count}: stored {stats['total_stored']} candles"
                )
            else:
                logger.debug(f"Cycle #{cycle_count}: no new data")

        except Exception as e:
            logger.error(f"Error in ingestion cycle #{cycle_count}: {e}")

        # Calculate sleep time to maintain consistent interval
        elapsed = (datetime.now(UTC) - cycle_start).total_seconds()
        sleep_time = max(0, config["ingest_interval_seconds"] - elapsed)

        if sleep_time > 0 and not _shutdown_requested:
            logger.debug(f"Sleeping for {sleep_time:.1f}s")
            await asyncio.sleep(sleep_time)

    logger.info("Continuous ingestion stopped gracefully")


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="OHLCV Ingestion Runner for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/run_ohlcv_ingestion.py --run      # Continuous ingestion
  python3 scripts/run_ohlcv_ingestion.py --check    # Dry-run connection check
  python3 scripts/run_ohlcv_ingestion.py --once     # One-time fetch and store
        """,
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run continuous ingestion loop",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check connections without storing data (dry-run)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        dest="once",
        help="Run one-time fetch and store",
    )

    args = parser.parse_args()

    # Default to --check if no mode specified
    if not (args.run or args.check or args.once):
        args.check = True

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load configuration
    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    # Execute requested mode
    if args.check:
        healthy = await check_connections(config)
        return 0 if healthy else 1

    elif args.once:
        success = await run_once(config)
        return 0 if success else 1

    elif args.run:
        await run_continuous(config)
        return 0

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        sys.exit(1)
