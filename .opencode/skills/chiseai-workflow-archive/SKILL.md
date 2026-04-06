---
name: chiseai-workflow-archive
description: Archive old workflow-status stories/epics into ARCH entries with lean stubs and metrics-first execution.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-04-05"
---

# chiseai-workflow-archive

## Goal

Archive stories/epics older than the retention threshold from `docs/bmm-workflow-status.yaml` into `docs/archives/workflow-status/entries/ARCH-*.yaml` while leaving lean stubs in place.

## Trigger

Load this skill when:

- user asks to archive old stories/epics from workflow status
- file size reduction is needed for `docs/bmm-workflow-status.yaml`
- periodic retention maintenance is requested

## Required sequence

1. Pre-check (no edits yet):
   - `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`

2. Dry-run first (mandatory):
   - `python3 scripts/workflow/archive_workflow_status_items.py --retention-days 7 --require-completion-evidence`
   - Review run metrics and candidate list.

3. Execute (only after dry-run review):
   - `python3 scripts/workflow/archive_workflow_status_items.py --retention-days 7 --require-completion-evidence --update-index --execute --migrated-by <agent>`

4. Post-run guards:
   - `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`
   - `python3 scripts/validate_status_sync.py`

5. If status-file validation fails:
   - Use `chise-status-yaml-guard` (`attempt`, then mandatory `repair` after 2 failed attempts).

## Non-negotiables

- Dry-run is the default and should always be run first.
- Keep stubs in the workflow file; do not fully delete archived items.
- Archive payloads must land in `docs/archives/workflow-status/entries/`.
- Do not skip status guard + status sync checks after execute mode.

## Metrics to report

- Candidate totals (stories/epics)
- Archived totals this run (stories/epics)
- Line reduction (before/after, absolute and percent)
- Skipped/error counts
