# Workflow Archiving Runbook

## Purpose

This runbook documents the comprehensive data retention and archival process for ChiseAI. It ensures workflow data is properly tiered for operational efficiency while preserving full historical traceability.

## Quick Reference

| Task | Command |
|------|---------|
| Check what would be archived | `python3 scripts/workflow/archive_old_stories.py --dry-run` |
| Archive eligible stories | `python3 scripts/workflow/archive_old_stories.py --execute` |
| Archive specific story | `python3 scripts/workflow/archive_old_stories.py --story-id ST-XXX --execute` |
| Restore from archive | `python3 scripts/workflow/restore_from_archive.py --story-id ST-XXX` |
| Validate references | `python3 scripts/workflow/validate_references.py` |

## Policy Reference

- **Policy Document**: `docs/policy/data_retention_policy.yaml`
- **Retention Period**: 7 days after story completion
- **Archive Location**: `docs/archives/`
- **Qdrant Promotion**: Automatic for P0/P1 stories and anti-patterns

## Retention Tiers

### Tier 1: Active Workflow File
- **Location**: `docs/bmm-workflow-status.yaml`
- **Retention**: Current + 7 days after completion
- **Contents**: Story ID, status, title, epic_id, priority, owner, dates, PR info
- **Target Size**: < 2000 lines

### Tier 2: Archive Documents
- **Location**: `docs/archives/`
- **Retention**: 7 days after completion → indefinite
- **Subdirectories**:
  - `story-details/`: Complete story evidence
  - `epic-summaries/`: Epic-level rollups
  - `monthly-reports/`: Aggregated metrics
  - `workflow-status/`: Monthly snapshots

### Tier 3: Qdrant Searchable Memory
- **Location**: Qdrant vector database (collection: ChiseAI)
- **Retention**: Permanent
- **Contents**: High-value patterns, decisions, anti-patterns
- **Auto-Promotion**: P0/P1 stories, 5+ point stories, anti-patterns

## Legacy Archive Location (Being Deprecated)

```
docs/archives/workflow-status/
├── archive-index.yaml      # Master index with cross-references
├── archive-2026-02.yaml    # February 2026 entries (legacy format)
└── ...                     # Additional monthly archives
```

**Note**: The legacy workflow-status archive format is being replaced by the comprehensive story-details format per the data retention policy.

## How to Access Archived Entries

### 1. By Story ID

```bash
# Search for a specific story across all archives
grep -r "ST-AUTO-CONTROL-001" docs/archives/workflow-status/

# Or check the index first
cat docs/archives/workflow-status/archive-index.yaml | grep "ST-AUTO-CONTROL-001"
```

### 2. By Date Range

```bash
# View February 2026 entries
cat docs/archives/workflow-status/archive-2026-02.yaml
```

### 3. By Epic ID

```bash
# Find all entries for a specific epic
grep -r "epic_id: EP-AUTO-GIT-001" docs/archives/workflow-status/
```

### 4. Using the Index

The `archive-index.yaml` file provides a quick lookup table:

```yaml
archive_index:
  entries:
    - story_id: ST-AUTO-CONTROL-003
      archived_to: archive-2026-02.yaml
      original_timestamp: "2026-02-26T23:55:00Z"
      epic_id: EP-AUTO-GIT-001
```

## How to Add New Archive Entries

### Manual Archive Process

1. **Identify entries to archive:**
   ```bash
   # Find entries older than threshold (e.g., 7 days)
   python3 -c "
   import yaml
   from datetime import datetime, timedelta
   
   with open('docs/bmm-workflow-status.yaml') as f:
       status = yaml.safe_load(f)
   
   threshold = datetime.now() - timedelta(days=7)
   for entry in status['metadata']['recent_changes']:
       ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
       if ts < threshold:
           print(f\"Archive: {entry['timestamp']} - {entry.get('action', 'unknown')}\")
   "
   ```

2. **Move entries to archive file:**
   - Copy the entry to the appropriate monthly archive file
   - Add `archived_from` and `archived_date` fields
   - Remove from active file's `recent_changes` list

3. **Update the index:**
   - Add entry to `archive-index.yaml` with key fields

4. **Validate:**
   ```bash
   yamllint docs/bmm-workflow-status.yaml docs/archives/workflow-status/*.yaml
   ```

### Automated Archive Script

(To be implemented as part of ST-CI-001 improvements)

```bash
# Future: scripts/archive_workflow_status.py
# Will automate the archive process based on retention policy
```

## Traceability Preservation Rules

### Required Fields (MUST preserve)

When archiving, these fields MUST be retained:

| Field | Purpose |
|-------|---------|
| `timestamp` | Original entry timestamp |
| `actor` | Who made the change |
| `action` | What action was taken |
| `description` | Full description |
| `story_id` | Associated story (if any) |
| `epic_id` | Associated epic (if any) |

### Archive-Specific Fields (ADD when archiving)

| Field | Purpose |
|-------|---------|
| `archived_from` | Source file path |
| `archived_date` | When entry was archived |

### Cross-Reference Format

```yaml
# In archive file:
- timestamp: "2026-02-26T23:55:00Z"
  story_id: ST-AUTO-CONTROL-003
  epic_id: EP-AUTO-GIT-001
  archived_from: docs/bmm-workflow-status.yaml
  archived_date: "2026-03-02"

# In index:
entries:
  - story_id: ST-AUTO-CONTROL-003
    archived_to: archive-2026-02.yaml
    original_timestamp: "2026-02-26T23:55:00Z"
    epic_id: EP-AUTO-GIT-001
```

## Index Structure

The `archive-index.yaml` serves as a master lookup table:

```yaml
archive_index:
  version: "1.0"
  created_date: "2026-03-02"
  retention_policy:
    active_file_keep_days: 7
    archive_location: docs/archives/workflow-status/
  
  entries:
    - story_id: <STORY_ID>
      action: <action_name>
      archived_to: <archive_filename>
      original_timestamp: <timestamp>
      epic_id: <EPIC_ID>
      actor: <actor_name>
      description: <brief_description>
```

## Troubleshooting

### Issue: Entry not found in archive

1. Check the index first: `cat docs/archives/workflow-status/archive-index.yaml`
2. Search all archive files: `grep -r "pattern" docs/archives/workflow-status/`
3. Check if entry might still be in active file

### Issue: YAML validation fails

1. Run yamllint: `yamllint docs/archives/workflow-status/*.yaml`
2. Check for indentation issues (use 2 spaces)
3. Verify all required fields are present

### Issue: Traceability broken

1. Verify `story_id` and `epic_id` match between archive and index
2. Check that `archived_from` points to correct source
3. Ensure `original_timestamp` matches the source entry

## Related Files

- `docs/bmm-workflow-status.yaml` - Active workflow status
- `docs/archives/workflow-status/archive-index.yaml` - Master index
- `docs/archives/workflow-status/archive-YYYY-MM.yaml` - Monthly archives

## Change History

| Date | Author | Change |
|------|--------|--------|
| 2026-03-09 | senior-dev | Comprehensive update per data retention policy v1.0 |
| 2026-03-02 | dev | Initial runbook creation for ST-WORKFLOW-001 |

## Related Documentation

- **Data Retention Policy**: `docs/policy/data_retention_policy.yaml`
- **Memory Policy**: `docs/policy/memory_policy.yaml`
- **Workflow Status**: `docs/bmm-workflow-status.yaml`
- **Archive Examples**: `docs/archives/examples/`

## Contact

For issues or questions:
- **Workflow Governance**: @merlin, @jarvis
- **Discord**: #workflow-alerts
