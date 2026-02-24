"""Tests for CI/CD Pipeline."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from scripts.ci.pipeline import (
    PipelineStage,
    PipelineStatus,
    StageResult,
    PipelineConfig,
    StageRunner,
    LintStage,
    TestStage,
    SecurityStage,
    CIPipeline,
)


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_stage_values(self):
        """Test that expected stage values exist."""
        assert PipelineStage.LINT.value == "lint"
        assert PipelineStage.TEST.value == "test"
        assert PipelineStage.SECURITY.value == "security"
        assert PipelineStage.BUILD.value == "build"
        assert PipelineStage.DEPLOY.value == "deploy"


class TestPipelineStatus:
    """Tests for PipelineStatus enum."""

    def test_status_values(self):
        """Test that expected status values exist."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.SUCCESS.value == "success"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.SKIPPED.value == "skipped"


class TestStageResult:
    """Tests for StageResult dataclass."""

    def test_result_creation(self):
        """Test creating a stage result."""
        result = StageResult(
            stage=PipelineStage.LINT,
            status=PipelineStatus.SUCCESS,
            start_time=datetime.now(timezone.utc),
        )
        assert result.stage == PipelineStage.LINT
        assert result.status == PipelineStatus.SUCCESS
        assert result.duration_seconds == 0

    def test_result_to_dict(self):
        """Test serializing result to dict."""
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc)
        result = StageResult(
            stage=PipelineStage.TEST,
            status=PipelineStatus.SUCCESS,
            start_time=start,
            end_time=end,
            duration_seconds=5.5,
            metrics={"coverage": 85.0},
        )
        d = result.to_dict()

        assert d["stage"] == "test"
        assert d["status"] == "success"
        assert "start_time" in d
        assert d["duration_seconds"] == 5.5
        assert d["metrics"]["coverage"] == 85.0

    def test_result_with_error(self):
        """Test result with error message."""
        result = StageResult(
            stage=PipelineStage.LINT,
            status=PipelineStatus.FAILED,
            start_time=datetime.now(timezone.utc),
            error="Linting failed",
        )
        assert result.status == PipelineStatus.FAILED
        assert "Linting failed" in result.error


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_config_defaults(self, pipeline_config):
        """Test default config values."""
        assert pipeline_config.project_name == "test-project"
        assert pipeline_config.python_version == "3.13"
        assert pipeline_config.enable_lint is True
        assert pipeline_config.enable_test is True
        assert pipeline_config.min_coverage == 80.0

    def test_config_custom_values(self):
        """Test custom config values."""
        config = PipelineConfig(
            project_name="custom-project",
            min_coverage=90.0,
            parallel_jobs=8,
            timeout_minutes=120,
        )
        assert config.project_name == "custom-project"
        assert config.min_coverage == 90.0
        assert config.parallel_jobs == 8

    def test_config_to_dict(self, pipeline_config):
        """Test serializing config to dict."""
        d = pipeline_config.to_dict()
        assert "project_name" in d
        assert "python_version" in d
        assert "min_coverage" in d


class TestStageRunner:
    """Tests for StageRunner base class."""

    def test_runner_creation(self, pipeline_config):
        """Test creating stage runner."""
        runner = StageRunner(pipeline_config)
        assert runner.config == pipeline_config

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run, pipeline_config):
        """Test running a successful command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

        runner = StageRunner(pipeline_config)
        code, stdout, stderr = runner.run_command(["echo", "hello"])

        assert code == 0
        assert stdout == "output"

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run, pipeline_config):
        """Test running a failing command."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        runner = StageRunner(pipeline_config)
        code, stdout, stderr = runner.run_command(["false"])

        assert code == 1
        assert stderr == "error"


class TestLintStage:
    """Tests for LintStage."""

    def test_lint_stage_creation(self, lint_stage):
        """Test creating lint stage."""
        assert lint_stage.config is not None

    @patch.object(StageRunner, "run_command")
    def test_lint_stage_run_success(self, mock_run, lint_stage):
        """Test running lint stage successfully."""
        mock_run.return_value = (0, "OK", "")

        result = lint_stage.run()

        assert result.stage == PipelineStage.LINT
        assert result.status == PipelineStatus.SUCCESS

    @patch.object(StageRunner, "run_command")
    def test_lint_stage_run_failure(self, mock_run, lint_stage):
        """Test running lint stage with failure."""
        mock_run.return_value = (1, "", "Linting error")

        result = lint_stage.run()

        assert result.stage == PipelineStage.LINT
        assert result.status == PipelineStatus.FAILED


class TestTestStage:
    """Tests for TestStage."""

    def test_test_stage_creation(self, test_stage):
        """Test creating test stage."""
        assert test_stage.config is not None

    @patch.object(StageRunner, "run_command")
    def test_test_stage_run(self, mock_run, test_stage):
        """Test running test stage."""
        mock_run.return_value = (0, "Tests passed", "")

        result = test_stage.run()

        assert result.stage == PipelineStage.TEST
        assert "coverage_percent" in result.metrics


