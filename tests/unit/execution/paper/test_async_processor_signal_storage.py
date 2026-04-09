"""Tests for AsyncSignalProcessor durable signal storage.

Covers:
- _store_signal() writes to Redis correctly with 7-day TTL
- Recovery on startup finds and returns unprocessed signals
- Idempotency (same signal stored twice is safe)
- Graceful handling of Redis unavailability
- _get_redis_client() lazy initialization
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from signal_generation.async_processor import (
    SIGNAL_KEY_PATTERN,
    SIGNAL_STORAGE_TTL_SECONDS,
    AsyncSignalProcessor,
    EnrichedSignal,
)
from signal_generation.models import (
    Signal,
    SignalDirection,
    SignalStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    signal_id: str | None = None,
    token: str = "BTC/USDT",
    direction: SignalDirection = SignalDirection.LONG,
    confidence: float = 0.85,
    timestamp: datetime | None = None,
) -> Signal:
    """Create a test Signal instance."""
    return Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        token=token,
        direction=direction,
        confidence=confidence,
        base_score=0.8,
        timestamp=timestamp or datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC),
        status=SignalStatus.ACTIONABLE,
        timeframe="1h",
        metadata={"source": "test"},
    )


def _make_enriched_signal(**kwargs) -> EnrichedSignal:
    """Create a test EnrichedSignal wrapping a Signal."""
    signal = _make_signal(**kwargs)
    return EnrichedSignal(
        signal=signal,
        current_price=50000.0,
        orderbook_depth={"bids": 100, "asks": 100},
        risk_params={"max_position": 1.0},
        market_context={"volatility": "low"},
    )


def _make_mock_redis() -> AsyncMock:
    """Create a mock async Redis client with common methods."""
    redis = AsyncMock()
    redis.hset = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)
    redis.scan = AsyncMock(return_value=(0, []))
    redis.sismember = AsyncMock(return_value=False)
    redis.hgetall = AsyncMock(return_value={})
    redis.close = AsyncMock()
    return redis


def _expected_key(signal: Signal) -> str:
    """Compute the expected Redis key for a signal."""
    ts = signal.timestamp.strftime("%Y%m%dT%H%M%S")
    token_safe = signal.token.replace("/", "_")
    return SIGNAL_KEY_PATTERN.format(
        timestamp=ts, token=token_safe, signal_id=signal.signal_id
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Fresh mock Redis client."""
    return _make_mock_redis()


@pytest.fixture
def processor(mock_redis):
    """AsyncSignalProcessor with injected mock Redis."""
    return AsyncSignalProcessor(redis_client=mock_redis)


# ---------------------------------------------------------------------------
# _get_redis_client tests
# ---------------------------------------------------------------------------


class TestGetRedisClient:
    """Tests for lazy Redis client initialization."""

    @pytest.mark.asyncio
    async def test_returns_injected_client(self, processor, mock_redis):
        """When redis_client is injected, return it directly."""
        client = await processor._get_redis_client()
        assert client is mock_redis

    @pytest.mark.asyncio
    async def test_lazy_init_success(self):
        """When no client injected, create one from redis_config."""
        proc = AsyncSignalProcessor()
        fake_client = AsyncMock()
        with patch(
            "execution.paper.redis_config.get_redis_client",
            return_value=fake_client,
        ):
            client = await proc._get_redis_client()
            assert client is fake_client

    @pytest.mark.asyncio
    async def test_lazy_init_failure_returns_none(self):
        """When redis_config import fails, return None and log warning."""
        proc = AsyncSignalProcessor()
        with patch(
            "execution.paper.redis_config.get_redis_client",
            side_effect=ImportError("no redis"),
        ):
            client = await proc._get_redis_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_no_repeated_init_attempts(self):
        """After a failed init, don't retry on subsequent calls."""
        proc = AsyncSignalProcessor()
        with patch(
            "execution.paper.redis_config.get_redis_client",
            side_effect=ImportError("no redis"),
        ) as mock_get:
            await proc._get_redis_client()
            await proc._get_redis_client()
            # Should only call once due to _redis_client_initialized guard
            assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# _store_signal tests
# ---------------------------------------------------------------------------


class TestStoreSignal:
    """Tests for durable signal storage."""

    @pytest.mark.asyncio
    async def test_store_writes_hash_to_redis(self, processor, mock_redis):
        """_store_signal writes signal data as a Redis hash."""
        es = _make_enriched_signal()
        result = await processor._store_signal(es)

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

        # Verify the key matches the expected pattern
        call_args = mock_redis.hset.call_args
        key = call_args[0][0] if call_args[0] else call_args[1].get("name")
        expected = _expected_key(es.signal)
        assert key == expected

    @pytest.mark.asyncio
    async def test_store_uses_7day_ttl(self, processor, mock_redis):
        """Stored signals get a 7-day TTL."""
        es = _make_enriched_signal()
        await processor._store_signal(es)

        mock_redis.expire.assert_called_once()
        ttl_arg = mock_redis.expire.call_args[0][1]
        assert ttl_arg == SIGNAL_STORAGE_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_store_writes_serializable_data(self, processor, mock_redis):
        """Nested dicts are JSON-serialized for Redis hash storage."""
        es = _make_enriched_signal()
        await processor._store_signal(es)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1].get("mapping") or call_args[0][1]

        # Nested dict fields should be JSON strings
        assert isinstance(mapping["signal"], str)
        signal_dict = json.loads(mapping["signal"])
        assert signal_dict["signal_id"] == es.signal.signal_id

    @pytest.mark.asyncio
    async def test_store_idempotent(self, processor, mock_redis):
        """Storing the same signal twice succeeds both times."""
        es = _make_enriched_signal()
        result1 = await processor._store_signal(es)
        result2 = await processor._store_signal(es)

        assert result1 is True
        assert result2 is True
        assert mock_redis.hset.call_count == 2

    @pytest.mark.asyncio
    async def test_store_returns_false_when_redis_unavailable(self):
        """When Redis client is None, _store_signal returns False."""
        proc = AsyncSignalProcessor(redis_client=None)
        # Simulate failed lazy init
        proc._redis_client_initialized = True
        proc._redis_client = None

        es = _make_enriched_signal()
        result = await proc._store_signal(es)
        assert result is False

    @pytest.mark.asyncio
    async def test_store_handles_redis_error(self, processor, mock_redis):
        """Redis write failure is caught and returns False."""
        mock_redis.hset.side_effect = ConnectionError("Redis down")
        es = _make_enriched_signal()
        result = await processor._store_signal(es)
        assert result is False

    @pytest.mark.asyncio
    async def test_store_token_slash_replaced(self, processor, mock_redis):
        """Token slashes are replaced with underscores in Redis key."""
        es = _make_enriched_signal(token="ETH/USDT")
        await processor._store_signal(es)

        call_args = mock_redis.hset.call_args
        key = call_args[0][0]
        assert "ETH_USDT" in key
        assert "/" not in key

    @pytest.mark.asyncio
    async def test_store_none_price_in_mapping(self, processor, mock_redis):
        """None values are stored as empty strings."""
        es = EnrichedSignal(signal=_make_signal(), current_price=None)
        await processor._store_signal(es)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1].get("mapping") or call_args[0][1]
        assert mapping["current_price"] == ""


