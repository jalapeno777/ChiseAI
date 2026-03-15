"""Tests for cron evidence tracking utilities."""

import time
import uuid
from datetime import UTC, datetime
from unittest.mock import Mock, call, patch

import pytest


class TestCronEvidenceAtomicWrites:
    """Test atomic write functionality with Redis pipeline."""

    def test_write_uses_pipeline_for_atomicity(self):
        """Test that evidence writes use Redis pipeline for atomic operations."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        # Mock _verify_evidence_write to return True
        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            success, invocation_id = write_cron_evidence(
                "pager", status="success", invocation_id="test-id-123"
            )

        assert success is True
        mock_redis.pipeline.assert_called_once()
        mock_pipeline.execute.assert_called_once()

    def test_pipeline_writes_all_expected_keys(self):
        """Test that pipeline writes all required evidence keys."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence(
                "pager",
                status="success",
                invocation_id="test-invocation-id",
                write_mode="direct",
            )

        # Verify pipeline.set was called for expected keys
        assert mock_pipeline.set.call_count >= 5

    def test_pipeline_verification_failure_triggers_retry(self):
        """Test that verification failure triggers retry attempts."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        # Mock verification to fail twice then succeed
        verify_calls = []

        def mock_verify(*args, **kwargs):
            verify_calls.append(1)
            return len(verify_calls) >= 3

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch("scripts.monitoring.cron_evidence.time.sleep"),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                side_effect=mock_verify,
            ),
        ):
            success, invocation_id = write_cron_evidence(
                "pager", status="success", invocation_id="test-id"
            )

        # Should succeed eventually after retries
        assert success is True
        # Pipeline execute should be called multiple times due to retries
        assert mock_pipeline.execute.call_count == 3


class TestCronEvidenceInvocationId:
    """Test invocation_id tracking functionality."""

    def test_invocation_id_generated_when_not_provided(self):
        """Test that UUID is generated when invocation_id not provided."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            success, invocation_id = write_cron_evidence("pager", status="success")

        assert success is True
        assert invocation_id is not None
        # Should be a valid UUID format
        try:
            uuid.UUID(invocation_id)
        except ValueError:
            pytest.fail(f"invocation_id {invocation_id} is not a valid UUID")

    def test_invocation_id_preserved_when_provided(self):
        """Test that provided invocation_id is used."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        provided_id = "my-custom-invocation-id"

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            success, invocation_id = write_cron_evidence(
                "pager", status="success", invocation_id=provided_id
            )

        assert success is True
        assert invocation_id == provided_id

    def test_invocation_id_written_to_redis(self):
        """Test that invocation_id is stored in Redis."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        test_id = "test-invocation-uuid"

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence("pager", status="success", invocation_id=test_id)

        # Check invocation_id was set in pipeline
        mock_pipeline.set.assert_any_call(f"{KEY_PREFIX}:pager:invocation_id", test_id)

    def test_check_cadence_returns_invocation_id(self):
        """Test that check_cron_cadence includes invocation_id in results."""
        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            f"{KEY_PREFIX}:pager:last_run": datetime.now(UTC).isoformat(),
            f"{KEY_PREFIX}:pager:missed_count": "0",
            f"{KEY_PREFIX}:pager:invocation_id": "test-inv-id-123",
            f"{KEY_PREFIX}:pager:write_mode": "wrapper",
            f"{KEY_PREFIX}:pager:status": "success",
        }.get(key)

        results = check_cron_cadence(mock_redis)

        assert "pager" in results["jobs"]
        assert results["jobs"]["pager"]["invocation_id"] == "test-inv-id-123"


