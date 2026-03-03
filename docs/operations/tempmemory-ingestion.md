# Tempmemory Ingestion Operational Guide

## Overview

The Tempmemory Ingestion system is an automated process that promotes relevant knowledge artifacts from `docs/tempmemories/` to structured memory storage systems. It serves as a bridge between human-curated insights and agent-accessible long-term knowledge.

### Purpose

- **Source**: Scans `docs/tempmemories/` for markdown files with YAML frontmatter
- **Destinations**:
  - **Redis** (short-term storage): `bmad:chiseai:tempmemory:content:{story_id}:{filename}` with 30-day TTL
  - **Qdrant** (long-term storage): Vector embeddings for semantic search
- **Integration**: Updates KPIs in BrainEval system from ingested memories

### Why It Exists

Agents create temporary memory artifacts during iteration loops, but these need to be:
1. **Persisted**: Temporary files may be cleaned up or archived
2. **Accessible**: Agents need programmatic access (Redis/Qdrant) vs. file system access
3. **Searchable**: Vector storage enables semantic retrieval across memory artifacts
4. **Tracked**: Ingestion metrics inform brain governance and KPI calculations

## Operational Modes

The Tempmemory Ingestion system can run in two distinct modes depending on your operational requirements:

### Mode 1: Integrated (via MemoryConsolidationScheduler)

**Use when:** You want ingestion to run as part of the consolidation governance flow with daily cadence.

#### Description

In integrated mode, the ingestion system runs as **Step 0** in the `MemoryConsolidationScheduler` workflow. This provides coordinated execution with other governance tasks (memory consolidation, cleanup, rollback management).

#### Cadence

- **Default**: Daily at 2 AM UTC (configurable via `schedule_time` and `schedule_timezone`)
- **Configurable cadence**: `daily` (default), `always` (every consolidation run), or `manual` (only on-demand)

#### How to Enable

Edit the consolidation configuration in `src/governance/consolidation/config.py` or set via environment:

```python
from src.governance.consolidation.config import ConsolidationConfig

scheduler = MemoryConsolidationScheduler(config=ConsolidationConfig(
    run_tempmemory_ingestion=True,  # Enable integrated mode
    tempmemory_ingestion_cadence="daily",  # Run daily
    tempmemory_ingestion_dry_run=False,  # Set True for testing
))
```

Or via environment variables (if using environment-based config):

```bash
export RUN_TEMPMEMORY_INGESTION=true
export TEMPMEMORY_INGESTION_CADENCE=daily
```

#### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `run_tempmemory_ingestion` | bool | `True` | Enable/disable ingestion in consolidation flow |
| `tempmemory_ingestion_dry_run` | bool | `False` | Preview what would be ingested without writing |
| `tempmemory_ingestion_filter_types` | list[str] | `["decision", "pattern", "summary", "anti-pattern"]` | Frontmatter types to ingest (empty list = all types) |
| `tempmemory_ingestion_cadence` | str | `"daily"` | Cadence: `"daily"`, `"always"`, or `"manual"` |

#### When to Use Integrated Mode

- ✅ You want coordinated governance (ingestion + consolidation + cleanup)
- ✅ Daily cadence is sufficient for your use case
- ✅ You prefer centralized management via scheduler
- ✅ You're already using `MemoryConsolidationScheduler` for other tasks

#### When NOT to Use Integrated Mode

- ❌ You need high-frequency ingestion (every 5 minutes)
- ❌ You want ingestion to run independently of consolidation
- ❌ You have frequent updates that need immediate availability

---

### Mode 2: Standalone (via Docker Compose or Cron)

**Use when:** You need high-frequency, independent ingestion runs.

#### Description

In standalone mode, the ingestion system runs independently of the consolidation scheduler. This provides maximum flexibility and the freshest data (5-minute cadence by default).

#### Cadence

- **Default**: Every 5 minutes (configurable via cron schedule)
- **Independent**: Runs regardless of consolidation scheduler state

#### How to Enable

