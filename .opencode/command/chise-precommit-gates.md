---
name: "chise-precommit-gates"
description: "ChiseAI: run local pre-commit gates (CI checks, status sync, iterloop compliance). Uses best-available commands in this repo."
disable-model-invocation: true
---

Run these gates before PR/merge. If a referenced script is missing, explicitly note it and run the closest available equivalent.

Required env for story work:
- `STORY_ID`
- `BRANCH`
- `WORKTREE_PATH`

1. Repo sanity
   - `python3 scripts/swarm/assert_session_context.py --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH"`
   - `(cd "$WORKTREE_PATH" && git status -sb)`
   - `(cd "$WORKTREE_PATH" && git branch --show-current)`
   - If this is agent-run story work, verify session:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical`
   - For merge-to-main actions, enforce authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

2. Local CI checks (best available)
   - If `scripts/local-ci-checks.sh` exists, run it in assigned worktree:
     - `bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- bash scripts/local-ci-checks.sh`
   - Otherwise, run the repo's test/lint entry points that exist (for example `pytest`, `ruff`, `black`) and report what you ran.
     - Example:
       - `bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- pytest`

3. Status sync (if present)
   - If `scripts/validate_status_sync.py` exists, run in assigned worktree:
     - `bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- python3 scripts/validate_status_sync.py`

4. Iterloop compliance (if present)
   - If `scripts/validate_iterloop_compliance.py` exists, run:
     - `bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- python3 scripts/validate_iterloop_compliance.py --story-id "$STORY_ID"`

5. Session close anti-drift (required at handoff/finish)
   - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged`
   - If intentionally closing with open PR and branch ahead of main:
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged --allow-unmerged`
