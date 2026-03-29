"""
Unit tests for the idempotency_checker module.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from scripts.evaluation.idempotency_checker import (
    IdempotencyChecker,
    CADENCE_TTL_SECONDS,
)


class TestIdempotencyCheckerRenderKey:
    """Tests for the render_key method."""

    def test_render_key_with_date_variable(self):
        """Test rendering key with {date} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key(
                "test_job", "autocog.improvement_cycle.daily:{date}"
            )
            assert (
                result
                == "autocog:job:test_job:autocog.improvement_cycle.daily:2026-03-29"
            )

    def test_render_key_with_hour_variable(self):
        """Test rendering key with {hour} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key(
                "hourly_job", "autocog.belief_consistency.hourly:{date}:{hour}"
            )
            assert (
                result
                == "autocog:job:hourly_job:autocog.belief_consistency.hourly:2026-03-29:14"
            )

    def test_render_key_with_week_variable(self):
        """Test rendering key with {week} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key(
                "weekly_job", "autocog.calibration.weekly:{week}"
            )
            assert (
                result == "autocog:job:weekly_job:autocog.calibration.weekly:2026-W13"
            )

    def test_render_key_with_month_variable(self):
        """Test rendering key with {month} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key(
                "monthly_job", "autocog.reporting.monthly:{month}"
            )
            assert result == "autocog:job:monthly_job:autocog.reporting.monthly:2026-03"

    def test_render_key_with_6h_bucket_variable(self):
        """Test rendering key with {6h_bucket} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key("6h_job", "autocog.eval.6h:{6h_bucket}")
            assert result == "autocog:job:6h_job:autocog.eval.6h:2"

    def test_render_key_with_multiple_variables(self):
        """Test rendering key with multiple variables."""
        checker = IdempotencyChecker(redis_client=MagicMock())

        with patch.object(checker, "_get_time_vars") as mock_time:
            mock_time.return_value = {
                "date": "2026-03-29",
                "hour": 14,
                "week": "2026-W13",
                "month": "2026-03",
                "6h_bucket": 2,
                "year": 2026,
            }

            result = checker.render_key(
                "complex_job",
                "autocog.{date}.{hour}.{6h_bucket}",
            )
            assert result == "autocog:job:complex_job:autocog.2026-03-29.14.2"


class TestIdempotencyCheckerShouldRun:
    """Tests for the should_run method."""

    def test_should_run_returns_true_for_first_run(self):
        """Test that should_run returns True when job hasn't run before."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = False

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("new_job", "autocog.test:{date}", "daily")
        assert result is True
        mock_redis.exists.assert_called_once()

    def test_should_run_returns_false_for_duplicate_run(self):
        """Test that should_run returns False for duplicate run in same window."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = True
        mock_redis.get.return_value = json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "success": True,
                "error": None,
            }
        )

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("existing_job", "autocog.test:{date}", "daily")
        assert result is False

    def test_should_run_returns_true_for_failed_previous_run(self):
        """Test that should_run returns True if previous run failed."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = True
        mock_redis.get.return_value = json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "success": False,
                "error": "Previous error occurred",
            }
        )

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("failed_job", "autocog.test:{date}", "daily")
        assert result is True

    def test_should_run_returns_true_for_expired_key(self):
        """Test that should_run returns True if key expired between exists() and get()."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = True
        mock_redis.get.return_value = None  # Key expired

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("expired_job", "autocog.test:{date}", "daily")
        assert result is True

    def test_should_run_returns_true_when_redis_unavailable(self):
        """Test that should_run returns True (fail-open) when Redis is unavailable."""
        checker = IdempotencyChecker(redis_client=None)

        result = checker.should_run("job", "autocog.test:{date}", "daily")
        assert result is True


