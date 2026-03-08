# Memory Deduplication Engine

> **Story:** ST-GOV-001  
> **Status:** Implementation Complete  
> **Last Updated:** 2026-03-07

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

## Implementation Details

### Source Code Structure

```
src/governance/deduplication/
├── __init__.py           # Module exports
├── config.py             # Configuration and settings
├── engine.py             # Main deduplication engine
├── hash_cache.py         # Redis-based hash caching
└── audit.py              # Audit trail for decisions
```

### Feature Flag

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
| `similarity_threshold` | 0.85 | Cosine similarity threshold for dedup |
| `qdrant_similarity_threshold` | 0.85 | Threshold for Qdrant vector similarity search |
| `redis_hash_cache_ttl` | 86400 | TTL in seconds for Redis hash cache (24 hours) |
| `redis_hash_cache_prefix` | `bmad:chiseai:dedup:hash_cache` | Prefix for Redis hash keys |
| `audit_trail_key` | `bmad:chiseai:deduplication:audit` | Redis key for audit trail |
| `audit_trail_ttl` | 2592000 | TTL in seconds for audit entries (30 days) |
| `batch_size` | 100 | Processing batch size |
| `dry_run` | true | Safe mode - no actual deletions |
| `strategy` | hybrid | Deduplication strategy to use |
| `collections` | ["ChiseAI"] | Qdrant collections to deduplicate |
| `hash_algorithm` | sha256 | Algorithm for content hashing |
| `temporal_window_seconds` | 3600 | Time window for temporal proximity (1 hour) |
| `min_duplicates` | 2 | Minimum duplicates to trigger consolidation |

Configuration can be overridden via environment or Redis keys.

## Deduplication Strategies

### 1. Exact Match Deduplication

Identifies entries with identical content using SHA-256 content hashing.

```python
hash_a = hashlib.sha256(content_a.encode()).hexdigest()
hash_b = hashlib.sha256(content_b.encode()).hexdigest()
if hash_a == hash_b:
    # Consider for deduplication
```

### 2. Semantic Similarity Deduplication

Uses vector embeddings with cosine similarity to identify semantically similar entries.

```python
# Cosine similarity calculation
similarity = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
if similarity >= threshold:
    # Consider for deduplication
```

Default threshold: **0.85 cosine similarity**

### 3. Temporal Proximity Deduplication

Considers entries created within a configurable time window as potential duplicates.

```python
if abs(entry_a.timestamp - entry_b.timestamp) < temporal_window:
    # Apply additional checks
```

Default window: **1 hour**

### 4. Hybrid Strategy

Combines all strategies, returning the maximum similarity score:

```python
exact_sim = exact_match_similarity(a, b)
semantic_sim = cosine_similarity(a, b)
temporal_sim = temporal_similarity(a, b)
return max(exact_sim, semantic_sim, temporal_sim)
```

## Usage

### Basic Usage

```python
from src.governance.deduplication import MemoryDeduplicationEngine

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
from src.governance.deduplication import (
    MemoryDeduplicationEngine,
    DeduplicationConfig,
    DeduplicationStrategy,
)

config = DeduplicationConfig(
    similarity_threshold=0.90,
    strategy=DeduplicationStrategy.SEMANTIC_SIMILARITY,
    dry_run=True,  # Always start with dry run
)

engine = MemoryDeduplicationEngine(config=config)
stats = engine.deduplicate()
```

### Hash Cache Usage

```python
from src.governance.deduplication import HashCache

cache = HashCache()

# Check for duplicates before ingestion
is_dup, source_id = cache.is_duplicate(new_content)
if is_dup:
    print(f"Duplicate of {source_id}, skipping...")
else:
    # Ingest and cache
    point_id = ingest_to_qdrant(new_content)
    cache.add_hash(new_content, point_id, "ChiseAI")
```

### Audit Trail Usage

```python
from src.governance.deduplication import AuditTrail, DeduplicationAction, DeduplicationResult

trail = AuditTrail()

# Log a deduplication decision
trail.log(
    action=DeduplicationAction.DUPLICATE_REMOVED,
    result=DeduplicationResult.REMOVED,
    source_id="point-1",
    collection="ChiseAI",
    similarity_score=0.92,
    reason="High similarity detected",
)

# Retrieve recent decisions
recent = trail.get_recent_entries(limit=100)
```

