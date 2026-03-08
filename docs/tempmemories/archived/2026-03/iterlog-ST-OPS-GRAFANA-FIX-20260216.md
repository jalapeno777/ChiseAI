---
project: ChiseAI
scope: observability
type: decision
story_id: ST-OPS-GRAFANA-FIX-20260216
story_title: Grafana dashboard data fixes and monitor deployment
phase: testing
status: completed
started_at: "2026-02-16T03:10:00Z"
completed_at: "2026-02-16T03:20:00Z"
tags: [grafana, influxdb, datasource-health, dashboard]
---

## Decisions
- Patched `data-freshness` dashboard queries to aggregate per source and tolerate sparse intervals (30m window).
- Fixed `is_stale` type handling in Flux (`int` vs `bool`) for status table.
- Patched `backtest-kpis` variable and comparison-table queries to avoid Flux runtime errors with `keys()` and `last()` after `pivot`.
- Added Influx export support to `scripts/run_datasource_health_monitor.py` for `datasource_health` and `datasource_alerts` measurements.
- Added Terraform container `chiseai-datasource-health-monitor` and tightened data-quality monitor healthcheck process match.

## Learnings
- Running Terraform from an isolated worktree without matching state context can produce an unsafe full-create plan. Apply must run from canonical infra state context.
- Existing Influx already contains `data_freshness`, `backtest_kpis`, and `ohlcv`; many no-data panels were query-shape/runtime issues rather than ingestion absence.

## Scope Ownership
- Scope: `infrastructure/grafana/provisioning/dashboards/*`, `infrastructure/terraform/main.tf`, `scripts/run_datasource_health_monitor.py`
- Owner: `ST-OPS-GRAFANA-FIX-20260216`

## Incidents
- Terraform plan from isolated worktree produced full-create drift due state context mismatch; no apply executed from this context.
