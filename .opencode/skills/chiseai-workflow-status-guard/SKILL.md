---
name: chiseai-workflow-status-guard
description: Hardened operating procedure for docs/bmm-workflow-status.yaml using status_guard.py with mandatory repair escalation.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-21"
---

# chiseai-workflow-status-guard

## Goal

Keep `docs/bmm-workflow-status.yaml` parseable and policy-valid with deterministic guard steps.

## Trigger

Load this skill when:
- editing `docs/bmm-workflow-status.yaml`
- YAML parse/lint errors mention this file
- CI or precommit fails on status-write/status-sync/workflow transition gates

## Required sequence

1. Pre-edit check:
   - `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`

2. If invalid, run attempt-tracked fix cycle:
   - `python3 scripts/governance/status_guard.py attempt --file docs/bmm-workflow-status.yaml --enforce-repair-after 2`
   - On first failure (`exit 1`): manual correction is allowed.
   - On second failure (`exit 2`): manual correction is no longer allowed.

3. Mandatory repair escalation (after two failed attempts):
   - `python3 scripts/governance/status_guard.py repair --file docs/bmm-workflow-status.yaml --enforce-repair-after 2`

4. If repair cannot complete:
   - `python3 scripts/governance/status_guard.py restore --file docs/bmm-workflow-status.yaml`

5. Post-edit validation:
   - `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`

## Non-negotiables

- Do not proceed with unrelated story work while this file is invalid.
- Do not bypass mandatory repair after two failed attempts.
- Preserve backups produced by `status_guard.py` for recovery and audit.
