---
story_id: ST-CI-EVIDENCE-001
story_title: Backfill ST-CI-001 Evidence Fields
epic_id: EP-CI-001
phase: implementation
status: planned
story_points: 1
priority: P1
created_date: "2026-03-24"
owner: TBD
depends_on: []
---

# Story: Backfill ST-CI-001 Evidence Fields

## Problem Statement

ST-CI-001 is marked `completed` in `docs/bmm-workflow-status.yaml` (lines 4610-4625) but lacks required `pr_number` and `merge_commit` evidence fields per completion-evidence-gate requirements.

## Background

ST-CI-001 (Real CI Gates - Black/Ruff/Mypy/Pytest/Coverage) was completed as part of EP-CI-001 sprint p0-1. The story is validated and documented in the workflow status but evidence fields were not populated at completion time.

**Research findings (2026-03-24):**

- Original ST-CI-001 was merged via **PR #25** (`feature/phase1-order-lock` branch)
- Merge commit: `13d68e4b` - "Merge pull request 'ST-CI-001 feature/phase1-order-lock' (#25)"
- Completion commit: `71ad89b9` - "Complete ST-CI-001: Real CI Gates implemented"
- **CRITICAL**: Both commits are NOT ancestors of current `origin/main`. The original ST-CI-001 history was lost in a rebase/history rewrite.
- The actual CI gates now on main are REPO-000 through REPO-011 (CI quality gate baselines, 2026-03-23).

**Resolution approach**: Since the original commits are orphaned, the evidence fields should reference the REPO-\* commits that represent the actual CI gate implementation on current main. Alternatively, a `note` field can explain the history rewrite.

## Acceptance Criteria

1. ST-CI-001 entry in workflow-status.yaml has valid `pr_number` field (or documented reason for absence)
2. ST-CI-001 entry has valid `merge_commit` SHA (or documented note about history rewrite)
3. `status-evidence-gate` and `completion-evidence-gate` pass for ST-CI-001

## Technical Approach

1. Determine best evidence strategy given history rewrite:
   - Option A: Reference REPO-\* commits as replacement evidence with note
   - Option B: Add `evidence_note` field explaining orphaned PR #25
   - Option C: Annotate workflow-status.yaml with history-rewrite caveat
2. Update bmm-workflow-status.yaml with chosen approach
3. Validate using status_guard.py

## Verification

- `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`
- `status-evidence-gate` CI check passes
- `completion-evidence-gate` CI check passes
