---
name: "chise-check-ownership"
description: "ChiseAI: check scope ownership before editing (Redis)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Preconditions
   - You MUST have a `story_id` and `agent` (dev/quickdev/senior-dev).
   - You MUST have `SCOPE_GLOBS` (repo-relative paths) for the work item.

2. Check ownership
   - Run:
     - `python3 scripts/iterlog_ops.py check-ownership --story-id=<story_id> --agent=<agent> --scopes <scope1> <scope2> ...`

3. If ownership is missing/mismatched
   - STOP and report back to `jarvis` for rescheduling/re-scoping.
   - Do not edit files until ownership is resolved or re-assigned.

4. Evidence
   - Record the command output under Evidence (iterlog and/or worker report).

