---
name: "chise-tempmemories-migrate"
description: "Migrate tempmemory files to Redis/Qdrant with verification and archival"
disable-model-invocation: true
---

Migrate temporary memory files from docs/tempmemories/ to Redis and Qdrant with tracking and archival.

## Overview

This command moves temporary memory files to persistent storage:
- **Redis**: Stores iterlog files as hashes with TTL (key: `bmad:chiseai:iterlog:story:*`)
- **Qdrant**: Stores all valid files for semantic search

Files are classified by priority:
- **P0**: Files with `needs_manual_qdrant_import: true` (highest priority)
- **P1**: Files with `needs_manual_import: true` (legacy flag)
- **P2**: Valid frontmatter without import flags
- **SKIP**: Protected files (templates, README, .gitkeep, archived, non-markdown)

## Prerequisites

Before running this command, ensure:
1. **Redis is available**: `redis-cli -h host.docker.internal -p 6380 ping`
2. **Qdrant is available**: Check container status `docker ps --filter name=chiseai-qdrant`
3. **Network connectivity**: Containers should be on `chiseai` network

## Usage Examples

### Dry Run (Preview What Will Be Migrated)
```bash
python3 scripts/ops/migrate_tempmemories.py --dry-run
```

### Execute Migration (No Archival)
```bash
python3 scripts/ops/migrate_tempmemories.py --execute
```

### Execute Migration with Cleanup (Archive After Success)
```bash
python3 scripts/ops/migrate_tempmemories.py --execute --cleanup
```

### Migrate Specific Story
```bash
python3 scripts/ops/migrate_tempmemories.py --execute --story ST-XXX-001
```

### Migrate Only P0 Priority Files
```bash
python3 scripts/ops/migrate_tempmemories.py --execute --priority P0
```

### Dry Run for Specific Story
```bash
python3 scripts/ops/migrate_tempmemories.py --dry-run --story ST-XXX-001
```

### Verbose Output
```bash
python3 scripts/ops/migrate_tempmemories.py --execute --verbose
```

### Cleanup Only (Archive Already Migrated Files)
```bash
python3 scripts/ops/migrate_tempmemories.py --cleanup
```

## Safety Warnings

### ⚠️ ALWAYS RUN DRY-RUN FIRST
Always start with `--dry-run` to preview what will be migrated before using `--execute`.

### ⚠️ CLEANUP IS IRREVERSIBLE
The `--cleanup` flag moves files to `docs/tempmemories/archived/YYYY-MM/` after successful migration. This action cannot be undone without manual file restoration.

### ⚠️ PROTECTED FILES ARE NEVER MIGRATED
The following files/patterns are explicitly skipped:
- `templates/` directory
- `README.md`
- `.gitkeep`
- `archived/` directory
- Non-markdown files (`.txt`, `.json`, `.yaml`, `.yml`)

### ⚠️ IDEMPOTENCY IS ENFORCED
Files are tracked by content signature in Redis. Already-migrated files are automatically skipped based on signature matching.

## Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview migration without making changes (default) |
| `--execute` | Actually perform migrations (writes to Redis and Qdrant) |
| `--cleanup` | Archive successfully migrated files after migration |
| `--story ID` | Migrate only files for specific story ID (e.g., ST-XXX-001) |
| `--priority {P0,P1,P2}` | Filter by priority level |
| `--verbose, -v` | Enable detailed output |
| `--backup` | Create backup before archiving (only with --cleanup) |

## Expected Output

### Console Summary
```
======================================================================
MIGRATION EXECUTE MODE
Writes will be made to Redis and Qdrant!
======================================================================

Scanning docs/tempmemories/...
Found 12 files:
  P0 (needs_qdrant_import): 2
  P1 (needs_import): 3
  P2 (valid_frontmatter): 5
  SKIP: 2

[PROCESSING] my-file.md (Priority: P0)
  Story ID: ST-XXX-001
  [REDIS] OK: Successfully migrated to Redis key: bmad:chiseai:iterlog:story:ST-XXX-001
  [QDRANT] OK: Successfully stored in Qdrant: my-file.md
  [ARCHIVE] OK: Archived to: docs/tempmemories/archived/2026-03/my-file.md

======================================================================
MIGRATION SUMMARY
======================================================================
Files attempted:  5
Succeeded:        5
Failed:           0
Skipped:          2
Already migrated: 5

Full report saved to: migration_report.json
```

### JSON Report Format
When `--execute` is used, a `migration_report.json` file is generated:

