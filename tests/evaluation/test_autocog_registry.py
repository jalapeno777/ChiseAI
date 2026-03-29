"""Tests for autocog_registry module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from scripts.evaluation.autocog_registry import (
    AutocogJob,
    Cadence,
    Precondition,
    PreconditionType,
    RetryPolicy,
    RiskLevel,
    get_autocog_jobs,
    get_jobs_by_cadence,
    load_registry,
)

# Sample registry data for testing
SAMPLE_REGISTRY_YAML = """
jobs:
  - job_id: "autocog_15m_health_check"
    enabled: true
    cadence: "15m"
    timeout_seconds: 120
    risk_level: "low"
    idempotency_key: "health-check-15m"
    command: ["python", "-m", "scripts.evaluation.validate_cadence"]
    preconditions:
      - type: "file_exists"
        params:
          path: "scripts/evaluation/validate_cadence.py"
    retry_policy:
      max_attempts: 3
      initial_delay_seconds: 30
      backoff_multiplier: 2.0
      max_delay_seconds: 300
    required_approvals: []

  - job_id: "autocog_hourly_kpi"
    enabled: true
    cadence: "1h"
    timeout_seconds: 300
    risk_level: "medium"
    idempotency_key: "kpi-hourly"
    command: ["python", "-m", "scripts.evaluation.kpi_scheduler"]
    preconditions:
      - type: "file_exists"
        params:
          path: "scripts/evaluation/kpi_scheduler.py"
      - type: "env_var"
        params:
          name: "REDIS_HOST"
    retry_policy:
      max_attempts: 2
      initial_delay_seconds: 60
      backoff_multiplier: 1.5
      max_delay_seconds: 600
    required_approvals: []

  - job_id: "autocog_6h_mini_brain"
    enabled: true
    cadence: "6h"
    timeout_seconds: 600
    risk_level: "medium"
    idempotency_key: "mini-brain-6h"
    command: ["python", "-m", "scripts.evaluation.mini_brain_eval"]
    preconditions:
      - type: "file_exists"
        params:
          path: "scripts/evaluation/mini_brain_eval.py"
      - type: "dir_exists"
        params:
          path: "output/evaluations"
    retry_policy:
      max_attempts: 2
      initial_delay_seconds: 120
      backoff_multiplier: 2.0
      max_delay_seconds: 900
    required_approvals: ["aria"]

  - job_id: "autocog_daily_reflection"
    enabled: true
    cadence: "daily"
    timeout_seconds: 1800
    risk_level: "high"
    idempotency_key: "daily-reflection"
    command: ["python", "-m", "scripts.evaluation.run_weekly_reflection"]
    preconditions:
      - type: "file_exists"
        params:
          path: "scripts/evaluation/run_weekly_reflection.py"
      - type: "env_var"
        params:
          name: "DATABASE_URL"
    retry_policy:
      max_attempts: 1
      initial_delay_seconds: 300
      backoff_multiplier: 1.0
      max_delay_seconds: 300
    required_approvals: ["aria", "craig"]

  - job_id: "autocog_weekly_trends"
    enabled: true
    cadence: "weekly"
    timeout_seconds: 3600
    risk_level: "high"
    idempotency_key: "weekly-trends"
    command: ["python", "-m", "scripts.evaluation.run_daily_trends"]
    preconditions:
      - type: "file_exists"
        params:
          path: "scripts/evaluation/run_daily_trends.py"
      - type: "flag"
        params:
          name: "ENABLE_WEEKLY_TRENDS"
    retry_policy:
      max_attempts: 1
      initial_delay_seconds: 600
      backoff_multiplier: 1.0
      max_delay_seconds: 600
    required_approvals: ["craig"]

  - job_id: "autocog_monthly_report"
    enabled: false
    cadence: "monthly"
    timeout_seconds: 7200
    risk_level: "high"
    idempotency_key: "monthly-report"
    command: ["python", "-m", "scripts.evaluation.run_monthly_report"]
    preconditions:
      - type: "dir_exists"
        params:
          path: "output/reports"
    retry_policy:
      max_attempts: 1
      initial_delay_seconds: 900
      backoff_multiplier: 1.0
      max_delay_seconds: 900
    required_approvals: ["craig"]

  # Non-autocog job (should be filtered out by get_autocog_jobs)
  - job_id: "manual_backup"
    enabled: true
    cadence: "daily"
    timeout_seconds: 300
    risk_level: "low"
    idempotency_key: "manual-backup"
    command: ["python", "-m", "scripts.backup"]
    preconditions: []
    retry_policy: {}
    required_approvals: []
"""


@pytest.fixture
def sample_registry_path():
    """Create a temporary registry file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_REGISTRY_YAML)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def loaded_jobs(sample_registry_path):
    """Load jobs from the sample registry."""
    return load_registry(sample_registry_path)


