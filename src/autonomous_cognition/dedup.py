"""
Autonomous Cognition Deduplication Module for ChiseAI.

Provides deduplication functionality specifically tailored for autonomous
cognition memory operations. Wraps the governance dedup engine with
autonomous_cognition-specific configuration and integration.

This module handles:
- Vector-based similarity detection for memory entries
- Content hashing for exact duplicate detection
- Integration with autonomous cognition memory stores (Redis/Qdrant)
- Daily sweep job support for memory hygiene

Feature Flag: chise:feature_flags:autonomous_cognition:dedup_enabled
Default: Disabled (safe rollout)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from governance.memory.deduplication import (
    DeduplicationConfig as GovernanceDeduplicationConfig,
)
from governance.memory.deduplication import (
    MemoryDeduplicationEngine as GovernanceMemoryDeduplicationEngine,
)

logger = logging.getLogger(__name__)

# Feature flag key in Redis for autonomous cognition dedup
FEATURE_FLAG_KEY = "chise:feature_flags:autonomous_cognition:dedup_enabled"

# Default similarity threshold for autocog dedup
DEFAULT_SIMILARITY_THRESHOLD = 0.92


@dataclass
class DeduplicationConfig:
    """Configuration for autonomous cognition deduplication.

    Attributes:
        similarity_threshold: Vector similarity threshold (0.0 to 1.0).
            Higher values = stricter matching. Default 0.92.
        max_age_days: Maximum age in days for entries to consider.
        batch_size: Number of entries to process per batch.
        dry_run: If True, don't actually delete duplicates.
        min_duplicates: Minimum duplicates needed to trigger action.
        qdrant_collection: Qdrant collection name for vector storage.
    """

    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    max_age_days: int = 30
    batch_size: int = 100
    dry_run: bool = True
    min_duplicates: int = 2
    qdrant_collection: str = "ChiseAI"


@dataclass
class DeduplicationStats:
    """Statistics from a deduplication run.

    Attributes:
        timestamp: When the run occurred.
        entries_scanned: Number of entries examined.
        duplicate_groups: Number of duplicate groups found.
        entries_to_remove: Entries marked for removal.
        entries_removed: Entries actually removed (0 if dry run).
        bytes_saved: Estimated storage saved.
        processing_time_seconds: How long the run took.
        was_dry_run: Whether this was a dry run.
        error: Error message if run failed.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    entries_scanned: int = 0
    duplicate_groups: int = 0
    entries_to_remove: int = 0
    entries_removed: int = 0
    bytes_saved: int = 0
    processing_time_seconds: float = 0.0
    was_dry_run: bool = True
    error: str | None = None


