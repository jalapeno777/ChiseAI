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
- Optional: `SCOPES` (space-separated repo-relative paths)

1. Start session (once per task)
   - `python3 scripts/swarm/session.py start --story-id "$STORY_ID" --agent "$AGENT_ID" --branch "$BRANCH" --scopes ${SCOPES:-}`

2. Verify session (before any git action)
   - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --check-canonical`
   - For any merge-to-main operation, require authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

3. Run work + tests in the assigned worktree only
   - Use explicit branch in push/PR commands (never use `HEAD` inference).

4. Close session (after merge or handoff)
   - `python3 scripts/swarm/session.py close --enforce-merged`
   - If intentionally handing off with an open PR and unmerged branch commits:
     - `python3 scripts/swarm/session.py close --enforce-merged --allow-unmerged`
   - Optional cleanup: `python3 scripts/swarm/session.py close --remove-worktree`
