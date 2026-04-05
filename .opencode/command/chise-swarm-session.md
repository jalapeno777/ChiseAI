---
name: "chise-swarm-session"
description: "ChiseAI: create/verify/close isolated swarm worktree sessions with Redis leases."
disable-model-invocation: true
---

Use this command before and during any agent-run git work to prevent branch/worktree race conditions.

**Important — Repo Startup Lock**: The `start` subcommand acquires an exclusive Redis startup lock (`bmad:chiseai:repo-startup-lock`) with a 300-second TTL while creating the worktree. This prevents concurrent worktree creation when multiple opencode sessions share the same physical repo. If another session is starting, `start` will fail with a clear message. The lock is released automatically after the worktree is ready. If a session crashes mid-startup, the lock auto-expires after 300s or can be force-released with the `unlock` subcommand.

Prereqs:
- `STORY_ID` (required)
- `AGENT_ID` (required, e.g. `dev`, `quickdev`, `senior-dev`, `merlin`)
- `BRANCH` (required, `feature/*` or `safety/*`)
- `WORKTREE_PATH` (required for deterministic verify/close in multi-worktree runs)
- Optional: `SCOPES` (space-separated repo-relative paths)

1. Start session (once per task)
   - `python3 scripts/swarm/session.py start --story-id "$STORY_ID" --agent "$AGENT_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --scopes ${SCOPES:-}`
   - `start` auto-configures `git config --local core.hooksPath .githooks` so repo-managed push guards are active.

2. Verify session (before any git action)
   - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical`
   - `verify` now enforces that feature branches include latest `origin/main` by default.
   - Exceptional bypass only (not normal flow): add `--no-require-up-to-date-main`
   - For any merge-to-main operation, require authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`
   - `verify` also repairs missing/wrong `core.hooksPath` values back to `.githooks`.

3. Push behavior
   - Sync before push (required for feature branches):
     - `git fetch origin --prune`
     - `git rebase origin/main` (or merge `origin/main` if rebase is not appropriate)
   - Standard push: `git push origin "$BRANCH"`
   - The repo-managed `.githooks/pre-push` hook runs `python3 scripts/ci/pre_push_gate.py` automatically.
   - Merlin-only authorized bypass:
     - `git -c chise.prePushBypass=true -c chise.prePushAuthorizedBy="<approver>" -c chise.prePushJustification="<reason>" push origin "$BRANCH"`
   - Bypass is accepted only when the active swarm session agent is `merlin`, and the hook appends an audit line to `_bmad-output/ci/pre-push-bypass.log`.

4. Run work + tests in the assigned worktree only
   - Use explicit branch in push/PR commands (never use `HEAD` inference).

5. Close session (after merge or handoff)
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

6. Unlock startup lock (emergency recovery only)
    - If a session crashed during `start` and the 300s TTL has not expired yet:
      - `python3 scripts/swarm/session.py unlock --force`
    - This force-releases the startup lock regardless of who holds it.
    - Normal operations should never need this — the lock auto-releases after `start` completes and auto-expires after 300s if a crash occurs.

**Parallel Session Safety**: Multiple opencode sessions can safely operate on the same repo as long as each session has its own worktree (created via `start`). Once sessions are in their worktrees, all git operations are fully isolated. The startup lock ensures only one session creates a worktree at a time, preventing the race conditions that would occur if two sessions tried `git worktree add` simultaneously on the same `.git` directory.
