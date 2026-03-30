"""Tests for ICT Data Collector."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.ict.data_collection.collector import (
    ICTDataCollector,
    OutcomeEvent,
    SignalEvent,
)


class TestICTDataCollector:
    """Tests for ICTDataCollector class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hset = MagicMock(return_value=True)
        mock.expire = MagicMock(return_value=True)
        mock.keys = MagicMock(return_value=[])
        return mock

    @pytest.fixture
    def collector(self, mock_redis):
        """Create collector with mock Redis."""
        return ICTDataCollector(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_start_collection(self, collector):
        """Test starting data collection."""
        assert not collector.is_enabled()
        await collector.start_collection()
        assert collector.is_enabled()

    @pytest.mark.asyncio
    async def test_stop_collection(self, collector):
        """Test stopping data collection."""
        await collector.start_collection()
        assert collector.is_enabled()
        await collector.stop_collection()
        assert not collector.is_enabled()

    @pytest.mark.asyncio
    async def test_collect_signal(self, collector, mock_redis):
        """Test collecting a signal."""
        await collector.start_collection()
        signal_id = await collector.collect_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
            context={"source": "test"},
            experiment_key="ict:exp:ICT-B1:baseline:20260329",
        )
        assert signal_id is not None
        assert len(signal_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_record_outcome(self, collector, mock_redis):
        """Test recording an outcome."""
        await collector.start_collection()
        await collector.record_outcome(
            position_id="pos-123",
            signal_id="sig-456",
            outcome="profit",
            pnl=100.50,
        )

    @pytest.mark.asyncio
    async def test_flush_to_redis(self, collector, mock_redis):
        """Test flushing signals to Redis."""
        await collector.start_collection()
        await collector.collect_signal(
            symbol="ETH/USDT",
            signal_type="entry",
            confidence=0.75,
            experiment_key="ict:exp:ICT-B2:enhanced:20260329",
        )
        await collector.stop_collection()
        assert mock_redis.hset.called

    @pytest.mark.asyncio
    async def test_double_start_warning(self, collector, caplog):
        """Test that double start logs a warning."""
        await collector.start_collection()
        await collector.start_collection()
        assert "already started" in caplog.text

    @pytest.mark.asyncio
    async def test_get_signal_count(self, collector, mock_redis):
        """Test getting signal count from Redis."""
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        count = await collector.get_signal_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_outcome_count(self, collector, mock_redis):
        """Test getting outcome count from Redis."""
        mock_redis.keys.return_value = ["outcome1", "outcome2"]
        count = await collector.get_outcome_count()
        assert count == 2


class TestSignalEvent:
    """Tests for SignalEvent dataclass."""

    def test_signal_event_creation(self):
        """Test creating a signal event."""
        event = SignalEvent(
            signal_id="test-123",
            timestamp=datetime.now(UTC),
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.9,
            context={"test": True},
            experiment_key="ict:exp:ICT-B1:baseline:20260329",
        )
        assert event.signal_id == "test-123"
        assert event.symbol == "BTC/USDT"
        assert event.confidence == 0.9


class TestOutcomeEvent:
    """Tests for OutcomeEvent dataclass."""

    def test_outcome_event_creation(self):
        """Test creating an outcome event."""
        event = OutcomeEvent(
            position_id="pos-123",
            signal_id="sig-456",
            outcome="profit",
            pnl=50.25,
            timestamp=datetime.now(UTC),
        )
        assert event.position_id == "pos-123"
        assert event.outcome == "profit"
        assert event.pnl == 50.25
