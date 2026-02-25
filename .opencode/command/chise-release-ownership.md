---
name: "chise-release-ownership"
description: "ChiseAI: release scope ownership when work is complete (counterpart to chise-claim-ownership)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Preconditions
   - You MUST have a `story_id` and `agent` (dev/quickdev/senior-dev).
   - You MUST have `SCOPE_GLOBS` (repo-relative paths) that were previously claimed.
   - Verify you are releasing ownership for the correct story/agent combination.

2. Release ownership
   - For each scope path in SCOPE_GLOBS:
     - Convert path to path_slug (lowercase, replace "/" with ":", strip leading "./")
     - Remove the ownership entry from Redis:
       - Use: `redis_state_hdel` with name="bmad:chiseai:ownership" and key=<path_slug>
   - Alternative (if iterlog_ops.py supports it):
     - Run: `python3 scripts/iterlog_ops.py release-ownership --story-id=<story_id> --agent=<agent> --scopes <scope1> <scope2> ...`

3. Verify release
   - Check that ownership entries have been removed:
     - Use: `redis_state_hgetall` with name="bmad:chiseai:ownership"
     - Confirm no entries exist for your story_id/agent scopes
   - If any entries remain, retry the release or report to jarvis.

4. Cleanup related keys (optional but recommended)
   - If this was the last scope for the story, consider cleaning up:
     - `bmad:chiseai:iterlog:story:<story_id>` (story hash)
     - `bmad:chiseai:iterlog:story:<story_id>:decisions` (decisions list)
     - `bmad:chiseai:iterlog:story:<story_id>:learnings` (learnings list)
     - `bmad:chiseai:iterlog:story:<story_id>:incidents` (incidents list)
   - Note: These may be kept for audit purposes; only delete if explicitly requested.

5. Evidence
   - Record the command output under Evidence (iterlog and/or worker report).
   - Note which scopes were released and when.

6. Integration with iterloop-close
   - This command should be called during `chise-iterloop-close` before marking the story as completed.
   - Release ownership AFTER all work is done but BEFORE updating story status to "completed".

## Related Commands

- `chise-claim-ownership` - Claim ownership before starting work
- `chise-check-ownership` - Verify ownership before editing
- `chise-iterloop-close` - Close iteration (calls this command)
