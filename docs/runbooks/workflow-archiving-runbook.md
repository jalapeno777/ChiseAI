# Workflow Status Archiving Runbook

## Purpose

This runbook documents the retention policy and procedures for archiving workflow status entries from `docs/bmm-workflow-status.yaml`.

## Retention Policy

| Policy | Value | Description |
|--------|-------|-------------|
| Active Retention | 4 days | Entries remain in active `recent_changes` for 4 days from current date |
| Archive Location | `docs/archives/workflow-status/` | Archived entries stored in monthly files |
| Traceability | Full preservation | All `epic_id`, `story_id`, and metadata preserved |

### Archive Schedule

- **When to archive**: When entries in `recent_changes` are older than 4 days
- **Archive frequency**: As needed (typically weekly or during sprint cleanup)
- **Archive format**: Monthly YAML files (e.g., `archive-2026-02.yaml`)

## Archive Structure

```
docs/archives/workflow-status/
├── archive-index.yaml      # Master index with cross-references
├── archive-2026-02.yaml    # February 2026 entries
├── archive-2026-03.yaml    # March 2026 entries (created when needed)
└── ...
```

### Index File (`archive-index.yaml`)

The index file maps `story_id` to archive location for quick lookup:

```yaml
archive_index:
  entries:
    - story_id: ST-EXAMPLE-001
      archived_to: archive-2026-02.yaml
      original_timestamp: "2026-02-24T14:30:00Z"
      epic_id: EP-EXAMPLE-001
```

## How to Archive Entries

### Step 1: Identify Entries to Archive

```bash
# Find entries older than 4 days
python3 -c "
import yaml
from datetime import datetime, timedelta

with open('docs/bmm-workflow-status.yaml') as f:
    data = yaml.safe_load(f)

cutoff = datetime.now() - timedelta(days=4)
recent = data['metadata']['recent_changes']

to_archive = [e for e in recent if datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')) < cutoff.replace(tzinfo=None)]
print(f'Entries to archive: {len(to_archive)}')
for e in to_archive:
    print(f'  - {e[\"timestamp\"]}: {e.get(\"action\", \"N/A\")}')
"
```

### Step 2: Move Entries to Archive File

1. Open the appropriate monthly archive file (create if needed)
2. Append entries to the `entries` list with full content preserved
3. Update `archive_metadata.entry_count` and `date_range`

### Step 3: Update Index

Add entries to `archive-index.yaml`:
```yaml
entries:
  - story_id: ST-EXAMPLE-001
    archived_to: archive-2026-02.yaml
    original_timestamp: "2026-02-24T14:30:00Z"
    epic_id: EP-EXAMPLE-001
    actor: jarvis
    action: example_action
```

### Step 4: Update Active File

1. Remove archived entries from `metadata.recent_changes`
2. Update `metadata.last_updated`
3. Add archive reference entry if not present

## How to Find Archived Entries

### By Story ID

```bash
# Search the index for a story_id
grep -A5 "story_id: ST-TARGET-001" docs/archives/workflow-status/archive-index.yaml
```

### By Date Range

```bash
# Check a specific monthly archive
cat docs/archives/workflow-status/archive-2026-02.yaml
```

### By Epic ID

```bash
# Search all archives for an epic
grep -r "epic_id: EP-TARGET-001" docs/archives/workflow-status/
```

## Traceability Rules

1. **Never delete entries** - Only move to archive
2. **Preserve all fields** - Including description, deltas, notes, etc.
3. **Keep links intact** - `epic_id` and `story_id` must remain valid
4. **Maintain index** - Every archived entry must have an index entry

## Validation

After archiving, validate:

```bash
# YAML syntax check
python3 -c "import yaml; yaml.safe_load(open('docs/bmm-workflow-status.yaml'))"
python3 -c "import yaml; yaml.safe_load(open('docs/archives/workflow-status/archive-index.yaml'))"

# Verify index entries match archive
python3 -c "
import yaml
with open('docs/archives/workflow-status/archive-index.yaml') as f:
    index = yaml.safe_load(f)
print(f'Indexed entries: {len(index[\"archive_index\"][\"entries\"])}')
"
```

## Emergency Recovery

If archived entries need to be restored:

1. Find the entry in the archive file
2. Copy the full entry content
3. Insert back into `metadata.recent_changes` in the active file
4. Remove from archive file and index
5. Validate YAML syntax

## Related Documents

- **Active Status**: `docs/bmm-workflow-status.yaml`
- **Archive Location**: `docs/archives/workflow-status/`
- **Ownership Tracking**: Redis key `bmad:chiseai:ownership` -> `docs:workflow-status`

---

*Created by ST-WORKFLOW-001 on 2026-03-02*