**Option A: Docker Compose Service (Recommended)**

1. Uncomment the `tempmemory-ingestion` service in `infrastructure/docker/docker-compose.scheduler.yml`:

```yaml
# Uncomment this service section
tempmemory-ingestion:
  image: chiseai-brain-scheduler:latest
  container_name: chiseai-tempmemory-ingestion

  # Run cron with ingestion command (every 5 minutes)
  command: >
    sh -c "echo '*/5 * * * * python3 /app/scripts/ops/tempmemory_ingestion_runner.py >> /var/log/tempmemory-ingestion.log 2>&1' | crontab - && cron -f"

  # Network configuration (MUST use chiseai network)
  networks:
    - chiseai

  # Environment variables
  environment:
    # Redis connection
    - REDIS_HOST=chiseai-redis
    - REDIS_PORT=6380
    - REDIS_DB=0

    # Python configuration
    - PYTHONUNBUFFERED=1
    - PYTHONPATH=/app

  # Volume mounts for logs
  volumes:
    - tempmemory-ingestion-logs:/var/log

  # Logging configuration
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"

  # Restart policy
  restart: unless-stopped

  # Resource limits
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 256M
      reservations:
        cpus: '0.1'
        memory: 64M

  # Labels for governance
  labels:
    - "project=chiseai"
    - "service=tempmemory-ingestion"
```

2. Set `run_tempmemory_ingestion: false` in consolidation config (to disable integrated mode):

```python
# src/governance/consolidation/config.py
run_tempmemory_ingestion: False  # Disable integrated mode
```

3. Start the service:

```bash
docker-compose -f infrastructure/docker/docker-compose.scheduler.yml up -d tempmemory-ingestion
```

**Option B: Host Cron with Docker Exec (Simpler Setup)**

Add to your host's crontab (`crontab -e`):

```bash
# Every 5 minutes
*/5 * * * * docker exec chiseai-brain-scheduler python3 /app/scripts/ops/tempmemory_ingestion_runner.py >> /var/log/tempmemory-ingestion.log 2>&1
```

**Option C: Direct Script Execution**

Run the script directly with the appropriate cron schedule:

```bash
*/5 * * * * /home/tacopants/projects/ChiseAI/scripts/ops/tempmemory_ingestion_runner.py >> /var/log/tempmemory-ingestion.log 2>&1
```

#### When to Use Standalone Mode

- ✅ You need high-frequency ingestion (every 5 minutes)
- ✅ You want ingestion to run independently
- ✅ You have frequent updates that need immediate availability
- ✅ You want separate monitoring and lifecycle management

#### When NOT to Use Standalone Mode

- ❌ You want coordinated governance with consolidation
- ❌ Daily cadence is sufficient
- ❌ You prefer centralized management

---

## Docker Configuration

### Network Requirements (MANDATORY)

The tempmemory ingestion system **MUST** use the `chiseai` external network (Terraform-managed) for proper connectivity.

**Network Configuration (chiseai):**
- **Subnet:** `172.27.0.0/16`
- **Gateway:** `172.27.0.1`
- **State Source:** `infrastructure/terraform/terraform.tfstate` (authoritative)

### Redis Connection

#### In-Container Connection (Preferred)

When running the ingestion service as a container on the `chiseai` network:

```bash
# Docker Compose service
environment:
  - REDIS_HOST=chiseai-redis
  - REDIS_PORT=6380
  - REDIS_DB=0
```

#### Host Fallback

When running from the host machine or from outside the `chiseai` network:

```bash
# Host environment or script
export REDIS_HOST=host.docker.internal
export REDIS_PORT=6380
export REDIS_DB=0
```

**Important:** `host.docker.internal` resolves to the host machine from within containers, allowing access to host services.

### Complete Docker Compose Service Definition

