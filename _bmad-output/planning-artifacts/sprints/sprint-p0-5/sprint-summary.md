# Sprint Summary: Observability (Grafana-First)

## Sprint Information

| Field | Value |
|-------|-------|
| **Sprint ID** | p0-5 |
| **Sprint Name** | Observability (Grafana-First) |
| **Phase** | Phase 1 (Foundation) |
| **Status** | planned |
| **Start Date** | 2026-02-08 |
| **Target Finish** | 2026-05-09 (90-day window) |

## Epics Covered

| Epic ID | Epic Name | Stories | Points |
|---------|-----------|---------|--------|
| EP-OPS-001 | Grafana-first Observability | 4 | 14 |

## Stories

### EP-OPS-001: Grafana-first Observability (4 stories, 14 points)

| Story ID | Title | Points | Priority | Status |
|----------|-------|--------|----------|--------|
| ST-OPS-001 | Grafana Dashboards - Data & Backtest KPIs | 4 | P0-CRITICAL | planned |
| ST-OPS-002 | Grafana Dashboards - Paper & Live Execution | 4 | P0-CRITICAL | planned |
| ST-OPS-003 | Alerting Runbook + Automation | 3 | P1-HIGH | planned |
| ST-OPS-004 | Taiga Sync (Story Status Monitoring) | 3 | P1-HIGH | planned |

## Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Stories** | 4 |
| **Total Story Points** | 14 |
| **P0-CRITICAL Stories** | 2 |
| **P1-HIGH Stories** | 2 |

## Dependencies

### Internal Dependencies
- ST-OPS-001 (Data/Backtest dashboards) can start with Sprint p0-2 completion
- ST-OPS-002 (Execution dashboards) requires Sprint p0-4 completion
- ST-OPS-003 (Alerting) depends on both dashboard stories
- ST-OPS-004 (Taiga Sync) requires Taiga instance access

### External Dependencies
- Grafana instance (deployed via Terraform on chiseai network)
- InfluxDB as data source for time-series metrics
- Taiga API access for story status sync
- Discord webhook for alert routing

### Sprint Dependencies
- Sprint p0-2 (Data & Backtesting) must complete for data/backtest dashboards
- Sprint p0-4 (Execution) must complete for execution dashboards

## Success Criteria

1. **All P0-CRITICAL stories completed** (2 stories)
2. **Data freshness visible** - Last update timestamps per source in Grafana
3. **Backtest KPIs displayed** - Sharpe, drawdown, win rate panels updating
4. **Execution dashboards operational** - Orders, fills, PnL, kill-switch state visible
5. **Alerting runbooks created** - API disconnect, data gaps, order rejects, drift
6. **Taiga sync functional** - Repo story status synced to Taiga hourly
7. **Dashboards version-controlled** - JSON exportable and deployable via IaC

## Dashboards

| Dashboard | Purpose | Key Panels |
|-----------|---------|------------|
| Data Health | Monitor data ingestion | Freshness, gaps, latency per source |
| Backtest KPIs | Track backtest performance | Sharpe, drawdown, win rate, trade count |
| Paper Trading | Monitor paper execution | Orders, fills, PnL, kill-switch state |
| Live Trading | Monitor live execution | Same as paper + risk metrics |
| System Health | Overall system status | Service health, error rates, alerts |

## Alerting Runbooks

| Scenario | Alert Channel | Runbook Location |
|----------|---------------|------------------|
| API disconnect | Discord #alerts | docs/runbooks/api-disconnect.md |
| Data gaps | Discord #alerts | docs/runbooks/data-gaps.md |
| Order rejects | Discord #alerts | docs/runbooks/order-rejects.md |
| Model drift | Discord #alerts | docs/runbooks/model-drift.md |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Grafana performance with high cardinality | Medium | Optimize queries, use recording rules |
| Alert fatigue | Medium | Tune thresholds, <5 false positives/day |
| Taiga API rate limits | Low | Batch updates, implement backoff |

## Notes

- Grafana is the primary observability platform (Grafana-first approach)
- Dashboards should load within 3 seconds for standard viewport
- All dashboard JSON should be version-controlled in infrastructure/terraform/
- Taiga sync is one-way (repo -> Taiga) to maintain repo as source of truth
