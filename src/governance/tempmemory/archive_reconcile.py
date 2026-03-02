"""
Tempmemory Archive and Reconciliation Module for ChiseAI.

Provides functionality to:
- Archive migrated tempmemory files
- Reconcile migration status (detect orphaned files)
- Generate reconciliation reports

This module is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governance.tempmemory.migration import (
    MigrationStatus,
)
from governance.tempmemory.tracking import TempmemoryTracker

logger = logging.getLogger(__name__)


@dataclass
class ArchiveResult:
    """Result of archiving a single file."""

    source_path: str
    archive_path: str
    success: bool
    error_message: str | None = None
    archived_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReconciliationIssue:
    """Represents a reconciliation issue."""

    issue_type: str  # "orphaned", "missing", "mismatch"
    file_path: str
    details: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReconciliationReport:
    """Report from a reconciliation run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_files_in_tempmemory: int = 0
    total_files_in_archive: int = 0
    total_tracked: int = 0
    orphaned_files: list[ReconciliationIssue] = field(default_factory=list)
    missing_files: list[ReconciliationIssue] = field(default_factory=list)
    mismatched_files: list[ReconciliationIssue] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_files_in_tempmemory": self.total_files_in_tempmemory,
            "total_files_in_archive": self.total_files_in_archive,
            "total_tracked": self.total_tracked,
            "orphaned_count": len(self.orphaned_files),
            "missing_count": len(self.missing_files),
            "mismatched_count": len(self.mismatched_files),
            "duration_seconds": self.duration_seconds,
            "orphaned_files": [
                {
                    "file_path": f.file_path,
                    "issue_type": f.issue_type,
                    "details": f.details,
                }
                for f in self.orphaned_files
            ],
            "missing_files": [
                {
                    "file_path": f.file_path,
                    "issue_type": f.issue_type,
                    "details": f.details,
                }
                for f in self.missing_files
            ],
            "mismatched_files": [
                {
                    "file_path": f.file_path,
                    "issue_type": f.issue_type,
                    "details": f.details,
                }
                for f in self.mismatched_files
            ],
        }

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class TempmemoryArchiveReconciler:
    """
    Archive and reconciliation manager for tempmemory files.

    Handles:
    - Archiving successfully migrated files
    - Detecting orphaned files (not tracked)
    - Detecting missing files (tracked but not on disk)
    - Detecting mismatched status
    """

    DEFAULT_TEMPMEMORY_PATH = "docs/tempmemories"
    DEFAULT_ARCHIVE_PATH = "docs/tempmemories/archive"
    ARCHIVE_METADATA_FILE = "archive_manifest.json"

    def __init__(
        self,
        tempmemory_path: str | Path | None = None,
        archive_path: str | Path | None = None,
        redis_client: Any | None = None,
        dry_run: bool = True,
    ):
        """
        Initialize the archive/reconciler.

        Args:
            tempmemory_path: Path to tempmemory directory.
            archive_path: Path to archive directory.
            redis_client: Optional Redis client.
            dry_run: If True, don't make actual changes.
        """
        self._tempmemory_path = Path(tempmemory_path or self.DEFAULT_TEMPMEMORY_PATH)
        self._archive_path = Path(archive_path or self.DEFAULT_ARCHIVE_PATH)
        self._redis_client = redis_client
        self._dry_run = dry_run

        # Initialize tracker
        self._tracker = TempmemoryTracker(redis_client=redis_client, dry_run=dry_run)

        # Ensure archive directory exists
        if not self._dry_run:
            self._archive_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "TempmemoryArchiveReconciler initialized",
            extra={
                "tempmemory_path": str(self._tempmemory_path),
                "archive_path": str(self._archive_path),
                "dry_run": dry_run,
            },
        )

    def archive_file(
        self,
        file_path: str | Path,
        preserve_structure: bool = True,
    ) -> ArchiveResult:
        """
        Archive a single tempmemory file.

        Args:
            file_path: Path to the file to archive.
            preserve_structure: If True, preserve subdirectory structure.

        Returns:
            ArchiveResult with status and details.
        """
        source = Path(file_path)

        if not source.exists():
            return ArchiveResult(
                source_path=str(file_path),
                archive_path="",
                success=False,
                error_message="Source file does not exist",
            )

        # Determine archive destination
        if preserve_structure:
            try:
                relative = source.relative_to(self._tempmemory_path)
                dest = self._archive_path / relative
            except ValueError:
                dest = self._archive_path / source.name
        else:
            dest = self._archive_path / source.name

        # Ensure destination directory exists
        if not self._dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self._dry_run:
                logger.debug(f"[DRY RUN] Would archive: {source} -> {dest}")
                return ArchiveResult(
                    source_path=str(source),
                    archive_path=str(dest),
                    success=True,
                )

            # Copy file to archive
            shutil.copy2(source, dest)

            # Remove original
            source.unlink()

            logger.info(f"Archived: {source} -> {dest}")

            return ArchiveResult(
                source_path=str(source),
                archive_path=str(dest),
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to archive {source}: {e}")
            return ArchiveResult(
                source_path=str(source),
                archive_path=str(dest),
                success=False,
                error_message=str(e),
            )

    def archive_completed_files(self) -> list[ArchiveResult]:
        """
        Archive all files that have been successfully migrated.

        Returns:
            List of ArchiveResult objects.
        """
        results: list[ArchiveResult] = []

        # Get all completed files from tracker
        completed = self._tracker.get_files_by_status(MigrationStatus.COMPLETED)

        logger.info(f"Found {len(completed)} completed files to archive")

        for record in completed:
            result = self.archive_file(record.file_path)
            results.append(result)

        return results

    def reconcile(self) -> ReconciliationReport:
        """
        Run reconciliation to detect issues.

        Detects:
        - Orphaned files: Exist in tempmemory but not tracked
        - Missing files: Tracked but don't exist on disk
        - Mismatched files: Status inconsistency

        Returns:
            ReconciliationReport with all issues found.
        """
        start_time = datetime.now(UTC)
        report = ReconciliationReport()

        logger.info("Starting reconciliation")

        # Scan tempmemory directory
        tempmemory_files = set()
        if self._tempmemory_path.exists():
            for f in self._tempmemory_path.rglob("*.md"):
                # Skip archive and templates
                if self._archive_path.name in str(f) or "templates" in str(f):
                    continue
                if f.name in ("README.md", ".gitkeep"):
                    continue
                try:
                    relative = str(f.relative_to(Path.cwd()))
                except ValueError:
                    relative = str(f)
                tempmemory_files.add(relative)

        report.total_files_in_tempmemory = len(tempmemory_files)

        # Count files in archive
        if self._archive_path.exists():
            archive_files = list(self._archive_path.rglob("*.md"))
            report.total_files_in_archive = len(archive_files)

        # Get tracked files
        tracked_files: set[str] = set()
        tracked_status: dict[str, MigrationStatus] = {}

        if self._redis_client:
            try:
                all_data = self._redis_client.hgetall(
                    TempmemoryTracker.REDIS_STATUS_KEY
                )
                report.total_tracked = len(all_data)

                for file_path, data in all_data.items():
                    tracked_files.add(file_path)
                    try:
                        parsed = json.loads(data)
                        tracked_status[file_path] = MigrationStatus(
                            parsed.get("status", "pending")
                        )
                    except (json.JSONDecodeError, ValueError):
                        tracked_status[file_path] = MigrationStatus.PENDING
            except Exception as e:
                logger.warning(f"Failed to get tracked files: {e}")

        # Detect orphaned files (exist but not tracked)
        orphaned = tempmemory_files - tracked_files
        for file_path in orphaned:
            issue = ReconciliationIssue(
                issue_type="orphaned",
                file_path=file_path,
                details={
                    "reason": "File exists in tempmemory but is not tracked",
                    "suggestion": "Run migration to track this file",
                },
            )
            report.orphaned_files.append(issue)

        # Detect missing files (tracked but don't exist)
        missing = tracked_files - tempmemory_files
        for file_path in missing:
            status = tracked_status.get(file_path, MigrationStatus.PENDING)
            issue = ReconciliationIssue(
                issue_type="missing",
                file_path=file_path,
                details={
                    "reason": "File is tracked but does not exist on disk",
                    "tracked_status": status.value,
                    "suggestion": "May have been manually deleted or moved",
                },
            )
            report.missing_files.append(issue)

        # Detect mismatched files (completed but not archived)
        for file_path in tracked_files & tempmemory_files:
            status = tracked_status.get(file_path)
            if status == MigrationStatus.COMPLETED:
                issue = ReconciliationIssue(
                    issue_type="mismatch",
                    file_path=file_path,
                    details={
                        "reason": "File is marked completed but still in tempmemory",
                        "tracked_status": status.value,
                        "suggestion": "Should be archived",
                    },
                )
                report.mismatched_files.append(issue)

        report.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            "Reconciliation completed",
            extra={
                "orphaned": len(report.orphaned_files),
                "missing": len(report.missing_files),
                "mismatched": len(report.mismatched_files),
                "duration": report.duration_seconds,
            },
        )

        return report

    def auto_fix_issues(
        self, report: ReconciliationReport | None = None
    ) -> dict[str, Any]:
        """
        Automatically fix detected issues.

        Fixes:
        - Archive mismatched files (completed but not archived)
        - Reset tracking for missing files

        Args:
            report: Optional pre-generated report. If None, runs reconcile().

        Returns:
            Dictionary with fix results.
        """
        if report is None:
            report = self.reconcile()

        if self._dry_run:
            logger.info("[DRY RUN] Would auto-fix issues")
            return {
                "dry_run": True,
                "fixes_applied": 0,
                "archived": 0,
                "reset": 0,
            }

        fixes_applied = 0
        archived_count = 0
        reset_count = 0

        # Fix mismatched files (archive them)
        for issue in report.mismatched_files:
            if issue.issue_type == "mismatch":
                result = self.archive_file(issue.file_path)
                if result.success:
                    fixes_applied += 1
                    archived_count += 1

        # Fix missing files (reset tracking)
        for issue in report.missing_files:
            if issue.issue_type == "missing":
                if self._tracker.reset_tracking(issue.file_path):
                    fixes_applied += 1
                    reset_count += 1

        logger.info(
            "Auto-fix completed",
            extra={
                "fixes_applied": fixes_applied,
                "archived": archived_count,
                "reset": reset_count,
            },
        )

        return {
            "fixes_applied": fixes_applied,
            "archived": archived_count,
            "reset": reset_count,
        }

    def get_archive_manifest(self) -> dict[str, Any]:
        """
        Get manifest of archived files.

        Returns:
            Dictionary with archive manifest.
        """
        manifest: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "archive_path": str(self._archive_path),
            "files": [],
        }

        if not self._archive_path.exists():
            return manifest

        for f in self._archive_path.rglob("*.md"):
            try:
                stat = f.stat()
                manifest["files"].append(
                    {
                        "path": str(f.relative_to(self._archive_path)),
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime, UTC
                        ).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to stat {f}: {e}")

        manifest["total_files"] = len(manifest["files"])
        manifest["total_size_bytes"] = sum(f["size_bytes"] for f in manifest["files"])

        return manifest

    def save_archive_manifest(self) -> bool:
        """
        Save archive manifest to disk.

        Returns:
            True if successful, False otherwise.
        """
        if self._dry_run:
            return False

        try:
            manifest = self.get_archive_manifest()
            manifest_path = self._archive_path / self.ARCHIVE_METADATA_FILE

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            logger.info(f"Saved archive manifest to {manifest_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save archive manifest: {e}")
            return False
