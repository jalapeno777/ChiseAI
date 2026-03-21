"""
Tests for Rollback Manager.

Story: ST-GOV-005
"""

import gzip
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.governance.consolidation.archiver import ArchivedMemory
from src.governance.consolidation.config import ConsolidationConfig, MemoryType
from src.governance.consolidation.rollback import (
    RollbackManager,
    RollbackOperation,
    RollbackStats,
    RollbackWindow,
)


class TestRollbackOperation:
    """Tests for RollbackOperation dataclass."""

    def test_default_values(self):
        """Test default rollback operation values."""
        op = RollbackOperation(
            memory_id="mem_123",
            restored_at=datetime.now(UTC),
            restored_from="/path/to/archive.gz",
            target_collection="ChiseAI",
        )

        assert op.success is True
        assert op.error is None

    def test_failed_operation(self):
        """Test failed rollback operation."""
        op = RollbackOperation(
            memory_id="mem_456",
            restored_at=datetime.now(UTC),
            restored_from="/path/to/archive.gz",
            target_collection="ChiseAI",
            success=False,
            error="Memory not found in archive",
        )

        assert op.success is False
        assert op.error is not None
        assert "not found" in op.error


class TestRollbackStats:
    """Tests for RollbackStats dataclass."""

    def test_default_values(self):
        """Test default rollback stats values."""
        stats = RollbackStats()

        assert stats.operations_requested == 0
        assert stats.operations_succeeded == 0
        assert stats.operations_failed == 0
        assert stats.rollback_time_seconds == 0.0

    def test_success_rate(self):
        """Test rollback success rate calculation."""
        stats = RollbackStats(
            operations_requested=10,
            operations_succeeded=8,
            operations_failed=2,
        )

        success_rate = stats.operations_succeeded / stats.operations_requested
        assert success_rate == 0.8


class TestRollbackWindow:
    """Tests for RollbackWindow dataclass."""

    def test_default_values(self):
        """Test default rollback window values."""
        now = datetime.now(UTC)
        window = RollbackWindow(
            start_date=now - timedelta(days=7),
            end_date=now,
            available_memories=0,
        )

        assert window.available_memories == 0
        assert window.archive_files == []

    def test_window_duration(self):
        """Test rollback window duration."""
        now = datetime.now(UTC)
        window = RollbackWindow(
            start_date=now - timedelta(days=7),
            end_date=now,
            available_memories=100,
        )

        duration = (window.end_date - window.start_date).days
        assert duration == 7


class TestRollbackManager:
    """Tests for RollbackManager."""

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
    def manager(self, config):
        """Create a rollback manager instance."""
        return RollbackManager(config)

    def test_initialization(self, manager, config):
        """Test manager initialization."""
        assert manager._config == config
        assert manager._last_stats is None

    def test_can_rollback_no_redis(self, manager):
        """Test can_rollback returns False without Redis."""
        result = manager.can_rollback("mem_123")

        assert result is False

    def test_get_stats_initially_none(self, manager):
        """Test get_stats returns None before any operation."""
        assert manager.get_stats() is None

    def test_get_rollback_window_no_redis(self, manager):
        """Test get_rollback_window works without Redis."""
        window = manager.get_rollback_window()

        assert window is not None
        assert window.available_memories == 0

    def test_rollback_memory_no_redis(self, manager):
        """Test rollback_memory without Redis returns error."""
        stats = manager.rollback_memory("mem_123")

        assert stats.operations_failed == 1
        assert len(stats.errors) > 0

    def test_rollback_memory_dry_run(self, manager):
        """Test rollback in dry-run mode."""
        # Even without rollback data, dry run should complete
        stats = manager.rollback_memory("mem_123", dry_run=True)

        assert stats.operations_requested == 1

    def test_rollback_batch_empty(self, manager):
        """Test rollback with empty batch."""
        stats = manager.rollback_batch([])

        assert stats.operations_requested == 0
        assert stats.operations_succeeded == 0

    def test_validate_rollback_performance_no_run(self, manager):
        """Test validation without any run."""
        result = manager.validate_rollback_performance()

        assert result["valid"] is False
        assert "No rollback" in result["reason"]


