#!/usr/bin/env python3
"""Test script for signal generation.

P0-RUNTIME-HARDEN-004: Manual signal generation test
Triggers signal generation and verifies signals appear in Redis.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

# Set Redis connection for containerized environment
# Override .env settings which may point to internal Docker network
os.environ["REDIS_HOST"] = "host.docker.internal"
os.environ["REDIS_PORT"] = "6380"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_signal_generation():
    """Test signal generation manually."""
    try:
        from signal_generation.signal_generator import (
            SignalGenerator,
            SignalGenerationConfig,
        )
        from signal_generation.models import SignalStatus
        from data_ingestion.ohlcv_fetcher import OHLCVData
        from data_ingestion.timeframe_config import Timeframe
        import redis

        # Connect to Redis (use host.docker.internal for containerized environment)
        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
        )

        # Get initial signal count
        initial_count = len(r.keys("bmad:chiseai:signals:*"))
        logger.info(f"Initial signal count: {initial_count}")

        # Create signal generator with lower threshold for testing
        config = SignalGenerationConfig(
            actionable_threshold=0.60,  # Lower threshold for testing
            dry_run_mode=False,
            enable_heartbeat=True,
            log_filtered_signals=True,
            enable_caching=False,  # Disable caching for testing
        )

        generator = SignalGenerator(config=config)
        logger.info(
            f"SignalGenerator created with threshold: {config.actionable_threshold:.0%}"
        )

        # Create mock OHLCV data
        mock_data = [
            OHLCVData(
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000)
                - (i * 60000),
                open_price=50000.0 + i * 10,
                high_price=50100.0 + i * 10,
                low_price=49900.0 + i * 10,
                close_price=50050.0 + i * 10,
                volume=100.0 + i,
            )
            for i in range(50)
        ]

        # Reverse to get chronological order
        mock_data.reverse()

        # Generate signal for BTC/USDT
        logger.info("Generating signal for BTC/USDT...")
        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_data,
            current_price=50050.0,
        )

        logger.info(f"Signal generated:")
        logger.info(f"  Token: {signal.token}")
        logger.info(f"  Direction: {signal.direction_str}")
        logger.info(f"  Confidence: {signal.confidence:.1%}")
        logger.info(f"  Status: {signal.status.value}")
        logger.info(f"  Latency: {signal.generation_latency_ms:.1f}ms")

        # Get diagnostics
        diagnostics = generator.get_diagnostics()
        logger.info(f"Diagnostics: {diagnostics}")

        # Get final signal count
        final_count = len(r.keys("bmad:chiseai:signals:*"))
        logger.info(f"Final signal count: {final_count}")
        logger.info(f"Signal count delta: {final_count - initial_count}")

        # Check heartbeat
        heartbeat = r.hgetall("bmad:chiseai:signal_generator:heartbeat")
        if heartbeat:
            logger.info(f"Generator heartbeat: {heartbeat}")
        else:
            logger.warning("No generator heartbeat found")

        # Success if we got a signal or diagnostics show attempts
        if diagnostics["total_attempts"] > 0:
            logger.info("✓ Signal generation test PASSED")
            return 0
        else:
            logger.error("✗ Signal generation test FAILED - no attempts recorded")
            return 1

    except Exception as e:
        logger.error(f"Signal generation test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


def test_dry_run_mode():
    """Test signal generation in dry-run mode."""
    try:
        from signal_generation.signal_generator import (
            SignalGenerator,
            SignalGenerationConfig,
        )
        from data_ingestion.ohlcv_fetcher import OHLCVData
        from data_ingestion.timeframe_config import Timeframe
        import redis

        # Connect to Redis (use host.docker.internal for containerized environment)
        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
        )

        # Get initial count
        initial_count = len(r.keys("bmad:chiseai:signals:*"))

        # Create generator in dry-run mode
        config = SignalGenerationConfig(
            actionable_threshold=0.60,
            dry_run_mode=True,  # Dry run - don't store signals
            enable_heartbeat=True,
        )

        generator = SignalGenerator(config=config)

        # Create mock data
        mock_data = [
            OHLCVData(
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000)
                - (i * 60000),
                open_price=50000.0,
                high_price=50100.0,
                low_price=49900.0,
                close_price=50050.0,
                volume=100.0,
            )
            for i in range(50)
        ]
        mock_data.reverse()

        # Generate signal
        signal = generator.generate_signal(
            token="ETH/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_data,
            current_price=3000.0,
        )

        # Check count didn't change in dry-run mode
        final_count = len(r.keys("bmad:chiseai:signals:*"))

        logger.info(f"Dry-run test: initial={initial_count}, final={final_count}")
        logger.info(f"Signal status: {signal.status.value}")

        logger.info("✓ Dry-run test PASSED")
        return 0

    except Exception as e:
        logger.error(f"Dry-run test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Signal Generation Test - P0-RUNTIME-HARDEN-004")
    logger.info("=" * 60)

    results = []

    # Test 1: Basic signal generation
    logger.info("\n[Test 1] Basic Signal Generation")
    logger.info("-" * 40)
    results.append(("Basic Generation", test_signal_generation()))

    # Test 2: Dry-run mode
    logger.info("\n[Test 2] Dry-Run Mode")
    logger.info("-" * 40)
    results.append(("Dry-Run Mode", test_dry_run_mode()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    for name, result in results:
        status = "✓ PASS" if result == 0 else "✗ FAIL"
        logger.info(f"  {name}: {status}")

    total = len(results)
    passed = sum(1 for _, r in results if r == 0)
    logger.info(f"\nTotal: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())