class TestSecurityStage:
    """Tests for SecurityStage."""

    def test_security_stage_creation(self, security_stage):
        """Test creating security stage."""
        assert security_stage.config is not None

    @patch.object(StageRunner, "run_command")
    def test_security_stage_run(self, mock_run, security_stage):
        """Test running security stage."""
        mock_run.return_value = (0, "No issues", "")

        result = security_stage.run()

        assert result.stage == PipelineStage.SECURITY
        assert "bandit_passed" in result.metrics


class TestCIPipeline:
    """Tests for CIPipeline."""

    def test_pipeline_creation(self, ci_pipeline):
        """Test creating CI pipeline."""
        assert ci_pipeline.config is not None
        assert ci_pipeline._results == []

    @patch.object(LintStage, "run")
    @patch.object(TestStage, "run")
    @patch.object(SecurityStage, "run")
    def test_pipeline_run(self, mock_sec, mock_test, mock_lint, ci_pipeline):
        """Test running pipeline."""
        mock_lint.return_value = StageResult(
            stage=PipelineStage.LINT,
            status=PipelineStatus.SUCCESS,
            start_time=datetime.now(timezone.utc),
        )
        mock_test.return_value = StageResult(
            stage=PipelineStage.TEST,
            status=PipelineStatus.SUCCESS,
            start_time=datetime.now(timezone.utc),
        )
        mock_sec.return_value = StageResult(
            stage=PipelineStage.SECURITY,
            status=PipelineStatus.SUCCESS,
            start_time=datetime.now(timezone.utc),
        )

        report = ci_pipeline.run()

        assert "pipeline" in report
        assert "status" in report
        assert report["status"] == "success"

    def test_pipeline_report(self, ci_pipeline):
        """Test getting pipeline report."""
        report = ci_pipeline.get_report()

        assert "stages" in report
        assert "summary" in report

    def test_pipeline_is_green(self, ci_pipeline):
        """Test checking if pipeline is green."""
        # Create a successful result manually
        from scripts.ci.pipeline import StageResult

        ci_pipeline._results = [
            StageResult(
                stage=PipelineStage.LINT,
                status=PipelineStatus.SUCCESS,
                start_time=datetime.now(timezone.utc),
            )
        ]
        is_green = ci_pipeline.is_green()
        assert is_green is True

        # Test with failed result
        ci_pipeline._results = [
            StageResult(
                stage=PipelineStage.LINT,
                status=PipelineStatus.FAILED,
                start_time=datetime.now(timezone.utc),
            )
        ]
        is_green = ci_pipeline.is_green()
        assert is_green is False

    def test_pipeline_with_disabled_stages(self):
        """Test pipeline with some stages disabled."""
        config = PipelineConfig(
            enable_lint=True,
            enable_test=False,
            enable_security_scan=False,
        )
        pipeline = CIPipeline(config)

        with patch.object(LintStage, "run") as mock_lint:
            mock_lint.return_value = StageResult(
                stage=PipelineStage.LINT,
                status=PipelineStatus.SUCCESS,
                start_time=datetime.now(timezone.utc),
            )
            report = pipeline.run()

        stage_names = [s["stage"] for s in report["stages"]]
        assert "lint" in stage_names

    def test_pipeline_summary(self, ci_pipeline):
        """Test pipeline summary."""
        report = ci_pipeline.get_report()

        assert "summary" in report
        assert "total_stages" in report["summary"]
        assert "passed_stages" in report["summary"]
        assert "failed_stages" in report["summary"]


class TestCoverageGating:
    """Tests for coverage gating functionality."""

    def test_coverage_threshold_config(self):
        """Test coverage threshold configuration."""
        config = PipelineConfig(min_coverage=95.0)
        assert config.min_coverage == 95.0

    def test_fail_on_coverage_drop_config(self):
        """Test fail on coverage drop configuration."""
        config = PipelineConfig(fail_on_coverage_drop=True)
        assert config.fail_on_coverage_drop is True


class TestParallelExecution:
    """Tests for parallel execution."""

    def test_parallel_jobs_config(self):
        """Test parallel jobs configuration."""
        config = PipelineConfig(parallel_jobs=8)
        assert config.parallel_jobs == 8

    def test_default_parallel_jobs(self, pipeline_config):
        """Test default parallel jobs."""
        assert pipeline_config.parallel_jobs == 4


class TestTimeout:
    """Tests for timeout functionality."""

    def test_pipeline_timeout_config(self):
        """Test pipeline timeout configuration."""
        config = PipelineConfig(timeout_minutes=120)
        assert config.timeout_minutes == 120

    def test_default_timeout(self, pipeline_config):
        """Test default timeout from fixture."""
        # Fixture uses 30 minute timeout
        assert pipeline_config.timeout_minutes == 30
