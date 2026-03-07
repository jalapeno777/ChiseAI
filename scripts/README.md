# GridAI Scripts

This directory contains utility scripts for the GridAI project.

## Available Scripts

### validate_status_sync.py

Validates synchronization between workflow status files and implementation state.

**Purpose:**
- Validates YAML parsing for `docs/bmm-workflow-status.yaml`
- Validates YAML parsing for `docs/validation/validation-registry.yaml`
- Validates story ID consistency between files
- Enforces allowed status vocabulary
- Returns appropriate exit codes (0=success, 1=errors, 2=warnings)

**Usage:**
```bash
python scripts/validate_status_sync.py
python scripts/validate_status_sync.py --full  # Weekly audit mode
```

**Status Vocab Enforced:**
- Workflow status: `planned|in_progress|completed|blocked|deprecated`
- Validation status: `planned|in_progress|validated|blocked|deprecated`

### validate_iterloop_compliance.py

Validates iteration-loop compliance using repo-checkable artifacts under `docs/tempmemories/` (CI-safe fallback when Redis/Qdrant are not reachable).

**Usage:**
```bash
python3 scripts/validate_iterloop_compliance.py
python3 scripts/validate_iterloop_compliance.py --story-id=CH-PRD-CI-ALIGN-001
```

### ci/validate_swarm_context.py

Validates swarm branch/ref context in CI/local gates.

**Usage:**
```bash
python3 scripts/ci/validate_swarm_context.py
```

### iterlog_ops.py

Helper to reduce hand-rolled Redis operations for parallel execution safety.

- Claim scope ownership (Redis; markdown fallback):
  - `python3 scripts/iterlog_ops.py claim-ownership --story-id=ST-XXX --agent=dev --scopes src/foo docs/bar`
- Check ownership (Redis only):
  - `python3 scripts/iterlog_ops.py check-ownership --story-id=ST-XXX --agent=dev --scopes src/foo`
- Append incident (Redis list + markdown fallback):
  - `python3 scripts/iterlog_ops.py append-incident --story-id=ST-XXX --text "symptom: ..."`
- Append insight packet block (markdown fallback):
  - `python3 scripts/iterlog_ops.py append-insight-packet --story-id=ST-XXX --text "INSIGHT_PACKET ..."`
- Append Aria decision block (markdown fallback):
  - `python3 scripts/iterlog_ops.py append-aria-decision --story-id=ST-XXX --text "ARIA_DECISION ..."`
- Archive rejected insight (Redis + markdown fallback):
  - `python3 scripts/iterlog_ops.py archive-rejected-insight --story-id=ST-XXX --issue "..." --reason-rejected "..." --decision REJECT --scope-context "..." --evidence-signature "sig:..."`

### validation/validate_insight_governance.py

Validates orchestrator insight-governance conformance from iterlog artifacts:
- `INSIGHT_PACKET` completeness
- `ARIA_DECISION` completeness
- No silent scope drift fields (`scope_impact`, `prd_scope_change`)
- Required fallback sections in markdown iterlogs

**Usage:**
```bash
python3 scripts/validation/validate_insight_governance.py
python3 scripts/validation/validate_insight_governance.py --story-id ST-XXX
python3 scripts/validation/validate_insight_governance.py --require-for-completed-only
python3 scripts/validation/validate_insight_governance.py --require-for-completed-only --strict
```

### validation/validate_metacog_compliance.py

Validates metacognition artifact completeness from iterlog artifacts:
- `## Metacognitive Predictions`
- `## Metacognitive Outcomes`
- `## Metacognitive Calibration`
- Required structured fields in each section

**Usage:**
```bash
python3 scripts/validation/validate_metacog_compliance.py
python3 scripts/validation/validate_metacog_compliance.py --story-id ST-XXX --strict
python3 scripts/validation/validate_metacog_compliance.py --require-for-completed-only
```

### backfill_tempmemory_iterlogs.py

Backfills older `docs/tempmemories/iterlog-*.md` files with standard sections:
`## Scope Ownership` and `## Incidents`.

- Apply changes:
  - `python3 scripts/backfill_tempmemory_iterlogs.py`
- Check only (exit non-zero if changes needed):
  - `python3 scripts/backfill_tempmemory_iterlogs.py --check`

### gitea_pr_automerge.py

Opens a PR (if missing) and enables merge when checks succeed, or waits and merges once a required status context is green.

**Usage:**
```bash
export GITEA_TOKEN=...
python3 scripts/gitea_pr_automerge.py --head feature/my-branch --story-id ST-NS-001
python3 scripts/gitea_pr_automerge.py --head feature/my-branch --story-id ST-NS-001 --wait --delete-branch
```

Notes:
- `--story-id` is required and must match accepted CI patterns (`ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*`; must include a digit).
- Script avoids duplicate title prefixes when the title already contains the provided story id token.

### gitea_pr_review.py

Posts an APPROVED / REQUEST_CHANGES review on a PR via Gitea API.

Notes:
- Use a dedicated `GITEA_REVIEW_TOKEN` for a separate bot user. Gitea disallows approving your own PR.

**Usage:**
```bash
export GITEA_REVIEW_TOKEN=...
python3 scripts/gitea_pr_review.py --pr 28 --state APPROVED --body "review-bot approval"
python3 scripts/gitea_pr_review.py --pr 28 --state REQUEST_CHANGES --body "blocking issues: ..."
```

### swarm/session.py

Creates and verifies isolated worktree sessions for agent execution.

**Usage:**
```bash
python3 scripts/swarm/session.py start --story-id ST-NS-001 --agent dev --branch feature/ST-NS-001-scope --scopes src/foo
python3 scripts/swarm/session.py verify --story-id ST-NS-001 --branch feature/ST-NS-001-scope --check-canonical
python3 scripts/swarm/session.py close
```

