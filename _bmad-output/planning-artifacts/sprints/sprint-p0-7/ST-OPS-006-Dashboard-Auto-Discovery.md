# ST-OPS-006: Dashboard Auto-Discovery

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-006 |
| **Title** | Dashboard Auto-Discovery |
| **Story Points** | 6 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Implement automatic dashboard discovery and registration system that scans for new dashboard JSON files and automatically provisions them without requiring Terraform changes or container restarts. This enables dynamic dashboard management and faster iteration cycles.

## Features Delivered

1. **File System Watcher**
   - Monitor dashboard directories for new/modified files
   - Detect dashboard JSON file changes in real-time
   - Trigger provisioning updates automatically

2. **Auto-Registration Service**
   - Python service for dashboard discovery
   - REST API endpoint for manual trigger
   - Integration with Grafana HTTP API

3. **Dashboard Metadata Extraction**
   - Parse dashboard JSON for title, tags, UID
   - Validate dashboard schema before provisioning
   - Extract and log dashboard dependencies

4. **Hot-Reload Capability**
   - Update dashboards without Grafana restart
   - Graceful handling of invalid dashboard files
   - Rollback on provisioning failures

## Dependencies

- ST-OPS-005: Grafana Provisioning Fix (must complete first - establishes provisioning foundation)
- ST-OPS-001: Grafana Dashboards (completed - base infrastructure exists)

## Acceptance Criteria

- [ ] AC1: Auto-discovery service runs as a container on `chiseai` network
- [ ] AC2: Service detects new dashboard files within 30 seconds of creation
- [ ] AC3: Valid dashboards are automatically provisioned via Grafana API
- [ ] AC4: Invalid dashboards are logged with specific error messages
- [ ] AC5: Dashboard updates are applied without Grafana restart
- [ ] AC6: Manual trigger endpoint available at `POST /api/v1/discover`
- [ ] AC7: Health check endpoint at `GET /health` returns discovery status

## Scope Globs

```yaml
implementation:
  - src/operations/dashboard_discovery/**
  - infrastructure/terraform/dashboard-discovery.tf
documentation:
  - docs/operations/dashboard-auto-discovery.md
tests:
  - tests/operations/test_dashboard_discovery.py
  - tests/integration/test_dashboard_discovery_e2e.py
```

## Verification Steps

1. Start auto-discovery service: `docker compose up dashboard-discovery`
2. Verify service health: `curl http://host.docker.internal:8080/health`
3. Create a new dashboard JSON file in monitored directory
4. Wait 30 seconds and verify dashboard appears in Grafana
5. Test manual trigger: `curl -X POST http://host.docker.internal:8080/api/v1/discover`
6. Create an invalid dashboard file and verify error logging
7. Update an existing dashboard file and confirm changes propagate

## Notes

- Use `watchdog` library for file system monitoring
- Grafana API requires admin credentials (use env vars)
- Consider implementing dashboard naming conventions for organization
- Log all discovery events for audit trail
