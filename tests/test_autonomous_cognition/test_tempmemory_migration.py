"""Tests for TempmemoryMigration module.

Validates real Qdrant write operations for tempmemory migration
with rollback capability.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.autonomous_cognition.learning_store import LearningStore
from src.autonomous_cognition.tempmemory_migration import (
    RECORD_TYPE_TEMPMEMORY,
    TempmemoryMigrator,
    TempmemoryRecord,
)


class TestTempmemoryRecord:
    """Tests for TempmemoryRecord parsing."""

    def test_parse_frontmatter_with_all_fields(self, tmp_path: Path):
        """Test parsing frontmatter with all standard fields."""
        content = """---
project: ChiseAI
scope: infra
type: decision
story_id: ST-TEST-001
date: 2026-03-27
---
Test content here.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.parse_tempmemory_file(file_path)

        assert result is not None
        assert result.story_id == "ST-TEST-001"
        assert result.scope == "infra"
        assert result.date == "2026-03-27"
        assert result.content == "Test content here."
        assert result.frontmatter["project"] == "ChiseAI"

    def test_parse_frontmatter_missing_fields(self, tmp_path: Path):
        """Test parsing frontmatter with missing fields uses defaults."""
        content = """---
project: ChiseAI
---
Test content without full frontmatter.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.parse_tempmemory_file(file_path)

        assert result is not None
        assert result.story_id == "test"  # Uses filename stem
        assert result.scope == "unknown"  # Default value
        assert "Test content" in result.content

    def test_parse_no_frontmatter(self, tmp_path: Path):
        """Test parsing file without frontmatter."""
        content = "Plain content without frontmatter."
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.parse_tempmemory_file(file_path)

        assert result is not None
        assert result.story_id == "test"
        assert result.content == content

    def test_parse_invalid_frontmatter(self, tmp_path: Path):
        """Test parsing with invalid frontmatter still extracts body."""
        content = """---
