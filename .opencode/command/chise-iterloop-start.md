---
name: "chise-iterloop-start"
description: "ChiseAI: start an iteration (MEM-SCAN, acceptance criteria lock, Redis iterlog start, Qdrant context query)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. MEM-SCAN
   - Locate and read the nearest `AGENTS.md` that governs the files you will touch.
   - Do not edit any files until MEM-SCAN is complete.

2. Identify the story
   - Choose `story_id` (example: `CH-AGENTS-002`) and a short `story_title`.
   - Set `phase` to one of: `analysis`, `planning`, `solutioning`, `implementation`, `testing`.

3. Redis iterlog (DB 0)
   - Create/update: `bmad:chiseai:iterlog:story:<story_id>` with required fields:
     - `story_id`, `story_title`, `phase`, `status=in_progress`, `started_at`
   - Set TTL: `EXPIRE 432000` (5 days)

4. Qdrant context query
   - Run a semantic find for relevant context (project conventions, prior decisions, related story ids).
   - If Qdrant is unavailable, create a fallback note under `docs/tempmemories/` with frontmatter for later import.

5. Acceptance criteria lock
   - Write explicit, testable acceptance criteria BEFORE implementation begins.
   - Store them in the Redis iterlog hash under `acceptance_criteria`.

6. Metacognition kickoff (required)
   - Run `.opencode/command/chise-metacog-start.md`.
   - Ensure iterlog includes `## Metacognitive Predictions` with measurable expected outcomes.
