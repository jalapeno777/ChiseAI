#!/usr/bin/env python3
"""Manual signal generator trigger.

P0-RUNTIME-HARDEN-004: Trigger signal generation and store in Redis.
This is a temporary fix to demonstrate signal generation is working.
"""

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Set Redis connection for containerized environment
os.environ["REDIS_HOST"] = "host.docker.internal"
os.environ["REDIS_PORT"] = "6380"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

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


def store_signal_in_redis(r: redis.Redis, signal, mode: str = "manual") -> bool:
    """Store a signal in Redis."""
    try:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        token_clean = signal.token.replace("/", "_")
        signal_id = signal.signal_id or str(uuid.uuid4())

        key = f"bmad:chiseai:signals:{date_str}:{token_clean}:{signal_id}"

        signal_data = {
            "signal_id": signal_id,
            "token": signal.token,
            "direction": signal.direction_str,
            "confidence": str(signal.confidence),
            "timestamp": signal.timestamp.isoformat(),
            "status": signal.status.value,
            "timeframe": signal.timeframe,
            "mode": mode,
        }

        r.hset(key, mapping=signal_data)
        # Set TTL to 7 days
        r.expire(key, 604800)

        logger.info(f"Signal stored in Redis: {key}")
        return True
    except Exception as e:
        logger.error(f"Failed to store signal: {e}")
        return False


def generate_and_store_signals():
    """Generate signals and store them in Redis."""

    # Connect to Redis
    r = redis.Redis(
        host="host.docker.internal",
        port=6380,
        decode_responses=True,
        socket_connect_timeout=5,
    )

    # Get initial count
    initial_count = len(r.keys("bmad:chiseai:signals:*"))
    logger.info(f"Initial signal count: {initial_count}")

    # Create signal generator with lower threshold for testing
    config = SignalGenerationConfig(
        actionable_threshold=0.60,  # Lower threshold for more signals
        enable_freshness_checks=True,
        enable_heartbeat=True,
        log_filtered_signals=True,
        enable_caching=False,
    )

    generator = SignalGenerator(config=config)

    # Create mock OHLCV data for BTC
    mock_data_btc = [
        OHLCVData(
            timestamp=int(datetime.now(UTC).timestamp() * 1000) - (i * 60000),
            open_price=50000.0 + i * 10,
            high_price=50100.0 + i * 10,
            low_price=49900.0 + i * 10,
            close_price=50050.0 + i * 10,
            volume=100.0 + i,
        )
        for i in range(50)
    ]
    mock_data_btc.reverse()

    # Generate signal for BTC/USDT
    logger.info("Generating signal for BTC/USDT...")
    signal_btc = generator.generate_signal(  # nosec B106
        token="BTC/USDT",
        timeframe=Timeframe.HOUR_1,
        ohlcv_data=mock_data_btc,
        current_price=50050.0,
    )

    logger.info(
        f"BTC Signal: {signal_btc.direction_str} | {signal_btc.confidence:.1%} | {signal_btc.status.value}"
    )

    # Store signal if actionable
    if signal_btc.status == SignalStatus.ACTIONABLE:
        store_signal_in_redis(r, signal_btc, mode="manual_fix")

    # Create mock OHLCV data for ETH
    mock_data_eth = [
        OHLCVData(
            timestamp=int(datetime.now(UTC).timestamp() * 1000) - (i * 60000),
            open_price=3000.0 + i * 5,
            high_price=3050.0 + i * 5,
            low_price=2950.0 + i * 5,
            close_price=3025.0 + i * 5,
            volume=50.0 + i,
        )
        for i in range(50)
    ]
    mock_data_eth.reverse()

    # Generate signal for ETH/USDT
    logger.info("Generating signal for ETH/USDT...")
    signal_eth = generator.generate_signal(  # nosec B106
        token="ETH/USDT",
        timeframe=Timeframe.HOUR_1,
        ohlcv_data=mock_data_eth,
        current_price=3025.0,
    )

    logger.info(
        f"ETH Signal: {signal_eth.direction_str} | {signal_eth.confidence:.1%} | {signal_eth.status.value}"
    )

    # Store signal if actionable
    if signal_eth.status == SignalStatus.ACTIONABLE:
        store_signal_in_redis(r, signal_eth, mode="manual_fix")

    # Get final count
    final_count = len(r.keys("bmad:chiseai:signals:*"))
    logger.info(f"Final signal count: {final_count}")
    logger.info(f"New signals added: {final_count - initial_count}")

    # Show diagnostics
    diagnostics = generator.get_diagnostics()
    logger.info(f"Diagnostics: {diagnostics}")

    # Check heartbeat
    heartbeat = r.hgetall("bmad:chiseai:signal_generator:heartbeat")
    if heartbeat:
        logger.info(f"Generator heartbeat: {heartbeat}")

    return final_count - initial_count


if __name__ == "__main__":
    try:
        new_signals = generate_and_store_signals()
        if new_signals > 0:
            logger.info(f"✓ SUCCESS: Generated and stored {new_signals} new signals")
            sys.exit(0)
        else:
            logger.warning("⚠ No new signals were stored")
            sys.exit(1)
    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
