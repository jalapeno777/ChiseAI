---
name: "chise-merlin-pr-sweep"
description: "ChiseAI: Jarvis-triggered Merlin sweep for unmerged branches, PR creation, CI diagnosis, consolidation, and safe prune."
disable-model-invocation: true
---

Use this command when Jarvis finishes a sprint/batch and needs Merlin to reconcile git/Gitea/Woodpecker safely.

Prereqs:

- `AGENT_ID=merlin`
- `GITEA_TOKEN` set
- Optional: `GITEA_BASE_URL` (default http://host.docker.internal:3000), `GITEA_OWNER` (default `craig`), `GITEA_REPO` (default `ChiseAI`)
- Run from an isolated control worktree
- Ensure mapping file exists/updated: `docs/operations/merlin-branch-story-map.json`
  - Mapping values must use accepted story-id patterns (same CI gate as `validate_pr_title.py`): `ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*` (must include a digit).

1. Run the automated sweep wrapper

```bash
python3 scripts/ops/merlin_pr_sweep.py --wait
```

2. Dry-run before merge windows (recommended)

```bash
python3 scripts/ops/merlin_pr_sweep.py --dry-run
```

3. Monitor failures and diagnose deterministically

- Identify failed PR pipelines:
  - `.opencode/command/chise-ci-pr-status.md`
- Diagnose root cause:
  - `.opencode/command/chise-ci-root-cause.md`
- If unresolved or high impact, generate bundle:
  - `.opencode/command/chise-ci-failure-bundle.md`

4. Consolidate when failures are systemic

- If multiple PRs fail for the same shared/main-file issue:
  - Create one consolidation branch from latest `main`.
  - Cherry-pick or merge required unique commits/fixes.
  - Open a single PR for the consolidation branch.
  - Focus only on getting that PR green and merged.
  - Add supersession comments to replaced PRs (required):

```bash
python3 scripts/ops/merlin_pr_sweep.py \
  --consolidation-mode \
  --supersession-pr <consolidation_pr_number> \
  --supersede-pr <old_pr_1> \
  --supersede-pr <old_pr_2>
```

5. Safe prune obsolete branches (local + remote)

- Only prune branches that are merged to `main` or superseded with equivalent merged commit history.

```bash
git branch --merged main | rg -v '(^\\*| main$)' | xargs -r git branch -d
git fetch -p origin
```

- For remote branches, delete only after merged/superseded verification:

```bash
git push origin --delete <branch>
```

6. Report back to Jarvis

- Include:
  - branches scanned
  - PRs opened/updated/closed
  - CI failure root causes (`tool`, `message`, `file:line|rule|test`)
  - consolidation actions taken
  - branches pruned (local/remote)