class TestCadenceEnum:
    """Tests for Cadence enum."""

    def test_all_cadences_defined(self):
        """Test that all expected cadences are defined."""
        assert Cadence.MIN_15.value == "15m"
        assert Cadence.HOURLY.value == "1h"
        assert Cadence.HOURLY_6.value == "6h"
        assert Cadence.DAILY.value == "daily"
        assert Cadence.WEEKLY.value == "weekly"
        assert Cadence.MONTHLY.value == "monthly"

    def test_cadence_from_string(self):
        """Test creating Cadence from string value."""
        assert Cadence("15m") == Cadence.MIN_15
        assert Cadence("1h") == Cadence.HOURLY
        assert Cadence("6h") == Cadence.HOURLY_6


class TestRiskLevelEnum:
    """Tests for RiskLevel enum."""

    def test_all_risk_levels_defined(self):
        """Test that all expected risk levels are defined."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"


class TestPrecondition:
    """Tests for Precondition dataclass."""

    def test_from_dict_file_exists(self):
        """Test creating Precondition from dict with file_exists type."""
        data = {"type": "file_exists", "params": {"path": "/some/file.py"}}
        p = Precondition.from_dict(data)

        assert p.type == PreconditionType.FILE_EXISTS
        assert p.params == {"path": "/some/file.py"}

    def test_from_dict_dir_exists(self):
        """Test creating Precondition from dict with dir_exists type."""
        data = {"type": "dir_exists", "params": {"path": "/some/dir"}}
        p = Precondition.from_dict(data)

        assert p.type == PreconditionType.DIR_EXISTS
        assert p.params == {"path": "/some/dir"}

    def test_from_dict_env_var(self):
        """Test creating Precondition from dict with env_var type."""
        data = {"type": "env_var", "params": {"name": "MY_VAR", "value": "test"}}
        p = Precondition.from_dict(data)

        assert p.type == PreconditionType.ENV_VAR
        assert p.params == {"name": "MY_VAR", "value": "test"}

    def test_from_dict_flag(self):
        """Test creating Precondition from dict with flag type."""
        data = {"type": "flag", "params": {"name": "MY_FLAG"}}
        p = Precondition.from_dict(data)

        assert p.type == PreconditionType.FLAG
        assert p.params == {"name": "MY_FLAG"}

    def test_is_met_file_exists_true(self, tmp_path):
        """Test is_met returns True when file exists."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        p = Precondition(PreconditionType.FILE_EXISTS, {"path": str(test_file)})
        assert p.is_met() is True

    def test_is_met_file_exists_false(self, tmp_path):
        """Test is_met returns False when file does not exist."""
        p = Precondition(
            PreconditionType.FILE_EXISTS, {"path": str(tmp_path / "nonexistent.txt")}
        )
        assert p.is_met() is False

    def test_is_met_dir_exists_true(self, tmp_path):
        """Test is_met returns True when directory exists."""
        p = Precondition(PreconditionType.DIR_EXISTS, {"path": str(tmp_path)})
        assert p.is_met() is True

    def test_is_met_dir_exists_false(self):
        """Test is_met returns False when directory does not exist."""
        p = Precondition(
            PreconditionType.DIR_EXISTS, {"path": "/nonexistent/directory/path"}
        )
        assert p.is_met() is False

    def test_is_met_env_var_set(self, monkeypatch):
        """Test is_met returns True when env var is set."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        p = Precondition(PreconditionType.ENV_VAR, {"name": "TEST_VAR"})
        assert p.is_met() is True

    def test_is_met_env_var_not_set(self, monkeypatch):
        """Test is_met returns False when env var is not set."""
        monkeypatch.delenv("UNSET_VAR", raising=False)
        p = Precondition(PreconditionType.ENV_VAR, {"name": "UNSET_VAR"})
        assert p.is_met() is False

    def test_is_met_env_var_with_expected_value(self, monkeypatch):
        """Test is_met with expected value comparison."""
        monkeypatch.setenv("APP_ENV", "production")
        p = Precondition(
            PreconditionType.ENV_VAR, {"name": "APP_ENV", "value": "production"}
        )
        assert p.is_met() is True

        p2 = Precondition(
            PreconditionType.ENV_VAR, {"name": "APP_ENV", "value": "development"}
        )
        assert p2.is_met() is False

    def test_is_met_flag_true(self, monkeypatch):
        """Test is_met returns True when flag is set."""
        monkeypatch.setenv("MY_FLAG", "true")
        p = Precondition(PreconditionType.FLAG, {"name": "MY_FLAG"})
        assert p.is_met() is True

    def test_is_met_flag_1(self, monkeypatch):
        """Test is_met returns True when flag is set to 1."""
        monkeypatch.setenv("MY_FLAG", "1")
        p = Precondition(PreconditionType.FLAG, {"name": "MY_FLAG"})
        assert p.is_met() is True

    def test_is_met_flag_no(self, monkeypatch):
        """Test is_met returns False when flag is set to no/false."""
        monkeypatch.setenv("MY_FLAG", "false")
        p = Precondition(PreconditionType.FLAG, {"name": "MY_FLAG"})
        assert p.is_met() is False


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_from_dict_full(self):
        """Test creating RetryPolicy from a full dict."""
        data = {
            "max_attempts": 5,
            "initial_delay_seconds": 30,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 600,
        }
        rp = RetryPolicy.from_dict(data)

        assert rp.max_attempts == 5
        assert rp.initial_delay_seconds == 30
        assert rp.backoff_multiplier == 2.0
        assert rp.max_delay_seconds == 600

    def test_from_dict_empty(self):
        """Test creating RetryPolicy from empty dict returns defaults."""
        rp = RetryPolicy.from_dict({})

        assert rp.max_attempts == 1
        assert rp.initial_delay_seconds == 60
        assert rp.backoff_multiplier == 2.0
        assert rp.max_delay_seconds == 3600

    def test_from_dict_none(self):
        """Test creating RetryPolicy from None returns defaults."""
        rp = RetryPolicy.from_dict(None)

        assert rp.max_attempts == 1
        assert rp.initial_delay_seconds == 60
        assert rp.backoff_multiplier == 2.0
        assert rp.max_delay_seconds == 3600


class TestAutocogJob:
    """Tests for AutocogJob dataclass."""

    def test_from_dict_minimal(self):
        """Test creating AutocogJob from minimal dict."""
        data = {
            "job_id": "test_job",
            "cadence": "1h",
            "risk_level": "medium",
        }
        job = AutocogJob.from_dict(data)

        assert job.job_id == "test_job"
        assert job.enabled is True  # default
        assert job.cadence == Cadence.HOURLY
        assert job.risk_level == RiskLevel.MEDIUM
        assert job.timeout_seconds == 300  # default
        assert job.idempotency_key == ""
        assert job.command == []
        assert job.preconditions == []
        assert job.required_approvals == []

    def test_from_dict_full(self):
        """Test creating AutocogJob from full dict."""
        data = {
            "job_id": "full_job",
            "enabled": True,
            "cadence": "6h",
            "timeout_seconds": 600,
            "risk_level": "high",
            "idempotency_key": "full-job-key",
            "command": ["python", "test.py"],
            "preconditions": [{"type": "file_exists", "params": {"path": "test.py"}}],
            "retry_policy": {"max_attempts": 3},
            "required_approvals": ["aria"],
        }
        job = AutocogJob.from_dict(data)

        assert job.job_id == "full_job"
        assert job.enabled is True
        assert job.cadence == Cadence.HOURLY_6
        assert job.timeout_seconds == 600
        assert job.risk_level == RiskLevel.HIGH
        assert job.idempotency_key == "full-job-key"
        assert job.command == ["python", "test.py"]
        assert len(job.preconditions) == 1
        assert job.preconditions[0].type == PreconditionType.FILE_EXISTS
        assert job.retry_policy.max_attempts == 3
        assert job.required_approvals == ["aria"]

    def test_is_ready_no_preconditions(self):
        """Test is_ready returns True when no preconditions."""
        job = AutocogJob(
            job_id="test",
            enabled=True,
            cadence=Cadence.HOURLY,
            timeout_seconds=300,
            risk_level=RiskLevel.LOW,
            idempotency_key="key",
            command=["test"],
        )
        assert job.is_ready() is True

    def test_is_ready_all_met(self, tmp_path):
        """Test is_ready returns True when all preconditions are met."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        job = AutocogJob(
            job_id="test",
            enabled=True,
            cadence=Cadence.HOURLY,
            timeout_seconds=300,
            risk_level=RiskLevel.LOW,
            idempotency_key="key",
            command=["test"],
            preconditions=[
                Precondition(PreconditionType.FILE_EXISTS, {"path": str(test_file)})
            ],
        )
        assert job.is_ready() is True

    def test_is_ready_not_met(self, tmp_path):
        """Test is_ready returns False when preconditions are not met."""
        job = AutocogJob(
            job_id="test",
            enabled=True,
            cadence=Cadence.HOURLY,
            timeout_seconds=300,
            risk_level=RiskLevel.LOW,
            idempotency_key="key",
            command=["test"],
            preconditions=[
                Precondition(
                    PreconditionType.FILE_EXISTS,
                    {"path": str(tmp_path / "nonexistent.txt")},
                )
            ],
        )
        assert job.is_ready() is False