class TestIdempotencyCheckerRecordCompletion:
    """Tests for the record_completion method."""

    def test_record_completion_stores_data_correctly(self):
        """Test that record_completion stores correct data in Redis."""
        mock_redis = MagicMock()

        checker = IdempotencyChecker(redis_client=mock_redis)

        with patch.object(checker, "_infer_cadence", return_value="daily"):
            result = checker.record_completion(
                "test_job",
                "autocog.test:{date}",
                success=True,
                error=None,
            )

        assert result is True
        mock_redis.setex.assert_called_once()

        # Verify the call arguments
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        ttl = call_args[0][1]
        data = json.loads(call_args[0][2])

        assert "test_job" in key
        assert ttl == CADENCE_TTL_SECONDS["daily"]
        assert data["success"] is True
        assert data["error"] is None
        assert "timestamp" in data

    def test_record_completion_stores_error_on_failure(self):
        """Test that record_completion stores error message on failure."""
        mock_redis = MagicMock()

        checker = IdempotencyChecker(redis_client=mock_redis)

        with patch.object(checker, "_infer_cadence", return_value="hourly"):
            result = checker.record_completion(
                "failing_job",
                "autocog.test:{hour}",
                success=False,
                error="Something went wrong",
            )

        assert result is True
        call_args = mock_redis.setex.call_args
        data = json.loads(call_args[0][2])

        assert data["success"] is False
        assert data["error"] == "Something went wrong"

    def test_record_completion_returns_false_when_redis_unavailable(self):
        """Test that record_completion returns False when Redis is unavailable."""
        checker = IdempotencyChecker(redis_client=None)

        result = checker.record_completion(
            "test_job",
            "autocog.test:{date}",
            success=True,
        )

        assert result is False


class TestIdempotencyCheckerGetLastRun:
    """Tests for the get_last_run method."""

    def test_get_last_run_returns_timestamp(self):
        """Test that get_last_run returns the timestamp from Redis."""
        mock_redis = MagicMock()
        expected_timestamp = datetime.now(timezone.utc).timestamp()
        mock_redis.get.return_value = json.dumps(
            {
                "timestamp": expected_timestamp,
                "success": True,
                "error": None,
            }
        )

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.get_last_run("test_job", "autocog.test:{date}")
        assert result == expected_timestamp

    def test_get_last_run_returns_none_when_no_record(self):
        """Test that get_last_run returns None when no record exists."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.get_last_run("nonexistent_job", "autocog.test:{date}")
        assert result is None

    def test_get_last_run_returns_none_when_redis_unavailable(self):
        """Test that get_last_run returns None when Redis is unavailable."""
        checker = IdempotencyChecker(redis_client=None)

        result = checker.get_last_run("test_job", "autocog.test:{date}")
        assert result is None


class TestIdempotencyCheckerCadenceInference:
    """Tests for cadence inference."""

    def test_infer_cadence_hourly(self):
        """Test that cadence is inferred as hourly from {hour} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence(
            "autocog.belief_consistency.hourly:{date}:{hour}"
        )
        assert result == "hourly"

    def test_infer_cadence_6hourly(self):
        """Test that cadence is inferred as 6hourly from {6h_bucket} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence("autocog.eval.6h:{6h_bucket}")
        assert result == "6hourly"

    def test_infer_cadence_daily(self):
        """Test that cadence is inferred as daily from {date} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence("autocog.improvement_cycle.daily:{date}")
        assert result == "daily"

    def test_infer_cadence_weekly(self):
        """Test that cadence is inferred as weekly from {week} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence("autocog.calibration.weekly:{week}")
        assert result == "weekly"

    def test_infer_cadence_monthly(self):
        """Test that cadence is inferred as monthly from {month} variable."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence("autocog.reporting.monthly:{month}")
        assert result == "monthly"

    def test_infer_cadence_default(self):
        """Test that unknown patterns default to hourly."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        result = checker._infer_cadence("autocog.unknown.pattern")
        assert result == "hourly"


class TestIdempotencyCheckerTTL:
    """Tests for TTL configuration."""

    def test_ttl_values_are_correct(self):
        """Test that TTL values match expected durations."""
        expected = {
            "hourly": 3600,
            "6hourly": 21600,
            "daily": 86400,
            "weekly": 604800,
            "monthly": 2592000,
        }

        assert CADENCE_TTL_SECONDS == expected

    def test_get_cadence_ttl_hourly(self):
        """Test TTL for hourly cadence."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        assert checker._get_cadence_ttl("hourly") == 3600

    def test_get_cadence_ttl_daily(self):
        """Test TTL for daily cadence."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        assert checker._get_cadence_ttl("daily") == 86400

    def test_get_cadence_ttl_unknown_defaults(self):
        """Test that unknown cadence defaults to hourly TTL."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        assert checker._get_cadence_ttl("unknown") == 3600


