#!/usr/bin/env python3
"""Continuous signal generator for live runtime.

This script continuously generates signals from live InfluxDB data
and stores them in Redis using the correct key pattern that the
forensic harness expects. No mock data is used.
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

# Set Redis connection defaults (only if not already set by container env)
os.environ.setdefault("REDIS_HOST", "host.docker.internal")
os.environ.setdefault("REDIS_PORT", "6380")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import redis

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.storage import InfluxDBStorage, StorageConfig
from data_ingestion.timeframe_config import Timeframe
from signal_generation.models import SignalStatus
from signal_generation.signal_generator import SignalGenerationConfig, SignalGenerator

# Enforce live InfluxDB only - no mock fallback allowed
ALLOW_SIMULATOR_FALLBACK = False

# Supported symbols for live runtime
LIVE_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
]

# Supported timeframes for live runtime
LIVE_TIMEFRAMES = [
    Timeframe.MINUTE_15,
    Timeframe.HOUR_1,
]


def get_influxdb_config() -> StorageConfig:
    """Build InfluxDB config from environment variables."""
    url = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    parsed = urlparse(url)
    return StorageConfig(
        host=parsed.hostname or "localhost",
        port=parsed.port or 8086,
        database=os.environ.get("INFLUXDB_BUCKET", "ohlcv"),
        username=os.environ.get("INFLUXDB_ORG", "-"),
        password=os.environ.get("INFLUXDB_TOKEN", ""),
        token=os.environ.get("INFLUXDB_TOKEN", ""),
        ssl=False,
    )


async def fetch_live_ohlcv(
    storage: InfluxDBStorage,
    symbol: str,
    timeframe: Timeframe,
    limit: int = 50,
) -> list[OHLCVData]:
    """Fetch live OHLCV data from InfluxDB.

    Args:
        storage: InfluxDB storage instance
        symbol: Trading pair symbol (e.g. "BTC/USDT")
        timeframe: Timeframe enum
        limit: Maximum number of candles to fetch

    Returns:
        List of OHLCVData objects, newest first
    """
    data = await storage.fetch(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )
    # Storage returns newest first; reverse for chronological order
    data.reverse()
    return data


async def check_influxdb_connectivity_with_retry(
    max_retries: int = 3,
    initial_backoff: float = 2.0,
    max_backoff: float = 30.0,
) -> bool:
    """Guardrail check for InfluxDB connectivity at startup with retry logic.

    Implements exponential backoff to handle transient connectivity issues.
    Logs all attempts and failures for diagnosis.

    Args:
        max_retries: Maximum number of connection attempts
        initial_backoff: Initial backoff delay in seconds
        max_backoff: Maximum backoff delay in seconds

    Returns:
        True if InfluxDB is reachable, False otherwise.
        Logs fatal error and exits with code 1 if unreachable after retries.
    """
    config = get_influxdb_config()
    backoff = initial_backoff

    for attempt in range(1, max_retries + 1):
        logger.info(
            f"Checking InfluxDB connectivity... (attempt {attempt}/{max_retries})"
        )
        logger.info(f"  Target: {config.host}:{config.port} (bucket={config.database})")

        storage = InfluxDBStorage(config)
        try:
            is_healthy = await storage.health_check()
            if is_healthy:
                logger.info("InfluxDB connection successful")
                return True
            else:
                logger.warning(
                    f"Attempt {attempt}/{max_retries}: InfluxDB health check returned False"
                )
        except Exception as e:
            logger.warning(
                f"Attempt {attempt}/{max_retries}: InfluxDB connection failed: {e}"
            )

        if attempt < max_retries:
            logger.info(f"Waiting {backoff:.1f}s before retry...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    # All retries exhausted
    logger.error("=" * 60)
    logger.error("FATAL: InfluxDB connectivity check failed after all retries")
    logger.error(f"  Target: {config.host}:{config.port}")
    logger.error(f"  Bucket: {config.database}")
    logger.error(
        "  Attempts: " + ", ".join([f"attempt {i + 1}" for i in range(max_retries)])
    )
    logger.error("=" * 60)
    logger.error("Cannot proceed without live InfluxDB data (no mock fallback allowed)")
    return False


async def check_influxdb_connectivity() -> bool:
    """Guardrail check for InfluxDB connectivity at startup.

    Returns:
        True if InfluxDB is reachable, False otherwise.
        Logs fatal error and exits with code 1 if unreachable.
    """
    return await check_influxdb_connectivity_with_retry()


def store_signal_in_redis_paper_mode(
    r: redis.Redis, signal, mode: str = "paper"
) -> bool:
    """Store a signal in Redis using the paper:signal:* pattern and update indexes."""
    try:
        now = datetime.now(UTC)
        timestamp_str = now.strftime("%Y%m%d%H%M%S")
        signal.token.replace("/", "_")
        signal_id = signal.signal_id or str(uuid.uuid4())

        # Use paper:signal pattern that forensic harness expects
        key = f"paper:signal:{timestamp_str}:{signal.token}:{signal_id}"

        signal_data = {
            "signal_id": signal_id,
            "token": signal.token,
            "direction": signal.direction_str,
            "confidence": str(signal.confidence),
            "timestamp": signal.timestamp.isoformat(),
            "status": signal.status.value,
            "timeframe": signal.timeframe,
            "mode": mode,
            "stored_at": now.isoformat(),
        }

        r.hset(key, mapping=signal_data)
        r.expire(key, 604800)  # 7 days

        # Also add to the sorted set index for forensic harness
        timestamp_score = now.timestamp()
        r.zadd("paper:index:signals", {signal_id: timestamp_score})
        r.expire("paper:index:signals", 604800)  # 7 days

        logger.info(
            f"Signal stored: {key} | {signal.token} {signal.direction_str} {signal.confidence:.1%}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store signal: {e}")
        return False


async def generate_signals_batch(
    r: redis.Redis,
    generator: SignalGenerator,
    storage: InfluxDBStorage,
    count: int = 2,
):
    """Generate a batch of signals from live InfluxDB data."""
    generated = 0

    for _ in range(count):
        for symbol in LIVE_SYMBOLS:
            for timeframe in LIVE_TIMEFRAMES:
                try:
                    ohlcv_data = await fetch_live_ohlcv(
                        storage=storage,
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=50,
                    )

                    if not ohlcv_data:
                        logger.warning(
                            f"No live OHLCV data for {symbol} {timeframe.value}"
                        )
                        continue

                    # Use the latest close price as current price
                    current_price = ohlcv_data[-1].close_price

                    signal = generator.generate_signal(
                        token=symbol,
                        timeframe=timeframe,
                        ohlcv_data=ohlcv_data,
                        current_price=current_price,
                    )

                    if signal.status == SignalStatus.ACTIONABLE:
                        if store_signal_in_redis_paper_mode(r, signal, mode="paper"):
                            generated += 1

                except Exception as e:
                    logger.error(f"Error generating signal for {symbol}: {e}")

    return generated


async def continuous_signal_generation(
    duration_minutes: int = 60, interval_seconds: int = 30
):
    """Continuously generate signals for the specified duration.

    Args:
        duration_minutes: Duration in minutes (0 = run forever)
        interval_seconds: Seconds between signal generation batches
    """
    duration_str = f"{duration_minutes} minutes" if duration_minutes > 0 else "forever"
    logger.info(f"Starting continuous signal generation for {duration_str}")
    logger.info(f"Signal interval: every {interval_seconds} seconds")
    logger.info(f"Live symbols: {LIVE_SYMBOLS}")
    logger.info(f"Live timeframes: {[tf.value for tf in LIVE_TIMEFRAMES]}")

    # Guardrail: Check InfluxDB connectivity BEFORE entering main loop
    if not await check_influxdb_connectivity():
        logger.critical("InfluxDB connectivity check failed - exiting")
        # Ensure all logs are flushed before exit
        for handler in logger.handlers:
            handler.flush()
        sys.exit(1)

    # Connect to Redis (use env vars, fallback to defaults)
    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "host.docker.internal"),
        port=int(os.environ.get("REDIS_PORT", "6380")),
        decode_responses=True,
        socket_connect_timeout=5,
    )

    # Test connection
    try:
        r.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return 0

    # Get initial count
    initial_count = len(cast(list[str], r.keys("paper:signal:*")))
    logger.info(f"Initial paper signal count: {initial_count}")

    # Create signal generator with lower threshold
    config = SignalGenerationConfig(
        actionable_threshold=0.50,  # Lower threshold for more signals
        enable_freshness_checks=True,
        enable_heartbeat=True,
        log_filtered_signals=False,
        enable_caching=False,
    )

    generator = SignalGenerator(config=config)
    logger.info("Signal generator initialized")

    # Create InfluxDB storage for live data fetching
    influx_config = get_influxdb_config()
    storage = InfluxDBStorage(influx_config)
    logger.info("InfluxDB storage initialized for live data")

    # Track metrics
    total_generated = 0
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else None

    # Signal generation loop
    iteration = 0
    while True:
        # Check if we should stop (only if duration is set)
        if end_time is not None and time.time() >= end_time:
            logger.info("Duration reached, stopping signal generation")
            break
        iteration += 1
        elapsed = time.time() - start_time

        # Calculate remaining time (only if duration is set)
        if end_time is not None:
            remaining = (end_time - time.time()) / 60
            remaining_str = f"{remaining:.1f}min"
        else:
            remaining_str = "∞"

        logger.info(
            f"[Iteration {iteration}] Elapsed: {elapsed / 60:.1f}min, Remaining: {remaining_str}"
        )

        # Generate signals from live data
        count = await generate_signals_batch(r, generator, storage, count=2)
        total_generated += count

        # Record heartbeat with pipeline status
        r.hset(
            "bmad:chiseai:scheduler:heartbeat",
            mapping={
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "running",
                "pipeline_status": "healthy",
                "iteration": str(iteration),
                "signals_generated": str(total_generated),
                "signals_15m": str(
                    total_generated
                ),  # For pipeline_alerts.py compatibility
                "unix_timestamp": str(int(time.time())),
            },
        )

        # Check current signal count
        current_count = len(cast(list[str], r.keys("paper:signal:*")))
        logger.info(
            f"Total paper signals: {current_count} (+{current_count - initial_count} since start)"
        )

        # Wait for next interval
        await asyncio.sleep(interval_seconds)

    # Final stats
    final_count = len(cast(list[str], r.keys("paper:signal:*")))
    logger.info("=" * 60)
    logger.info("Signal generation complete!")
    logger.info(f"Total signals generated: {total_generated}")
    logger.info(f"Final paper signal count: {final_count}")
    logger.info(f"Net new signals: {final_count - initial_count}")
    logger.info("=" * 60)

    return total_generated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Continuous signal generator for live runtime"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in minutes (default: 60, 0 = run forever)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Signal generation interval in seconds (default: 30)",
    )

    args = parser.parse_args()

    try:
        count = asyncio.run(
            continuous_signal_generation(
                duration_minutes=args.duration, interval_seconds=args.interval
            )
        )

        if count > 0:
            logger.info(f"✓ SUCCESS: Generated {count} signals")
            sys.exit(0)
        else:
            logger.warning("⚠ No signals were generated")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except SystemExit as e:
        # SystemExit is not caught by Exception, so handle it explicitly
        # This ensures errors are visible before exiting
        if e.code == 0:
            logger.info("Exiting normally")
        else:
            logger.error(f"✗ EXITED WITH CODE {e.code}")
            logger.error("Check logs above for error details")
        sys.exit(e.code)
    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
