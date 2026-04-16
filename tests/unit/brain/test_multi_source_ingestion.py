"""
Unit tests for multi-source ingestion into BrainEval.

Tests the BrainEvalIntegration class and related functionality.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory.brain_integration import (
    BrainEvalIntegration,
    IngestionMetrics,
    IngestionResult,
    IngestionSource,
)
from governance.tempmemory.migration import (
    MigrationReport,
    MigrationResult,
    MigrationStatus,
    MigrationTarget,
)


class TestIngestionMetrics:
    """Test IngestionMetrics dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = IngestionMetrics(
            source="test_source",
            items_processed=10,
            items_ingested=8,
            items_failed=2,
            items_deduplicated=1,
            kpi_updates=1,
            duration_seconds=5.5,
        )

        result = metrics.to_dict()

        assert result["source"] == "test_source"
        assert result["items_processed"] == 10
        assert result["items_ingested"] == 8
        assert result["items_failed"] == 2
        assert result["items_deduplicated"] == 1
        assert result["kpi_updates"] == 1
        assert result["duration_seconds"] == 5.5


class TestIngestionResult:
    """Test IngestionResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = IngestionResult(
            ingestion_id="test-id",
            timestamp="2026-03-01T00:00:00Z",
            overall_success=True,
            brain_eval_updated=True,
            mini_eval_updated=False,
        )

        result.metrics.append(
            IngestionMetrics(source="test", items_processed=5, items_ingested=5)
        )

        data = result.to_dict()

        assert data["ingestion_id"] == "test-id"
        assert data["timestamp"] == "2026-03-01T00:00:00Z"
        assert data["overall_success"] is True
        assert data["brain_eval_updated"] is True
        assert data["mini_eval_updated"] is False
        assert len(data["metrics"]) == 1

    def test_to_json(self):
        """Test conversion to JSON."""
        result = IngestionResult(
            ingestion_id="test-id",
            timestamp="2026-03-01T00:00:00Z",
        )

        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["ingestion_id"] == "test-id"


class TestBrainEvalIntegration:
    """Test BrainEvalIntegration class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.scan.return_value = (0, [])
        redis.lrange.return_value = []
        return redis

    @pytest.fixture
    def integration(self, mock_redis):
        """Create a BrainEvalIntegration instance."""
        return BrainEvalIntegration(
            redis_client=mock_redis,
            dry_run=True,
        )

    def test_init(self, integration, mock_redis):
        """Test initialization."""
        assert integration._redis_client == mock_redis
        assert integration._dry_run is True
        assert integration._brain_evaluator is None
        assert integration._mini_eval is None

    def test_ingest_from_migration_report(self, integration, mock_redis):
        """Test ingestion from migration report."""
        # Create a mock migration report
        report = MigrationReport(dry_run=True)
        report.total_files = 3
        report.results = [
            MigrationResult(
                file_path="test1.md",
                status=MigrationStatus.COMPLETED,
                target=MigrationTarget.BOTH,
                redis_success=True,
                qdrant_success=True,
            ),
            MigrationResult(
                file_path="test2.md",
                status=MigrationStatus.COMPLETED,
                target=MigrationTarget.REDIS,
                redis_success=True,
            ),
            MigrationResult(
                file_path="test3.md",
                status=MigrationStatus.FAILED,
                target=MigrationTarget.QDRANT,
                error_message="Test error",
            ),
        ]

        metrics = integration.ingest_from_migration_report(report, update_kpis=False)

        assert metrics.source == IngestionSource.MIGRATION_REPORT.value
        assert metrics.items_processed == 3
        assert metrics.items_ingested == 2
        assert metrics.items_failed == 1

    def test_ingest_from_iterlog(self, integration, mock_redis):
        """Test ingestion from iterlog."""
        # Mock Redis to return some decisions
        decision = {
            "id": "decision-1",
            "decision": "Test decision",
            "rationale": "Test rationale",
            "agent": "test-agent",
            "story_id": "ST-TEST-001",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        mock_redis.lrange.return_value = [json.dumps(decision)]

        metrics = integration.ingest_from_iterlog(
            story_id="ST-TEST-001",
            limit=10,
            update_kpis=False,
        )

        assert metrics.source == IngestionSource.ITERLOG_DECISIONS.value
        assert metrics.items_processed == 1

    def test_ingest_from_tempmemory_files(self, integration, mock_redis):
        """Test ingestion from tempmemory files."""
        # Create a temporary file
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test tempmemory file
            test_file = os.path.join(tmpdir, "test.md")
            with open(test_file, "w") as f:
                f.write("""---
story_id: ST-TEST-001
scope: test
type: decision
---

Test content
""")

            # Update integration to use temp directory (production code expects Path)
            integration._migration_engine._tempmemory_path = Path(tmpdir)

            metrics = integration.ingest_from_tempmemory_files(update_kpis=False)

            assert metrics.source == IngestionSource.TEMPMEMORY_FILES.value
            assert metrics.items_processed == 1
            assert metrics.items_ingested == 1

    def test_extract_story_id(self, integration):
        """Test story ID extraction from file paths."""
        assert (
            integration._extract_story_id("iterlog-ST-MEMORY-003.md") == "ST-MEMORY-003"
        )
        assert (
            integration._extract_story_id("story-ST-DSL-042-decision.md")
            == "ST-DSL-042"
        )
        assert integration._extract_story_id("random-file.md") is None

    def test_get_ingestion_history(self, integration, mock_redis):
        """Test retrieving ingestion history."""
        # Mock Redis to return ingestion results
        result_data = {
            "ingestion_id": "test-id",
            "timestamp": "2026-03-01T00:00:00Z",
            "overall_success": True,
            "brain_eval_updated": True,
            "mini_eval_updated": False,
        }
        mock_redis.scan.return_value = (0, [b"bmad:chiseai:brain:ingestion:test-id"])
        mock_redis.get.return_value = json.dumps(result_data)

        history = integration.get_ingestion_history(limit=10)

        assert len(history) == 1
        assert history[0].ingestion_id == "test-id"

    def test_run_full_ingestion(self, integration, mock_redis):
        """Test full multi-source ingestion."""
        # Mock migration engine
        with patch.object(
            integration._migration_engine,
            "run_migration",
            return_value=MigrationReport(dry_run=True),
        ):
            result = integration.run_full_ingestion(update_kpis=False)

        assert result.ingestion_id is not None
        assert result.timestamp is not None
        assert len(result.metrics) >= 1  # At least migration metrics


class TestIngestionSource:
    """Test IngestionSource enum."""

    def test_source_values(self):
        """Test that all sources have correct values."""
        assert IngestionSource.ITERLOG_DECISIONS.value == "iterlog_decisions"
        assert IngestionSource.TEMPMEMORY_FILES.value == "tempmemory_files"
        assert IngestionSource.REDIS_STATE.value == "redis_state"
        assert IngestionSource.MIGRATION_REPORT.value == "migration_report"
