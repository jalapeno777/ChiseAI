"""Tests for SignalConsumer.

Tests the Redis → Orchestrator signal bridge functionality.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
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
            SignalConsumer.HEALTH_MARKER_KEY,
            mapping={
                "status": "active",
                "started_at": mock_redis.hset.call_args[1]["mapping"]["started_at"],
                "poll_interval": "5.0",
                "processed_count": "0",
            },
        )

        await consumer.stop()

        # Verify health marker was cleared
        mock_redis.delete.assert_called_with(SignalConsumer.HEALTH_MARKER_KEY)


class TestHealthMarkerTTL:
    """Tests for health marker TTL functionality."""

    @pytest.mark.asyncio
    async def test_health_marker_set_with_ttl(self, mock_orchestrator):
        """Test that health marker is set with TTL of 120 seconds."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        await consumer.start()

        # Verify hset was called with correct key
        hset_calls = [
            c
            for c in mock_redis.hset.call_args_list
            if c[0][0] == "paper:signal_consumer:health"
        ]
        assert len(hset_calls) == 1

        # Verify expire was called with TTL=120
        mock_redis.expire.assert_called_with(
            SignalConsumer.HEALTH_MARKER_KEY,
            SignalConsumer.HEALTH_MARKER_TTL,
        )

        await consumer.stop()

    @pytest.mark.asyncio
    async def test_refresh_health_marker_ttl(self, mock_orchestrator, mock_redis):
        """Test that _refresh_health_marker_ttl resets TTL to 120s."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        mock_redis.expire.reset_mock()
        await consumer._refresh_health_marker_ttl()

        mock_redis.expire.assert_called_once_with(
            SignalConsumer.HEALTH_MARKER_KEY,
            SignalConsumer.HEALTH_MARKER_TTL,
        )

    @pytest.mark.asyncio
    async def test_ttl_refreshed_during_polling_loop(self, mock_orchestrator):
        """Test that TTL is refreshed after each poll cycle."""
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=0.05,  # Very fast for test
            symbol_throttle_seconds=0.0,
        )

        await consumer.start()

        # Let it run a couple of poll cycles
        await asyncio.sleep(0.15)

        await consumer.stop()

        # expire should have been called multiple times:
        # once in start() + at least once per poll cycle
        expire_calls = [
            c
            for c in mock_redis.expire.call_args_list
            if c[0][0] == SignalConsumer.HEALTH_MARKER_KEY
        ]
        assert (
            len(expire_calls) >= 2
        ), f"Expected at least 2 expire calls (start + poll refresh), got {len(expire_calls)}"

    @pytest.mark.asyncio
    async def test_crash_leaves_marker_to_expire(self, mock_orchestrator):
        """Test that if consumer crashes (no stop()), marker expires via TTL.

        Simulates a crash by setting health marker but NOT calling stop().
        The TTL ensures the marker auto-expires after HEALTH_MARKER_TTL seconds.
        """
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        # NOTE: delete is NOT called (simulating crash)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        # Start sets health marker with TTL
        await consumer._set_health_marker(
            datetime.fromisoformat("2026-03-29T13:00:00+00:00")
        )

        # Verify expire was called with TTL
        mock_redis.expire.assert_called_with(
            SignalConsumer.HEALTH_MARKER_KEY,
            SignalConsumer.HEALTH_MARKER_TTL,
        )

        # Verify delete was NOT called (crash scenario)
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_graceful_stop_clears_marker(self, mock_orchestrator):
        """Test that graceful stop clears the health marker entirely."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        await consumer.start()
        await consumer.stop()

        # Verify delete was called with the correct key
        mock_redis.delete.assert_called_with(SignalConsumer.HEALTH_MARKER_KEY)

    @pytest.mark.asyncio
    async def test_refresh_health_marker_ttl_handles_redis_exception(
        self, mock_orchestrator, mock_redis
    ):
        """Test that _refresh_health_marker_ttl handles Redis exceptions gracefully.

        When redis.expire() raises an exception, it should be caught and logged
        as a warning, not crash the consumer.
        """
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        # Configure expire to raise an exception
        mock_redis.expire.side_effect = Exception("Redis connection error")

        # Should not raise, just log warning
        await consumer._refresh_health_marker_ttl()

        # Verify expire was still called (it attempted the operation)
        mock_redis.expire.assert_called_once_with(
            SignalConsumer.HEALTH_MARKER_KEY,
            SignalConsumer.HEALTH_MARKER_TTL,
        )

    @pytest.mark.asyncio
    async def test_ttl_refresh_stops_after_consumer_stop(self, mock_orchestrator):
        """Test that TTL refresh does not continue after consumer.stop() is called.

        Verifies that once stop() is called, _refresh_health_marker_ttl() is
        not called anymore, ensuring clean shutdown without stray operations.
        """
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=0.05,  # Fast polling for test
            symbol_throttle_seconds=0.0,
        )

        # Use a flag to track TTL refresh calls
        refresh_calls = []
        original_expire = mock_redis.expire

        async def track_expire(*args, **kwargs):
            refresh_calls.append(args)
            return await original_expire(*args, **kwargs)

        mock_redis.expire = AsyncMock(side_effect=track_expire)

        await consumer.start()

        # Wait for at least one poll cycle
        await asyncio.sleep(0.12)

        # Get the number of TTL refreshes before stop
        expire_count_before_stop = len(refresh_calls)

        # Stop the consumer
        await consumer.stop()

        # Get the number of TTL refreshes after stop
        expire_count_after_stop = len(refresh_calls)

        # Verify that stop() was called
        assert (
            expire_count_before_stop >= 1
        ), "Expected at least 1 TTL refresh before stop"

        # No additional TTL refreshes should occur after stop()
        # The stop should cause the polling loop to exit before next refresh
        assert len(refresh_calls) == expire_count_before_stop, (
            f"TTL refresh should not continue after stop(). "
            f"Expected {expire_count_before_stop} calls, got {len(refresh_calls)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
