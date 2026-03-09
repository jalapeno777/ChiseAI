# Workflow Status Archival System - Access Guide

## Overview

The workflow status archival system automatically moves completed stories older than 7 days from the active `docs/bmm-workflow-status.yaml` file to individual archive documents. This keeps the main workflow file lean while preserving all historical data.

## Archive Structure

```
docs/archives/workflow-status/
├── archive-index.yaml          # Master index of all archives
├── story-details/              # Individual story archives
│   ├── ST-XXX-slug-details.yaml
│   └── ST-YYY-slug-details.yaml
└── epic-summaries/             # Epic summary archives
    └── EP-XXX-summary.yaml
```

## How to Access Archived Stories

### Method 1: Archive Index

The master index at `docs/archives/workflow-status/archive-index.yaml` contains metadata for all archived stories:

```yaml
archive_index:
  entries:
    - story_id: ST-XXX
      archived_to: story-details/ST-XXX-slug-details.yaml
      archived_at: "2026-03-09T10:00:00Z"
      epic_id: EP-YYY
```

### Method 2: Direct File Access

Archive files follow the naming convention:
```
{story-id}-{slug}-details.yaml
```

Example:
```
ST-AUTO-001-automation-framework-details.yaml
```

### Method 3: Qdrant Search

High-value content from archived stories is indexed in Qdrant for semantic search:

```python
from qdrant_client import QdrantClient

client = QdrantClient("http://localhost:6333")
results = client.search(
    collection_name="chiseai_workflow_archives",
    query_vector=embedding,
    limit=5
)
```

## Archive Document Format

Each archive document contains:

```yaml
archived_story:
  metadata:
    story_id: "ST-XXX"
    archived_at: "2026-03-09T10:00:00Z"
    archived_by: "archive_old_stories.py"
    archive_version: "1.0"
  
  lean_reference:
    id: "ST-XXX"
    status: "completed"
    pr_number: 123
    merge_commit: "abc123"
    completed_date: "2026-03-01"
    title: "Story Title"
  
  full_details:
    # Complete original story content
    ...
  
  high_value_extracts:
    acceptance_criteria: [...]
    key_decisions: [...]
    lessons_learned: [...]
```

## Scripts Reference

### Archive Old Stories

```bash
# Dry run - preview what would be archived
python3 scripts/workflow/archive_old_stories.py --dry-run

# Execute archival
python3 scripts/workflow/archive_old_stories.py --execute

# Archive specific story
python3 scripts/workflow/archive_old_stories.py --story-id ST-XXX --execute
```

### Verify Archive Completeness

```bash
# Verify all archives are complete
python3 scripts/workflow/verify_archive_completeness.py --strict
```

### Restore From Archive

```bash
# Restore specific story
python3 scripts/workflow/restore_from_archive.py --story-id ST-XXX

# Restore all archived stories
python3 scripts/workflow/restore_from_archive.py --all
```

### Identify Candidates

```bash
# Find stories eligible for archival
python3 scripts/workflow/identify_archival_candidates.py --age-days 7
```

## Automation Schedule

- **Daily at 02:00 UTC**: Auto-archive stories older than 7 days
- **Daily at 03:00 UTC**: Verify archive integrity
- **Weekly on Sunday**: Clean up archives older than 2 years
- **Weekly on Monday**: Generate archive report

## Emergency Procedures

### Rollback

If archival causes issues:

```bash
# Stop archival automation
redis-cli SET bmad:chiseai:workflow:archival:enabled 0

# Restore from backup
cp docs/bmm-workflow-status.yaml.backup.YYYYMMDD docs/bmm-workflow-status.yaml

# Or restore specific story
python3 scripts/workflow/restore_from_archive.py --story-id ST-XXX
```

### Data Loss Recovery

If archive files are missing:

1. Check backup files: `ls docs/bmm-workflow-status.yaml.backup.*`
2. Restore from most recent backup
3. Re-run archival with verification

## Retention Policy

- **Active workflow**: Stories < 7 days old
- **Archive storage**: 2 years
- **Qdrant index**: Permanent (for high-value content)

## Monitoring

### Redis Metrics

```bash
# Check archival statistics
redis-cli HGETALL bmad:chiseai:workflow:archival:stats

# Check recent archival log
redis-cli LRANGE bmad:chiseai:workflow:archival:log 0 10
```

### File Size Targets

- Workflow status target: < 5,000 lines
- Warning threshold: 6,000 lines
- Current size: Check with `wc -l docs/bmm-workflow-status.yaml`

## Troubleshooting

### Story Not Found in Archive

1. Check archive index: `grep "ST-XXX" docs/archives/workflow-status/archive-index.yaml`
2. Search story-details directory: `ls docs/archives/workflow-status/story-details/ | grep ST-XXX`
3. Check if story was ever archived in Redis log

### Archive Verification Fails

1. Run verification with details: `python3 scripts/workflow/verify_archive_completeness.py`
2. Check for missing files
3. Restore from backup if needed

### Workflow File Too Large

1. Run archival: `python3 scripts/workflow/archive_old_stories.py --execute`
2. Check size: `wc -l docs/bmm-workflow-status.yaml`
3. Verify integrity: `python3 scripts/workflow/verify_workflow_integrity.py`

## Support

For issues with the archival system:

1. Check this guide
2. Review migration plan: `docs/governance/workflow-archival-migration-plan.yaml`
3. Check Redis logs: `redis-cli LRANGE bmad:chiseai:workflow:archival:log 0 20`
4. Contact: ops-team
