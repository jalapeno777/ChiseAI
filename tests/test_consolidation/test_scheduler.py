"""
Tests for MemoryConsolidationScheduler with tempmemory ingestion integration.

Story: ST-MEMORY-INGEST-001
"""

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.governance.consolidation.config import ConsolidationConfig
from src.governance.consolidation.scheduler import (
    ConsolidationResult,
    MemoryConsolidationScheduler,
)
from src.governance.tempmemory.ingestion_runner import IngestionStats


class TestTempmemoryIngestionIntegration:
    """Test tempmemory ingestion integration in scheduler."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return ConsolidationConfig(
            enabled=True,
            dry_run=True,
            run_tempmemory_ingestion=True,
            tempmemory_ingestion_dry_run=True,
            tempmemory_ingestion_filter_types=["decision", "pattern"],
        )

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def mock_qdrant(self):
        """Create a mock Qdrant client."""
        return MagicMock()

    @pytest.fixture
    def scheduler(self, config, mock_redis, mock_qdrant):
        """Create a scheduler instance."""
        return MemoryConsolidationScheduler(
            config=config,
            qdrant_client=mock_qdrant,
            redis_client=mock_redis,
        )

    def test_scheduler_has_ingestion_runner(self, scheduler):
        """Test that scheduler has an ingestion runner initialized."""
        assert scheduler._ingestion_runner is not None
        assert scheduler._ingestion_runner._filter_types == ["decision", "pattern"]

    def test_consolidation_result_has_ingestion_stats(self):
        """Test that ConsolidationResult has ingestion_stats field."""
        result = ConsolidationResult()
        assert hasattr(result, "ingestion_stats")
        assert result.ingestion_stats is None

    def test_run_now_includes_ingestion_by_default(self, scheduler):
        """Test that run_now() includes ingestion by default."""
        with patch.object(
            scheduler._ingestion_runner,
            "scan_and_ingest",
            return_value=IngestionStats(
                total_files_scanned=5,
                files_ingested=3,
                files_failed=0,
            ),
        ):
            result = scheduler.run_now(dry_run=True, archive=False, promote=False)

            assert result.ingestion_stats is not None
            assert result.ingestion_stats.total_files_scanned == 5
            assert result.ingestion_stats.files_ingested == 3

    def test_run_now_can_disable_ingestion(self, scheduler):
        """Test that run_now() can disable ingestion."""
        result = scheduler.run_now(
            dry_run=True, archive=False, promote=False, ingest=False
        )

        assert result.ingestion_stats is None

    def test_ingestion_runs_before_archival(self, scheduler, mock_redis):
        """Test that ingestion runs before archival."""
        call_order = []

        def track_ingestion(*args, **kwargs):
            call_order.append("ingestion")
            return IngestionStats(files_ingested=1)

        def track_archival(*args, **kwargs):
            call_order.append("archival")
            from src.governance.consolidation.archiver import ArchiveStats

            return ArchiveStats(memories_scanned=10, memories_archived=5)

        with patch.object(
            scheduler._ingestion_runner, "scan_and_ingest", side_effect=track_ingestion
        ):
            with patch.object(
                scheduler._archiver, "archive_memories", side_effect=track_archival
            ):
                result = scheduler.run_now(dry_run=True)

                assert call_order == ["ingestion", "archival"]

    def test_ingestion_feature_flag_disabled(self, mock_redis, mock_qdrant):
        """Test that ingestion is skipped when feature flag is disabled."""
        config = ConsolidationConfig(
            enabled=True,
            dry_run=True,
            run_tempmemory_ingestion=False,  # Disabled
        )
        scheduler = MemoryConsolidationScheduler(
            config=config,
            qdrant_client=mock_qdrant,
            redis_client=mock_redis,
        )

        result = scheduler.run_now(dry_run=True, archive=False, promote=False)
        assert result.ingestion_stats is None

    def test_ingestion_dry_run_mode(self, mock_redis, mock_qdrant):
        """Test that ingestion respects dry_run config."""
        config = ConsolidationConfig(
            enabled=True,
            dry_run=False,
            run_tempmemory_ingestion=True,
            tempmemory_ingestion_dry_run=True,  # Always dry run for ingestion
        )
        scheduler = MemoryConsolidationScheduler(
            config=config,
            qdrant_client=mock_qdrant,
            redis_client=mock_redis,
        )

        with patch.object(
            scheduler._ingestion_runner,
            "scan_and_ingest",
            return_value=IngestionStats(dry_run=True),
        ) as mock_ingest:
            scheduler.run_now(dry_run=False, archive=False, promote=False)

            # Should be called with dry_run=True due to config override
            mock_ingest.assert_called_once_with(dry_run=True)

    def test_ingestion_errors_logged_in_result(self, scheduler):
        """Test that ingestion errors are logged in result."""
        error_stats = IngestionStats(
            files_failed=2,
            errors=["File 1 error", "File 2 error"],
        )

        with patch.object(
            scheduler._ingestion_runner, "scan_and_ingest", return_value=error_stats
        ):
            result = scheduler.run_now(dry_run=True, archive=False, promote=False)

            assert len(result.errors) == 2
            assert "File 1 error" in result.errors
            assert "File 2 error" in result.errors

    def test_ingestion_metrics_exported_to_redis(self, mock_redis):
        """Test that ingestion metrics are exported to Redis."""
        config = ConsolidationConfig(
            enabled=True,
            dry_run=False,
            run_tempmemory_ingestion=True,
        )
        scheduler = MemoryConsolidationScheduler(
            config=config,
            qdrant_client=None,
            redis_client=mock_redis,
        )

        stats = IngestionStats(
            total_files_scanned=10,
            files_ingested=7,
            files_failed=1,
            redis_ingested=5,
            qdrant_ingested=7,
        )

        with patch.object(
            scheduler._ingestion_runner, "scan_and_ingest", return_value=stats
        ):
            scheduler.run_now(dry_run=False, archive=False, promote=False)

            # Check that metrics were exported (may be called multiple times)
            assert mock_redis.hset.called
            # Find the call for ingestion metrics
            ingestion_call_found = False
            for call in mock_redis.hset.call_args_list:
                if call[0][0] == "chise:governance:consolidation:metrics:ingestion":
                    ingestion_call_found = True
                    break
            assert ingestion_call_found, "Ingestion metrics should be exported to Redis"

    def test_ingestion_failure_does_not_block_other_steps(self, scheduler):
        """Test that ingestion failure doesn't block archival and promotion."""
        with patch.object(
            scheduler._ingestion_runner,
            "scan_and_ingest",
            side_effect=Exception("Ingestion failed"),
        ):
            with patch.object(scheduler._archiver, "archive_memories") as mock_archive:
                result = scheduler.run_now(dry_run=True, archive=True, promote=False)

                # Archival should still be called
                mock_archive.assert_called_once()
                # Result should have error but still succeed
                assert any("Ingestion failed" in e for e in result.errors)

    def test_config_has_tempmemory_settings(self):
        """Test that ConsolidationConfig has tempmemory settings."""
        config = ConsolidationConfig()

        assert hasattr(config, "run_tempmemory_ingestion")
        assert hasattr(config, "tempmemory_ingestion_dry_run")
        assert hasattr(config, "tempmemory_ingestion_filter_types")

        assert config.run_tempmemory_ingestion is True
        assert config.tempmemory_ingestion_dry_run is False
        assert "decision" in config.tempmemory_ingestion_filter_types
        assert "pattern" in config.tempmemory_ingestion_filter_types
        assert "summary" in config.tempmemory_ingestion_filter_types


class TestIngestionRunnerMocked:
    """Test TempmemoryIngestionRunner with mocked dependencies."""

    def test_scan_and_ingest_returns_stats(self):
        """Test that scan_and_ingest returns IngestionStats."""
        from src.governance.tempmemory.ingestion_runner import TempmemoryIngestionRunner

        runner = TempmemoryIngestionRunner(
            tempmemory_path="docs/tempmemories",
            filter_types=["decision"],
        )

        with patch(
            "src.governance.tempmemory.migration.TempmemoryMigrationEngine"
        ) as MockEngine:
            mock_engine = MagicMock()
            MockEngine.return_value = mock_engine

            # Mock scan_files to return empty list
            mock_engine.scan_files.return_value = []

            stats = runner.scan_and_ingest(dry_run=True)

            assert isinstance(stats, IngestionStats)
            assert stats.dry_run is True
