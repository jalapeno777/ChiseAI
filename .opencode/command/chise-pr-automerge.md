---
name: "chise-pr-automerge"
description: "ChiseAI: Merlin-only exceptional PR recovery flow (normal PR creation is push-triggered)."
disable-model-invocation: true
---

Use this command only for exceptional Merlin-managed PR recovery operations (auto-PR outage/manual override/backfill). Normal PR creation must come from push-triggered automation in `.woodpecker/pr-auto-flow.yaml`.

Prereqs:
- Set `GITEA_TOKEN` (PAT) in env.
- For autonomous review-required merges: set `GITEA_REVIEW_TOKEN` (PAT for a separate bot user that can submit PR reviews).
- Optional: `GITEA_BASE_URL` (defaults to `http://host.docker.internal:3000`), `GITEA_OWNER`, `GITEA_REPO`.
- Set `STORY_ID` (required). Example: `export STORY_ID=ST-NS-001`
  - Accepted patterns include: `ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*` (must contain a digit).
- Set `BRANCH` (required). Example: `export BRANCH=feature/ST-NS-001-my-change`
- Set `AGENT_ID=merlin` (required; non-Merlin PR submission is blocked by script policy).
- Set `WORKTREE_PATH` (required). Example: `export WORKTREE_PATH=/tmp/worktrees/ST-NS-001-merlin`
- Ensure a swarm session exists for this branch:
  - `python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical`
 - Optional helper to derive `STORY_ID` from branch when omitted:
   - `export STORY_ID="$(python3 -c 'import re,os; b=os.environ.get(\"BRANCH\",\"\").upper(); m=re.search(r\"(?:ST|CH|FT|REWARD|REPO|SAFETY|BRANCH|PAPER|RECON)(?:-[A-Z0-9]+){1,}\", b); print(m.group(0) if m else \"\")')"`

1. Safety gates (must not be on main)
   - `git status -sb`
   - `git branch --show-current`
   - If on `main`: create a feature branch first (no direct commits to `main`).

2. Run local gates
   - Run `.opencode/command/chise-precommit-gates.md`

3. Push branch to Gitea (if needed)
   - `git push -u gitea "$BRANCH"`

4. Open PR (no merge side effects)
   - `python3 scripts/gitea_pr_automerge.py --story-id "$STORY_ID" --head "$BRANCH"`

5. Explicit merge (opt-in)
   - If approvals are required, have the review bot approve first:
     - `.opencode/agent/GitReviewBot.md` (review) + `python3 scripts/gitea_pr_review.py --pr <num> --state APPROVED`
   - Then run:
     - `python3 scripts/gitea_pr_automerge.py --story-id "$STORY_ID" --head "$BRANCH" --wait --enable-automerge --delete-branch`

6. Non-blocking mode for Merlin reconcile windows
   - Resolve PR number from Gitea UI/API and export it:
     - `export PR_NUMBER=<gitea-pr-number>`
   - Get head SHA:
     - `HEAD_SHA=$(git rev-parse "$BRANCH")`
   - Enqueue for reconcile loop:
     - `python3 scripts/ops/merge_reconciler.py enqueue --story-id "$STORY_ID" --branch "$BRANCH" --pr-number "$PR_NUMBER" --head-sha "$HEAD_SHA" --queued-by "${AGENT_ID:-jarvis}"`
   - Continue development in your assigned worktree; Merlin performs bounded reconcile ticks and merges on green.

7. Sync local main and prune
   - `git switch main`
   - `git pull --ff-only gitea main`
   - `git fetch -p gitea`
   - Delete local feature branch (safe): `git branch -d <branch>`
   - Close swarm session with anti-drift check:
     - `python3 scripts/swarm/session.py close --worktree-path "$WORKTREE_PATH" --enforce-merged`