class DeduplicationEngine:
    """
    Deduplication engine for autonomous cognition memory hygiene.

    This engine wraps the governance MemoryDeduplicationEngine with
    autocog-specific defaults and integration points.

    It provides:
    - Vector similarity detection for semantic duplicates
    - Content hashing for exact duplicates
    - Redis and Qdrant integration
    - Configurable similarity thresholds
    - Dry-run mode for safe testing

    Example:
        >>> engine = DeduplicationEngine()
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
            config: Optional configuration override.
            redis_client: Optional Redis client for storage and feature flags.
            qdrant_client: Optional Qdrant client for vector similarity.
        """
        self._config = config or DeduplicationConfig()
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._enabled: bool | None = None

        # Convert to governance config
        self._governance_config = GovernanceDeduplicationConfig(
            similarity_threshold=self._config.similarity_threshold,
            max_age_days=self._config.max_age_days,
            batch_size=self._config.batch_size,
            dry_run=self._config.dry_run,
            min_duplicates=self._config.min_duplicates,
            qdrant_collection=self._config.qdrant_collection,
        )

        # Wrap governance engine
        self._governance_engine = GovernanceMemoryDeduplicationEngine(
            config=self._governance_config,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
        )

        logger.info(
            "AutonomousCognition DeduplicationEngine initialized",
            extra={
                "dry_run": self._config.dry_run,
                "similarity_threshold": self._config.similarity_threshold,
            },
        )

    def _is_feature_enabled(self) -> bool:
        """Check if dedup is enabled via Redis feature flag."""
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

    def is_enabled(self) -> bool:
        """
        Check if deduplication is enabled.

        Returns:
            True if enabled, False otherwise.
        """
        if self._enabled is not None:
            return self._enabled

        if self._redis_client is not None:
            self._enabled = self._is_feature_enabled()
        else:
            self._enabled = False

        return self._enabled

    def enable(self) -> bool:
        """
        Enable deduplication (requires Redis).

        Returns:
            True if successfully enabled.
        """
        if self._redis_client is None:
            logger.warning("Cannot enable: no Redis client")
            return False

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "true")
            self._enabled = True
            logger.info("Deduplication enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable deduplication: {e}")
            return False

    def disable(self) -> bool:
        """
        Disable deduplication.

        Returns:
            True if successfully disabled.
        """
        if self._redis_client is None:
            self._enabled = False
            return True

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "false")
            self._enabled = False
            logger.info("Deduplication disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable deduplication: {e}")
            self._enabled = False
            return True

    def deduplicate(
        self,
        scope: str | None = None,
        dry_run: bool | None = None,
    ) -> DeduplicationStats:
        """
        Run deduplication across memory stores.

        Args:
            scope: Optional scope filter ('redis', 'qdrant', or None for both).
            dry_run: Override dry_run setting.

        Returns:
            DeduplicationStats with results.
        """
        # Delegate to governance engine
        gov_stats = self._governance_engine.deduplicate(
            scope=scope,
            dry_run=dry_run if dry_run is not None else self._config.dry_run,
        )

        # Convert to autocog stats
        return DeduplicationStats(
            timestamp=gov_stats.timestamp,
            entries_scanned=gov_stats.entries_scanned,
            duplicate_groups=gov_stats.duplicate_groups,
            entries_to_remove=gov_stats.entries_to_remove,
            entries_removed=gov_stats.entries_removed,
            bytes_saved=gov_stats.bytes_saved,
            processing_time_seconds=gov_stats.processing_time_seconds,
            was_dry_run=gov_stats.was_dry_run,
            error=gov_stats.error,
        )

    def get_stats(self) -> DeduplicationStats | None:
        """
        Get stats from last deduplication run.

        Returns:
            DeduplicationStats or None if no run has occurred.
        """
        gov_stats = self._governance_engine.get_stats()
        if gov_stats is None:
            return None
        return DeduplicationStats(
            timestamp=gov_stats.timestamp,
            entries_scanned=gov_stats.entries_scanned,
            duplicate_groups=gov_stats.duplicate_groups,
            entries_to_remove=gov_stats.entries_to_remove,
            entries_removed=gov_stats.entries_removed,
            bytes_saved=gov_stats.bytes_saved,
            processing_time_seconds=gov_stats.processing_time_seconds,
            was_dry_run=gov_stats.was_dry_run,
            error=gov_stats.error,
        )

    def get_config(self) -> DeduplicationConfig:
        """Get current configuration."""
        return self._config

    def daily_sweep(self, dry_run: bool | None = None) -> DeduplicationStats:
        """
        Run daily sweep of memory stores for deduplication.

        This is a convenience method that runs deduplication with settings
        appropriate for daily maintenance. It wraps the governance engine's
        deduplicate method with proper error handling.

        Args:
            dry_run: Override config dry_run setting.

        Returns:
            DeduplicationStats with results of the sweep.
        """
        try:
            logger.info("Starting daily dedup sweep")
            stats = self.deduplicate(
                scope=None,
                dry_run=dry_run if dry_run is not None else self._config.dry_run,
            )
            logger.info(
                "Daily dedup sweep completed",
                extra={
                    "entries_scanned": stats.entries_scanned,
                    "duplicate_groups": stats.duplicate_groups,
                    "entries_removed": stats.entries_removed,
                    "was_dry_run": stats.was_dry_run,
                },
            )
            return stats
        except Exception as e:
            logger.exception("Daily dedup sweep failed: %s", e)
            return DeduplicationStats(
                was_dry_run=True,
                error=f"Daily sweep failed: {e}",
            )
