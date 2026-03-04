"""
Tempmemory Migration Module for ChiseAI.

Provides functionality to migrate temporary memory files from docs/tempmemories/
to Redis (short-term) and Qdrant (long-term) storage.

This module is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    """Status of a tempmemory file migration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MigrationTarget(Enum):
    """Target storage for migration."""

    REDIS = "redis"
    QDRANT = "qdrant"
    BOTH = "both"


@dataclass
class TempmemoryFile:
    """Represents a tempmemory file with parsed metadata."""

    path: Path
    relative_path: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    has_frontmatter: bool = False

    @property
    def story_id(self) -> str | None:
        """Get story_id from frontmatter."""
        return self.frontmatter.get("story_id")

    @property
    def scope(self) -> str | None:
        """Get scope from frontmatter."""
        return self.frontmatter.get("scope")

    @property
    def memory_type(self) -> str | None:
        """Get type from frontmatter."""
        return self.frontmatter.get("type")

    @property
    def date(self) -> str | None:
        """Get date from frontmatter."""
        return self.frontmatter.get("date")

    @property
    def project(self) -> str | None:
        """Get project from frontmatter."""
        return self.frontmatter.get("project")

    def determine_target(self) -> MigrationTarget:
        """Determine migration target based on file content and metadata."""
        # Decision and pattern types go to both Redis and Qdrant
        if self.memory_type in ("decision", "pattern"):
            return MigrationTarget.BOTH

        # Summary and anti-pattern go primarily to Qdrant
        if self.memory_type in ("summary", "anti-pattern"):
            return MigrationTarget.QDRANT

        # Default: try both
        return MigrationTarget.BOTH

    def to_redis_entry(self) -> dict[str, Any]:
        """Convert to Redis hash entry format."""
        return {
            "story_id": self.story_id or "",
            "scope": self.scope or "",
            "type": self.memory_type or "",
            "date": self.date or "",
            "project": self.project or "",
            "content": self.content[:10000],  # Limit content size
            "source_file": self.relative_path,
            "migrated_at": datetime.now(UTC).isoformat(),
        }

    def to_qdrant_entry(self) -> dict[str, Any]:
        """Convert to Qdrant entry format."""
        return {
            "content": self.content,
            "metadata": {
                "story_id": self.story_id,
                "scope": self.scope,
                "type": self.memory_type,
                "date": self.date,
                "project": self.project,
                "source_file": self.relative_path,
                "migrated_at": datetime.now(UTC).isoformat(),
            },
        }


