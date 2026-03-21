"""
Tests for Memory Archiver.

Story: ST-GOV-005
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.governance.consolidation.archiver import (
    ArchivedMemory,
    ArchiveStats,
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


class TestTempmemoryArchiveEntry:
    """Tests for TempmemoryArchiveEntry dataclass."""

    def test_to_dict(self):
        """Test tempmemory archive entry serialization."""
        from src.governance.consolidation.archiver import TempmemoryArchiveEntry

        entry = TempmemoryArchiveEntry(
            original_path=Path("docs/tempmemories/test.md"),
            archived_path=Path("docs/tempmemories/archive/test_20240315.md"),
            archived_at=datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC),
            file_size=1024,
            file_hash="abc123def456",
            original_content="test content",
            metadata={"type": "decision"},
        )

        data = entry.to_dict()

        assert data["original_path"] == "docs/tempmemories/test.md"
        assert data["archived_path"] == "docs/tempmemories/archive/test_20240315.md"
        assert data["file_size"] == 1024
        assert data["file_hash"] == "abc123def456"
        assert data["metadata"]["type"] == "decision"

    def test_from_dict(self):
        """Test tempmemory archive entry deserialization."""
        from src.governance.consolidation.archiver import TempmemoryArchiveEntry

        data = {
            "original_path": "docs/tempmemories/test.md",
            "archived_path": "docs/tempmemories/archive/test.md",
            "archived_at": "2024-03-15T10:30:00+00:00",
            "file_size": 2048,
            "file_hash": "xyz789",
            "metadata": {"type": "pattern"},
        }

        entry = TempmemoryArchiveEntry.from_dict(data)

        assert entry.original_path == Path("docs/tempmemories/test.md")
        assert entry.file_size == 2048
        assert entry.file_hash == "xyz789"


class TestTempmemoryArchiveReport:
    """Tests for TempmemoryArchiveReport."""

    def test_default_values(self):
        """Test default report values."""
        from src.governance.consolidation.archiver import TempmemoryArchiveReport

        report = TempmemoryArchiveReport()

        assert report.files_archived == []
        assert report.files_skipped == []
        assert report.errors == []
        assert report.total_size_bytes == 0
        assert report.was_dry_run is True

    def test_to_dict(self):
        """Test report serialization."""
        from src.governance.consolidation.archiver import (
            TempmemoryArchiveEntry,
            TempmemoryArchiveReport,
        )

        entry = TempmemoryArchiveEntry(
            original_path=Path("test.md"),
            archived_path=Path("archive/test.md"),
            archived_at=datetime.now(UTC),
            file_size=100,
            file_hash="hash123",
            original_content="content",
        )

        report = TempmemoryArchiveReport(
            files_archived=[entry],
            files_skipped=["skipped.md"],
            total_size_bytes=100,
            was_dry_run=False,
        )

        data = report.to_dict()

        assert len(data["files_archived"]) == 1
        assert data["files_skipped"] == ["skipped.md"]
        assert data["total_size_bytes"] == 100
        assert data["was_dry_run"] is False

    def test_to_markdown(self):
        """Test markdown report generation."""
        from src.governance.consolidation.archiver import TempmemoryArchiveReport

        report = TempmemoryArchiveReport(
            files_archived=[],
            files_skipped=["skipped.md"],
            was_dry_run=True,
        )

        markdown = report.to_markdown()

        assert "# Tempmemory Archive Report" in markdown
        assert "Dry Run" in markdown
        assert "skipped.md" in markdown


class TestTempmemoryAutoArchive:
    """Tests for tempmemory auto-archive functionality."""

    @pytest.fixture
    def temp_archive_config(self):
        """Create tempmemory archive config."""
        from src.governance.consolidation.config import (
            AutoArchiveMode,
            TempmemoryArchiveConfig,
        )

        return TempmemoryArchiveConfig(
            enabled=True,
            mode=AutoArchiveMode.IMMEDIATE,
            archive_location="docs/tempmemories/archive/",
            generate_reports=False,
        )

    @pytest.fixture
    def archiver_with_tempmemory_config(self, tmp_path, temp_archive_config):
        """Create archiver with tempmemory config."""
        from src.governance.consolidation.config import ConsolidationConfig

        temp_storage = str(tmp_path / "cold_storage")
        config = ConsolidationConfig(
            dry_run=True,
            cold_storage_path=temp_storage,
        )
        config.tempmemory_archive = temp_archive_config
        return MemoryArchiver(config)

    def test_should_archive_immediate_mode(self, archiver_with_tempmemory_config):
        """Test immediate archive mode always returns True."""
        from src.governance.consolidation.config import AutoArchiveMode

        temp_path = Path("docs/tempmemories/test.md")
        config = archiver_with_tempmemory_config._config.tempmemory_archive
        config.mode = AutoArchiveMode.IMMEDIATE

        assert (
            archiver_with_tempmemory_config.should_archive_tempmemory(temp_path) is True
        )

    def test_should_archive_after_n_days_mode(
        self, archiver_with_tempmemory_config, tmp_path
    ):
        """Test after_n_days mode checks file age."""
        from src.governance.consolidation.config import AutoArchiveMode

        # Create a temp file
        temp_file = tmp_path / "test.md"
        temp_file.write_text("test content")

        config = archiver_with_tempmemory_config._config.tempmemory_archive
        config.mode = AutoArchiveMode.AFTER_N_DAYS
        config.delay_days = 7

        # File is new, should not archive
        assert (
            archiver_with_tempmemory_config.should_archive_tempmemory(temp_file)
            is False
        )

    def test_archive_tempmemory_dry_run(
        self, archiver_with_tempmemory_config, tmp_path
    ):
        """Test tempmemory archive in dry run mode."""
        # Create a temp file
        temp_file = tmp_path / "test.md"
        temp_file.write_text("---\ntype: decision\n---\nTest content")

        report = archiver_with_tempmemory_config.archive_tempmemories(
            [temp_file],
            dry_run=True,
        )

        assert report.was_dry_run is True
        assert len(report.files_archived) == 1
        assert report.files_archived[0].original_path == temp_file

    def test_archive_tempmemory_disabled(self, archiver_with_tempmemory_config):
        """Test archiving is skipped when disabled."""
        archiver_with_tempmemory_config._config.tempmemory_archive.enabled = False

        report = archiver_with_tempmemory_config.archive_tempmemories([])

        assert len(report.files_archived) == 0

    def test_extract_tempmemory_metadata(self, archiver_with_tempmemory_config):
        """Test metadata extraction from frontmatter."""
        content = "---\ntype: decision\nstory_id: ST-001\n---\nContent here"

        metadata = archiver_with_tempmemory_config._extract_tempmemory_metadata(content)

        assert metadata.get("type") == "decision"
        assert metadata.get("story_id") == "ST-001"

    def test_get_tempmemory_archive_path(self, archiver_with_tempmemory_config):
        """Test archive path generation."""
        from src.governance.consolidation.config import TempmemoryArchiveConfig

        original_path = Path("docs/tempmemories/test.md")
        archive_dir = Path("docs/tempmemories/archive/")
        config = TempmemoryArchiveConfig()

        archive_path = archiver_with_tempmemory_config._get_tempmemory_archive_path(
            original_path, archive_dir, config
        )

        assert archive_path.parent == archive_dir
        assert archive_path.name.startswith("test_")
        assert archive_path.suffix == ".md"


class TestTempmemoryAutoArchiveWithMockRedis:
    """Tests for tempmemory auto-archive with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def archiver_with_redis(self, mock_redis):
        """Create archiver with mock Redis."""
        from src.governance.consolidation.config import (
            ConsolidationConfig,
            TempmemoryArchiveConfig,
        )

        config = ConsolidationConfig(dry_run=False)
        config.tempmemory_archive = TempmemoryArchiveConfig(
            enabled=True,
            skip_already_archived=True,
        )
        return MemoryArchiver(config, redis_client=mock_redis)

    def test_is_tempmemory_archived_check(self, archiver_with_redis, mock_redis):
        """Test checking if tempmemory is already archived."""
        temp_path = Path("docs/tempmemories/test.md")

        # Mock sismember to return True (already archived)
        mock_redis.sismember.return_value = True

        is_archived = archiver_with_redis._is_tempmemory_archived(temp_path)

        assert is_archived is True
        mock_redis.sismember.assert_called_once()

    def test_track_archived_tempmemory(self, archiver_with_redis, mock_redis):
        """Test tracking archived tempmemory in Redis."""
        from src.governance.consolidation.archiver import TempmemoryArchiveEntry

        temp_path = Path("docs/tempmemories/test.md")
        entry = TempmemoryArchiveEntry(
            original_path=temp_path,
            archived_path=Path("archive/test.md"),
            archived_at=datetime.now(UTC),
            file_size=100,
            file_hash="hash123",
            original_content="content",
        )

        archiver_with_redis._track_archived_tempmemory(temp_path, entry)

        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called()

    def test_skip_already_archived(self, archiver_with_redis, mock_redis, tmp_path):
        """Test that already archived files are skipped."""
        temp_file = tmp_path / "test.md"
        temp_file.write_text("content")

        # Mock sismember to return True (already archived)
        mock_redis.sismember.return_value = True

        report = archiver_with_redis.archive_tempmemories([temp_file])

        assert len(report.files_skipped) == 1
        assert str(temp_file) in report.files_skipped
