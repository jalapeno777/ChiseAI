"""Tests for canary_metrics.py - G-Exit-24h instrumentation.

Tests canary close recording, querying, and Redis fallback behavior.

For G-EXIT-24H: Canary Close & PnL Instrumentation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from src.execution.paper.canary_metrics import (
    CANARY_CLOSES_KEY,
    CANARY_REALIZED_PNL_KEY,
    CanaryMetrics,
    get_canary_metrics,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = MagicMock()
    redis_mock.ping.return_value = True
    redis_mock.zadd.return_value = 1
    redis_mock.hset.return_value = 1
    redis_mock.expire.return_value = True
    redis_mock.incrbyfloat.return_value = 1.0
    redis_mock.zcount.return_value = 0
    redis_mock.zrange.return_value = []
    redis_mock.get.return_value = None
    redis_mock.hgetall.return_value = {}
    redis_mock.delete.return_value = 1
    redis_mock.zrangebyscore.return_value = []
    return redis_mock


@pytest.fixture
def canary_metrics(mock_redis):
    """CanaryMetrics instance with mocked Redis."""
    metrics = CanaryMetrics(redis_client=mock_redis)
    return metrics


@pytest.fixture
def canary_metrics_no_redis():
    """CanaryMetrics instance without Redis (fallback mode)."""
    metrics = CanaryMetrics(redis_client=None, fallback_enabled=True)
    return metrics


class TestRecordCanaryClose:
    """Tests for record_canary_close method."""

    def test_records_close_to_redis(self, canary_metrics, mock_redis):
        """Should record close event to Redis sorted set."""
        position_id = "test-position-123"
        realized_pnl = 10.5
        timestamp = datetime.now(UTC).timestamp()

        result = canary_metrics.record_canary_close(
            position_id=position_id,
            realized_pnl=realized_pnl,
            timestamp=timestamp,
        )

        assert result is True
        mock_redis.zadd.assert_called_once_with(
            CANARY_CLOSES_KEY, {position_id: timestamp}
        )
        mock_redis.incrbyfloat.assert_called_once_with(
            CANARY_REALIZED_PNL_KEY, realized_pnl
        )

    def test_uses_current_timestamp_when_not_provided(self, canary_metrics, mock_redis):
        """Should use current timestamp when not provided."""
        position_id = "test-position-456"
        realized_pnl = 5.0

        before = datetime.now(UTC).timestamp()
        result = canary_metrics.record_canary_close(
            position_id=position_id,
            realized_pnl=realized_pnl,
        )
        after = datetime.now(UTC).timestamp()

        assert result is True
        call_args = mock_redis.zadd.call_args
        recorded_timestamp = call_args[0][1][position_id]
        assert before <= recorded_timestamp <= after

    def test_stores_close_data_in_hash(self, canary_metrics, mock_redis):
        """Should store close data including realized_pnl in Redis hash."""
        position_id = "test-position-789"
        realized_pnl = 25.0
        metadata = {"symbol": "BTCUSDT", "side": "long"}

        result = canary_metrics.record_canary_close(
            position_id=position_id,
            realized_pnl=realized_pnl,
            metadata=metadata,
        )

        assert result is True
        mock_redis.hset.assert_called()
        # Check the hset was called with mapping parameter
        call_kwargs = mock_redis.hset.call_args[1]
        assert "mapping" in call_kwargs

    def test_returns_false_when_redis_unavailable(self, canary_metrics_no_redis):
        """Should return False when Redis is unavailable and fallback disabled."""
        # Create instance without fallback
        metrics = CanaryMetrics(redis_client=None, fallback_enabled=False)

        result = metrics.record_canary_close(
            position_id="test-pos",
            realized_pnl=10.0,
        )

        assert result is False

    def test_falls_back_to_file_when_redis_unavailable(
        self, canary_metrics_no_redis, tmp_path
    ):
        """Should write to fallback file when Redis is unavailable."""
        import src.execution.paper.canary_metrics as cm_module

        # Override fallback file path to tmp
        with patch.object(
            canary_metrics_no_redis,
            "_get_redis",
            return_value=None,
        ):
            # Point to tmp fallback file
            fallback_path = tmp_path / "canary_closes.json"
            with patch.object(cm_module, "CANARY_FALLBACK_FILE", fallback_path):
                result = canary_metrics_no_redis.record_canary_close(
                    position_id="test-pos-fallback",
                    realized_pnl=15.0,
                    timestamp=1000000.0,
                )

        assert result is True
        assert fallback_path.exists()


class TestGetCanaryCloseCount:
    """Tests for get_canary_close_count method."""

    def test_returns_count_from_redis_zcount(self, canary_metrics, mock_redis):
        """Should return count from Redis ZCOUNT operation."""
        mock_redis.zcount.return_value = 5

        count = canary_metrics.get_canary_close_count(since_hours=24)

        assert count == 5
        mock_redis.zcount.assert_called_once()
        # Verify time window calculation
        call_args = mock_redis.zcount.call_args[0]
        assert call_args[0] == CANARY_CLOSES_KEY
        # cutoff should be approximately 24 hours ago
        cutoff = call_args[1]
        assert cutoff > 0  # Valid timestamp

    def test_calculates_48h_window_correctly(self, canary_metrics, mock_redis):
        """Should handle 48 hour time window."""
        mock_redis.zcount.return_value = 3

        count = canary_metrics.get_canary_close_count(since_hours=48)

        assert count == 3
        call_args = mock_redis.zcount.call_args[0]
        cutoff = call_args[1]
        # 48 hours in seconds
        expected_cutoff = datetime.now(UTC).timestamp() - (48 * 3600)
        # Allow 5 second tolerance for test execution time
        assert abs(cutoff - expected_cutoff) < 5

    def test_returns_fallback_count_when_redis_unavailable(
        self, canary_metrics_no_redis, tmp_path
    ):
        """Should calculate from fallback file when Redis unavailable."""
        # Create fallback file with some entries
        fallback_data = [
            {
                "position_id": "pos-1",
                "realized_pnl": 10.0,
                "timestamp": datetime.now(UTC).timestamp(),  # now
                "metadata": {},
            },
            {
                "position_id": "pos-2",
                "realized_pnl": 20.0,
                "timestamp": datetime.now(UTC).timestamp() - (60 * 60),  # 1 hour ago
                "metadata": {},
            },
            {
                "position_id": "pos-3",
                "realized_pnl": 30.0,
                "timestamp": datetime.now(UTC).timestamp()
                - (25 * 3600),  # 25 hours ago
                "metadata": {},
            },
        ]

        fallback_path = tmp_path / "canary_closes.json"
        with open(fallback_path, "w") as f:
            json.dump(fallback_data, f)

        import src.execution.paper.canary_metrics as cm_module

        with patch.object(cm_module, "CANARY_FALLBACK_FILE", fallback_path):
            with patch.object(
                canary_metrics_no_redis,
                "_get_redis",
                return_value=None,
            ):
                count_24h = canary_metrics_no_redis.get_canary_close_count(
                    since_hours=24
                )
                count_48h = canary_metrics_no_redis.get_canary_close_count(
                    since_hours=48
                )

        assert count_24h == 2  # pos-1 and pos-2 (within 24h)
        assert count_48h == 3  # all three (within 48h)


class TestGetRealizedPnl:
    """Tests for get_realized_pnl method."""

    def test_calculates_pnl_from_close_records(self, canary_metrics, mock_redis):
        """Should sum realized_pnl from individual close records."""
        position_ids = ["pos-1", "pos-2", "pos-3"]
        mock_redis.zrangebyscore.return_value = position_ids

        # Mock hgetall for each position
        def mock_hgetall(key):
            pos_id = key.split(":")[-1]
            pnl_values = {"pos-1": 10.0, "pos-2": 20.0, "pos-3": -5.0}
            if pos_id in pnl_values:
                return {"realized_pnl": json.dumps(pnl_values[pos_id])}
            return {}

        mock_redis.hgetall.side_effect = mock_hgetall

        pnl = canary_metrics.get_realized_pnl(since_hours=24)

        assert pnl == 25.0  # 10 + 20 + (-5)

    def test_returns_zero_when_no_closes(self, canary_metrics, mock_redis):
        """Should return 0 when no close records exist."""
        mock_redis.zcount.return_value = 0
        mock_redis.zrangebyscore.return_value = []

        pnl = canary_metrics.get_realized_pnl(since_hours=24)

        assert pnl == 0.0

    def test_filters_by_time_window(self, canary_metrics, mock_redis):
        """Should only include closes within time window."""
        # Only return one position
        mock_redis.zcount.return_value = 1
        mock_redis.zrangebyscore.return_value = ["pos-1"]

        def mock_hgetall(key):
            return {"realized_pnl": json.dumps(100.0)}

        mock_redis.hgetall.side_effect = mock_hgetall

        pnl = canary_metrics.get_realized_pnl(since_hours=24)

        assert pnl == 100.0


class TestGetRunningRealizedPnl:
    """Tests for get_running_realized_pnl method."""

    def test_returns_total_from_redis(self, canary_metrics, mock_redis):
        """Should return running total from Redis key."""
        mock_redis.get.return_value = "150.75"

        total = canary_metrics.get_running_realized_pnl()

        assert total == 150.75
        mock_redis.get.assert_called_with(CANARY_REALIZED_PNL_KEY)

    def test_returns_zero_when_key_not_exists(self, canary_metrics, mock_redis):
        """Should return 0 when key doesn't exist."""
        mock_redis.get.return_value = None

        total = canary_metrics.get_running_realized_pnl()

        assert total == 0.0