```yaml
tempmemory-ingestion:
  image: chiseai-brain-scheduler:latest
  container_name: chiseai-tempmemory-ingestion

  # Run cron with ingestion command (every 5 minutes)
  command: >
    sh -c "echo '*/5 * * * * python3 /app/scripts/ops/tempmemory_ingestion_runner.py >> /var/log/tempmemory-ingestion.log 2>&1' | crontab - && cron -f"

  # Network configuration (MUST use chiseai network)
  networks:
    - chiseai

  # Environment variables
  environment:
    # Redis connection (in-container)
    - REDIS_HOST=chiseai-redis
    - REDIS_PORT=6380
    - REDIS_DB=0

    # Python configuration
    - PYTHONUNBUFFERED=1
    - PYTHONPATH=/app

  # Volume mounts for logs
  volumes:
    - tempmemory-ingestion-logs:/var/log

  # Logging configuration
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"

  # Restart policy
  restart: unless-stopped

  # Resource limits
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 256M
      reservations:
        cpus: '0.1'
        memory: 64M

  # Labels for governance
  labels:
    - "project=chiseai"
    - "service=tempmemory-ingestion"

networks:
  chiseai:
    external: true

volumes:
  tempmemory-ingestion-logs:
    driver: local
```

---

## Configuration Reference

### ConsolidationConfig Fields (Integrated Mode)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `run_tempmemory_ingestion` | bool | `True` | Enable/disable ingestion in consolidation flow |
| `tempmemory_ingestion_dry_run` | bool | `False` | Preview what would be ingested without writing |
| `tempmemory_ingestion_filter_types` | list[str] | `["decision", "pattern", "summary", "anti-pattern"]` | Frontmatter types to ingest (empty list = all types) |
| `tempmemory_ingestion_cadence` | str | `"daily"` | Cadence: `"daily"`, `"always"`, or `"manual"` |

### Environment Variables (Standalone Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `chiseai-redis` (container) / `host.docker.internal` (host) | Redis server hostname |
| `REDIS_PORT` | `6380` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| `PYTHONUNBUFFERED` | `1` | Disable Python output buffering |
| `PYTHONPATH` | `/app` | Python module search path |

### Command-Line Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--dry-run` | - | Show what would be ingested without making changes |
| `--single-file PATH` | - | Ingest specific file |
| `--force` | - | Re-ingest even if already processed (ignores hash check) |
| `--filter-type TYPE` | - | Filter by frontmatter type (can be specified multiple times) |
| `--status` | - | Show ingestion status and exit |
| `--redis-url URL` | - | Redis connection URL (default: from `REDIS_URL` env var) |
| `--tempmemory-path PATH` | - | Path to tempmemories directory (default: `docs/tempmemories`) |

**Valid Filter Types:** `decision`, `pattern`, `summary`, `anti-pattern`

---

## Running Ingestion

### Integrated Mode (via Scheduler)

Ingestion runs automatically as Step 0 of the consolidation workflow when `run_tempmemory_ingestion: true`:

```python
# Example scheduler configuration
scheduler = MemoryConsolidationScheduler(config=ConsolidationConfig(
    run_tempmemory_ingestion=True,
    tempmemory_ingestion_cadence="daily",
))

# Scheduler runs at configured time (default: 2 AM UTC)
scheduler.run()
```

**No additional commands needed** - ingestion runs automatically with consolidation.

### Standalone Mode (via Docker Compose)

Start the standalone service:

```bash
# Start the service
docker-compose -f infrastructure/docker/docker-compose.scheduler.yml up -d tempmemory-ingestion

# View logs
docker logs -f chiseai-tempmemory-ingestion

# Stop the service
docker-compose -f infrastructure/docker/docker-compose.scheduler.yml down tempmemory-ingestion
```

### Standalone Mode (via Cron)

Add to host crontab:

```bash
# Every 5 minutes
*/5 * * * * docker exec chiseai-brain-scheduler python3 /app/scripts/ops/tempmemory_ingestion_runner.py >> /var/log/tempmemory-ingestion.log 2>&1
```

### Manual Mode

Run ingestion on-demand using the CLI:

