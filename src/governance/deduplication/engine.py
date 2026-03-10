"""
Memory Deduplication Engine for ChiseAI Governance.

Identifies and eliminates duplicate memory entries across Qdrant collections
with configurable similarity thresholds and Redis-based hash caching.

Story: ST-GOV-001
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from src.governance.deduplication.audit import (
    AuditTrail,
    DeduplicationAction,
    DeduplicationResult,
)
from src.governance.deduplication.config import (
    DEDUPLICATION_PREFIX,
    DeduplicationConfig,
    DeduplicationStrategy,
)
from src.governance.deduplication.hash_cache import HashCache


@dataclass
class DeduplicationStats:
    """Statistics from a deduplication run."""

    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    """When the run started"""

    collections_scanned: int = 0
    """Number of collections scanned"""

    entries_scanned: int = 0
    """Total entries scanned"""

    duplicate_groups: int = 0
    """Number of duplicate groups found"""

    entries_to_remove: int = 0
    """Entries that would be removed (dry run)"""

    entries_removed: int = 0
    """Entries actually removed"""

    cache_hits: int = 0
    """Number of cache hits"""

    cache_misses: int = 0
    """Number of cache misses"""

    similarity_checks: int = 0
    """Number of similarity checks performed"""

    processing_time_seconds: float = 0.0
    """Total processing time"""

    was_dry_run: bool = True
    """Whether this was a dry run"""

    errors: list[str] = field(default_factory=list)
    """Any errors encountered"""

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "collections_scanned": self.collections_scanned,
            "entries_scanned": self.entries_scanned,
            "duplicate_groups": self.duplicate_groups,
            "entries_to_remove": self.entries_to_remove,
            "entries_removed": self.entries_removed,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "similarity_checks": self.similarity_checks,
            "processing_time_seconds": self.processing_time_seconds,
            "was_dry_run": self.was_dry_run,
            "errors": self.errors,
        }


@dataclass
class DuplicateGroup:
    """Represents a group of duplicate entries."""

    group_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for this group"""

    canonical_id: str = ""
    """ID of the canonical (kept) entry"""

    duplicate_ids: list[str] = field(default_factory=list)
    """IDs of duplicate entries to remove"""

    collection: str = ""
    """Collection name"""

    similarity_score: float = 0.0
    """Maximum similarity score within group"""

    reason: str = ""
    """Reason for grouping"""

    def to_dict(self) -> dict[str, Any]:
        """Convert group to dictionary."""
        return {
            "group_id": self.group_id,
            "canonical_id": self.canonical_id,
            "duplicate_ids": self.duplicate_ids,
            "collection": self.collection,
            "similarity_score": self.similarity_score,
            "reason": self.reason,
        }


