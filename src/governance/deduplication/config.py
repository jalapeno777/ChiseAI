"""
Configuration for Memory Deduplication Engine.

Defines similarity thresholds, cache settings, and deduplication policies.

Story: ST-GOV-001
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeduplicationStrategy(Enum):
    """Strategies for detecting duplicates."""

    EXACT_MATCH = "exact_match"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    TEMPORAL_PROXIMITY = "temporal_proximity"
    HYBRID = "hybrid"


@dataclass
class DeduplicationConfig:
    """
    Configuration for memory deduplication.

    Controls similarity thresholds, caching behavior, and audit settings.
    """

    # Similarity thresholds
    similarity_threshold: float = 0.85
    """Default cosine similarity threshold for semantic deduplication (0.0-1.0)"""

    qdrant_similarity_threshold: float = 0.85
    """Threshold for Qdrant vector similarity search"""

    # Cache settings
    redis_hash_cache_ttl: int = 86400  # 24 hours
    """TTL in seconds for Redis hash cache entries"""

    redis_hash_cache_prefix: str = "bmad:chiseai:dedup:hash_cache"
    """Prefix for Redis hash cache keys"""

    # Audit trail settings
    audit_trail_key: str = "bmad:chiseai:deduplication:audit"
    """Redis key for audit trail hash"""

    audit_trail_ttl: int = 2592000  # 30 days
    """TTL in seconds for audit trail entries"""

    # Processing settings
    batch_size: int = 100
    """Number of entries to process per batch"""

    dry_run: bool = True
    """If True, no actual deletions are performed"""

    # Strategy selection
    strategy: DeduplicationStrategy = DeduplicationStrategy.HYBRID
    """Deduplication strategy to use"""

    # Collection settings
    collections: list[str] = field(default_factory=lambda: ["ChiseAI"])
    """Qdrant collections to deduplicate across"""

    # Feature flag
    feature_flag_key: str = "chise:feature_flags:governance:memory_dedup_enabled"
    """Redis key for feature flag"""

    enabled: bool = False
    """Whether deduplication is enabled (controlled by feature flag)"""

    # Hash settings
    hash_algorithm: str = "sha256"
    """Hash algorithm for content hashing"""

    # Temporal settings
    temporal_window_seconds: int = 3600  # 1 hour
    """Time window for temporal proximity deduplication"""

    # Min duplicates threshold
    min_duplicates: int = 2
    """Minimum number of duplicates to trigger consolidation"""

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")
        if not 0.0 <= self.qdrant_similarity_threshold <= 1.0:
            raise ValueError("qdrant_similarity_threshold must be between 0.0 and 1.0")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.redis_hash_cache_ttl < 1:
            raise ValueError("redis_hash_cache_ttl must be positive")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "similarity_threshold": self.similarity_threshold,
            "qdrant_similarity_threshold": self.qdrant_similarity_threshold,
            "redis_hash_cache_ttl": self.redis_hash_cache_ttl,
            "redis_hash_cache_prefix": self.redis_hash_cache_prefix,
            "audit_trail_key": self.audit_trail_key,
            "audit_trail_ttl": self.audit_trail_ttl,
            "batch_size": self.batch_size,
            "dry_run": self.dry_run,
            "strategy": self.strategy.value,
            "collections": self.collections,
            "feature_flag_key": self.feature_flag_key,
            "enabled": self.enabled,
            "hash_algorithm": self.hash_algorithm,
            "temporal_window_seconds": self.temporal_window_seconds,
            "min_duplicates": self.min_duplicates,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeduplicationConfig":
        """Create config from dictionary."""
        config = cls()

        if "similarity_threshold" in data:
            config.similarity_threshold = data["similarity_threshold"]
        if "qdrant_similarity_threshold" in data:
            config.qdrant_similarity_threshold = data["qdrant_similarity_threshold"]
        if "redis_hash_cache_ttl" in data:
            config.redis_hash_cache_ttl = data["redis_hash_cache_ttl"]
        if "redis_hash_cache_prefix" in data:
            config.redis_hash_cache_prefix = data["redis_hash_cache_prefix"]
        if "audit_trail_key" in data:
            config.audit_trail_key = data["audit_trail_key"]
        if "audit_trail_ttl" in data:
            config.audit_trail_ttl = data["audit_trail_ttl"]
        if "batch_size" in data:
            config.batch_size = data["batch_size"]
        if "dry_run" in data:
            config.dry_run = data["dry_run"]
        if "strategy" in data:
            config.strategy = DeduplicationStrategy(data["strategy"])
        if "collections" in data:
            config.collections = data["collections"]
        if "feature_flag_key" in data:
            config.feature_flag_key = data["feature_flag_key"]
        if "enabled" in data:
            config.enabled = data["enabled"]
        if "hash_algorithm" in data:
            config.hash_algorithm = data["hash_algorithm"]
        if "temporal_window_seconds" in data:
            config.temporal_window_seconds = data["temporal_window_seconds"]
        if "min_duplicates" in data:
            config.min_duplicates = data["min_duplicates"]

        return config

    def get_collection_threshold(self, collection_name: str) -> float:
        """
        Get similarity threshold for a specific collection.

        Args:
            collection_name: Name of the Qdrant collection

        Returns:
            Similarity threshold (defaults to qdrant_similarity_threshold)
        """
        # Currently uses global threshold, but can be extended
        # to support per-collection thresholds via Redis config
        return self.qdrant_similarity_threshold


# Redis key prefixes for deduplication
DEDUPLICATION_PREFIX = "bmad:chiseai:dedup"
HASH_CACHE_PREFIX = f"{DEDUPLICATION_PREFIX}:hash_cache"
AUDIT_PREFIX = f"{DEDUPLICATION_PREFIX}:audit"
STATS_PREFIX = f"{DEDUPLICATION_PREFIX}:stats"
