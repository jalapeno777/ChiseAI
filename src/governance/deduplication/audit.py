"""
Audit Trail for Memory Deduplication.

Records all deduplication decisions with configurable thresholds for auditability.

Story: ST-GOV-001
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.governance.deduplication.config import DeduplicationConfig


class DeduplicationAction(Enum):
    """Actions that can be recorded in the audit trail."""

    DUPLICATE_DETECTED = "duplicate_detected"
    DUPLICATE_REMOVED = "duplicate_removed"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    SIMILARITY_CHECK = "similarity_check"
    THRESHOLD_ADJUSTED = "threshold_adjusted"


class DeduplicationResult(Enum):
    """Result of a deduplication decision."""

    REMOVED = "removed"
    KEPT = "kept"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class AuditEntry:
    """Single entry in the deduplication audit trail."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for this audit entry"""

    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    """When the action occurred"""

    action: DeduplicationAction = DeduplicationAction.SIMILARITY_CHECK
    """Type of action recorded"""

    result: DeduplicationResult = DeduplicationResult.KEPT
    """Result of the deduplication decision"""

    source_id: str = ""
    """ID of the source entry"""

    duplicate_id: Optional[str] = None
    """ID of the duplicate entry (if applicable)"""

    collection: str = ""
    """Collection name"""

    similarity_score: Optional[float] = None
    """Similarity score if applicable (0.0-1.0)"""

    threshold_used: float = 0.85
    """Similarity threshold used for the decision"""

    strategy: str = "hybrid"
    """Deduplication strategy used"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata"""

    reason: str = ""
    """Human-readable reason for the decision"""

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "result": self.result.value,
            "source_id": self.source_id,
            "duplicate_id": self.duplicate_id,
            "collection": self.collection,
            "similarity_score": self.similarity_score,
            "threshold_used": self.threshold_used,
            "strategy": self.strategy,
            "metadata": self.metadata,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEntry":
        """Create entry from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            action=DeduplicationAction(data["action"]),
            result=DeduplicationResult(data["result"]),
            source_id=data["source_id"],
            duplicate_id=data.get("duplicate_id"),
            collection=data["collection"],
            similarity_score=data.get("similarity_score"),
            threshold_used=data.get("threshold_used", 0.85),
            strategy=data.get("strategy", "hybrid"),
            metadata=data.get("metadata", {}),
            reason=data.get("reason", ""),
        )


class AuditTrail:
    """
    Redis-based audit trail for deduplication decisions.

    Records all deduplication actions with configurable thresholds
    for complete auditability.
    """

    def __init__(self, config: Optional[DeduplicationConfig] = None):
        self.config = config or DeduplicationConfig()
        self._redis_client = None

    def _get_redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            try:
                from redis import Redis

                self._redis_client = Redis(
                    host="host.docker.internal",
                    port=6380,
                    db=0,
                    decode_responses=True,
                )
            except ImportError:
                raise RuntimeError(
                    "Redis not available. Install with: pip install redis"
                )
        return self._redis_client

    def _make_key(self, entry_id: str) -> str:
        """Create Redis key for an audit entry."""
        return f"{self.config.audit_trail_key}:{entry_id}"

    def log(
        self,
        action: DeduplicationAction,
        result: DeduplicationResult,
        source_id: str,
        collection: str,
        duplicate_id: Optional[str] = None,
        similarity_score: Optional[float] = None,
        threshold_used: Optional[float] = None,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> AuditEntry:
        """
        Log a deduplication decision to the audit trail.

        Args:
            action: Type of action
            result: Result of the decision
            source_id: ID of the source entry
            collection: Collection name
            duplicate_id: ID of duplicate entry (if applicable)
            similarity_score: Similarity score (0.0-1.0)
            threshold_used: Threshold used for decision
            reason: Human-readable reason
            metadata: Additional metadata

        Returns:
            The created AuditEntry
        """
        redis_client = self._get_redis_client()

        entry = AuditEntry(
            action=action,
            result=result,
            source_id=source_id,
            duplicate_id=duplicate_id,
            collection=collection,
            similarity_score=similarity_score,
            threshold_used=threshold_used or self.config.similarity_threshold,
            strategy=self.config.strategy.value,
            reason=reason,
            metadata=metadata or {},
        )

        key = self._make_key(entry.entry_id)
        redis_client.hset(
            key,
            mapping={
                "data": json.dumps(entry.to_dict()),
                "timestamp": entry.timestamp.isoformat(),
                "collection": collection,
                "action": action.value,
            },
        )
        redis_client.expire(key, self.config.audit_trail_ttl)

        # Also add to a list for chronological access
        list_key = f"{self.config.audit_trail_key}:list"
        redis_client.lpush(list_key, entry.entry_id)
        redis_client.expire(list_key, self.config.audit_trail_ttl)

        return entry

    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """
        Retrieve a specific audit entry.

        Args:
            entry_id: ID of the entry to retrieve

        Returns:
            AuditEntry if found, None otherwise
        """
        redis_client = self._get_redis_client()
        key = self._make_key(entry_id)

        data = redis_client.hget(key, "data")
        if data:
            try:
                return AuditEntry.from_dict(json.loads(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                return None

        return None

    def get_recent_entries(
        self,
        limit: int = 100,
        collection: Optional[str] = None,
        action: Optional[DeduplicationAction] = None,
    ) -> list[AuditEntry]:
        """
        Get recent audit entries.

        Args:
            limit: Maximum number of entries to return
            collection: Filter by collection name
            action: Filter by action type

        Returns:
            List of AuditEntry objects
        """
        redis_client = self._get_redis_client()
        list_key = f"{self.config.audit_trail_key}:list"

        entry_ids = redis_client.lrange(
            list_key, 0, limit * 2
        )  # Get extra for filtering
        entries = []

        for entry_id in entry_ids:
            entry = self.get_entry(entry_id)
            if entry is None:
                continue

            # Apply filters
            if collection and entry.collection != collection:
                continue
            if action and entry.action != action:
                continue

            entries.append(entry)

            if len(entries) >= limit:
                break

        return entries

    def get_stats(self) -> dict[str, Any]:
        """
        Get audit trail statistics.

        Returns:
            Dictionary with statistics
        """
        redis_client = self._get_redis_client()
        pattern = f"{self.config.audit_trail_key}:*"

        keys = list(redis_client.scan_iter(match=pattern))
        count = len(keys)

        # Count by action type
        action_counts = {}
        result_counts = {}

        for key in keys:
            if key.endswith(":list"):
                continue

            data = redis_client.hget(key, "data")
            if data:
                try:
                    entry_data = json.loads(data)
                    action = entry_data.get("action", "unknown")
                    result = entry_data.get("result", "unknown")
                    action_counts[action] = action_counts.get(action, 0) + 1
                    result_counts[result] = result_counts.get(result, 0) + 1
                except json.JSONDecodeError:
                    continue

        return {
            "total_entries": count,
            "action_counts": action_counts,
            "result_counts": result_counts,
            "ttl_seconds": self.config.audit_trail_ttl,
        }

    def clear(self) -> int:
        """
        Clear all audit trail entries.

        Returns:
            Number of entries cleared
        """
        redis_client = self._get_redis_client()
        pattern = f"{self.config.audit_trail_key}:*"

        keys = list(redis_client.scan_iter(match=pattern))
        if keys:
            return redis_client.delete(*keys)
        return 0
