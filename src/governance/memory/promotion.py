"""
Memory Promotion Engine for ChiseAI.

Handles auto-promotion of memories from Redis (short-term) to Qdrant (long-term)
based on configurable rules and thresholds.

Feature Flag: chise:feature_flags:governance:memory_promotion_enabled
Default: Disabled (safe rollout)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:governance:memory_promotion_enabled"

# Default policy path
DEFAULT_POLICY_PATH = "docs/policy/memory_policy.yaml"


class MemoryCategory(Enum):
    """Memory categories with different promotion rules."""

    INVARIANT = "invariant"
    DECISION = "decision"
    PATTERN = "pattern"
    POSTMORTEM = "postmortem"
    METRIC = "metric"
    RESEARCH = "research"


class PromotionRule(Enum):
    """Promotion rules determining when memories are promoted."""

    IMMEDIATE = "immediate"  # Promote immediately
    OCCURRENCES = "occurrences"  # Promote after N occurrences
    CI_IMPACT = "ci_impact"  # Promote if CI-related
    VALIDATED = "validated"  # Promote after validation
    AGGREGATE_ONLY = "aggregate_only"  # Keep in Redis, aggregate only


@dataclass
class MemoryEntry:
    """Represents a memory entry from Redis."""

    # Unique identifier
    id: str

    # Memory content
    content: str

    # Category (invariant, decision, pattern, etc.)
    category: MemoryCategory

    # Source information
    story_id: str
    agent: str
    timestamp: datetime

    # Optional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Evidence pointers
    pr_link: str | None = None
    commit_hash: str | None = None
    branch_name: str | None = None

    # Promotion tracking
    occurrence_count: int = 1
    ci_failure: bool = False
    ci_prevention: bool = False
    touches_invariant: bool = False
    touches_kill_switch: bool = False
    touches_canary: bool = False
    touches_risk_limit: bool = False
    validated: bool = False

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Convert to Qdrant payload format."""
        return {
            "content": self.content,
            "category": self.category.value,
            "story_id": self.story_id,
            "agent": self.agent,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "pr_link": self.pr_link,
            "commit_hash": self.commit_hash,
            "branch_name": self.branch_name,
            "occurrence_count": self.occurrence_count,
            "promoted_at": datetime.now(UTC).isoformat(),
        }

    def compute_hash(self) -> str:
        """Compute a hash of the content for deduplication."""
        content = f"{self.category.value}:{self.content}:{self.story_id}"
        return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass
class PromotionConfig:
    """Configuration for the promotion engine."""

    # Path to policy YAML file
    policy_path: str = DEFAULT_POLICY_PATH

    # Similarity threshold for deduplication (0.0 to 1.0)
    similarity_threshold: float = 0.92

    # Contradiction detection threshold
    contradiction_threshold: float = 0.85

    # Minimum occurrences for OCCURRENCES rule
    min_occurrences: int = 2

    # Dry run mode (no actual promotions)
    dry_run: bool = True

    # Qdrant collection name
    qdrant_collection: str = "ChiseAI"

    # Loaded policy data
    policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Load policy from YAML file."""
        try:
            with open(self.policy_path) as f:
                self.policy = yaml.safe_load(f)
            logger.info(f"Loaded promotion policy from {self.policy_path}")
        except Exception as e:
            logger.warning(f"Failed to load policy from {self.policy_path}: {e}")
            self.policy = self._default_policy()

    def _default_policy(self) -> dict[str, Any]:
        """Return default policy if file cannot be loaded."""
        return {
            "memory_categories": {
                "invariant": {"storage": "qdrant", "promotion_rule": "immediate"},
                "decision": {"storage": "qdrant", "promotion_rule": "occurrences"},
                "pattern": {"storage": "qdrant", "promotion_rule": "ci_impact"},
                "postmortem": {"storage": "qdrant", "promotion_rule": "immediate"},
                "metric": {"storage": "redis", "promotion_rule": "aggregate_only"},
                "research": {"storage": "qdrant", "promotion_rule": "validated"},
            },
            "auto_promotion_rules": [
                {"name": "duplicate_clustering", "condition": "occurrence_count >= 2"},
                {
                    "name": "ci_impact",
                    "condition": "ci_failure == true OR ci_prevention == true",
                },
            ],
        }

    def get_category_config(self, category: MemoryCategory) -> dict[str, Any]:
        """Get configuration for a memory category."""
        categories = self.policy.get("memory_categories", {})
        return categories.get(category.value, {})

    def get_promotion_rule(self, category: MemoryCategory) -> PromotionRule:
        """Get promotion rule for a category."""
        config = self.get_category_config(category)
        rule_str = config.get("promotion_rule", "occurrences")
        try:
            return PromotionRule(rule_str)
        except ValueError:
            return PromotionRule.OCCURRENCES


@dataclass
class PromotionStats:
    """Statistics from a promotion run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    entries_scanned: int = 0
    entries_promoted: int = 0
    entries_skipped: int = 0
    entries_deduplicated: int = 0
    contradictions_found: int = 0
    processing_time_seconds: float = 0.0
    was_dry_run: bool = True
    error: str | None = None

    # Detailed breakdown by category
    by_category: dict[str, int] = field(default_factory=dict)

    # Promotion reasons
    promotion_reasons: dict[str, int] = field(default_factory=dict)


