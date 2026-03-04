"""
Tempmemory Ingestion Runner for ChiseAI.

Provides a cron-safe, idempotent ingestion runner that wraps the existing
TempmemoryMigrationEngine for scheduled ingestion of tempmemory files.

Features:
- Redis-based locking to prevent concurrent runs
- Idempotent processing (checks file hash/mtime before re-ingesting)
- Filtering by frontmatter type
- Progress tracking in Redis
- Failure handling (log errors, continue with other files)

This module is part of the Tempmemory Ingestion Runner story (ST-MEMORY-INGEST-001).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governance.tempmemory.migration import (
    MigrationReport,
    MigrationStatus,
    TempmemoryFile,
    TempmemoryMigrationEngine,
)

logger = logging.getLogger(__name__)


# Redis key patterns
REDIS_LOCK_KEY = "bmad:chiseai:tempmemory:ingestion:lock"
REDIS_STATUS_KEY = "bmad:chiseai:tempmemory:ingestion:status"
REDIS_HASH_KEY = "bmad:chiseai:tempmemory:ingestion:hashes"

# Lock timeout (5 minutes)
LOCK_TIMEOUT_SECONDS = 300

# Valid frontmatter types for ingestion
VALID_INGESTION_TYPES = {"decision", "pattern", "summary", "anti-pattern"}


@dataclass
class IngestionStatus:
    """Status of the ingestion runner."""

    last_run: str | None = None
    last_success: bool = False
    total_files_processed: int = 0
    total_files_ingested: int = 0
    total_files_failed: int = 0
    last_error: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "last_run": self.last_run,
            "last_success": self.last_success,
            "total_files_processed": self.total_files_processed,
            "total_files_ingested": self.total_files_ingested,
            "total_files_failed": self.total_files_failed,
            "last_error": self.last_error,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IngestionStatus:
        """Create from dictionary."""
        return cls(
            last_run=data.get("last_run"),
            last_success=data.get("last_success", False),
            total_files_processed=data.get("total_files_processed", 0),
            total_files_ingested=data.get("total_files_ingested", 0),
            total_files_failed=data.get("total_files_failed", 0),
            last_error=data.get("last_error"),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass
class FileIngestionResult:
    """Result of ingesting a single file."""

    file_path: str
    status: MigrationStatus
    already_processed: bool = False
    filtered: bool = False
    filter_reason: str | None = None
    error_message: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TempmemoryIngestionRunner:
    """
    Cron-safe ingestion runner for tempmemory files.

    Wraps TempmemoryMigrationEngine with additional features:
    - Redis-based locking to prevent concurrent runs
    - Idempotent processing (file hash checking)
    - Type-based filtering
    - Progress tracking
    - Failure handling with continuation

    Usage:
        runner = TempmemoryIngestionRunner(redis_client=redis_client)
        result = runner.run_with_lock()
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
        tempmemory_path: str | Path | None = None,
        dry_run: bool = False,
        force: bool = False,
        filter_types: list[str] | None = None,
    ):
        """
        Initialize the ingestion runner.

        Args:
            redis_client: Optional Redis client for locking and status.
            qdrant_client: Optional Qdrant client for storage.
            tempmemory_path: Path to tempmemory directory.
            dry_run: If True, don't make actual changes.
            force: If True, re-ingest even if already processed.
            filter_types: List of frontmatter types to ingest (default: all valid types).
        """
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._tempmemory_path = tempmemory_path
        self._dry_run = dry_run
        self._force = force
        self._filter_types = (
            set(filter_types) if filter_types else VALID_INGESTION_TYPES
        )

        # Initialize migration engine
        self._migration_engine = TempmemoryMigrationEngine(
            tempmemory_path=tempmemory_path,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
            dry_run=dry_run,
        )

        logger.info(
            "TempmemoryIngestionRunner initialized",
            extra={
                "tempmemory_path": str(tempmemory_path or "default"),
                "dry_run": dry_run,
                "force": force,
                "filter_types": list(self._filter_types),
            },
        )

    def acquire_lock(self) -> bool:
        """
        Acquire Redis lock to prevent concurrent runs.

        Returns:
            True if lock acquired, False if lock already held.
        """
        if self._redis_client is None:
            logger.debug("No Redis client, skipping lock")
            return True

        try:
            # Try to set lock with NX (only if not exists) and EX (expiration)
            result = self._redis_client.set(
                REDIS_LOCK_KEY,
                json.dumps(
                    {
                        "acquired_at": datetime.now(UTC).isoformat(),
                        "pid": __import__("os").getpid(),
                    }
                ),
                nx=True,
                ex=LOCK_TIMEOUT_SECONDS,
            )

            if result:
                logger.debug("Lock acquired successfully")
                return True
            else:
                logger.warning("Lock already held by another process")
                return False

        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    def release_lock(self) -> bool:
        """
        Release Redis lock.

        Returns:
            True if lock released, False otherwise.
        """
        if self._redis_client is None:
            return True

        try:
            self._redis_client.delete(REDIS_LOCK_KEY)
            logger.debug("Lock released successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
            return False

    def get_file_hash(self, file_path: Path) -> str:
        """
        Calculate hash of file content for idempotency.

        Args:
            file_path: Path to the file.

        Returns:
            SHA256 hash of file content.
        """
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def is_file_processed(self, file_path: str, current_hash: str) -> bool:
        """
        Check if file has already been processed (by hash comparison).

        Args:
            file_path: Relative path to the file.
            current_hash: Current hash of file content.

        Returns:
            True if file already processed with same hash, False otherwise.
        """
        if self._redis_client is None:
            return False

        try:
            stored_hash = self._redis_client.hget(REDIS_HASH_KEY, file_path)
            if stored_hash:
                stored_hash_str = (
                    stored_hash.decode()
                    if isinstance(stored_hash, bytes)
                    else stored_hash
                )
                return stored_hash_str == current_hash
            return False
        except Exception as e:
            logger.warning(f"Failed to check file hash for {file_path}: {e}")
            return False

    def mark_file_processed(self, file_path: str, file_hash: str) -> bool:
        """
        Mark file as processed by storing its hash.

        Args:
            file_path: Relative path to the file.
            file_hash: Hash of file content.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None or self._dry_run:
            return True

        try:
            self._redis_client.hset(REDIS_HASH_KEY, file_path, file_hash)
            return True
        except Exception as e:
            logger.warning(f"Failed to mark file as processed {file_path}: {e}")
            return False

    def should_ingest_file(self, temp_file: TempmemoryFile) -> tuple[bool, str | None]:
        """
        Determine if a file should be ingested based on type filter.

        Args:
            temp_file: The tempmemory file to check.

        Returns:
            Tuple of (should_ingest, reason_if_not).
        """
        memory_type = temp_file.memory_type

        if memory_type is None:
            return False, "No type in frontmatter"

        if memory_type not in self._filter_types:
            return False, f"Type '{memory_type}' not in filter list"

        return True, None

    def ingest_single_file(self, file_path: str | Path) -> FileIngestionResult:
        """
        Ingest a specific file.

        Args:
            file_path: Path to the file to ingest.

        Returns:
            FileIngestionResult with status and details.
        """
        file_path = Path(file_path)
        result = FileIngestionResult(
            file_path=str(file_path),
            status=MigrationStatus.PENDING,
        )

        try:
            # Parse file
            temp_file = self._migration_engine._parse_file(file_path)

            # Check type filter
            should_ingest, filter_reason = self.should_ingest_file(temp_file)
            if not should_ingest:
                result.status = MigrationStatus.SKIPPED
                result.filtered = True
                result.filter_reason = filter_reason
                logger.debug(f"Filtered file {file_path}: {filter_reason}")
                return result

            # Check idempotency (unless force mode)
            if not self._force:
                current_hash = self.get_file_hash(file_path)
                relative_path = temp_file.relative_path

                if self.is_file_processed(relative_path, current_hash):
                    result.status = MigrationStatus.COMPLETED
                    result.already_processed = True
                    logger.debug(f"File already processed: {file_path}")
                    return result

            # Migrate the file
            migration_result = self._migration_engine.migrate_file(temp_file)
            result.status = migration_result.status
            result.error_message = migration_result.error_message

            # Mark as processed if successful
            if result.status == MigrationStatus.COMPLETED and not self._dry_run:
                current_hash = self.get_file_hash(file_path)
                self.mark_file_processed(temp_file.relative_path, current_hash)

        except Exception as e:
            result.status = MigrationStatus.FAILED
            result.error_message = str(e)
            logger.exception(f"Failed to ingest file {file_path}")

        return result

    def scan_and_ingest(self) -> MigrationReport:
        """
        Scan docs/tempmemories/ and ingest new/modified files.

        Returns:
            MigrationReport with detailed results.
        """
        start_time = datetime.now(UTC)
        report = MigrationReport(dry_run=self._dry_run)

        logger.info("Starting tempmemory ingestion scan")

        # Scan for files
        files = self._migration_engine.scan_files()
        report.total_files = len(files)
        report.scanned_files = len(files)

        # Process each file
        for temp_file in files:
            result = self.ingest_single_file(temp_file.path)
            report.results.append(self._convert_result(result, temp_file))

            if result.status == MigrationStatus.COMPLETED:
                report.migrated_files += 1
            elif result.status == MigrationStatus.FAILED:
                report.failed_files += 1
            elif result.status == MigrationStatus.SKIPPED:
                report.skipped_files += 1

        # Calculate duration
        report.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            "Ingestion scan completed",
            extra={
                "total": report.total_files,
                "migrated": report.migrated_files,
                "failed": report.failed_files,
                "skipped": report.skipped_files,
                "duration": report.duration_seconds,
            },
        )

        return report

    def _convert_result(
        self, file_result: FileIngestionResult, temp_file: TempmemoryFile
    ) -> Any:
        """Convert FileIngestionResult to MigrationResult for report."""
        from governance.tempmemory.migration import MigrationResult

        return MigrationResult(
            file_path=file_result.file_path,
            status=file_result.status,
            target=temp_file.determine_target(),
            error_message=file_result.error_message,
        )

    def get_ingestion_status(self) -> IngestionStatus:
        """
        Get last run info from Redis.

        Returns:
            IngestionStatus with last run details.
        """
        if self._redis_client is None:
            return IngestionStatus()

        try:
            status_data = self._redis_client.get(REDIS_STATUS_KEY)
            if status_data:
                data = json.loads(
                    status_data.decode()
                    if isinstance(status_data, bytes)
                    else status_data
                )
                return IngestionStatus.from_dict(data)
            return IngestionStatus()
        except Exception as e:
            logger.warning(f"Failed to get ingestion status: {e}")
            return IngestionStatus()

    def update_ingestion_status(self, status: IngestionStatus) -> bool:
        """
        Update ingestion status in Redis.

        Args:
            status: The status to store.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None or self._dry_run:
            return True

        try:
            self._redis_client.set(
                REDIS_STATUS_KEY,
                json.dumps(status.to_dict()),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to update ingestion status: {e}")
            return False

    def run_with_lock(self) -> MigrationReport:
        """
        Acquire Redis lock and run ingestion.

        This is the main entry point for cron-safe ingestion.

        Returns:
            MigrationReport with detailed results.

        Raises:
            RuntimeError: If lock cannot be acquired.
        """
        # Try to acquire lock
        if not self.acquire_lock():
            raise RuntimeError("Ingestion already running (lock held)")

        try:
            # Run ingestion
            report = self.scan_and_ingest()

            # Update status
            status = IngestionStatus(
                last_run=datetime.now(UTC).isoformat(),
                last_success=(report.failed_files == 0),
                total_files_processed=report.total_files,
                total_files_ingested=report.migrated_files,
                total_files_failed=report.failed_files,
                duration_seconds=report.duration_seconds,
            )

            if report.failed_files > 0:
                failed_files = [
                    r.file_path
                    for r in report.results
                    if r.status == MigrationStatus.FAILED
                ]
                status.last_error = f"Failed files: {', '.join(failed_files[:5])}"

            self.update_ingestion_status(status)

            return report

        finally:
            # Always release lock
            self.release_lock()
