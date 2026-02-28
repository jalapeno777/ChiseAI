---
name: "chise-swarm-session"
description: "ChiseAI: create/verify/close isolated swarm worktree sessions with Redis leases."
disable-model-invocation: true
---

Use this command before and during any agent-run git work to prevent branch/worktree race conditions.

Prereqs:
- `STORY_ID` (required)
- `AGENT_ID` (required, e.g. `dev`, `quickdev`, `senior-dev`, `merlin`)
- `BRANCH` (required, `feature/*` or `safety/*`)
- `WORKTREE_PATH` (required after session start; absolute path to assigned worktree)
- Optional: `SCOPES` (space-separated repo-relative paths)

1. Start session (once per task)
   - `python3 scripts/swarm/session.py start --story-id "$STORY_ID" --agent "$AGENT_ID" --branch "$BRANCH" --scopes ${SCOPES:-}`
   - Set `WORKTREE_PATH` to the printed `- worktree: ...` path from the start output.
   - Ensure all subsequent commands run from that worktree:
     - `cd "$WORKTREE_PATH"`

2. Verify session (before any git action)
   - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical`
   - For any merge-to-main operation, require authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

3. Run work + tests in the assigned worktree only
   - Run `python3 scripts/swarm/assert_session_context.py --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH"` before tests/lint/git commands.
   - Prefer wrapper:
     - `bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- <command ...>`
   - Use explicit branch in push/PR commands (never use `HEAD` inference).

4. Close session (after merge or handoff)
   - Default behavior (removes worktree after successful close):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --remove-worktree`
   - If intentionally handing off with an open PR and unmerged branch commits:
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --allow-unmerged --remove-worktree`
   - Exception (preserving worktree requires justification):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged` (without --remove-worktree)
     - Document justification: Why is the worktree being preserved? (e.g., "Pending manual verification", "Shared worktree with other agent")
