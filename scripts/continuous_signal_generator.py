#!/usr/bin/env python3
"""Continuous signal generator for proof loop testing.

This script continuously generates signals and stores them in Redis
using the correct key pattern that the forensic harness expects.
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

# Set Redis connection
os.environ["REDIS_HOST"] = "host.docker.internal"
os.environ["REDIS_PORT"] = "6380"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import redis

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe
from signal_generation.models import SignalStatus
from signal_generation.signal_generator import SignalGenerationConfig, SignalGenerator


def create_mock_ohlcv(base_price: float, trend: str = "up"):
    """Create mock OHLCV data."""
    now = int(datetime.now(UTC).timestamp() * 1000)
    data = []

    for i in range(50):
        if trend == "up":
            price = base_price + i * 10
        elif trend == "down":
            price = base_price - i * 10
        else:
            price = base_price + (i % 10) * 5

        data.append(
            OHLCVData(
                timestamp=now - (i * 60000),
                open_price=price - 50,
                high_price=price + 50,
                low_price=price - 100,
                close_price=price,
                volume=100.0 + i * 10,
            )
        )

    data.reverse()
    return data


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


def generate_signals_batch(r: redis.Redis, generator: SignalGenerator, count: int = 2):
    """Generate a batch of signals."""
    generated = 0

    symbols = [
        ("BTC/USDT", 50000.0, "up"),
        ("ETH/USDT", 3000.0, "down"),
        ("SOL/USDT", 150.0, "up"),
        ("LINK/USDT", 15.0, "up"),
        ("BNB/USDT", 600.0, "down"),
    ]

    for _ in range(count):
        for symbol, base_price, trend in symbols:
            try:
                ohlcv_data = create_mock_ohlcv(base_price, trend)

                signal = generator.generate_signal(
                    token=symbol,
                    timeframe=Timeframe.HOUR_1,
                    ohlcv_data=ohlcv_data,
                    current_price=base_price,
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

    # Connect to Redis
    r = redis.Redis(
        host="host.docker.internal",
        port=6380,
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

        # Generate signals
        count = generate_signals_batch(r, generator, count=2)
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
        description="Continuous signal generator for proof loop"
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
    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
