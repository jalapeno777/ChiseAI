# ST-OPS-009: Backup & Versioning

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-009 |
| **Title** | Dashboard Backup & Versioning |
| **Story Points** | 5 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Implement automated backup and versioning system for Grafana dashboards to ensure data durability and enable point-in-time recovery. This includes scheduled backups, version history, and disaster recovery procedures for dashboard configurations.

## Features Delivered

1. **Automated Backup Service**
   - Scheduled backups of all dashboard configurations
   - Export via Grafana API to JSON files
   - Compression and storage optimization

2. **Version History Management**
   - Git-based versioning for dashboard changes
   - Automatic commits on dashboard modifications
   - Branch-based versioning for experiments

3. **Backup Storage**
   - Local storage with rotation policy
   - Optional cloud storage integration (S3-compatible)
   - Encrypted backup storage

4. **Disaster Recovery**
   - One-click dashboard restore from backup
   - Point-in-time recovery capability
   - Cross-environment migration tools

## Dependencies

- ST-OPS-005: Grafana Provisioning Fix (should complete first - backup provisioned dashboards)
- ST-OPS-006: Dashboard Auto-Discovery (parallel - may share discovery logic)
- ST-OPS-001: Grafana Dashboards (completed - dashboards to backup exist)

## Acceptance Criteria

- [ ] AC1: Backup service runs daily at 02:00 UTC
- [ ] AC2: All dashboards exported to `backups/grafana/YYYY-MM-DD/` directory
- [ ] AC3: Backups retained for 30 days with automatic cleanup
- [ ] AC4: Restore script exists at `scripts/restore_dashboards.py`
- [ ] AC5: Backup verification test runs weekly
- [ ] AC6: Discord notification on backup success/failure
- [ ] AC7: Documentation for disaster recovery procedures

## Scope Globs

```yaml
implementation:
  - src/operations/dashboard_backup/**
  - scripts/backup_dashboards.py
  - scripts/restore_dashboards.py
  - infrastructure/terraform/dashboard-backup.tf
documentation:
  - docs/operations/dashboard-backup-recovery.md
tests:
  - tests/operations/test_dashboard_backup.py
  - tests/integration/test_backup_restore_e2e.py
```

## Verification Steps

1. Run backup manually: `python scripts/backup_dashboards.py`
2. Verify backup files created in `backups/grafana/` directory
3. Check backup file contents include all dashboard JSON
4. Delete a test dashboard from Grafana
5. Run restore script: `python scripts/restore_dashboards.py --date YYYY-MM-DD`
6. Verify dashboard is restored correctly
7. Test automatic cleanup of backups older than 30 days

## Notes

- Use Grafana's `/api/dashboards/uid/{uid}` API for exports
- Consider implementing incremental backups for efficiency
- Encrypt backups if storing in shared/cloud storage
- Document RTO (Recovery Time Objective) and RPO (Recovery Point Objective)
