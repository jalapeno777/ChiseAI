---
name: "chise-skill-backlog-ingest"
description: "ChiseAI: ingest autonomous skills backlog candidates from Redis queue into docs/bmm-workflow-status.yaml with dedupe."
disable-model-invocation: true
---

Run after weekly skills autonomy tick.

1. Ingest candidates
   - Run:
     ```bash
     python3 scripts/ops/ingest_skill_backlog_candidates.py
     ```

2. Dry-run preview
   - Run:
     ```bash
     python3 scripts/ops/ingest_skill_backlog_candidates.py --dry-run
     ```

3. Bounded processing
   - Use `--max-items=<n>` to cap work per run.

Behavior:
- Reads candidates from Redis queue: `bmad:chiseai:skills:backlog:candidates`
- Deduplicates with deterministic backlog IDs
- Appends new entries to canonical backlog in `docs/bmm-workflow-status.yaml`
- Never blocks task execution; this is planning ingestion only