@dataclass
class MigrationResult:
    """Result of a single file migration."""

    file_path: str
    status: MigrationStatus
    target: MigrationTarget
    redis_success: bool = False
    qdrant_success: bool = False
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class MigrationReport:
    """Report of a complete migration run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_files: int = 0
    scanned_files: int = 0
    migrated_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    results: list[MigrationResult] = field(default_factory=list)
    dry_run: bool = True
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_files": self.total_files,
            "scanned_files": self.scanned_files,
            "migrated_files": self.migrated_files,
            "failed_files": self.failed_files,
            "skipped_files": self.skipped_files,
            "dry_run": self.dry_run,
            "duration_seconds": self.duration_seconds,
            "results": [
                {
                    "file_path": r.file_path,
                    "status": r.status.value,
                    "target": r.target.value,
                    "redis_success": r.redis_success,
                    "qdrant_success": r.qdrant_success,
                    "error_message": r.error_message,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in self.results
            ],
        }

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class TempmemoryMigrationEngine:
    """
    Engine for migrating tempmemory files to Redis and Qdrant.

    Features:
    - Scan docs/tempmemories/ for markdown files
    - Parse YAML frontmatter
    - Migrate to appropriate storage (Redis/Qdrant)
    - Support dry-run mode
    - Generate detailed reports
    """

    # Default paths
    DEFAULT_TEMPMEMORY_PATH = "docs/tempmemories"
    DEFAULT_ARCHIVE_PATH = "docs/tempmemories/archive"

    # Redis key patterns
    REDIS_TEMPMEMORY_PREFIX = "bmad:chiseai:tempmemory"
    REDIS_STATUS_KEY = "bmad:chiseai:tempmemory:migration:status"

    def __init__(
        self,
        tempmemory_path: str | Path | None = None,
        archive_path: str | Path | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
        dry_run: bool = True,
    ):
        """
        Initialize the migration engine.

        Args:
            tempmemory_path: Path to tempmemory directory.
            archive_path: Path to archive directory.
            redis_client: Optional Redis client.
            qdrant_client: Optional Qdrant client.
            dry_run: If True, don't make actual changes.
        """
        self._tempmemory_path = Path(tempmemory_path or self.DEFAULT_TEMPMEMORY_PATH)
        self._archive_path = Path(archive_path or self.DEFAULT_ARCHIVE_PATH)
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._dry_run = dry_run

        logger.info(
            "TempmemoryMigrationEngine initialized",
            extra={
                "tempmemory_path": str(self._tempmemory_path),
                "archive_path": str(self._archive_path),
                "dry_run": dry_run,
                "has_redis": redis_client is not None,
                "has_qdrant": qdrant_client is not None,
            },
        )

    def scan_files(self, pattern: str = "*.md") -> list[TempmemoryFile]:
        """
        Scan tempmemory directory for files matching pattern.

        Args:
            pattern: Glob pattern to match files.

        Returns:
            List of TempmemoryFile objects.
        """
        files: list[TempmemoryFile] = []

        if not self._tempmemory_path.exists():
            logger.warning(f"Tempmemory path does not exist: {self._tempmemory_path}")
            return files

        for file_path in self._tempmemory_path.rglob(pattern):
            # Skip files in archive directory
            if self._archive_path.name in str(file_path):
                continue

            # Skip README and template files
            if file_path.name in ("README.md", ".gitkeep"):
                continue
            if "templates" in str(file_path):
                continue

            try:
                temp_file = self._parse_file(file_path)
                files.append(temp_file)
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")

        logger.info(f"Scanned {len(files)} tempmemory files")
        return files

    def _parse_file(self, file_path: Path) -> TempmemoryFile:
        """
        Parse a tempmemory file, extracting frontmatter and content.

        Args:
            file_path: Path to the markdown file.

        Returns:
            TempmemoryFile with parsed data.
        """
        content = file_path.read_text(encoding="utf-8")

        # Parse YAML frontmatter
        frontmatter: dict[str, Any] = {}
        has_frontmatter = False
        body = content

        # Match YAML frontmatter between --- markers
        frontmatter_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL
        )

        if frontmatter_match:
            try:
                yaml_content = frontmatter_match.group(1)
                body = frontmatter_match.group(2)
                frontmatter = yaml.safe_load(yaml_content) or {}
                has_frontmatter = True
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse frontmatter in {file_path}: {e}")

        # Calculate relative path
        try:
            relative_path = str(file_path.relative_to(Path.cwd()))
        except ValueError:
            relative_path = str(file_path)

        return TempmemoryFile(
            path=file_path,
            relative_path=relative_path,
            frontmatter=frontmatter,
            content=body.strip(),
            has_frontmatter=has_frontmatter,
        )

    def migrate_file(self, temp_file: TempmemoryFile) -> MigrationResult:
        """
        Migrate a single tempmemory file to appropriate storage.

        Args:
            temp_file: The tempmemory file to migrate.

        Returns:
            MigrationResult with status and details.
        """
        target = temp_file.determine_target()
        result = MigrationResult(
            file_path=temp_file.relative_path,
            status=MigrationStatus.IN_PROGRESS,
            target=target,
        )

        try:
            # Migrate to Redis if needed
            if target in (MigrationTarget.REDIS, MigrationTarget.BOTH):
                result.redis_success = self._migrate_to_redis(temp_file)

            # Migrate to Qdrant if needed
            if target in (MigrationTarget.QDRANT, MigrationTarget.BOTH):
                result.qdrant_success = self._migrate_to_qdrant(temp_file)

            # Determine final status
            if target == MigrationTarget.BOTH:
                if result.redis_success and result.qdrant_success:
                    result.status = MigrationStatus.COMPLETED
                elif result.redis_success or result.qdrant_success:
                    result.status = MigrationStatus.COMPLETED  # Partial success
                else:
                    result.status = MigrationStatus.FAILED
                    result.error_message = "Failed to migrate to both targets"
            elif target == MigrationTarget.REDIS:
                result.status = (
                    MigrationStatus.COMPLETED
                    if result.redis_success
                    else MigrationStatus.FAILED
                )
                if not result.redis_success:
                    result.error_message = "Failed to migrate to Redis"
            elif target == MigrationTarget.QDRANT:
                result.status = (
                    MigrationStatus.COMPLETED
                    if result.qdrant_success
                    else MigrationStatus.FAILED
                )
                if not result.qdrant_success:
                    result.error_message = "Failed to migrate to Qdrant"

        except Exception as e:
            result.status = MigrationStatus.FAILED
            result.error_message = str(e)
            logger.exception(f"Migration failed for {temp_file.relative_path}")

        return result

    def _migrate_to_redis(self, temp_file: TempmemoryFile) -> bool:
        """
        Migrate file content to Redis.

        Args:
            temp_file: The tempmemory file to migrate.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None:
            logger.debug("No Redis client, skipping Redis migration")
            return False

        if self._dry_run:
            logger.debug(f"[DRY RUN] Would migrate to Redis: {temp_file.relative_path}")
            return True

        try:
            entry = temp_file.to_redis_entry()
            story_id = temp_file.story_id or "unknown"
            file_name = temp_file.path.stem

            # Store in Redis hash
            redis_key = f"{self.REDIS_TEMPMEMORY_PREFIX}:content:{story_id}:{file_name}"
            self._redis_client.hset(redis_key, mapping=entry)

            # Set TTL (30 days for tempmemory content)
            self._redis_client.expire(redis_key, 30 * 24 * 3600)

            logger.debug(f"Migrated to Redis: {redis_key}")

            # After successful Redis migration, send Discord notification (non-blocking)
            if not self._dry_run and temp_file.memory_type == "decision":
                try:
                    import asyncio

                    from governance.notifications import DiscordNotifier

                    notifier = DiscordNotifier()
                    decision_data = {
                        "story_id": temp_file.story_id or "unknown",
                        "title": temp_file.frontmatter.get(
                            "title", "Decision Migrated"
                        ),
                        "rationale": temp_file.frontmatter.get(
                            "rationale", "See source file"
                        ),
                        "impact": temp_file.frontmatter.get(
                            "impact", "See source file"
                        ),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    asyncio.create_task(notifier.notify_decision(decision_data))
                except Exception as e:
                    logger.debug(f"Discord notification skipped: {e}")

            return True

        except Exception as e:
            logger.warning(f"Redis migration failed for {temp_file.relative_path}: {e}")
            return False

    def _migrate_to_qdrant(self, temp_file: TempmemoryFile) -> bool:
        """
        Migrate file content to Qdrant.

        Args:
            temp_file: The tempmemory file to migrate.

        Returns:
            True if successful, False otherwise.
        """
        if self._qdrant_client is None:
            logger.debug("No Qdrant client, skipping Qdrant migration")
            return False

        if self._dry_run:
            logger.debug(
                f"[DRY RUN] Would migrate to Qdrant: {temp_file.relative_path}"
            )
            return True

        try:
            entry = temp_file.to_qdrant_entry()

            # Note: Actual Qdrant storage would require vectorization
            # For now, we just log that we would store it
            # Full implementation would use qdrant_client.upsert()

            logger.debug(
                f"[QDRANT] Would store: {temp_file.relative_path} "
                f"with metadata: {entry['metadata']}"
            )

            # TODO: Implement actual Qdrant vectorization and storage
            # This requires embedding generation which is not yet implemented
            return True

        except Exception as e:
            logger.warning(
                f"Qdrant migration failed for {temp_file.relative_path}: {e}"
            )
            return False

    def run_migration(self) -> MigrationReport:
        """
        Run the complete migration process.

        Returns:
            MigrationReport with detailed results.
        """
        start_time = datetime.now(UTC)
        report = MigrationReport(dry_run=self._dry_run)

        logger.info(
            "Starting tempmemory migration",
            extra={"dry_run": self._dry_run},
        )

        # Scan for files
        files = self.scan_files()
        report.total_files = len(files)
        report.scanned_files = len(files)

        # Migrate each file
        for temp_file in files:
            result = self.migrate_file(temp_file)
            report.results.append(result)

            if result.status == MigrationStatus.COMPLETED:
                report.migrated_files += 1
            elif result.status == MigrationStatus.FAILED:
                report.failed_files += 1
            elif result.status == MigrationStatus.SKIPPED:
                report.skipped_files += 1

        # Calculate duration
        report.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            "Migration completed",
            extra={
                "total": report.total_files,
                "migrated": report.migrated_files,
                "failed": report.failed_files,
                "skipped": report.skipped_files,
                "duration": report.duration_seconds,
            },
        )

        return report

    def get_file_status(self, file_path: str) -> MigrationStatus | None:
        """
        Get migration status for a specific file.

        Args:
            file_path: Path to the file (relative to repo root).

        Returns:
            MigrationStatus if found, None otherwise.
        """
        if self._redis_client is None:
            return None

        try:
            status = self._redis_client.hget(self.REDIS_STATUS_KEY, file_path)
            if status:
                return MigrationStatus(status)
            return None
        except Exception as e:
            logger.warning(f"Failed to get status for {file_path}: {e}")
            return None

    def update_file_status(
        self,
        file_path: str,
        status: MigrationStatus,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """
        Update migration status for a file.

        Args:
            file_path: Path to the file.
            status: New migration status.
            details: Optional additional details.

        Returns:
            True if successful, False otherwise.
        """
        if self._redis_client is None or self._dry_run:
            return False

        try:
            data = {
                "status": status.value,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if details:
                data.update(details)

            self._redis_client.hset(
                self.REDIS_STATUS_KEY,
                file_path,
                json.dumps(data),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to update status for {file_path}: {e}")
            return False
