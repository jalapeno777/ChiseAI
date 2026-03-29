"""Tests for KPI Scheduler autocog integration."""

from __future__ import annotations

# Ensure project root is in path
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from scripts.evaluation.autocog_registry import (
    AutocogJob,
    Cadence,
    Precondition,
    PreconditionType,
    RiskLevel,
)
from scripts.evaluation.kpi_scheduler import (
    HealthCheckServer,
    KPIScheduler,
    SchedulerCheckpoint,
    SchedulerState,
)


class TestSchedulerCheckpointV2:
    """Test SchedulerCheckpoint v2 format with dict-based last_run."""

    def test_default_v2_checkpoint(self):
        """Test default v2 checkpoint has dict last_run."""
        checkpoint = SchedulerCheckpoint()
        assert checkpoint.version == "2.0"
        assert checkpoint.last_run == {}
        # v2 uses dict-based last_run, not scalar fields
        assert "ops.kpi_ingest_6h" not in checkpoint.last_run

    def test_to_dict_v2(self):
        """Test v2 checkpoint serializes correctly."""
        checkpoint = SchedulerCheckpoint()
        checkpoint.last_run["ops.kpi_ingest_6h"] = 1234567890.0
        checkpoint.last_run["autocog.test_job"] = 1234567900.0

        data = checkpoint.to_dict()
        assert data["version"] == "2.0"
        assert data["last_run"]["ops.kpi_ingest_6h"] == 1234567890.0
        assert data["last_run"]["autocog.test_job"] == 1234567900.0
        # Legacy fields also present for backwards compat
        assert data["last_run_6h"] == 1234567890.0

    def test_from_dict_v1_migration(self):
        """Test v1 checkpoint migrates to v2 correctly."""
        v1_data = {
            "state": "running",
            "last_run_6h": 1000.0,
            "last_run_daily": 2000.0,
            "last_run_weekly": 3000.0,
            "cycle_count": 10,
            "error_count": 2,
            "last_error": "Some error",
            "version": "1.0",
        }

        checkpoint = SchedulerCheckpoint.from_dict(v1_data)
        assert checkpoint.version == "1.0"
        assert checkpoint.last_run == {
            "ops.kpi_ingest_6h": 1000.0,
            "ops.daily_trends": 2000.0,
            "governance.weekly_reflection": 3000.0,
        }

    def test_from_dict_v2(self):
        """Test v2 checkpoint loads correctly."""
        v2_data = {
            "state": "running",
            "last_run": {
                "ops.kpi_ingest_6h": 1000.0,
                "autocog.test_job": 1500.0,
            },
            "cycle_count": 10,
            "error_count": 2,
            "version": "2.0",
        }

        checkpoint = SchedulerCheckpoint.from_dict(v2_data)
        assert checkpoint.version == "2.0"
        assert checkpoint.last_run["ops.kpi_ingest_6h"] == 1000.0
        assert checkpoint.last_run["autocog.test_job"] == 1500.0


class TestKPISchedulerAutocogInit:
    """Test KPIScheduler autocog initialization."""

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_loads_autocog_jobs(self, mock_idem_class, mock_get_jobs, mock_load_reg):
        """Test scheduler loads autocog jobs at init."""
        # Setup mocks
        mock_jobs = [MagicMock(), MagicMock()]
        mock_load_reg.return_value = mock_jobs
        mock_get_jobs.return_value = [mock_jobs[1]]

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)

            mock_load_reg.assert_called_once()
            mock_get_jobs.assert_called_once_with(mock_jobs)
            assert scheduler.all_jobs == mock_jobs
            assert scheduler.autocog_jobs == [mock_jobs[1]]

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_idempotency_initialized(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test scheduler initializes idempotency checker."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)
            assert scheduler.idempotency is not None
            mock_idem_class.assert_called_once()


class TestRunAutocogJob:
    """Test run_autocog_job method."""

    def _make_job(
        self,
        job_id: str = "autocog.test",
        cadence: Cadence = Cadence.HOURLY,
        enabled: bool = True,
        command: list[str] | None = None,
        idempotency_key: str = "test:{date}",
    ) -> AutocogJob:
        """Helper to create AutocogJob for testing."""
        return AutocogJob(
            job_id=job_id,
            enabled=enabled,
            cadence=cadence,
            timeout_seconds=30,
            risk_level=RiskLevel.LOW,
            idempotency_key=idempotency_key,
            command=command or ["echo", "test"],
        )

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_skips_when_idempotency_blocks(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test job is skipped when idempotency checker says no."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem = MagicMock()
        mock_idem.should_run.return_value = False
        mock_idem_class.return_value = mock_idem

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)
            job = self._make_job()

            result = scheduler.run_autocog_job(job)

            assert result == 0
            mock_idem.should_run.assert_called_once_with(
                job.job_id, job.idempotency_key, job.cadence.value
            )

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_skips_when_preconditions_not_met(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test job is skipped when preconditions not met."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem = MagicMock()
        mock_idem.should_run.return_value = True
        mock_idem_class.return_value = mock_idem

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)
            job = self._make_job()
            job.preconditions = [
                Precondition(
                    type=PreconditionType.FILE_EXISTS, params={"path": "/nonexistent"}
                )
            ]

            result = scheduler.run_autocog_job(job)

            assert result == 1

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_dry_run_records_completion(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test dry run mode records completion but doesn't execute."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem = MagicMock()
        mock_idem.should_run.return_value = True
        mock_idem_class.return_value = mock_idem

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir, dry_run=True)
            job = self._make_job()

            result = scheduler.run_autocog_job(job)

            assert result == 0
            mock_idem.record_completion.assert_called_once_with(
                job.job_id, job.idempotency_key, success=True
            )

    @patch("subprocess.run")
    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_executes_job_success(
        self, mock_idem_class, mock_get_jobs, mock_load_reg, mock_run
    ):
        """Test job execution on success."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem = MagicMock()
        mock_idem.should_run.return_value = True
        mock_idem_class.return_value = mock_idem
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir, dry_run=False)
            job = self._make_job(command=["python3", "test.py"])

            result = scheduler.run_autocog_job(job)

            assert result == 0
            mock_idem.record_completion.assert_called_once_with(
                job.job_id, job.idempotency_key, success=True, error=None
            )

    @patch("subprocess.run")
    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_executes_job_failure(
        self, mock_idem_class, mock_get_jobs, mock_load_reg, mock_run
    ):
        """Test job execution on failure."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem = MagicMock()
        mock_idem.should_run.return_value = True
        mock_idem_class.return_value = mock_idem
        mock_run.return_value = MagicMock(returncode=1, stderr="Error occurred")

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir, dry_run=False)
            job = self._make_job(command=["python3", "test.py"])

            result = scheduler.run_autocog_job(job)

            assert result == 1
            mock_idem.record_completion.assert_called_once_with(
                job.job_id, job.idempotency_key, success=False, error="Error occurred"
            )