# ---------------------------------------------------------------------------
# recover_pending_signals tests
# ---------------------------------------------------------------------------


class TestRecoverPendingSignals:
    """Tests for startup recovery of unprocessed signals."""

    @pytest.mark.asyncio
    async def test_no_pending_signals(self, processor, mock_redis):
        """Returns empty list when no unprocessed signals exist."""
        mock_redis.scan.return_value = (0, [])
        recovered = await processor.recover_pending_signals()
        assert recovered == []

    @pytest.mark.asyncio
    async def test_recovers_unprocessed_signals(self, processor, mock_redis):
        """Finds signals not in the processed set and returns them."""
        key = "paper:signal:20260409T120000:BTC_USDT:test-id-123"
        signal_data = {
            "signal": json.dumps(
                {
                    "signal_id": "test-id-123",
                    "token": "BTC/USDT",
                    "confidence": 0.85,
                }
            ),
            "current_price": "50000.0",
        }
        mock_redis.scan.return_value = (0, [key])
        mock_redis.sismember.return_value = False  # Not processed
        mock_redis.hgetall.return_value = signal_data

        recovered = await processor.recover_pending_signals()

        assert len(recovered) == 1
        # Nested JSON should be deserialized
        assert isinstance(recovered[0]["signal"], dict)
        assert recovered[0]["signal"]["signal_id"] == "test-id-123"

    @pytest.mark.asyncio
    async def test_skips_already_processed_signals(self, processor, mock_redis):
        """Signals in the processed set are skipped."""
        key = "paper:signal:20260409T120000:BTC_USDT:test-id-123"
        mock_redis.scan.return_value = (0, [key])
        mock_redis.sismember.return_value = True  # Already processed

        recovered = await processor.recover_pending_signals()
        assert recovered == []
        mock_redis.hgetall.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_multiple_pages(self, processor, mock_redis):
        """Recovers signals across multiple SCAN pages."""
        key1 = "paper:signal:20260409T120000:BTC_USDT:id1"
        key2 = "paper:signal:20260409T120000:ETH_USDT:id2"

        # First scan returns cursor=1 (more pages), second returns cursor=0
        mock_redis.scan.side_effect = [
            (1, [key1]),
            (0, [key2]),
        ]
        mock_redis.sismember.return_value = False
        mock_redis.hgetall.side_effect = [
            {"signal": json.dumps({"signal_id": "id1"})},
            {"signal": json.dumps({"signal_id": "id2"})},
        ]

        recovered = await processor.recover_pending_signals()
        assert len(recovered) == 2
        assert mock_redis.scan.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_redis_error_gracefully(self, processor, mock_redis):
        """Redis errors during recovery are caught, returns empty."""
        mock_redis.scan.side_effect = ConnectionError("Redis down")
        recovered = await processor.recover_pending_signals()
        assert recovered == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_redis_unavailable(self):
        """Returns empty list when Redis client is None."""
        proc = AsyncSignalProcessor(redis_client=None)
        proc._redis_client_initialized = True
        proc._redis_client = None

        recovered = await proc.recover_pending_signals()
        assert recovered == []

    @pytest.mark.asyncio
    async def test_skips_empty_signal_data(self, processor, mock_redis):
        """Keys with empty hash data are skipped."""
        key = "paper:signal:20260409T120000:BTC_USDT:id1"
        mock_redis.scan.return_value = (0, [key])
        mock_redis.sismember.return_value = False
        mock_redis.hgetall.return_value = {}  # Empty

        recovered = await processor.recover_pending_signals()
        assert recovered == []

    @pytest.mark.asyncio
    async def test_handles_corrupt_json_gracefully(self, processor, mock_redis):
        """Corrupt JSON fields are left as-is without crashing."""
        key = "paper:signal:20260409T120000:BTC_USDT:id1"
        mock_redis.scan.return_value = (0, [key])
        mock_redis.sismember.return_value = False
        mock_redis.hgetall.return_value = {
            "signal": "not-valid-json{{{",
            "current_price": "50000.0",
        }

        recovered = await processor.recover_pending_signals()
        assert len(recovered) == 1
        # Corrupt JSON left as raw string
        assert recovered[0]["signal"] == "not-valid-json{{{"
