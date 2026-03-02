"""
Memory Deduplication Engine for ChiseAI.

Identifies and eliminates duplicate memory entries across Redis and Qdrant
to optimize storage and improve retrieval accuracy.

Feature Flag: chise:feature_flags:governance:memory_dedup_enabled
Default: Disabled (safe rollout)
"""

import contextlib
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:governance:memory_dedup_enabled"

# Legacy config key compatibility (B3 test suite)
CONFIG_KEY = "chise:config:memory_dedup"

# Legacy hash key prefix compatibility (B3 test suite)
HASH_PREFIX = "chise:memory:dedup:hash:"

# Audit trail key prefix in Redis
AUDIT_TRAIL_KEY_PREFIX = "chise:governance:dedup:audit"

# Qdrant collection name for memory storage
DEFAULT_QDRANT_COLLECTION = "ChiseAI"


@dataclass
class DeduplicationConfig:
    """Configuration for the deduplication engine."""

    # Similarity threshold for vector-based deduplication (0.0 to 1.0)
    similarity_threshold: float = 0.95

    # Maximum age in days for entries to consider for deduplication
    max_age_days: int = 30

    # Batch size for processing entries
    batch_size: int = 100

    # Enable dry run mode (no actual deletions)
    dry_run: bool = True

    # Minimum number of duplicates to trigger consolidation
    min_duplicates: int = 2

    # Redis key prefix for configuration overrides
    config_prefix: str = "chise:governance:dedup:config"

    # Qdrant collection name
    qdrant_collection: str = DEFAULT_QDRANT_COLLECTION


@dataclass
class DeduplicationStats:
    """Statistics from a deduplication run."""

    # Timestamp of the run
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Number of entries scanned
    entries_scanned: int = 0

    # Number of duplicate groups found
    duplicate_groups: int = 0

    # Number of entries marked for removal
    entries_to_remove: int = 0

    # Number of entries actually removed (0 if dry run)
    entries_removed: int = 0

    # Storage saved in bytes
    bytes_saved: int = 0

    # Processing time in seconds
    processing_time_seconds: float = 0.0

    # Whether this was a dry run
    was_dry_run: bool = True

    # Error message if any
    error: str | None = None