```json
{
  "timestamp": "2026-03-08T12:00:00.000000+00:00",
  "mode": "execute",
  "cleanup": true,
  "stats": {
    "attempted": 5,
    "succeeded": 5,
    "failed": 0,
    "skipped": 2,
    "already_migrated": 5
  },
  "redis_keys": [
    "bmad:chiseai:iterlog:story:ST-XXX-001",
    "bmad:chiseai:iterlog:story:CH-XXX-002"
  ],
  "failed_files": [],
  "archive_location": "docs/tempmemories/archived/2026-03"
}
```

## Rollback Instructions

### Restoring Archived Files
If you need to restore a file from the archive:

```bash
# Move file from archive back to tempmemories
mv docs/tempmemories/archived/2026-03/my-file.md docs/tempmemories/

# Reset the signature to allow re-migration
# Edit .migration_signatures.json and remove the entry for that file

# Re-migrate (optional, if you want to re-import)
python3 scripts/ops/migrate_tempmemories.py --execute --story ST-XXX-001
```

### Clearing Redis Keys
Redis keys automatically expire after 5 days (TTL). To manually delete:

```bash
# Delete specific story key
redis-cli -h host.docker.internal -p 6380 DEL bmad:chiseai:iterlog:story:ST-XXX-001

# Delete all signatures (allows re-migration of everything)
redis-cli -h host.docker.internal -p 6380 DEL bmad:chiseai:migration:signatures
```

### Clearing Qdrant Records
To delete records from Qdrant, you'll need to:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="host.docker.internal", port=6334)

# Delete by filter (e.g., specific story_id)
client.delete(
    collection_name="ChiseAI",
    points_selector=models.Filter(
        must=[
            models.FieldCondition(
                key="story_id",
                match=models.MatchValue(value="ST-XXX-001")
            )
        ]
    )
)

# Delete all migrated records (use with caution)
client.delete(
    collection_name="ChiseAI",
    points_selector=models.Filter(
        must=[
            models.FieldCondition(
                key="migrated_at",
                match=models.MatchValue(value="*")  # Match all with migrated_at field
            )
        ]
    )
)
```

## Troubleshooting

### "Redis not available"
**Symptoms**: Redis connection errors during migration

**Solutions**:
- Check Redis connectivity: `redis-cli -h host.docker.internal -p 6380 ping`
- Verify Redis container running: `docker ps --filter name=chiseai-redis`
- Check network: Ensure containers on `chiseai` network
- Verify environment variables: `REDIS_HOST` and `REDIS_PORT`

**Fallback**: Migration continues to Qdrant only if Redis is unavailable

### "Qdrant not available"
**Symptoms**: Qdrant connection errors

**Solutions**:
- Check Qdrant container: `docker ps --filter name=chiseai-qdrant`
- Verify port 6334 is accessible: `curl http://host.docker.internal:6334`
- Check Qdrant collection exists: `python3 scripts/ops/migrate_tempmemories.py --verbose`

**Fallback**: Iterlog files still migrate to Redis; other files are skipped

### "Migration failed for specific file"
**Symptoms**: Individual file migration failures

**Solutions**:
- Check file permissions: `ls -la docs/tempmemories/your-file.md`
- Validate YAML frontmatter format
- Verify story_id field exists for iterlog files
- Check for special characters or encoding issues

**Recovery**: Fix the issue, then re-run with `--story <ID>` flag

### High failure rate
**Symptoms**: Multiple files failing to migrate

**Solutions**:
- Run with `--verbose` for detailed error messages
- Check Redis/Qdrant capacity and connectivity
- Verify file encoding is UTF-8
- Review batch sizes in migration engine

### "File already migrated"
**Symptoms**: Files being skipped due to existing signature

**Solutions**:
- This is expected behavior for idempotency
- To force re-migration, delete the signature from `.migration_signatures.json`
- Or delete the Redis signature key: `redis-cli -h host.docker.internal -p 6380 HDEL bmad:chiseai:migration:signatures <signature>`

### Archive directory not created
**Symptoms**: Files not being archived after successful migration

**Solutions**:
- Check write permissions: `ls -la docs/tempmemories/`
- Ensure parent directories exist
- Verify `--cleanup` flag was specified
- Check for permission errors in verbose output

### JSON report not generated
**Symptoms**: No `migration_report.json` file created

**Solutions**:
- Report is only generated with `--execute` flag
- Check working directory permissions
- Verify script completed without errors
- Check for error messages in verbose output

## Redis Schema

Migration uses these Redis keys:

### Iterlog Storage (for story tracking)
```
Key: bmad:chiseai:iterlog:story:<story_id>
Type: Hash
TTL: 432000 seconds (5 days)
Fields:
  - story_id: Story identifier
  - story_title: Story title from frontmatter
  - phase: Current phase
  - status: Story status
  - started_at: Start timestamp
  - priority: Migration priority (P0/P1/P2)
  - migrated_at: Migration timestamp
  - migration_signature: Content hash for idempotency
```

