---
name: "chise-claim-ownership"
description: "ChiseAI: claim scope ownership for parallel work (Redis preferred; tempmemories fallback)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Preconditions
   - You MUST have a `story_id` and `agent` (dev/quickdev/senior-dev).
   - You MUST have `SCOPE_GLOBS` (repo-relative paths) for the work item.

2. Claim ownership
   - Run:
     - `python3 scripts/iterlog_ops.py claim-ownership --story-id=<story_id> --agent=<agent> --scopes <scope1> <scope2> ...`
   - If the command reports an ownership conflict, STOP and report back to `jarvis` (do not proceed with edits).

3. Evidence
   - Record the command output under Evidence (iterlog and/or worker report).