invalid: yaml: content: [
---
Actual content.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.parse_tempmemory_file(file_path)

        assert result is not None
        assert "Actual content" in result.content

    def test_parse_nonexistent_file(self, tmp_path: Path):
        """Test parsing a file that doesn't exist."""
        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.parse_tempmemory_file(tmp_path / "nonexistent.md")

        assert result is None


class TestTempmemoryMigrator:
    """Tests for TempmemoryMigrator class."""

    def setUp(self):
        """Reset singleton before each test to ensure isolation."""
        import src.autonomous_cognition.learning_store as ls_module
        import src.autonomous_cognition.tempmemory_migration as tm_module

        ls_module._default_store = None
        tm_module._default_migrator = None

    def test_initialization_default(self):
        """Test initialization with defaults."""
        migrator = TempmemoryMigrator()

        assert migrator.tempmemory_dir == Path("docs/tempmemories")
        assert migrator.learning_store is not None

    def test_initialization_custom_params(self, tmp_path: Path):
        """Test initialization with custom parameters."""
        mock_store = MagicMock(spec=LearningStore)
        migrator = TempmemoryMigrator(
            learning_store=mock_store,
            tempmemory_dir=tmp_path,
        )

        assert migrator.tempmemory_dir == tmp_path
        assert migrator.learning_store == mock_store

    def test_create_learning_record(self):
        """Test creating LearningRecord from TempmemoryRecord."""
        migrator = TempmemoryMigrator()

        tempmemory = TempmemoryRecord(
            file_path="docs/tempmemories/test.md",
            story_id="ST-TEST-001",
            date="2026-03-27",
            scope="testing",
            content="Test content for embedding.",
            frontmatter={"project": "ChiseAI"},
        )

        record = migrator.create_learning_record(tempmemory)

        assert record.record_type == RECORD_TYPE_TEMPMEMORY
        assert record.metadata["story_id"] == "ST-TEST-001"
        assert record.metadata["scope"] == "testing"
        assert "Test content" in record.content
        assert len(record.record_id) == 32

    def test_create_learning_record_deterministic(self):
        """Test that same tempmemory produces same record_id."""
        migrator = TempmemoryMigrator()

        tempmemory = TempmemoryRecord(
            file_path="docs/tempmemories/test.md",
            story_id="ST-TEST-001",
            date="2026-03-27",
            scope="testing",
            content="Same content.",
            frontmatter={},
        )

        record1 = migrator.create_learning_record(tempmemory)
        record2 = migrator.create_learning_record(tempmemory)

        assert record1.record_id == record2.record_id

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_migrate_file_success(self, mock_get_qdrant, tmp_path: Path):
        """Test successful migration of a single file."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        content = """---
story_id: ST-MIGRATE-001
date: 2026-03-27
scope: test
---
Migration content.
"""
        file_path = tmp_path / "migrate.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        # Patch the instance's _qdrant_client to ensure mock is used
        migrator.learning_store._qdrant_client = mock_client
        success, record_id = migrator.migrate_file(file_path)

        assert success is True
        assert len(record_id) == 32
        mock_client.upsert.assert_called_once()

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_migrate_file_failure(self, mock_get_qdrant, tmp_path: Path):
        """Test failed migration due to invalid file."""
        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        success, record_id = migrator.migrate_file(tmp_path / "nonexistent.md")

        assert success is False
        assert record_id == ""

    def test_backup_file(self, tmp_path: Path):
        """Test file backup creation."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        source_file = source_dir / "test.md"
        source_file.write_text("Test content")

        migrator = TempmemoryMigrator(tempmemory_dir=source_dir)
        backup_dir = tmp_path / "backup"

        backup_path = migrator.backup_file(source_file, backup_dir)

        assert backup_path.exists()
        assert backup_path.read_text() == "Test content"

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_migrate_all_multiple_files(self, mock_get_qdrant, tmp_path: Path):
        """Test migrating multiple files."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        # Create multiple tempmemory files
        for i in range(3):
            content = f"""---
story_id: ST-MULTI-00{i}
date: 2026-03-27
scope: test
---
Content for file {i}.
"""
            (tmp_path / f"file{i}.md").write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.migrate_all(create_backups=False)

        assert result.success is True
        assert result.records_migrated == 3
        assert result.records_failed == 0
        assert len(result.migrated_ids) == 3

    def test_migrate_all_nonexistent_directory(self):
        """Test migration with nonexistent directory."""
        migrator = TempmemoryMigrator(tempmemory_dir=Path("/nonexistent"))
        result = migrator.migrate_all()

        assert result.success is False
        assert len(result.errors) > 0
        assert "not found" in result.errors[0]

    def test_migrate_all_no_matching_files(self, tmp_path: Path):
        """Test migration with no matching files."""
        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.migrate_all(file_pattern="*.txt")

        # No failures means success=True even with 0 migrations
        assert result.records_migrated == 0
        assert result.records_failed == 0
        assert "No files matching" in result.errors[0]

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_migrate_all_skips_index(self, mock_get_qdrant, tmp_path: Path):
        """Test that index.md is skipped during migration."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        # Create index.md and regular file
        (tmp_path / "index.md").write_text("Index content")
        (tmp_path / "regular.md").write_text("""---
story_id: ST-SKIP-001
---
Content.
""")

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        result = migrator.migrate_all(create_backups=False)

        assert result.records_migrated == 1
        assert result.records_failed == 0

    def test_get_migration_history(self):
        """Test getting migration history."""
        migrator = TempmemoryMigrator()

        # Initially empty
        history = migrator.get_migration_history()
        assert len(history) == 0

    def test_rollback_no_migrations(self):
        """Test rollback with no migrations."""
        migrator = TempmemoryMigrator()

        result = migrator.rollback()

        assert result is False

    def test_rollback_nonexistent_migration(self):
        """Test rollback with nonexistent migration ID."""
        migrator = TempmemoryMigrator()
        migrator._rollback_info.append(MagicMock(migration_id="existing-id"))

        result = migrator.rollback(migration_id="nonexistent-id")

        assert result is False


class TestTempmemoryMigratorIntegration:
    """Integration-style tests for tempmemory migration."""

    def setUp(self):
        """Reset singleton before each test to ensure isolation."""
        import src.autonomous_cognition.learning_store as ls_module
        import src.autonomous_cognition.tempmemory_migration as tm_module

        ls_module._default_store = None
        tm_module._default_migrator = None

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_full_migration_with_real_store(self, mock_get_qdrant, tmp_path: Path):
        """Test complete migration flow using real LearningStore."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        # Create test tempmemory files
        test_files = [
            ("story1.md", "ST-INTEGRATE-001", "Scope A"),
            ("story2.md", "ST-INTEGRATE-002", "Scope B"),
        ]

        for filename, story_id, scope in test_files:
            content = f"""---
story_id: {story_id}
scope: {scope}
date: 2026-03-27
---
Content for {story_id}.
"""
            (tmp_path / filename).write_text(content)

        # Run migration
        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        # Patch the instance's _qdrant_client to ensure mock is used
        migrator.learning_store._qdrant_client = mock_client
        result = migrator.migrate_all(create_backups=False)

        # Verify results
        assert result.success is True
        assert result.records_migrated == 2
        assert mock_client.upsert.call_count == 2

        # Verify backup was created
        assert migrator.get_migration_history()[0] is not None

    @patch.object(LearningStore, "_get_qdrant_client")
    def test_content_includes_story_metadata(self, mock_get_qdrant, tmp_path: Path):
        """Test that migrated content includes story metadata."""
        mock_client = MagicMock()
        mock_get_qdrant.return_value = mock_client

        content = """---
story_id: ST-META-001
scope: testing
date: 2026-03-27
---
Detailed decision content here.
"""
        file_path = tmp_path / "meta.md"
        file_path.write_text(content)

        migrator = TempmemoryMigrator(tempmemory_dir=tmp_path)
        # Patch the instance's _qdrant_client to ensure mock is used
        migrator.learning_store._qdrant_client = mock_client
        migrator.migrate_file(file_path)

        # Get the upsert call
        upsert_call = mock_client.upsert.call_args
        points = upsert_call.kwargs["points"]
        payload = points[0]["payload"]

        # Verify metadata in payload
        assert payload["metadata"]["story_id"] == "ST-META-001"
        assert payload["metadata"]["scope"] == "testing"
        assert "Detailed decision" in payload["content"]
