---
name: "chise-workflow-archive"
description: "ChiseAI: archive workflow-status stories/epics older than retention threshold with lean stubs and run metrics."
disable-model-invocation: true
---

Archive old workflow-status items while preserving lean stubs in `docs/bmm-workflow-status.yaml` and writing full payloads to `docs/archives/workflow-status/entries/ARCH-*.yaml`.

Default mode is dry-run.

## 1) Dry Run (Recommended First)

```bash
python3 scripts/workflow/archive_workflow_status_items.py --retention-days 7
```

Optional JSON metrics:

```bash
python3 scripts/workflow/archive_workflow_status_items.py --retention-days 7 --json
```

## 2) Execute Archival

```bash
python3 scripts/workflow/archive_workflow_status_items.py --retention-days 7 --execute --migrated-by jarvis
```

Hardened execute with evidence + index update:

```bash
python3 scripts/workflow/archive_workflow_status_items.py \
  --retention-days 7 \
  --require-completion-evidence \
  --update-index \
  --execute \
  --migrated-by jarvis
```

## 3) Scope Controls

Specific IDs only:

```bash
python3 scripts/workflow/archive_workflow_status_items.py --id ST-LOCAL-001 --id EP-NS-006
```

Batch size limit:

```bash
python3 scripts/workflow/archive_workflow_status_items.py --batch-size 20 --execute
```

## 4) Required Post-Run Validation

```bash
python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml
python3 scripts/validate_status_sync.py
```

## Metrics Returned

The script returns run metrics including:

- candidates (`stories`, `epics`, total)
- items archived this run (`stories`, `epics`, total)
- line reduction (`before`, `after projected/actual`, absolute and %)
- skipped count and error count

Dry-run includes the exact items that would be archived and their generated `archive_ref`.
