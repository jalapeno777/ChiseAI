---
name: "chise-pr-automerge"
description: "ChiseAI: standard push -> PR -> auto-merge flow (green CI only). Uses scripts/gitea_pr_automerge.py."
disable-model-invocation: true
---

Use this command to keep autonomous development convergent: every change lands via PR and merges to `main` only after Woodpecker checks are green.

Prereqs:
- Set `GITEA_TOKEN` (PAT) in env.
- For autonomous review-required merges: set `GITEA_REVIEW_TOKEN` (PAT for a separate bot user that can submit PR reviews).
- Optional: `GITEA_BASE_URL` (defaults to `http://host.docker.internal:3000`), `GITEA_OWNER`, `GITEA_REPO`.
- Set `STORY_ID` (required). Example: `export STORY_ID=ST-NS-001`
- Set `BRANCH` (required). Example: `export BRANCH=feature/ST-NS-001-my-change`
- Set `AGENT_ID=jarvis` (required for main-merge authority).
- Ensure a swarm session exists for this branch:
  - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

1. Safety gates (must not be on main)
   - `git status -sb`
   - `git branch --show-current`
   - If on `main`: create a feature branch first (no direct commits to `main`).

2. Run local gates
   - Run `.opencode/command/chise-precommit-gates.md`

3. Push branch to Gitea
   - `git push -u gitea "$BRANCH"`

4. Open PR and enable auto-merge on green CI
   - If approvals are required, have the review bot approve first:
     - `.opencode/agent/GitReviewBot.md` (review) + `python3 scripts/gitea_pr_review.py --pr <num> --state APPROVED`
   - Then run:
     - `python3 scripts/gitea_pr_automerge.py --story-id "$STORY_ID" --head "$BRANCH" --wait --delete-branch`

5. Non-blocking mode for swarm throughput (recommended for busy merge windows)
   - Resolve PR number from Gitea UI/API and export it:
     - `export PR_NUMBER=<gitea-pr-number>`
   - Get head SHA:
     - `HEAD_SHA=$(git rev-parse "$BRANCH")`
   - Enqueue for Jarvis reconcile loop:
     - `python3 scripts/ops/merge_reconciler.py enqueue --story-id "$STORY_ID" --branch "$BRANCH" --pr-number "$PR_NUMBER" --head-sha "$HEAD_SHA" --queued-by "${AGENT_ID:-jarvis}"`
   - Continue development in your assigned worktree; Jarvis performs bounded reconcile ticks and merges on green.

6. Sync local main and prune
   - `git switch main`
   - `git pull --ff-only gitea main`
   - `git fetch -p gitea`
   - Delete local feature branch (safe): `git branch -d <branch>`
   - Close swarm session with anti-drift check:
     - `python3 scripts/swarm/session.py close --enforce-merged`
