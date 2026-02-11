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

### iterlog_ops.py

Helper to reduce hand-rolled Redis operations for parallel execution safety.

- Claim scope ownership (Redis; markdown fallback):
  - `python3 scripts/iterlog_ops.py claim-ownership --story-id=ST-XXX --agent=dev --scopes src/foo docs/bar`
- Check ownership (Redis only):
  - `python3 scripts/iterlog_ops.py check-ownership --story-id=ST-XXX --agent=dev --scopes src/foo`
- Append incident (Redis list + markdown fallback):
  - `python3 scripts/iterlog_ops.py append-incident --story-id=ST-XXX --text "symptom: ..."`

### backfill_tempmemory_iterlogs.py

Backfills older `docs/tempmemories/iterlog-*.md` files with standard sections:
`## Scope Ownership` and `## Incidents`.

- Apply changes:
  - `python3 scripts/backfill_tempmemory_iterlogs.py`
- Check only (exit non-zero if changes needed):
  - `python3 scripts/backfill_tempmemory_iterlogs.py --check`
```

### gitea_pr_automerge.py

Opens a PR (if missing) and enables merge when checks succeed, or waits and merges once a required status context is green.

**Usage:**
```bash
export GITEA_TOKEN=...
python3 scripts/gitea_pr_automerge.py --head feature/my-branch
python3 scripts/gitea_pr_automerge.py --head feature/my-branch --wait --delete-branch
```

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
