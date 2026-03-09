# Workflow Status Archival System

## Overview

The Workflow Status Archival System is an automated data retention solution that maintains the health and performance of the `docs/bmm-workflow-status.yaml` file by archiving completed stories older than 7 days to a structured archive system.

## Problem Statement

The `docs/bmm-workflow-status.yaml` file has grown to over 6,500 lines containing 206+ stories. This bloated file:

- Slows down CI validation
- Makes manual editing difficult
- Increases risk of merge conflicts
- Complicates workflow status management

## Solution

Archive completed stories older than 7 days to individual YAML files while preserving:

1. **Completion Evidence**: PR numbers, merge commits, dates
2. **High-Value Content**: Acceptance criteria, decisions, lessons learned
3. **Searchability**: Index in Qdrant for semantic search
4. **Restorability**: Full rollback capability

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Status File                      │
│              (Active: <7 days, ~4,500 lines)                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ Daily archival (02:00 UTC)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Archive Pipeline                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Identify   │──▶│   Create     │──▶│   Promote    │      │
│  │  Candidates  │  │   Archive    │  │   to Qdrant  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Story Detail │ │ Archive Index│ │ Qdrant Index │
│   Archives   │ │   (YAML)     │ │  (Vectors)   │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Components

### 1. Archive Old Stories (`scripts/workflow/archive_old_stories.py`)

Main archival script that:
- Identifies eligible stories (>7 days, completed/merged)
- Creates archive documents
- Updates archive index
- Promotes high-value content to Qdrant
- Leans workflow status

### 2. Verification Scripts

- **`verify_archive_completeness.py`**: Ensures no data loss
- **`verify_workflow_integrity.py`**: Validates workflow file structure
- **`identify_archival_candidates.py`**: Finds stories for archival

### 3. Restoration Scripts

- **`restore_from_archive.py`**: Emergency restoration of archived stories
- **`cleanup_old_archives.py`**: Removes archives older than 2 years

### 4. Lean Workflow Status (`scripts/workflow/lean_workflow_status.py`)

Removes archived details from main workflow file while preserving:
- `id`, `status`, `title`
- `pr_number`, `merge_commit`
- `completed_date`, `merged_date`
- `epic_id`

## Archive Document Structure

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
    # Complete original story content preserved
    acceptance_criteria: [...]
    description: "..."
    notes: [...]
    test_results: {...}
    validation_summary: {...}
  
  high_value_extracts:
    # Content promoted to Qdrant
    acceptance_criteria: [...]
    key_decisions: [...]
    lessons_learned: [...]
```

## CI Integration

### Pipeline Steps

```yaml
# .woodpecker/ci.yaml additions

post-merge-archive:
  image: python:3.11
  commands:
    - python3 scripts/workflow/archive_old_stories.py --execute
  when:
    branch: main
    event: [push, cron]
  schedule: "0 2 * * *"  # Daily at 02:00 UTC

archive-verification:
  image: python:3.11
  commands:
    - python3 scripts/workflow/verify_archive_completeness.py
  schedule: "0 3 * * *"  # Daily at 03:00 UTC
```

### Environment Variables

- `ARCHIVE_AGE_DAYS`: Age threshold (default: 7)
- `ARCHIVE_QDRANT_PROMOTION`: Enable Qdrant indexing (default: true)
- `ARCHIVE_BACKUP`: Create backups (default: true)
- `REDIS_URL`: Redis connection URL
- `QDRANT_URL`: Qdrant connection URL

## Migration Plan

See `docs/governance/workflow-archival-migration-plan.yaml` for:

1. **Phase 0**: Preparation (backups, directory structure)
2. **Phase 1**: Analysis (identify candidates)
3. **Phase 2**: Migration (create archives, lean workflow)
4. **Phase 3**: Validation (verify completeness)
5. **Phase 4**: Cleanup (remove temp files, update docs)

## Rollback Plan

### Emergency Full Rollback

```bash
# 1. Stop archival
redis-cli SET bmad:chiseai:workflow:archival:enabled 0

# 2. Alert team
scripts/notify/alert_team.sh "Archival rollback initiated"

# 3. Restore from backup
BACKUP=$(ls -t docs/bmm-workflow-status.yaml.backup.* | head -1)
cp "$BACKUP" docs/bmm-workflow-status.yaml

# 4. Verify
python3 scripts/workflow/verify_workflow_integrity.py
```

### Partial Rollback (Single Story)

```bash
# Restore specific story
python3 scripts/workflow/restore_from_archive.py --story-id ST-XXX
```

## Monitoring

### Redis Metrics

```bash
# Archival statistics
redis-cli HGETALL bmad:chiseai:workflow:archival:stats

# Recent operations
redis-cli LRANGE bmad:chiseai:workflow:archival:log 0 10

# Migration status
redis-cli HGETALL bmad:chiseai:workflow:migration:status
```

### File Size Monitoring

```bash
# Current workflow size
wc -l docs/bmm-workflow-status.yaml

# Archive count
ls docs/archives/workflow-status/story-details/ | wc -l

# Index size
grep -c "story_id:" docs/archives/workflow-status/archive-index.yaml
```

## Retention Policy

| Storage Location | Retention | Description |
|-----------------|-----------|-------------|
| Active Workflow | 7 days | Stories actively being worked |
| Archive Files | 2 years | Individual story archives |
| Qdrant Index | Permanent | High-value content for search |
| Backups | 30 days | Pre-modification backups |

## Security

### Data Protection

- All archives preserve completion evidence
- Hash-based integrity verification
- Backup before any modification
- Immutable archive files (versioned if changed)

### Access Control

- Archive directory: readable by all agents
- Restoration: requires explicit approval
- Cleanup: 2-year retention enforced

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Workflow file size | < 5,000 lines | ~6,500 lines |
| Archive operation | < 5 minutes | TBD |
| Verification | < 2 minutes | TBD |
| Restoration | < 30 seconds | TBD |

## Troubleshooting

### Common Issues

**Issue**: Archive verification fails
```bash
# Check specific story
python3 scripts/workflow/verify_archive_completeness.py --manifest PATH
```

**Issue**: Workflow file too large
```bash
# Force archival
python3 scripts/workflow/archive_old_stories.py --execute --age-days 1
```

**Issue**: Qdrant promotion fails
```bash
# Check Qdrant health
curl http://localhost:6333/healthz

# Retry promotion
python3 scripts/memory/promote_archived_to_qdrant.py --retry
```

## References

- Migration Plan: `docs/governance/workflow-archival-migration-plan.yaml`
- Access Guide: `docs/governance/archive-access-guide.md`
- Archive Index: `docs/archives/workflow-status/archive-index.yaml`
- Scripts: `scripts/workflow/`

## Changelog

### Version 1.0 (2026-03-09)

- Initial implementation
- Migration plan created
- Automation scripts developed
- CI integration designed
