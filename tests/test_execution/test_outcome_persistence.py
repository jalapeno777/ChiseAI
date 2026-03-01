#!/usr/bin/env python3
"""Tests for OutcomePersistence with venue provenance fields.

For ST-VENUE-001: Venue provenance fields implementation
"""

import pytest
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import Mock, MagicMock

from src.ml.models.signal_outcome import (
    SignalOutcome,
    OutcomeType,
    SignalOutcomeStatus,
)
from src.execution.persistence.outcome_persistence import OutcomePersistence


class TestOutcomePersistenceVenueFields:
    """Test venue provenance fields persistence."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.zadd = Mock(return_value=True)
        mock.ping = Mock(return_value=True)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis."""
        return OutcomePersistence(redis_client=mock_redis)

    def test_persist_outcome_includes_venue_fields(self, persistence, mock_redis):
        """Test that persist_outcome includes venue fields in stored data."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            direction="LONG",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("1.0"),
            execution_venue="bybit_demo",
            execution_mode="demo",
            execution_source="bybit_demo_connector",
            venue_metadata={"connector_id": "demo-123", "is_paper_trade": True},
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify key was returned
        assert key is not None
        assert "paper:outcome:" in key
        assert "BTCUSDT" in key

        # Verify Redis set was called with venue fields
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        stored_key = call_args[0][0]
        stored_data_json = call_args[0][1]

        # Parse stored data
        stored_data = json.loads(stored_data_json)

        # Verify venue fields are present
        assert "execution_venue" in stored_data
        assert "execution_mode" in stored_data
        assert "execution_source" in stored_data
        assert "venue_metadata" in stored_data

        # Verify venue field values
        assert stored_data["execution_venue"] == "bybit_demo"
        assert stored_data["execution_mode"] == "demo"
        assert stored_data["execution_source"] == "bybit_demo_connector"
        assert stored_data["venue_metadata"] == {
            "connector_id": "demo-123",
            "is_paper_trade": True,
        }

    def test_persist_outcome_with_empty_venue_fields(self, persistence, mock_redis):
        """Test persistence with empty/default venue fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="ETHUSDT",
            side="Sell",
            direction="SHORT",
            fill_price=Decimal("3000"),
            fill_quantity=Decimal("10.0"),
            # No venue fields set - should use defaults
        )

        # Persist the outcome
        key = persistence.persist_outcome(outcome)

        # Verify key was returned
        assert key is not None

        # Parse stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify venue fields are present with empty defaults
        assert stored_data["execution_venue"] == ""
        assert stored_data["execution_mode"] == ""
        assert stored_data["execution_source"] == ""
        assert stored_data["venue_metadata"] == {}

    def test_persist_outcome_with_correlation_id(self, persistence, mock_redis):
        """Test persistence includes correlation_id and venue fields."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            signal_id=uuid4(),
            order_id="test-order-123",
            symbol="BTCUSDT",
            execution_venue="local_sim",
            execution_mode="testnet",
            execution_source="paper_trading",
        )

        correlation_id = "corr-123-abc"
        key = persistence.persist_outcome(outcome, correlation_id=correlation_id)

        # Parse stored data
        call_args = mock_redis.set.call_args
        stored_data = json.loads(call_args[0][1])

        # Verify both correlation_id and venue fields
        assert stored_data["correlation_id"] == correlation_id
        assert stored_data["execution_venue"] == "local_sim"
        assert stored_data["execution_mode"] == "testnet"
        assert stored_data["execution_source"] == "paper_trading"
        assert "persisted_at" in stored_data

    def test_venue_fields_in_redis_index(self, persistence, mock_redis):
        """Test that venue fields are persisted and index is updated."""
        outcome = SignalOutcome(
            outcome_id=uuid4(),
            symbol="BTCUSDT",
            execution_venue="bybit_demo",
            execution_mode="demo",
        )

        key = persistence.persist_outcome(outcome)

        # Verify index was updated
        mock_redis.zadd.assert_called()
        mock_redis.expire.assert_called()

        # Verify the key pattern
        assert "paper:outcome:" in key


class TestOutcomePersistenceBasic:
    """Test basic OutcomePersistence functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock()
        mock.set = Mock(return_value=True)
        mock.expire = Mock(return_value=True)
        mock.zadd = Mock(return_value=True)
        mock.zrevrange = Mock(return_value=[])
        mock.get = Mock(return_value=None)
        mock.zcard = Mock(return_value=0)
        mock.ping = Mock(return_value=True)
        return mock

    @pytest.fixture
    def persistence(self, mock_redis):
        """Create OutcomePersistence with mock Redis."""
        return OutcomePersistence(redis_client=mock_redis)

    def test_persist_signal(self, persistence, mock_redis):
        """Test signal persistence."""
        # Create a mock signal
        mock_signal = Mock()
        mock_signal.signal_id = "signal-123"
        mock_signal.token = "BTC"
        mock_signal.direction = Mock()
        mock_signal.direction.value = "LONG"
        mock_signal.confidence = 0.85
        mock_signal.confidence_percent = 85.0
        mock_signal.base_score = 0.9
        mock_signal.timeframe = "1h"
        mock_signal.timestamp = datetime.now(UTC)
        mock_signal.generation_latency_ms = 100
        mock_signal.stop_loss = 0.95
        mock_signal.stop_loss_method = "atr"
        mock_signal.metadata = {"source": "test"}

        key = persistence.persist_signal(mock_signal)

        assert key is not None
        assert "paper:signal:" in key
        mock_redis.set.assert_called_once()

    def test_get_recent_outcomes_empty(self, persistence, mock_redis):
        """Test getting recent outcomes when none exist."""
        mock_redis.zrevrange.return_value = []

        outcomes = persistence.get_recent_outcomes(limit=10)

        assert outcomes == []
        mock_redis.zrevrange.assert_called_once()

    def test_get_stats(self, persistence, mock_redis):
        """Test getting persistence stats."""
        mock_redis.zcard.return_value = 5

        stats = persistence.get_stats()

        assert stats["signal_count"] == 5
        assert stats["order_count"] == 5
        assert stats["fill_count"] == 5
        assert stats["outcome_count"] == 5
        assert stats["key_prefix"] == "paper"

    def test_health_check_healthy(self, persistence, mock_redis):
        """Test health check when Redis is healthy."""
        mock_redis.ping.return_value = True
        mock_redis.zcard.return_value = 0

        health = persistence.health_check()

        assert health["healthy"] is True
        assert health["redis_connected"] is True

    def test_health_check_unhealthy(self, persistence, mock_redis):
        """Test health check when Redis is down."""
        mock_redis.ping.side_effect = Exception("Connection refused")

        health = persistence.health_check()

        assert health["healthy"] is False
        assert health["redis_connected"] is False
        assert "error" in health


class TestOutcomePersistenceKeyPatterns:
    """Test Redis key patterns."""

    def test_key_patterns(self):
        """Test that key patterns are correctly defined."""
        persistence = OutcomePersistence()

        # Verify key patterns
        assert "paper:signal:" in persistence.SIGNAL_KEY_PATTERN
        assert "paper:order:" in persistence.ORDER_KEY_PATTERN
        assert "paper:fill:" in persistence.FILL_KEY_PATTERN
        assert "paper:outcome:" in persistence.OUTCOME_KEY_PATTERN

        # Verify index keys
        assert persistence.SIGNAL_INDEX_KEY == "paper:index:signals"
        assert persistence.ORDER_INDEX_KEY == "paper:index:orders"
        assert persistence.FILL_INDEX_KEY == "paper:index:fills"
        assert persistence.OUTCOME_INDEX_KEY == "paper:index:outcomes"

    def test_default_ttl(self):
        """Test default TTL is 7 days."""
        persistence = OutcomePersistence()
        assert persistence.ttl_seconds == 604800  # 7 days in seconds

    def test_custom_ttl(self):
        """Test custom TTL can be set."""
        persistence = OutcomePersistence(ttl_seconds=3600)  # 1 hour
        assert persistence.ttl_seconds == 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