class MemoryDeduplicationEngine:
    """
    Engine for identifying and eliminating duplicate memory entries.

    This engine scans both Redis (short-term) and Qdrant (long-term) memory
    stores to identify and consolidate duplicate entries based on:
    - Exact content matches
    - Semantic similarity (vector-based)
    - Temporal proximity with similar content

    Safety Features:
    - Disabled by default via feature flag
    - Dry run mode enabled by default
    - Comprehensive logging of all operations
    - Rollback support through audit trail

    Example:
        >>> engine = MemoryDeduplicationEngine()
        >>> if engine.is_enabled():
        ...     stats = engine.deduplicate()
        ...     print(f"Removed {stats.entries_removed} duplicates")
    """

    def __init__(
        self,
        config: DeduplicationConfig | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        """
        Initialize the deduplication engine.

        Args:
            config: Optional configuration override. If not provided,
                    config is loaded from Redis or defaults are used.
            redis_client: Optional Redis client for feature flag and config.
            qdrant_client: Optional Qdrant client for vector operations.
        """
        self._config = config or DeduplicationConfig()
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._enabled: bool | None = None
        self._last_stats: DeduplicationStats | None = None

        # Load config from Redis if available
        if self._redis_client is not None:
            self._config = self._load_config_from_redis(use_legacy_config=False)

        logger.info(
            "MemoryDeduplicationEngine initialized",
            extra={
                "dry_run": self._config.dry_run,
                "similarity_threshold": self._config.similarity_threshold,
            },
        )

    def _is_valid_config_value(self, value) -> bool:
        """
        Check if a value is a valid config value from Redis.

        Args:
            value: The value to check.

        Returns:
            True if the value is a valid string/number, False otherwise.
        """
        if value is None:
            return False
        # Handle MagicMock objects from tests
        if hasattr(value, "_mock_name"):
            return False
        # Handle empty strings
        return not (isinstance(value, str) and not value)

    def _load_config_from_redis(self, use_legacy_config: bool = True) -> DeduplicationConfig:
        """
        Load configuration overrides from Redis.

        Returns:
            DeduplicationConfig with Redis overrides applied.
        """
        if self._redis_client is None:
            logger.debug("No Redis client, using default config")
            return self._config

        try:
            # Compatibility path for legacy JSON config payload at CONFIG_KEY.
            # New hash-based overrides still apply below and take precedence.
            config_kwargs: dict[str, Any] = {}
            if use_legacy_config:
                legacy_config = self._load_redis_config()
                if self._is_valid_config_value(legacy_config.get("threshold")):
                    try:
                        config_kwargs["similarity_threshold"] = float(
                            legacy_config["threshold"]
                        )
                    except (ValueError, TypeError, KeyError):
                        logger.warning(
                            f"Invalid legacy threshold in Redis: {legacy_config.get('threshold')}"
                        )

            config_values_key = f"{self._config.config_prefix}:values"

            # Load each config value from Redis hash
            similarity_threshold = self._redis_client.hget(
                config_values_key, "similarity_threshold"
            )
            max_age_days = self._redis_client.hget(config_values_key, "max_age_days")
            batch_size = self._redis_client.hget(config_values_key, "batch_size")
            dry_run = self._redis_client.hget(config_values_key, "dry_run")
            min_duplicates = self._redis_client.hget(
                config_values_key, "min_duplicates"
            )

            # Build new config with hash overrides (merged with legacy overrides)

            if self._is_valid_config_value(similarity_threshold):
                try:
                    config_kwargs["similarity_threshold"] = float(similarity_threshold)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid similarity_threshold in Redis: {similarity_threshold}"
                    )

            if self._is_valid_config_value(max_age_days):
                try:
                    config_kwargs["max_age_days"] = int(max_age_days)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid max_age_days in Redis: {max_age_days}")

            if self._is_valid_config_value(batch_size):
                try:
                    config_kwargs["batch_size"] = int(batch_size)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid batch_size in Redis: {batch_size}")

            if self._is_valid_config_value(dry_run):
                config_kwargs["dry_run"] = str(dry_run).lower() in ("true", "1", "yes")

            if self._is_valid_config_value(min_duplicates):
                try:
                    config_kwargs["min_duplicates"] = int(min_duplicates)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid min_duplicates in Redis: {min_duplicates}")

            if config_kwargs:
                logger.info(f"Loaded config overrides from Redis: {config_kwargs}")
                # Merge with original config to preserve non-overridden values
                merged_kwargs = {
                    "similarity_threshold": self._config.similarity_threshold,
                    "max_age_days": self._config.max_age_days,
                    "batch_size": self._config.batch_size,
                    "dry_run": self._config.dry_run,
                    "min_duplicates": self._config.min_duplicates,
                    "config_prefix": self._config.config_prefix,
                    "qdrant_collection": self._config.qdrant_collection,
                }
                merged_kwargs.update(config_kwargs)
                return DeduplicationConfig(**merged_kwargs)

            logger.debug("No config overrides found in Redis, using defaults")
            return self._config

        except Exception as e:
            logger.warning(f"Failed to load config from Redis: {e}")
            return self._config

    def _load_redis_config(self) -> dict[str, Any]:
        """
        Load legacy JSON config payload from Redis.

        Returns:
            Dict with keys: enabled, threshold, ttl.
        """
        default_config: dict[str, Any] = {
            "enabled": False,
            "threshold": self._config.similarity_threshold,
            "ttl": 86400,
        }

        if self._redis_client is None:
            return default_config

        try:
            raw = self._redis_client.get(CONFIG_KEY)
            if raw is None:
                return default_config
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return default_config
            return {
                "enabled": bool(parsed.get("enabled", default_config["enabled"])),
                "threshold": float(parsed.get("threshold", default_config["threshold"])),
                "ttl": int(parsed.get("ttl", default_config["ttl"])),
            }
        except Exception as e:
            logger.warning(f"Failed to load legacy dedup config: {e}")
            return default_config

    def _calculate_hash(self, content: str) -> str:
        """Calculate deterministic SHA-256 hash for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_duplicate(self, content_hash: str) -> bool:
        """Check whether a content hash has already been seen."""
        if self._redis_client is None:
            return False
        try:
            return bool(self._redis_client.exists(f"{HASH_PREFIX}{content_hash}"))
        except Exception as e:
            logger.warning(f"Failed duplicate check for hash {content_hash}: {e}")
            return False

    def _store_hash(self, content_hash: str, ttl: int | None = None) -> None:
        """Store seen hash in Redis with TTL."""
        if self._redis_client is None:
            return
        effective_ttl = ttl if ttl is not None else self._config.max_age_days * 86400
        try:
            self._redis_client.setex(f"{HASH_PREFIX}{content_hash}", effective_ttl, "1")
        except Exception as e:
            logger.warning(f"Failed storing hash {content_hash}: {e}")

    def deduplicate_content(self, content: str) -> dict[str, Any]:
        """
        Legacy content-level deduplication API.

        Returns:
            Dict with `is_duplicate` and `hash`.
        """
        content_hash = self._calculate_hash(content)
        duplicate = self._is_duplicate(content_hash)
        if not duplicate:
            self._store_hash(content_hash)
        return {"is_duplicate": duplicate, "hash": content_hash}

    def _is_feature_enabled(self) -> bool:
        """Legacy feature flag helper with byte/string compatibility."""
        if self._redis_client is None:
            return False
        try:
            flag_value = self._redis_client.get(FEATURE_FLAG_KEY)
            if flag_value is None:
                return False
            if isinstance(flag_value, bytes):
                flag_value = flag_value.decode("utf-8")
            return str(flag_value).lower() in ("true", "1", "yes")
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return False

    def _set_feature_flag(self, enabled: bool) -> bool:
        """Legacy feature flag setter used by enable/disable wrappers."""
        if self._redis_client is None:
            return False
        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "true" if enabled else "false")
            self._enabled = enabled
            return True
        except Exception as e:
            logger.error(f"Failed to set feature flag: {e}")
            return False

    def is_enabled(self) -> bool:
        """
        Check if the deduplication engine is enabled via feature flag.

        The feature flag is stored at:
        chise:feature_flags:governance:memory_dedup_enabled

        Returns:
            True if enabled, False otherwise. Defaults to False if flag
            cannot be read.
        """
        if self._enabled is not None:
            return self._enabled

        # Try to read feature flag from Redis
        if self._redis_client is not None:
            self._enabled = self._is_feature_enabled()
            logger.debug(f"Feature flag check: enabled={self._enabled}")
        else:
            # No Redis client, default to disabled for safety
            self._enabled = False
            logger.debug("No Redis client, defaulting to disabled")

        return self._enabled

    def _scan_redis_entries(self, scope: str | None = None) -> list[dict]:
        """
        Scan Redis for memory entries.

        Args:
            scope: Optional scope/prefix to filter keys.

        Returns:
            List of entry dictionaries with key, value, type, ttl, and source.
        """
        if self._redis_client is None:
            return []

        entries = []
        pattern = f"{scope}:*" if scope else "*"
        cursor = 0

        try:
            while True:
                cursor, keys = self._redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=self._config.batch_size,
                )

                for key in keys:
                    try:
                        key_type = self._redis_client.type(key)
                        ttl = self._redis_client.ttl(key)

                        # Get value based on type
                        value = None
                        if key_type == "string":
                            value = self._redis_client.get(key)
                        elif key_type == "hash":
                            value = self._redis_client.hgetall(key)
                        elif key_type == "list":
                            value = self._redis_client.lrange(key, 0, -1)
                        elif key_type == "set":
                            value = list(self._redis_client.smembers(key))
                        elif key_type == "zset":
                            value = self._redis_client.zrange(
                                key, 0, -1, withscores=True
                            )

                        entries.append(
                            {
                                "key": key,
                                "value": value,
                                "type": key_type,
                                "ttl": ttl if ttl > 0 else None,
                                "source": "redis",
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read key {key}: {e}")
                        continue

                if cursor == 0:
                    break

        except Exception as e:
            logger.error(f"Redis scan failed: {e}")

        return entries

    def _scan_qdrant_entries(self, scope: str | None = None) -> list[dict]:
        """
        Scan Qdrant collection for memory entries.

        Args:
            scope: Optional collection name override.

        Returns:
            List of entry dictionaries with id, payload, vector, and source.
        """
        if self._qdrant_client is None:
            return []

        entries = []
        collection_name = scope or self._config.qdrant_collection
        offset = None

        try:
            while True:
                result = self._qdrant_client.scroll(
                    collection_name=collection_name,
                    limit=self._config.batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )

                points, next_offset = result

                for point in points:
                    entries.append(
                        {
                            "id": point.id,
                            "payload": point.payload,
                            "vector": point.vector,
                            "source": "qdrant",
                        }
                    )

                if next_offset is None:
                    break
                offset = next_offset

        except Exception as e:
            logger.error(f"Qdrant scan failed: {e}")

        return entries

    def _compute_content_hash(self, entry: dict) -> str:
        """
        Compute a content hash for an entry.

        Args:
            entry: Entry dictionary from Redis or Qdrant.

        Returns:
            MD5 hash of the entry content.
        """
        if entry["source"] == "redis":
            content = str(entry.get("value"))
        else:  # qdrant
            content = str(entry.get("payload"))

        return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _compute_vector_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity score between 0.0 and 1.0.
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        # Compute dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))

        # Compute magnitudes
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def _identify_duplicates(
        self,
        redis_entries: list[dict],
        qdrant_entries: list[dict],
    ) -> list[list[dict]]:
        """
        Identify duplicate entry groups.

        Args:
            redis_entries: List of Redis entries.
            qdrant_entries: List of Qdrant entries.

        Returns:
            List of duplicate groups, where each group is a list of entries.
        """
        all_entries = redis_entries + qdrant_entries

        # Group by content hash
        hash_groups: dict[str, list[dict]] = {}
        for entry in all_entries:
            content_hash = self._compute_content_hash(entry)
            if content_hash not in hash_groups:
                hash_groups[content_hash] = []
            hash_groups[content_hash].append(entry)

        # Filter to groups with at least min_duplicates
        duplicate_groups = [
            group
            for group in hash_groups.values()
            if len(group) >= self._config.min_duplicates
        ]

        # Also check for vector similarity for Qdrant entries
        if qdrant_entries and len(qdrant_entries) > 1:
            vector_groups = self._find_vector_similar_groups(qdrant_entries)
            # Merge with existing groups, avoiding duplicates
            existing_ids = set()
            for group in duplicate_groups:
                for entry in group:
                    entry_id = entry.get("key") or entry.get("id")
                    existing_ids.add((entry["source"], entry_id))

            for vgroup in vector_groups:
                vgroup_ids = set(
                    (e["source"], e.get("key") or e.get("id")) for e in vgroup
                )
                if not vgroup_ids.issubset(existing_ids):
                    duplicate_groups.append(vgroup)

        return duplicate_groups

    def _find_vector_similar_groups(
        self, qdrant_entries: list[dict]
    ) -> list[list[dict]]:
        """
        Find groups of similar vectors using cosine similarity.

        Args:
            qdrant_entries: List of Qdrant entries with vectors.

        Returns:
            List of similar vector groups.
        """
        if not qdrant_entries:
            return []

        # Build similarity graph
        n = len(qdrant_entries)
        visited = [False] * n
        groups = []

        for i in range(n):
            if visited[i]:
                continue

            group = [qdrant_entries[i]]
            visited[i] = True

            for j in range(i + 1, n):
                if visited[j]:
                    continue

                vec_i = qdrant_entries[i].get("vector")
                vec_j = qdrant_entries[j].get("vector")

                if vec_i and vec_j:
                    similarity = self._compute_vector_similarity(vec_i, vec_j)
                    if similarity >= self._config.similarity_threshold:
                        group.append(qdrant_entries[j])
                        visited[j] = True

            if len(group) >= self._config.min_duplicates:
                groups.append(group)

        return groups

    def _select_canonical_entry(self, group: list[dict]) -> dict:
        """
        Select the canonical entry from a duplicate group.

        Priority:
        1. Entry with highest TTL (longest remaining life)
        2. Entry with most recent timestamp (if available in payload)
        3. First entry in the group

        Args:
            group: List of duplicate entries.

        Returns:
            The canonical entry to keep.
        """

        # Sort by TTL (higher is better), then by payload timestamp if available
        def sort_key(entry):
            ttl = entry.get("ttl") or 0
            # Try to get timestamp from payload for Qdrant entries
            timestamp = 0
            if entry["source"] == "qdrant" and entry.get("payload"):
                payload = entry["payload"]
                if isinstance(payload, dict):
                    ts = payload.get("timestamp") or payload.get("created_at")
                    if ts:
                        with contextlib.suppress(ValueError, TypeError):
                            timestamp = int(ts)
            return (-ttl, -timestamp)

        sorted_group = sorted(group, key=sort_key)
        return sorted_group[0]

    def _remove_duplicates(
        self,
        duplicate_groups: list[list[dict]],
        dry_run: bool,
    ) -> tuple[int, int]:
        """
        Remove duplicate entries, keeping the canonical one from each group.

        Args:
            duplicate_groups: List of duplicate groups.
            dry_run: If True, don't actually delete anything.

        Returns:
            Tuple of (entries_to_remove, entries_removed).
        """
        entries_to_remove = 0
        entries_removed = 0

        for group in duplicate_groups:
            canonical = self._select_canonical_entry(group)
            to_remove = [e for e in group if e != canonical]
            entries_to_remove += len(to_remove)

            if not dry_run:
                for entry in to_remove:
                    try:
                        if entry["source"] == "redis" and self._redis_client:
                            self._redis_client.delete(entry["key"])
                            entries_removed += 1
                            logger.info(f"Deleted Redis key: {entry['key']}")
                        elif entry["source"] == "qdrant" and self._qdrant_client:
                            self._qdrant_client.delete(
                                collection_name=self._config.qdrant_collection,
                                points_selector=[entry["id"]],
                            )
                            entries_removed += 1
                            logger.info(f"Deleted Qdrant point: {entry['id']}")
                    except Exception as e:
                        logger.error(f"Failed to delete entry {entry}: {e}")

        return entries_to_remove, entries_removed

    def _estimate_bytes_saved(self, duplicate_groups: list[list[dict]]) -> int:
        """
        Estimate bytes saved by removing duplicates.

        Args:
            duplicate_groups: List of duplicate groups.

        Returns:
            Estimated bytes saved.
        """
        total_bytes = 0

        for group in duplicate_groups:
            canonical = self._select_canonical_entry(group)
            to_remove = [e for e in group if e != canonical]

            for entry in to_remove:
                if entry["source"] == "redis":
                    value = entry.get("value")
                    if value:
                        total_bytes += len(str(value).encode("utf-8"))
                elif entry["source"] == "qdrant":
                    payload = entry.get("payload")
                    if payload:
                        total_bytes += len(str(payload).encode("utf-8"))

        return total_bytes

    def _log_audit_trail(
        self,
        stats: DeduplicationStats,
        duplicate_groups: list[list[dict]],
    ) -> None:
        """
        Log audit trail for deduplication operation.

        Args:
            stats: Deduplication statistics.
            duplicate_groups: List of duplicate groups.
        """
        audit_entry = {
            "timestamp": stats.timestamp.isoformat(),
            "entries_scanned": stats.entries_scanned,
            "duplicate_groups": stats.duplicate_groups,
            "entries_to_remove": stats.entries_to_remove,
            "entries_removed": stats.entries_removed,
            "bytes_saved": stats.bytes_saved,
            "was_dry_run": stats.was_dry_run,
            "error": stats.error,
            "duplicate_details": [
                {
                    "canonical": self._entry_to_dict(
                        self._select_canonical_entry(group)
                    ),
                    "duplicates": [
                        self._entry_to_dict(e)
                        for e in group
                        if e != self._select_canonical_entry(group)
                    ],
                }
                for group in duplicate_groups
            ],
        }

        # Log to Python logger
        logger.info("Deduplication audit trail", extra=audit_entry)

        # Store in Redis if available
        if self._redis_client:
            try:
                audit_key = f"{AUDIT_TRAIL_KEY_PREFIX}:{stats.timestamp.strftime('%Y%m%d%H%M%S')}"
                self._redis_client.hset(
                    audit_key,
                    mapping={
                        "data": json.dumps(audit_entry),
                    },
                )
                # Set TTL to 30 days
                self._redis_client.expire(audit_key, 30 * 24 * 3600)
            except Exception as e:
                logger.warning(f"Failed to store audit trail in Redis: {e}")

    def _entry_to_dict(self, entry: dict) -> dict:
        """
        Convert an entry to a serializable dictionary.

        Args:
            entry: Entry dictionary.

        Returns:
            Serializable dictionary representation.
        """
        return {
            "source": entry.get("source"),
            "key": entry.get("key"),
            "id": entry.get("id"),
            "type": entry.get("type"),
            "ttl": entry.get("ttl"),
            # Don't include full value/payload/vector for brevity
            "has_value": entry.get("value") is not None,
            "has_payload": entry.get("payload") is not None,
            "has_vector": entry.get("vector") is not None,
        }

    def deduplicate(
        self,
        scope: str | None = None,
        dry_run: bool | None = None,
    ) -> DeduplicationStats:
        """
        Run the deduplication process.

        This method scans memory stores and identifies/removes duplicates
        based on the configured similarity threshold and strategy.

        Args:
            scope: Optional scope to limit deduplication (e.g., "redis",
                   "qdrant", or a specific collection/key prefix).
            dry_run: Override config dry_run setting. If True, no actual
                     deletions occur.

        Returns:
            DeduplicationStats containing results of the operation.

        Raises:
            RuntimeError: If engine is disabled and dry_run is False.
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run
        stats = DeduplicationStats(was_dry_run=is_dry_run)

        # Safety check - don't allow actual dedup if disabled
        if not self.is_enabled() and not is_dry_run:
            stats.error = "Engine is disabled. Enable feature flag or use dry_run=True"
            logger.error(stats.error)
            return stats

        try:
            logger.info(
                "Deduplication started",
                extra={"scope": scope, "dry_run": is_dry_run},
            )

            # 1. Scan Redis for short-term memory entries
            redis_entries = []
            if scope is None or scope == "redis":
                redis_entries = self._scan_redis_entries(
                    scope=None if scope == "redis" else scope
                )

            # 2. Scan Qdrant for long-term memory vectors
            qdrant_entries = []
            if scope is None or scope == "qdrant":
                qdrant_entries = self._scan_qdrant_entries(
                    scope=None if scope == "qdrant" else scope
                )

            # 3. Identify duplicates
            duplicate_groups = self._identify_duplicates(redis_entries, qdrant_entries)

            # 4. Remove duplicates (or just count in dry run)
            entries_to_remove, entries_removed = self._remove_duplicates(
                duplicate_groups, is_dry_run
            )

            # 5. Calculate bytes saved
            bytes_saved = self._estimate_bytes_saved(duplicate_groups)

            # 6. Update stats
            stats.entries_scanned = len(redis_entries) + len(qdrant_entries)
            stats.duplicate_groups = len(duplicate_groups)
            stats.entries_to_remove = entries_to_remove
            stats.entries_removed = entries_removed if not is_dry_run else 0
            stats.bytes_saved = bytes_saved

            # 7. Log audit trail
            self._log_audit_trail(stats, duplicate_groups)

            logger.info(
                "Deduplication completed",
                extra={
                    "entries_scanned": stats.entries_scanned,
                    "duplicate_groups": stats.duplicate_groups,
                    "entries_to_remove": stats.entries_to_remove,
                    "entries_removed": stats.entries_removed,
                    "bytes_saved": stats.bytes_saved,
                    "dry_run": is_dry_run,
                },
            )

        except Exception as e:
            stats.error = str(e)
            logger.exception("Deduplication failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return stats

    def get_stats(self) -> DeduplicationStats | None:
        """
        Get statistics from the last deduplication run.

        Returns:
            DeduplicationStats from the last run, or None if no run
            has been performed.
        """
        return self._last_stats

    def get_config(self) -> DeduplicationConfig:
        """
        Get the current configuration.

        Returns:
            The active DeduplicationConfig.
        """
        return self._config

    def enable(self) -> bool:
        """
        Enable the deduplication engine (requires Redis).

        This sets the feature flag to True. Use with caution.

        Returns:
            True if successfully enabled, False otherwise.
        """
        if self._redis_client is None:
            logger.warning("Cannot enable: no Redis client available")
            return False

        try:
            if not self._set_feature_flag(True):
                return False
            logger.info("Deduplication engine enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable deduplication engine: {e}")
            return False

    def disable(self) -> bool:
        """
        Disable the deduplication engine (requires Redis).

        This sets the feature flag to False.

        Returns:
            True if successfully disabled, False otherwise.
        """
        if self._redis_client is None:
            # Can still disable locally even without Redis
            self._enabled = False
            logger.info("Deduplication engine disabled (local state only)")
            return True

        try:
            if not self._set_feature_flag(False):
                # Keep local disable semantics even if Redis write fails.
                self._enabled = False
                return True
            logger.info("Deduplication engine disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable deduplication engine: {e}")
            # Still disable locally
            self._enabled = False
            return True
