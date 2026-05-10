"""Tests for SignalConsumer.

Tests the Redis → Orchestrator signal bridge functionality.
"""

from __future__ import annotations

import asyncio
import json
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
    # Stream-related mocks
    redis.xgroup_create = AsyncMock()
    redis.xreadgroup = AsyncMock(return_value=None)
    redis.xack = AsyncMock(return_value=1)
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


@pytest.fixture
def sample_stream_message(sample_signal_data):
    """Create a sample stream message as produced by S4 XADD."""
    message_id = "1708950000000-0"
    fields = {"data": json.dumps(sample_signal_data)}
    return message_id, fields


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
        mock_redis.expire = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        # Stream mocks: return empty so SCAN fallback is used
        mock_redis.xreadgroup = AsyncMock(return_value=None)

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
    async def test_refresh_health_marker(self, mock_orchestrator, mock_redis):
        """Test that _refresh_health_marker updates processed_count and resets TTL."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        mock_redis.hset.reset_mock()
        mock_redis.expire.reset_mock()
        await consumer._refresh_health_marker()

        mock_redis.hset.assert_called_once_with(
            SignalConsumer.HEALTH_MARKER_KEY,
            "processed_count",
            str(len(consumer._processed_signals)),
        )
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
        assert len(expire_calls) >= 2, (
            f"Expected at least 2 expire calls (start + poll refresh), got {len(expire_calls)}"
        )

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
    async def test_refresh_health_marker_handles_redis_exception(
        self, mock_orchestrator, mock_redis
    ):
        """Test that _refresh_health_marker handles Redis exceptions gracefully.

        When redis.hset() or redis.expire() raises an exception, it should be
        caught and logged as a warning, not crash the consumer.
        """
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        # Configure hset to raise an exception
        mock_redis.hset.side_effect = Exception("Redis connection error")

        # Should not raise, just log warning
        await consumer._refresh_health_marker()

        # Verify hset was still called (it attempted the operation)
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_not_called()  # expire should not be called if hset fails

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
        assert expire_count_before_stop >= 1, (
            "Expected at least 1 TTL refresh before stop"
        )

        # No additional TTL refreshes should occur after stop()
        # The stop should cause the polling loop to exit before next refresh
        assert len(refresh_calls) == expire_count_before_stop, (
            f"TTL refresh should not continue after stop(). "
            f"Expected {expire_count_before_stop} calls, got {len(refresh_calls)}"
        )


class TestSilentSignalConsumptionFix:
    """Regression tests for ST-AC7-DEBUG-001.

    Ensures signals for non-allowed symbols are NOT silently consumed
    (marked as processed) without order creation. The fix ensures:
    1. Non-allowed symbols are skipped with WARNING log, NOT consumed
    2. Throttled symbols are skipped with INFO log, NOT consumed
    3. Signals can be retried if symbol is later added to allowlist
    """

    @pytest.mark.asyncio
    async def test_non_allowed_symbol_not_consumed(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Non-allowed symbol signal must NOT be marked consumed.

        Before fix: signal was marked 'consumed' + added to processed set
        at DEBUG log level, making it invisible to future polls.

        After fix: signal is skipped with WARNING, NOT consumed, so it
        can be picked up if the symbol is later added to allowed_symbols.
        """
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )
        # Override allowed_symbols to exclude BTC
        consumer.allowed_symbols = {"ETH/USDT", "SOL/USDT"}

        count = await consumer._poll_once()

        # Must not count as processed
        assert count == 0
        # Must NOT have called orchestrator
        mock_orchestrator.submit_signal.assert_not_called()
        # Must NOT have marked as consumed in Redis
        consumed_calls = [
            c
            for c in mock_redis.hset.call_args_list
            if len(c.args) >= 3 and c.args[1] == "status" and c.args[2] == "consumed"
        ]
        assert len(consumed_calls) == 0, (
            f"Signal for non-allowed symbol should NOT be marked consumed. "
            f"Got {consumed_calls}"
        )
        # Must NOT have added to processed set
        mock_redis.sadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_allowed_symbol_logged_at_warning(
        self, mock_orchestrator, mock_redis, sample_signal_data, caplog
    ):
        """Non-allowed symbol skip must be logged at WARNING level."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )
        consumer.allowed_symbols = {"ETH/USDT"}

        with caplog.at_level("WARNING", logger="execution.paper.signal_consumer"):
            await consumer._poll_once()

        assert any(
            "SKIPPED" in rec.message and "non-allowed" in rec.message
            for rec in caplog.records
        ), f"Expected WARNING with 'SKIPPED' and 'non-allowed', got: {caplog.text}"

    @pytest.mark.asyncio
    async def test_throttled_symbol_not_consumed(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Throttled symbol signal must NOT be marked consumed.

        Before fix: throttled signal was marked 'consumed' + added to
        processed set, permanently discarding it.

        After fix: throttled signal returns False but is NOT consumed,
        so it will be retried after throttle cooldown expires.
        """
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=300.0,  # 5 minute throttle
        )

        # First submission succeeds
        count1 = await consumer._poll_once()
        assert count1 == 1
        mock_orchestrator.submit_signal.assert_called_once()

        # Second poll: same symbol should be throttled, NOT consumed
        mock_orchestrator.submit_signal.reset_mock()
        count2 = await consumer._poll_once()
        assert count2 == 0
        mock_orchestrator.submit_signal.assert_not_called()

        # Verify NOT marked consumed on second poll
        # Only the first poll should have set consumed
        consumed_calls = [
            c
            for c in mock_redis.hset.call_args_list
            if len(c.args) >= 3 and c.args[1] == "status" and c.args[2] == "consumed"
        ]
        assert len(consumed_calls) == 1, (
            f"Throttled signal should NOT add a second consumed marker. "
            f"Got {len(consumed_calls)} consumed calls: {consumed_calls}"
        )
        # processed set should only have the first signal
        sadd_calls = mock_redis.sadd.call_args_list
        assert len(sadd_calls) == 1, (
            f"Throttled signal should NOT be added to processed set. "
            f"Got {len(sadd_calls)} sadd calls: {sadd_calls}"
        )

    @pytest.mark.asyncio
    async def test_allowed_symbol_still_consumed_after_fix(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Allowed symbols must still be consumed normally after fix."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"bmad:chiseai:signals:2026-02-26:BTC_USDT:{signal_id}"

        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )
        # Ensure BTC/USDT is in the allowed set
        consumer.allowed_symbols = {"BTC/USDT"}

        count = await consumer._poll_once()

        assert count == 1
        mock_orchestrator.submit_signal.assert_called_once()
        # Must be marked consumed
        mock_redis.hset.assert_any_call(redis_key, "status", "consumed")
        mock_redis.sadd.assert_called_with(SignalConsumer.PROCESSED_SET_KEY, signal_id)