## Redis Cache for Recent Hashes

The hash cache stores recently ingested content hashes in Redis with configurable TTL (default: 24 hours). This prevents near-duplicate ingestion during high-volume periods.

### Cache Key Structure

```
bmad:chiseai:dedup:hash_cache:<content_hash>
```

### Cache Entry Format

```json
{
  "content_hash": "sha256_hash",
  "source_id": "qdrant_point_id",
  "collection": "ChiseAI",
  "timestamp": "2026-03-07T14:45:00Z",
  "metadata": {}
}
```

### Cache Statistics

```python
from src.governance.deduplication import HashCache

cache = HashCache()
stats = cache.get_cache_stats()
print(f"Cached entries: {stats['entry_count']}")
print(f"Memory usage: {stats['approx_memory_bytes']} bytes")
print(f"TTL: {stats['ttl_seconds']} seconds")
```

## Audit Trail for Deduplication Decisions

All deduplication decisions are logged to Redis for auditability.

### Audit Key Structure

```
bmad:chiseai:deduplication:audit:<entry_id>
bmad:chiseai:deduplication:audit:list  # Chronological list
```

### Audit Entry Format

```json
{
  "entry_id": "uuid",
  "timestamp": "2026-03-07T14:45:00Z",
  "action": "duplicate_removed",
  "result": "removed",
  "source_id": "canonical_point_id",
  "duplicate_id": "duplicate_point_id",
  "collection": "ChiseAI",
  "similarity_score": 0.92,
  "threshold_used": 0.85,
  "strategy": "hybrid",
  "metadata": {},
  "reason": "High similarity detected"
}
```

### Audit Actions

- `duplicate_detected` - Duplicate was identified
- `duplicate_removed` - Duplicate was removed
- `duplicate_skipped` - Duplicate was kept (dry run or below threshold)
- `cache_hit` - Hash found in cache
- `cache_miss` - Hash not in cache
- `similarity_check` - Similarity comparison performed
- `threshold_adjusted` - Threshold was adjusted dynamically

## Statistics Tracking

Each deduplication run produces `DeduplicationStats`:

```python
@dataclass
class DeduplicationStats:
    timestamp: datetime
    collections_scanned: int
    entries_scanned: int
    duplicate_groups: int
    entries_to_remove: int
    entries_removed: int
    cache_hits: int
    cache_misses: int
    similarity_checks: int
    processing_time_seconds: float
    was_dry_run: bool
    errors: list[str]
```

Stats are stored in Redis with key pattern:
```
bmad:chiseai:dedup:stats:<timestamp>
```

## Testing

Run the test suite:

```bash
pytest tests/test_governance/test_deduplication.py -v
```

Coverage requirement: **≥ 85%** (current: 88%)

### Test Categories

- Configuration validation
- Hash cache operations
- Audit trail logging
- Similarity calculations (cosine, exact match, temporal)
- Engine deduplication logic
- Dry run mode
- Edge cases and error handling

## Related Files

- `src/governance/deduplication/__init__.py` - Module exports
- `src/governance/deduplication/config.py` - Configuration
- `src/governance/deduplication/engine.py` - Main engine
- `src/governance/deduplication/hash_cache.py` - Hash caching
- `src/governance/deduplication/audit.py` - Audit trail
- `tests/test_governance/test_deduplication.py` - Test suite

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-07 | 1.0.0 | Full implementation with configurable thresholds, Redis cache, and audit trail |
| 2026-02-22 | 0.1.0 | Initial skeleton with feature flag integration |

## Acceptance Criteria (Met)

- ✅ Configurable similarity threshold (default: 0.85 cosine similarity)
- ✅ Deduplication across Qdrant collections with configurable thresholds
- ✅ Redis cache for recent hashes to prevent near-duplicate ingestion (TTL: 24 hours)
- ✅ Audit trail for deduplication decisions with configurable thresholds
