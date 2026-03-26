"""Tests for Signal Timestamp Tracker (ST-ICT-023).

Tests the Redis-backed signal timestamp tracking for dynamic weight adjustment.
"""

import pytest
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch, PropertyMock

from ict.weights.signal_timestamp_tracker import (
    SignalTimestampTracker,
    TrackedSignal,
    get_timestamp_tracker,
)


class TestTrackedSignal:
    """Test suite for TrackedSignal dataclass."""

    def test_creation(self):
        """Test creating a TrackedSignal."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=10000.0,
            direction="bullish",
        )

        assert signal.signal_id == "test-123"
        assert signal.signal_type == "cvd"
        assert signal.token == "BTC/USDT"
        assert signal.timeframe == "1H"
        assert signal.timestamp == 10000.0
        assert signal.direction == "bullish"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=10000.0,
            direction="bullish",
            confluence_score=0.75,
        )

        data = signal.to_dict()

        assert data["signal_id"] == "test-123"
        assert data["signal_type"] == "cvd"
        assert data["token"] == "BTC/USDT"
        assert data["timeframe"] == "1H"
        assert data["timestamp"] == 10000.0
        assert data["direction"] == "bullish"
        assert data["confluence_score"] == 0.75

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "signal_id": "test-456",
            "signal_type": "fvg",
            "token": "ETH/USDT",
            "timeframe": "4H",
            "timestamp": 20000.0,
            "direction": "bearish",
            "confluence_score": 0.65,
            "metadata": {"key": "value"},
        }

        signal = TrackedSignal.from_dict(data)

        assert signal.signal_id == "test-456"
        assert signal.signal_type == "fvg"
        assert signal.token == "ETH/USDT"
        assert signal.timeframe == "4H"
        assert signal.timestamp == 20000.0
        assert signal.direction == "bearish"
        assert signal.confluence_score == 0.65
        assert signal.metadata == {"key": "value"}

    def test_get_age_seconds(self):
        """Test age calculation."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=10000.0,
        )

        age = signal.get_age_seconds(current_time=10060.0)
        assert age == 60.0

    def test_get_age_seconds_no_current_time(self):
        """Test age calculation with no current time provided."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=datetime.now(UTC).timestamp() - 120,
        )

        age = signal.get_age_seconds()
        assert 119 <= age <= 121  # Should be approximately 120 seconds


class TestSignalTimestampTracker:
    """Test suite for SignalTimestampTracker."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = SignalTimestampTracker(
            key_prefix="test:signals",
            index_prefix="test:index",
            ttl_seconds=7200,
        )

        assert tracker.key_prefix == "test:signals"
        assert tracker.index_prefix == "test:index"
        assert tracker.ttl_seconds == 7200

    def test_signal_key_generation(self):
        """Test Redis key generation for signals."""
        tracker = SignalTimestampTracker(key_prefix="ict:signals")

        key = tracker._signal_key("test-123")
        assert key == "ict:signals:test-123"

    def test_index_key_generation(self):
        """Test Redis key generation for indices."""
        tracker = SignalTimestampTracker(index_prefix="ict:index")

        key = tracker._index_key("BTC/USDT", "1H")
        assert key == "ict:index:BTC/USDT:1H"

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_track_signal(self, mock_redis):
        """Test tracking a signal."""
        mock_redis.setex = MagicMock(return_value=True)
        mock_redis.sadd = MagicMock(return_value=1)
        mock_redis.expire = MagicMock(return_value=True)

        tracker = SignalTimestampTracker(redis_client=mock_redis)

        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="cvd",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=10000.0,
        )

        result = tracker.track_signal(signal)

        assert result is True
        mock_redis.setex.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signal(self, mock_redis):
        """Test retrieving a tracked signal."""
        mock_redis.get = MagicMock(
            return_value=json.dumps(
                {
                    "signal_id": "test-123",
                    "signal_type": "cvd",
                    "token": "BTC/USDT",
                    "timeframe": "1H",
                    "timestamp": 10000.0,
                    "direction": "bullish",
                }
            )
        )

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        signal = tracker.get_signal("test-123")

        assert signal is not None
        assert signal.signal_id == "test-123"
        assert signal.signal_type == "cvd"
        assert signal.token == "BTC/USDT"

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signal_not_found(self, mock_redis):
        """Test retrieving a non-existent signal."""
        mock_redis.get = MagicMock(return_value=None)

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        signal = tracker.get_signal("nonexistent")

        assert signal is None

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signal_age(self, mock_redis):
        """Test getting signal age."""
        mock_redis.get = MagicMock(
            return_value=json.dumps(
                {
                    "signal_id": "test-123",
                    "signal_type": "cvd",
                    "token": "BTC/USDT",
                    "timeframe": "1H",
                    "timestamp": 10000.0,
                }
            )
        )

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        age = tracker.get_signal_age("test-123", current_time=10060.0)

        assert age == 60.0

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signal_age_not_found(self, mock_redis):
        """Test getting age for non-existent signal."""
        mock_redis.get = MagicMock(return_value=None)

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        age = tracker.get_signal_age("nonexistent")

        assert age is None

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_remove_signal(self, mock_redis):
        """Test removing a tracked signal."""
        mock_redis.get = MagicMock(
            return_value=json.dumps(
                {
                    "signal_id": "test-123",
                    "signal_type": "cvd",
                    "token": "BTC/USDT",
                    "timeframe": "1H",
                    "timestamp": 10000.0,
                }
            )
        )
        mock_redis.srem = MagicMock(return_value=1)
        mock_redis.delete = MagicMock(return_value=1)

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        result = tracker.remove_signal("test-123")

        assert result is True
        mock_redis.srem.assert_called_once()
        mock_redis.delete.assert_called_once()

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_remove_signal_not_found(self, mock_redis):
        """Test removing a non-existent signal."""
        mock_redis.get = MagicMock(return_value=None)

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        result = tracker.remove_signal("nonexistent")

        assert result is False

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signals_for_token_timeframe(self, mock_redis):
        """Test getting all signals for a token/timeframe."""
        mock_redis.srandmember = MagicMock(return_value=["sig-1", "sig-2"])
        mock_redis.get = MagicMock(
            side_effect=[
                json.dumps(
                    {
                        "signal_id": "sig-1",
                        "signal_type": "cvd",
                        "token": "BTC/USDT",
                        "timeframe": "1H",
                        "timestamp": 10100.0,
                    }
                ),
                json.dumps(
                    {
                        "signal_id": "sig-2",
                        "signal_type": "fvg",
                        "token": "BTC/USDT",
                        "timeframe": "1H",
                        "timestamp": 10000.0,
                    }
                ),
            ]
        )

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        signals = tracker.get_signals_for_token_timeframe("BTC/USDT", "1H")

        assert len(signals) == 2
        # Should be sorted by timestamp descending (newest first)
        assert signals[0].signal_id == "sig-1"
        assert signals[1].signal_id == "sig-2"

    @patch("ict.weights.signal_timestamp_tracker.SignalTimestampTracker.redis")
    def test_get_signals_for_token_timeframe_empty(self, mock_redis):
        """Test getting signals when none exist."""
        mock_redis.srandmember = MagicMock(return_value=None)

        tracker = SignalTimestampTracker(redis_client=mock_redis)
        signals = tracker.get_signals_for_token_timeframe("BTC/USDT", "1H")

        assert len(signals) == 0


