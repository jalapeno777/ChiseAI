"""
Configuration for Memory Consolidation Scheduler.

Defines retention policies, scheduling parameters, and rollback settings.

Story: ST-GOV-005
Governance Feature: GF-005
"""

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Any


class MemoryType(Enum):
    """Types of memories with different retention policies."""

    DECISION = "decision"
    PATTERN = "pattern"
    ANTI_PATTERN = "anti-pattern"
    SUMMARY = "summary"
    LEARNING = "learning"
    INCIDENT = "incident"
    CONTEXT = "context"


class MemoryPriority(Enum):
    """Priority levels for memory promotion."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    GOLDEN = 4  # Highest priority, never archived


@dataclass
class RetentionPolicy:
    """
    Retention policy for a specific memory type.

    Defines how long memories of a given type should be retained
    before being eligible for archival.
    """

    memory_type: MemoryType
    """Type of memory this policy applies to"""

    retention_days: int = 90
    """Days before memory is eligible for archival"""

    archive_to_cold: bool = True
    """Whether to move to cold storage or delete"""

    min_access_count: int = 0
    """Minimum accesses to prevent archival (0 = no minimum)"""

    preserve_if_tagged: list[str] = field(default_factory=list)
    """Tags that prevent archival if present"""


@dataclass
class ConsolidationConfig:
    """
    Main configuration for the consolidation scheduler.

    Controls scheduling, retention policies, and rollback behavior.
    """

    # Scheduling
    schedule_time: time = field(default_factory=lambda: time(2, 0))  # 2 AM UTC
    """Time of day to run consolidation (UTC)"""

    schedule_timezone: str = "UTC"
    """Timezone for scheduling"""

    enabled: bool = False
    """Whether consolidation is enabled (feature flag)"""

    dry_run: bool = True
    """If True, no actual changes are made"""

    # Retention policies per memory type
    retention_policies: dict[MemoryType, RetentionPolicy] = field(
        default_factory=lambda: {
            MemoryType.DECISION: RetentionPolicy(
                memory_type=MemoryType.DECISION,
                retention_days=90,
                archive_to_cold=True,
                min_access_count=1,
            ),
            MemoryType.PATTERN: RetentionPolicy(
                memory_type=MemoryType.PATTERN,
                retention_days=180,
                archive_to_cold=True,
                min_access_count=2,
            ),
            MemoryType.ANTI_PATTERN: RetentionPolicy(
                memory_type=MemoryType.ANTI_PATTERN,
                retention_days=180,
                archive_to_cold=True,
                min_access_count=1,
            ),
            MemoryType.SUMMARY: RetentionPolicy(
                memory_type=MemoryType.SUMMARY,
                retention_days=60,
                archive_to_cold=True,
                min_access_count=0,
            ),
            MemoryType.LEARNING: RetentionPolicy(
                memory_type=MemoryType.LEARNING,
                retention_days=120,
                archive_to_cold=True,
                min_access_count=3,
            ),
            MemoryType.INCIDENT: RetentionPolicy(
                memory_type=MemoryType.INCIDENT,
                retention_days=365,
                archive_to_cold=True,
                min_access_count=2,
                preserve_if_tagged=["postmortem", "critical"],
            ),
            MemoryType.CONTEXT: RetentionPolicy(
                memory_type=MemoryType.CONTEXT,
                retention_days=30,
                archive_to_cold=True,
                min_access_count=0,
            ),
        }
    )

    # Rollback configuration
    rollback_retention_days: int = 7
    """Number of days rollback data is preserved"""

    rollback_max_operations: int = 10000
    """Maximum operations stored for rollback"""

    # Golden promotion thresholds
    golden_min_access_count: int = 5
    """Minimum accesses for golden promotion"""

    golden_min_age_days: int = 30
    """Minimum age for golden promotion"""

    golden_min_relevance_score: float = 0.85
    """Minimum relevance score for golden promotion"""

    # Performance settings
    batch_size: int = 100
    """Number of memories to process per batch"""

    max_concurrent_operations: int = 10
    """Maximum concurrent archive/promote operations"""

    # Storage targets
    cold_storage_path: str = "/data/chiseai/cold_storage/memories"
    """Path to cold storage for archived memories"""

    golden_collection: str = "ChiseAI_golden"
    """Qdrant collection name for golden memories"""

    # Feature flag key
    feature_flag_key: str = "chise:feature_flags:governance:consolidation_enabled"

    # Tempmemory ingestion settings
    run_tempmemory_ingestion: bool = True
    """Whether to run tempmemory ingestion as Step 0"""

    tempmemory_ingestion_dry_run: bool = False
    """If True, tempmemory ingestion runs in dry-run mode"""

    tempmemory_ingestion_filter_types: list[str] = field(
        default_factory=lambda: ["decision", "pattern", "summary", "anti-pattern"]
    )
    """Frontmatter types to ingest (empty list = all types)"""

    tempmemory_ingestion_cadence: str = "daily"
    """Cadence for tempmemory ingestion: 'daily', 'always', or 'manual'"""

    def get_policy(self, memory_type: MemoryType) -> RetentionPolicy:
        """
        Get retention policy for a memory type.

        Args:
            memory_type: Type of memory to get policy for

        Returns:
            RetentionPolicy for the memory type
        """
        return self.retention_policies.get(
            memory_type,
            RetentionPolicy(memory_type=memory_type),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "schedule_time": self.schedule_time.isoformat(),
            "schedule_timezone": self.schedule_timezone,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "rollback_retention_days": self.rollback_retention_days,
            "rollback_max_operations": self.rollback_max_operations,
            "golden_min_access_count": self.golden_min_access_count,
            "golden_min_age_days": self.golden_min_age_days,
            "golden_min_relevance_score": self.golden_min_relevance_score,
            "batch_size": self.batch_size,
            "cold_storage_path": self.cold_storage_path,
            "golden_collection": self.golden_collection,
            "feature_flag_key": self.feature_flag_key,
            "run_tempmemory_ingestion": self.run_tempmemory_ingestion,
            "tempmemory_ingestion_dry_run": self.tempmemory_ingestion_dry_run,
            "tempmemory_ingestion_filter_types": self.tempmemory_ingestion_filter_types,
            "tempmemory_ingestion_cadence": self.tempmemory_ingestion_cadence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsolidationConfig":
        """Create config from dictionary."""
        config = cls()

        if "schedule_time" in data:
            config.schedule_time = time.fromisoformat(data["schedule_time"])
        if "schedule_timezone" in data:
            config.schedule_timezone = data["schedule_timezone"]
        if "enabled" in data:
            config.enabled = data["enabled"]
        if "dry_run" in data:
            config.dry_run = data["dry_run"]
        if "rollback_retention_days" in data:
            config.rollback_retention_days = data["rollback_retention_days"]
        if "rollback_max_operations" in data:
            config.rollback_max_operations = data["rollback_max_operations"]
        if "golden_min_access_count" in data:
            config.golden_min_access_count = data["golden_min_access_count"]
        if "golden_min_age_days" in data:
            config.golden_min_age_days = data["golden_min_age_days"]
        if "golden_min_relevance_score" in data:
            config.golden_min_relevance_score = data["golden_min_relevance_score"]
        if "batch_size" in data:
            config.batch_size = data["batch_size"]
        if "cold_storage_path" in data:
            config.cold_storage_path = data["cold_storage_path"]
        if "golden_collection" in data:
            config.golden_collection = data["golden_collection"]
        if "run_tempmemory_ingestion" in data:
            config.run_tempmemory_ingestion = data["run_tempmemory_ingestion"]
        if "tempmemory_ingestion_dry_run" in data:
            config.tempmemory_ingestion_dry_run = data["tempmemory_ingestion_dry_run"]
        if "tempmemory_ingestion_filter_types" in data:
            config.tempmemory_ingestion_filter_types = data[
                "tempmemory_ingestion_filter_types"
            ]
        if "tempmemory_ingestion_cadence" in data:
            config.tempmemory_ingestion_cadence = data["tempmemory_ingestion_cadence"]

        return config


# Redis key prefixes for consolidation
CONSOLIDATION_PREFIX = "chise:governance:consolidation"
LAST_RUN_KEY = f"{CONSOLIDATION_PREFIX}:last_run"
ROLLBACK_PREFIX = f"{CONSOLIDATION_PREFIX}:rollback"
METRICS_PREFIX = f"{CONSOLIDATION_PREFIX}:metrics"
