"""
Memory Archiver for Consolidation.

Handles archival of memories older than retention period to cold storage.

Story: ST-GOV-005, ST-MEMORY-INGEST-003
Governance Feature: GF-005
"""

import gzip
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.governance.consolidation.config import (
    CONSOLIDATION_PREFIX,
    AutoArchiveMode,
    MemoryType,
    RetentionPolicy,
    TempmemoryArchiveConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ArchiveStats:
    """Statistics from an archive operation."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    memories_scanned: int = 0
    memories_eligible: int = 0
    memories_archived: int = 0
    memories_preserved: int = 0
    bytes_archived: int = 0
    errors: list[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0
    was_dry_run: bool = True


@dataclass
class ArchivedMemory:
    """Represents an archived memory with metadata."""

    original_id: str
    content: str
    metadata: dict[str, Any]
    archived_at: datetime
    original_collection: str
    memory_type: MemoryType
    access_count: int = 0
    relevance_score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_id": self.original_id,
            "content": self.content,
            "metadata": self.metadata,
            "archived_at": self.archived_at.isoformat(),
            "original_collection": self.original_collection,
            "memory_type": self.memory_type.value,
            "access_count": self.access_count,
            "relevance_score": self.relevance_score,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArchivedMemory":
        """Create from dictionary."""
        return cls(
            original_id=data["original_id"],
            content=data["content"],
            metadata=data["metadata"],
            archived_at=datetime.fromisoformat(data["archived_at"]),
            original_collection=data["original_collection"],
            memory_type=MemoryType(data["memory_type"]),
            access_count=data.get("access_count", 0),
            relevance_score=data.get("relevance_score", 0.0),
            tags=data.get("tags", []),
        )


@dataclass
class TempmemoryArchiveEntry:
    """Represents a single archived tempmemory file with metadata."""

    original_path: Path
    archived_path: Path
    archived_at: datetime
    file_size: int
    file_hash: str
    original_content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_path": str(self.original_path),
            "archived_path": str(self.archived_path),
            "archived_at": self.archived_at.isoformat(),
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TempmemoryArchiveEntry":
        """Create from dictionary."""
        return cls(
            original_path=Path(data["original_path"]),
            archived_path=Path(data["archived_path"]),
            archived_at=datetime.fromisoformat(data["archived_at"]),
            file_size=data["file_size"],
            file_hash=data["file_hash"],
            original_content="",  # Not stored in metadata
            metadata=data.get("metadata", {}),
        )


@dataclass
class TempmemoryArchiveReport:
    """Report of tempmemory archival operations."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    files_archived: list[TempmemoryArchiveEntry] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_size_bytes: int = 0
    was_dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "files_archived": [f.to_dict() for f in self.files_archived],
            "files_skipped": self.files_skipped,
            "errors": self.errors,
            "total_size_bytes": self.total_size_bytes,
            "was_dry_run": self.was_dry_run,
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "# Tempmemory Archive Report",
            "",
            f"**Generated:** {self.timestamp.isoformat()}",
            f"**Mode:** {'Dry Run' if self.was_dry_run else 'Live'}",
            "",
            "## Summary",
            f"- Files archived: {len(self.files_archived)}",
            f"- Files skipped: {len(self.files_skipped)}",
            f"- Errors: {len(self.errors)}",
            f"- Total size: {self.total_size_bytes} bytes",
            "",
        ]

        if self.files_archived:
            lines.extend(["## Archived Files", ""])
            for entry in self.files_archived:
                lines.extend(
                    [
                        f"### {entry.original_path.name}",
                        f"- Original path: `{entry.original_path}`",
                        f"- Archived to: `{entry.archived_path}`",
                        f"- Size: {entry.file_size} bytes",
                        f"- Hash: `{entry.file_hash[:16]}...`",
                        f"- Archived at: {entry.archived_at.isoformat()}",
                        "",
                    ]
                )

        if self.files_skipped:
            lines.extend(["## Skipped Files", ""])
            for path in self.files_skipped:
                lines.append(f"- `{path}`")
            lines.append("")

        if self.errors:
            lines.extend(["## Errors", ""])
            for error in self.errors:
                lines.append(f"- {error}")
            lines.append("")

        return "\n".join(lines)


