"""
Tests for Memory Archiver.

Story: ST-GOV-005
"""

import gzip
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.governance.consolidation.archiver import (
    ArchiveStats,
    ArchivedMemory,
    MemoryArchiver,
)
from src.governance.consolidation.config import (
    ConsolidationConfig,
    MemoryType,
    RetentionPolicy,
)


class TestArchivedMemory:
    """Tests for ArchivedMemory dataclass."""

    def test_to_dict(self):
        """Test archived memory serialization."""
        memory = ArchivedMemory(
            original_id="mem_123",
            content="Test content",
            metadata={"key": "value"},
            archived_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            original_collection="ChiseAI",
            memory_type=MemoryType.DECISION,
            access_count=5,
            relevance_score=0.9,
            tags=["important", "reviewed"],
        )

        data = memory.to_dict()

        assert data["original_id"] == "mem_123"
        assert data["content"] == "Test content"
        assert data["memory_type"] == "decision"
        assert data["access_count"] == 5
        assert "important" in data["tags"]

    def test_from_dict(self):
        """Test archived memory deserialization."""
        data = {
            "original_id": "mem_456",
            "content": "Restored content",
            "metadata": {"source": "test"},
            "archived_at": "2024-02-20T14:00:00+00:00",
            "original_collection": "ChiseAI_golden",
            "memory_type": "pattern",
            "access_count": 3,
            "relevance_score": 0.75,
            "tags": ["example"],
        }

        memory = ArchivedMemory.from_dict(data)

        assert memory.original_id == "mem_456"
        assert memory.content == "Restored content"
        assert memory.memory_type == MemoryType.PATTERN
        assert memory.access_count == 3

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = ArchivedMemory(
            original_id="mem_789",
            content="Roundtrip test",
            metadata={},
            archived_at=datetime.now(UTC),
            original_collection="ChiseAI",
            memory_type=MemoryType.LEARNING,
            access_count=1,
            relevance_score=0.5,
            tags=["test"],
        )

        data = original.to_dict()
        restored = ArchivedMemory.from_dict(data)

        assert restored.original_id == original.original_id
        assert restored.content == original.content
        assert restored.memory_type == original.memory_type


class TestArchiveStats:
    """Tests for ArchiveStats dataclass."""

    def test_default_values(self):
        """Test default archive stats values."""
        stats = ArchiveStats()

        assert stats.memories_scanned == 0
        assert stats.memories_archived == 0
        assert stats.errors == []
        assert stats.was_dry_run is True

    def test_processing_time(self):
        """Test processing time is tracked."""
        stats = ArchiveStats(processing_time_seconds=1.5)

        assert stats.processing_time_seconds == 1.5


