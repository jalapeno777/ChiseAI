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
