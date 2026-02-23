# Memory Deduplication Engine

> **Story:** ST-GOV-001  
> **Status:** Implementation Skeleton  
> **Last Updated:** 2026-02-22

## Overview

The Memory Deduplication Engine identifies and eliminates duplicate memory entries across ChiseAI's memory stores (Redis and Qdrant) to optimize storage and improve retrieval accuracy.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Memory Deduplication Engine                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Config     │    │  Feature     │    │   Stats      │       │
│  │   Manager    │    │  Flags       │    │   Tracker    │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Deduplication Core                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │   Scanner   │→ │  Analyzer   │→ │  Remover    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────┐    ┌────────────────────┐              │
│  │   Redis Client     │    │   Qdrant Client    │              │
│  │   (Short-term)     │    │   (Long-term)      │              │
│  └────────────────────┘    └────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Feature Flag

The engine is controlled by a feature flag stored in Redis:

```
Key: chise:feature_flags:governance:memory_dedup_enabled
Type: Boolean
Default: false (disabled)
```

### Safety Rollout Pattern

1. **Phase 1:** Deploy skeleton with feature flag disabled (current)
2. **Phase 2:** Enable for specific test cases
3. **Phase 3:** Enable for canary deployment
4. **Phase 4:** General availability

## Configuration

Configuration is stored in `DeduplicationConfig`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `similarity_threshold` | 0.95 | Vector similarity threshold for dedup |
| `max_age_days` | 30 | Maximum entry age to consider |
| `batch_size` | 100 | Processing batch size |
| `dry_run` | true | Safe mode - no actual deletions |
| `min_duplicates` | 2 | Minimum duplicates to trigger consolidation |

Configuration can be overridden via Redis keys under `chise:governance:dedup:config:*`.

## Deduplication Strategies

### 1. Exact Match Deduplication

Identifies entries with identical content using content hashing.

```python
# Content hash comparison
hash(entry_a.content) == hash(entry_b.content)
```

### 2. Semantic Similarity Deduplication

Uses vector embeddings to identify semantically similar entries.

```python
# Vector similarity comparison
similarity = cosine_similarity(entry_a.vector, entry_b.vector)
if similarity >= threshold:
    # Consider for deduplication
```

### 3. Temporal Proximity Deduplication

Considers entries created within a time window as potential duplicates.

```python
# Time window comparison
if abs(entry_a.timestamp - entry_b.timestamp) < time_window:
    # Apply additional checks
```

## Usage

### Basic Usage

```python
from src.governance.memory import MemoryDeduplicationEngine

# Create engine (disabled by default)
engine = MemoryDeduplicationEngine()

# Check if enabled
if engine.is_enabled():
    # Run deduplication
    stats = engine.deduplicate()
    print(f"Removed {stats.entries_removed} duplicates")
else:
    # Dry run for testing
    stats = engine.deduplicate(dry_run=True)
    print(f"Would remove {stats.entries_to_remove} duplicates")
```

### With Custom Configuration

```python
from src.governance.memory.deduplication import (
    MemoryDeduplicationEngine,
    DeduplicationConfig,
)

config = DeduplicationConfig(
    similarity_threshold=0.9,
    max_age_days=7,
    dry_run=True,  # Always start with dry run
)

engine = MemoryDeduplicationEngine(config=config)
stats = engine.deduplicate()
```

## Statistics Tracking

Each deduplication run produces `DeduplicationStats`:

```python
@dataclass
class DeduplicationStats:
    timestamp: datetime
    entries_scanned: int
    duplicate_groups: int
    entries_to_remove: int
    entries_removed: int
    bytes_saved: int
    processing_time_seconds: float
    was_dry_run: bool
    error: Optional[str]
```

## Audit Trail

All deduplication operations are logged for audit purposes:

- Timestamp of operation
- Scope of deduplication
- Number of entries affected
- Dry run status
- Any errors encountered

## Future Enhancements

### Phase 2 (Planned)
- [ ] Actual Redis scanning implementation
- [ ] Actual Qdrant vector similarity search
- [ ] Content hashing for exact match detection
- [ ] Rollback mechanism

### Phase 3 (Planned)
- [ ] Automated scheduling via cron/interval
- [ ] Metrics export to Grafana
- [ ] Alerting on anomalies
- [ ] Cross-store deduplication

### Phase 4 (Future)
- [ ] Machine learning for duplicate scoring
- [ ] Automatic canonical entry selection
- [ ] Reference update automation

## Related Files

- `src/governance/memory/deduplication.py` - Main engine implementation
- `src/governance/memory/__init__.py` - Module exports
- `tests/test_governance/test_memory_dedup.py` - Test suite

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-22 | 0.1.0 | Initial skeleton with feature flag integration |