class TestMemoryArchiver:
    """Tests for MemoryArchiver."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary directory for cold storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def config(self, temp_storage):
        """Create a test configuration."""
        return ConsolidationConfig(
            dry_run=True,
            cold_storage_path=temp_storage,
            rollback_retention_days=7,
        )

    @pytest.fixture
    def archiver(self, config):
        """Create an archiver instance."""
        return MemoryArchiver(config)

    def test_initialization(self, archiver, config):
        """Test archiver initialization."""
        assert archiver._config == config
        assert archiver._last_stats is None

    def test_dry_run_by_default(self, archiver):
        """Test archiver runs in dry-run mode by default."""
        stats = archiver.archive_memories()

        assert stats.was_dry_run is True

    def test_dry_run_override(self, config):
        """Test dry_run can be overridden."""
        archiver = MemoryArchiver(config)

        stats = archiver.archive_memories(dry_run=False)

        # Should still be dry run since config is True and no actual client
        assert stats.was_dry_run is False

    def test_get_stats_initially_none(self, archiver):
        """Test get_stats returns None before any run."""
        assert archiver.get_stats() is None

    def test_get_stats_after_run(self, archiver):
        """Test get_stats returns stats after a run."""
        archiver.archive_memories()

        stats = archiver.get_stats()
        assert stats is not None
        assert isinstance(stats, ArchiveStats)

    def test_get_cold_storage_size_empty(self, archiver):
        """Test cold storage size is 0 when empty."""
        size = archiver.get_cold_storage_size()

        assert size == 0

    def test_is_eligible_for_archive_age(self, config):
        """Test eligibility based on age."""
        archiver = MemoryArchiver(config)
        policy = RetentionPolicy(
            memory_type=MemoryType.DECISION,
            retention_days=90,
            min_access_count=1,  # Set >0 so 0 access count is eligible
        )

        # Too young
        young_memory = {
            "created_at": datetime.now(UTC) - timedelta(days=30),
            "access_count": 0,
            "tags": [],
        }
        is_eligible, reason = archiver._is_eligible_for_archive(young_memory, policy)
        assert is_eligible is False
        assert "young" in reason.lower()

        # Old enough and low access
        old_memory = {
            "created_at": datetime.now(UTC) - timedelta(days=100),
            "access_count": 0,
            "tags": [],
        }
        is_eligible, reason = archiver._is_eligible_for_archive(old_memory, policy)
        assert is_eligible is True

    def test_is_eligible_for_archive_access_count(self, config):
        """Test eligibility based on access count."""
        archiver = MemoryArchiver(config)
        policy = RetentionPolicy(
            memory_type=MemoryType.PATTERN,
            retention_days=90,
            min_access_count=2,
        )

        # High access count - should be preserved
        memory = {
            "created_at": datetime.now(UTC) - timedelta(days=100),
            "access_count": 5,
            "tags": [],
        }
        is_eligible, reason = archiver._is_eligible_for_archive(memory, policy)
        assert is_eligible is False
        assert "access" in reason.lower()

    def test_is_eligible_for_archive_preserve_tags(self, config):
        """Test eligibility based on preservation tags."""
        archiver = MemoryArchiver(config)
        policy = RetentionPolicy(
            memory_type=MemoryType.INCIDENT,
            retention_days=90,
            preserve_if_tagged=["postmortem", "critical"],
            min_access_count=1,  # Set >0 so 0 access count is eligible
        )

        # Has preservation tag
        memory = {
            "created_at": datetime.now(UTC) - timedelta(days=100),
            "access_count": 0,
            "tags": ["postmortem", "incident"],
        }
        is_eligible, reason = archiver._is_eligible_for_archive(memory, policy)
        assert is_eligible is False
        assert "tag" in reason.lower()

    def test_is_eligible_for_archive_golden_priority(self, config):
        """Test golden priority memories are never archived."""
        archiver = MemoryArchiver(config)
        policy = RetentionPolicy(
            memory_type=MemoryType.DECISION,
            min_access_count=1,  # Set >0 so 0 access count is eligible
        )

        memory = {
            "created_at": datetime.now(UTC) - timedelta(days=365),
            "access_count": 0,
            "tags": [],
            "priority": "golden",
        }
        is_eligible, reason = archiver._is_eligible_for_archive(memory, policy)
        assert is_eligible is False
        assert "golden" in reason.lower()

    def test_determine_memory_type(self, archiver):
        """Test memory type determination from metadata."""
        # Known type
        memory = {"metadata": {"type": "pattern"}}
        assert archiver._determine_memory_type(memory) == MemoryType.PATTERN

        # Unknown type defaults to context
        memory = {"metadata": {"type": "unknown"}}
        assert archiver._determine_memory_type(memory) == MemoryType.CONTEXT

        # Missing metadata defaults to context
        memory = {}
        assert archiver._determine_memory_type(memory) == MemoryType.CONTEXT

    def test_ensure_storage_path(self, archiver):
        """Test cold storage path is created."""
        # Should not raise
        archiver._ensure_storage_path()
        assert Path(archiver._cold_storage_path).exists()

    def test_get_archive_path_format(self, archiver):
        """Test archive path format."""
        date = datetime(2024, 3, 15, tzinfo=UTC)
        path = archiver._get_archive_path(date)

        assert "20240315" in str(path)
        assert path.suffix == ".gz"
        assert path.stem.endswith(".jsonl")


class TestArchiverWithMockClients:
    """Tests for archiver with mocked Redis and Qdrant."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary directory for cold storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def config(self, temp_storage):
        """Create a test configuration."""
        return ConsolidationConfig(
            dry_run=False,
            cold_storage_path=temp_storage,
        )

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def mock_qdrant(self):
        """Create a mock Qdrant client."""
        return MagicMock()

    def test_rollback_data_stored(self, config, mock_redis, mock_qdrant):
        """Test rollback data is stored in Redis."""
        archiver = MemoryArchiver(config, mock_qdrant, mock_redis)

        archived = ArchivedMemory(
            original_id="mem_test",
            content="Test",
            metadata={},
            archived_at=datetime.now(UTC),
            original_collection="ChiseAI",
            memory_type=MemoryType.DECISION,
        )

        archiver._store_rollback_data(archived)

        # Verify setex was called
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert "rollback:mem_test" in call_args[0][0]

    def test_metrics_updated_after_archive(self, config, mock_redis, mock_qdrant):
        """Test metrics are updated after archival."""
        archiver = MemoryArchiver(config, mock_qdrant, mock_redis)

        stats = ArchiveStats(
            memories_archived=10,
            bytes_archived=1024,
            was_dry_run=False,
        )

        archiver._update_metrics(stats)

        mock_redis.hset.assert_called_once()