### ci/swarm_triage.sh

Replays Woodpecker wrapper logic locally for deterministic CI debugging:
- Runs lint/security/local-ci in captured mode
- Writes `_bmad-output/ci/*.status` and logs
- Executes `scripts/ci/ci_gate.py` for final pass/fail summary

**Usage:**
```bash
bash scripts/ci/swarm_triage.sh
# Optional: skip dependency install if your environment is pre-provisioned
SWARM_TRIAGE_INSTALL_DEPS=0 bash scripts/ci/swarm_triage.sh
```

Notes:
- Default behavior auto-detects `.venv-debug` / `.venv` and uses that Python when present.
- Dependency installation defaults to `1` in virtualenv contexts and `0` otherwise.

### ci/woodpecker_triage.py

Root-cause-first CI triage utility for Woodpecker pipelines.

- Fetches PR/pipeline status and step logs directly from Woodpecker API
- Falls back to Woodpecker DB `log_entries` when API step-log endpoints are unavailable
- Extracts exact failures (rule/file/line/test) when possible
- Writes triage bundles to `_bmad-output/ci/woodpecker/<pipeline_number>/`

**Usage:**
```bash
# Pipeline/PR status matrix
python3 scripts/ci/woodpecker_triage.py status --pr 123

# Diagnose failures and write artifacts
python3 scripts/ci/woodpecker_triage.py diagnose --pr 123 --write-artifacts

# Optional explicit DB DSN for authoritative step-log fallback
python3 scripts/ci/woodpecker_triage.py diagnose --pr 123 --write-artifacts --db-dsn "$WOODPECKER_DB_DSN"

# Force local artifact fallback mode
python3 scripts/ci/woodpecker_triage.py diagnose --from-local-dir _bmad-output/ci --write-artifacts
```

### ci/check_woodpecker_forge_token_health.py

Detects Woodpecker forge-token drift/expiry issues before they cause pre-step CI failures.

- Validates `users.expiry` vs JWT `exp` drift
- Detects expired or near-expiry access tokens
- Supports direct DSN input or auto-discovery from `woodpecker-server`

**Usage:**
```bash
python3 scripts/ci/check_woodpecker_forge_token_health.py --require-user craig
python3 scripts/ci/check_woodpecker_forge_token_health.py --dsn "$WOODPECKER_DATABASE_DATASOURCE" --warn-seconds 1800
```

### ci/ci_change_scope.py

Classifies changed files for path-aware CI behavior.

- `docs-only` mode: exits `0` when changes are docs/opencode/report-only
- `changed-python` mode: prints changed Python file list (used by lint step)

**Usage:**
```bash
python3 scripts/ci/ci_change_scope.py --mode summary
python3 scripts/ci/ci_change_scope.py --mode docs-only
python3 scripts/ci/ci_change_scope.py --mode changed-python
```

### ci/check_woodpecker_stuck_pipelines.py

Watchdog for likely-stuck Woodpecker pipelines (running/pending beyond threshold
with no active running/pending steps).

**Usage:**
```bash
python3 scripts/ci/check_woodpecker_stuck_pipelines.py --max-running-seconds 1800
python3 scripts/ci/check_woodpecker_stuck_pipelines.py --fail-on-stuck
```

### ops/merge_reconciler.py

Merge queue + reconciliation utility for non-blocking swarm throughput while preserving `main` integrity.

- Stores queued PR merge intents in Redis (`bmad:chiseai:merge-queue:main`)
- Runs bounded queue ticks so Jarvis can merge green PRs without blocking worker development
- Emits incidents for CI failures, merge conflicts, and branch/main drift
- Performs git hygiene checks (local `main` vs `gitea/main`, local branches ahead of `main`)

**Usage:**
```bash
# Enqueue
python3 scripts/ops/merge_reconciler.py enqueue --story-id ST-NS-001 --branch feature/ST-NS-001-x --pr-number 42 --head-sha <sha>

# Bounded merge tick
python3 scripts/ops/merge_reconciler.py queue-tick --max-items 3 --allow-merge

# Queue + hygiene reconciliation
python3 scripts/ops/merge_reconciler.py reconcile-tick --max-items 3 --allow-merge

# Incident intake
python3 scripts/ops/merge_reconciler.py intake-incidents --limit 100
```

### ops/merlin_pr_sweep.py

Merlin-only automation wrapper for end-to-end PR sweep and cleanup.

- Discovers non-main branches with unique commits ahead of `main`
- Resolves story IDs from explicit mapping (`docs/operations/merlin-branch-story-map.json`) with regex fallback
- Opens/updates PRs through `scripts/gitea_pr_automerge.py`
- Enforces supersession-link comments in consolidation mode

**Usage:**
```bash
# Standard sweep
python3 scripts/ops/merlin_pr_sweep.py --wait

# Dry-run
python3 scripts/ops/merlin_pr_sweep.py --dry-run

# Consolidation supersession comments (required in consolidation mode)
python3 scripts/ops/merlin_pr_sweep.py \
  --consolidation-mode \
  --supersession-pr 123 \
  --supersede-pr 120 \
  --supersede-pr 121
```

## Adding New Scripts

When adding scripts to this directory:
1. Make scripts executable (`chmod +x script_name.py`)
2. Include `if __name__ == '__main__':` block for CLI usage
3. Add docstrings explaining purpose and usage
4. Update this README with script description
5. Add to `.woodpecker.yml` if it should run in CI

## Script Standards

- Python scripts should use Poetry or venv for dependencies
- Scripts should be idempotent (safe to run multiple times)
- Error messages should be clear and actionable
- Return codes should follow Unix conventions