```bash
# Dry run - preview what would be ingested
python3 scripts/ops/tempmemory_ingestion_runner.py --dry-run

# Single file ingestion
python3 scripts/ops/tempmemory_ingestion_runner.py --single-file docs/tempmemories/ST-XXX-001-decision.md

# Force re-ingest all files
python3 scripts/ops/tempmemory_ingestion_runner.py --force

# Filter by type
python3 scripts/ops/tempmemory_ingestion_runner.py --filter-type decision --filter-type pattern

# Show status
python3 scripts/ops/tempmemory_ingestion_runner.py --status
```

---

## Monitoring

### Redis Keys

| Key | Type | Purpose | TTL |
|-----|------|---------|-----|
| `bmad:chiseai:tempmemory:ingestion:status` | Hash | Last run metadata | Never |
| `bmad:chiseai:tempmemory:ingestion:lock` | String | Active lock | 300s (auto) |
| `bmad:chiseai:tempmemory:ingestion:file_hashes` | Hash | File hash tracking | Never |
| `chise:governance:consolidation:metrics:ingestion` | Hash | Ingestion metrics | Never |

### Status Key Structure

```bash
bmad:chiseai:tempmemory:ingestion:status = {
  "last_run": "2026-03-03T12:34:56Z",
  "files_processed": 15,
  "files_ingested": 12,
  "files_skipped": 3,
  "errors": 0,
  "exit_code": 0,
  "duration_seconds": 2.34
}
```

### Log Locations

```bash
# Docker Compose logs (standalone mode)
docker logs chiseai-tempmemory-ingestion

# Consolidation scheduler logs (integrated mode)
docker logs chiseai-brain-scheduler | grep tempmemory

# Cron redirect (if configured)
/var/log/tempmemory-ingestion.log
```

### Metrics in Redis

Ingestion metrics tracked in consolidation metrics:

```bash
chise:governance:consolidation:metrics:ingestion = {
  "total_runs": 1234,
  "successful_runs": 1230,
  "failed_runs": 4,
  "total_files_processed": 15432,
  "total_files_ingested": 14987,
  "avg_duration_seconds": 2.1,
  "last_success": "2026-03-03T12:34:56Z",
  "last_failure": null
}
```

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | All files processed (some may have errors) |
| 1 | Failure | Critical error (Redis/Qdrant connection, etc.) |
| 2 | Already Running | Another instance has the lock |

---

## Troubleshooting

### Issue: Files Not Being Ingested

**Symptom**: Ingestion runs but 0 files processed.

**Diagnosis**:
```bash
# Check for files
ls -la docs/tempmemories/*.md

# Check frontmatter validity
python3 scripts/ops/tempmemory_ingestion_runner.py --dry-run
```

**Solutions**:
- Ensure files have YAML frontmatter with `type` field
- Verify files are not in `archive/` subdirectory
- Check file permissions (must be readable)

### Issue: Redis Connection Errors

**Symptom**: Exit code 1 with Redis connection error.

**Diagnosis**:
```bash
# Test Redis connectivity from container
docker exec chiseai-tempmemory-ingestion python3 -c "
import redis
r = redis.Redis(host='chiseai-redis', port=6380, db=0)
print(r.ping())
"

# Test from host
redis-cli -h host.docker.internal -p 6380 ping
```

**Solutions**:
- Verify Redis container is running: `docker ps | grep redis`
- Check network connectivity: `docker network inspect chiseai`
- Verify container is on `chiseai` network
- Check environment variables (REDIS_HOST, REDIS_PORT)

### Issue: Qdrant Write Failures

**Symptom**: Files ingested to Redis but Qdrant errors in logs.

**Diagnosis**:
```bash
# Test Qdrant connectivity
docker exec chiseai-tempmemory-ingestion python3 -c "
from qdrant_client import QdrantClient
qc = QdrantClient(host='chiseai-qdrant', port=6334)
print(qc.get_collections())
"
```

**Solutions**:
- Verify Qdrant container is running
- Check collection exists: `tempmemories`
- Verify vector dimensionality matches model (1536 for OpenAI)
- Ensure Qdrant is on `chiseai` network