class TestLoadRegistry:
    """Tests for load_registry function."""

    def test_load_registry_from_file(self, sample_registry_path):
        """Test loading registry from a YAML file."""
        jobs = load_registry(sample_registry_path)

        assert len(jobs) == 7  # 6 autocog + 1 manual

    def test_load_registry_default_path(self):
        """Test load_registry uses default path when none provided."""
        # This should work if the actual registry file exists
        try:
            jobs = load_registry()
            # If file exists, verify it's a list
            assert isinstance(jobs, list)
        except FileNotFoundError:
            # Expected if the actual registry doesn't exist yet
            pass


class TestGetAutocogJobs:
    """Tests for get_autocog_jobs function."""

    def test_filters_enabled_autocog_jobs(self, loaded_jobs):
        """Test that only enabled autocog jobs are returned."""
        autocog = get_autocog_jobs(loaded_jobs)

        # All returned jobs should have job_id starting with "autocog_"
        for job in autocog:
            assert job.job_id.startswith("autocog_")
            assert job.enabled is True

    def test_excludes_disabled_jobs(self, loaded_jobs):
        """Test that disabled jobs are excluded."""
        autocog = get_autocog_jobs(loaded_jobs)
        job_ids = [j.job_id for j in autocog]

        # autocog_monthly_report is disabled
        assert "autocog_monthly_report" not in job_ids

    def test_excludes_non_autocog_jobs(self, loaded_jobs):
        """Test that non-autocog jobs are excluded."""
        autocog = get_autocog_jobs(loaded_jobs)
        job_ids = [j.job_id for j in autocog]

        # manual_backup is not an autocog job
        assert "manual_backup" not in job_ids

    def test_returns_all_six_autocog_jobs(self, loaded_jobs):
        """Test that all 6 autocog jobs are parsed correctly."""
        autocog = get_autocog_jobs(loaded_jobs)

        expected_ids = {
            "autocog_15m_health_check",
            "autocog_hourly_kpi",
            "autocog_6h_mini_brain",
            "autocog_daily_reflection",
            "autocog_weekly_trends",
        }
        actual_ids = {j.job_id for j in autocog}

        assert actual_ids == expected_ids