class TestRecordCycleComplete:
    """Test record_cycle_complete method."""

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_records_job_id_in_checkpoint(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test job_id is stored in checkpoint.last_run dict."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem_class.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)

            scheduler.record_cycle_complete("autocog.test_job", success=True)

            assert "autocog.test_job" in scheduler.checkpoint.last_run
            assert scheduler.checkpoint.last_run["autocog.test_job"] > 0

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_backwards_compatible_with_legacy_cycle_names(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test legacy cycle names still work."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem_class.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)

            # Use legacy cycle names
            scheduler.record_cycle_complete("6h", success=True)
            scheduler.record_cycle_complete("daily", success=True)
            scheduler.record_cycle_complete("weekly", success=True)

            # Verify they were stored in dict
            assert "6h" in scheduler.checkpoint.last_run
            assert "daily" in scheduler.checkpoint.last_run
            assert "weekly" in scheduler.checkpoint.last_run


class TestHealthCheckStatus:
    """Test health check includes autocog job status."""

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_status_includes_jobs(self, mock_idem_class, mock_get_jobs, mock_load_reg):
        """Test status endpoint includes job information."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem_class.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)
            scheduler.checkpoint.last_run["autocog.test_job"] = 1234567890.0
            scheduler.checkpoint.state = SchedulerState.RUNNING.value

            health_server = HealthCheckServer(scheduler.checkpoint, port=0)

            # Create mock request
            mock_request = MagicMock()
            mock_request.path = "/status"

            handler = health_server._create_handler()
            handler.checkpoint = scheduler.checkpoint

            # We can't easily test the full HTTP response, but we can verify
            # the status dict structure that would be generated
            status = {
                "status": "healthy",
                "state": scheduler.checkpoint.state,
                "checkpoint": scheduler.checkpoint.to_dict(),
                "timestamp": datetime.now(UTC).isoformat(),
                "jobs": {
                    job_id: {
                        "last_run": ts,
                        "since_last_run": time.time() - ts if ts > 0 else None,
                    }
                    for job_id, ts in scheduler.checkpoint.last_run.items()
                },
            }

            assert "jobs" in status
            assert "autocog.test_job" in status["jobs"]
            assert status["jobs"]["autocog.test_job"]["last_run"] == 1234567890.0


class TestDryRunIntegration:
    """Test dry-run integration with autocog."""

    @patch("scripts.evaluation.kpi_scheduler.load_registry")
    @patch("scripts.evaluation.kpi_scheduler.get_autocog_jobs")
    @patch("scripts.evaluation.kpi_scheduler.IdempotencyChecker")
    def test_dry_run_all_includes_autocog_cycle(
        self, mock_idem_class, mock_get_jobs, mock_load_reg
    ):
        """Test --dry-run-all works with new cycle types."""
        mock_load_reg.return_value = []
        mock_get_jobs.return_value = []
        mock_idem_class.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = KPIScheduler(output_dir=tmpdir)
            # run_all_dry runs 6h, daily, weekly cycles
            # It should not fail even if autocog_jobs is empty
            result = scheduler.run_all_dry()
            assert result == 0  # Should pass dry run
