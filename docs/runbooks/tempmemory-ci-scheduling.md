# TempMemory CI Scheduling Runbook

> **Story**: ST-MEMORY-003  
> **Purpose**: Operational guide for tempmemory CI scheduling jobs  
> **Last Updated**: 2026-03-01

---

## Overview

This runbook documents the CI scheduling setup for tempmemory operations in the ChiseAI Woodpecker CI pipeline. Three scheduled jobs run to maintain tempmemory hygiene and perform brain evaluations.

---

## Scheduled Jobs

### 1. `tempmemory-scheduler`

**Purpose**: Runs full tempmemory migration to process pending tempmemory files.

**When It Runs**:
- **Cron**: Daily (when triggered by cron event)
- **Manual**: Can be triggered manually via Woodpecker UI
- **Event Types**: `cron`, `manual`

**What It Does**:
1. Installs required Python dependencies (`pyyaml`)
2. Executes `scripts/ops/tempmemory_migration.py --full-migration --enable`
3. Processes all pending tempmemory files in `docs/tempmemories/`
4. Migrates valid files to permanent storage

**Output**:
- Log: `_bmad-output/ci/tempmemory-scheduler.log`
- Status: `_bmad-output/ci/tempmemory-scheduler.status` (exit code)

**Non-Blocking**: Always exits 0; failures are logged but don't fail the pipeline

---

### 2. `mini-brain-eval`

**Purpose**: Runs mini brain evaluation to detect issues from iterlog files.

**When It Runs**:
- **Cron**: Daily (when triggered by cron event)
- **Manual**: Can be triggered manually via Woodpecker UI
- **Event Types**: `cron`, `manual`

**What It Does**:
1. Installs required Python dependencies (`pyyaml`)
2. Executes `scripts/evaluation/mini_brain_eval.py` with:
   - `--cadence daily`: Daily evaluation mode
   - `--use-all`: Use all available sources
   - `--provenance`: Enable provenance tracking
   - `--output-dir _bmad-output/ci/mini-brain-eval`: Output directory
3. Scans `docs/tempmemories/*.md` for issues
4. Generates evaluation reports with detected patterns

**Output**:
- Log: `_bmad-output/ci/mini-brain-eval.log`
- Status: `_bmad-output/ci/mini-brain-eval.status` (exit code)
- Reports: `_bmad-output/ci/mini-brain-eval/` directory

**Non-Blocking**: Always exits 0; failures are logged but don't fail the pipeline

---

### 3. `tempmemory-reconcile`

**Purpose**: Runs tempmemory reconciliation and archiving.

**When It Runs**:
- **Cron**: Daily (when triggered by cron event)
- **Manual**: Can be triggered manually via Woodpecker UI
- **Event Types**: `cron`, `manual`

**What It Does**:
1. Installs required Python dependencies (`pyyaml`)
2. Executes `scripts/ops/tempmemory_scheduler.py --once --dry-run`
3. Reconciles migration status:
   - Detects orphaned files (in tempmemory but not tracked)
   - Detects missing files (tracked but not in tempmemory)
4. Archives completed files

**Output**:
- Log: `_bmad-output/ci/tempmemory-reconcile.log`
- Status: `_bmad-output/ci/tempmemory-reconcile.status` (exit code)

**Non-Blocking**: Always exits 0; failures are logged but don't fail the pipeline

---

## CI Configuration Location

All jobs are defined in `.woodpecker/ci.yaml`:

```yaml
# Lines ~199-260
tempmemory-scheduler:
  image: python:3.11
  commands:
    - |
      set -euo pipefail
      mkdir -p _bmad-output/ci
      set +e
      (
        set -euo pipefail
        pip install --no-cache-dir pyyaml
        python3 scripts/ops/tempmemory_migration.py --full-migration --enable
      ) > _bmad-output/ci/tempmemory-scheduler.log 2>&1
      code=$?
      cat _bmad-output/ci/tempmemory-scheduler.log
      echo "$code" > _bmad-output/ci/tempmemory-scheduler.status
      exit 0

mini-brain-eval:
  image: python:3.11
  commands:
    - |
      set -euo pipefail
      mkdir -p _bmad-output/ci
      set +e
      (
        set -euo pipefail
        pip install --no-cache-dir pyyaml
        python3 scripts/evaluation/mini_brain_eval.py --cadence daily --use-all --provenance --output-dir _bmad-output/ci/mini-brain-eval
      ) > _bmad-output/ci/mini-brain-eval.log 2>&1
      code=$?
      cat _bmad-output/ci/mini-brain-eval.log
      echo "$code" > _bmad-output/ci/mini-brain-eval.status
      exit 0

tempmemory-reconcile:
  image: python:3.11
  commands:
    - |
      set -euo pipefail
      mkdir -p _bmad-output/ci
      set +e
      (
        set -euo pipefail
        pip install --no-cache-dir pyyaml
        python3 scripts/ops/tempmemory_scheduler.py --once --dry-run
      ) > _bmad-output/ci/tempmemory-reconcile.log 2>&1
      code=$?
      cat _bmad-output/ci/tempmemory-reconcile.log
      echo "$code" > _bmad-output/ci/tempmemory-reconcile.status
      exit 0
```

