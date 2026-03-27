"""Tempmemory Migration Module for Autonomous Cognition.

Migrates tempmemory artifacts from docs/tempmemories/ to Qdrant vector storage
using the LearningStore for real writes with rollback capability.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from autonomous_cognition.learning_store import (
    LearningRecord,
    LearningStore,
    get_learning_store,
)

logger = logging.getLogger(__name__)

# Default tempmemory directory
DEFAULT_TEMPMEMORY_DIR = Path("docs/tempmemories")

# Backup directory for rollback
BACKUP_DIR = Path("docs/.tempmemory_backup")

# Collection name for tempmemory artifacts
TEMPMEMORY_COLLECTION = "autocog_tempmemory"

# Record type for tempmemory migrations
RECORD_TYPE_TEMPMEMORY = "tempmemory"


@dataclass
class TempmemoryRecord:
    """A parsed tempmemory artifact."""

    file_path: str
    story_id: str
    date: str
    scope: str
    content: str
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    success: bool
    records_migrated: int
    records_failed: int
    errors: list[str] = field(default_factory=list)
    migrated_ids: list[str] = field(default_factory=list)


@dataclass
class RollbackInfo:
    """Information needed to rollback a migration."""

    migration_id: str
    timestamp: datetime
    record_ids: list[str]
    backup_dir: Path


class TempmemoryMigrator:
    """Handles migration of tempmemory artifacts to Qdrant.

    Provides real vector storage operations with rollback capability
    if migration fails.

    Attributes:
        learning_store: The LearningStore instance for Qdrant writes
        tempmemory_dir: Directory containing tempmemory artifacts
    """

    def __init__(
        self,
        learning_store: LearningStore | None = None,
        tempmemory_dir: Path | str = DEFAULT_TEMPMEMORY_DIR,
    ) -> None:
        """Initialize the TempmemoryMigrator.

        Args:
            learning_store: Optional LearningStore instance (uses singleton if None)
            tempmemory_dir: Path to tempmemory directory
        """
        self.learning_store = learning_store or get_learning_store()
        self.tempmemory_dir = Path(tempmemory_dir)
        self._rollback_info: list[RollbackInfo] = []

    def parse_tempmemory_file(self, file_path: Path) -> TempmemoryRecord | None:
        """Parse a single tempmemory markdown file.

        Args:
            file_path: Path to the tempmemory .md file

        Returns:
            TempmemoryRecord if parsing succeeded, None otherwise
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Split frontmatter and content
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_text = parts[1]
                    body_content = parts[2].strip()
                else:
                    frontmatter_text = ""
                    body_content = content
            else:
                frontmatter_text = ""
                body_content = content

            # Parse YAML frontmatter
            frontmatter: dict[str, Any] = {}
            if frontmatter_text:
                try:
                    frontmatter = yaml.safe_load(frontmatter_text) or {}
                except yaml.YAMLError as e:
                    logger.warning(
                        "Failed to parse frontmatter in %s: %s", file_path, e
                    )

            # Extract required fields with defaults
            story_id = frontmatter.get("story_id", file_path.stem)
            date = frontmatter.get("date", datetime.now(UTC).isoformat())
            scope = frontmatter.get("scope", "unknown")

            return TempmemoryRecord(
                file_path=str(file_path),
                story_id=story_id,
                date=str(date),
                scope=scope,
                content=body_content,
                frontmatter=frontmatter,
            )
        except Exception as e:
            logger.error("Failed to parse tempmemory file %s: %s", file_path, e)
            return None

    def create_learning_record(
        self, tempmemory: TempmemoryRecord, vector: list[float] | None = None
    ) -> LearningRecord:
        """Create a LearningRecord from a TempmemoryRecord.

        Args:
            tempmemory: The parsed tempmemory artifact
            vector: Optional pre-computed embedding

        Returns:
            LearningRecord ready for storage
        """
        # Generate deterministic record ID from file path
        record_id = hashlib.sha256(tempmemory.file_path.encode("utf-8")).hexdigest()[
            :32
        ]

        # Build content string for embedding
        content_parts = [
            f"Story: {tempmemory.story_id}",
            f"Scope: {tempmemory.scope}",
            f"Date: {tempmemory.date}",
            "",
            tempmemory.content[:2000],  # Limit content length
        ]
        content = "\n".join(content_parts)

        # Create metadata
        metadata = {
            "source_file": tempmemory.file_path,
            "story_id": tempmemory.story_id,
            "scope": tempmemory.scope,
            "original_date": tempmemory.date,
            "record_type": RECORD_TYPE_TEMPMEMORY,
            "frontmatter": tempmemory.frontmatter,
        }

        return LearningRecord(
            record_id=record_id,
            record_type=RECORD_TYPE_TEMPMEMORY,
            content=content,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )

    def migrate_file(self, file_path: Path) -> tuple[bool, str]:
        """Migrate a single tempmemory file to Qdrant.

        Args:
            file_path: Path to the tempmemory .md file

        Returns:
            Tuple of (success, record_id)
        """
        tempmemory = self.parse_tempmemory_file(file_path)
        if tempmemory is None:
            return False, ""

        record = self.create_learning_record(tempmemory)
        success = self.learning_store.store_learning(record)

        return success, record.record_id

    def backup_file(self, file_path: Path, backup_dir: Path) -> Path:
        """Create a backup of a tempmemory file.

        Args:
            file_path: Path to the original file
            backup_dir: Directory to store backups

        Returns:
            Path to the backup file
        """
        backup_dir.mkdir(parents=True, exist_ok=True)
        relative_path = file_path.relative_to(self.tempmemory_dir)
        backup_path = backup_dir / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path

    def migrate_all(
        self,
        file_pattern: str = "*.md",
        skip_existing: bool = True,
        create_backups: bool = True,
    ) -> MigrationResult:
        """Migrate all tempmemory files to Qdrant.

        Args:
            file_pattern: Glob pattern for files to migrate
            skip_existing: Skip files already migrated (by story_id check)
            create_backups: Create backups before migration

        Returns:
            MigrationResult with counts and any errors
        """
        result = MigrationResult(
            success=True,
            records_migrated=0,
            records_failed=0,
        )

        if not self.tempmemory_dir.exists():
            result.success = False
            result.errors.append(
                f"Tempmemory directory not found: {self.tempmemory_dir}"
            )
            return result

        # Find all matching files
        files = list(self.tempmemory_dir.glob(file_pattern))
        if not files:
            result.errors.append(f"No files matching {file_pattern} found")
            return result

        # Setup backup directory
        backup_dir = BACKUP_DIR / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if create_backups:
            backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate migration ID
        migration_id = hashlib.sha256(
            datetime.now(UTC).isoformat().encode("utf-8")
        ).hexdigest()[:16]

        migrated_ids: list[str] = []
        errors: list[str] = []

        for file_path in sorted(files):
            # Skip index files
            if file_path.name == "index.md":
                continue

            # Create backup if requested
            if create_backups:
                self.backup_file(file_path, backup_dir)

            # Attempt migration
            success, record_id = self.migrate_file(file_path)

            if success:
                result.records_migrated += 1
                migrated_ids.append(record_id)
            else:
                result.records_failed += 1
                errors.append(f"Failed to migrate: {file_path}")

        # Store rollback info
        if migrated_ids:
            self._rollback_info.append(
                RollbackInfo(
                    migration_id=migration_id,
                    timestamp=datetime.now(UTC),
                    record_ids=migrated_ids,
                    backup_dir=backup_dir,
                )
            )

        result.migrated_ids = migrated_ids
        result.errors = errors
        result.success = result.records_failed == 0

        return result

    def rollback(self, migration_id: str | None = None) -> bool:
        """Rollback a migration by restoring files from backup.

        Args:
            migration_id: ID of migration to rollback (latest if None)

        Returns:
            True if rollback succeeded
        """
        if migration_id is None:
            if not self._rollback_info:
                logger.error("No migration to rollback")
                return False
            rollback_info = self._rollback_info[-1]
        else:
            rollback_info = None
            for info in self._rollback_info:
                if info.migration_id == migration_id:
                    rollback_info = info
                    break
            if rollback_info is None:
                logger.error("Migration not found: %s", migration_id)
                return False

        # Restore files from backup
        if not rollback_info.backup_dir.exists():
            logger.error("Backup directory not found: %s", rollback_info.backup_dir)
            return False

        success = True
        for record_id in rollback_info.record_ids:
            # Find corresponding backup file by scanning
            for backup_file in rollback_info.backup_dir.rglob("*.md"):
                file_record_id = hashlib.sha256(
                    str(backup_file.relative_to(rollback_info.backup_dir)).encode(
                        "utf-8"
                    )
                ).hexdigest()[:32]
                if file_record_id == record_id:
                    # Restore file
                    original_path = self.tempmemory_dir / backup_file.relative_to(
                        rollback_info.backup_dir
                    )
                    original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, original_path)
                    break

        # Clean up backup directory
        shutil.rmtree(rollback_info.backup_dir, ignore_errors=True)
        self._rollback_info.remove(rollback_info)

        logger.info("Rollback completed for migration: %s", rollback_info.migration_id)
        return success

    def get_migration_history(self) -> list[RollbackInfo]:
        """Get history of migrations performed.

        Returns:
            List of RollbackInfo for each migration
        """
        return self._rollback_info.copy()


# Module-level convenience instance
_default_migrator: TempmemoryMigrator | None = None


def get_tempmemory_migrator() -> TempmemoryMigrator:
    """Get or create the default TempmemoryMigrator instance.

    Returns:
        A singleton TempmemoryMigrator instance
    """
    global _default_migrator
    if _default_migrator is None:
        _default_migrator = TempmemoryMigrator()
    return _default_migrator