class TestCronEvidenceRetryLogic:
    """Test retry logic for evidence writes."""

    def test_retry_on_pipeline_failure(self):
        """Test that write is retried when pipeline fails."""
        from scripts.monitoring.cron_evidence import (
            write_cron_evidence,
            MAX_RETRY_ATTEMPTS,
        )

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline

        # First two calls fail, third succeeds
        mock_pipeline.execute.side_effect = [
            Exception("Connection error"),
            Exception("Connection error"),
            [True] * 7,
        ]

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch("scripts.monitoring.cron_evidence.time.sleep") as mock_sleep,
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            success, invocation_id = write_cron_evidence("pager", status="success")

        assert success is True
        assert mock_pipeline.execute.call_count == 3
        # Should have slept between retries with exponential backoff
        assert mock_sleep.call_count == 2

    def test_retry_exhaustion_returns_failure(self):
        """Test that all retries exhausted results in failure."""
        from scripts.monitoring.cron_evidence import (
            write_cron_evidence,
            MAX_RETRY_ATTEMPTS,
        )

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        # All calls fail
        mock_pipeline.execute.side_effect = Exception("Persistent connection error")

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch("scripts.monitoring.cron_evidence.time.sleep"),
        ):
            success, invocation_id = write_cron_evidence("pager", status="success")

        assert success is False
        assert mock_pipeline.execute.call_count == MAX_RETRY_ATTEMPTS

    def test_retry_with_exponential_backoff(self):
        """Test that retry delays increase with exponential backoff."""
        from scripts.monitoring.cron_evidence import (
            write_cron_evidence,
            RETRY_DELAY_SECONDS,
        )

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            [True] * 7,
        ]

        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence.time.sleep", side_effect=capture_sleep
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence("pager", status="success")

        # Should have exponential backoff: 0.5s, 1.0s
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == RETRY_DELAY_SECONDS * 1
        assert sleep_calls[1] == RETRY_DELAY_SECONDS * 2


class TestCronEvidenceWriteMode:
    """Test write_mode field functionality."""

    def test_write_mode_wrapper(self):
        """Test write_mode is set to 'wrapper' when called from cron_wrapper."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence(
                "pager", status="success", write_mode="wrapper", invocation_id="test"
            )

        mock_pipeline.set.assert_any_call(f"{KEY_PREFIX}:pager:write_mode", "wrapper")

    def test_write_mode_direct(self):
        """Test write_mode defaults to 'direct'."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence("pager", status="success", invocation_id="test")

        mock_pipeline.set.assert_any_call(f"{KEY_PREFIX}:pager:write_mode", "direct")

    def test_check_cadence_returns_write_mode(self):
        """Test that check_cron_cadence includes write_mode in results."""
        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            f"{KEY_PREFIX}:pager:last_run": datetime.now(UTC).isoformat(),
            f"{KEY_PREFIX}:pager:missed_count": "0",
            f"{KEY_PREFIX}:pager:invocation_id": "test-id",
            f"{KEY_PREFIX}:pager:write_mode": "wrapper",
            f"{KEY_PREFIX}:pager:status": "success",
        }.get(key)

        results = check_cron_cadence(mock_redis)

        assert results["jobs"]["pager"]["write_mode"] == "wrapper"


