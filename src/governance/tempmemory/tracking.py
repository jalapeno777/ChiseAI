"""
Tempmemory Migration Tracking Module for ChiseAI.

Tracks the status of tempmemory file migrations in Redis.
Provides functionality for status reporting and tracking management.

This module is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from governance.tempmemory.migration import MigrationStatus

logger = logging.getLogger(__name__)


class TrackingReportType(Enum):
    """Types of tracking reports."""

    SUMMARY = "summary"
    DETAILED = "detailed"
    FAILED_ONLY = "failed_only"
    PENDING_ONLY = "pending_only"


@dataclass
class FileTrackingRecord:
    """Tracking record for a single tempmemory file."""

    file_path: str
    status: MigrationStatus
    story_id: str | None = None
    memory_type: str | None = None
    migrated_at: datetime | None = None
    error_message: str | None = None
    redis_key: str | None = None
    qdrant_id: str | None = None
    attempt_count: int = 0
    last_attempt: datetime | None = None

    @classmethod
    def from_redis(cls, file_path: str, data: dict[str, Any]) -> FileTrackingRecord:
        """Create a FileTrackingRecord from Redis data."""
        status = MigrationStatus(data.get("status", "pending"))

        migrated_at = None
        if data.get("migrated_at"):
            with contextlib.suppress(ValueError):
                migrated_at = datetime.fromisoformat(data["migrated_at"])

        last_attempt = None
        if data.get("last_attempt"):
            with contextlib.suppress(ValueError):
                last_attempt = datetime.fromisoformat(data["last_attempt"])

        return cls(
            file_path=file_path,
            status=status,
            story_id=data.get("story_id"),
            memory_type=data.get("memory_type"),
            migrated_at=migrated_at,
            error_message=data.get("error_message"),
            redis_key=data.get("redis_key"),
            qdrant_id=data.get("qdrant_id"),
            attempt_count=data.get("attempt_count", 0),
            last_attempt=last_attempt,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "status": self.status.value,
            "story_id": self.story_id or "",
            "memory_type": self.memory_type or "",
            "migrated_at": self.migrated_at.isoformat() if self.migrated_at else "",
            "error_message": self.error_message or "",
            "redis_key": self.redis_key or "",
            "qdrant_id": self.qdrant_id or "",
            "attempt_count": str(self.attempt_count),
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else "",
        }


@dataclass
class TrackingSummary:
    """Summary of migration tracking status."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_tracked: int = 0
    pending_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    by_story: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_tracked": self.total_tracked,
            "pending_count": self.pending_count,
            "in_progress_count": self.in_progress_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "by_story": self.by_story,
            "by_type": self.by_type,
        }


