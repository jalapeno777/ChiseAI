"""
Memory Sweep Engine for ChiseAI.

Orchestrates the memory stewardship process including:
- TTL management for ephemeral vs canonical memories
- Integration with promotion engine
- Deduplication using existing deduplication.py
- Contradiction detection

Feature Flag: chise:feature_flags:governance:memory_sweep_enabled
Default: Disabled (safe rollout)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import yaml

from governance.memory.contradiction import (
    ContradictionConfig,
    ContradictionDetector,
)
from governance.memory.deduplication import (
    DeduplicationConfig,
    MemoryDeduplicationEngine,
)
from governance.memory.promotion import (
    MemoryCategory,
    MemoryPromotionEngine,
    PromotionConfig,
)

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:governance:memory_sweep_enabled"

# Default policy path
DEFAULT_POLICY_PATH = "docs/policy/memory_policy.yaml"


@dataclass
class SweepConfig:
    """Configuration for the memory sweep process."""

    # Path to policy YAML file
    policy_path: str = DEFAULT_POLICY_PATH

    # Dry run mode
    dry_run: bool = True

    # Maximum memories to process per sweep
    max_memories_per_sweep: int = 1000

    # TTL management
    default_ephemeral_ttl_days: int = 7
    active_memory_extension_days: int = 14
    deletion_grace_period_hours: int = 24

    # Component configs
    dedup_config: DeduplicationConfig | None = None
    promotion_config: PromotionConfig | None = None
    contradiction_config: ContradictionConfig | None = None

    # Loaded policy data
    policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Load policy from YAML file."""
        try:
            with open(self.policy_path) as f:
                self.policy = yaml.safe_load(f)
            logger.info(f"Loaded sweep policy from {self.policy_path}")
        except Exception as e:
            logger.warning(f"Failed to load policy from {self.policy_path}: {e}")
            self.policy = self._default_policy()

        # Initialize component configs
        if self.dedup_config is None:
            self.dedup_config = DeduplicationConfig()
        if self.promotion_config is None:
            self.promotion_config = PromotionConfig()
        if self.contradiction_config is None:
            self.contradiction_config = ContradictionConfig()

    def _default_policy(self) -> dict[str, Any]:
        """Return default policy if file cannot be loaded."""
        return {
            "sweep": {
                "schedule": "0 2 * * *",
                "dry_run": True,
                "max_memories_per_sweep": 1000,
                "redis_patterns": [
                    "bmad:chiseai:iterlog:story:*",
                    "bmad:chiseai:iterlog:story:*:decisions",
                    "bmad:chiseai:iterlog:story:*:incidents",
                ],
            },
            "ttl_management": {
                "default_ephemeral_ttl_days": 7,
                "active_memory_extension_days": 14,
                "deletion_grace_period_hours": 24,
            },
        }

    def get_ttl_for_category(self, category: MemoryCategory) -> int | None:
        """
        Get TTL in seconds for a memory category.

        Returns:
            TTL in seconds, or None for permanent storage.
        """
        categories = self.policy.get("memory_categories", {})
        cat_config = categories.get(category.value, {})

        ttl = cat_config.get("ttl")
        if ttl == "permanent":
            return None

        ttl_days = cat_config.get("ttl_days")
        if ttl_days:
            return ttl_days * 24 * 3600

        # Default TTL for ephemeral memories
        return self.default_ephemeral_ttl_days * 24 * 3600