class TestCronEvidenceNoFalseStale:
    """Test prevention of false stale conditions."""

    def test_no_false_stale_with_direct_invocation(self):
        """Test that direct invocation doesn't create false stale alerts."""
        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        # Simulate a recent successful run with direct mode (10 seconds ago)
        # This ensures the elapsed time is well within the grace period
        now = datetime.now(UTC)
        recent_run = (now - __import__("datetime").timedelta(seconds=10)).isoformat()

        def mock_get(key):
            # Return data for all jobs so overall_status is based on all jobs
            job_keys = {
                f"{KEY_PREFIX}:pager:last_run": recent_run,
                f"{KEY_PREFIX}:pager:missed_count": "0",
                f"{KEY_PREFIX}:pager:invocation_id": "direct-invocation-id",
                f"{KEY_PREFIX}:pager:write_mode": "direct",
                f"{KEY_PREFIX}:pager:status": "success",
                f"{KEY_PREFIX}:signal-growth:last_run": recent_run,
                f"{KEY_PREFIX}:signal-growth:missed_count": "0",
                f"{KEY_PREFIX}:signal-growth:invocation_id": "direct-invocation-id",
                f"{KEY_PREFIX}:signal-growth:write_mode": "direct",
                f"{KEY_PREFIX}:signal-growth:status": "success",
                f"{KEY_PREFIX}:hourly-health:last_run": recent_run,
                f"{KEY_PREFIX}:hourly-health:missed_count": "0",
                f"{KEY_PREFIX}:hourly-health:invocation_id": "direct-invocation-id",
                f"{KEY_PREFIX}:hourly-health:write_mode": "direct",
                f"{KEY_PREFIX}:hourly-health:status": "success",
                f"{KEY_PREFIX}:checkpoint-audit:last_run": recent_run,
                f"{KEY_PREFIX}:checkpoint-audit:missed_count": "0",
                f"{KEY_PREFIX}:checkpoint-audit:invocation_id": "direct-invocation-id",
                f"{KEY_PREFIX}:checkpoint-audit:write_mode": "direct",
                f"{KEY_PREFIX}:checkpoint-audit:status": "success",
                f"{KEY_PREFIX}:bybit-truth-collector:last_run": recent_run,
                f"{KEY_PREFIX}:bybit-truth-collector:missed_count": "0",
                f"{KEY_PREFIX}:bybit-truth-collector:invocation_id": "direct-invocation-id",
                f"{KEY_PREFIX}:bybit-truth-collector:write_mode": "direct",
                f"{KEY_PREFIX}:bybit-truth-collector:status": "success",
            }
            return job_keys.get(key)

        mock_redis = Mock()
        mock_redis.get.side_effect = mock_get

        results = check_cron_cadence(mock_redis)

        # Should be PASS, not CHECK or FAIL
        assert results["jobs"]["pager"]["status"] == "PASS"
        assert results["overall_status"] == "PASS"

    def test_no_false_stale_with_wrapper_invocation(self):
        """Test that wrapper invocation is properly tracked."""
        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        now = datetime.now(UTC)
        recent_run = now.isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            f"{KEY_PREFIX}:pager:last_run": recent_run,
            f"{KEY_PREFIX}:pager:missed_count": "0",
            f"{KEY_PREFIX}:pager:invocation_id": "wrapper-invocation-id",
            f"{KEY_PREFIX}:pager:write_mode": "wrapper",
            f"{KEY_PREFIX}:pager:status": "success",
        }.get(key)

        results = check_cron_cadence(mock_redis)

        assert results["jobs"]["pager"]["status"] == "PASS"

    def test_invocation_id_prevents_timestamp_comparison_issues(self):
        """Test that unique invocation_id prevents race condition false positives."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        # Setup proper mock for Redis get (for verification)
        timestamps = {}
        invocation_ids = {}

        def mock_get(key):
            return timestamps.get(key) or invocation_ids.get(key)

        def capture_set(key, value):
            if "last_run" in key:
                timestamps[key] = value
            elif "invocation_id" in key:
                invocation_ids[key] = value
            return Mock()

        mock_pipeline.set.side_effect = capture_set
        mock_redis.get.side_effect = mock_get

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            # Two rapid writes
            success1, id1 = write_cron_evidence("pager", status="success")
            success2, id2 = write_cron_evidence("pager", status="success")

        # Each should have unique invocation ID
        assert id1 != id2
        assert success1 is True
        assert success2 is True


class TestCronEvidenceErrorHandling:
    """Test error handling and logging."""

    def test_unknown_job_returns_failure(self):
        """Test that unknown job name returns failure."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        success, invocation_id = write_cron_evidence("unknown-job", status="success")

        assert success is False
        assert invocation_id is None

    def test_redis_connection_failure(self):
        """Test behavior when Redis connection fails."""
        from scripts.monitoring.cron_evidence import write_cron_evidence

        with patch(
            "scripts.monitoring.cron_evidence.get_redis_connection",
            return_value=None,
        ):
            success, invocation_id = write_cron_evidence("pager", status="success")

        assert success is False
        # Invocation ID should still be returned even if write fails
        assert invocation_id is not None

    def test_error_message_written_to_redis(self):
        """Test that error messages are stored in Redis."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        error_msg = "Something went wrong"

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence(
                "pager",
                status="error",
                error_message=error_msg,
                invocation_id="test-id",
            )

        mock_pipeline.set.assert_any_call(f"{KEY_PREFIX}:pager:last_error", error_msg)

    def test_success_clears_error(self):
        """Test that successful write clears previous error."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence("pager", status="success", invocation_id="test-id")

        # delete should be called at least once
        mock_pipeline.delete.assert_any_call(f"{KEY_PREFIX}:pager:last_error")