class MemoryDeduplicationEngine:
    """
    Main engine for memory deduplication across Qdrant collections.

    Provides:
    - Configurable similarity thresholds
    - Redis-based hash caching
    - Audit trail for all decisions
    - Support for multiple collections
    - Dry-run mode for safety
    """

    def __init__(self, config: DeduplicationConfig | None = None):
        """
        Initialize the deduplication engine.

        Args:
            config: Configuration for deduplication. Uses defaults if not provided.
        """
        self.config = config or DeduplicationConfig()
        self.hash_cache = HashCache(self.config)
        self.audit_trail = AuditTrail(self.config)
        self._qdrant_client = None
        self._redis_client = None

    def _get_qdrant_client(self):
        """Lazy initialization of Qdrant client."""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient

                self._qdrant_client = QdrantClient(
                    host="host.docker.internal",
                    port=6334,
                )
            except ImportError:
                raise RuntimeError(
                    "Qdrant client not available. Install with: pip install qdrant-client"
                )
        return self._qdrant_client

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

    def is_enabled(self) -> bool:
        """
        Check if deduplication is enabled via feature flag.

        Returns:
            True if enabled, False otherwise
        """
        try:
            redis_client = self._get_redis_client()
            enabled = redis_client.get(self.config.feature_flag_key)
            return enabled == b"true" or enabled == "true" or self.config.enabled
        except Exception:
            return self.config.enabled

    def enable(self) -> None:
        """Enable deduplication via feature flag."""
        try:
            redis_client = self._get_redis_client()
            redis_client.set(self.config.feature_flag_key, "true")
            self.config.enabled = True
        except Exception as e:
            raise RuntimeError(f"Failed to enable deduplication: {e}")

    def disable(self) -> None:
        """Disable deduplication via feature flag."""
        try:
            redis_client = self._get_redis_client()
            redis_client.set(self.config.feature_flag_key, "false")
            self.config.enabled = False
        except Exception as e:
            raise RuntimeError(f"Failed to disable deduplication: {e}")

    def check_duplicate(
        self, content: str, collection: str = "ChiseAI"
    ) -> tuple[bool, float | None, str | None]:
        """
        Check if content is a duplicate.

        Args:
            content: Content to check
            collection: Collection to check against

        Returns:
            Tuple of (is_duplicate, similarity_score, source_id)
        """
        # First check hash cache
        is_cached, cached_id = self.hash_cache.is_duplicate(content)
        if is_cached:
            self.audit_trail.log(
                action=DeduplicationAction.CACHE_HIT,
                result=DeduplicationResult.KEPT,
                source_id=cached_id or "unknown",
                collection=collection,
                reason="Content hash found in cache",
            )
            return True, 1.0, cached_id

        self.audit_trail.log(
            action=DeduplicationAction.CACHE_MISS,
            result=DeduplicationResult.SKIPPED,
            source_id="unknown",
            collection=collection,
            reason="Content hash not in cache",
        )

        # If not in cache, check Qdrant for similar vectors
        # This would require embedding the content, which we'll handle
        # in the full deduplication scan
        return False, None, None

    def deduplicate(
        self,
        dry_run: bool | None = None,
        collections: list[str] | None = None,
    ) -> DeduplicationStats:
        """
        Run deduplication across specified collections.

        Args:
            dry_run: If True, don't actually remove duplicates.
                     Defaults to config.dry_run.
            collections: List of collections to deduplicate.
                        Defaults to config.collections.

        Returns:
            DeduplicationStats with results
        """
        start_time = datetime.utcnow()
        stats = DeduplicationStats(
            timestamp=start_time,
            was_dry_run=dry_run if dry_run is not None else self.config.dry_run,
        )

        collections = collections or self.config.collections
        stats.collections_scanned = len(collections)

        try:
            for collection in collections:
                collection_stats = self._deduplicate_collection(
                    collection, dry_run or self.config.dry_run
                )
                stats.entries_scanned += collection_stats.entries_scanned
                stats.duplicate_groups += collection_stats.duplicate_groups
                stats.entries_to_remove += collection_stats.entries_to_remove
                stats.entries_removed += collection_stats.entries_removed
                stats.cache_hits += collection_stats.cache_hits
                stats.cache_misses += collection_stats.cache_misses
                stats.similarity_checks += collection_stats.similarity_checks
                stats.errors.extend(collection_stats.errors)

        except Exception as e:
            stats.errors.append(str(e))

        end_time = datetime.utcnow()
        stats.processing_time_seconds = (end_time - start_time).total_seconds()

        # Store stats in Redis
        self._store_stats(stats)

        return stats

    def _deduplicate_collection(
        self,
        collection: str,
        dry_run: bool,
    ) -> DeduplicationStats:
        """
        Deduplicate a single collection.

        Args:
            collection: Collection name
            dry_run: If True, don't remove duplicates

        Returns:
            DeduplicationStats for this collection
        """
        stats = DeduplicationStats(was_dry_run=dry_run)
        threshold = self.config.get_collection_threshold(collection)

        try:
            qdrant_client = self._get_qdrant_client()

            # Get all points from collection
            # Note: In production, this would use scroll with batching
            # For now, we'll implement the logic structure
            points = qdrant_client.scroll(
                collection_name=collection,
                limit=self.config.batch_size,
                with_payload=True,
                with_vectors=True,
            )[0]

            stats.entries_scanned = len(points)

            # Group by similarity
            duplicate_groups = self._find_duplicates(points, threshold, collection)

            for group in duplicate_groups:
                stats.duplicate_groups += 1
                stats.entries_to_remove += len(group.duplicate_ids)

                if (
                    not dry_run
                    and len(group.duplicate_ids) >= self.config.min_duplicates
                ):
                    # Remove duplicates
                    try:
                        qdrant_client.delete(
                            collection_name=collection,
                            points_selector=group.duplicate_ids,
                        )
                        stats.entries_removed += len(group.duplicate_ids)

                        # Log audit entry
                        self.audit_trail.log(
                            action=DeduplicationAction.DUPLICATE_REMOVED,
                            result=DeduplicationResult.REMOVED,
                            source_id=group.canonical_id,
                            collection=collection,
                            duplicate_id=",".join(group.duplicate_ids),
                            similarity_score=group.similarity_score,
                            threshold_used=threshold,
                            reason=group.reason,
                        )
                    except Exception as e:
                        stats.errors.append(
                            f"Failed to remove duplicates in {collection}: {e}"
                        )
                else:
                    # Log what would be removed (dry run or not enough duplicates)
                    self.audit_trail.log(
                        action=DeduplicationAction.DUPLICATE_DETECTED,
                        result=(
                            DeduplicationResult.SKIPPED
                            if dry_run
                            else DeduplicationResult.KEPT
                        ),
                        source_id=group.canonical_id,
                        collection=collection,
                        duplicate_id=",".join(group.duplicate_ids),
                        similarity_score=group.similarity_score,
                        threshold_used=threshold,
                        reason=group.reason
                        + (" (dry run)" if dry_run else " (below min_duplicates)"),
                    )

        except Exception as e:
            stats.errors.append(f"Error deduplicating {collection}: {e}")

        return stats

    def _find_duplicates(
        self,
        points: list,
        threshold: float,
        collection: str,
    ) -> list[DuplicateGroup]:
        """
        Find duplicate groups among points.

        Args:
            points: List of Qdrant points
            threshold: Similarity threshold
            collection: Collection name

        Returns:
            List of DuplicateGroup objects
        """
        groups = []
        processed_ids = set()

        for i, point in enumerate(points):
            if point.id in processed_ids:
                continue

            # Find similar points
            similar_points = self._find_similar_points(
                point, points[i + 1 :], threshold, collection
            )

            if similar_points:
                group = DuplicateGroup(
                    canonical_id=str(point.id),
                    duplicate_ids=[str(p.id) for p in similar_points],
                    collection=collection,
                    similarity_score=self._calculate_max_similarity(
                        point, similar_points
                    ),
                    reason=f"Similarity >= {threshold} via {self.config.strategy.value} strategy",
                )
                groups.append(group)

                processed_ids.add(point.id)
                processed_ids.update(p.id for p in similar_points)

        return groups

    def _find_similar_points(
        self,
        reference_point: Any,
        candidate_points: list,
        threshold: float,
        collection: str,
    ) -> list:
        """
        Find points similar to the reference point.

        Args:
            reference_point: Reference point
            candidate_points: Points to compare against
            threshold: Similarity threshold
            collection: Collection name

        Returns:
            List of similar points
        """
        similar = []

        for candidate in candidate_points:
            similarity = self._calculate_similarity(
                reference_point, candidate, collection
            )

            if similarity >= threshold:
                similar.append(candidate)
                self.audit_trail.log(
                    action=DeduplicationAction.SIMILARITY_CHECK,
                    result=DeduplicationResult.KEPT,
                    source_id=str(reference_point.id),
                    collection=collection,
                    duplicate_id=str(candidate.id),
                    similarity_score=similarity,
                    threshold_used=threshold,
                    reason=f"Similarity {similarity:.3f} >= threshold {threshold}",
                )

        return similar

    def _calculate_similarity(
        self,
        point_a: Any,
        point_b: Any,
        collection: str,
    ) -> float:
        """
        Calculate similarity between two points.

        Args:
            point_a: First point
            point_b: Second point
            collection: Collection name

        Returns:
            Similarity score (0.0-1.0)
        """
        if self.config.strategy == DeduplicationStrategy.EXACT_MATCH:
            return self._exact_match_similarity(point_a, point_b)
        elif self.config.strategy == DeduplicationStrategy.SEMANTIC_SIMILARITY:
            return self._cosine_similarity(point_a, point_b)
        elif self.config.strategy == DeduplicationStrategy.TEMPORAL_PROXIMITY:
            return self._temporal_similarity(point_a, point_b)
        else:  # HYBRID
            return self._hybrid_similarity(point_a, point_b)

    def _cosine_similarity(self, point_a: Any, point_b: Any) -> float:
        """Calculate cosine similarity between two points' vectors."""
        try:
            vec_a = np.array(point_a.vector)
            vec_b = np.array(point_b.vector)

            dot_product = np.dot(vec_a, vec_b)
            norm_a = np.linalg.norm(vec_a)
            norm_b = np.linalg.norm(vec_b)

            if norm_a == 0 or norm_b == 0:
                return 0.0

            return float(dot_product / (norm_a * norm_b))
        except Exception:
            return 0.0

    def _exact_match_similarity(self, point_a: Any, point_b: Any) -> float:
        """Check for exact match in content."""
        try:
            content_a = str(point_a.payload.get("content", ""))
            content_b = str(point_b.payload.get("content", ""))

            if content_a == content_b:
                return 1.0

            # Also check hash
            hash_a = self.hash_cache.compute_hash(content_a)
            hash_b = self.hash_cache.compute_hash(content_b)

            return 1.0 if hash_a == hash_b else 0.0
        except Exception:
            return 0.0

    def _temporal_similarity(self, point_a: Any, point_b: Any) -> float:
        """Calculate similarity based on temporal proximity."""
        try:
            # Get timestamps from metadata
            ts_a = point_a.payload.get("timestamp")
            ts_b = point_b.payload.get("timestamp")

            if not ts_a or not ts_b:
                return 0.0

            # Parse timestamps
            from datetime import datetime

            if isinstance(ts_a, str):
                ts_a = datetime.fromisoformat(ts_a)
            if isinstance(ts_b, str):
                ts_b = datetime.fromisoformat(ts_b)

            time_diff = abs((ts_a - ts_b).total_seconds())

            if time_diff <= self.config.temporal_window_seconds:
                # Within window, check content similarity
                return self._exact_match_similarity(point_a, point_b)

            return 0.0
        except Exception:
            return 0.0

    def _hybrid_similarity(self, point_a: Any, point_b: Any) -> float:
        """Calculate hybrid similarity combining multiple strategies."""
        # Check exact match first
        exact_sim = self._exact_match_similarity(point_a, point_b)
        if exact_sim >= self.config.similarity_threshold:
            return exact_sim

        # Check semantic similarity
        semantic_sim = self._cosine_similarity(point_a, point_b)
        if semantic_sim >= self.config.similarity_threshold:
            return semantic_sim

        # Check temporal similarity
        temporal_sim = self._temporal_similarity(point_a, point_b)

        # Return the maximum
        return max(exact_sim, semantic_sim, temporal_sim)

    def _calculate_max_similarity(self, reference: Any, similar_points: list) -> float:
        """Calculate maximum similarity score in a group."""
        max_sim = 0.0
        for point in similar_points:
            sim = self._calculate_similarity(reference, point, "")
            max_sim = max(max_sim, sim)
        return max_sim

    def _store_stats(self, stats: DeduplicationStats) -> None:
        """Store stats in Redis."""
        try:
            redis_client = self._get_redis_client()
            stats_key = f"{DEDUPLICATION_PREFIX}:stats:{stats.timestamp.isoformat()}"
            redis_client.hset(stats_key, mapping=stats.to_dict())
            redis_client.expire(stats_key, 86400 * 30)  # 30 days
        except Exception:
            pass  # Stats storage failure shouldn't stop processing

    def get_stats(self, limit: int = 10) -> list[DeduplicationStats]:
        """
        Get recent deduplication stats.

        Args:
            limit: Maximum number of stats to return

        Returns:
            List of DeduplicationStats
        """
        try:
            redis_client = self._get_redis_client()
            pattern = f"{DEDUPLICATION_PREFIX}:stats:*"

            keys = list(redis_client.scan_iter(match=pattern))
            keys.sort(reverse=True)  # Most recent first

            stats = []
            for key in keys[:limit]:
                data = redis_client.hgetall(key)
                if data:
                    stats.append(
                        DeduplicationStats(
                            timestamp=datetime.fromisoformat(data.get("timestamp", "")),
                            collections_scanned=int(data.get("collections_scanned", 0)),
                            entries_scanned=int(data.get("entries_scanned", 0)),
                            duplicate_groups=int(data.get("duplicate_groups", 0)),
                            entries_to_remove=int(data.get("entries_to_remove", 0)),
                            entries_removed=int(data.get("entries_removed", 0)),
                            cache_hits=int(data.get("cache_hits", 0)),
                            cache_misses=int(data.get("cache_misses", 0)),
                            similarity_checks=int(data.get("similarity_checks", 0)),
                            processing_time_seconds=float(
                                data.get("processing_time_seconds", 0)
                            ),
                            was_dry_run=data.get("was_dry_run", "true").lower()
                            == "true",
                            errors=data.get("errors", "[]"),
                        )
                    )

            return stats
        except Exception:
            return []