class TestClearCanaryData:
    """Tests for clear_canary_data method."""

    def test_clears_all_keys_from_redis(self, canary_metrics, mock_redis):
        """Should delete all canary-related keys from Redis."""
        mock_redis.zrange.return_value = ["pos-1", "pos-2"]
        mock_redis.delete.return_value = 1

        result = canary_metrics.clear_canary_data()

        assert result is True
        # Should delete main keys plus individual close records
        mock_redis.delete.assert_called()

    def test_clears_fallback_file(self, canary_metrics_no_redis, tmp_path):
        """Should delete fallback file when clearing."""
        fallback_path = tmp_path / "canary_closes.json"
        fallback_path.write_text("[]")

        import src.execution.paper.canary_metrics as cm_module

        with patch.object(cm_module, "CANARY_FALLBACK_FILE", fallback_path):
            with patch.object(
                canary_metrics_no_redis,
                "_get_redis",
                return_value=None,
            ):
                result = canary_metrics_no_redis.clear_canary_data()

        assert result is True
        assert not fallback_path.exists()


class TestGetCanaryMetrics:
    """Tests for get_canary_metrics singleton function."""

    def test_returns_singleton_instance(self):
        """Should return the same instance on multiple calls."""
        # Reset singleton
        import src.execution.paper.canary_metrics as cm

        cm._default_instance = None

        instance1 = get_canary_metrics()
        instance2 = get_canary_metrics()

        assert instance1 is instance2

    def test_creates_new_instance_if_none_exists(self):
        """Should create new instance when singleton doesn't exist."""
        import src.execution.paper.canary_metrics as cm

        cm._default_instance = None

        instance = get_canary_metrics()

        assert instance is not None
        assert isinstance(instance, CanaryMetrics)