### Issue: Lock Timeout (Exit Code 2)

**Symptom**: Frequent exit code 2 errors.

**Diagnosis**:
```bash
# Check lock TTL
redis-cli -h chiseai-redis -p 6380 TTL bmad:chiseai:tempmemory:ingestion:lock
```

**Solutions**:
- Verify cron frequency (must be >5 min apart)
- Check for stuck processes: `docker exec chiseai-tempmemory-ingestion ps aux | grep tempmemory`
- Manually clear lock: `redis-cli -h chiseai-redis -p 6380 DEL bmad:chiseai:tempmemory:ingestion:lock`

### Issue: Docker Container Not Starting

**Symptom**: Container fails to start with network errors.

**Diagnosis**:
```bash
# Check container logs
docker logs chiseai-tempmemory-ingestion

# Check network status
docker network inspect chiseai
```

**Solutions**:
- Ensure `chiseai` network exists: `docker network ls | grep chiseai`
- Create network if missing: `docker network create chiseai` (should be created by Terraform)
- Verify network is external: `docker network inspect chiseai | grep "External:"`
- Check for conflicting container names: `docker ps -a | grep tempmemory`

---

## Idempotency Guarantees

The ingestion system is designed to be safely re-runnable without duplication:

### File Hash Tracking

Each processed file's SHA256 hash is stored in Redis:

```
Redis Key: bmad:chiseai:tempmemory:ingestion:file_hashes
Type: Hash
Fields: <story_id>/<filename> -> SHA256 hash
```

### Idempotency Flow

```
1. Scan docs/tempmemories/
2. For each file:
   a. Calculate SHA256 hash
   b. Check against stored hash in Redis
   c. If match found: Skip (already ingested)
   d. If no match: Ingest + update hash
3. Return success/failure status
```

### Force Re-ingestion

Override hash checking with `--force` flag:

```bash
# Re-ingest all files (ignoring hash check)
python3 scripts/ops/tempmemory_ingestion_runner.py --force

# Force re-ingest specific file
python3 scripts/ops/tempmemory_ingestion_runner.py --single-file PATH --force
```

**Warning**: Force re-ingestion creates duplicate entries in Qdrant (non-destructive to Redis).

### Safety Guarantees

- ✅ Multiple concurrent runs prevented by Redis lock (5-min TTL)
- ✅ No data loss on failed runs
- ✅ Failed files don't block successful processing
- ✅ Archive files (`docs/tempmemories/archive/`) automatically skipped

---

## Filtering and Relevance

### Frontmatter Type Filter

Only files with valid YAML frontmatter are processed:

```yaml
---
type: decision  # Must be: decision, pattern, summary, anti-pattern
story_id: ST-XXX-001
created: 2026-03-03
tags: [design, decision]
---

# Decision content here...
```

### Supported Types

| Type | Purpose | Example |
|------|---------|---------|
| `decision` | Architectural/design decisions | Chose PostgreSQL over MongoDB |
| `pattern` | Reusable patterns/conventions | Error handling pattern |
| `summary` | Sprint/project summaries | ST-XXX-001 completion |
| `anti-pattern` | What to avoid | Don't use shared mutable state |

### Filtering Configuration

Filter by specific type:

```bash
# Only ingest decisions
python3 scripts/ops/tempmemory_ingestion_runner.py --filter-type decision

# Only ingest patterns
python3 scripts/ops/tempmemory_ingestion_runner.py --filter-type pattern

# Multiple types (comma-separated or repeat flag)
python3 scripts/ops/tempmemory_ingestion_runner.py --filter-type decision --filter-type pattern
```

### Excluded Files

Files are skipped if:
- ❌ No YAML frontmatter found
- ❌ `type` field missing or invalid
- ❌ Located in `docs/tempmemories/archive/`
- ❌ Filename doesn't match `*.md` pattern

---

## Failure Handling

### Error Recovery Strategy

The system uses **continue-on-error** semantics:

