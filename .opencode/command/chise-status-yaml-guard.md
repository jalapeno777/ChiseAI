---
name: "chise-status-yaml-guard"
description: "ChiseAI: hardened guard for docs/bmm-workflow-status.yaml (validate, attempt tracking, repair, restore)."
disable-model-invocation: true
---

Use this command whenever `docs/bmm-workflow-status.yaml` is edited, or when YAML errors are reported.

## Modes

1. Validate only:
   - `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`

2. Attempt tracking (for manual fix attempts):
   - `python3 scripts/governance/status_guard.py attempt --file docs/bmm-workflow-status.yaml --enforce-repair-after 2`
   - Exit code behavior:
     - `0`: valid
     - `1`: invalid, another manual attempt allowed
     - `2`: invalid and repair is now mandatory

3. Forced repair (mandatory after two failed attempts):
   - `python3 scripts/governance/status_guard.py repair --file docs/bmm-workflow-status.yaml --enforce-repair-after 2`

4. Restore from latest valid backup:
   - `python3 scripts/governance/status_guard.py restore --file docs/bmm-workflow-status.yaml`

5. Restore from explicit backup:
   - `python3 scripts/governance/status_guard.py restore --file docs/bmm-workflow-status.yaml --backup <backup_path>`

## Required policy

- After any two failed `attempt` runs, do not continue ad-hoc edits.
- Run `repair` and revalidate before proceeding with any other workflow tasks.
