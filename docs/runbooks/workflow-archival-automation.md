# Workflow Archival Automation Runbook

> **Story:** ST-WORKFLOW-ARCHIVAL-001  
> **Version:** 1.0.0  
> **Last Updated:** 2026-03-09  
> **Owner:** senior-dev

## Table of Contents

1. [Overview](#overview)
2. [Automation Schedule](#automation-schedule)
3. [Preflight Guard](#preflight-guard)
4. [Manual Execution](#manual-execution)
5. [Rollback Procedures](#rollback-procedures)
6. [Monitoring and Alerting](#monitoring-and-alerting)
7. [Troubleshooting](#troubleshooting)
8. [Discord Integration](#discord-integration)

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