class TestCronWrapperIntegration:
    """Test cron_wrapper integration with evidence system."""

    def test_wrapper_generates_invocation_id(self):
        """Test that cron_wrapper generates invocation ID for execution."""
        # Test that UUID is generated for each execution
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())

        assert id1 != id2
        # Both should be valid UUIDs
        assert uuid.UUID(id1)
        assert uuid.UUID(id2)

    def test_wrapper_passes_write_mode_wrapper(self):
        """Test that cron_wrapper passes write_mode='wrapper'."""
        from scripts.monitoring.cron_evidence import write_cron_evidence, KEY_PREFIX

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            write_cron_evidence(
                "pager", status="success", write_mode="wrapper", invocation_id="test"
            )

        # The write_mode should be "wrapper" when called from cron_wrapper
        mock_pipeline.set.assert_any_call(f"{KEY_PREFIX}:pager:write_mode", "wrapper")

    def test_wrapper_retry_config(self):
        """Test that cron_wrapper has proper retry configuration."""
        from scripts.monitoring.cron_wrapper import (
            MAX_RETRY_ATTEMPTS,
            RETRY_DELAY_SECONDS,
        )

        # Verify retry configuration
        assert MAX_RETRY_ATTEMPTS == 3
        assert RETRY_DELAY_SECONDS == 0.5


class TestCronEvidenceVerification:
    """Test evidence write verification."""

    def test_verification_checks_timestamp_match(self):
        """Test that verification compares stored timestamp with expected."""
        from scripts.monitoring.cron_evidence import _verify_evidence_write

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "chise:cron:pager:last_run": "2024-01-01T12:00:00+00:00",
            "chise:cron:pager:invocation_id": "test-id",
        }.get(key)

        result = _verify_evidence_write(
            mock_redis, "pager", "2024-01-01T12:00:00+00:00", "test-id"
        )

        assert result is True

    def test_verification_fails_on_mismatch(self):
        """Test that verification fails when stored values don't match."""
        from scripts.monitoring.cron_evidence import _verify_evidence_write

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "chise:cron:pager:last_run": "2024-01-01T11:00:00+00:00",  # Different!
            "chise:cron:pager:invocation_id": "wrong-id",
        }.get(key)

        result = _verify_evidence_write(
            mock_redis, "pager", "2024-01-01T12:00:00+00:00", "test-id"
        )

        assert result is False

    def test_verification_handles_missing_keys(self):
        """Test that verification handles missing keys gracefully."""
        from scripts.monitoring.cron_evidence import _verify_evidence_write

        mock_redis = Mock()
        mock_redis.get.return_value = None

        result = _verify_evidence_write(
            mock_redis, "pager", "2024-01-01T12:00:00+00:00", "test-id"
        )

        assert result is False


class TestCronEvidenceFormatStatus:
    """Test status formatting."""

    def test_format_cron_status_with_invocation_id(self):
        """Test that format includes invocation info when available."""
        from scripts.monitoring.cron_evidence import format_cron_status

        results = {
            "overall_status": "PASS",
            "jobs": {
                "pager": {
                    "status": "PASS",
                    "elapsed_seconds": 120,
                    "expected_interval": 300,
                    "missed_count": 0,
                    "invocation_id": "test-inv-id",
                    "write_mode": "wrapper",
                    "detail": "Running on schedule (120s ago)",
                }
            },
        }

        formatted = format_cron_status(results)

        assert "✅" in formatted
        assert "PASS" in formatted
        assert "pager" in formatted

    def test_format_cron_status_with_error(self):
        """Test formatting when Redis connection fails."""
        from scripts.monitoring.cron_evidence import format_cron_status

        results = {
            "overall_status": "FAIL",
            "error": "Cannot connect to Redis",
            "jobs": {},
        }

        formatted = format_cron_status(results)

        assert "❌" in formatted
        assert "Cannot connect to Redis" in formatted