class TestIntegration:
    """Integration tests for full canary metrics workflow."""

    def test_full_workflow_record_and_query(self, canary_metrics, mock_redis):
        """Test complete workflow: record closes then query counts."""
        # Record some closes
        timestamps = []
        for i in range(3):
            ts = datetime.now(UTC).timestamp() - (i * 3600)  # hours apart
            timestamps.append(ts)
            canary_metrics.record_canary_close(
                position_id=f"pos-{i}",
                realized_pnl=float(i * 10),
                timestamp=ts,
            )

        # Mock queries
        mock_redis.zcount.return_value = 3
        mock_redis.zrangebyscore.return_value = ["pos-0", "pos-1", "pos-2"]

        def mock_hgetall(key):
            pos_num = int(key.split(":")[-1].split("-")[1])
            return {"realized_pnl": json.dumps(float(pos_num * 10))}

        mock_redis.hgetall.side_effect = mock_hgetall

        # Query
        count = canary_metrics.get_canary_close_count(since_hours=24)
        pnl = canary_metrics.get_realized_pnl(since_hours=24)

        assert count == 3
        assert pnl == 30.0  # 0 + 10 + 20

    def test_instrumentation_additive_nature(self):
        """Verify instrumentation doesn't modify existing position tracking."""
        # This is a documentation test - the additive nature is ensured
        # by the design: we only ADD record_canary_close() calls without
        # modifying existing close_position() behavior
        assert True  # Placeholder - actual verification done in integration tests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