### Signature Tracking (for idempotency)
```
Key: bmad:chiseai:migration:signatures
Type: Hash
TTL: 1728000 seconds (20 days)
Fields:
  - <signature>: JSON metadata with story_id, source, migrated_at
```

### Local Fallback Cache
```
File: .migration_signatures.json
Type: JSON object
Purpose: Fallback when Redis unavailable
Format: { "<signature>": { "story_id": "...", "source": "...", "migrated_at": "..." } }
```

## Priority Classification

Files are classified based on frontmatter:

### P0 (Highest Priority)
- Has `needs_manual_qdrant_import: true`
- Requires immediate migration to Qdrant

### P1 (High Priority)
- Has `needs_manual_import: true` (legacy flag)
- Important for knowledge retention

### P2 (Standard Priority)
- Valid frontmatter (has `story_id`, `type`, etc.)
- No import flags needed

### SKIP (Never Migrated)
- Files in `templates/` directory
- `README.md`, `.gitkeep` files
- Files in `archived/` directory
- Non-markdown files (`.txt`, `.json`, `.yaml`, `.yml`)
- Files without valid frontmatter

## Related Commands

- `chise-iterloop-start.md` - Start iteration loop (creates tempmemories)
- `chise-iterloop-close.md` - Close iteration loop (promotes to Serena memory)
- `chise-swarm-session.md` - Session management for worktrees
- `chise-sprint-cleanup.md` - Pre-sprint cleanup routine

## Operational Cadence

Recommended migration schedule for production environments:

### Weekly Dry-Run (Every Monday)
Preview what would be migrated without making changes:
```bash
# Weekly preview - see what's pending migration
python3 scripts/ops/migrate_tempmemories.py --dry-run --priority P0
python3 scripts/ops/migrate_tempmemories.py --dry-run --priority P1
```

**Purpose**: Monitor accumulation of tempmemory files and identify P0 items needing attention.

### Bi-Weekly P0 Cleanup (1st and 15th of each month)
Execute migration for P0 priority files (highest priority - needs_manual_qdrant_import):
```bash
# Migrate only P0 files with archival
python3 scripts/ops/migrate_tempmemories.py --execute --priority P0 --cleanup

# Verify migration succeeded
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:iterlog:story:*'
```

**Purpose**: Keep high-priority tempmemories (needs_manual_qdrant_import) from accumulating.

### Monthly Full Audit (Last Friday of each month)
Run comprehensive audit and migrate remaining files:
```bash
# 1. Generate audit report first
python3 scripts/ops/migrate_tempmemories.py --dry-run --all-priorities > /tmp/migration_audit.json

# 2. Review counts
# 3. Execute if counts look reasonable
python3 scripts/ops/migrate_tempmemories.py --execute --all-priorities --cleanup

# 4. Generate post-migration evidence
# (see Post-Migration Audit section below)
```

### Quarterly Deep Clean
Archive old files and verify data integrity:
```bash
# Verify Qdrant collection health
curl http://host.docker.internal:6334/collections/ChiseAI

# Check Redis key TTLs
redis-cli -h host.docker.internal -p 6380 --eval scripts/check_ttl.lua

# Review archived files older than 90 days
find docs/tempmemories/archived -type f -mtime +90 -ls
```

## Post-Migration Audit

After any `--execute` migration, generate an audit report:

```bash
# Run migration and capture output
python3 scripts/ops/migrate_tempmemories.py --execute --priority P0 --cleanup | tee /tmp/migration_output.json

# Verify Redis keys exist
redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:iterlog:story:*' | head -5

# Sample Qdrant retrieval
python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='host.docker.internal', port=6334)
results = client.search(
    collection_name='ChiseAI',
    query_vector=[0.0] * 384,
    limit=5,
    with_payload=True
)
for r in results:
    print(f'Score: {r.score}, Story: {r.payload.get(\"story_id\", \"N/A\")}')
"
```

Save the audit evidence to `docs/evidence/TEMPMEMORY-MIGRATION-AUDIT-YYYY-MM-DD.md`.

## Best Practices

1. **Always dry-run first**: Preview migration before executing
2. **Run per story**: Use `--story` flag for incremental migration
3. **Monitor failures**: Check `migration_report.json` for failed files
4. **Keep backups**: Use `--backup` flag when cleaning up
5. **Verify after migration**: Check Redis and Qdrant for migrated content
6. **Clean up regularly**: Use `--cleanup` to keep tempmemories directory clean
