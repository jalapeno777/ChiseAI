"""
Unit tests for tempmemory archive and reconciliation module.

Tests the TempmemoryArchiveReconciler and related classes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from governance.tempmemory.archive_reconcile import (
    ArchiveResult,
    ReconciliationIssue,
    ReconciliationReport,
    TempmemoryArchiveReconciler,
)


class TestArchiveResult:
    """Tests for ArchiveResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = ArchiveResult(
            source_path="docs/tempmemories/test.md",
            archive_path="docs/tempmemories/archive/test.md",
            success=True,
        )

        assert result.source_path == "docs/tempmemories/test.md"
        assert result.archive_path == "docs/tempmemories/archive/test.md"
        assert result.success is True
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed result creation."""
        result = ArchiveResult(
            source_path="docs/tempmemories/test.md",
            archive_path="",
            success=False,
            error_message="Permission denied",
        )

        assert result.success is False
        assert result.error_message == "Permission denied"


class TestReconciliationIssue:
    """Tests for ReconciliationIssue dataclass."""

    def test_basic_creation(self):
        """Test basic issue creation."""
        issue = ReconciliationIssue(
            issue_type="orphaned",
            file_path="docs/tempmemories/test.md",
            details={"reason": "Not tracked"},
        )

        assert issue.issue_type == "orphaned"
        assert issue.file_path == "docs/tempmemories/test.md"
        assert issue.details["reason"] == "Not tracked"


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_basic_creation(self):
        """Test basic report creation."""
        report = ReconciliationReport(
            total_files_in_tempmemory=100,
            total_files_in_archive=50,
            total_tracked=95,
        )

        assert report.total_files_in_tempmemory == 100
        assert report.total_files_in_archive == 50
        assert report.total_tracked == 95

    def test_to_dict(self):
        """Test conversion to dictionary."""
        issue = ReconciliationIssue(
            issue_type="orphaned",
            file_path="test.md",
            details={"reason": "Not tracked"},
        )
        report = ReconciliationReport(
            total_files_in_tempmemory=10,
            orphaned_files=[issue],
        )

        data = report.to_dict()

        assert data["total_files_in_tempmemory"] == 10
        assert data["orphaned_count"] == 1
        assert len(data["orphaned_files"]) == 1
        assert data["orphaned_files"][0]["file_path"] == "test.md"

    def test_to_json(self):
        """Test conversion to JSON."""
        report = ReconciliationReport(
            total_files_in_tempmemory=10,
            total_tracked=8,
        )
        json_str = report.to_json()

        assert "total_files_in_tempmemory" in json_str
        assert "total_tracked" in json_str


class TestTempmemoryArchiveReconciler:
    """Tests for TempmemoryArchiveReconciler."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tempmemory_path = Path(tmpdir) / "tempmemories"
            archive_path = Path(tmpdir) / "archive"
            tempmemory_path.mkdir()
            archive_path.mkdir()
            yield tempmemory_path, archive_path

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    def test_initialization(self, temp_dirs, mock_redis):
        """Test reconciler initialization."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=True,
        )

        assert reconciler._tempmemory_path == tempmemory_path
        assert reconciler._archive_path == archive_path
        assert reconciler._dry_run is True

    def test_archive_file_success(self, temp_dirs, mock_redis):
        """Test successful file archiving."""
        tempmemory_path, archive_path = temp_dirs

        # Create test file
        source_file = tempmemory_path / "test.md"
        source_file.write_text("Test content")

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=False,
        )

        result = reconciler.archive_file(source_file)

        assert result.success is True
        assert Path(result.archive_path).exists()
        assert not source_file.exists()  # Original should be removed

    def test_archive_file_not_found(self, temp_dirs, mock_redis):
        """Test archiving non-existent file."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        result = reconciler.archive_file("/nonexistent/file.md")

        assert result.success is False
        assert "does not exist" in result.error_message

    def test_archive_file_preserves_structure(self, temp_dirs, mock_redis):
        """Test that subdirectory structure is preserved."""
        tempmemory_path, archive_path = temp_dirs

        # Create file in subdirectory
        subdir = tempmemory_path / "subdir"
        subdir.mkdir()
        source_file = subdir / "test.md"
        source_file.write_text("Test content")

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=False,
        )

        result = reconciler.archive_file(source_file, preserve_structure=True)

        assert result.success is True
        expected_archive = archive_path / "subdir" / "test.md"
        assert Path(result.archive_path) == expected_archive
        assert expected_archive.exists()

    def test_archive_file_dry_run(self, temp_dirs, mock_redis):
        """Test that dry_run doesn't move files."""
        tempmemory_path, archive_path = temp_dirs

        source_file = tempmemory_path / "test.md"
        source_file.write_text("Test content")

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=True,
        )

        result = reconciler.archive_file(source_file)

        assert result.success is True
        assert source_file.exists()  # Original should still exist

    def test_reconcile_empty(self, temp_dirs, mock_redis):
        """Test reconciliation with empty directories."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        report = reconciler.reconcile()

        assert report.total_files_in_tempmemory == 0
        assert report.total_files_in_archive == 0
        assert len(report.orphaned_files) == 0

    def test_reconcile_detects_orphaned(self, temp_dirs, mock_redis):
        """Test detection of orphaned files."""
        tempmemory_path, archive_path = temp_dirs

        # Create file in tempmemory (not tracked)
        source_file = tempmemory_path / "orphaned.md"
        source_file.write_text("---\nstory_id: ST-001\n---\nContent")

        # Mock Redis to return empty (no tracked files)
        mock_redis.hgetall.return_value = {}

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        report = reconciler.reconcile()

        assert report.total_files_in_tempmemory == 1
        assert len(report.orphaned_files) == 1
        assert report.orphaned_files[0].file_path == str(source_file)

    def test_reconcile_detects_missing(self, temp_dirs, mock_redis):
        """Test detection of missing files."""
        tempmemory_path, archive_path = temp_dirs

        # Mock Redis to show tracked file that doesn't exist
        mock_redis.hgetall.return_value = {
            "docs/tempmemories/missing.md": json.dumps({"status": "completed"}),
        }

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        report = reconciler.reconcile()

        assert len(report.missing_files) == 1
        assert report.missing_files[0].file_path == "docs/tempmemories/missing.md"

    def test_reconcile_detects_mismatched(self, temp_dirs, mock_redis):
        """Test detection of mismatched files."""
        tempmemory_path, archive_path = temp_dirs

        # Create file in tempmemory
        source_file = tempmemory_path / "completed.md"
        source_file.write_text("---\nstory_id: ST-001\n---\nContent")

        # Mock Redis to show file as completed
        mock_redis.hgetall.return_value = {
            str(source_file): json.dumps({"status": "completed"}),
        }

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        report = reconciler.reconcile()

        assert len(report.mismatched_files) == 1
        assert report.mismatched_files[0].file_path == str(source_file)

    def test_auto_fix_issues(self, temp_dirs, mock_redis):
        """Test auto-fixing issues."""
        tempmemory_path, archive_path = temp_dirs

        # Create file marked as completed
        source_file = tempmemory_path / "completed.md"
        source_file.write_text("---\nstory_id: ST-001\n---\nContent")

        # Mock Redis
        mock_redis.hgetall.return_value = {
            str(source_file): json.dumps({"status": "completed"}),
        }

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=False,
        )

        # Run reconcile first
        report = reconciler.reconcile()

        # Auto-fix should archive the completed file
        result = reconciler.auto_fix_issues(report)

        assert result["fixes_applied"] == 1
        assert result["archived"] == 1
        assert not source_file.exists()  # Should be archived

    def test_auto_fix_dry_run(self, temp_dirs, mock_redis):
        """Test that auto-fix respects dry_run."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=True,
        )

        result = reconciler.auto_fix_issues()

        assert result["dry_run"] is True
        assert result["fixes_applied"] == 0

    def test_get_archive_manifest(self, temp_dirs, mock_redis):
        """Test getting archive manifest."""
        tempmemory_path, archive_path = temp_dirs

        # Create archived files
        (archive_path / "file1.md").write_text("Content 1")
        (archive_path / "file2.md").write_text("Content 2")

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        manifest = reconciler.get_archive_manifest()

        assert manifest["total_files"] == 2
        assert len(manifest["files"]) == 2
        assert manifest["archive_path"] == str(archive_path)

    def test_get_archive_manifest_empty(self, temp_dirs, mock_redis):
        """Test getting manifest from empty archive."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
        )

        manifest = reconciler.get_archive_manifest()

        assert manifest["total_files"] == 0
        assert manifest["files"] == []

    def test_save_archive_manifest(self, temp_dirs, mock_redis):
        """Test saving archive manifest."""
        tempmemory_path, archive_path = temp_dirs

        # Create archived file
        (archive_path / "file1.md").write_text("Content")

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=False,
        )

        result = reconciler.save_archive_manifest()

        assert result is True
        manifest_path = archive_path / "archive_manifest.json"
        assert manifest_path.exists()

        # Verify content
        import json

        with open(manifest_path) as f:
            data = json.load(f)
        assert data["total_files"] == 1

    def test_save_archive_manifest_dry_run(self, temp_dirs, mock_redis):
        """Test that save respects dry_run."""
        tempmemory_path, archive_path = temp_dirs

        reconciler = TempmemoryArchiveReconciler(
            tempmemory_path=tempmemory_path,
            archive_path=archive_path,
            redis_client=mock_redis,
            dry_run=True,
        )

        result = reconciler.save_archive_manifest()

        assert result is False
