"""
Memory Archiver for Consolidation.

Handles archival of memories older than retention period to cold storage.

Story: ST-GOV-005
Governance Feature: GF-005
"""

import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.governance.consolidation.config import (
    CONSOLIDATION_PREFIX,
    MemoryType,
    RetentionPolicy,
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
