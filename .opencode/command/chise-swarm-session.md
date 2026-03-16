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
- `WORKTREE_PATH` (required for deterministic verify/close in multi-worktree runs)
- Optional: `SCOPES` (space-separated repo-relative paths)

1. Start session (once per task)
   - `python3 scripts/swarm/session.py start --story-id "$STORY_ID" --agent "$AGENT_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --scopes ${SCOPES:-}`

2. Verify session (before any git action)
   - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical`
   - For any merge-to-main operation, require authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

3. Run work + tests in the assigned worktree only
   - Use explicit branch in push/PR commands (never use `HEAD` inference).

4. Close session (after merge or handoff)
   - `close` now blocks if the worktree is dirty unless you explicitly handle it.
   - Default behavior (removes worktree after successful close):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --remove-worktree`
   - Preferred dirty cleanup: commit/discard changes explicitly, then close.
   - Auto-stash dirty changes before close (last resort only; explicit confirmation required):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --auto-stash-dirty --confirm-stash-last-resort --remove-worktree`
   - Allow dirty close without stashing (not recommended):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --allow-dirty`
   - If intentionally handing off with an open PR and unmerged branch commits:
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --allow-unmerged --remove-worktree`
   - Exception (preserving worktree requires justification):
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged` (without --remove-worktree)
     - Document justification: Why is the worktree being preserved? (e.g., "Pending manual verification", "Shared worktree with other agent")
