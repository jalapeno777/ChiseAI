---
name: "chise-pr-automerge"
description: "ChiseAI: standard push -> PR -> auto-merge flow (green CI only). Uses scripts/gitea_pr_automerge.py."
disable-model-invocation: true
---

Use this command to keep autonomous development convergent: every change lands via PR and merges to `main` only after Woodpecker checks are green.

Prereqs:
- Set `GITEA_TOKEN` (PAT) in env.
- Optional: `GITEA_BASE_URL` (defaults to `http://host.docker.internal:3000`), `GITEA_OWNER`, `GITEA_REPO`.

1. Safety gates (must not be on main)
   - `git status -sb`
   - `git branch --show-current`
   - If on `main`: create a feature branch first (no direct commits to `main`).

2. Run local gates
   - Run `.opencode/command/chise-precommit-gates.md`

3. Push branch to Gitea
   - `git push -u gitea HEAD`

4. Open PR and enable auto-merge on green CI
   - `python3 scripts/gitea_pr_automerge.py --head "$(git branch --show-current)" --wait --delete-branch`

5. Sync local main and prune
   - `git switch main`
   - `git pull --ff-only gitea main`
   - `git fetch -p gitea`
   - Delete local feature branch (safe): `git branch -d <branch>`