class TestIdempotencyCheckerRedisFailure:
    """Tests for Redis failure handling."""

    def test_redis_connection_failure_causes_fail_open(self):
        """Test that Redis connection failure allows job to run."""
        # Mock redis.ConnectionError
        import redis

        with patch("redis.Redis") as mock_redis_class:
            mock_redis_class.return_value.ping.side_effect = redis.ConnectionError(
                "Connection refused"
            )

            checker = IdempotencyChecker()
            assert checker._redis is None

            result = checker.should_run("job", "autocog.test:{date}", "daily")
            assert result is True

    def test_redis_error_on_exists_allows_run(self):
        """Test that Redis error during exists() allows job to run."""
        import redis

        mock_redis = MagicMock()
        mock_redis.exists.side_effect = redis.RedisError("Redis error")

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("job", "autocog.test:{date}", "daily")
        assert result is True

    def test_redis_error_on_get_allows_run(self):
        """Test that Redis error during get() allows job to run."""
        import redis

        mock_redis = MagicMock()
        mock_redis.exists.return_value = True
        mock_redis.get.side_effect = redis.RedisError("Redis error")

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("job", "autocog.test:{date}", "daily")
        assert result is True

    def test_invalid_json_on_get_allows_run(self):
        """Test that invalid JSON in stored data allows job to run."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = True
        mock_redis.get.return_value = "not valid json"

        checker = IdempotencyChecker(redis_client=mock_redis)

        result = checker.should_run("job", "autocog.test:{date}", "daily")
        assert result is True


class TestTimeVariables:
    """Integration-style tests for time variable rendering."""

    def test_date_format_is_yyyy_mm_dd(self):
        """Test that date variable renders in YYYY-MM-DD format."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        time_vars = checker._get_time_vars()

        # Date should match YYYY-MM-DD pattern
        assert len(time_vars["date"]) == 10
        assert time_vars["date"][4] == "-"
        assert time_vars["date"][7] == "-"

    def test_hour_is_0_to_23(self):
        """Test that hour variable is in valid range."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        time_vars = checker._get_time_vars()

        assert 0 <= time_vars["hour"] <= 23

    def test_6h_bucket_is_0_to_3(self):
        """Test that 6h_bucket variable is in valid range."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        time_vars = checker._get_time_vars()

        assert 0 <= time_vars["6h_bucket"] <= 3
        # Verify it matches the hour
        assert time_vars["6h_bucket"] == time_vars["hour"] // 6

    def test_week_format_is_yyyy_wnn(self):
        """Test that week variable renders in YYYY-WNN format."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        time_vars = checker._get_time_vars()

        # Week should match YYYY-WNN pattern
        assert "-W" in time_vars["week"]
        week_part = time_vars["week"].split("-W")[1]
        assert len(week_part) == 2
        assert 1 <= int(week_part) <= 53

    def test_month_format_is_yyyy_mm(self):
        """Test that month variable renders in YYYY-MM format."""
        checker = IdempotencyChecker(redis_client=MagicMock())
        time_vars = checker._get_time_vars()

        # Month should match YYYY-MM pattern
        assert len(time_vars["month"]) == 7
        assert time_vars["month"][4] == "-"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
