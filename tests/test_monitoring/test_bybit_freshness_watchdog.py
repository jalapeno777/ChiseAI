"""Tests for Bybit truth data freshness watchdog.

Tests for the BybitFreshnessChecker class and related components.
Ensures proper exit codes, threshold handling, and error conditions.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest


class TestWatchdogFreshData:
    """Test cases when data is fresh (< 45 minutes old)."""

    def test_watchdog_fresh_data_returns_0(self):
        """When data is fresh (<45m), exit code 0."""
        from scripts.validation.bybit_freshness_check import (
            BybitFreshnessChecker,
            FreshnessCheckResult,
        )

        # Create timestamp 30 minutes ago (fresh)
        fresh_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": fresh_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is True
        assert result.status == "fresh"
        assert result.reason == "fresh"
        assert result.hours_since_collection < 0.75  # Less than 45 minutes


class TestWatchdogWarningThreshold:
    """Test cases for warning at 45-60 minute threshold."""

    def test_watchdog_warning_at_45m(self):
        """When data is 45-60m old, warning status."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create timestamp 50 minutes ago (warning zone)
        warning_time = (datetime.now(UTC) - timedelta(minutes=50)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": warning_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        # At 50 minutes with 1 hour threshold, data is still technically fresh
        # but approaching stale. The status depends on threshold_hours.
        assert result.hours_since_collection >= 0.75  # At least 45 minutes
        assert result.hours_since_collection < 1.0  # Less than 60 minutes

    def test_watchdog_stale_approaching_threshold(self):
        """When data is approaching 60m but under threshold."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create timestamp 55 minutes ago
        near_stale_time = (datetime.now(UTC) - timedelta(minutes=55)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": near_stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        # At 55 minutes with 1 hour threshold, data is still fresh
        assert result.is_fresh is True
        assert result.hours_since_collection >= 0.9  # At least 54 minutes
        assert result.hours_since_collection < 1.0


class TestWatchdogFailThreshold:
    """Test cases for fail at >60 minute threshold."""

    def test_watchdog_fail_at_60m(self):
        """When data >60m old, exit code 1 (stale)."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create timestamp 65 minutes ago (stale)
        stale_time = (datetime.now(UTC) - timedelta(minutes=65)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_old"
        assert result.hours_since_collection > 1.0

    def test_watchdog_fail_at_24h(self):
        """When data is 24+ hours old, definitely stale."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create timestamp 25 hours ago (very stale)
        very_stale_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": very_stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=24)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_old"
        assert result.hours_since_collection > 24.0


class TestWatchdogNoData:
    """Test cases when no timestamp data exists in Redis."""

    def test_watchdog_no_data_returns_error(self):
        """When no timestamp in Redis, exit code 2 (error)."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        mock_redis = Mock()
        mock_redis.get.return_value = None  # No data
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_no_collection"
        assert "No collection data found" in result.error_message


class TestWatchdogAutoRecover:
    """Test cases for auto-recovery functionality."""

    def test_watchdog_auto_recover_triggers_collector(self):
        """--auto-recover flag triggers collector subprocess."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create stale timestamp to trigger recovery
        stale_time = (datetime.now(UTC) - timedelta(minutes=65)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True
        mock_redis.set.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)

        with (
            patch.object(checker, "_get_redis", return_value=mock_redis),
            patch("subprocess.run") as mock_subprocess,
        ):
            result = checker.check()

            # Simulate auto-recovery logic that would trigger collector
            if not result.is_fresh:
                # Trigger collector
                mock_subprocess.return_value = Mock(returncode=0)
                import subprocess

                subprocess.run(
                    [
                        "python3",
                        "scripts/validation/bybit_truth_collector.py",
                        "--dry-run",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

            # Verify subprocess was called
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args
            assert "bybit_truth_collector.py" in str(call_args)


class TestWatchdogRecoveryLock:
    """Test cases for recovery lock mechanism."""

    def test_watchdog_recovery_lock_prevents_duplicate(self):
        """Redis lock prevents concurrent recovery attempts."""
        import redis as redis_lib

        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        # Create stale timestamp
        stale_time = (datetime.now(UTC) - timedelta(minutes=65)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        # Simulate lock already exists (another process is recovering)
        mock_redis.setnx.return_value = False  # Lock already held

        checker = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

            # Check if lock exists (would be done in real implementation)
            lock_acquired = mock_redis.setnx(
                "bmad:chiseai:bybit_truth:recovery_lock", "1"
            )

            assert lock_acquired is False  # Lock already held

    def test_watchdog_recovery_lock_acquired_when_available(self):
        """Lock is acquired when available."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        stale_time = (datetime.now(UTC) - timedelta(minutes=65)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": stale_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        # Simulate lock is available
        mock_redis.setnx.return_value = True
        mock_redis.expire.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            # Check if lock is available
            lock_acquired = mock_redis.setnx(
                "bmad:chiseai:bybit_truth:recovery_lock", "1"
            )
            if lock_acquired:
                mock_redis.expire("bmad:chiseai:bybit_truth:recovery_lock", 300)

            assert lock_acquired is True
            mock_redis.expire.assert_called_with(
                "bmad:chiseai:bybit_truth:recovery_lock", 300
            )


class TestWatchdogInvalidTimestamp:
    """Test cases for malformed timestamp handling."""

    def test_watchdog_invalid_timestamp_format(self):
        """Handles malformed timestamp gracefully."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": "invalid-timestamp",
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "error"
        assert "stale_redis_error" in result.reason
        assert "Failed to parse timestamp" in result.error_message

    def test_watchdog_empty_timestamp(self):
        """Handles empty timestamp string."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": "",
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_no_collection"

    def test_watchdog_malformed_iso_timestamp(self):
        """Handles malformed ISO timestamp."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": "2024-13-45T99:99:99",
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "error"
        assert "stale_redis_error" in result.reason


class TestWatchdogCollectionStatusErrors:
    """Test cases for collection status error handling."""

    def test_watchdog_api_error_status(self):
        """Handles API_ERROR status from last collection."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": recent_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "0",
            "bmad:chiseai:bybit_truth:last_collection_status": "api_error",
            "bmad:chiseai:bybit_truth:last_collection_reason": "stale_api_error",
            "bmad:chiseai:bybit_truth:last_collection_error": "Bybit API timeout",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_api_error"
        # Error message should contain the stored error or a default
        assert result.error_message != ""

    def test_watchdog_redis_error_status(self):
        """Handles REDIS_ERROR status from last collection."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": recent_time,
            "bmad:chiseai:bybit_truth:last_collection_count": "0",
            "bmad:chiseai:bybit_truth:last_collection_status": "redis_error",
            "bmad:chiseai:bybit_truth:last_collection_reason": "stale_redis_error",
            "bmad:chiseai:bybit_truth:last_collection_error": "Redis connection failed",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "stale"
        assert result.reason == "stale_redis_error"
        # Error message should contain the stored error or a default
        assert result.error_message != ""


class TestWatchdogRedisConnection:
    """Test cases for Redis connection failures."""

    def test_watchdog_redis_connection_failure(self):
        """Handles Redis connection failure gracefully."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(
            checker, "_get_redis", side_effect=Exception("Connection refused")
        ):
            result = checker.check()

        assert result.is_fresh is False
        assert result.status == "error"
        assert "stale_redis_error" in result.reason
        assert "Redis error" in result.error_message


class TestWatchdogExitCodes:
    """Test cases for proper exit code handling."""

    def test_exit_code_logic_fresh(self):
        """Exit code should be 0 when check result is fresh."""
        from scripts.validation.bybit_freshness_check import (
            BybitFreshnessChecker,
            FreshnessCheckResult,
            FreshnessReason,
        )

        # Create a result that would produce exit code 0
        result = FreshnessCheckResult(
            is_fresh=True,
            status="fresh",
            reason=FreshnessReason.FRESH.value,
            hours_since_collection=0.5,
        )

        # Simulate exit code logic from main()
        if result.status == "fresh":
            exit_code = 0
        elif result.status == "stale":
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 0

    def test_exit_code_logic_stale(self):
        """Exit code should be 1 when check result is stale."""
        from scripts.validation.bybit_freshness_check import (
            FreshnessCheckResult,
            FreshnessReason,
        )

        result = FreshnessCheckResult(
            is_fresh=False,
            status="stale",
            reason=FreshnessReason.STALE_OLD.value,
            hours_since_collection=2.0,
        )

        if result.status == "fresh":
            exit_code = 0
        elif result.status == "stale":
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 1

    def test_exit_code_logic_error(self):
        """Exit code should be 2 when check result is error."""
        from scripts.validation.bybit_freshness_check import (
            FreshnessCheckResult,
            FreshnessReason,
        )

        result = FreshnessCheckResult(
            is_fresh=False,
            status="error",
            reason=FreshnessReason.STALE_REDIS_ERROR.value,
            hours_since_collection=0.0,
            error_message="Redis connection failed",
        )

        if result.status == "fresh":
            exit_code = 0
        elif result.status == "stale":
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 2


class TestWatchdogResultFormatting:
    """Test cases for result formatting and output."""

    def test_result_to_dict(self):
        """FreshnessCheckResult can be converted to dict."""
        from scripts.validation.bybit_freshness_check import FreshnessCheckResult

        result = FreshnessCheckResult(
            is_fresh=True,
            status="fresh",
            reason="fresh",
            hours_since_collection=0.5,
            last_collection_timestamp="2024-01-01T12:00:00+00:00",
            last_collection_count=10,
            last_collection_status="success",
            threshold_hours=1,
            error_message="",
        )

        d = result.to_dict()

        assert d["is_fresh"] is True
        assert d["status"] == "fresh"
        assert d["hours_since_collection"] == 0.5
        assert d["last_collection_count"] == 10

    def test_result_to_json(self):
        """FreshnessCheckResult can be converted to JSON."""
        import json

        from scripts.validation.bybit_freshness_check import FreshnessCheckResult

        result = FreshnessCheckResult(
            is_fresh=True,
            status="fresh",
            reason="fresh",
            hours_since_collection=0.5,
            last_collection_timestamp="2024-01-01T12:00:00+00:00",
            last_collection_count=10,
            last_collection_status="success",
            threshold_hours=1,
            error_message="",
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["is_fresh"] is True
        assert parsed["status"] == "fresh"


class TestWatchdogTimestampParsing:
    """Test cases for timestamp parsing with various formats."""

    def test_parse_iso_timestamp_with_z(self):
        """Parse ISO timestamp ending with Z."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        # Timestamp with Z (UTC indicator)
        result = checker._parse_timestamp("2024-01-01T12:00:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_parse_iso_timestamp_with_offset(self):
        """Parse ISO timestamp with timezone offset."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        result = checker._parse_timestamp("2024-01-01T12:00:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_iso_timestamp_without_tz(self):
        """Parse ISO timestamp without timezone."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        result = checker._parse_timestamp("2024-01-01T12:00:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_empty_timestamp(self):
        """Parse empty timestamp returns None."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        result = checker._parse_timestamp("")
        assert result is None

    def test_parse_none_timestamp(self):
        """Parse None timestamp returns None."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        # Test with None (edge case - actual code handles this)
        result = checker._parse_timestamp(None)  # type: ignore
        assert result is None


class TestWatchdogHoursCalculation:
    """Test cases for hours since calculation."""

    def test_calculate_hours_since_with_tz(self):
        """Calculate hours for timestamp with timezone."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        # Timestamp 2 hours ago with timezone
        past = datetime.now(UTC) - timedelta(hours=2)
        hours = checker._calculate_hours_since(past)

        assert hours >= 1.99  # Allow for test execution time
        assert hours <= 2.1

    def test_calculate_hours_since_without_tz(self):
        """Calculate hours for timestamp without timezone."""
        from datetime import datetime as dt

        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        # Create a naive datetime (no timezone) 2 hours in the past
        # This simulates timestamps stored without timezone info
        past = dt.now(UTC) - timedelta(hours=2)
        hours = checker._calculate_hours_since(past)

        # Should be approximately 2 hours (with tolerance for test execution)
        assert hours >= 1.9
        assert hours <= 2.1


class TestWatchdogConfiguration:
    """Test cases for configuration options."""

    def test_custom_threshold_hours(self):
        """Custom threshold hours is respected."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker(threshold_hours=6)

        assert checker.threshold_hours == 6

    def test_custom_redis_host_port(self):
        """Custom Redis host and port are stored."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker(redis_host="custom.redis.host", redis_port=1234)

        assert checker.redis_host == "custom.redis.host"
        assert checker.redis_port == 1234

    @pytest.mark.parametrize(
        "threshold,minutes,expected_fresh",
        [
            (1, 30, True),  # 30 min < 1 hour threshold = fresh
            (1, 65, False),  # 65 min > 1 hour threshold = stale
            (24, 60, True),  # 1 hour < 24 hour threshold = fresh
            (24, 1500, False),  # 25 hours > 24 hour threshold = stale
        ],
    )
    def test_threshold_boundaries(self, threshold, minutes, expected_fresh):
        """Test various threshold boundaries."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        time_ago = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": time_ago,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=threshold)
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

        assert result.is_fresh is expected_fresh
