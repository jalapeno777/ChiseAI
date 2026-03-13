"""
Unit tests for tempmemory migration module.

Tests the TempmemoryMigrationEngine and related classes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from governance.tempmemory.migration import (
    MigrationReport,
    MigrationResult,
    MigrationStatus,
    MigrationTarget,
    TempmemoryFile,
    TempmemoryMigrationEngine,
)


class TestMigrationStatus:
    """Tests for MigrationStatus enum."""

    def test_status_values(self):
        """Test that all statuses have correct values."""
        assert MigrationStatus.PENDING.value == "pending"
        assert MigrationStatus.IN_PROGRESS.value == "in_progress"
        assert MigrationStatus.COMPLETED.value == "completed"
        assert MigrationStatus.FAILED.value == "failed"
        assert MigrationStatus.SKIPPED.value == "skipped"


class TestMigrationTarget:
    """Tests for MigrationTarget enum."""

    def test_target_values(self):
        """Test that all targets have correct values."""
        assert MigrationTarget.REDIS.value == "redis"
        assert MigrationTarget.QDRANT.value == "qdrant"
        assert MigrationTarget.BOTH.value == "both"


class TestTempmemoryFile:
    """Tests for TempmemoryFile dataclass."""

    def test_basic_properties(self):
        """Test basic property access."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={
                "story_id": "ST-TEST-001",
                "scope": "test",
                "type": "decision",
                "date": "2026-03-01",
                "project": "ChiseAI",
            },
            content="Test content",
            has_frontmatter=True,
        )

        assert temp_file.story_id == "ST-TEST-001"
        assert temp_file.scope == "test"
        assert temp_file.memory_type == "decision"
        assert temp_file.date == "2026-03-01"
        assert temp_file.project == "ChiseAI"

    def test_missing_frontmatter(self):
        """Test handling of missing frontmatter fields."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={},
            content="Test content",
            has_frontmatter=False,
        )

        assert temp_file.story_id is None
        assert temp_file.scope is None
        assert temp_file.memory_type is None

    def test_determine_target_decision(self):
        """Test target determination for decision type."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={"type": "decision"},
            content="Test",
        )
        assert temp_file.determine_target() == MigrationTarget.BOTH

    def test_determine_target_pattern(self):
        """Test target determination for pattern type."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={"type": "pattern"},
            content="Test",
        )
        assert temp_file.determine_target() == MigrationTarget.BOTH

    def test_determine_target_summary(self):
        """Test target determination for summary type."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={"type": "summary"},
            content="Test",
        )
        assert temp_file.determine_target() == MigrationTarget.QDRANT

    def test_determine_target_default(self):
        """Test target determination for unknown type."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={},
            content="Test",
        )
        assert temp_file.determine_target() == MigrationTarget.BOTH

    def test_to_redis_entry(self):
        """Test conversion to Redis entry format."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={
                "story_id": "ST-TEST-001",
                "scope": "test",
                "type": "decision",
                "date": "2026-03-01",
                "project": "ChiseAI",
            },
            content="Test content",
        )

        entry = temp_file.to_redis_entry()

        assert entry["story_id"] == "ST-TEST-001"
        assert entry["scope"] == "test"
        assert entry["type"] == "decision"
        assert entry["content"] == "Test content"
        assert entry["source_file"] == "docs/tempmemories/test.md"
        assert "migrated_at" in entry

    def test_to_qdrant_entry(self):
        """Test conversion to Qdrant entry format."""
        temp_file = TempmemoryFile(
            path=Path("/test/file.md"),
            relative_path="docs/tempmemories/test.md",
            frontmatter={
                "story_id": "ST-TEST-001",
                "scope": "test",
                "type": "decision",
            },
            content="Test content",
        )

        entry = temp_file.to_qdrant_entry()

        assert entry["content"] == "Test content"
        assert entry["metadata"]["story_id"] == "ST-TEST-001"
        assert entry["metadata"]["scope"] == "test"
        assert entry["metadata"]["source_file"] == "docs/tempmemories/test.md"


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = MigrationResult(
            file_path="docs/tempmemories/test.md",
            status=MigrationStatus.COMPLETED,
            target=MigrationTarget.BOTH,
            redis_success=True,
            qdrant_success=True,
        )

        assert result.file_path == "docs/tempmemories/test.md"
        assert result.status == MigrationStatus.COMPLETED
        assert result.target == MigrationTarget.BOTH
        assert result.redis_success is True
        assert result.qdrant_success is True