@dataclass
class SweepStats:
    """Statistics from a sweep run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Processing stats
    entries_scanned: int = 0
    entries_promoted: int = 0
    entries_deduplicated: int = 0
    entries_expired: int = 0
    entries_extended: int = 0
    contradictions_found: int = 0

    # Component stats
    dedup_stats: dict[str, Any] = field(default_factory=dict)
    promotion_stats: dict[str, Any] = field(default_factory=dict)
    contradiction_stats: dict[str, Any] = field(default_factory=dict)

    # Timing
    processing_time_seconds: float = 0.0
    was_dry_run: bool = True
    error: str | None = None


class MemorySweepEngine:
    """
    Engine for orchestrating memory stewardship.

    Coordinates multiple components:
    - Deduplication (from deduplication.py)
    - Promotion (to Qdrant)
    - Contradiction detection
    - TTL management

    Safety Features:
    - Disabled by default via feature flag
    - Dry run mode for testing
    - Grace period before deletion
    - Comprehensive audit logging
    """

    def __init__(
        self,
        config: SweepConfig | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        """
        Initialize the sweep engine.

        Args:
            config: Optional configuration override.
            redis_client: Optional Redis client.
            qdrant_client: Optional Qdrant client.
        """
        self._config = config or SweepConfig()
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._enabled: bool | None = None
        self._last_stats: SweepStats | None = None

        # Initialize component engines
        self._dedup_engine = MemoryDeduplicationEngine(
            config=self._config.dedup_config,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
        )
        self._promotion_engine = MemoryPromotionEngine(
            config=self._config.promotion_config,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
        )
        self._contradiction_detector = ContradictionDetector(
            config=self._config.contradiction_config,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
        )

        logger.info(
            "MemorySweepEngine initialized",
            extra={
                "dry_run": self._config.dry_run,
                "max_memories": self._config.max_memories_per_sweep,
            },
        )

    def is_enabled(self) -> bool:
        """Check if sweep engine is enabled via feature flag."""
        if self._enabled is not None:
            return self._enabled

        if self._redis_client is not None:
            try:
                flag_value = self._redis_client.get(FEATURE_FLAG_KEY)
                if flag_value is not None:
                    self._enabled = flag_value.lower() in ("true", "1", "yes")
                else:
                    self._enabled = False
                logger.debug(f"Feature flag check: enabled={self._enabled}")
            except Exception as e:
                logger.warning(f"Failed to read feature flag: {e}")
                return False
        else:
            self._enabled = False
            logger.debug("No Redis client, defaulting to disabled")

        return self._enabled

    def manage_ttl(
        self, key: str, category: MemoryCategory, dry_run: bool = True
    ) -> str:
        """
        Manage TTL for a memory entry.

        Args:
            key: Redis key for the memory.
            category: Memory category.
            dry_run: If True, don't actually modify TTL.

        Returns:
            Action taken: "extended", "expired", "permanent", "skipped"
        """
        if self._redis_client is None:
            return "skipped"

        try:
            # Get current TTL
            current_ttl = self._redis_client.ttl(key)

            # Get target TTL for category
            target_ttl = self._config.get_ttl_for_category(category)

            # Permanent memories (no TTL)
            if target_ttl is None:
                if current_ttl > 0 and not dry_run:
                    # Remove TTL to make permanent
                    self._redis_client.persist(key)
                return "permanent"

            # Check if memory is active (has recent activity)
            is_active = self._is_memory_active(key)

            if is_active and current_ttl > 0:
                # Extend TTL for active memories
                extension = self._config.active_memory_extension_days * 24 * 3600
                new_ttl = max(current_ttl, target_ttl) + extension

                if not dry_run:
                    self._redis_client.expire(key, new_ttl)
                return "extended"

            # Set TTL for new or updated memories
            if current_ttl < 0:  # No TTL set
                if not dry_run:
                    self._redis_client.expire(key, target_ttl)
                return "expired"  # Will expire after TTL

            return "skipped"

        except Exception as e:
            logger.warning(f"Failed to manage TTL for {key}: {e}")
            return "skipped"

    def _is_memory_active(self, key: str) -> bool:
        """
        Check if a memory has recent activity.

        Args:
            key: Redis key.

        Returns:
            True if memory shows recent activity.
        """
        # For now, check if it's been accessed recently
        # This could be enhanced with access tracking
        return False  # Conservative default

    def run_sweep(self, dry_run: bool | None = None) -> SweepStats:
        """
        Run the complete memory sweep process.

        Args:
            dry_run: Override config dry_run setting.

        Returns:
            SweepStats containing results.
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run
        stats = SweepStats(was_dry_run=is_dry_run)

        # Safety check
        if not self.is_enabled() and not is_dry_run:
            stats.error = "Engine is disabled. Enable feature flag or use dry_run=True"
            logger.error(stats.error)
            return stats

        try:
            logger.info("Memory sweep started", extra={"dry_run": is_dry_run})

            # Step 1: Run deduplication
            logger.info("Step 1: Running deduplication")
            dedup_stats = self._dedup_engine.deduplicate(dry_run=is_dry_run)
            stats.dedup_stats = {
                "entries_scanned": dedup_stats.entries_scanned,
                "duplicate_groups": dedup_stats.duplicate_groups,
                "entries_to_remove": dedup_stats.entries_to_remove,
                "entries_removed": dedup_stats.entries_removed,
                "bytes_saved": dedup_stats.bytes_saved,
            }
            stats.entries_deduplicated = dedup_stats.entries_removed

            # Step 2: Run promotion
            logger.info("Step 2: Running promotion")
            promotion_stats = self._promotion_engine.run_promotion(dry_run=is_dry_run)
            stats.promotion_stats = {
                "entries_scanned": promotion_stats.entries_scanned,
                "entries_promoted": promotion_stats.entries_promoted,
                "entries_skipped": promotion_stats.entries_skipped,
                "by_category": promotion_stats.by_category,
                "promotion_reasons": promotion_stats.promotion_reasons,
            }
            stats.entries_promoted = promotion_stats.entries_promoted

            # Step 3: Detect contradictions
            logger.info("Step 3: Running contradiction detection")
            self._contradiction_detector.scan_for_contradictions()
            contradiction_stats = self._contradiction_detector.get_stats()
            if contradiction_stats:
                stats.contradiction_stats = {
                    "memories_checked": contradiction_stats.memories_checked,
                    "comparisons_made": contradiction_stats.comparisons_made,
                    "contradictions_found": contradiction_stats.contradictions_found,
                    "high_severity": contradiction_stats.high_severity,
                    "medium_severity": contradiction_stats.medium_severity,
                    "low_severity": contradiction_stats.low_severity,
                }
                stats.contradictions_found = contradiction_stats.contradictions_found

            # Step 4: TTL management for remaining Redis entries
            logger.info("Step 4: Managing TTLs")
            ttl_stats = self._manage_ttls(dry_run=is_dry_run)
            stats.entries_expired = ttl_stats.get("expired", 0)
            stats.entries_extended = ttl_stats.get("extended", 0)

            # Calculate total scanned
            stats.entries_scanned = (
                dedup_stats.entries_scanned + promotion_stats.entries_scanned
            )

            logger.info(
                "Memory sweep completed",
                extra={
                    "entries_scanned": stats.entries_scanned,
                    "entries_promoted": stats.entries_promoted,
                    "entries_deduplicated": stats.entries_deduplicated,
                    "contradictions_found": stats.contradictions_found,
                    "dry_run": is_dry_run,
                },
            )

            # Log audit trail
            self._log_sweep_audit(stats)

        except Exception as e:
            stats.error = str(e)
            logger.exception("Memory sweep failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return stats

    def _manage_ttls(self, dry_run: bool = True) -> dict[str, int]:
        """
        Manage TTLs for Redis memory entries.

        Args:
            dry_run: If True, don't actually modify TTLs.

        Returns:
            Dictionary of action counts.
        """
        stats = {"extended": 0, "expired": 0, "permanent": 0, "skipped": 0}

        if self._redis_client is None:
            return stats

        patterns = self._config.policy.get("sweep", {}).get(
            "redis_patterns", ["bmad:chiseai:iterlog:story:*"]
        )

        for pattern in patterns:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis_client.scan(
                        cursor=cursor,
                        match=pattern,
                        count=100,
                    )

                    for key in keys:
                        # Determine category from key
                        category = self._infer_category_from_key(key)

                        action = self.manage_ttl(key, category, dry_run)
                        stats[action] = stats.get(action, 0) + 1

                    if cursor == 0:
                        break

            except Exception as e:
                logger.error(f"TTL management failed for pattern {pattern}: {e}")

        return stats

    def _infer_category_from_key(self, key: str) -> MemoryCategory:
        """
        Infer memory category from Redis key.

        Args:
            key: Redis key.

        Returns:
            Inferred MemoryCategory.
        """
        if "incident" in key:
            return MemoryCategory.POSTMORTEM
        elif "decision" in key:
            return MemoryCategory.DECISION
        elif "pattern" in key:
            return MemoryCategory.PATTERN
        elif "metric" in key:
            return MemoryCategory.METRIC
        elif "invariant" in key:
            return MemoryCategory.INVARIANT
        else:
            return MemoryCategory.DECISION  # Default

    def _log_sweep_audit(self, stats: SweepStats) -> None:
        """
        Log audit trail for sweep operation.

        Args:
            stats: Sweep statistics.
        """
        audit_entry = {
            "timestamp": stats.timestamp.isoformat(),
            "entries_scanned": stats.entries_scanned,
            "entries_promoted": stats.entries_promoted,
            "entries_deduplicated": stats.entries_deduplicated,
            "entries_expired": stats.entries_expired,
            "entries_extended": stats.entries_extended,
            "contradictions_found": stats.contradictions_found,
            "processing_time_seconds": stats.processing_time_seconds,
            "was_dry_run": stats.was_dry_run,
            "error": stats.error,
        }

        logger.info("Sweep audit trail", extra=audit_entry)

        # Store in Redis if available
        if self._redis_client:
            try:
                audit_key = f"chise:governance:sweep:audit:{stats.timestamp.strftime('%Y%m%d%H%M%S')}"
                self._redis_client.hset(
                    audit_key,
                    mapping={"data": json.dumps(audit_entry)},
                )
                # Set TTL to 30 days
                self._redis_client.expire(audit_key, 30 * 24 * 3600)
            except Exception as e:
                logger.warning(f"Failed to store sweep audit in Redis: {e}")

    def get_stats(self) -> SweepStats | None:
        """Get statistics from the last sweep run."""
        return self._last_stats

    def enable(self) -> bool:
        """Enable the sweep engine."""
        if self._redis_client is None:
            logger.warning("Cannot enable: no Redis client available")
            return False

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "true")
            self._enabled = True
            logger.info("Sweep engine enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable sweep engine: {e}")
            return False

    def disable(self) -> bool:
        """Disable the sweep engine."""
        if self._redis_client is None:
            self._enabled = False
            logger.info("Sweep engine disabled (local state only)")
            return True

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "false")
            self._enabled = False
            logger.info("Sweep engine disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable sweep engine: {e}")
            self._enabled = False
            return True