---

## Troubleshooting Guide

### Issue: Job Not Running on Cron

**Symptoms**: Scheduled job doesn't execute at expected time

**Checklist**:
1. Verify Woodpecker cron is configured for the repository
2. Check if the branch filter allows cron events (see `when` section in CI YAML)
3. Verify the Woodpecker server has cron enabled

**Commands**:
```bash
# Check Woodpecker cron configuration
woodpecker-cli cron ls <repo>

# Check pipeline events
woodpecker-cli build ls <repo>
```

---

### Issue: tempmemory-scheduler Fails

**Symptoms**: `tempmemory-scheduler.status` contains non-zero exit code

**Checklist**:
1. Check the log file for errors:
   ```bash
   cat _bmad-output/ci/tempmemory-scheduler.log
   ```
2. Verify `scripts/ops/tempmemory_migration.py` exists and is executable
3. Check if tempmemory files exist in `docs/tempmemories/`
4. Verify Python dependencies can be installed

**Common Causes**:
- Missing tempmemory files
- Python import errors
- Permission issues with output directory

---

### Issue: mini-brain-eval Fails

**Symptoms**: `mini-brain-eval.status` contains non-zero exit code

**Checklist**:
1. Check the log file:
   ```bash
   cat _bmad-output/ci/mini-brain-eval.log
   ```
2. Verify `scripts/evaluation/mini_brain_eval.py` exists
3. Check if iterlog files exist in `docs/tempmemories/`
4. Verify output directory is writable

**Common Causes**:
- No iterlog files to evaluate
- Python dependency issues
- Invalid YAML in tempmemory files

---

### Issue: tempmemory-reconcile Fails

**Symptoms**: `tempmemory-reconcile.status` contains non-zero exit code

**Checklist**:
1. Check the log file:
   ```bash
   cat _bmad-output/ci/tempmemory-reconcile.log
   ```
2. Verify `scripts/ops/tempmemory_scheduler.py` exists
3. Check Redis connectivity (if using Redis-backed tracking)
4. Verify archive directory permissions

**Common Causes**:
- Redis connection issues
- Archive directory not writable
- Corrupted tracking state

---

### Issue: Output Artifacts Missing

**Symptoms**: Expected output files not present in `_bmad-output/ci/`

**Checklist**:
1. Verify the job actually ran (check Woodpecker UI)
2. Check if `mkdir -p _bmad-output/ci` succeeded
3. Verify artifact persistence is configured in Woodpecker

**Commands**:
```bash
# List output directory
ls -la _bmad-output/ci/

# Check specific job output
cat _bmad-output/ci/<job-name>.log
```

---

## Manual Triggering

To manually trigger these jobs:

1. Go to Woodpecker UI
2. Navigate to the repository
3. Click "New Build" or "Run Pipeline"
4. Select the branch (usually `main`)
5. The jobs will run as part of the pipeline

Alternatively, use the Woodpecker CLI:

```bash
# Trigger a manual build
woodpecker-cli build create <repo> --branch main
```

---

## Related Documentation

- [TempMemory Migration Runbook](./tempmemory-migration.md)
- [Brain Evaluation Guide](../brain-evaluation.md)
- [Woodpecker CI Configuration](../../.woodpecker/ci.yaml)

---

## Maintenance Notes

- All jobs use `python:3.11` Docker image
- Jobs are **non-blocking** by design (always exit 0)
- Status codes are captured in `.status` files for monitoring
- Logs are captured in `.log` files for debugging
- Jobs follow the same pattern as other CI steps (swarm-context, lint, etc.)

---

## Contact

For issues or questions about tempmemory CI scheduling:
- **Story**: ST-MEMORY-003
- **Team**: ChiseAI Memory Governance
- **Slack**: #chiseai-memory