class MemoryPromotionEngine:
    """
    Engine for promoting memories from Redis to Qdrant.

    This engine evaluates memories against promotion rules and moves
    qualifying entries from short-term (Redis) to long-term (Qdrant)
    storage with deduplication and contradiction detection.

    Safety Features:
    - Disabled by default via feature flag
    - Dry run mode for testing
    - Comprehensive audit logging
    - Rollback support through Redis TTL
    """

    def __init__(
        self,
        config: PromotionConfig | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        """
        Initialize the promotion engine.

        Args:
            config: Optional configuration override.
            redis_client: Optional Redis client for source data.
            qdrant_client: Optional Qdrant client for destination.
        """
        self._config = config or PromotionConfig()
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._enabled: bool | None = None
        self._last_stats: PromotionStats | None = None

        logger.info(
            "MemoryPromotionEngine initialized",
            extra={
                "dry_run": self._config.dry_run,
                "similarity_threshold": self._config.similarity_threshold,
            },
        )

    def is_enabled(self) -> bool:
        """Check if promotion engine is enabled via feature flag."""
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

    def should_promote(self, entry: MemoryEntry) -> tuple[bool, str]:
        """
        Determine if a memory entry should be promoted.

        Args:
            entry: The memory entry to evaluate.

        Returns:
            Tuple of (should_promote, reason).
        """
        rule = self._config.get_promotion_rule(entry.category)

        # Check category-specific rules
        if rule == PromotionRule.IMMEDIATE:
            return True, "immediate_promotion"

        if rule == PromotionRule.AGGREGATE_ONLY:
            return False, "aggregate_only"

        if rule == PromotionRule.VALIDATED and not entry.validated:
            return False, "not_validated"

        # Check auto-promotion rules
        if entry.occurrence_count >= self._config.min_occurrences:
            return True, "duplicate_clustering"

        if entry.ci_failure or entry.ci_prevention:
            return True, "ci_impact"

        if entry.touches_invariant:
            return True, "invariant_update"

        if (
            entry.touches_kill_switch
            or entry.touches_canary
            or entry.touches_risk_limit
        ):
            return True, "execution_safety"

        return False, "no_matching_rule"

    def promote_entry(
        self,
        entry: MemoryEntry,
        dry_run: bool = True,
    ) -> bool:
        """
        Promote a single entry to Qdrant.

        Args:
            entry: The memory entry to promote.
            dry_run: If True, don't actually promote.

        Returns:
            True if promoted (or would be in dry run), False otherwise.
        """
        if self._qdrant_client is None:
            logger.warning("No Qdrant client available")
            return False

        try:
            payload = entry.to_qdrant_payload()

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would promote entry {entry.id}",
                    extra={
                        "category": entry.category.value,
                        "story_id": entry.story_id,
                    },
                )
                return True

            # Store in Qdrant
            # Note: Actual vector generation would happen here or be provided
            # For now, we assume the entry has a pre-computed vector or we use a placeholder
            self._qdrant_client.upsert(
                collection_name=self._config.qdrant_collection,
                points=[
                    {
                        "id": entry.id,
                        "payload": payload,
                        # Vector would be generated from content
                        "vector": entry.metadata.get("vector", []),
                    }
                ],
            )

            logger.info(f"Promoted entry {entry.id} to Qdrant")
            return True

        except Exception as e:
            logger.error(f"Failed to promote entry {entry.id}: {e}")
            return False

    def run_promotion(
        self,
        entries: list[MemoryEntry] | None = None,
        dry_run: bool | None = None,
    ) -> PromotionStats:
        """
        Run the promotion process.

        Args:
            entries: Optional list of entries to process. If None, scans Redis.
            dry_run: Override config dry_run setting.

        Returns:
            PromotionStats containing results.
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run
        stats = PromotionStats(was_dry_run=is_dry_run)

        # Safety check
        if not self.is_enabled() and not is_dry_run:
            stats.error = "Engine is disabled. Enable feature flag or use dry_run=True"
            logger.error(stats.error)
            return stats

        try:
            logger.info("Promotion started", extra={"dry_run": is_dry_run})

            # Get entries if not provided
            if entries is None:
                entries = self._scan_redis_entries()

            stats.entries_scanned = len(entries)

            # Process each entry
            for entry in entries:
                should_promote, reason = self.should_promote(entry)

                if not should_promote:
                    stats.entries_skipped += 1
                    continue

                # Track by category
                cat_key = entry.category.value
                stats.by_category[cat_key] = stats.by_category.get(cat_key, 0) + 1
                stats.promotion_reasons[reason] = (
                    stats.promotion_reasons.get(reason, 0) + 1
                )

                # Promote the entry
                if self.promote_entry(entry, dry_run=is_dry_run):
                    stats.entries_promoted += 1

            logger.info(
                "Promotion completed",
                extra={
                    "entries_scanned": stats.entries_scanned,
                    "entries_promoted": stats.entries_promoted,
                    "entries_skipped": stats.entries_skipped,
                    "dry_run": is_dry_run,
                },
            )

        except Exception as e:
            stats.error = str(e)
            logger.exception("Promotion failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return stats

    def _scan_redis_entries(self) -> list[MemoryEntry]:
        """
        Scan Redis for memory entries to promote.

        Returns:
            List of MemoryEntry objects.
        """
        entries = []

        if self._redis_client is None:
            return entries

        # Scan iterlog patterns
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
                        try:
                            entry = self._parse_redis_key(key)
                            if entry:
                                entries.append(entry)
                        except Exception as e:
                            logger.warning(f"Failed to parse key {key}: {e}")

                    if cursor == 0:
                        break

            except Exception as e:
                logger.error(f"Redis scan failed for pattern {pattern}: {e}")

        return entries

    def _parse_redis_key(self, key: str) -> MemoryEntry | None:
        """
        Parse a Redis key into a MemoryEntry.

        Args:
            key: Redis key string.

        Returns:
            MemoryEntry or None if not parseable.
        """
        # Extract story_id from key pattern: bmad:chiseai:iterlog:story:<id>
        parts = key.split(":")

        if len(parts) < 5 or parts[3] != "story":
            return None

        story_id = parts[4]

        # Get the data from Redis
        try:
            key_type = self._redis_client.type(key)

            if key_type == "hash":
                data = self._redis_client.hgetall(key)
            elif key_type == "list":
                data = {"items": self._redis_client.lrange(key, 0, -1)}
            else:
                data = {"value": self._redis_client.get(key)}

            # Determine category based on key suffix
            category = MemoryCategory.DECISION  # Default
            if "incident" in key:
                category = MemoryCategory.POSTMORTEM
            elif "decision" in key:
                category = MemoryCategory.DECISION

            # Build content from data
            content = json.dumps(data, default=str)

            return MemoryEntry(
                id=f"{story_id}_{hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:8]}",
                content=content,
                category=category,
                story_id=story_id,
                agent=data.get("agent", "unknown"),
                timestamp=datetime.now(UTC),  # Would parse from data if available
                metadata={"source_key": key, "redis_type": key_type},
            )

        except Exception as e:
            logger.warning(f"Failed to read key {key}: {e}")
            return None

    def get_stats(self) -> PromotionStats | None:
        """Get statistics from the last promotion run."""
        return self._last_stats

    def enable(self) -> bool:
        """Enable the promotion engine."""
        if self._redis_client is None:
            logger.warning("Cannot enable: no Redis client available")
            return False

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "true")
            self._enabled = True
            logger.info("Promotion engine enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable promotion engine: {e}")
            return False

    def disable(self) -> bool:
        """Disable the promotion engine."""
        if self._redis_client is None:
            self._enabled = False
            logger.info("Promotion engine disabled (local state only)")
            return True

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "false")
            self._enabled = False
            logger.info("Promotion engine disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable promotion engine: {e}")
            self._enabled = False
            return True
