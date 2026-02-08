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

### gitea_pr_automerge.py

Opens a PR (if missing) and enables merge when checks succeed, or waits and merges once a required status context is green.

**Usage:**
```bash
export GITEA_TOKEN=...
python3 scripts/gitea_pr_automerge.py --head feature/my-branch
python3 scripts/gitea_pr_automerge.py --head feature/my-branch --wait --delete-branch
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
