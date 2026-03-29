"""Tests for SignalConsumer idempotency and duplicate prevention.

PAPER-001b: Ensure no double-processing, atomic transitions, and restart safety.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.paper.signal_consumer import SignalConsumer


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    orchestrator = MagicMock()
    orchestrator.submit_signal = AsyncMock()
    return orchestrator


def _make_signal_data(signal_id: str | None = None, status: str = "actionable") -> dict:
    """Create sample signal data as stored in Redis."""
    return {
        "signal_id": signal_id or str(uuid.uuid4()),
        "token": "BTC/USDT",
        "direction": "short",
        "confidence": "0.84",
        "timestamp": "2026-02-26T16:25:58.142992+00:00",
        "status": status,
        "timeframe": "1h",
        "mode": "monitor",
    }


class TestSkipNonActionable:
    """Verify non-actionable signals are skipped without processing."""

    @pytest.mark.asyncio
    async def test_status_logged_only_is_skipped(self, mock_orchestrator):
        """Signals with status='logged_only' must not be submitted."""
        signal_data = _make_signal_data(status="logged_only")
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)
        mock_redis.set = AsyncMock(return_value=True)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()
        # Processing lock should NOT have been acquired for non-actionable
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_consumed_is_skipped(self, mock_orchestrator):
        """Signals with status='consumed' must not be submitted."""
        signal_data = _make_signal_data(status="consumed")
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)
        mock_redis.set = AsyncMock(return_value=True)

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
    async def test_status_error_is_skipped(self, mock_orchestrator):
        """Signals with status='error' must not be submitted."""
        signal_data = _make_signal_data(status="error")
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()


class TestAtomicProcessingLock:
    """Verify SETNX-based atomic transition prevents double processing."""

    @pytest.mark.asyncio
    async def test_lock_acquired_on_actionable_signal(self, mock_orchestrator):
        """Processing lock must be acquired before processing an actionable signal."""
        signal_data = _make_signal_data()
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)
        mock_redis.set = AsyncMock(return_value=True)  # NX succeeds
        mock_redis.delete = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 1
        # Verify SET NX EX was called with correct params
        lock_key = SignalConsumer.PROCESSING_KEY_PREFIX.format(signal_id=signal_id)
        mock_redis.set.assert_called_once_with(
            lock_key, "1", nx=True, ex=SignalConsumer.PROCESSING_MARKER_TTL
        )
        # Verify lock was released after processing
        mock_redis.delete.assert_called_with(lock_key)

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_signal(self, mock_orchestrator):
        """If SETNX returns None (lock held), signal must be skipped."""
        signal_data = _make_signal_data()
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)
        mock_redis.set = AsyncMock(return_value=None)  # NX fails - lock held

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
    async def test_lock_released_on_processing_failure(self, mock_orchestrator):
        """Processing lock must be released even if processing fails."""
        signal_data = _make_signal_data()
        signal_id = signal_data["signal_id"]
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)
        mock_redis.set = AsyncMock(return_value=True)  # Lock acquired
        mock_redis.delete = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.hset = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        # Make orchestrator.submit_signal raise
        mock_orchestrator.submit_signal.side_effect = RuntimeError("orchestrator boom")

        count = await consumer._poll_once()

        assert count == 0
        # Lock must still be released
        lock_key = SignalConsumer.PROCESSING_KEY_PREFIX.format(signal_id=signal_id)
        mock_redis.delete.assert_called_with(lock_key)

    @pytest.mark.asyncio
    async def test_acquire_lock_returns_false_when_set_nx_fails(
        self, mock_orchestrator
    ):
        """_acquire_processing_lock returns False when SET NX returns None."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        result = await consumer._acquire_processing_lock("sig-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_lock_returns_true_when_set_nx_succeeds(
        self, mock_orchestrator
    ):
        """_acquire_processing_lock returns True when SET NX succeeds."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        result = await consumer._acquire_processing_lock("sig-123")

        assert result is True
        lock_key = SignalConsumer.PROCESSING_KEY_PREFIX.format(signal_id="sig-123")
        mock_redis.set.assert_called_once_with(
            lock_key, "1", nx=True, ex=SignalConsumer.PROCESSING_MARKER_TTL
        )

    @pytest.mark.asyncio
    async def test_release_lock_deletes_key(self, mock_orchestrator):
        """_release_processing_lock deletes the lock key from Redis."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
        )

        await consumer._release_processing_lock("sig-456")

        lock_key = SignalConsumer.PROCESSING_KEY_PREFIX.format(signal_id="sig-456")
        mock_redis.delete.assert_called_once_with(lock_key)

    @pytest.mark.asyncio
    async def test_no_signal_id_skips_lock_and_processing(self, mock_orchestrator):
        """Signal with empty signal_id must skip lock acquisition entirely."""
        signal_data = _make_signal_data()
        signal_data["signal_id"] = ""  # Explicitly empty after creation
        redis_key = "paper:signal:BTC_USDT:no-id"

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis.type = AsyncMock(return_value="hash")
        mock_redis.hgetall = AsyncMock(return_value=signal_data)

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count = await consumer._poll_once()

        assert count == 0
        mock_orchestrator.submit_signal.assert_not_called()
        # SET should not be called for empty signal_id
        mock_redis.set.assert_not_called()


