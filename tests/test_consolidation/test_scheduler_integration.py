"""
Integration tests for MemoryConsolidationScheduler with tempmemory ingestion.

Tests verify that tempmemory ingestion is properly integrated as Step 0
of the consolidation workflow.

Story: ST-MEMORY-INGEST-001
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.governance.consolidation.config import ConsolidationConfig
from src.governance.consolidation.scheduler import (
    ConsolidationResult,
    MemoryConsolidationScheduler,
)


class TestConsolidationConfigTempmemorySettings:
    """Test that config has tempmemory settings."""

    def test_config_has_tempmemory_ingestion_enabled_default(self):
        """Config should have run_tempmemory_ingestion defaulting to True."""
        config = ConsolidationConfig()
        assert hasattr(config, "run_tempmemory_ingestion")
        assert config.run_tempmemory_ingestion is True

    def test_config_has_tempmemory_dry_run_default(self):
        """Config should have tempmemory_ingestion_dry_run defaulting to False."""
        config = ConsolidationConfig()
        assert hasattr(config, "tempmemory_ingestion_dry_run")
        assert config.tempmemory_ingestion_dry_run is False

    def test_config_has_tempmemory_filter_types_default(self):
        """Config should have tempmemory_ingestion_filter_types with defaults."""
        config = ConsolidationConfig()
        assert hasattr(config, "tempmemory_ingestion_filter_types")
        assert config.tempmemory_ingestion_filter_types == [
            "decision",
            "pattern",
            "summary",
            "anti-pattern",
        ]

    def test_config_has_tempmemory_cadence_default(self):
        """Config should have tempmemory_ingestion_cadence defaulting to 'daily'."""
        config = ConsolidationConfig()
        assert hasattr(config, "tempmemory_ingestion_cadence")
        assert config.tempmemory_ingestion_cadence == "daily"

    def test_config_to_dict_includes_tempmemory_fields(self):
        """to_dict should include tempmemory settings."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = False
        config.tempmemory_ingestion_dry_run = True
        config.tempmemory_ingestion_filter_types = ["decision"]
        config.tempmemory_ingestion_cadence = "manual"

        data = config.to_dict()

        assert data["run_tempmemory_ingestion"] is False
        assert data["tempmemory_ingestion_dry_run"] is True
        assert data["tempmemory_ingestion_filter_types"] == ["decision"]
        assert data["tempmemory_ingestion_cadence"] == "manual"

    def test_config_from_dict_parses_tempmemory_fields(self):
        """from_dict should parse tempmemory settings."""
        data = {
            "schedule_time": "02:00:00",
            "schedule_timezone": "UTC",
            "enabled": False,
            "dry_run": True,
            "rollback_retention_days": 7,
            "rollback_max_operations": 10000,
            "golden_min_access_count": 5,
            "golden_min_age_days": 30,
            "golden_min_relevance_score": 0.85,
            "batch_size": 100,
            "cold_storage_path": "/data/chiseai/cold_storage/memories",
            "golden_collection": "ChiseAI_golden",
            "feature_flag_key": "chise:feature_flags:governance:consolidation_enabled",
            "run_tempmemory_ingestion": False,
            "tempmemory_ingestion_dry_run": True,
            "tempmemory_ingestion_filter_types": ["pattern"],
            "tempmemory_ingestion_cadence": "always",
        }

        config = ConsolidationConfig.from_dict(data)

        assert config.run_tempmemory_ingestion is False
        assert config.tempmemory_ingestion_dry_run is True
        assert config.tempmemory_ingestion_filter_types == ["pattern"]
        assert config.tempmemory_ingestion_cadence == "always"