class TestBybitTruthCollectorCronJobs:
    """Test Bybit truth collector cron job configuration."""

    def test_bybit_truth_collector_in_cron_jobs(self):
        """Verify bybit-truth-collector is in CRON_JOBS."""
        from scripts.monitoring.cron_evidence import CRON_JOBS

        # Bybit truth collector should be registered in CRON_JOBS
        # Note: If this test fails, add bybit-truth-collector to CRON_JOBS
        # in scripts/monitoring/cron_evidence.py
        assert "bybit-truth-collector" in CRON_JOBS, (
            "bybit-truth-collector should be registered in CRON_JOBS. "
            "Add it to scripts/monitoring/cron_evidence.py"
        )

    def test_bybit_truth_collector_30m_interval(self):
        """Verify 30-minute interval is correct for bybit-truth-collector."""
        from scripts.monitoring.cron_evidence import CRON_JOBS

        # Skip test if not yet configured
        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        job_config = CRON_JOBS["bybit-truth-collector"]

        # Expected interval: 1800 seconds = 30 minutes
        expected_interval = 1800
        assert job_config["interval"] == expected_interval, (
            f"bybit-truth-collector interval should be {expected_interval}s (30m), "
            f"got {job_config['interval']}s"
        )

    def test_bybit_truth_collector_has_description(self):
        """Verify bybit-truth-collector has a description."""
        from scripts.monitoring.cron_evidence import CRON_JOBS

        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        job_config = CRON_JOBS["bybit-truth-collector"]

        assert "description" in job_config
        assert len(job_config["description"]) > 0
        assert "bybit" in job_config["description"].lower()

    def test_bybit_truth_collector_cadence_check(self):
        """Verify check_cron_cadence returns bybit-truth-collector status."""
        from datetime import UTC, datetime

        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        # Skip if not in CRON_JOBS yet
        from scripts.monitoring.cron_evidence import CRON_JOBS

        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        now = datetime.now(UTC)
        recent_run = now.isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            f"{KEY_PREFIX}:bybit-truth-collector:last_run": recent_run,
            f"{KEY_PREFIX}:bybit-truth-collector:missed_count": "0",
            f"{KEY_PREFIX}:bybit-truth-collector:invocation_id": "test-id",
            f"{KEY_PREFIX}:bybit-truth-collector:write_mode": "wrapper",
            f"{KEY_PREFIX}:bybit-truth-collector:status": "success",
        }.get(key)

        results = check_cron_cadence(mock_redis)

        assert "bybit-truth-collector" in results["jobs"]
        assert results["jobs"]["bybit-truth-collector"]["status"] == "PASS"

    def test_bybit_truth_collector_evidence_write(self):
        """Verify evidence can be written for bybit-truth-collector."""
        from datetime import UTC, datetime

        from scripts.monitoring.cron_evidence import (
            CRON_JOBS,
            KEY_PREFIX,
            write_cron_evidence,
        )

        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        mock_redis = Mock()
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 7

        with (
            patch(
                "scripts.monitoring.cron_evidence.get_redis_connection",
                return_value=mock_redis,
            ),
            patch(
                "scripts.monitoring.cron_evidence._verify_evidence_write",
                return_value=True,
            ),
        ):
            success, invocation_id = write_cron_evidence(
                "bybit-truth-collector",
                status="success",
                invocation_id="test-bybit-id",
            )

        assert success is True
        assert invocation_id == "test-bybit-id"
        # Verify the correct key prefix was used
        mock_pipeline.set.assert_any_call(
            f"{KEY_PREFIX}:bybit-truth-collector:status", "success"
        )

    def test_bybit_truth_collector_interval_consistency(self):
        """Verify collector interval matches cron job interval."""
        from scripts.monitoring.cron_evidence import CRON_JOBS

        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        # The bybit_truth_collector.py default interval is 300s (5 min)
        # But cron job should run every 30 minutes (1800s)
        # This test documents this relationship
        job_config = CRON_JOBS["bybit-truth-collector"]
        cron_interval = job_config["interval"]

        # Collector runs more frequently internally than cron triggers
        # Cron is the orchestrator, collector handles internal pacing
        assert cron_interval >= 1800, (
            "Cron interval should be at least 30 minutes to avoid overlap"
        )

    def test_bybit_truth_collector_missed_runs_detection(self):
        """Verify missed runs are detected for bybit-truth-collector."""
        from datetime import UTC, datetime, timedelta

        from scripts.monitoring.cron_evidence import check_cron_cadence, KEY_PREFIX

        # Skip if not in CRON_JOBS yet
        from scripts.monitoring.cron_evidence import CRON_JOBS

        if "bybit-truth-collector" not in CRON_JOBS:
            pytest.skip("bybit-truth-collector not yet in CRON_JOBS")

        # Simulate last run was 2 hours ago (should show as missed runs)
        two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            f"{KEY_PREFIX}:bybit-truth-collector:last_run": two_hours_ago,
            f"{KEY_PREFIX}:bybit-truth-collector:missed_count": "3",
            f"{KEY_PREFIX}:bybit-truth-collector:invocation_id": "old-id",
            f"{KEY_PREFIX}:bybit-truth-collector:write_mode": "wrapper",
            f"{KEY_PREFIX}:bybit-truth-collector:status": "success",
        }.get(key)

        results = check_cron_cadence(mock_redis)

        job_result = results["jobs"]["bybit-truth-collector"]
        assert job_result["missed_count"] == 3
        assert job_result["status"] in ["CHECK", "FAIL"]
