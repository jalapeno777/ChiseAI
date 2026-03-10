# Workflow Archival Automation Runbook

> **Story:** ST-WORKFLOW-ARCHIVAL-001  
> **Version:** 1.1.0  
> **Last Updated:** 2026-03-09  
> **Owner:** senior-dev

## Table of Contents

1. [Overview](#overview)
2. [Already Completed Items](#already-completed-items)
3. [Newly Implemented Items](#newly-implemented-items)
4. [Intentionally Deferred Items](#intentionally-deferred-items)
5. [Anti-Regression Rule](#anti-regression-rule)
6. [Automation Schedule](#automation-schedule)
7. [Preflight Guard](#preflight-guard)
8. [Manual Execution](#manual-execution)
9. [Rollback Procedures](#rollback-procedures)
10. [Monitoring and Alerting](#monitoring-and-alerting)
11. [Troubleshooting](#troubleshooting)
12. [Discord Integration](#discord-integration)

---

## Overview

This runbook documents the workflow status archival automation system (Phase 4), which automatically archives completed stories from `docs/bmm-workflow-status.yaml` to the archive storage at `docs/archives/workflow-status/entries/`.

### Key Components

| Component | Script | Purpose |
|-----------|--------|---------|
| Preflight Guard | `scripts/workflow/preflight_archive.py` | Safety checks before archival |
| Automated Archive | `scripts/workflow/automated_archive.py` | Main automation wrapper |
| Health Report | `scripts/workflow/daily_health_report.py` | Daily health metrics |
| Discord Notifier | `scripts/notifications/discord_workflow_notifier.py` | Notifications |
| CI Pipeline | `.woodpecker/workflow-archive.yaml` | Scheduled automation |

### Archive Schema

Archive entries follow the schema defined in `docs/archives/workflow-status/schema/archive-entry-schema.yaml`.

---

## Already Completed Items

### Phase 4 Components Deployed

The following components were implemented and deployed as part of Phase 4 (Full Automation):

| Component | Status | Evidence |
|-----------|--------|----------|
| Preflight Guard | ✅ Complete | `scripts/workflow/preflight_archive.py` (lines 1-350) |
| Automated Archive | ✅ Complete | `scripts/workflow/automated_archive.py` (lines 1-772) |
| Daily Health Report | ✅ Complete | `scripts/workflow/daily_health_report.py` |
| Discord Notifier | ✅ Complete | `scripts/notifications/discord_workflow_notifier.py` |
| CI Pipeline | ✅ Complete | `.woodpecker/workflow-archive.yaml` (lines 1-221) |
| Archive Schema | ✅ Complete | `docs/archives/workflow-status/schema/archive-entry-schema.yaml` |
| Migration Scripts | ✅ Complete | `scripts/workflow/migration/` (archive_stories.py, verify_archive.py, rollback_archive.py) |

### Evidence References

**File Locations:**
- Preflight Guard: `scripts/workflow/preflight_archive.py` - Performs 7 safety checks (dependencies, disk space, git status, dry-run candidates, data loss prevention, rollback readiness, integrity validation)
- Automated Archive: `scripts/workflow/automated_archive.py` - Main automation wrapper with fail-closed design
- CI Pipeline: `.woodpecker/workflow-archive.yaml` - Woodpecker CI pipeline with weekly and daily cron schedules
- Archive Entries: `docs/archives/workflow-status/entries/` - 20 stories archived to date
- Schema: `docs/archives/workflow-status/schema/archive-entry-schema.yaml` - Archive entry schema definition

**Status Source:**
- See `docs/bmm-workflow-status.yaml` lines 8-26 for Phase 4 activation details
- Phase 4 Activation Date: 2026-03-09
- Total archived to date: 20 stories
- Legacy Integrity Cleanup: COMPLETED 2026-03-09 (10 archives with checksum mismatches repaired)

### Automation Schedule

| Job | Schedule | Cron Name | Script |
|-----|----------|-----------|--------|
| Weekly Archival | Sundays at 02:00 UTC | `workflow-archive-weekly` | `automated_archive.py` |
| Daily Health Check | Every day at 06:00 UTC | `workflow-archive-daily` | `daily_health_report.py` |

---

## Newly Implemented Items

### CI Validation Gates

Three CI validation gates have been implemented to ensure workflow integrity:

| Gate | Script | Purpose | Status |
|------|--------|---------|--------|
| Status Evidence | `scripts/validation/validate_status_evidence.py` | Validates that workflow status entries have required evidence | ✅ Complete |
| Completion Evidence | `scripts/validation/validate_completion_evidence.py` | Validates completion criteria and evidence for completed stories | ✅ Complete |
| Workflow Transition | `scripts/validation/validate_workflow_transitions.py` | Validates state machine transitions and epic-story consistency | ✅ Complete |

**Evidence:**
- Status Evidence Validator: `scripts/validation/validate_status_evidence.py` (lines 1-300+)
- Workflow Transition Validator: `scripts/validation/validate_workflow_transitions.py` (lines 1-781)

### Live Mode with Safety Controls

Live mode enables actual archival execution (not dry-run) with multiple safety controls:

**Activation Requirements:**
1. Set `WORKFLOW_ARCHIVE_LIVE="true"` in environment
2. Set `WORKFLOW_ARCHIVE_LIVE_CONFIRM="true"` in environment
3. Both must be explicitly "true" for live mode to activate

**Safety Controls:**
- **Redis Lock**: Prevents concurrent archival operations (`bmad:chiseai:workflow:archival:lock`)
- **Backup Creation**: Timestamped backup of `workflow-status.yaml` before any changes
- **Preflight Checks**: 7 safety checks must pass before execution
- **Post-Verification**: All archives verified after execution
- **Fail-Closed Design**: Any failure blocks archival

**Evidence:**
- Live mode implementation: `scripts/workflow/automated_archive.py` lines 534-604
- Safety check logic: lines 578-607
- Redis lock management: lines 213-259
- Backup creation: lines 262-301

### State Machine Validator

The workflow state machine validator ensures status transitions follow valid rules:

**Valid Transitions:**
```
planned → in_progress
in_progress → completed
in_progress → cancelled
completed → archived
completed → merged
backlog → planned
Any status → deprecated (admin override)
```

**Validation Features:**
- Status transition validation
- Epic-story consistency checks
- Terminal status enforcement (cannot transition out of archived/cancelled/deprecated)
- Orphaned story detection
- JSON and text output formats

**Evidence:**
- State machine validator: `scripts/validation/validate_workflow_transitions.py`
- Transition rules: lines 66-77
- Epic compatibility rules: lines 81-96
- Validation logic: lines 387-431

---

## Intentionally Deferred Items

### Full Live Mode Enablement

**Status:** Deferred - Requires Manual Activation

Live mode is implemented but **disabled by default** in the CI pipeline. To enable:

1. Set Woodpecker secrets:
   ```bash
   woodpecker-cli secret add \
     --repo gitea/chiseai/chiseai \
     --name WORKFLOW_ARCHIVE_LIVE \
     --value "true"
   
   woodpecker-cli secret add \
     --repo gitea/chiseai/chiseai \
     --name WORKFLOW_ARCHIVE_LIVE_CONFIRM \
     --value "true"
   ```

2. Verify in `.woodpecker/workflow-archive.yaml` lines 81-84

**Rationale:**
- Dry-run mode provides safety during initial deployment
- Manual activation ensures explicit human decision
- Allows monitoring of automation behavior before enabling changes

### Additional Runbooks for CI Gates

**Status:** Deferred - Future Enhancement

The following documentation is planned but not yet implemented:

- Detailed runbook for `validate_status_evidence.py` troubleshooting
- Detailed runbook for `validate_completion_evidence.py` troubleshooting  
- Integration guide for CI gate failure response

**Current Coverage:**
- Basic usage documented in script docstrings
- Validation logic is self-documenting via `--help` and `--verbose` flags

---

## Anti-Regression Rule

### When to Re-Audit

Do **NOT** re-audit Phase 4 components unless one of the following conditions is met:

| Condition | Trigger | Action |
|-----------|---------|--------|
| CI Gate Failure | Validation gate fails on unrelated PRs | Investigate root cause, fix if systemic |
| Data Loss Incident | Archival causes data loss | Immediate rollback, incident response |
| New Workflow Fields | New fields introduced in workflow schema | Update validators and documentation |
| Regulatory Changes | Compliance requirements change | Review and update as needed |

### Evidence Preservation

All Phase 4 implementation evidence is preserved in the following locations:

**Code Evidence:**
- `scripts/workflow/preflight_archive.py` - Preflight guard implementation
- `scripts/workflow/automated_archive.py` - Automation wrapper (v2.0.0)
- `scripts/workflow/daily_health_report.py` - Health monitoring
- `scripts/notifications/discord_workflow_notifier.py` - Notifications
- `scripts/validation/validate_workflow_transitions.py` - State machine validator
- `.woodpecker/workflow-archive.yaml` - CI pipeline (v2.0.0)

**Documentation Evidence:**
- `docs/runbooks/workflow-archival-automation.md` - This runbook
- `docs/bmm-workflow-status.yaml` - Workflow status with Phase 4 header (lines 1-44)
- `docs/archives/workflow-status/schema/archive-entry-schema.yaml` - Archive schema

**Audit Trail:**
- Archive entries: `docs/archives/workflow-status/entries/ARCH-*.yaml`
- Redis iterlog: `bmad:chiseai:iterlog:story:ST-WORKFLOW-ARCHIVAL-001`
- Git history: Commits related to Phase 4 implementation

### No-Reaudit Policy

**Normal Operations:**
- Weekly archival runs in dry-run mode (default)
- Daily health checks monitor system health
- Discord notifications alert on issues

**Exception Handling:**
- If CI gate fails, investigate but do not re-audit entire Phase 4
- If data loss occurs, follow incident response procedures
- If new requirements emerge, scope changes appropriately

**Preservation Guarantee:**
All evidence files are under version control and protected by the standard Git workflow. Archive entries are immutable once created.

---

## Automation Schedule

### Weekly Archival Job

- **Schedule:** Sundays at 02:00 UTC
- **Cron Name:** `workflow-archive-weekly`
- **Pipeline:** `.woodpecker/workflow-archive.yaml`
- **Script:** `scripts/workflow/automated_archive.py`
- **Batch Size:** 20 stories per run

### Daily Health Check Job

- **Schedule:** Every day at 06:00 UTC
- **Cron Name:** `workflow-archive-daily`
- **Pipeline:** `.woodpecker/workflow-archive.yaml`
- **Script:** `scripts/workflow/daily_health_report.py`

### Configuring Woodpecker Cron

To set up the cron schedules in Woodpecker:

```bash
# Add weekly archival cron (Sundays at 02:00 UTC)
woodpecker-cli cron add \
  --repo gitea/chiseai/chiseai \
  --name workflow-archive-weekly \
  --expr "0 2 * * 0" \
  --branch main

# Add daily health check cron (daily at 06:00 UTC)
woodpecker-cli cron add \
  --repo gitea/chiseai/chiseai \
  --name workflow-archive-daily \
  --expr "0 6 * * *" \
  --branch main
```

---

## Preflight Guard

The preflight guard performs safety checks before any archival operation. It uses a **fail-closed** design - any failure blocks archival.

### Preflight Checks

1. **Dependencies** - Verify required scripts and files exist
2. **Disk Space** - Ensure sufficient disk space (≥100MB)
3. **Git Status** - Check for uncommitted changes
4. **Dry-Run Candidates** - Scan for stories that would be archived
5. **No Data Loss** - Verify checksum integrity of existing archives
6. **Rollback Readiness** - Test rollback capability
7. **Integrity Validation** - Run verify_archive.py on all archives

### Running Preflight Manually

```bash
# Basic preflight check
python3 scripts/workflow/preflight_archive.py

# Verbose output
python3 scripts/workflow/preflight_archive.py --verbose

# JSON output for automation
python3 scripts/workflow/preflight_archive.py --json

# Skip specific checks (use with caution)
python3 scripts/workflow/preflight_archive.py --skip git_status,disk_space
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Non-critical failures |
| 2 | Critical failure (data loss risk) |

---

## Manual Execution

### Automated Archive Wrapper

```bash
# Dry-run mode (default)
python3 scripts/workflow/automated_archive.py

# Execute archival with preflight
python3 scripts/workflow/automated_archive.py --batch-size 10

# Skip preflight (USE WITH CAUTION)
python3 scripts/workflow/automated_archive.py --skip-preflight

# With Discord notification
python3 scripts/workflow/automated_archive.py --notify

# JSON output
python3 scripts/workflow/automated_archive.py --json
```

### Direct Archive Script

```bash
# Dry-run
python3 scripts/workflow/migration/archive_stories.py --dry-run

# Execute archival
python3 scripts/workflow/migration/archive_stories.py --execute --batch-size 10

# Archive specific story
python3 scripts/workflow/migration/archive_stories.py --execute --story-id ST-LAUNCH-001
```

### Daily Health Report

```bash
# Generate health report
python3 scripts/workflow/daily_health_report.py

# With notification
python3 scripts/workflow/daily_health_report.py --notify

# JSON output for monitoring
python3 scripts/workflow/daily_health_report.py --json
```

---

## Rollback Procedures

### Automatic Rollback Capability

The system maintains rollback capability through:

1. **Archive Entries** - Complete story data preserved in archive files
2. **Checksums** - SHA-256 checksums for integrity verification
3. **Lean Status** - Minimal status retained in workflow-status.yaml

### Manual Rollback

To restore an archived story:

```bash
# Rollback by archive reference (dry-run by default)
python3 scripts/workflow/migration/rollback_archive.py --archive-ref ARCH-20260309-123456-ST-LAUNCH-001

# Execute rollback
python3 scripts/workflow/migration/rollback_archive.py --archive-ref ARCH-20260309-123456-ST-LAUNCH-001 --execute

# Rollback by story ID
python3 scripts/workflow/migration/rollback_archive.py --story-id ST-LAUNCH-001 --execute
```

### Bulk Rollback

For bulk rollback scenarios:

```bash
# List all archives
ls -la docs/archives/workflow-status/entries/

# Rollback multiple stories
for archive in docs/archives/workflow-status/entries/ARCH-*.yaml; do
    ref=$(basename "$archive" .yaml)
    echo "Rolling back $ref..."
    python3 scripts/workflow/migration/rollback_archive.py --archive-ref "$ref" --execute
done
```

### Post-Rollback Verification

After rollback, verify the story is restored:

```bash
# Check workflow status
grep -A 5 "ST-LAUNCH-001" docs/bmm-workflow-status.yaml

# Verify archive still exists (for audit)
ls docs/archives/workflow-status/entries/ARCH-*-ST-LAUNCH-001.yaml

# Run integrity check
python3 scripts/workflow/migration/verify_archive.py --story-id ST-LAUNCH-001
```

---

## Monitoring and Alerting

### Health Metrics

The daily health report tracks:

- **Total Stories** - Total stories in workflow-status.yaml
- **Archived Stories** - Stories with archive_ref
- **Active Stories** - Stories without archive_ref
- **Orphaned Archives** - Archives without workflow entry (>7 days)
- **Integrity Failures** - Archives failing checksum verification
- **Archive Size** - Total and average archive size

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Orphaned Archives | >0 | >5 |
| Integrity Failures | >0 | >0 |
| Archive Ratio | >80% | >95% |
| Disk Space | <500MB | <100MB |

### Discord Notifications

Notifications are sent to the **#development** channel:

- **Channel ID:** `1448414506412806347`
- **Webhook:** Configured via `DISCORD_WEBHOOK_URL` environment variable

**Notification Levels:**

- **INFO** - Archival complete, daily health report (healthy)
- **WARNING** - Health check warnings, non-critical issues
- **ERROR** - Preflight failures, archival execution failures
- **CRITICAL** - Integrity failures, data loss risk

### Setting Up Discord Webhook

1. In Discord, go to Server Settings → Integrations → Webhooks
2. Create a new webhook for the #development channel
3. Copy the webhook URL
4. Configure in Woodpecker:

```bash
woodpecker-cli secret add \
  --repo gitea/chiseai/chiseai \
  --name discord_webhook_url \
  --value "https://discord.com/api/webhooks/..."
```

---

## Troubleshooting

### Common Issues

#### Preflight Check Failures

**Issue:** `Integrity validation failed`

```bash
# Check specific archive
python3 scripts/workflow/migration/verify_archive.py --archive-ref ARCH-20260309-...

# Re-verify all archives
python3 scripts/workflow/migration/verify_archive.py --all --verbose
```

**Issue:** `No completion evidence found`

Stories must have one of:
- `pr_number` (not null/N/A)
- `merge_commit` (not null/N/A)
- `remediation_pr_numbers` (non-empty list)
- `merge_commits` (non-empty list)

#### Archival Execution Failures

**Issue:** `Archival execution failed`

```bash
# Check disk space
df -h docs/archives/

# Verify permissions
ls -la docs/archives/workflow-status/entries/

# Run with verbose output
python3 scripts/workflow/automated_archive.py --verbose
```

**Issue:** `Batch size too large`

Reduce batch size:
```bash
python3 scripts/workflow/automated_archive.py --batch-size 5
```

#### Orphaned Archives

**Issue:** Health report shows orphaned archives

```bash
# List orphaned archives
python3 scripts/workflow/daily_health_report.py --verbose

# Manual cleanup (use with caution)
# Archives >7 days old without workflow entry may be safe to remove
```

### Debug Mode

Enable verbose logging:

```bash
# All scripts support --verbose
python3 scripts/workflow/preflight_archive.py --verbose
python3 scripts/workflow/automated_archive.py --verbose
python3 scripts/workflow/daily_health_report.py --verbose
```

### Emergency Procedures

#### Stop Automated Archival

To immediately stop automated archival:

1. Disable Woodpecker cron jobs:
   ```bash
   woodpecker-cli cron rm --repo gitea/chiseai/chiseai workflow-archive-weekly
   woodpecker-cli cron rm --repo gitea/chiseai/chiseai workflow-archive-daily
   ```

2. Or block at CI gate by setting environment variable:
   ```bash
   WORKFLOW_ARCHIVE_DISABLED=1
   ```

#### Data Loss Incident

If data loss is suspected:

1. **STOP** - Immediately disable archival automation
2. **ASSESS** - Run verification on all archives:
   ```bash
   python3 scripts/workflow/migration/verify_archive.py --all --verbose
   ```
3. **ROLLBACK** - Restore affected stories:
   ```bash
   python3 scripts/workflow/migration/rollback_archive.py --story-id ST-XXX --execute
   ```
4. **NOTIFY** - Alert team via Discord #development
5. **INVESTIGATE** - Review logs and identify root cause

---

## Discord Integration

### Channel Configuration

| Channel | ID | Purpose |
|---------|-----|---------|
| #development | `1448414506412806347` | Daily summaries, archival completion |
| #globalalerts | `1480675962785107968` | Critical alerts, integrity failures |

### Manual Notification

```bash
# Send test notification
python3 scripts/notifications/discord_workflow_notifier.py \
  --level INFO \
  --title "Test Notification" \
  --message "This is a test message"

# Send with custom fields
python3 scripts/notifications/discord_workflow_notifier.py \
  --level WARNING \
  --title "Health Check Warning" \
  --message "Orphaned archives detected" \
  --field "Count=5" \
  --field "Action=Review required"
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Yes | Discord webhook URL |
| `DISCORD_BOT_TOKEN` | No | For direct channel posting (fallback) |

---

## References

- **Story:** ST-WORKFLOW-ARCHIVAL-001
- **Archive Schema:** `docs/archives/workflow-status/schema/archive-entry-schema.yaml`
- **Migration Scripts:** `scripts/workflow/migration/`
- **CI Pipeline:** `.woodpecker/workflow-archive.yaml`
- **Workflow Status:** `docs/bmm-workflow-status.yaml`

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-09 | 1.0.0 | Initial Phase 4 automation runbook |
| 2026-03-09 | 1.1.0 | Task 4.1: Added completion evidence sections (Already Completed, Newly Implemented, Intentionally Deferred, Anti-Regression Rule) |
