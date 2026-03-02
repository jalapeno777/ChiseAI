"""
Unit tests for tempmemory tracking module.

Tests the TempmemoryTracker and related classes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from governance.tempmemory.migration import MigrationStatus
from governance.tempmemory.tracking import (
    FileTrackingRecord,
    TempmemoryTracker,
    TrackingReportType,
    TrackingSummary,
)


class TestTrackingReportType:
    """Tests for TrackingReportType enum."""

    def test_report_type_values(self):
        """Test that all report types have correct values."""
        assert TrackingReportType.SUMMARY.value == "summary"
        assert TrackingReportType.DETAILED.value == "detailed"
        assert TrackingReportType.FAILED_ONLY.value == "failed_only"
        assert TrackingReportType.PENDING_ONLY.value == "pending_only"


class TestFileTrackingRecord:
    """Tests for FileTrackingRecord dataclass."""

    def test_basic_creation(self):
        """Test basic record creation."""
        record = FileTrackingRecord(
            file_path="docs/tempmemories/test.md",
            status=MigrationStatus.PENDING,
            story_id="ST-TEST-001",
            memory_type="decision",
        )

        assert record.file_path == "docs/tempmemories/test.md"
        assert record.status == MigrationStatus.PENDING
        assert record.story_id == "ST-TEST-001"
        assert record.memory_type == "decision"
        assert record.attempt_count == 0

    def test_from_redis(self):
        """Test creating record from Redis data."""
        data = {
            "status": "completed",
            "story_id": "ST-001",
            "memory_type": "decision",
            "migrated_at": "2026-03-01T12:00:00+00:00",
            "error_message": "",
            "redis_key": "key:123",
            "qdrant_id": "id-456",
            "attempt_count": "2",
            "last_attempt": "2026-03-01T12:00:00+00:00",
        }

        record = FileTrackingRecord.from_redis("test.md", data)

        assert record.file_path == "test.md"
        assert record.status == MigrationStatus.COMPLETED
        assert record.story_id == "ST-001"
        assert record.attempt_count == 2
        assert record.migrated_at is not None
        assert record.last_attempt is not None

    def test_from_redis_invalid_dates(self):
        """Test handling of invalid date strings."""
        data = {
            "status": "pending",
            "migrated_at": "invalid-date",
            "last_attempt": "also-invalid",
        }

        record = FileTrackingRecord.from_redis("test.md", data)

        assert record.migrated_at is None
        assert record.last_attempt is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        record = FileTrackingRecord(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
            story_id="ST-001",
            memory_type="decision",
            attempt_count=1,
        )

        data = record.to_dict()

        assert data["status"] == "completed"
        assert data["story_id"] == "ST-001"
        assert data["memory_type"] == "decision"
        assert data["attempt_count"] == "1"


class TestTrackingSummary:
    """Tests for TrackingSummary dataclass."""

    def test_basic_creation(self):
        """Test basic summary creation."""
        summary = TrackingSummary(
            total_tracked=100,
            pending_count=10,
            in_progress_count=5,
            completed_count=80,
            failed_count=3,
            skipped_count=2,
        )

        assert summary.total_tracked == 100
        assert summary.completed_count == 80
        assert summary.failed_count == 3

    def test_to_dict(self):
        """Test conversion to dictionary."""
        summary = TrackingSummary(
            total_tracked=10,
            by_story={"ST-001": 5, "ST-002": 5},
            by_type={"decision": 8, "pattern": 2},
        )

        data = summary.to_dict()

        assert data["total_tracked"] == 10
        assert data["by_story"] == {"ST-001": 5, "ST-002": 5}
        assert data["by_type"] == {"decision": 8, "pattern": 2}


class TestTempmemoryTracker:
    """Tests for TempmemoryTracker."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    def test_initialization(self, mock_redis):
        """Test tracker initialization."""
        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=True)

        assert tracker._redis_client == mock_redis
        assert tracker._dry_run is True

    def test_track_file(self, mock_redis):
        """Test tracking a file."""
        mock_redis.hget.return_value = None  # No existing record

        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=False)
        result = tracker.track_file(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
            story_id="ST-001",
            memory_type="decision",
        )

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_track_file_increments_attempts(self, mock_redis):
        """Test that tracking increments attempt count."""
        existing_data = json.dumps(
            {
                "status": "pending",
                "attempt_count": "2",
            }
        )
        mock_redis.hget.return_value = existing_data

        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=False)
        tracker.track_file(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
        )

        # Check that hset was called with attempt_count = 3
        call_args = mock_redis.hset.call_args
        stored_data = json.loads(call_args[1]["value"])
        assert stored_data["attempt_count"] == "3"

    def test_track_file_dry_run(self, mock_redis):
        """Test that dry_run doesn't modify Redis."""
        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=True)
        result = tracker.track_file(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
        )

        assert result is True
        mock_redis.hset.assert_not_called()

    def test_track_file_no_redis(self):
        """Test tracking without Redis."""
        tracker = TempmemoryTracker(redis_client=None)
        result = tracker.track_file(
            file_path="test.md",
            status=MigrationStatus.COMPLETED,
        )

        assert result is False

    def test_get_file_record(self, mock_redis):
        """Test getting a file record."""
        mock_redis.hget.return_value = json.dumps(
            {
                "status": "completed",
                "story_id": "ST-001",
                "memory_type": "decision",
            }
        )

        tracker = TempmemoryTracker(redis_client=mock_redis)
        record = tracker.get_file_record("test.md")

        assert record is not None
        assert record.file_path == "test.md"
        assert record.status == MigrationStatus.COMPLETED
        assert record.story_id == "ST-001"

    def test_get_file_record_not_found(self, mock_redis):
        """Test getting non-existent record."""
        mock_redis.hget.return_value = None

        tracker = TempmemoryTracker(redis_client=mock_redis)
        record = tracker.get_file_record("test.md")

        assert record is None

    def test_get_files_by_status(self, mock_redis):
        """Test getting files by status."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps({"status": "completed"}),
            "file2.md": json.dumps({"status": "failed"}),
            "file3.md": json.dumps({"status": "completed"}),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis)
        records = tracker.get_files_by_status(MigrationStatus.COMPLETED)

        assert len(records) == 2
        assert all(r.status == MigrationStatus.COMPLETED for r in records)

    def test_get_summary(self, mock_redis):
        """Test getting summary."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps(
                {
                    "status": "completed",
                    "story_id": "ST-001",
                    "memory_type": "decision",
                }
            ),
            "file2.md": json.dumps(
                {
                    "status": "failed",
                    "story_id": "ST-001",
                    "memory_type": "pattern",
                }
            ),
            "file3.md": json.dumps(
                {
                    "status": "pending",
                    "story_id": "ST-002",
                    "memory_type": "decision",
                }
            ),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=False)
        summary = tracker.get_summary()

        assert summary.total_tracked == 3
        assert summary.completed_count == 1
        assert summary.failed_count == 1
        assert summary.pending_count == 1
        assert summary.by_story == {"ST-001": 2, "ST-002": 1}
        assert summary.by_type == {"decision": 2, "pattern": 1}

    def test_get_summary_no_redis(self):
        """Test getting summary without Redis."""
        tracker = TempmemoryTracker(redis_client=None)
        summary = tracker.get_summary()

        assert summary.total_tracked == 0

    def test_generate_report_summary(self, mock_redis):
        """Test generating summary report."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps({"status": "completed"}),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis)
        report = tracker.generate_report(TrackingReportType.SUMMARY)

        assert report["report_type"] == "summary"
        assert "summary" in report
        assert "records" not in report

    def test_generate_report_detailed(self, mock_redis):
        """Test generating detailed report."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps(
                {
                    "status": "completed",
                    "story_id": "ST-001",
                    "memory_type": "decision",
                }
            ),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis)
        report = tracker.generate_report(TrackingReportType.DETAILED)

        assert report["report_type"] == "detailed"
        assert "records" in report
        assert len(report["records"]) == 1

    def test_generate_report_failed_only(self, mock_redis):
        """Test generating failed-only report."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps({"status": "completed"}),
            "file2.md": json.dumps(
                {
                    "status": "failed",
                    "error_message": "Test error",
                    "attempt_count": "3",
                }
            ),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis)
        report = tracker.generate_report(TrackingReportType.FAILED_ONLY)

        assert report["report_type"] == "failed_only"
        assert "failed_files" in report
        assert len(report["failed_files"]) == 1
        assert report["failed_files"][0]["file_path"] == "file2.md"

    def test_generate_report_pending_only(self, mock_redis):
        """Test generating pending-only report."""
        mock_redis.hgetall.return_value = {
            "file1.md": json.dumps({"status": "completed"}),
            "file2.md": json.dumps(
                {
                    "status": "pending",
                    "story_id": "ST-001",
                }
            ),
        }

        tracker = TempmemoryTracker(redis_client=mock_redis)
        report = tracker.generate_report(TrackingReportType.PENDING_ONLY)

        assert report["report_type"] == "pending_only"
        assert "pending_files" in report
        assert len(report["pending_files"]) == 1
        assert report["pending_files"][0]["file_path"] == "file2.md"

    def test_reset_tracking_single_file(self, mock_redis):
        """Test resetting tracking for single file."""
        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=False)
        result = tracker.reset_tracking("test.md")

        assert result is True
        mock_redis.hdel.assert_called_once_with(
            TempmemoryTracker.REDIS_STATUS_KEY,
            "test.md",
        )

    def test_reset_tracking_all(self, mock_redis):
        """Test resetting all tracking."""
        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=False)
        result = tracker.reset_tracking()

        assert result is True
        mock_redis.delete.assert_any_call(TempmemoryTracker.REDIS_STATUS_KEY)
        mock_redis.delete.assert_any_call(TempmemoryTracker.REDIS_SUMMARY_KEY)

    def test_reset_tracking_dry_run(self, mock_redis):
        """Test that reset respects dry_run."""
        tracker = TempmemoryTracker(redis_client=mock_redis, dry_run=True)
        result = tracker.reset_tracking("test.md")

        assert result is False
        mock_redis.hdel.assert_not_called()

    def test_get_audit_log(self, mock_redis):
        """Test getting audit log."""
        mock_redis.lrange.return_value = [
            json.dumps(
                {
                    "timestamp": "2026-03-01T12:00:00",
                    "file_path": "test.md",
                    "status": "completed",
                }
            ),
        ]

        tracker = TempmemoryTracker(redis_client=mock_redis)
        entries = tracker.get_audit_log(limit=10)

        assert len(entries) == 1
        assert entries[0]["file_path"] == "test.md"
        mock_redis.lrange.assert_called_once_with(
            TempmemoryTracker.REDIS_AUDIT_KEY,
            0,
            9,
        )

    def test_get_audit_log_no_redis(self):
        """Test getting audit log without Redis."""
        tracker = TempmemoryTracker(redis_client=None)
        entries = tracker.get_audit_log()

        assert entries == []