class TestRollbackManagerWithMockRedis:
    """Tests for RollbackManager with mocked Redis."""

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
            rollback_retention_days=7,
        )

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client with rollback data."""
        mock = MagicMock()

        # Set up rollback data
        rollback_data = {
            "archived_at": datetime.now(UTC).isoformat(),
            "original_collection": "ChiseAI",
            "archive_file": "/tmp/test_archive.gz",
            "memory_type": "decision",
        }
        mock.get.return_value = json.dumps(rollback_data)

        return mock

    @pytest.fixture
    def manager(self, config, mock_redis):
        """Create a rollback manager with mocked Redis."""
        return RollbackManager(config, redis_client=mock_redis)

    def test_can_rollback_with_redis(self, manager, mock_redis, temp_storage):
        """Test can_rollback with Redis and valid data."""
        # Create archive file
        archive_path = Path(temp_storage) / "memories_20240315.jsonl.gz"
        archived = ArchivedMemory(
            original_id="mem_123",
            content="Test content",
            metadata={},
            archived_at=datetime.now(UTC),
            original_collection="ChiseAI",
            memory_type=MemoryType.DECISION,
        )

        with gzip.open(archive_path, "wt", encoding="utf-8") as f:
            f.write(json.dumps(archived.to_dict()) + "\n")

        # Update mock to return correct archive path
        rollback_data = {
            "archived_at": datetime.now(UTC).isoformat(),
            "original_collection": "ChiseAI",
            "archive_file": str(archive_path),
            "memory_type": "decision",
        }
        mock_redis.get.return_value = json.dumps(rollback_data)

        result = manager.can_rollback("mem_123")

        assert result is True

    def test_can_rollback_expired_window(self, manager, mock_redis):
        """Test can_rollback with expired window."""
        # Archived 10 days ago (outside 7-day window)
        old_date = datetime.now(UTC) - timedelta(days=10)
        rollback_data = {
            "archived_at": old_date.isoformat(),
            "original_collection": "ChiseAI",
            "archive_file": "/tmp/test.gz",
            "memory_type": "decision",
        }
        mock_redis.get.return_value = json.dumps(rollback_data)

        result = manager.can_rollback("mem_old")

        assert result is False

    def test_get_rollback_window_with_data(self, config, mock_redis):
        """Test get_rollback_window with Redis data."""
        # Mock scan to return some keys
        mock_redis.scan.return_value = (0, [b"rollback:mem_1", b"rollback:mem_2"])
        mock_redis.get.return_value = json.dumps(
            {
                "archived_at": datetime.now(UTC).isoformat(),
                "archive_file": "/tmp/test.gz",
            }
        )

        manager = RollbackManager(config, redis_client=mock_redis)
        window = manager.get_rollback_window()

        assert window.available_memories == 2


class TestRollbackPerformance:
    """Tests for rollback performance validation."""

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
            rollback_retention_days=7,
        )

    def test_rollback_time_under_5_minutes(self, config):
        """Test rollback completes within 5 minutes."""
        manager = RollbackManager(config)

        # Simulate fast rollback
        stats = RollbackStats(
            operations_succeeded=1,
            rollback_time_seconds=30.0,  # 30 seconds
        )
        manager._last_stats = stats

        validation = manager.validate_rollback_performance()

        assert validation["valid"] is True
        assert validation["rollback_time_seconds"] < 300

    def test_rollback_time_over_5_minutes_fails(self, config):
        """Test rollback over 5 minutes fails validation."""
        manager = RollbackManager(config)

        # Simulate slow rollback
        stats = RollbackStats(
            operations_succeeded=1,
            rollback_time_seconds=400.0,  # Over 5 minutes
        )
        manager._last_stats = stats

        validation = manager.validate_rollback_performance()

        assert validation["valid"] is False
        assert validation["rollback_time_seconds"] >= 300


class TestTempmemoryRollback:
    """Tests for tempmemory rollback functionality (ST-MEMORY-INGEST-003)."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return ConsolidationConfig(
            dry_run=True,
            rollback_retention_days=7,
        )

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    def test_can_rollback_tempmemory(self, config, tmp_path):
        """Test checking if tempmemory can be rolled back."""
        manager = RollbackManager(config)

        # Create an archived file
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        archived_file = archive_dir / "test.md"
        archived_file.write_text("content")

        # Should be able to rollback
        assert manager.can_rollback_tempmemory(archived_file) is True

    def test_cannot_rollback_missing_file(self, config, tmp_path):
        """Test cannot rollback if file doesn't exist."""
        manager = RollbackManager(config)

        missing_file = tmp_path / "missing.md"

        assert manager.can_rollback_tempmemory(missing_file) is False

    def test_rollback_tempmemory_dry_run(self, config, tmp_path):
        """Test tempmemory rollback in dry run mode."""
        manager = RollbackManager(config)

        # Create an archived file
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        archived_file = archive_dir / "test.md"
        archived_file.write_text("""---
type: decision
original_path: docs/tempmemories/test.md
---
Test content
""")

        # Rollback in dry run mode
        stats = manager.rollback_tempmemory(archived_file, dry_run=True)

        assert stats.operations_succeeded == 1
        # File should still exist in dry run
        assert archived_file.exists()

    def test_rollback_tempmemory_batch(self, config, tmp_path):
        """Test rolling back multiple archived tempmemories."""
        manager = RollbackManager(config)

        # Create archived files
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        files = []
        for i in range(3):
            archived_file = archive_dir / f"test_{i}.md"
            archived_file.write_text(f"""---
type: decision
original_path: docs/tempmemories/test_{i}.md
---
Test content {i}
""")
            files.append(archived_file)

        # Rollback batch
        stats = manager.rollback_tempmemory_batch(files, dry_run=True)

        assert stats.operations_requested == 3
        assert stats.operations_succeeded == 3

    def test_get_tempmemory_rollback_window(self, config, tmp_path):
        """Test getting tempmemory rollback window."""
        manager = RollbackManager(config)

        # Create archive directory with files
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        archived_file = archive_dir / "test.md"
        archived_file.write_text("content")

        window = manager.get_tempmemory_rollback_window(archive_dir)

        assert window.available_memories == 1
        assert len(window.archive_files) == 1

    def test_extract_original_path_from_frontmatter(self, config):
        """Test extracting original path from frontmatter."""
        manager = RollbackManager(config)

        content = """---
type: decision
original_path: docs/tempmemories/original.md
---
Content here
"""

        original_path = manager._extract_original_path(content, Path("archive/test.md"))

        assert original_path == Path("docs/tempmemories/original.md")

    def test_extract_original_path_no_frontmatter(self, config):
        """Test extracting original path when no frontmatter."""
        manager = RollbackManager(config)

        content = "Just content, no frontmatter"

        original_path = manager._extract_original_path(content, Path("archive/test.md"))

        assert original_path is None

    def test_cleanup_tempmemory_rollback_data(self, config, tmp_path, mock_redis):
        """Test cleaning up tempmemory rollback data."""
        manager = RollbackManager(config, redis_client=mock_redis)

        archived_path = tmp_path / "test.md"

        manager._cleanup_tempmemory_rollback_data(archived_path)

        mock_redis.srem.assert_called_once()
        mock_redis.delete.assert_called_once()
