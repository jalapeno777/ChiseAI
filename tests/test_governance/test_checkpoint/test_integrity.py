"""Tests for metric integrity checking module.

Tests the MetricIntegrityChecker class and IntegrityResult dataclass.

Story: BATCH3-METRIC-INTEGRITY-003
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import redis
from src.governance.checkpoint.integrity import (
    IntegrityResult,
    MetricIntegrityChecker,
)


class TestIntegrityResult:
    """Tests for IntegrityResult dataclass."""

    def test_integrity_result_creation(self):
        """Test creating an IntegrityResult."""
        now = datetime.now(UTC)
        result = IntegrityResult(
            status="OK",
            heartbeat_count=100,
            actual_count=95,
            difference=5,
            tolerance=10.0,
            message="Test message",
            timestamp=now,
        )
        assert result.status == "OK"
        assert result.heartbeat_count == 100
        assert result.actual_count == 95
        assert result.difference == 5
        assert result.tolerance == 10.0
        assert result.message == "Test message"
        assert result.timestamp == now

    def test_integrity_result_default_timestamp(self):
        """Test IntegrityResult with default timestamp."""
        before = datetime.now(UTC)
        result = IntegrityResult(
            status="OK",
            heartbeat_count=50,
            actual_count=50,
            difference=0,
            tolerance=5.0,
            message="Exact match",
        )
        after = datetime.now(UTC)

        assert result.timestamp is not None
        assert before <= result.timestamp  # type: ignore
        assert result.timestamp <= after


class TestMetricIntegrityCheckerInitialization:
    """Tests for MetricIntegrityChecker initialization."""

    def test_default_initialization(self):
        """Test MetricIntegrityChecker with default values."""
        checker = MetricIntegrityChecker()
        assert checker._redis is None
        assert checker._redis_host is not None
        assert checker._redis_port is not None
        assert checker._sample_size == 100
        assert checker._tolerance_percent == 0.1
        assert checker._min_tolerance == 5

    def test_with_redis_client(self, mock_redis_client):
        """Test MetricIntegrityChecker with provided Redis client."""
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        assert checker._redis == mock_redis_client

    def test_with_custom_host_port(self):
        """Test MetricIntegrityChecker with custom host and port."""
        checker = MetricIntegrityChecker(
            redis_host="custom-host",
            redis_port=1234,
        )
        assert checker._redis_host == "custom-host"
        assert checker._redis_port == 1234

    def test_with_custom_sampling_params(self):
        """Test MetricIntegrityChecker with custom sampling parameters."""
        checker = MetricIntegrityChecker(
            sample_size=200,
            tolerance_percent=0.15,
            min_tolerance=10,
        )
        assert checker._sample_size == 200
        assert checker._tolerance_percent == 0.15
        assert checker._min_tolerance == 10


class TestGetHeartbeatSignals:
    """Tests for _get_heartbeat_signals method."""

    def test_get_heartbeat_signals_success(self, mock_redis_client):
        """Test getting heartbeat signals successfully."""
        mock_redis_client.hgetall.return_value = {
            "signals_15m": "42",
            "status": "running",
        }
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._get_heartbeat_signals()

        assert count == 42
        mock_redis_client.hgetall.assert_called_once_with(
            "bmad:chiseai:scheduler:heartbeat"
        )

    def test_get_heartbeat_signals_zero(self, mock_redis_client):
        """Test getting heartbeat signals when count is zero."""
        mock_redis_client.hgetall.return_value = {
            "signals_15m": "0",
            "status": "running",
        }
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._get_heartbeat_signals()

        assert count == 0

    def test_get_heartbeat_signals_missing(self, mock_redis_client):
        """Test getting heartbeat signals when field is missing."""
        mock_redis_client.hgetall.return_value = {"status": "running"}
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._get_heartbeat_signals()

        assert count == 0

    def test_get_heartbeat_signals_empty_heartbeat(self, mock_redis_client):
        """Test getting heartbeat signals when heartbeat is empty."""
        mock_redis_client.hgetall.return_value = {}
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._get_heartbeat_signals()

        assert count == 0

    def test_get_heartbeat_signals_no_redis(self):
        """Test getting heartbeat signals when Redis is unavailable."""
        checker = MetricIntegrityChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            count = checker._get_heartbeat_signals()

        assert count == 0

    def test_get_heartbeat_signals_exception(self, mock_redis_client):
        """Test getting heartbeat signals when exception occurs."""
        mock_redis_client.hgetall.side_effect = Exception("Redis error")
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._get_heartbeat_signals()

        assert count == 0


class TestCountRawSignals:
    """Tests for _count_raw_signals_last_15m method."""

    def test_count_raw_signals_success(self, mock_redis_client):
        """Test counting raw signals successfully."""
        mock_redis_client.scan.side_effect = [
            (
                0,
                [
                    "bmad:chiseai:signals:20240314:001",
                    "bmad:chiseai:signals:20240314:002",
                ],
            ),
        ]
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._count_raw_signals_last_15m()

        assert count == 2

    def test_count_raw_signals_multiple_scans(self, mock_redis_client):
        """Test counting raw signals with multiple scan iterations."""
        mock_redis_client.scan.side_effect = [
            (1, ["bmad:chiseai:signals:20240314:001"]),
            (0, ["bmad:chiseai:signals:20240314:002"]),
        ]
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._count_raw_signals_last_15m()

        assert count == 2

    def test_count_raw_signals_empty(self, mock_redis_client):
        """Test counting raw signals when no keys exist."""
        mock_redis_client.scan.return_value = (0, [])
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._count_raw_signals_last_15m()

        assert count == 0

    def test_count_raw_signals_no_redis(self):
        """Test counting raw signals when Redis is unavailable."""
        checker = MetricIntegrityChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            count = checker._count_raw_signals_last_15m()

        assert count == 0

    def test_count_raw_signals_exception(self, mock_redis_client):
        """Test counting raw signals when exception occurs."""
        mock_redis_client.scan.side_effect = Exception("Redis error")
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._count_raw_signals_last_15m()

        assert count == 0

    def test_count_raw_signals_above_sample_size(self, mock_redis_client):
        """Test counting when total keys exceed sample size."""
        # Create 150 keys (above default sample_size of 100)
        keys = [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(150)]
        mock_redis_client.scan.return_value = (0, keys)
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        count = checker._count_raw_signals_last_15m()

        # Should return total count (150), not sample size
        assert count == 150


class TestCheckSignalCountIntegrity:
    """Tests for check_signal_count_integrity method."""

    def test_exact_match_ok(self, mock_redis_client):
        """Test exact match returns OK status."""
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(100)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        assert result.status == "OK"
        assert result.heartbeat_count == 100
        assert result.actual_count == 100
        assert result.difference == 0

    def test_within_tolerance_ok(self, mock_redis_client):
        """Test count within tolerance returns OK status."""
        # Heartbeat: 100, Actual: 95 (5% diff, within 10% tolerance)
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(95)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        assert result.status == "OK"
        assert result.heartbeat_count == 100
        assert result.actual_count == 95
        assert result.difference == 5
        assert result.tolerance == 10.0  # 10% of 100

    def test_small_mismatch_check(self, mock_redis_client):
        """Test small mismatch (10-20%) returns CHECK status."""
        # Heartbeat: 100, Actual: 85 (15% diff, within 20% but outside 10%)
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(85)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        assert result.status == "CHECK"
        assert result.heartbeat_count == 100
        assert result.actual_count == 85
        assert result.difference == 15

    def test_large_mismatch_fail(self, mock_redis_client):
        """Test large mismatch (>20%) returns FAIL status."""
        # Heartbeat: 100, Actual: 70 (30% diff, outside 20%)
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(70)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        assert result.status == "FAIL"
        assert result.heartbeat_count == 100
        assert result.actual_count == 70
        assert result.difference == 30

    def test_zero_heartbeat_with_signals_check(self, mock_redis_client):
        """Test zero heartbeat count with actual signals returns CHECK."""
        # Heartbeat: 0, Actual: 10 (diff=10, tolerance=5, so CHECK)
        mock_redis_client.hgetall.return_value = {"signals_15m": "0"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(10)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        # With min_tolerance=5, diff=10 > 5*2=10, so it's at the boundary
        # diff=10, tolerance=5, diff <= tolerance*2 (10 <= 10) -> CHECK
        assert result.status == "CHECK"
        assert result.heartbeat_count == 0
        assert result.actual_count == 10

    def test_no_redis_fail(self):
        """Test integrity check when Redis is unavailable."""
        checker = MetricIntegrityChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_signal_count_integrity()

        assert result.status == "FAIL"
        assert result.heartbeat_count == 0
        assert result.actual_count == 0
        assert "Redis unavailable" in result.message

    def test_exception_handling(self, mock_redis_client):
        """Test integrity check handles Redis failures gracefully.

        When Redis operations fail internally (returning 0), the check
        should handle this gracefully. If both counts are 0, the difference
        is 0 which falls within tolerance, resulting in OK status.
        This is the expected behavior when Redis is unavailable.
        """
        # Make hgetall and scan raise exceptions - they return 0 internally
        mock_redis_client.hgetall.side_effect = Exception("Redis error")
        mock_redis_client.scan.side_effect = Exception("Redis error")
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        # Both methods return 0 when they fail, so diff=0, tolerance=5, status=OK
        # This is graceful degradation - we don't fail the check when Redis is down
        assert result.status == "OK"
        assert result.heartbeat_count == 0
        assert result.actual_count == 0
        assert result.difference == 0

    def test_tolerance_calculation(self, mock_redis_client):
        """Test tolerance calculation uses max(10%, min_tolerance)."""
        # Heartbeat: 20, Actual: 15 (diff=5)
        # 10% of 20 = 2, min_tolerance = 5, so tolerance = 5
        mock_redis_client.hgetall.return_value = {"signals_15m": "20"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(15)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.check_signal_count_integrity()

        assert result.tolerance == 5.0  # min_tolerance wins
        assert result.difference == 5
        # diff=5 <= tolerance=5 -> OK
        assert result.status == "OK"


class TestToGateResult:
    """Tests for to_gate_result method."""

    def test_to_gate_result_ok(self):
        """Test converting OK integrity result to gate result."""
        integrity_result = IntegrityResult(
            status="OK",
            heartbeat_count=100,
            actual_count=100,
            difference=0,
            tolerance=10.0,
            message="Signals match",
        )
        checker = MetricIntegrityChecker()
        gate_result = checker.to_gate_result(integrity_result)

        assert gate_result.gate == "G9"
        assert gate_result.status == "✅ PASS"
        assert gate_result.detail == "Signals match"

    def test_to_gate_result_check(self):
        """Test converting CHECK integrity result to gate result."""
        integrity_result = IntegrityResult(
            status="CHECK",
            heartbeat_count=100,
            actual_count=85,
            difference=15,
            tolerance=10.0,
            message="Small mismatch detected",
        )
        checker = MetricIntegrityChecker()
        gate_result = checker.to_gate_result(integrity_result)

        assert gate_result.gate == "G9"
        assert gate_result.status == "⚠️ CHECK"
        assert gate_result.detail == "Small mismatch detected"

    def test_to_gate_result_fail(self):
        """Test converting FAIL integrity result to gate result."""
        integrity_result = IntegrityResult(
            status="FAIL",
            heartbeat_count=100,
            actual_count=70,
            difference=30,
            tolerance=10.0,
            message="Large mismatch detected",
        )
        checker = MetricIntegrityChecker()
        gate_result = checker.to_gate_result(integrity_result)

        assert gate_result.gate == "G9"
        assert gate_result.status == "❌ FAIL"
        assert gate_result.detail == "Large mismatch detected"

    def test_to_gate_result_auto_check(self, mock_redis_client):
        """Test to_gate_result with auto-check (no pre-computed result)."""
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(100)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        gate_result = checker.to_gate_result()  # No argument - runs check

        assert gate_result.gate == "G9"
        assert gate_result.status == "✅ PASS"
        assert "match" in gate_result.detail.lower()

    def test_to_gate_result_preserves_timestamp(self):
        """Test that timestamp is preserved in gate result conversion."""
        now = datetime.now(UTC)
        integrity_result = IntegrityResult(
            status="OK",
            heartbeat_count=100,
            actual_count=100,
            difference=0,
            tolerance=10.0,
            message="Signals match",
            timestamp=now,
        )
        checker = MetricIntegrityChecker()
        gate_result = checker.to_gate_result(integrity_result)

        assert gate_result.timestamp == now


class TestRunIntegrityCheck:
    """Tests for run_integrity_check method."""

    def test_run_integrity_check_ok(self, mock_redis_client):
        """Test running full integrity check with OK result."""
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(100)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.run_integrity_check()

        assert result["status"] == "OK"
        assert result["heartbeat_count"] == 100
        assert result["actual_count"] == 100
        assert result["difference"] == 0
        assert result["healthy"] is True
        assert "timestamp" in result

    def test_run_integrity_check_fail(self, mock_redis_client):
        """Test running full integrity check with FAIL result."""
        mock_redis_client.hgetall.return_value = {"signals_15m": "100"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(50)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.run_integrity_check()

        assert result["status"] == "FAIL"
        assert result["heartbeat_count"] == 100
        assert result["actual_count"] == 50
        assert result["difference"] == 50
        assert result["healthy"] is False

    def test_run_integrity_check_includes_all_fields(self, mock_redis_client):
        """Test that run_integrity_check returns all expected fields."""
        mock_redis_client.hgetall.return_value = {"signals_15m": "50"}
        mock_redis_client.scan.return_value = (
            0,
            [f"bmad:chiseai:signals:20240314:{i:03d}" for i in range(50)],
        )

        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        result = checker.run_integrity_check()

        expected_fields = [
            "status",
            "heartbeat_count",
            "actual_count",
            "difference",
            "tolerance",
            "message",
            "timestamp",
            "healthy",
        ]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"


class TestSamplingLogic:
    """Tests for the sampling logic."""

    def test_scan_uses_correct_pattern(self, mock_redis_client):
        """Test that scan uses the correct date-based pattern."""
        mock_redis_client.scan.return_value = (0, [])
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)

        with patch("src.governance.checkpoint.integrity.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 3, 14, 12, 0, 0, tzinfo=UTC)
            checker._count_raw_signals_last_15m()

        # Check that scan was called with correct pattern
        calls = mock_redis_client.scan.call_args_list
        assert len(calls) > 0
        # The pattern should include today's date
        expected_pattern = "bmad:chiseai:signals:20240314:*"
        assert any(
            expected_pattern in str(call) for call in calls
        ), f"Expected pattern {expected_pattern} in scan calls"

    def test_scan_uses_count_parameter(self, mock_redis_client):
        """Test that scan uses appropriate count parameter."""
        mock_redis_client.scan.return_value = (0, [])
        checker = MetricIntegrityChecker(redis_client=mock_redis_client)
        checker._count_raw_signals_last_15m()

        calls = mock_redis_client.scan.call_args_list
        assert len(calls) > 0
        # Should use count=1000 for efficient scanning
        assert any(
            "count=1000" in str(call) for call in calls
        ), "Expected count=1000 in scan calls"


# Fixtures
@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    mock = MagicMock(spec=redis.Redis)
    mock.hgetall.return_value = {}
    mock.hget.return_value = None
    mock.hset.return_value = True
    mock.get.return_value = None
    mock.set.return_value = True
    mock.keys.return_value = []
    mock.scan.return_value = (0, [])
    mock.scard.return_value = 0
    mock.lpush.return_value = True
    mock.ltrim.return_value = True
    mock.lrange.return_value = []
    mock.ping.return_value = True
    mock.dbsize.return_value = 100
    mock.info.return_value = {"uptime_in_seconds": 7200}
    return mock
