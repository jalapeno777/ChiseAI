# BrainEval Ingestion Runbook

## Overview

This runbook documents the operational procedures for BrainEval integration with tempmemory migration, including multi-source ingestion, provenance tracking, and deduplication.

**Story**: ST-MEMORY-003 - Phase 2: Mini/Full BrainEval Multi-Source Ingestion + Provenance + Anti-Dup Basics

## Table of Contents

1. [Quick Start](#quick-start)
2. [Multi-Source Ingestion](#multi-source-ingestion)
3. [Provenance Tracking](#provenance-tracking)
4. [Deduplication](#deduplication)
5. [KPI Updates](#kpi-updates)
6. [Troubleshooting](#troubleshooting)
7. [KPI Interpretation](#kpi-interpretation)

## Quick Start

### Prerequisites

- Redis running on `host.docker.internal:6380`
- Qdrant running on `host.docker.internal:6334` (optional)
- Access to `docs/tempmemories/` directory

### Dry Run (Recommended First Step)

```bash
python3 scripts/ops/brain_eval_ingestion.py --dry-run
```

This will scan all tempmemory files and show what would be ingested without making any changes.

### Full Ingestion

```bash
python3 scripts/ops/brain_eval_ingestion.py --full-ingestion
```

This runs the complete multi-source ingestion pipeline.

## Multi-Source Ingestion

The BrainEval integration supports ingestion from multiple sources:

### 1. Migration Reports

Ingest from tempmemory migration results:

```bash
python3 scripts/ops/brain_eval_ingestion.py --source=migration_report
```

**What it does**:
- Scans `docs/tempmemories/` for markdown files
- Parses YAML frontmatter
- Migrates to Redis and/or Qdrant based on file type
- Records provenance for each file

**File Type Mapping**:
| Type | Target | Description |
|------|--------|-------------|
| `decision` | BOTH | Goes to Redis + Qdrant |
| `pattern` | BOTH | Goes to Redis + Qdrant |
| `summary` | QDRANT | Goes to Qdrant only |
| `anti-pattern` | QDRANT | Goes to Qdrant only |
| default | BOTH | Goes to both |

### 2. Iterlog Decisions

Ingest from Redis iterlog:

```bash
python3 scripts/ops/brain_eval_ingestion.py --source=iterlog_decisions --story-id=ST-XXX
```

**What it does**:
- Reads from `bmad:chiseai:iterlog:story:{story_id}:decisions`
- Extracts decisions and metadata
- Records provenance with agent information

### 3. Tempmemory Files

Direct file ingestion:

```bash
python3 scripts/ops/brain_eval_ingestion.py --source=tempmemory_files
```

**What it does**:
- Scans files directly without migration engine
- Records provenance for each file
- Useful for one-off file ingestion

## Provenance Tracking

Provenance tracking records the origin and lineage of every memory.

### What is Tracked

For each memory, the following is recorded:

- **memory_id**: Unique identifier
- **source_type**: Type of source (file, Redis, Qdrant, etc.)
- **source_path**: Path or identifier of the source
- **commit_sha**: Git commit SHA at time of ingestion
- **timestamp**: ISO timestamp
- **agent**: Agent that performed the ingestion
- **story_id**: Associated story ID
- **content_hash**: SHA256 hash for integrity verification
- **parent_ids**: List of parent memory IDs (for derived memories)

### Redis Key Structure

```
bmad:chiseai:tempmemory:provenance:{memory_id}     # Hash with provenance data
bmad:chiseai:tempmemory:provenance:chain:{memory_id}  # List of chain entries
bmad:chiseai:tempmemory:provenance:by_source:{type}   # Set of memory IDs
bmad:chiseai:tempmemory:provenance:by_story:{story_id} # Set of memory IDs
```

### Querying Provenance

```python
from governance.tempmemory.provenance import ProvenanceTracker

tracker = ProvenanceTracker(redis_client=redis)

# Get provenance for a memory
record = tracker.get_provenance("memory-id")

# Get full chain
chain = tracker.get_provenance_chain("memory-id")

# Query by source
memory_ids = tracker.query_by_source(ProvenanceSource.TEMPMEMORY_FILE)

# Query by story
memory_ids = tracker.query_by_story("ST-MEMORY-003")

# Generate audit report
report = tracker.generate_audit_report(story_id="ST-MEMORY-003")
```

### Audit Report

Generate an audit report to see where memories came from:

```python
from governance.tempmemory.provenance import ProvenanceTracker

tracker = ProvenanceTracker(redis_client=redis)
report = tracker.generate_audit_report()

print(f"Total records: {report['statistics']['total_records']}")
print(f"By source: {report['statistics']['by_source']}")
print(f"By agent: {report['statistics']['by_agent']}")
```

## Deduplication

The deduplication engine detects and handles duplicate memories using embedding-based similarity.

### How it Works

1. **Embedding Generation**: Uses `sentence-transformers` (all-MiniLM-L6-v2) to generate embeddings
2. **Similarity Check**: Computes cosine similarity between embeddings
3. **Threshold**: Default threshold is 0.92 (configurable)
4. **Action**: Configurable action when duplicate detected

### Configuration

```python
from governance.tempmemory.deduplication import DeduplicationEngine, DeduplicationAction

engine = DeduplicationEngine(
    redis_client=redis,
    similarity_threshold=0.92,  # 0.0 to 1.0
    default_action=DeduplicationAction.FLAG,  # SKIP, MERGE, FLAG, REPLACE
)
```

### Actions

| Action | Description |
|--------|-------------|
| `SKIP` | Don't store the duplicate |
| `MERGE` | Merge with existing memory |
| `FLAG` | Store but flag as duplicate |
| `REPLACE` | Replace existing with new |

### Checking for Duplicates

```python
from governance.tempmemory.deduplication import DeduplicationEngine

engine = DeduplicationEngine(redis_client=redis)

result = engine.check_duplicate(
    content="Memory content to check",
    memory_id="optional-existing-id",
)

if result.is_duplicate:
    print(f"Duplicate detected: {result.message}")
    print(f"Best match: {result.selected_match.memory_id}")
    print(f"Similarity: {result.selected_match.similarity}")
```

### Index Management

```python
# Index a memory for future deduplication checks
engine.index_memory(
    memory_id="my-memory",
    content="Memory content",
    metadata={"story_id": "ST-XXX"},
)

# Get index statistics
stats = engine.get_index_stats()
print(f"Total indexed: {stats['total_indexed']}")

# Clear the index
engine.clear_index()
```

## KPI Updates

### BrainEval KPIs

The integration updates the following BrainEval KPIs:

**From Migration**:
- `migration_success_rate`: Percentage of files successfully migrated
- `migration_failed_count`: Number of failed migrations
- `migration_skipped_count`: Number of skipped files
- `migration_duration_seconds`: Time taken for migration

**From Ingestion**:
- `ingestion_success_rate`: Percentage of items successfully ingested
- `ingestion_failed_count`: Number of failed ingestions
- `ingestion_sources`: Number of sources processed

### MiniBrainEval KPIs

MiniBrainEval receives updates through its `collect_kpis()` method:
- Data freshness checks for Redis, InfluxDB, Qdrant
- Issue detection from log scanning
- Proxy metrics when primary KPIs unavailable

## Troubleshooting

### Issue: Redis Connection Failed

**Symptom**: `Redis not available: Error connecting to Redis`

**Solution**:
1. Check Redis is running: `docker ps | grep redis`
2. Verify connection: `redis-cli -h host.docker.internal -p 6380 ping`
3. Check network connectivity from container

### Issue: Qdrant Storage Fails

**Symptom**: `Qdrant migration failed for {file}: ...`

**Solution**:
1. Check Qdrant is running: `docker ps | grep qdrant`
2. Verify collection exists: `curl http://host.docker.internal:6334/collections`
3. Check Qdrant logs: `docker logs chiseai-qdrant`

### Issue: High Duplicate Rate

**Symptom**: Many files flagged as duplicates

**Solution**:
1. Check similarity threshold (default 0.92)
2. Review deduplication action (FLAG vs SKIP)
3. Clear deduplication index if needed:
   ```python
   from governance.tempmemory.deduplication import DeduplicationEngine
   engine = DeduplicationEngine(redis_client=redis)
   engine.clear_index()
   ```

### Issue: Provenance Records Missing

**Symptom**: No provenance data found in Redis

**Solution**:
1. Check Redis keys: `KEYS bmad:chiseai:tempmemory:provenance:*`
2. Verify provenance tracker is initialized
3. Check for errors in logs during ingestion

### Issue: Embedding Generation Slow

**Symptom**: Migration takes very long

**Solution**:
1. Check if `sentence-transformers` is installed
2. Without it, fallback embeddings are used (faster but less accurate)
3. Install for better quality: `pip install sentence-transformers`

## KPI Interpretation

### Migration Success Rate

```
Success Rate = Migrated Files / Total Files
```

- **> 0.95**: Excellent - most files migrated successfully
- **0.80 - 0.95**: Good - some files failed, review logs
- **< 0.80**: Poor - significant issues, investigate

### Ingestion Success Rate

```
Success Rate = Items Ingested / Items Processed
```

- **> 0.95**: Excellent - most items ingested
- **0.80 - 0.95**: Good - some items failed, may be duplicates
- **< 0.80**: Poor - investigate source data quality

### Deduplication Rate

```
Deduplication Rate = Items Deduplicated / Items Processed
```

- **< 0.10**: Normal - low duplicate rate
- **0.10 - 0.30**: Moderate - some redundancy in sources
- **> 0.30**: High - significant duplication, review source organization

### Provenance Coverage

```
Coverage = Memories with Provenance / Total Memories
```

- **= 1.0**: Complete - all memories tracked
- **< 1.0**: Incomplete - some memories missing provenance

## Maintenance

### Regular Tasks

1. **Weekly**: Review ingestion history
   ```bash
   python3 scripts/ops/brain_eval_ingestion.py --history --limit=50
   ```

2. **Monthly**: Clean up old deduplication index
   ```python
   from governance.tempmemory.deduplication import DeduplicationEngine
   engine = DeduplicationEngine(redis_client=redis)
   stats = engine.get_index_stats()
   if stats['total_indexed'] > 10000:
       engine.clear_index()
   ```

3. **Quarterly**: Generate full audit report
   ```python
   from governance.tempmemory.provenance import ProvenanceTracker
   tracker = ProvenanceTracker(redis_client=redis)
   report = tracker.generate_audit_report()
   # Save report
   ```

### TTL Management

All Redis keys have TTLs:
- Tempmemory content: 30 days
- Provenance records: 90 days
- Deduplication index: 90 days
- Ingestion results: 90 days

To extend TTL for important records:
```python
redis.expire("key", 90 * 24 * 3600)  # 90 days
```

## References

- **Migration Module**: `src/governance/tempmemory/migration.py`
- **Provenance Module**: `src/governance/tempmemory/provenance.py`
- **Deduplication Module**: `src/governance/tempmemory/deduplication.py`
- **Brain Integration**: `src/governance/tempmemory/brain_integration.py`
- **CLI Script**: `scripts/ops/brain_eval_ingestion.py`
