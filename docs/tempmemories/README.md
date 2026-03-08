# Temporary Memories

Use this folder to store Redis/Qdrant fallback logs when MCP access is unavailable.

## Format
Create one markdown file per task or decision with YAML frontmatter:

```md
---
project: ChiseAI
scope: <area>
type: decision|pattern|anti-pattern|summary
story_id: <id>
date: YYYY-MM-DD
---

Decisions:
- ...

Learnings:
- ...
```

These files should be manually imported to Redis/Qdrant later.

## Migration

When MCP access to Redis/Qdrant was unavailable, tempmemory files were created with `needs_manual_qdrant_import: true` flags. These files need to be migrated to the proper memory stores.

### Quick Migration

Preview what would be migrated:
```bash
python3 scripts/ops/migrate_tempmemories.py --dry-run
```

Migrate all P0 files (needs_manual_qdrant_import: true):
```bash
python3 scripts/ops/migrate_tempmemories.py --execute --priority P0
```

### Archive Policy

After successful migration, files are moved to:
```
docs/tempmemories/archived/YYYY-MM/
```

Preserved files (never archived):
- `templates/` - Template files for new tempmemories
- `README.md` - This documentation
- `.gitkeep` - Git directory tracking

### Tools

- **Command**: `.opencode/command/chise-tempmemories-migrate.md`
- **Script**: `scripts/ops/migrate_tempmemories.py`

Both support dry-run mode for safe previewing.
