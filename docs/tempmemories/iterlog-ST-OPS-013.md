---
story_id: ST-OPS-013
story_title: Grafana Datasource Provisioning with Env Var Token Wiring
epic_id: EP-OPS-001
story_points: 3
phase: implementation
status: completed
started_at: 2026-02-12T00:00:00Z
completed_at: 2026-02-12T00:15:00Z
---

# ST-OPS-013 Iteration Log

## Metadata
- Story ID: ST-OPS-013
- Story Title: Grafana Datasource Provisioning with Env Var Token Wiring
- Epic ID: EP-OPS-001
- Story Points: 3
- Phase: implementation
- Status: completed
- Started: 2026-02-12T00:00:00Z
- Completed: 2026-02-12T00:15:00Z

## Acceptance Criteria
- AC1: grafana container mounts provisioning dir to /etc/grafana/provisioning ✅
- AC2: grafana container gets INFLUXDB_TOKEN env var ✅
- AC3: After terraform apply, Grafana has ChiseAI InfluxDB datasource ⏳
- AC4: Docs: runbook for env var and datasource verification ✅
- AC5: Update bmm-workflow-status.yaml and validation-registry.yaml ✅
- AC6: PR merged to protected main with green CI ⏳

## Key Decisions
1. Use Grafana container env vars for InfluxDB auth: Grafana supports env var interpolation in datasource provisioning YAML (${INFLUXDB_TOKEN}). Passing token via Terraform env var keeps secrets out of repo and allows easy configuration.

## Learnings
1. Terraform bind mount for Grafana provisioning requires read_only=true and abspath() for reliable host path resolution.

## Files Changed
- infrastructure/terraform/main.tf (added env vars and volume mount)
- docs/bmm-workflow-status.yaml (added ST-OPS-013)
- docs/validation/validation-registry.yaml (added V-OPS-013)
- docs/operations/grafana-datasource-provisioning.md (new runbook)
- docs/tempmemories/iterlog-ST-OPS-013.md (this file)