class TestMigrationReport:
    """Tests for MigrationReport dataclass."""

    def test_basic_creation(self):
        """Test basic report creation."""
        report = MigrationReport(
            total_files=10,
            scanned_files=10,
            migrated_files=8,
            failed_files=1,
            skipped_files=1,
            dry_run=True,
            duration_seconds=1.5,
        )

        assert report.total_files == 10
        assert report.migrated_files == 8
        assert report.failed_files == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = MigrationResult(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
            target=MigrationTarget.BOTH,
        )
        report = MigrationReport(
            total_files=1,
            migrated_files=1,
            results=[result],
        )

        data = report.to_dict()

        assert data["total_files"] == 1
        assert data["migrated_files"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["file_path"] == "test.md"

    def test_to_json(self):
        """Test conversion to JSON."""
        report = MigrationReport(total_files=1, migrated_files=1)
        json_str = report.to_json()

        assert "total_files" in json_str
        assert "migrated_files" in json_str

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert data["total_files"] == 1


class TestTempmemoryMigrationEngine:
    """Tests for TempmemoryMigrationEngine."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def mock_qdrant(self):
        """Create a mock Qdrant client."""
        return MagicMock()

    def test_initialization(self, mock_redis, mock_qdrant):
        """Test engine initialization."""
        engine = TempmemoryMigrationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            dry_run=True,
        )

        assert engine._redis_client == mock_redis
        assert engine._qdrant_client == mock_qdrant
        assert engine._dry_run is True

    def test_scan_files_empty_directory(self, temp_dir):
        """Test scanning empty directory."""
        engine = TempmemoryMigrationEngine(tempmemory_path=temp_dir)
        files = engine.scan_files()

        assert files == []

    def test_scan_files_with_content(self, temp_dir):
        """Test scanning directory with files."""
        # Create test files
        (temp_dir / "test1.md").write_text("---\nstory_id: ST-001\n---\nContent")
        (temp_dir / "test2.md").write_text("---\nstory_id: ST-002\n---\nContent")
        (temp_dir / "README.md").write_text("# README")  # Should be skipped

        engine = TempmemoryMigrationEngine(tempmemory_path=temp_dir)
        files = engine.scan_files()

        assert len(files) == 2
        assert all(f.path.name != "README.md" for f in files)

    def test_scan_files_skips_archive(self, temp_dir):
        """Test that archive directory is skipped."""
        # Create archive directory with file
        archive_dir = temp_dir / "archive"
        archive_dir.mkdir()
        (archive_dir / "archived.md").write_text("---\nstory_id: ST-001\n---\nContent")

        # Create regular file
        (temp_dir / "regular.md").write_text("---\nstory_id: ST-002\n---\nContent")

        engine = TempmemoryMigrationEngine(
            tempmemory_path=temp_dir,
            archive_path=archive_dir,
        )
        files = engine.scan_files()

        assert len(files) == 1
        assert files[0].path.name == "regular.md"

    def test_parse_file_with_frontmatter(self, temp_dir):
        """Test parsing file with YAML frontmatter."""
        file_path = temp_dir / "test.md"
        file_path.write_text("""---
story_id: ST-TEST-001
scope: test
type: decision
date: 2026-03-01
project: ChiseAI
---

# Test Content

This is test content.
""")

        engine = TempmemoryMigrationEngine(tempmemory_path=temp_dir)
        temp_file = engine._parse_file(file_path)

        assert temp_file.has_frontmatter is True
        assert temp_file.story_id == "ST-TEST-001"
        assert temp_file.scope == "test"
        assert temp_file.memory_type == "decision"
        assert "Test Content" in temp_file.content

    def test_parse_file_without_frontmatter(self, temp_dir):
        """Test parsing file without YAML frontmatter."""
        file_path = temp_dir / "test.md"
        file_path.write_text("# Just content\n\nNo frontmatter here.")

        engine = TempmemoryMigrationEngine(tempmemory_path=temp_dir)
        temp_file = engine._parse_file(file_path)

        assert temp_file.has_frontmatter is False
        assert temp_file.frontmatter == {}

    def test_parse_file_invalid_yaml(self, temp_dir):
        """Test parsing file with invalid YAML frontmatter."""
        file_path = temp_dir / "test.md"
        file_path.write_text("---\ninvalid: yaml: : :\n---\nContent")

        engine = TempmemoryMigrationEngine(tempmemory_path=temp_dir)
        temp_file = engine._parse_file(file_path)

        # Should still parse but without frontmatter
        assert temp_file.has_frontmatter is False

    def test_migrate_file_to_redis(self, mock_redis, temp_dir):
        """Test migrating file to Redis."""
        temp_file = TempmemoryFile(
            path=temp_dir / "test.md",
            relative_path="test.md",
            frontmatter={"story_id": "ST-001", "type": "decision"},
            content="Test content",
        )

        engine = TempmemoryMigrationEngine(
            redis_client=mock_redis,
            dry_run=False,
        )
        result = engine.migrate_file(temp_file)

        assert result.status == MigrationStatus.COMPLETED
        assert result.redis_success is True
        mock_redis.hset.assert_called_once()

    def test_migrate_file_to_qdrant(self, mock_qdrant, temp_dir):
        """Test migrating file to Qdrant."""
        temp_file = TempmemoryFile(
            path=temp_dir / "test.md",
            relative_path="test.md",
            frontmatter={"story_id": "ST-001", "type": "summary"},
            content="Test content",
        )

        engine = TempmemoryMigrationEngine(
            qdrant_client=mock_qdrant,
            dry_run=False,
        )
        result = engine.migrate_file(temp_file)

        assert result.status == MigrationStatus.COMPLETED
        assert result.qdrant_success is True
        mock_qdrant.upsert.assert_called_once()

    def test_migrate_file_dry_run(self, mock_redis, temp_dir):
        """Test that dry_run doesn't modify Redis."""
        temp_file = TempmemoryFile(
            path=temp_dir / "test.md",
            relative_path="test.md",
            frontmatter={"story_id": "ST-001", "type": "decision"},
            content="Test content",
        )

        engine = TempmemoryMigrationEngine(
            redis_client=mock_redis,
            dry_run=True,
        )
        result = engine.migrate_file(temp_file)

        assert result.status == MigrationStatus.COMPLETED
        mock_redis.hset.assert_not_called()

    def test_migrate_file_no_clients(self, temp_dir):
        """Test migration with no clients available."""
        temp_file = TempmemoryFile(
            path=temp_dir / "test.md",
            relative_path="test.md",
            frontmatter={"story_id": "ST-001", "type": "decision"},
            content="Test content",
        )

        engine = TempmemoryMigrationEngine(dry_run=False)
        result = engine.migrate_file(temp_file)

        # Should fail since no clients available
        assert result.status == MigrationStatus.FAILED

    def test_run_migration(self, temp_dir, mock_redis):
        """Test running full migration."""
        # Create test files
        (temp_dir / "test1.md").write_text(
            "---\nstory_id: ST-001\ntype: decision\n---\nContent 1"
        )
        (temp_dir / "test2.md").write_text(
            "---\nstory_id: ST-002\ntype: pattern\n---\nContent 2"
        )

        engine = TempmemoryMigrationEngine(
            tempmemory_path=temp_dir,
            redis_client=mock_redis,
            dry_run=False,
        )
        report = engine.run_migration()

        assert report.total_files == 2
        assert report.scanned_files == 2
        assert report.migrated_files == 2
        assert report.failed_files == 0

    def test_get_file_status(self, mock_redis):
        """Test getting file status from Redis."""
        mock_redis.hget.return_value = json.dumps({"status": "completed"})

        engine = TempmemoryMigrationEngine(redis_client=mock_redis)
        status = engine.get_file_status("test.md")

        assert status == MigrationStatus.COMPLETED

    def test_get_file_status_not_found(self, mock_redis):
        """Test getting status for non-existent file."""
        mock_redis.hget.return_value = None

        engine = TempmemoryMigrationEngine(redis_client=mock_redis)
        status = engine.get_file_status("test.md")

        assert status is None

    def test_update_file_status(self, mock_redis):
        """Test updating file status."""
        engine = TempmemoryMigrationEngine(
            redis_client=mock_redis,
            dry_run=False,
        )
        result = engine.update_file_status(
            "test.md",
            MigrationStatus.COMPLETED,
            {"story_id": "ST-001"},
        )

        assert result is True
        mock_redis.hset.assert_called_once()

    def test_update_file_status_dry_run(self, mock_redis):
        """Test that update respects dry_run."""
        engine = TempmemoryMigrationEngine(
            redis_client=mock_redis,
            dry_run=True,
        )
        result = engine.update_file_status("test.md", MigrationStatus.COMPLETED)

        assert result is False
        mock_redis.hset.assert_not_called()