```
For each file:
  try:
    ingest_file(file)
  except Exception as e:
    log_error(file, e)
    continue  # Process next file
```

### Lock Management

```
Redis Key: bmad:chiseai:tempmemory:ingestion:lock
TTL: 300 seconds (5 minutes)
```

- Acquire lock before processing
- Auto-released by TTL (no deadlocks)
- Exit code 2 if lock unavailable

### Logging Strategy

```bash
# Standard output (info)
INFO: Processed 15 files, 2 skipped, 0 errors
INFO: Ingested: ST-XXX-001-decision.md (decision)
INFO: Skipped: ST-YYY-002-summary.md (hash match)

# Standard error (errors)
ERROR: Failed to ingest docs/tempmemories/broken.md: Invalid frontmatter
ERROR: Qdrant write failed: Connection timeout
```

### Retry Strategy

Failed files can be retried individually:

```bash
# Re-ingest failed file (after fixing frontmatter)
python3 scripts/ops/tempmemory_ingestion_runner.py \
  --single-file docs/tempmemories/st-fixed-file.md \
  --force
```

---

## Best Practices

### Frontmatter Schema

Always use consistent frontmatter:

```yaml
---
type: decision  # Required: decision, pattern, summary, anti-pattern
story_id: ST-XXX-001  # Required
created: 2026-03-03  # Recommended
tags: [design, decision]  # Optional
author: jarvis  # Optional
priority: high  # Optional
---

# Content here...
```

### File Naming

Use descriptive, consistent names:

```
✓ ST-XXX-001-architecture-decision.md
✓ ST-YYY-002-error-handling-pattern.md
✓ ST-ZZZ-003-sprint-summary.md

✗ random-decision.md  # Missing story ID
✗ decision.md  # Too generic
✗ ST-XXX-001.DOC  # Wrong extension
```

### Archive Strategy

Move successfully ingested files to archive after verification:

```bash
# Archive processed files
mv docs/tempmemories/ST-XXX-001-*.md docs/tempmemories/archive/

# Archive by date
mkdir -p docs/tempmemories/archive/2026-03
mv docs/tempmemories/2026-03-*.md docs/tempmemories/archive/2026-03/
```

### Choosing Between Modes

**Use Integrated Mode when:**
- You want coordinated governance
- Daily cadence is sufficient
- You prefer centralized management
- You're already using the consolidation scheduler

**Use Standalone Mode when:**
- You need high-frequency ingestion
- You want independent execution
- You have frequent updates
- You prefer separate monitoring

---

## Appendix

### File Structure

```
docs/tempmemories/
├── ST-XXX-001-decision.md
├── ST-YYY-002-pattern.md
├── ST-ZZZ-003-summary.md
└── archive/
    ├── ST-AAA-010-decision.md
    └── ST-BBB-020-pattern.md
```

### Data Flow

```
docs/tempmemories/*.md
       ↓
   [SHA256 Hash]
       ↓
   Redis Check
       ↓ (new/mismatch)
   [Parse Frontmatter]
       ↓
   [Type Filter]
       ↓ (valid)
   Redis Storage (TTL 30 days)
       ↓
   Qdrant Vector Embedding
       ↓
   BrainEval KPI Update
```

### Configuration Files

- **Runner**: `src/governance/tempmemory/ingestion_runner.py`
- **CLI**: `scripts/ops/tempmemory_ingestion_runner.py`
- **Config**: `src/governance/consolidation/config.py`
- **Scheduler**: `src/governance/consolidation/scheduler.py`
- **Docker Compose**: `infrastructure/docker/docker-compose.scheduler.yml`

### Related Documentation

- [BrainEval Scheduler](../evidence/BRAINEVAL-SCHEDULER-DOCKER-VALIDATION-2026-03-03.md)
- [Consolidation Scheduler](../runbooks/consolidation-scheduler.md)
- [Memory Operations](../runbooks/memory-operations.md)
- [Docker Governance](../runbooks/docker-governance.md)
