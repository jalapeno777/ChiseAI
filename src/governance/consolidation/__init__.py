"""
Memory Consolidation Module for ChiseAI Governance.

Provides automated memory lifecycle management including:
- Daily archival of aged memories to cold storage
- Promotion of high-value memories to "golden" set
- Configurable retention policies per memory type
- 7-day rollback capability

Story: ST-GOV-005
Governance Feature: GF-005
"""

from src.governance.consolidation.archiver import (
    ArchivedMemory,
    ArchiveStats,
    MemoryArchiver,
)
from src.governance.consolidation.config import (
    CONSOLIDATION_PREFIX,
    LAST_RUN_KEY,
    ROLLBACK_PREFIX,
    ConsolidationConfig,
    MemoryPriority,
    MemoryType,
    RetentionPolicy,
)
from src.governance.consolidation.promoter import (
    GoldenMemoryPromoter,
    PromotionCandidate,
    PromotionStats,
)
from src.governance.consolidation.rollback import (
    RollbackManager,
    RollbackOperation,
    RollbackStats,
    RollbackWindow,
)
from src.governance.consolidation.scheduler import (
    ConsolidationResult,
    MemoryConsolidationScheduler,
)

__all__ = [
    # Scheduler
    "MemoryConsolidationScheduler",
    "ConsolidationResult",
    # Config
    "ConsolidationConfig",
    "MemoryType",
    "MemoryPriority",
    "RetentionPolicy",
    # Archiver
    "MemoryArchiver",
    "ArchivedMemory",
    "ArchiveStats",
    # Promoter
    "GoldenMemoryPromoter",
    "PromotionCandidate",
    "PromotionStats",
    # Rollback
    "RollbackManager",
    "RollbackOperation",
    "RollbackStats",
    "RollbackWindow",
    # Keys
    "CONSOLIDATION_PREFIX",
    "LAST_RUN_KEY",
    "ROLLBACK_PREFIX",
]