class TestStreamBasedConsumption:
    """Tests for XREADGROUP-based stream consumption (S5).

    Verifies that the consumer reads from paper:signals:stream via XREADGROUP,
    acknowledges messages with XACK, and falls back to SCAN for legacy keys.
    """

    @pytest.mark.asyncio
    async def test_ensure_stream_group_creates_group(
        self, mock_orchestrator, mock_redis
    ):
        """Test that _ensure_stream_group creates consumer group on stream."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        await consumer._ensure_stream_group()

        mock_redis.xgroup_create.assert_called_once_with(
            name=SignalConsumer.STREAM_KEY,
            groupname=SignalConsumer.CONSUMER_GROUP,
            id="$",
            mkstream=True,
        )

    @pytest.mark.asyncio
    async def test_ensure_stream_group_handles_busygroup(
        self, mock_orchestrator, mock_redis
    ):
        """Test that BUSYGROUP error is handled gracefully."""
        from redis.exceptions import ResponseError

        mock_redis.xgroup_create.side_effect = ResponseError(
            "BUSYGROUP Consumer Group name already exists"
        )

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        # Should NOT raise
        await consumer._ensure_stream_group()

        mock_redis.xgroup_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_from_stream_returns_messages(
        self, mock_orchestrator, mock_redis, sample_stream_message
    ):
        """Test that _read_from_stream returns parsed messages."""
        message_id, fields = sample_stream_message
        mock_redis.xreadgroup.return_value = [
            (SignalConsumer.STREAM_KEY, [(message_id, fields)])
        ]

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        messages = await consumer._read_from_stream()

        assert len(messages) == 1
        assert messages[0][0] == message_id
        assert messages[0][1] == fields

    @pytest.mark.asyncio
    async def test_read_from_stream_returns_empty_on_no_messages(
        self, mock_orchestrator, mock_redis
    ):
        """Test that _read_from_stream returns empty list when no messages."""
        mock_redis.xreadgroup.return_value = None

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        messages = await consumer._read_from_stream()

        assert messages == []

    @pytest.mark.asyncio
    async def test_ack_stream_message(self, mock_orchestrator, mock_redis):
        """Test that _ack_stream_message calls XACK correctly."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        await consumer._ack_stream_message("1708950000000-0")

        mock_redis.xack.assert_called_once_with(
            SignalConsumer.STREAM_KEY,
            SignalConsumer.CONSUMER_GROUP,
            "1708950000000-0",
        )

    @pytest.mark.asyncio
    async def test_poll_once_processes_stream_messages(
        self, mock_orchestrator, mock_redis, sample_signal_data, sample_stream_message
    ):
        """Test that poll_once processes actionable stream messages."""
        message_id, fields = sample_stream_message
        signal_id = sample_signal_data["signal_id"]

        # Setup stream to return one message
        mock_redis.xreadgroup.return_value = [
            (SignalConsumer.STREAM_KEY, [(message_id, fields)])
        ]
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 1
        mock_orchestrator.submit_signal.assert_called_once()
        # Must acknowledge the stream message
        mock_redis.xack.assert_called_once_with(
            SignalConsumer.STREAM_KEY,
            SignalConsumer.CONSUMER_GROUP,
            message_id,
        )
        # Must add to processed set
        mock_redis.sadd.assert_called_with(SignalConsumer.PROCESSED_SET_KEY, signal_id)

    @pytest.mark.asyncio
    async def test_poll_once_skips_non_actionable_stream_messages(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Test that non-actionable stream messages are acknowledged and skipped."""
        non_actionable_data = {**sample_signal_data, "status": "logged_only"}
        message_id = "1708950000001-0"
        fields = {"data": json.dumps(non_actionable_data)}

        mock_redis.xreadgroup.return_value = [
            (SignalConsumer.STREAM_KEY, [(message_id, fields)])
        ]

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()
        # Non-actionable messages should still be acknowledged to avoid re-reading
        mock_redis.xack.assert_called_once_with(
            SignalConsumer.STREAM_KEY,
            SignalConsumer.CONSUMER_GROUP,
            message_id,
        )

    @pytest.mark.asyncio
    async def test_poll_once_falls_back_to_scan_when_stream_empty(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Test that SCAN fallback works when stream has no messages."""
        signal_id = sample_signal_data["signal_id"]
        redis_key = f"paper:signal:{signal_id}"

        # Stream returns empty
        mock_redis.xreadgroup.return_value = None
        # SCAN returns a legacy key
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=sample_signal_data)
        mock_redis.smembers = AsyncMock(return_value=set())

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 1
        mock_orchestrator.submit_signal.assert_called_once()
        # Legacy path should update status
        mock_redis.hset.assert_called_with(redis_key, "status", "consumed")

    @pytest.mark.asyncio
    async def test_stream_non_allowed_symbol_not_consumed(
        self, mock_orchestrator, mock_redis, sample_signal_data
    ):
        """Non-allowed symbol stream messages must NOT be acknowledged."""
        message_id = "1708950000002-0"
        fields = {"data": json.dumps(sample_signal_data)}

        mock_redis.xreadgroup.return_value = [
            (SignalConsumer.STREAM_KEY, [(message_id, fields)])
        ]

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )
        consumer.allowed_symbols = {"ETH/USDT"}

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()
        # Must NOT ack non-allowed symbol messages (so they can be retried)
        mock_redis.xack.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_ensures_stream_group(self, mock_orchestrator, mock_redis):
        """Test that start() calls _ensure_stream_group."""
        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
        )

        await consumer.start()
        await consumer.stop()

        mock_redis.xgroup_create.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
