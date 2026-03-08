"""
Memory Deduplication Engine for ChiseAI Governance.

Provides deduplication across memory stores with configurable thresholds,
Redis-based hash caching, and comprehensive audit trails.

Story: ST-GOV-001
"""

from src.governance.deduplication.audit import (
    AuditEntry,
    AuditTrail,
    DeduplicationAction,
    DeduplicationResult,
)
from src.governance.deduplication.config import (
    DEDUPLICATION_PREFIX,
    DeduplicationConfig,
    DeduplicationStrategy,
)
from src.governance.deduplication.engine import (
    DeduplicationStats,
    DuplicateGroup,
    MemoryDeduplicationEngine,
)
from src.governance.deduplication.hash_cache import (
    HashCache,
    HashCacheEntry,
)

__all__ = [
    # Engine
    "MemoryDeduplicationEngine",
    "DeduplicationStats",
    "DuplicateGroup",
    # Config
    "DeduplicationConfig",
    "DeduplicationStrategy",
    "DEDUPLICATION_PREFIX",
    # Hash Cache
    "HashCache",
    "HashCacheEntry",
    # Audit Trail
    "AuditTrail",
    "AuditEntry",
    "DeduplicationAction",
    "DeduplicationResult",
]