class MemoryArchiver:
    """
    Handles archival of aged memories to cold storage.

    This component identifies memories older than their retention period
    and moves them to cold storage, preserving their content and metadata
    for potential recovery.

    Safety Features:
    - Dry run mode by default
    - Rollback data preserved
    - Access count considerations
    - Tag-based preservation rules

    Example:
        >>> archiver = MemoryArchiver(config)
        >>> stats = archiver.archive_memories(dry_run=True)
        >>> print(f"Archived {stats.memories_archived} memories")
    """

    def __init__(
        self,
        config: Any,  # ConsolidationConfig
        qdrant_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the memory archiver.

        Args:
            config: ConsolidationConfig instance
            qdrant_client: Optional Qdrant client for vector operations
            redis_client: Optional Redis client for state management
        """
        self._config = config
        self._qdrant_client = qdrant_client
        self._redis_client = redis_client
        self._cold_storage_path = Path(config.cold_storage_path)
        self._last_stats: ArchiveStats | None = None

        logger.info(
            "MemoryArchiver initialized",
            extra={
                "cold_storage_path": str(self._cold_storage_path),
                "dry_run": config.dry_run,
            },
        )

    def _ensure_storage_path(self) -> None:
        """Ensure cold storage directory exists."""
        self._cold_storage_path.mkdir(parents=True, exist_ok=True)

    def _get_archive_path(self, date: datetime | None = None) -> Path:
        """Get the archive file path for a given date."""
        if date is None:
            date = datetime.now(UTC)

        filename = f"memories_{date.strftime('%Y%m%d')}.jsonl.gz"
        return self._cold_storage_path / filename

    def _is_eligible_for_archive(
        self,
        memory: dict[str, Any],
        policy: RetentionPolicy,
    ) -> tuple[bool, str]:
        """
        Check if a memory is eligible for archival.

        Args:
            memory: Memory record to check
            policy: Retention policy to apply

        Returns:
            Tuple of (is_eligible, reason)
        """
        # Check age
        created_at = memory.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            age_days = (datetime.now(UTC) - created_at).days

            if age_days < policy.retention_days:
                return False, f"Memory too young: {age_days} days"

        # Check access count
        access_count = memory.get("access_count", 0)
        if access_count >= policy.min_access_count:
            return False, f"Access count too high: {access_count}"

        # Check preservation tags
        memory_tags = set(memory.get("tags", []))
        preserve_tags = set(policy.preserve_if_tagged)
        if memory_tags & preserve_tags:
            matching_tags = memory_tags & preserve_tags
            return False, f"Has preservation tag(s): {matching_tags}"

        # Check if already golden
        if memory.get("priority") == "golden":
            return False, "Memory is golden priority"

        return True, "Eligible for archival"

    def archive_memories(
        self,
        dry_run: bool | None = None,
        batch_size: int | None = None,
    ) -> ArchiveStats:
        """
        Archive memories older than their retention period.

        Args:
            dry_run: Override config dry_run setting
            batch_size: Override config batch_size setting

        Returns:
            ArchiveStats with operation results
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run
        batch = batch_size or self._config.batch_size

        stats = ArchiveStats(was_dry_run=is_dry_run)

        try:
            if not is_dry_run:
                self._ensure_storage_path()

            archive_path = self._get_archive_path()
            archived_memories: list[ArchivedMemory] = []

            # Scan memories from Qdrant
            if self._qdrant_client is not None:
                memories = self._scan_memories(batch)
                stats.memories_scanned = len(memories)

                for memory in memories:
                    memory_type = self._determine_memory_type(memory)
                    policy = self._config.get_policy(memory_type)

                    is_eligible, reason = self._is_eligible_for_archive(memory, policy)

                    if is_eligible:
                        stats.memories_eligible += 1

                        archived = ArchivedMemory(
                            original_id=memory.get("id", ""),
                            content=memory.get("content", ""),
                            metadata=memory.get("metadata", {}),
                            archived_at=datetime.now(UTC),
                            original_collection=memory.get("collection", "ChiseAI"),
                            memory_type=memory_type,
                            access_count=memory.get("access_count", 0),
                            relevance_score=memory.get("relevance_score", 0.0),
                            tags=memory.get("tags", []),
                        )

                        archived_memories.append(archived)

                        if not is_dry_run:
                            # Store for rollback capability
                            self._store_rollback_data(archived)

                    else:
                        stats.memories_preserved += 1
                        logger.debug(f"Preserving memory {memory.get('id')}: {reason}")

                # Write to cold storage if not dry run
                if archived_memories and not is_dry_run:
                    self._write_to_cold_storage(archive_path, archived_memories)
                    stats.memories_archived = len(archived_memories)
                    stats.bytes_archived = archive_path.stat().st_size

                    # Remove from active collection
                    self._remove_archived_from_active(archived_memories)

                    # Update metrics
                    self._update_metrics(stats)

            logger.info(
                "Archive operation completed",
                extra={
                    "memories_scanned": stats.memories_scanned,
                    "memories_archived": stats.memories_archived,
                    "dry_run": is_dry_run,
                },
            )

        except Exception as e:
            stats.errors.append(str(e))
            logger.exception("Archive operation failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return stats

    def _scan_memories(self, batch_size: int) -> list[dict[str, Any]]:
        """Scan memories from Qdrant collection."""
        # Stub implementation - will be connected to actual Qdrant
        logger.debug(f"Scanning memories with batch size {batch_size}")
        return []

    def _determine_memory_type(self, memory: dict[str, Any]) -> MemoryType:
        """Determine the memory type from metadata."""
        type_str = memory.get("metadata", {}).get("type", "context")
        try:
            return MemoryType(type_str)
        except ValueError:
            return MemoryType.CONTEXT

    def _write_to_cold_storage(
        self,
        path: Path,
        memories: list[ArchivedMemory],
    ) -> None:
        """Write archived memories to cold storage file."""
        with gzip.open(path, "at", encoding="utf-8") as f:
            for memory in memories:
                f.write(json.dumps(memory.to_dict()) + "\n")

        logger.info(f"Wrote {len(memories)} memories to {path}")

    def _remove_archived_from_active(
        self,
        memories: list[ArchivedMemory],
    ) -> None:
        """Remove archived memories from active Qdrant collection."""
        if self._qdrant_client is None:
            return

        ids_to_remove = [m.original_id for m in memories]
        logger.info(f"Removing {len(ids_to_remove)} memories from active storage")

        # Stub - actual Qdrant deletion would go here

    def _store_rollback_data(self, archived: ArchivedMemory) -> None:
        """Store rollback data in Redis for 7-day recovery window."""
        if self._redis_client is None:
            return

        rollback_key = f"{CONSOLIDATION_PREFIX}:rollback:{archived.original_id}"
        rollback_data = {
            "archived_at": archived.archived_at.isoformat(),
            "original_collection": archived.original_collection,
            "archive_file": str(self._get_archive_path()),
            "memory_type": archived.memory_type.value,
        }

        try:
            # Store with 7-day expiration
            self._redis_client.setex(
                rollback_key,
                self._config.rollback_retention_days * 86400,
                json.dumps(rollback_data),
            )
        except Exception as e:
            logger.warning(f"Could not store rollback data: {e}")

    def _update_metrics(self, stats: ArchiveStats) -> None:
        """Update consolidation metrics in Redis."""
        if self._redis_client is None:
            return

        try:
            metrics_key = f"{CONSOLIDATION_PREFIX}:metrics:archive"
            self._redis_client.hset(
                metrics_key,
                mapping={
                    "last_run": stats.timestamp.isoformat(),
                    "memories_archived": stats.memories_archived,
                    "bytes_archived": stats.bytes_archived,
                    "dry_run": str(stats.was_dry_run).lower(),
                },
            )
        except Exception as e:
            logger.warning(f"Could not update metrics: {e}")

    def get_stats(self) -> ArchiveStats | None:
        """Get statistics from last archive run."""
        return self._last_stats

    def get_cold_storage_size(self) -> int:
        """Get total size of cold storage in bytes."""
        if not self._cold_storage_path.exists():
            return 0

        return sum(f.stat().st_size for f in self._cold_storage_path.glob("*.jsonl.gz"))

    # ==========================================================================
    # Tempmemory Auto-Archive Methods (ST-MEMORY-INGEST-003)
    # ==========================================================================

    def archive_tempmemories(
        self,
        tempmemory_paths: list[Path],
        config: TempmemoryArchiveConfig | None = None,
        dry_run: bool | None = None,
    ) -> TempmemoryArchiveReport:
        """
        Archive tempmemory files to cold storage.

        Args:
            tempmemory_paths: List of paths to tempmemory files to archive
            config: Tempmemory archive configuration (uses self._config if None)
            dry_run: Override config dry_run setting

        Returns:
            TempmemoryArchiveReport with operation results
        """
        archive_config = config or self._config.tempmemory_archive
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run

        report = TempmemoryArchiveReport(was_dry_run=is_dry_run)

        if not archive_config.enabled:
            logger.info("Tempmemory auto-archive is disabled")
            return report

        try:
            # Ensure archive directory exists
            archive_dir = Path(archive_config.archive_location)
            if not is_dry_run:
                archive_dir.mkdir(parents=True, exist_ok=True)

            for tempmemory_path in tempmemory_paths:
                try:
                    # Check if already archived (re-ingestion prevention)
                    if archive_config.skip_already_archived:
                        if self._is_tempmemory_archived(tempmemory_path):
                            report.files_skipped.append(str(tempmemory_path))
                            logger.debug(
                                f"Skipping already archived: {tempmemory_path}"
                            )
                            continue

                    # Archive the file
                    entry = self._archive_single_tempmemory(
                        tempmemory_path, archive_dir, archive_config, is_dry_run
                    )

                    if entry:
                        report.files_archived.append(entry)
                        report.total_size_bytes += entry.file_size

                        # Track in Redis for re-ingestion prevention
                        if not is_dry_run:
                            self._track_archived_tempmemory(tempmemory_path, entry)

                except Exception as e:
                    error_msg = f"Failed to archive {tempmemory_path}: {e}"
                    report.errors.append(error_msg)
                    logger.error(error_msg)

            # Generate report file if configured
            if archive_config.generate_reports and not is_dry_run:
                self._generate_archive_report(report, archive_dir, archive_config)

        except Exception as e:
            report.errors.append(f"Archive operation failed: {e}")
            logger.exception("Tempmemory archive operation failed")

        return report

    def _archive_single_tempmemory(
        self,
        tempmemory_path: Path,
        archive_dir: Path,
        config: TempmemoryArchiveConfig,
        dry_run: bool,
    ) -> TempmemoryArchiveEntry | None:
        """Archive a single tempmemory file."""
        if not tempmemory_path.exists():
            logger.warning(f"File not found: {tempmemory_path}")
            return None

        # Read file content
        content = tempmemory_path.read_text(encoding="utf-8")
        file_size = tempmemory_path.stat().st_size
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        # Determine archive path
        archived_path = self._get_tempmemory_archive_path(
            tempmemory_path, archive_dir, config
        )

        # Extract metadata from frontmatter if present
        metadata = self._extract_tempmemory_metadata(content)

        if config.preserve_original_path:
            metadata["original_path"] = str(tempmemory_path)
            metadata["ingestion_timestamp"] = datetime.now(UTC).isoformat()

        entry = TempmemoryArchiveEntry(
            original_path=tempmemory_path,
            archived_path=archived_path,
            archived_at=datetime.now(UTC),
            file_size=file_size,
            file_hash=file_hash,
            original_content=content,
            metadata=metadata,
        )

        if not dry_run:
            # Write to archive
            archived_path.parent.mkdir(parents=True, exist_ok=True)
            archived_path.write_text(content, encoding="utf-8")

            # Remove original file
            tempmemory_path.unlink()

            logger.info(f"Archived {tempmemory_path} to {archived_path}")

        return entry

    def _get_tempmemory_archive_path(
        self,
        original_path: Path,
        archive_dir: Path,
        config: TempmemoryArchiveConfig,
    ) -> Path:
        """Generate archive path for a tempmemory file."""
        # Preserve directory structure under archive
        relative_path = original_path.name
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        archive_name = f"{original_path.stem}_{timestamp}{original_path.suffix}"
        return archive_dir / archive_name

    def _extract_tempmemory_metadata(self, content: str) -> dict[str, Any]:
        """Extract metadata from tempmemory frontmatter."""
        metadata: dict[str, Any] = {}

        if content.startswith("---"):
            try:
                # Find end of frontmatter
                end_idx = content.find("\n---", 3)
                if end_idx != -1:
                    frontmatter = content[3:end_idx].strip()
                    # Simple YAML-like parsing for common fields
                    for line in frontmatter.split("\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            metadata[key.strip()] = value.strip()
            except Exception as e:
                logger.debug(f"Could not parse frontmatter: {e}")

        return metadata

    def _is_tempmemory_archived(self, tempmemory_path: Path) -> bool:
        """Check if a tempmemory file has already been archived."""
        if self._redis_client is None:
            return False

        try:
            key = f"{CONSOLIDATION_PREFIX}:archived_tempmemories"
            archived_hash = hashlib.sha256(str(tempmemory_path).encode()).hexdigest()
            return self._redis_client.sismember(key, archived_hash)
        except Exception as e:
            logger.debug(f"Could not check archived status: {e}")
            return False

    def _track_archived_tempmemory(
        self,
        tempmemory_path: Path,
        entry: TempmemoryArchiveEntry,
    ) -> None:
        """Track archived tempmemory in Redis for re-ingestion prevention."""
        if self._redis_client is None:
            return

        try:
            key = f"{CONSOLIDATION_PREFIX}:archived_tempmemories"
            archived_hash = hashlib.sha256(str(tempmemory_path).encode()).hexdigest()

            # Store with 30-day expiration
            self._redis_client.sadd(key, archived_hash)
            self._redis_client.expire(key, 30 * 86400)

            # Also store detailed metadata
            detail_key = f"{CONSOLIDATION_PREFIX}:archived_tempmemory:{archived_hash}"
            self._redis_client.hset(detail_key, mapping=entry.to_dict())
            self._redis_client.expire(detail_key, 30 * 86400)

        except Exception as e:
            logger.warning(f"Could not track archived tempmemory: {e}")

    def _generate_archive_report(
        self,
        report: TempmemoryArchiveReport,
        archive_dir: Path,
        config: TempmemoryArchiveConfig,
    ) -> Path:
        """Generate and save archive report."""
        reports_dir = archive_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = report.timestamp.strftime("%Y%m%d_%H%M%S")

        if config.report_format == "markdown":
            report_path = reports_dir / f"archive_report_{timestamp}.md"
            report_path.write_text(report.to_markdown(), encoding="utf-8")
        else:
            report_path = reports_dir / f"archive_report_{timestamp}.json"
            report_path.write_text(
                json.dumps(report.to_dict(), indent=2), encoding="utf-8"
            )

        logger.info(f"Generated archive report: {report_path}")
        return report_path

    def should_archive_tempmemory(
        self,
        tempmemory_path: Path,
        config: TempmemoryArchiveConfig | None = None,
    ) -> bool:
        """
        Check if a tempmemory should be archived based on mode and timing.

        Args:
            tempmemory_path: Path to tempmemory file
            config: Archive configuration

        Returns:
            True if file should be archived
        """
        archive_config = config or self._config.tempmemory_archive

        if not archive_config.enabled:
            return False

        if archive_config.mode == AutoArchiveMode.IMMEDIATE:
            return True

        if archive_config.mode == AutoArchiveMode.AFTER_N_DAYS:
            # Check file age
            try:
                stat = tempmemory_path.stat()
                file_age = datetime.now(UTC) - datetime.fromtimestamp(
                    stat.st_mtime, UTC
                )
                return file_age.days >= archive_config.delay_days
            except Exception as e:
                logger.warning(f"Could not check file age: {e}")
                return False

        # DAILY mode - check if scheduled time has passed
        if archive_config.mode == AutoArchiveMode.DAILY:
            now = datetime.now(UTC)
            scheduled_time = now.replace(
                hour=archive_config.daily_schedule_time.hour,
                minute=archive_config.daily_schedule_time.minute,
                second=0,
                microsecond=0,
            )
            return now >= scheduled_time

        return False

    def get_archived_tempmemories(self) -> list[dict[str, Any]]:
        """Get list of archived tempmemories from Redis."""
        if self._redis_client is None:
            return []

        try:
            key = f"{CONSOLIDATION_PREFIX}:archived_tempmemories"
            archived_hashes = self._redis_client.smembers(key)

            results = []
            for hash_val in archived_hashes:
                detail_key = f"{CONSOLIDATION_PREFIX}:archived_tempmemory:{hash_val}"
                data = self._redis_client.hgetall(detail_key)
                if data:
                    results.append(data)

            return results
        except Exception as e:
            logger.warning(f"Could not retrieve archived tempmemories: {e}")
            return []
