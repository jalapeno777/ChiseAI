"""
Tempmemory Provenance Tracking Module for ChiseAI.

Tracks the origin and lineage of every memory for audit trail purposes.
Provides functionality to trace where memories came from and their history.

This module is part of Phase 2 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProvenanceSource(Enum):
    """Source types for memory provenance."""

    TEMPMEMORY_FILE = "tempmemory_file"
    ITERLOG_DECISION = "iterlog_decision"
    REDIS_STATE = "redis_state"
    QDRANT_VECTOR = "qdrant_vector"
    MANUAL_ENTRY = "manual_entry"
    MIGRATION_IMPORT = "migration_import"


@dataclass
class ProvenanceRecord:
    """Provenance record for a single memory.

    Attributes:
        memory_id: Unique identifier for the memory
        source_type: Type of source (file, Redis, Qdrant, etc.)
        source_path: Path or identifier of the source
        commit_sha: Git commit SHA when memory was created/ingested
        timestamp: ISO timestamp of creation
        agent: Agent that created/ingested the memory
        story_id: Associated story ID
        content_hash: SHA256 hash of the content for integrity
        parent_ids: List of parent memory IDs (for derived memories)
        metadata: Additional metadata
    """

    memory_id: str
    source_type: str
    source_path: str
    commit_sha: str
    timestamp: str
    agent: str
    story_id: str | None = None
    content_hash: str = ""
    parent_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "memory_id": self.memory_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp,
            "agent": self.agent,
            "story_id": self.story_id,
            "content_hash": self.content_hash,
            "parent_ids": self.parent_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceRecord:
        """Create from dictionary."""
        return cls(
            memory_id=data["memory_id"],
            source_type=data["source_type"],
            source_path=data["source_path"],
            commit_sha=data["commit_sha"],
            timestamp=data["timestamp"],
            agent=data["agent"],
            story_id=data.get("story_id"),
            content_hash=data.get("content_hash", ""),
            parent_ids=data.get("parent_ids", []),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        memory_id: str,
        source_type: ProvenanceSource,
        source_path: str,
        agent: str,
        content: str = "",
        story_id: str | None = None,
        parent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProvenanceRecord:
        """Create a new provenance record with auto-generated fields."""
        commit_sha = get_current_commit_sha()
        content_hash = compute_content_hash(content) if content else ""

        return cls(
            memory_id=memory_id,
            source_type=source_type.value,
            source_path=source_path,
            commit_sha=commit_sha,
            timestamp=datetime.now(UTC).isoformat(),
            agent=agent,
            story_id=story_id,
            content_hash=content_hash,
            parent_ids=parent_ids or [],
            metadata=metadata or {},
        )


@dataclass
class ProvenanceChain:
    """Chain of provenance records showing memory lineage.

    Attributes:
        memory_id: The target memory ID
        chain: List of provenance records from oldest to newest
    """

    memory_id: str
    chain: list[ProvenanceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "chain": [r.to_dict() for r in self.chain],
        }

    def get_origin(self) -> ProvenanceRecord | None:
        """Get the original source record (oldest in chain)."""
        if self.chain:
            return self.chain[0]
        return None

    def get_latest(self) -> ProvenanceRecord | None:
        """Get the most recent record in the chain."""
        if self.chain:
            return self.chain[-1]
        return None


class ProvenanceTracker:
    """Tracker for memory provenance.

    Manages provenance records in Redis and provides audit functionality.

    Redis Key Structure:
    - bmad:chiseai:tempmemory:provenance:{memory_id} - Hash of provenance data
    - bmad:chiseai:tempmemory:provenance:chain:{memory_id} - List of chain entries
    - bmad:chiseai:tempmemory:provenance:by_source:{source_type} - Set of memory IDs
    - bmad:chiseai:tempmemory:provenance:by_story:{story_id} - Set of memory IDs
    """

    REDIS_PROVENANCE_PREFIX = "bmad:chiseai:tempmemory:provenance"
    REDIS_PROVENANCE_TTL = 90 * 24 * 3600  # 90 days

    def __init__(self, redis_client: Any | None = None, dry_run: bool = False):
        """Initialize the provenance tracker.

        Args:
            redis_client: Optional Redis client.
            dry_run: If True, don't make actual changes.
        """
        self._redis_client = redis_client
        self._dry_run = dry_run

        logger.info(
            "ProvenanceTracker initialized",
            extra={
                "has_redis": redis_client is not None,
                "dry_run": dry_run,
            },
        )

    def record_provenance(
        self,
        memory_id: str,
        source_type: ProvenanceSource,
        source_path: str,
        agent: str,
        content: str = "",
        story_id: str | None = None,
        parent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProvenanceRecord | None:
        """Record provenance for a memory.

        Args:
            memory_id: Unique identifier for the memory.
            source_type: Type of source.
            source_path: Path or identifier of the source.
            agent: Agent that created/ingested the memory.
            content: Content for hash computation.
            story_id: Optional story ID.
            parent_ids: Optional parent memory IDs.
            metadata: Optional additional metadata.

        Returns:
            ProvenanceRecord if successful, None otherwise.
        """
        record = ProvenanceRecord.create(
            memory_id=memory_id,
            source_type=source_type,
            source_path=source_path,
            agent=agent,
            content=content,
            story_id=story_id,
            parent_ids=parent_ids or [],
            metadata=metadata or {},
        )

        if self._dry_run:
            logger.debug(f"[DRY RUN] Would record provenance: {memory_id}")
            return record

        if self._redis_client is None:
            logger.debug(f"No Redis client, skipping provenance for {memory_id}")
            return None

        try:
            # Store provenance record
            redis_key = f"{self.REDIS_PROVENANCE_PREFIX}:{memory_id}"
            self._redis_client.hset(
                redis_key,
                mapping={
                    k: json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                    for k, v in record.to_dict().items()
                },
            )
            self._redis_client.expire(redis_key, self.REDIS_PROVENANCE_TTL)

            # Add to chain
            chain_key = f"{self.REDIS_PROVENANCE_PREFIX}:chain:{memory_id}"
            self._redis_client.rpush(chain_key, json.dumps(record.to_dict()))
            self._redis_client.expire(chain_key, self.REDIS_PROVENANCE_TTL)

            # Index by source type
            if record.source_type:
                source_key = (
                    f"{self.REDIS_PROVENANCE_PREFIX}:by_source:{record.source_type}"
                )
                self._redis_client.sadd(source_key, memory_id)
                self._redis_client.expire(source_key, self.REDIS_PROVENANCE_TTL)

            # Index by story
            if record.story_id:
                story_key = f"{self.REDIS_PROVENANCE_PREFIX}:by_story:{record.story_id}"
                self._redis_client.sadd(story_key, memory_id)
                self._redis_client.expire(story_key, self.REDIS_PROVENANCE_TTL)

            logger.debug(f"Recorded provenance: {memory_id}")
            return record

        except Exception as e:
            logger.warning(f"Failed to record provenance for {memory_id}: {e}")
            return None

    def get_provenance(self, memory_id: str) -> ProvenanceRecord | None:
        """Get provenance record for a memory.

        Args:
            memory_id: The memory ID.

        Returns:
            ProvenanceRecord if found, None otherwise.
        """
        if self._redis_client is None:
            return None

        try:
            redis_key = f"{self.REDIS_PROVENANCE_PREFIX}:{memory_id}"
            data = self._redis_client.hgetall(redis_key)
            if data:
                # Parse the data
                parsed = {}
                for k, v in data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    val = v.decode() if isinstance(v, bytes) else v
                    # Try to parse JSON for complex fields
                    if key in ("parent_ids", "metadata"):
                        try:
                            parsed[key] = json.loads(val)
                        except json.JSONDecodeError:
                            parsed[key] = []
                    else:
                        parsed[key] = val
                return ProvenanceRecord.from_dict(parsed)
            return None
        except Exception as e:
            logger.warning(f"Failed to get provenance for {memory_id}: {e}")
            return None

    def get_provenance_chain(self, memory_id: str) -> ProvenanceChain:
        """Get the full provenance chain for a memory.

        Args:
            memory_id: The memory ID.

        Returns:
            ProvenanceChain with all records in the chain.
        """
        chain = ProvenanceChain(memory_id=memory_id)

        if self._redis_client is None:
            return chain

        try:
            chain_key = f"{self.REDIS_PROVENANCE_PREFIX}:chain:{memory_id}"
            entries = self._redis_client.lrange(chain_key, 0, -1)
            for entry in entries:
                try:
                    data = json.loads(
                        entry.decode() if isinstance(entry, bytes) else entry
                    )
                    chain.chain.append(ProvenanceRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception as e:
            logger.warning(f"Failed to get provenance chain for {memory_id}: {e}")

        return chain

    def query_by_source(self, source_type: ProvenanceSource) -> list[str]:
        """Query memory IDs by source type.

        Args:
            source_type: The source type to query.

        Returns:
            List of memory IDs from that source.
        """
        if self._redis_client is None:
            return []

        try:
            source_key = f"{self.REDIS_PROVENANCE_PREFIX}:by_source:{source_type.value}"
            members = self._redis_client.smembers(source_key)
            return [m.decode() if isinstance(m, bytes) else m for m in members]
        except Exception as e:
            logger.warning(f"Failed to query by source {source_type.value}: {e}")
            return []

    def query_by_story(self, story_id: str) -> list[str]:
        """Query memory IDs by story ID.

        Args:
            story_id: The story ID to query.

        Returns:
            List of memory IDs for that story.
        """
        if self._redis_client is None:
            return []

        try:
            story_key = f"{self.REDIS_PROVENANCE_PREFIX}:by_story:{story_id}"
            members = self._redis_client.smembers(story_key)
            return [m.decode() if isinstance(m, bytes) else m for m in members]
        except Exception as e:
            logger.warning(f"Failed to query by story {story_id}: {e}")
            return []

    def verify_integrity(self, memory_id: str, content: str) -> bool:
        """Verify content integrity against stored hash.

        Args:
            memory_id: The memory ID.
            content: The content to verify.

        Returns:
            True if integrity check passes, False otherwise.
        """
        record = self.get_provenance(memory_id)
        if record is None or not record.content_hash:
            return False

        computed_hash = compute_content_hash(content)
        return computed_hash == record.content_hash

    def generate_audit_report(
        self,
        story_id: str | None = None,
        source_type: ProvenanceSource | None = None,
    ) -> dict[str, Any]:
        """Generate an audit report.

        Args:
            story_id: Optional story ID filter.
            source_type: Optional source type filter.

        Returns:
            Dictionary containing audit report data.
        """
        report: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "filters": {
                "story_id": story_id,
                "source_type": source_type.value if source_type else None,
            },
            "records": [],
            "statistics": {
                "total_records": 0,
                "by_source": {},
                "by_agent": {},
            },
        }

        if self._redis_client is None:
            return report

        try:
            # Get memory IDs based on filters
            if story_id:
                memory_ids = self.query_by_story(story_id)
            elif source_type:
                memory_ids = self.query_by_source(source_type)
            else:
                # Get all - scan for provenance keys
                memory_ids = []
                cursor = 0
                pattern = f"{self.REDIS_PROVENANCE_PREFIX}:*"
                while True:
                    cursor, keys = self._redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    for key in keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        # Extract memory_id from key
                        # Main provenance records: bmad:chiseai:tempmemory:provenance:{memory_id}
                        # Chain records: bmad:chiseai:tempmemory:provenance:chain:{memory_id}
                        # Index keys: bmad:chiseai:tempmemory:provenance:by_source:{source}
                        #            bmad:chiseai:tempmemory:provenance:by_story:{story_id}
                        # Skip chain and index keys - only keep main provenance records
                        if (
                            key_str.startswith(self.REDIS_PROVENANCE_PREFIX + ":")
                            and ":chain:" not in key_str
                            and ":by_source:" not in key_str
                            and ":by_story:" not in key_str
                        ):
                            # Extract memory_id by removing the prefix
                            memory_id = key_str[len(self.REDIS_PROVENANCE_PREFIX) + 1 :]
                            memory_ids.append(memory_id)
                    if cursor == 0:
                        break
                memory_ids = list(set(memory_ids))  # Remove duplicates

            # Get provenance for each memory
            for memory_id in memory_ids:
                record = self.get_provenance(memory_id)
                if record:
                    report["records"].append(record.to_dict())
                    report["statistics"]["total_records"] += 1

                    # Count by source
                    source = record.source_type
                    report["statistics"]["by_source"][source] = (
                        report["statistics"]["by_source"].get(source, 0) + 1
                    )

                    # Count by agent
                    agent = record.agent
                    report["statistics"]["by_agent"][agent] = (
                        report["statistics"]["by_agent"].get(agent, 0) + 1
                    )

        except Exception as e:
            logger.warning(f"Failed to generate audit report: {e}")

        return report


def get_current_commit_sha() -> str:
    """Get the current Git commit SHA.

    Returns:
        The current commit SHA or "unknown" if not in a git repo.
    """
    try:
        result = subprocess.run(  # nosec B607
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return "unknown"


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content.

    Args:
        content: The content to hash.

    Returns:
        Hex digest of the SHA256 hash.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