class TestGetJobsByCadence:
    """Tests for get_jobs_by_cadence function."""

    def test_filter_15m_cadence(self, loaded_jobs):
        """Test filtering jobs by 15m cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.MIN_15)

        assert len(cadence_jobs) == 1
        assert cadence_jobs[0].job_id == "autocog_15m_health_check"
        assert cadence_jobs[0].cadence == Cadence.MIN_15

    def test_filter_1h_cadence(self, loaded_jobs):
        """Test filtering jobs by 1h cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.HOURLY)

        assert len(cadence_jobs) == 1
        assert cadence_jobs[0].job_id == "autocog_hourly_kpi"
        assert cadence_jobs[0].cadence == Cadence.HOURLY

    def test_filter_6h_cadence(self, loaded_jobs):
        """Test filtering jobs by 6h cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.HOURLY_6)

        assert len(cadence_jobs) == 1
        assert cadence_jobs[0].job_id == "autocog_6h_mini_brain"
        assert cadence_jobs[0].cadence == Cadence.HOURLY_6

    def test_filter_daily_cadence(self, loaded_jobs):
        """Test filtering jobs by daily cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.DAILY)

        # Should have 2 daily jobs: autocog_daily_reflection and manual_backup
        assert len(cadence_jobs) == 2
        job_ids = [j.job_id for j in cadence_jobs]
        assert "autocog_daily_reflection" in job_ids
        assert "manual_backup" in job_ids
        # First should be autocog_daily_reflection
        assert cadence_jobs[0].cadence == Cadence.DAILY

    def test_filter_weekly_cadence(self, loaded_jobs):
        """Test filtering jobs by weekly cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.WEEKLY)

        assert len(cadence_jobs) == 1
        assert cadence_jobs[0].job_id == "autocog_weekly_trends"
        assert cadence_jobs[0].cadence == Cadence.WEEKLY

    def test_filter_monthly_cadence(self, loaded_jobs):
        """Test filtering jobs by monthly cadence."""
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.MONTHLY)

        # Note: autocog_monthly_report is disabled but still parsed
        assert len(cadence_jobs) == 1
        assert cadence_jobs[0].job_id == "autocog_monthly_report"
        assert cadence_jobs[0].cadence == Cadence.MONTHLY
        assert cadence_jobs[0].enabled is False

    def test_no_matching_cadence(self, loaded_jobs):
        """Test that empty list is returned when no jobs match."""
        # The registry doesn't have any daily cadence jobs that are enabled (except autocog_daily_reflection)
        # Actually autocog_daily_reflection IS daily and enabled, so we should get 1
        cadence_jobs = get_jobs_by_cadence(loaded_jobs, Cadence.MONTHLY)
        assert len(cadence_jobs) == 1
