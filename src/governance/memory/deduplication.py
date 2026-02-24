"""
Memory Deduplication Engine for ChiseAI.

Identifies and eliminates duplicate memory entries across Redis and Qdrant
to optimize storage and improve retrieval accuracy.

Feature Flag: chise:feature_flags:governance:memory_dedup_enabled
Default: Disabled (safe rollout)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:governance:memory_dedup_enabled"

# Redis config key for memory deduplication
CONFIG_KEY = "chise:config:memory_dedup"

# Redis key prefix for storing content hashes
HASH_PREFIX = "chise:memory:dedup:hash:"


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

        logger.info(
            "MemoryDeduplicationEngine initialized",
            extra={
                "dry_run": self._config.dry_run,
                "similarity_threshold": self._config.similarity_threshold,
            },
        )

    def _load_redis_config(self) -> dict:
        """
        Load memory deduplication configuration from Redis.

        Loads from Redis key: "chise:config:memory_dedup"
        Config format: {"enabled": bool, "threshold": float, "ttl": int}

        Returns:
            Config dict with Redis values or defaults if key missing.
            Defaults: {"enabled": False, "threshold": 0.95, "ttl": 86400}
        """
        defaults = {"enabled": False, "threshold": 0.95, "ttl": 86400}

        if self._redis_client is None:
            logger.debug("No Redis client, returning default config")
            return defaults

        try:
            config_data = self._redis_client.get(CONFIG_KEY)
            if config_data is None:
                logger.debug(
                    f"Redis config key '{CONFIG_KEY}' not found, using defaults"
                )
                return defaults

            # Handle both string and bytes responses
            if isinstance(config_data, bytes):
                config_data = config_data.decode("utf-8")

            config = json.loads(config_data)

            # Merge with defaults to ensure all keys exist
            merged = {**defaults, **config}
            logger.debug(f"Loaded config from Redis: {merged}")
            return merged

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Redis config JSON: {e}, using defaults")
            return defaults
        except Exception as e:
            logger.warning(f"Failed to load config from Redis: {e}, using defaults")
            return defaults

    def _load_config_from_redis(self) -> DeduplicationConfig:
        """
        Load configuration overrides from Redis and apply to current config.

        Returns:
            DeduplicationConfig with Redis overrides applied.
        """
        redis_config = self._load_redis_config()

        # Apply Redis config to current config
        self._config.similarity_threshold = redis_config.get(
            "threshold", self._config.similarity_threshold
        )

        logger.debug("Config loaded from Redis and applied")
        return self._config

    def _calculate_hash(self, content: str) -> str:
        """
        Calculate SHA-256 hash of content for deduplication.

        Args:
            content: String content to hash.

        Returns:
            Hex digest of SHA-256 hash (64 characters).
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_duplicate(self, content_hash: str) -> bool:
        """
        Check if a content hash already exists in Redis.

        Args:
            content_hash: The hash to check.

        Returns:
            True if hash exists (is a duplicate), False otherwise.
        """
        if self._redis_client is None:
            return False

        try:
            key = f"{HASH_PREFIX}{content_hash}"
            exists = self._redis_client.exists(key)
            return bool(exists)
        except Exception as e:
            logger.warning(f"Failed to check duplicate hash: {e}")
            return False

    def _store_hash(self, content_hash: str, ttl: int | None = None) -> None:
        """
        Store content hash in Redis with TTL for deduplication tracking.

        Args:
            content_hash: The hash to store.
            ttl: Time-to-live in seconds. Defaults to config value or 86400.
        """
        if self._redis_client is None:
            return

        try:
            key = f"{HASH_PREFIX}{content_hash}"
            effective_ttl = ttl or self._config.max_age_days * 86400
            self._redis_client.setex(key, effective_ttl, "1")
            logger.debug(
                f"Stored hash with TTL {effective_ttl}: {content_hash[:16]}..."
            )
        except Exception as e:
            logger.warning(f"Failed to store hash: {e}")

    def deduplicate_content(self, content: str) -> dict:
        """
        Check if content is a duplicate and store hash if new.

        This is the main deduplication orchestration method that:
        1. Calculates content hash
        2. Checks if hash exists in Redis
        3. Stores hash if new

        Args:
            content: The content to deduplicate.

        Returns:
            Dict with keys:
                - "is_duplicate": bool indicating if content is duplicate
                - "hash": the calculated content hash
        """
        content_hash = self._calculate_hash(content)
        is_dup = self._is_duplicate(content_hash)

        if not is_dup:
            self._store_hash(content_hash)

        return {"is_duplicate": is_dup, "hash": content_hash}

    def _is_feature_enabled(self) -> bool:
        """
        Check if the deduplication feature flag is enabled in Redis.

        Reads from Redis key: "chise:feature_flags:governance:memory_dedup_enabled"

        Returns:
            True if enabled, False otherwise (including on error or missing flag).
        """
        if self._redis_client is None:
            return False

        try:
            flag_value = self._redis_client.get(FEATURE_FLAG_KEY)
            if flag_value is None:
                return False

            # Handle both string and bytes
            if isinstance(flag_value, bytes):
                flag_value = flag_value.decode("utf-8")

            return flag_value.lower() == "true"
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return False

    def _set_feature_flag(self, enabled: bool) -> bool:
        """
        Set the deduplication feature flag in Redis.

        Sets Redis key: "chise:feature_flags:governance:memory_dedup_enabled"

        Args:
            enabled: True to enable, False to disable.

        Returns:
            True if successfully set, False otherwise.
        """
        if self._redis_client is None:
            return False

        try:
            value = "true" if enabled else "false"
            self._redis_client.set(FEATURE_FLAG_KEY, value)
            # Update cached value
            self._enabled = enabled
            logger.info(f"Feature flag set to {enabled}")
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

        # Use _is_feature_enabled for actual Redis check
        self._enabled = self._is_feature_enabled()
        logger.debug(f"Feature flag check: enabled={self._enabled}")

        return self._enabled

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
        stats = DeduplicationStats(
            was_dry_run=dry_run if dry_run is not None else self._config.dry_run,
        )

        # Safety check - don't allow actual dedup if disabled
        if not self.is_enabled() and not stats.was_dry_run:
            stats.error = "Engine is disabled. Enable feature flag or use dry_run=True"
            logger.error(stats.error)
            return stats

        try:
            # TODO: Implement actual deduplication logic
            # 1. Scan Redis for short-term memory entries
            # 2. Scan Qdrant for long-term memory vectors
            # 3. Identify duplicates using content hash and vector similarity
            # 4. Group duplicates and select canonical entry
            # 5. Remove non-canonical entries (if not dry run)
            # 6. Update references if needed
            # 7. Log audit trail

            logger.info(
                "Deduplication started",
                extra={"scope": scope, "dry_run": stats.was_dry_run},
            )

            # Stub implementation - just return empty stats
            stats.entries_scanned = 0
            stats.duplicate_groups = 0
            stats.entries_to_remove = 0
            stats.entries_removed = 0 if stats.was_dry_run else 0

            logger.info(
                "Deduplication completed (stub)",
                extra={
                    "entries_scanned": stats.entries_scanned,
                    "dry_run": stats.was_dry_run,
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
        return self._set_feature_flag(True)

    def disable(self) -> bool:
        """
        Disable the deduplication engine (requires Redis).

        This sets the feature flag to False.

        Returns:
            True if successfully disabled, False otherwise.
        """
        return self._set_feature_flag(False)