class TestGetTimestampTracker:
    """Test suite for get_timestamp_tracker singleton."""

    def test_returns_same_instance(self):
        """Test that get_timestamp_tracker returns the same instance."""
        # Reset global
        import ict.weights.signal_timestamp_tracker as module

        module._tracker_instance = None

        tracker1 = get_timestamp_tracker()
        tracker2 = get_timestamp_tracker()

        assert tracker1 is tracker2

    def test_instance_is_correct_type(self):
        """Test that returned instance is SignalTimestampTracker."""
        import ict.weights.signal_timestamp_tracker as module

        module._tracker_instance = None

        tracker = get_timestamp_tracker()
        assert isinstance(tracker, SignalTimestampTracker)


class TestEdgeCases:
    """Test edge cases for signal timestamp tracking."""

    def test_tracked_signal_with_metadata(self):
        """Test TrackedSignal with metadata."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="order_block",
            token="ETH/USDT",
            timeframe="4H",
            timestamp=15000.0,
            metadata={
                "price": 2500.0,
                "volume": 1000000,
                "custom_field": "value",
            },
        )

        data = signal.to_dict()
        assert data["metadata"]["price"] == 2500.0
        assert data["metadata"]["volume"] == 1000000

        restored = TrackedSignal.from_dict(data)
        assert restored.metadata == signal.metadata

    def test_tracked_signal_without_confluence_score(self):
        """Test TrackedSignal without confluence score."""
        signal = TrackedSignal(
            signal_id="test-123",
            signal_type="fvg",
            token="BTC/USDT",
            timeframe="1H",
            timestamp=10000.0,
        )

        assert signal.confluence_score is None

        data = signal.to_dict()
        assert data["confluence_score"] is None

    def test_tracker_handles_redis_error(self):
        """Test that tracker handles Redis errors gracefully."""
        import logging

        tracker = SignalTimestampTracker(redis_client=MagicMock())
        tracker._redis.get = MagicMock(side_effect=Exception("Redis error"))

        signal = tracker.get_signal("test-123")
        assert signal is None

    def test_tracker_handles_invalid_json(self):
        """Test that tracker handles invalid JSON from Redis."""
        tracker = SignalTimestampTracker(redis_client=MagicMock())
        tracker._redis.get = MagicMock(return_value="invalid json{")

        signal = tracker.get_signal("test-123")
        assert signal is None