class TestProcessedSetOnStartup:
    """Verify processed set is loaded on startup and prevents duplicates."""

    @pytest.mark.asyncio
    async def test_processed_set_loaded_on_start(self, mock_orchestrator):
        """Processed signal IDs are loaded from Redis during start()."""
        existing_ids = {"sig-already-done-1", "sig-already-done-2"}

        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=existing_ids)
        mock_redis.hset = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        await consumer.start()

        assert consumer._processed_signals == existing_ids
        mock_redis.smembers.assert_called_with(SignalConsumer.PROCESSED_SET_KEY)

        await consumer.stop()

    @pytest.mark.asyncio
    async def test_restart_prevents_duplicate_processing(self, mock_orchestrator):
        """After restart (new consumer instance), previously processed signals are skipped."""
        signal_id = str(uuid.uuid4())
        signal_data = _make_signal_data(signal_id=signal_id)
        redis_key = f"paper:signal:BTC_USDT:{signal_id}"

        # First consumer processes the signal
        mock_redis_1 = AsyncMock()
        mock_redis_1.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis_1.type = AsyncMock(return_value="hash")
        mock_redis_1.hgetall = AsyncMock(return_value=signal_data)
        mock_redis_1.set = AsyncMock(return_value=True)
        mock_redis_1.delete = AsyncMock()
        mock_redis_1.sadd = AsyncMock()
        mock_redis_1.hset = AsyncMock()
        mock_redis_1.smembers = AsyncMock(return_value=set())  # Nothing processed yet

        consumer_1 = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis_1,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        count_1 = await consumer_1._poll_once()
        assert count_1 == 1
        mock_orchestrator.submit_signal.assert_called_once()

        # Simulate restart: new consumer instance loads processed set from Redis
        mock_orchestrator.reset_mock()
        mock_redis_2 = AsyncMock()
        mock_redis_2.scan = AsyncMock(return_value=(0, [redis_key]))
        mock_redis_2.type = AsyncMock(return_value="hash")
        mock_redis_2.hgetall = AsyncMock(return_value=signal_data)
        mock_redis_2.set = AsyncMock(return_value=True)
        mock_redis_2.delete = AsyncMock()
        mock_redis_2.smembers = AsyncMock(return_value={signal_id})  # Already processed

        consumer_2 = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis_2,
            poll_interval=1.0,
            symbol_throttle_seconds=0.0,
        )

        # Load processed signals (normally done in start())
        await consumer_2._load_processed_signals()

        count_2 = await consumer_2._poll_once()

        assert count_2 == 0
        mock_orchestrator.submit_signal.assert_not_called()
        # SET NX should not have been called since it was in processed set
        mock_redis_2.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_processed_set_empty_on_start_when_redis_fails(
        self, mock_orchestrator
    ):
        """If Redis fails during load, processed set starts empty (graceful degradation)."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.hset = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.close = AsyncMock()

        consumer = SignalConsumer(
            orchestrator=mock_orchestrator,
            redis_client=mock_redis,
            poll_interval=5.0,
        )

        await consumer.start()

        assert consumer._processed_signals == set()

        await consumer.stop()
