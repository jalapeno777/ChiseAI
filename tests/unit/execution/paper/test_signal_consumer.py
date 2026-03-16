"""Tests for SignalConsumer.

Tests the Redis → Orchestrator signal bridge functionality.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.signal_consumer import SignalConsumer
from signal_generation.models import SignalDirection, SignalStatus


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    orchestrator = MagicMock()
    orchestrator.submit_signal = AsyncMock()
    return orchestrator


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.scan = AsyncMock(return_value=(0, []))
    redis.type = AsyncMock(return_value="hash")
    redis.hgetall = AsyncMock(return_value={})
    redis.smembers = AsyncMock(return_value=set())
    redis.sadd = AsyncMock()
    redis.hset = AsyncMock()
    redis.close = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def sample_signal_data():
    """Create sample signal data as stored in Redis."""
    return {
        "signal_id": str(uuid.uuid4()),
        "token": "BTC/USDT",
        "direction": "short",
        "confidence": "0.84",
        "timestamp": "2026-02-26T16:25:58.142992+00:00",
        "status": "actionable",
        "timeframe": "1h",
        "mode": "monitor",
    }


class TestSignalConsumer:
    """Test cases for SignalConsumer."""

    @pytest.mark.asyncio
    async def test_consumer_initialization(self, mock_orchestrator):
        """Test that consumer initializes correctly."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            poll_interval=1.0,
        )

        assert consumer.orchestrator == mock_orchestrator
        assert consumer.poll_interval == 1.0
        assert not consumer._running
        assert consumer._processed_signals == set()

    @pytest.mark.asyncio
    async def test_consumer_start_stop(self, mock_orchestrator, mock_redis):
        """Test that consumer starts and stops correctly."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        # Start consumer
        await consumer.start()
        assert consumer._running
        assert consumer._poll_task is not None

        # Stop consumer
        await consumer.stop()
        assert not consumer._running

    @pytest.mark.asyncio
    async def test_convert_to_signal(self, mock_orchestrator, sample_signal_data):
        """Test conversion from Redis hash to Signal object."""
        consumer = SignalConsumer(orchestrator=mock_orchestrator)

        signal = consumer._convert_to_signal(sample_signal_data)

        assert signal is not None
        assert signal.token == "BTC/USDT"
        assert signal.direction == SignalDirection.SHORT
        assert signal.confidence == 0.84
        assert signal.status == SignalStatus.ACTIONABLE
        assert signal.timeframe == "1h"
        assert signal.signal_id == sample_signal_data["signal_id"]

    @pytest.mark.asyncio
    async def test_convert_to_signal_invalid_data(self, mock_orchestrator):
        """Test conversion with invalid data returns None."""
        consumer = SignalConsumer(orchestrator=mock_orchestrator)

        # Invalid direction
        invalid_data = {
            "token": "BTC/USDT",
            "direction": "invalid_direction",
            "confidence": "0.84",
            "timestamp": "2026-02-26T16:25:58.142992+00:00",
            "status": "actionable",
            "timeframe": "1h",
        }

        signal = consumer._convert_to_signal(invalid_data)
        assert signal is None

    @pytest.mark.asyncio
    async def test_poll_once_processes_actionable_signals(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Test that poll_once processes actionable signals."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        # Setup mock to return one signal key
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())  # Not processed yet

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 1
        mock_orchestrator.submit_signal.assert_called_once()
        mock_redis.hset.assert_called_with(redis_key, "status", "consumed")
        mock_redis.sadd.assert_called_with(SignalConsumer.PROCESSED_SET_KEY, signal_id)

    @pytest.mark.asyncio
    async def test_poll_once_skips_non_actionable(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Test that non-actionable signals are skipped."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        # Change status to non-actionable
        sample_signal_data["status"] = "logged_only"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_once_skips_already_processed(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Test that already processed signals are skipped."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value={signal_id})  # Already processed

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        # Load processed signals (normally done in start())
        await consumer._load_processed_signals()

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_orchestrator, mock_redis):
        """Test that stats are returned correctly."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        stats = consumer.get_stats()

        assert stats["running"] is False
        assert stats["poll_interval"] == 5.0
        assert stats["processed_count"] == 0

    @pytest.mark.asyncio
    async def test_reset_processed_set(self, mock_orchestrator, mock_redis):
        """Test that processed set can be reset."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        # Add some processed signals
        consumer._processed_signals = {"signal1", "signal2"}

        await consumer.reset_processed_set()

        assert consumer._processed_signals == set()
        mock_redis.delete.assert_called_with(SignalConsumer.PROCESSED_SET_KEY)


class TestSignalConsumerIntegration:
    """Integration-style tests for SignalConsumer."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, mock_orchestrator, sample_signal_data):
        """Test the full lifecycle of signal consumption."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        # Create mock Redis that returns our test signal
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=0.1,  # Fast polling for test
        )

        # Start consumer
        await consumer.start()
        assert consumer._running

        # Wait for one poll cycle
        await asyncio.sleep(0.15)

        # Stop consumer
        await consumer.stop()
        assert not consumer._running

        # Verify signal was submitted
        mock_orchestrator.submit_signal.assert_called_once()
        call_args = mock_orchestrator.submit_signal.call_args[0][0]
        assert call_args.token == "BTC/USDT"
        assert call_args.direction == SignalDirection.SHORT

    @pytest.mark.asyncio
    async def test_multiple_signals_in_one_poll(self, mock_orchestrator):
        """Test processing multiple signals in a single poll."""
        # Create multiple signal keys
        signal_ids = [str(uuid.uuid4()) for _ in range(3)]
        redis_keys = [
            f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{sid}" for sid in signal_ids
        ]

        signal_data_list = [
            {
                "signal_id": sid,
                "token": "BTC/USDT",
                "direction": "long" if i % 2 == 0 else "short",
                "confidence": "0.85",
                "timestamp": "2026-02-26T16:25:58.142992+00:00",
                "status": "actionable",
                "timeframe": "1h",
            }
            for i, sid in enumerate(signal_ids)
        ]

        # Setup mock to return all keys
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, redis_keys))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(side_effect=signal_data_list)
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 3
        assert mock_orchestrator.submit_signal.call_count == 3

    @pytest.mark.asyncio
    async def test_health_check(self, mock_orchestrator):
        """Test that health check returns correct status."""
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"status": "active"})
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        # Check health before start
        health = await consumer.check_health()
        assert health["healthy"] is False
        assert health["running"] is False

        # Start consumer
        await consumer.start()

        # Check health after start
        health = await consumer.check_health()
        assert health["healthy"] is True
        assert health["running"] is True
        assert health["poll_interval"] == 5.0

        # Stop consumer
        await consumer.stop()

        # Check health after stop
        health = await consumer.check_health()
        assert health["healthy"] is False
        assert health["running"] is False

    @pytest.mark.asyncio
    async def test_health_marker_set_on_start(self, mock_orchestrator):
        """Test that health marker is set in Redis on start."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.hset = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        await consumer.start()

        # Verify health marker was set
        mock_redis.hset.assert_called_with(
            "paper:signal_consumer:health",
            mapping={
                "status": "active",
                "started_at": mock_redis.hset.call_args[1]["mapping"]["started_at"],
                "poll_interval": "5.0",
                "processed_count": "0",
            },
        )

        await consumer.stop()

        # Verify health marker was cleared
        mock_redis.delete.assert_called_with("paper:signal_consumer:health")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
