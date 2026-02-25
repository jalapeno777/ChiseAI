---
name: "chise-iterloop-close"
description: "ChiseAI: close an iteration (evidence, learnings, Redis close, promote to Qdrant or docs/tempmemories fallback)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Evidence collection
   - Capture: files changed, commands run, test results, and any live validation checks.

2. Redis iterlog close (DB 0)
   - Update: `bmad:chiseai:iterlog:story:<story_id>`
     - `status=completed`
     - `completed_at`
     - `key_decisions` (compact JSON-like string)
     - `learnings` (compact JSON-like string)
   - Refresh TTL to 5 days for the story hash and any `:decisions`/`:learnings` lists.

3. Promote learnings
   - Promote durable decisions/patterns to Qdrant `ChiseAI` collection.
   - If Qdrant is unavailable, write to `docs/tempmemories/` with the same metadata you would store in Qdrant.

4. Cleanup gate
   - Ensure working tree is clean (or explicitly approved to remain dirty).
   - Ensure no untracked secret files (for example `.env`) are present.

5. Worker Completion Handoff Report (workers must provide before marking completed)
   Required fields:
   - `story_id`: Story identifier (e.g., ST-001)
   - `branch`: Feature branch name (e.g., feature/ST-001-description)
   - `head_sha`: Current commit SHA of branch tip
   - `test_summary`: Test results summary (e.g., "pytest: 15 passed, 0 failed")
   - `status_sync_proof`: Output of `python3 scripts/validate_status_sync.py --pr <number>`
   - `blockers`: Any blocking issues or "None"
   
   Before marking `status=completed`, you MUST:
   - Call `chise-release-ownership` to release scope locks
   - Verify all EVIDENCE_REQUIRED from worker contract is documented