class TempmemoryTracker:
    """
    Tracker for tempmemory migration status.

    Manages tracking records in Redis and provides reporting functionality.

    Redis Key Structure:
    - bmad:chiseai:tempmemory:migration:status - Hash of file_path -> status_json
    - bmad:chiseai:tempmemory:migration:summary - Hash of summary data
    - bmad:chiseai:tempmemory:migration:audit - List of audit entries
    """

    REDIS_STATUS_KEY = "bmad:chiseai:tempmemory:migration:status"
    REDIS_SUMMARY_KEY = "bmad:chiseai:tempmemory:migration:summary"
    REDIS_AUDIT_KEY = "bmad:chiseai:tempmemory:migration:audit"
    REDIS_TRACKING_TTL = 30 * 24 * 3600  # 30 days

    def __init__(self, redis_client: Any | None = None, dry_run: bool = False):
        """
        Initialize the tracker.

        Args:
            redis_client: Optional Redis client.
            dry_run: If True, don't make actual changes.
        """
        self._redis_client = redis_client
        self._dry_run = dry_run

        logger.info(
            "TempmemoryTracker initialized",
            extra={
                "has_redis": redis_client is not None,
                "dry_run": dry_run,
            },
        )

    def track_file(
        self,
        file_path: str,
        status: MigrationStatus,
        story_id: str | None = None,
        memory_type: str | None = None,
        error_message: str | None = None,
        redis_key: str | None = None,
        qdrant_id: str | None = None,
    ) -> bool:
        """
        Track or update a file's migration status.

        Args:
            file_path: Path to the tempmemory file.
            status: Current migration status.
            story_id: Optional story ID.
            memory_type: Optional memory type.
            error_message: Optional error message.
            redis_key: Optional Redis key where content was stored.
            qdrant_id: Optional Qdrant ID where content was stored.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None:
            logger.debug(f"No Redis client, skipping tracking for {file_path}")
            return False

        if self._dry_run:
            logger.debug(f"[DRY RUN] Would track: {file_path} -> {status.value}")
            return True

        try:
            # Get existing record to increment attempt count
            existing = self.get_file_record(file_path)
            attempt_count = existing.attempt_count + 1 if existing else 1

            record = FileTrackingRecord(
                file_path=file_path,
                status=status,
                story_id=story_id,
                memory_type=memory_type,
                migrated_at=(
                    datetime.now(UTC) if status == MigrationStatus.COMPLETED else None
                ),
                error_message=error_message,
                redis_key=redis_key,
                qdrant_id=qdrant_id,
                attempt_count=attempt_count,
                last_attempt=datetime.now(UTC),
            )

            # Store in Redis
            self._redis_client.hset(
                self.REDIS_STATUS_KEY,
                file_path,
                json.dumps(record.to_dict()),
            )

            # Set TTL on the hash key
            self._redis_client.expire(self.REDIS_STATUS_KEY, self.REDIS_TRACKING_TTL)

            # Add audit entry
            self._add_audit_entry(file_path, status, error_message)

            logger.debug(f"Tracked: {file_path} -> {status.value}")
            return True

        except Exception as e:
            logger.warning(f"Failed to track {file_path}: {e}")
            return False

    def get_file_record(self, file_path: str) -> FileTrackingRecord | None:
        """
        Get tracking record for a specific file.

        Args:
            file_path: Path to the tempmemory file.

        Returns:
            FileTrackingRecord if found, None otherwise.
        """
        if self._redis_client is None:
            return None

        try:
            data = self._redis_client.hget(self.REDIS_STATUS_KEY, file_path)
            if data:
                parsed = json.loads(data)
                return FileTrackingRecord.from_redis(file_path, parsed)
            return None
        except Exception as e:
            logger.warning(f"Failed to get record for {file_path}: {e}")
            return None

    def get_files_by_status(self, status: MigrationStatus) -> list[FileTrackingRecord]:
        """
        Get all files with a specific status.

        Args:
            status: Status to filter by.

        Returns:
            List of FileTrackingRecord objects.
        """
        if self._redis_client is None:
            return []

        records: list[FileTrackingRecord] = []

        try:
            all_data = self._redis_client.hgetall(self.REDIS_STATUS_KEY)
            for file_path, data in all_data.items():
                try:
                    parsed = json.loads(data)
                    if parsed.get("status") == status.value:
                        records.append(FileTrackingRecord.from_redis(file_path, parsed))
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"Failed to get files by status: {e}")

        return records

    def get_summary(self) -> TrackingSummary:
        """
        Get a summary of all tracked files.

        Returns:
            TrackingSummary with aggregated statistics.
        """
        summary = TrackingSummary()

        if self._redis_client is None:
            return summary

        try:
            all_data = self._redis_client.hgetall(self.REDIS_STATUS_KEY)
            summary.total_tracked = len(all_data)

            for _file_path, data in all_data.items():
                try:
                    parsed = json.loads(data)
                    status = MigrationStatus(parsed.get("status", "pending"))

                    # Count by status
                    if status == MigrationStatus.PENDING:
                        summary.pending_count += 1
                    elif status == MigrationStatus.IN_PROGRESS:
                        summary.in_progress_count += 1
                    elif status == MigrationStatus.COMPLETED:
                        summary.completed_count += 1
                    elif status == MigrationStatus.FAILED:
                        summary.failed_count += 1
                    elif status == MigrationStatus.SKIPPED:
                        summary.skipped_count += 1

                    # Count by story
                    story_id = parsed.get("story_id")
                    if story_id:
                        summary.by_story[story_id] = (
                            summary.by_story.get(story_id, 0) + 1
                        )

                    # Count by type
                    memory_type = parsed.get("memory_type")
                    if memory_type:
                        summary.by_type[memory_type] = (
                            summary.by_type.get(memory_type, 0) + 1
                        )

                except (json.JSONDecodeError, ValueError):
                    continue

            # Store summary in Redis
            if not self._dry_run:
                self._redis_client.hset(
                    self.REDIS_SUMMARY_KEY,
                    mapping={
                        k: str(v)
                        for k, v in summary.to_dict().items()
                        if k != "timestamp"
                    },
                )
                self._redis_client.hset(
                    self.REDIS_SUMMARY_KEY,
                    "timestamp",
                    summary.timestamp.isoformat(),
                )
                self._redis_client.expire(
                    self.REDIS_SUMMARY_KEY, self.REDIS_TRACKING_TTL
                )

        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")

        return summary

    def generate_report(
        self, report_type: TrackingReportType = TrackingReportType.SUMMARY
    ) -> dict[str, Any]:
        """
        Generate a tracking report.

        Args:
            report_type: Type of report to generate.

        Returns:
            Dictionary containing report data.
        """
        summary = self.get_summary()

        report: dict[str, Any] = {
            "report_type": report_type.value,
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": summary.to_dict(),
        }

        if report_type == TrackingReportType.DETAILED:
            # Include all records
            all_records: list[dict[str, Any]] = []
            if self._redis_client:
                try:
                    all_data = self._redis_client.hgetall(self.REDIS_STATUS_KEY)
                    for file_path, data in all_data.items():
                        try:
                            parsed = json.loads(data)
                            record = FileTrackingRecord.from_redis(file_path, parsed)
                            all_records.append(
                                {
                                    "file_path": record.file_path,
                                    "status": record.status.value,
                                    "story_id": record.story_id,
                                    "memory_type": record.memory_type,
                                    "migrated_at": (
                                        record.migrated_at.isoformat()
                                        if record.migrated_at
                                        else None
                                    ),
                                    "error_message": record.error_message,
                                    "attempt_count": record.attempt_count,
                                    "last_attempt": (
                                        record.last_attempt.isoformat()
                                        if record.last_attempt
                                        else None
                                    ),
                                }
                            )
                        except (json.JSONDecodeError, ValueError):
                            continue
                except Exception as e:
                    logger.warning(f"Failed to get detailed records: {e}")

            report["records"] = all_records

        elif report_type == TrackingReportType.FAILED_ONLY:
            failed_records = self.get_files_by_status(MigrationStatus.FAILED)
            report["failed_files"] = [
                {
                    "file_path": r.file_path,
                    "error_message": r.error_message,
                    "attempt_count": r.attempt_count,
                    "last_attempt": (
                        r.last_attempt.isoformat() if r.last_attempt else None
                    ),
                }
                for r in failed_records
            ]

        elif report_type == TrackingReportType.PENDING_ONLY:
            pending_records = self.get_files_by_status(MigrationStatus.PENDING)
            report["pending_files"] = [
                {
                    "file_path": r.file_path,
                    "story_id": r.story_id,
                    "memory_type": r.memory_type,
                }
                for r in pending_records
            ]

        return report

    def reset_tracking(self, file_path: str | None = None) -> bool:
        """
        Reset tracking for a specific file or all files.

        Args:
            file_path: Optional specific file to reset. If None, resets all.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None or self._dry_run:
            return False

        try:
            if file_path:
                self._redis_client.hdel(self.REDIS_STATUS_KEY, file_path)
                logger.info(f"Reset tracking for {file_path}")
            else:
                self._redis_client.delete(self.REDIS_STATUS_KEY)
                self._redis_client.delete(self.REDIS_SUMMARY_KEY)
                logger.info("Reset all tracking data")
            return True
        except Exception as e:
            logger.warning(f"Failed to reset tracking: {e}")
            return False

    def _add_audit_entry(
        self, file_path: str, status: MigrationStatus, error_message: str | None = None
    ) -> bool:
        """
        Add an audit entry for a tracking update.

        Args:
            file_path: Path to the file.
            status: New status.
            error_message: Optional error message.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None:
            return False

        try:
            entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "file_path": file_path,
                "status": status.value,
                "error_message": error_message or "",
            }

            # Use list to store audit entries (keep last 1000)
            self._redis_client.lpush(self.REDIS_AUDIT_KEY, json.dumps(entry))
            self._redis_client.ltrim(self.REDIS_AUDIT_KEY, 0, 999)
            self._redis_client.expire(self.REDIS_AUDIT_KEY, self.REDIS_TRACKING_TTL)

            return True
        except Exception as e:
            logger.warning(f"Failed to add audit entry: {e}")
            return False

    def get_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of audit entries.
        """
        if self._redis_client is None:
            return []

        try:
            entries = self._redis_client.lrange(self.REDIS_AUDIT_KEY, 0, limit - 1)
            return [json.loads(e) for e in entries if e]
        except Exception as e:
            logger.warning(f"Failed to get audit log: {e}")
            return []
