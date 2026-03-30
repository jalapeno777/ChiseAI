"""Tests for ICT signal rate monitor."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.ict.dry_run.signal_rate_monitor import (
    SignalRateBounds,
    SignalRateMonitor,
    SignalRateSnapshot,
)


class TestSignalRateBounds:
    """Test signal rate bounds checking."""

    def test_default_bounds(self):
        """Test default bounds are reasonable."""
        bounds = SignalRateBounds()
        assert bounds.min_signals_per_hour == 0
        assert bounds.max_signals_per_hour == 50
        assert bounds.min_signals_per_day == 10
        assert bounds.max_signals_per_day == 500

    def test_check_hourly_rate_valid(self):
        """Test hourly rate within bounds passes."""
        bounds = SignalRateBounds()
        valid, msg = bounds.check_hourly_rate(25)
        assert valid is True
        assert "within bounds" in msg

    def test_check_hourly_rate_too_high(self):
        """Test hourly rate exceeding max fails."""
        bounds = SignalRateBounds()
        valid, msg = bounds.check_hourly_rate(100)
        assert valid is False
        assert "exceeds maximum" in msg

    def test_check_hourly_rate_too_low(self):
        """Test hourly rate below min fails."""
        bounds = SignalRateBounds(min_signals_per_hour=5)
        valid, msg = bounds.check_hourly_rate(2)
        assert valid is False
        assert "below minimum" in msg

    def test_check_daily_rate_valid(self):
        """Test daily rate within bounds passes."""
        bounds = SignalRateBounds()
        valid, msg = bounds.check_daily_rate(250)
        assert valid is True
        assert "within bounds" in msg

    def test_check_daily_rate_too_high(self):
        """Test daily rate exceeding max fails."""
        bounds = SignalRateBounds()
        valid, msg = bounds.check_daily_rate(600)
        assert valid is False
        assert "exceeds maximum" in msg

    def test_check_daily_rate_too_low(self):
        """Test daily rate below min fails."""
        bounds = SignalRateBounds(min_signals_per_day=50)
        valid, msg = bounds.check_daily_rate(5)
        assert valid is False
        assert "below minimum" in msg


class TestSignalRateSnapshot:
    """Test signal rate snapshot."""

    def test_to_dict(self):
        """Test snapshot serialization to dict."""
        snapshot = SignalRateSnapshot(
            timestamp=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            hour_count=10,
            day_count=100,
            symbol_counts={"BTC/USDT": 50, "ETH/USDT": 50},
        )
        data = snapshot.to_dict()
        assert data["hour_count"] == 10
        assert data["day_count"] == 100
        assert data["symbol_counts"]["BTC/USDT"] == 50


class TestSignalRateMonitor:
    """Test signal rate monitor functionality."""

    def _create_mock_redis(self):
        """Create a mock Redis client with async methods."""
        mock = MagicMock()
        mock._data = {}
        mock._hash_data = {}

        async def mock_set(key, value, ex=None):
            mock._data[key] = value
            return True

        async def mock_get(key):
            return mock._data.get(key)

        async def mock_hincrby(key, field, amount):
            if key not in mock._hash_data:
                mock._hash_data[key] = {}
            if field not in mock._hash_data[key]:
                mock._hash_data[key][field] = 0
            mock._hash_data[key][field] += amount
            return mock._hash_data[key][field]

        async def mock_hgetall(key):
            return mock._hash_data.get(key, {})

        async def mock_hget(key, field):
            return mock._hash_data.get(key, {}).get(field)

        async def mock_expire(key, ttl):
            return True

        async def mock_keys(pattern):
            # Simple pattern matching for cleanup
            prefix = pattern.replace("*", "")
            return [k for k in mock._data if k.startswith(prefix)]

        async def mock_delete(*keys):
            for key in keys:
                mock._data.pop(key, None)
                mock._hash_data.pop(key, None)
            return len(keys)

        async def mock_close():
            pass

        # Pipeline mock (pipeline() is sync in redis-py async, returns obj directly)
        pipe_mock = MagicMock()
        pipe_commands = []

        def pipe_hincrby(key, field, amount):
            pipe_commands.append(("hincrby", key, field, amount))

        def pipe_expire(key, ttl):
            pipe_commands.append(("expire", key, ttl))

        async def pipe_execute():
            for cmd in pipe_commands:
                if cmd[0] == "hincrby":
                    await mock_hincrby(cmd[1], cmd[2], cmd[3])
                elif cmd[0] == "expire":
                    await mock_expire(cmd[1], cmd[2])
            pipe_commands.clear()
            return [True] * len(pipe_commands) if pipe_commands else []

        pipe_mock.hincrby = pipe_hincrby
        pipe_mock.expire = pipe_expire
        pipe_mock.execute = pipe_execute

        def mock_pipeline():
            return pipe_mock

        mock.set = mock_set
        mock.get = mock_get
        mock.hincrby = mock_hincrby
        mock.hgetall = mock_hgetall
        mock.hget = mock_hget
        mock.expire = mock_expire
        mock.keys = mock_keys
        mock.delete = mock_delete
        mock.close = mock_close
        mock.pipeline = mock_pipeline

        return mock

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return self._create_mock_redis()

    @pytest.fixture
    def monitor(self, mock_redis):
        """Create monitor instance with mock Redis."""
        return SignalRateMonitor(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_start_24h_dry_run(self, monitor, mock_redis):
        """Test starting dry-run records start time."""
        await monitor.start_24h_dry_run()

        start_time = await mock_redis.get("ict:dry_run:signals:start_time")
        assert start_time is not None

    @pytest.mark.asyncio
    async def test_record_signal(self, monitor, mock_redis):
        """Test recording signals increments counters."""
        await monitor.start_24h_dry_run()

        await monitor.record_signal("BTC/USDT", "BOS")
        await monitor.record_signal("BTC/USDT", "CHOCH")
        await monitor.record_signal("ETH/USDT", "FVG")

        snapshot = await monitor.get_current_snapshot()
        assert snapshot.hour_count == 3
        assert snapshot.symbol_counts["BTC/USDT"] == 2
        assert snapshot.symbol_counts["ETH/USDT"] == 1

    @pytest.mark.asyncio
    async def test_get_current_snapshot(self, monitor):
        """Test getting current snapshot returns correct structure."""
        await monitor.start_24h_dry_run()
        await monitor.record_signal("BTC/USDT", "BOS")

        snapshot = await monitor.get_current_snapshot()
        assert isinstance(snapshot, SignalRateSnapshot)
        assert snapshot.hour_count >= 1
        assert snapshot.day_count >= 1
        assert "BTC/USDT" in snapshot.symbol_counts

    @pytest.mark.asyncio
    async def test_check_bounds_valid(self, monitor):
        """Test bounds checking with valid rates."""
        await monitor.start_24h_dry_run()
        await monitor.record_signal("BTC/USDT", "BOS")

        result = await monitor.check_bounds()
        assert "hourly" in result
        assert "daily" in result
        assert "overall_valid" in result

    @pytest.mark.asyncio
    async def test_generate_report(self, monitor):
        """Test report generation."""
        await monitor.start_24h_dry_run()
        await monitor.record_signal("BTC/USDT", "BOS")

        report = await monitor.generate_report()
        assert report["dry_run_type"] == "ICT_Signal_Rate_24h"
        assert "start_time" in report
        assert "end_time" in report
        assert "snapshot" in report
        assert "bounds_check" in report
        assert "expected_bounds" in report
        assert report["status"] in ("PASS", "FAIL")

    @pytest.mark.asyncio
    async def test_signal_type_tracking(self, monitor, mock_redis):
        """Test that signal types are tracked separately."""
        await monitor.start_24h_dry_run()

        await monitor.record_signal("BTC/USDT", "BOS")
        await monitor.record_signal("BTC/USDT", "BOS")
        await monitor.record_signal("BTC/USDT", "CHOCH")

        # Check type tracking in Redis
        now = datetime.now(UTC)
        hour_key = now.strftime("%Y%m%d%H")

        bos_count = await mock_redis.hget(f"ict:dry_run:signals:type:{hour_key}", "BOS")
        chch_count = await mock_redis.hget(
            f"ict:dry_run:signals:type:{hour_key}", "CHOCH"
        )

        assert bos_count == 2
        assert chch_count == 1

    @pytest.mark.asyncio
    async def test_check_bounds_hourly_exceeded(self, monitor):
        """Test bounds checking detects hourly rate exceeded."""
        bounds = SignalRateBounds(max_signals_per_hour=1)
        monitor = SignalRateMonitor(
            redis_client=self._create_mock_redis(), bounds=bounds
        )

        await monitor.start_24h_dry_run()
        await monitor.record_signal("BTC/USDT", "BOS")
        await monitor.record_signal("ETH/USDT", "BOS")  # 2 in hour - exceeds max of 1

        result = await monitor.check_bounds()
        assert result["hourly"]["valid"] is False
        assert "exceeds maximum" in result["hourly"]["message"]

    @pytest.mark.asyncio
    async def test_check_bounds_daily_exceeded(self, monitor):
        """Test bounds checking detects daily rate exceeded."""
        bounds = SignalRateBounds(min_signals_per_day=0, max_signals_per_day=1)
        monitor = SignalRateMonitor(
            redis_client=self._create_mock_redis(), bounds=bounds
        )

        await monitor.start_24h_dry_run()
        await monitor.record_signal("BTC/USDT", "BOS")
        await monitor.record_signal("ETH/USDT", "BOS")  # 2 in day - exceeds max of 1

        result = await monitor.check_bounds()
        assert result["daily"]["valid"] is False
        assert "exceeds maximum" in result["daily"]["message"]

    @pytest.mark.asyncio
    async def test_check_bounds_daily_below_minimum(self, monitor):
        """Test bounds checking detects daily rate below minimum."""
        bounds = SignalRateBounds(min_signals_per_day=50)
        monitor = SignalRateMonitor(
            redis_client=self._create_mock_redis(), bounds=bounds
        )

        await monitor.start_24h_dry_run()
        # Only 1 signal - below min of 50

        result = await monitor.check_bounds()
        assert result["daily"]["valid"] is False
        assert "below minimum" in result["daily"]["message"]

    @pytest.mark.asyncio
    async def test_multiple_symbols(self, monitor):
        """Test tracking multiple symbols correctly."""
        await monitor.start_24h_dry_run()

        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT"]
        for symbol in symbols:
            await monitor.record_signal(symbol, "BOS")

        snapshot = await monitor.get_current_snapshot()
        assert snapshot.hour_count == 4
        assert snapshot.day_count == 4
        for symbol in symbols:
            assert symbol in snapshot.symbol_counts
            assert snapshot.symbol_counts[symbol] == 1