class TestSchedulerTempmemoryIngestionInitialization:
    """Test scheduler initializes ingestion runner when enabled."""

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_scheduler_initializes_ingestion_runner_when_enabled(
        self, mock_runner_class
    ):
        """Scheduler should initialize ingestion runner when run_tempmemory_ingestion is True."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.tempmemory_ingestion_dry_run = False
        config.tempmemory_ingestion_filter_types = ["decision", "pattern"]

        mock_redis = MagicMock()
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(
            config=config,
            redis_client=mock_redis,
        )

        assert scheduler._ingestion_runner is not None
        mock_runner_class.assert_called_once_with(
            redis_client=mock_redis,
            dry_run=False,
            filter_types=["decision", "pattern"],
        )

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_scheduler_skips_ingestion_runner_when_disabled(self, mock_runner_class):
        """Scheduler should not initialize ingestion runner when run_tempmemory_ingestion is False."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = False

        mock_redis = MagicMock()

        scheduler = MemoryConsolidationScheduler(
            config=config,
            redis_client=mock_redis,
        )

        assert scheduler._ingestion_runner is None
        mock_runner_class.assert_not_called()

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_scheduler_handles_ingestion_runner_init_failure(self, mock_runner_class):
        """Scheduler should handle ingestion runner initialization failure gracefully."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True

        mock_redis = MagicMock()
        mock_runner_class.side_effect = Exception("Init failed")

        # Should not raise
        scheduler = MemoryConsolidationScheduler(
            config=config,
            redis_client=mock_redis,
        )

        assert scheduler._ingestion_runner is None


class TestSchedulerTempmemoryIngestionStep:
    """Test _run_tempmemory_ingestion_step method."""

    def test_ingestion_step_returns_skipped_when_disabled(self):
        """Step should return skipped when run_tempmemory_ingestion is False."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = False

        scheduler = MemoryConsolidationScheduler(config=config)

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["skipped"] is True
        assert result["reason"] == "disabled in config"

    def test_ingestion_step_returns_skipped_when_runner_not_initialized(self):
        """Step should return skipped when ingestion runner is None."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True

        scheduler = MemoryConsolidationScheduler(config=config)
        scheduler._ingestion_runner = None

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["skipped"] is True
        assert result["reason"] == "runner not initialized"

    def test_ingestion_step_returns_skipped_when_cadence_is_manual(self):
        """Step should return skipped when cadence is set to manual."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.tempmemory_ingestion_cadence = "manual"

        scheduler = MemoryConsolidationScheduler(config=config)
        scheduler._ingestion_runner = MagicMock()

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["skipped"] is True
        assert result["reason"] == "cadence set to manual"

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_ingestion_step_returns_stats_on_success(self, mock_runner_class):
        """Step should return stats when ingestion succeeds."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.tempmemory_ingestion_cadence = "daily"

        mock_report = MagicMock()
        mock_report.total_files = 10
        mock_report.scanned_files = 10
        mock_report.migrated_files = 8
        mock_report.failed_files = 0
        mock_report.skipped_files = 2
        mock_report.duration_seconds = 5.5
        mock_report.dry_run = False

        mock_runner = MagicMock()
        mock_runner.run_with_lock.return_value = mock_report
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["success"] is True
        assert result["total_files"] == 10
        assert result["scanned_files"] == 10
        assert result["migrated_files"] == 8
        assert result["failed_files"] == 0
        assert result["skipped_files"] == 2
        assert result["duration_seconds"] == 5.5
        assert result["dry_run"] is False

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_ingestion_step_returns_failure_when_files_fail(self, mock_runner_class):
        """Step should indicate failure when some files fail."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.tempmemory_ingestion_cadence = "daily"

        mock_report = MagicMock()
        mock_report.total_files = 10
        mock_report.scanned_files = 10
        mock_report.migrated_files = 7
        mock_report.failed_files = 3
        mock_report.skipped_files = 0
        mock_report.duration_seconds = 5.5
        mock_report.dry_run = False

        mock_runner = MagicMock()
        mock_runner.run_with_lock.return_value = mock_report
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["success"] is False  # Failed because failed_files > 0
        assert result["failed_files"] == 3

    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_ingestion_step_handles_exception(self, mock_runner_class):
        """Step should handle exceptions gracefully."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.tempmemory_ingestion_cadence = "daily"

        mock_runner = MagicMock()
        mock_runner.run_with_lock.side_effect = Exception("Ingestion failed")
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        result = scheduler._run_tempmemory_ingestion_step(dry_run=False)

        assert result["success"] is False
        assert "error" in result
        assert "Ingestion failed" in result["error"]


class TestConsolidationResultIngestionStats:
    """Test ConsolidationResult has ingestion_stats field."""

    def test_result_has_ingestion_stats_field(self):
        """ConsolidationResult should have ingestion_stats field."""
        result = ConsolidationResult()
        assert hasattr(result, "ingestion_stats")
        assert result.ingestion_stats is None

    def test_result_can_store_ingestion_stats(self):
        """ConsolidationResult should be able to store ingestion stats."""
        result = ConsolidationResult()
        result.ingestion_stats = {
            "success": True,
            "total_files": 10,
            "migrated_files": 8,
            "failed_files": 0,
        }

        assert result.ingestion_stats["success"] is True
        assert result.ingestion_stats["total_files"] == 10


class TestSchedulerIntegrationWithConsolidation:
    """Test that ingestion runs as Step 0 before archival."""

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_ingestion_runs_before_archival(
        self, mock_runner_class, mock_promoter_class, mock_archiver_class
    ):
        """Tempmemory ingestion should run as Step 0 before archival."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.enabled = True

        # Mock archiver
        mock_archiver = MagicMock()
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver_class.return_value = mock_archiver

        # Mock promoter
        mock_promoter = MagicMock()
        mock_promoter_class.return_value = mock_promoter

        # Mock ingestion runner
        mock_report = MagicMock()
        mock_report.total_files = 5
        mock_report.scanned_files = 5
        mock_report.migrated_files = 5
        mock_report.failed_files = 0
        mock_report.skipped_files = 0
        mock_report.duration_seconds = 1.0
        mock_report.dry_run = False

        mock_runner = MagicMock()
        mock_runner.run_with_lock.return_value = mock_report
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        # Run consolidation
        with patch.object(scheduler, "_update_last_run_time"):
            with patch.object(scheduler, "_export_metrics"):
                result = scheduler.run_now(dry_run=True)

        # Verify ingestion stats are in result
        assert result.ingestion_stats is not None
        assert result.ingestion_stats["total_files"] == 5
        assert result.ingestion_stats["migrated_files"] == 5

        # Verify ingestion runner was called
        mock_runner.run_with_lock.assert_called_once()

    @patch("src.governance.consolidation.scheduler.MemoryArchiver")
    @patch("src.governance.consolidation.scheduler.GoldenMemoryPromoter")
    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_ingestion_errors_dont_block_other_steps(
        self, mock_runner_class, mock_promoter_class, mock_archiver_class
    ):
        """Ingestion errors should not block archival and promotion steps."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.enabled = True

        # Mock archiver
        mock_archiver = MagicMock()
        mock_archiver.get_cold_storage_size.return_value = 0
        mock_archiver.archive_memories.return_value = MagicMock(errors=[])
        mock_archiver_class.return_value = mock_archiver

        # Mock promoter
        mock_promoter = MagicMock()
        mock_promoter.promote_memories.return_value = MagicMock(errors=[])
        mock_promoter_class.return_value = mock_promoter

        # Mock ingestion runner that fails
        mock_runner = MagicMock()
        mock_runner.run_with_lock.side_effect = Exception("Ingestion error")
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        # Run consolidation - should not raise
        with patch.object(scheduler, "_update_last_run_time"):
            with patch.object(scheduler, "_export_metrics"):
                result = scheduler.run_now(dry_run=True)

        # Verify result has error in ingestion_stats
        assert result.ingestion_stats is not None
        assert result.ingestion_stats["success"] is False
        assert "error" in result.ingestion_stats

        # Verify archival still ran
        mock_archiver.archive_memories.assert_called_once()

        # Verify promotion still ran
        mock_promoter.promote_memories.assert_called_once()

        # Overall result should still be successful
        assert result.success is True


class TestSchedulerIngestionWarningOnFailures:
    """Test that scheduler logs warnings when ingestion has failures."""

    @patch("src.governance.consolidation.scheduler.logger")
    @patch("src.governance.consolidation.scheduler.TempmemoryIngestionRunner")
    def test_scheduler_logs_warning_on_ingestion_failures(
        self, mock_runner_class, mock_logger
    ):
        """Scheduler should log warning when ingestion has failed files."""
        config = ConsolidationConfig()
        config.run_tempmemory_ingestion = True
        config.enabled = True

        mock_report = MagicMock()
        mock_report.total_files = 10
        mock_report.scanned_files = 10
        mock_report.migrated_files = 7
        mock_report.failed_files = 3
        mock_report.skipped_files = 0
        mock_report.duration_seconds = 5.5
        mock_report.dry_run = False

        mock_runner = MagicMock()
        mock_runner.run_with_lock.return_value = mock_report
        mock_runner_class.return_value = mock_runner

        scheduler = MemoryConsolidationScheduler(config=config)

        # Run consolidation
        with patch.object(scheduler, "_update_last_run_time"):
            with patch.object(scheduler, "_export_metrics"):
                with patch.object(
                    scheduler._archiver, "get_cold_storage_size", return_value=0
                ):
                    scheduler.run_now(dry_run=True)

        # Verify warning was logged
        mock_logger.warning.assert_any_call("Tempmemory ingestion had 3 failures")
