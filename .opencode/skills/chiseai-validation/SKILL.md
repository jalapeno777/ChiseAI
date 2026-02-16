---
name: chiseai-validation
description: Validation patterns and gates for ChiseAI workflows (status sync, compliance, CI).
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
---

# chiseai-validation

## Goal

Ensure all changes meet ChiseAI quality and compliance standards before merge.

## When To Use

- Before committing changes
- Before PR creation
- Before merging to main
- CI failure diagnosis

## Validation Layers

### 1. Pre-Commit (Local)
Run via `.opencode/command/chise-precommit-gates.md`:
- Git sanity checks
- Local CI (if available)
- Status sync validation
- Iterloop compliance

### 2. CI Gates (Woodpecker)
Server-side validation:
- Full test suite
- Security scans
- Status sync (required)
- Required contexts must pass

### 3. Pre-Merge (Merlin)
Final authority checks:
- Green CI verification
- Status file sync confirmed
- PR review completed (if required)

## Status Sync Validation

Every PR adding story implementations MUST:
1. Update `docs/bmm-workflow-status.yaml`
2. Run `python3 scripts/validate_status_sync.py`
3. Pass before merge

## CI Failure Diagnosis

When CI fails:
1. Use `.opencode/command/chise-ci-pr-status.md` - identify failed pipeline
2. Use `.opencode/command/chise-ci-root-cause.md` - extract exact root cause
3. If unresolved, use `.opencode/command/chise-ci-failure-bundle.md`

## Required Evidence

CI failure reports must include:
- `tool` that failed
- `message` (exact error)
- One of: `file:line`, `rule`, or `test`

## Related Commands
- `.opencode/command/chise-precommit-gates.md`
- `.opencode/command/chise-ci-pr-status.md`
- `.opencode/command/chise-ci-root-cause.md`
- `.opencode/command/chise-ci-failure-bundle.md`
