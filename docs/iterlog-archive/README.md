# Iterlog Archive

## Purpose

This directory stores archived iteration log entries that have been completed or are no longer active in Redis. Archiving preserves historical iteration data for audit, retrospectives, and long-term trend analysis while keeping the live Redis store lean.

## Directory Structure

```
docs/iterlog-archive/
├── README.md          # This file
├── index.json         # Searchable index of all archived entries
└── 2026-02/           # Monthly buckets (YYYY-MM)
    ├── ST-BT-001.json
    ├── ST-DATA-001.json
    └── ...
```

- **Monthly buckets**: Each subdirectory (`YYYY-MM/`) groups entries by the month they were archived.
- **Entry files**: Individual JSON files named `<story-id>.json`, one per story iteration log.
- **index.json**: A flat index mapping story IDs to archive paths, dates, and summary metadata for fast lookup.

## Searching the Archive

Use `index.json` to locate entries without traversing directories:

```bash
# Find all entries for a story
jq '.entries | map(select(.story_id == "ST-BT-001"))' docs/iterlog-archive/index.json

# Find entries archived in a specific month
jq '.entries | map(select(.archived_month == "2026-02"))' docs/iterlog-archive/index.json
```

For full-text search across entry contents:

```bash
grep -rl "keyword" docs/iterlog-archive/*/
```

## Retention Policy

- Entries are archived from Redis **after 30 days** of completion.
- Archive files are retained indefinitely (no automatic deletion).
- Redis keys under `bmad:chiseai:iterlog:story:*` are purged after successful archive write.
