# Tempmemory Migration Runbook

> **Story**: ST-MEMORY-003  
> **Purpose**: Operational procedures for tempmemory migration  
> **Last Updated**: 2026-03-01

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Migration Workflow](#migration-workflow)
4. [Scheduling](#scheduling)
5. [Tracking and Reporting](#tracking-and-reporting)
6. [Archive and Reconciliation](#archive-and-reconciliation)
7. [Troubleshooting](#troubleshooting)
8. [Quick Reference](#quick-reference)

---

## Overview

The tempmemory migration system moves temporary memory files from `docs/tempmemories/` to:
- **Redis**: Short-term storage for quick access
- **Qdrant**: Long-term semantic storage

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| Migration Engine | Scan and migrate files | `src/governance/tempmemory/migration.py` |
| Tracker | Track migration status | `src/governance/tempmemory/tracking.py` |
| Archive/Reconciler | Archive and detect issues | `src/governance/tempmemory/archive_reconcile.py` |
| Migration CLI | Manual migration commands | `scripts/ops/tempmemory_migration.py` |
| Scheduler | Docker-based scheduling | `scripts/ops/tempmemory_scheduler.py` |
| Tracker CLI | Status and reporting | `scripts/ops/tempmemory_tracker.py` |

---

## Prerequisites

### Required Infrastructure

1. **Redis Server**
   - Host: `host.docker.internal` (or configured Redis host)
   - Port: `6380`
   - Key prefix: `bmad:chiseai:tempmemory`

2. **Qdrant Vector Database** (optional)
   - Host: `host.docker.internal` (or configured Qdrant host)
   - Port: `6334`
   - Collection: `ChiseAI`

3. **Python Environment**
   - Python 3.11+
   - Dependencies: `redis`, `qdrant-client`, `pyyaml`

### Verification

```bash
# Test Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping

# Test migration script
python3 scripts/ops/tempmemory_migration.py --dry-run
```

---

## Migration Workflow

### Step 1: Dry Run (Recommended First Step)

Always start with a dry run to see what would be migrated:

```bash
python3 scripts/ops/tempmemory_migration.py --dry-run
```

Expected output:
```
============================================================
Dry-Run Migration Report
============================================================
Total files scanned: 85
Would migrate: 85
Would fail: 0
Would skip: 0
Duration: 0.45s
============================================================

Sample files to migrate:
  - docs/tempmemories/2026-02-07-infra-setup.md -> both
  - docs/tempmemories/iterlog-ST-CI-001.md -> both
  ...
```

### Step 2: Run Migration

After verifying the dry run output:

```bash
python3 scripts/ops/tempmemory_migration.py --migrate
```

This will:
1. Scan all files in `docs/tempmemories/`
2. Parse YAML frontmatter
3. Migrate to Redis and/or Qdrant based on file type
4. Update tracking status

### Step 3: Verify Migration

Check the migration status:

```bash
python3 scripts/ops/tempmemory_tracker.py --status
```

Expected output:
```
============================================================
Tempmemory Migration Status
============================================================
Total tracked files: 85

By Status:
  Pending:      0
  In Progress:  0
  Completed:    85
  Failed:       0
  Skipped:      0
============================================================
```

---

## Scheduling

### Docker-Based Scheduling

The scheduler runs as a long-lived process within a Docker container.

#### Option 1: Run Scheduler Continuously

```bash
# Build scheduler image
docker build -t chiseai-tempmemory-scheduler -f docker/tempmemory-scheduler.Dockerfile .

# Run scheduler
docker run -d \
  --name chiseai-tempmemory-scheduler \
  --network chiseai \
  -v $(pwd):/app \
  -e REDIS_HOST=chiseai-redis \
  -e SCHEDULE_INTERVAL=daily \
  chiseai-tempmemory-scheduler
```

#### Option 2: Run Once (for cron integration)

```bash
# Run migration task once
python3 scripts/ops/tempmemory_scheduler.py --once --interval daily
```

#### Option 3: Docker Compose

```yaml
version: '3.8'

services:
  tempmemory-scheduler:
    build:
      context: .
      dockerfile: docker/tempmemory-scheduler.Dockerfile
    container_name: chiseai-tempmemory-scheduler
    networks:
      - chiseai
    volumes:
      - .:/app
    environment:
      - REDIS_HOST=chiseai-redis
      - REDIS_PORT=6380
      - QDRANT_HOST=chiseai-qdrant
      - QDRANT_PORT=6334
      - SCHEDULE_INTERVAL=daily
    restart: unless-stopped
    labels:
      - "project=chiseai"

networks:
  chiseai:
    external: true
```

### Schedule Intervals

| Interval | Description | Use Case |
|----------|-------------|----------|
| `hourly` | Every hour | High-frequency testing |
| `daily` | Every 24 hours | Production standard |
| `weekly` | Every 7 days | Development environments |

### Testing Scheduler Configuration

```bash
python3 scripts/ops/tempmemory_scheduler.py --test
```

This will:
1. Test Redis/Qdrant connectivity
2. Scan tempmemory files
3. Test tracking system
4. Run reconciliation check

---

## Tracking and Reporting

### Check Status

```bash
# Summary status
python3 scripts/ops/tempmemory_tracker.py --status

# Detailed report
python3 scripts/ops/tempmemory_tracker.py --report --type detailed

# Failed only
python3 scripts/ops/tempmemory_tracker.py --report --type failed_only

# Pending only
python3 scripts/ops/tempmemory_tracker.py --report --type pending_only
```

### View Audit Log

```bash
# Last 100 entries
python3 scripts/ops/tempmemory_tracker.py --audit-log

# Last 50 entries
python3 scripts/ops/tempmemory_tracker.py --audit-log --limit 50
```

### List Failed Migrations

```bash
python3 scripts/ops/tempmemory_tracker.py --list-failed
```

### Update File Status

```bash
# Mark a file as completed
python3 scripts/ops/tempmemory_tracker.py \
  --update \
  --file docs/tempmemories/my-file.md \
  --status completed \
  --story ST-MY-STORY-001

# Mark a file as failed with error
python3 scripts/ops/tempmemory_tracker.py \
  --update \
  --file docs/tempmemories/my-file.md \
  --status failed \
  --error "Migration failed: Redis timeout"
```

### Reset Tracking

```bash
# Reset specific file
python3 scripts/ops/tempmemory_tracker.py --reset --file docs/tempmemories/my-file.md

# Reset all tracking (use with caution!)
python3 scripts/ops/tempmemory_tracker.py --reset --all --force
```

---

## Archive and Reconciliation

### Manual Reconciliation

Run reconciliation to detect issues:

```bash
python3 scripts/ops/tempmemory_scheduler.py --once
```

This will detect:
- **Orphaned files**: Exist in tempmemory but not tracked
- **Missing files**: Tracked but don't exist on disk
- **Mismatched files**: Marked completed but not archived

### Archive Completed Files

Completed files are automatically archived during scheduled runs.

To manually archive:

```bash
# This is done automatically by the scheduler
# Archive location: docs/tempmemories/archive/
```

### View Archive Manifest

```python
from governance.tempmemory import TempmemoryArchiveReconciler

reconciler = TempmemoryArchiveReconciler()
manifest = reconciler.get_archive_manifest()
print(f"Archived files: {manifest['total_files']}")
```

---

## Troubleshooting

### Issue: Redis Not Available

**Symptoms:**
```
WARNING - Redis not available: Error 111 connecting to host.docker.internal:6380
```

**Diagnosis:**
```bash
# Test Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping

# Check Redis container
docker ps --filter name=redis

# Check Redis logs
docker logs chiseai-redis
```

**Resolution:**
1. Ensure Redis container is running: `docker start chiseai-redis`
2. Check network connectivity
3. Verify correct host/port in environment variables

---

### Issue: Migration Fails for Specific File

**Symptoms:**
```
Failed: 1
File: docs/tempmemories/problematic-file.md
```

**Diagnosis:**
```bash
# Check file content
cat docs/tempmemories/problematic-file.md

# Check if frontmatter is valid YAML
python3 -c "import yaml; yaml.safe_load(open('docs/tempmemories/problematic-file.md').read().split('---')[1])"
```

**Resolution:**
1. Fix YAML frontmatter syntax
2. Ensure required fields (story_id, type) are present
3. Re-run migration for specific file

---

### Issue: Scheduler Not Running

**Symptoms:**
- No new migrations after scheduled time
- Scheduler status shows "stopped"

**Diagnosis:**
```bash
# Check scheduler status
python3 scripts/ops/tempmemory_scheduler.py --status

# Check if scheduler container is running
docker ps --filter name=tempmemory-scheduler

# Check scheduler logs
docker logs chiseai-tempmemory-scheduler
```

**Resolution:**
1. Restart scheduler container: `docker restart chiseai-tempmemory-scheduler`
2. Check for lock issues: `redis-cli -h host.docker.internal -p 6380 DEL bmad:chiseai:tempmemory:scheduler:lock`
3. Verify Redis connectivity from scheduler container

---

### Issue: Orphaned Files Detected

**Symptoms:**
```
Orphaned files: 5
```

**Diagnosis:**
```bash
# List orphaned files
python3 scripts/ops/tempmemory_scheduler.py --once 2>&1 | grep "orphaned"

# Check if files are tracked
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:tempmemory:migration:status
```

**Resolution:**
1. Run migration to track orphaned files:
   ```bash
   python3 scripts/ops/tempmemory_migration.py --migrate
   ```
2. Or manually track specific files:
   ```bash
   python3 scripts/ops/tempmemory_tracker.py \
     --update --file docs/tempmemories/orphaned-file.md --status pending
   ```

---

### Issue: Files Not Being Archived

**Symptoms:**
```
Mismatched files: 10
Reason: File is marked completed but still in tempmemory
```

**Diagnosis:**
```bash
# Check archive directory
ls -la docs/tempmemories/archive/

# Check file permissions
ls -la docs/tempmemories/
```

**Resolution:**
1. Ensure archive directory exists: `mkdir -p docs/tempmemories/archive`
2. Check write permissions
3. Run scheduler with `--once` to trigger archiving

---

## Quick Reference

### Commands

```bash
# Dry run migration
python3 scripts/ops/tempmemory_migration.py --dry-run

# Run migration
python3 scripts/ops/tempmemory_migration.py --migrate

# Check status
python3 scripts/ops/tempmemory_tracker.py --status

# Generate report
python3 scripts/ops/tempmemory_tracker.py --report --type detailed

# List failed
python3 scripts/ops/tempmemory_tracker.py --list-failed

# Test scheduler
python3 scripts/ops/tempmemory_scheduler.py --test

# Run scheduler once
python3 scripts/ops/tempmemory_scheduler.py --once

# Check scheduler status
python3 scripts/ops/tempmemory_scheduler.py --status
```

### Redis Keys

| Key | Purpose |
|-----|---------|
| `bmad:chiseai:tempmemory:migration:status` | File migration status |
| `bmad:chiseai:tempmemory:migration:summary` | Migration summary |
| `bmad:chiseai:tempmemory:migration:audit` | Audit log |
| `bmad:chiseai:tempmemory:scheduler:state` | Scheduler state |
| `bmad:chiseai:tempmemory:scheduler:lock` | Scheduler lock |
| `bmad:chiseai:tempmemory:content:*` | Migrated content |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `host.docker.internal` | Redis hostname |
| `REDIS_PORT` | `6380` | Redis port |
| `QDRANT_HOST` | `host.docker.internal` | Qdrant hostname |
| `QDRANT_PORT` | `6334` | Qdrant port |
| `SCHEDULE_INTERVAL` | `daily` | Schedule interval |

---

**End of Runbook**
