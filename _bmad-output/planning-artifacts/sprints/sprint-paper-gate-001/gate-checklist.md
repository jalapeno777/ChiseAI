# Gate Checklist: Sprint PAPER-GATE-001

## Canary Gate Criteria

| Criterion | Threshold | Monitoring Interval | Auto-Enforce |
|-----------|-----------|-------------------|--------------|
| Max Drawdown | 5% | 15 minutes | Yes - auto-halt if breached |
| Min Win Rate | 55% | 15 minutes | Yes - flag if below (min 10 trades) |
| Canary Duration | 7 days minimum | Daily | No - human reviews at completion |
| Portfolio Allocation | 10% max | 15 minutes | Yes - hard cap enforced |
| Leverage | 3x max | Per-trade | Yes - rejected if exceeded |

---

## Pre-Flight Checklist

### Data Infrastructure

- [ ] **PF-01**: Data feeds active and <5min freshness (ST-DATA-001, ST-DATA-002)
  - Verification: Grafana data freshness panel shows green
  - Fallback: Manual `curl` check against InfluxDB

- [ ] **PF-02**: InfluxDB KPI storage functional (ST-OPS-011)
  - Verification: Write test metric, read back successfully
  - Fallback: Check container logs for errors

- [ ] **PF-03**: Continuous backtest runner operational (ST-DATA-003)
  - Verification: Recent backtest results in InfluxDB
  - Fallback: Manual backtest trigger and result check

### Monitoring Infrastructure

- [ ] **PF-04**: Grafana market analysis dashboard renders (ST-OPS-001)
  - Verification: All panels load without errors
  - Fallback: Screenshot evidence of working panels

- [ ] **PF-05**: Grafana paper execution dashboard renders (ST-OPS-002)
  - Verification: Paper trading panels configured and loading
  - Fallback: Manual panel check via Grafana API

- [ ] **PF-06**: Discord webhook functional (ST-NS-009)
  - Verification: Test message sent and received
  - Fallback: Check webhook URL and permissions

### Execution Infrastructure

- [ ] **PF-07**: Kill-switch armed and visible in Grafana (ST-EX-003)
  - Verification: Kill-switch state = ARMED in Grafana
  - Fallback: Direct Redis state check

- [ ] **PF-08**: Bybit demo account connected (ST-EX-001)
  - Verification: API connection test returns account info
  - Fallback: Manual API key validation

- [ ] **PF-09**: Strategy registry has champion strategy (ST-SIG-002)
  - Verification: Registry query returns active champion
  - Fallback: Manual registry inspection

### Safety Checks

- [ ] **PF-10**: Risk caps configured (per-trade 1%, per-grid 2%, leverage 3x)
  - Verification: Config file review + runtime validation
  - Fallback: Manual config inspection

- [ ] **PF-11**: Position sizing formulas correct
  - Verification: Unit test pass for sizing calculations
  - Fallback: Manual calculation check

- [ ] **PF-12**: Rollback procedure documented
  - Verification: Runbook exists in operational docs
  - Fallback: Create ad-hoc rollback steps

---

## Canary Activation Checklist

- [ ] **CA-01**: All pre-flight checks passed (PF-01 through PF-12)
- [ ] **CA-02**: Human approval received to START canary
- [ ] **CA-03**: Canary configuration deployed (10% allocation, BTC, gate criteria)
- [ ] **CA-04**: First paper trade executed successfully
- [ ] **CA-05**: 15-minute monitoring interval verified (at least 4 consecutive checks)
- [ ] **CA-06**: Kill-switch trigger test completed (trigger and reset)

---

## Gate Monitoring Checklist (During 7-Day Canary)

### Daily Checks

- [ ] **GM-D1**: Drawdown within 5% threshold
- [ ] **GM-D2**: Win rate tracking (55% target, requires min 10 trades)
- [ ] **GM-D3**: Monitoring interval logs present (96 checks/day expected)
- [ ] **GM-D4**: No kill-switch triggers (or documented recovery)
- [ ] **GM-D5**: Data feeds remain fresh (<5min)

### Day 3 Milestone

- [ ] **GM-M3-01**: At least 5 trades executed
- [ ] **GM-M3-02**: Drawdown <3% (early warning threshold)
- [ ] **GM-M3-03**: No data feed interruptions >15min
- [ ] **GM-M3-04**: Monitoring uptime >99%

### Day 7 Completion

- [ ] **GM-M7-01**: Minimum 10 trades executed
- [ ] **GM-M7-02**: Win rate >= 55% (calculated over all trades)
- [ ] **GM-M7-03**: Max drawdown never exceeded 5%
- [ ] **GM-M7-04**: Monitoring uptime >= 99%
- [ ] **GM-M7-05**: No unresolved kill-switch events

---

## Evidence Collection Checklist

### Promotion Packet Requirements

- [ ] **EP-01**: Trade log (all trades with timestamps, prices, sizes)
- [ ] **EP-02**: KPI summary (Sharpe, drawdown, win rate, trade count)
- [ ] **EP-03**: Equity curve visualization (from Grafana)
- [ ] **EP-04**: Risk metrics summary (leverage used, margin, exposure)
- [ ] **EP-05**: Monitoring uptime report
- [ ] **EP-06**: Kill-switch event log (if any)
- [ ] **EP-07**: Data feed quality report
- [ ] **EP-08**: Strategy configuration snapshot
- [ ] **EP-09**: Backtest comparison (paper results vs backtest predictions)
- [ ] **EP-10**: Human-readable executive summary

### Promotion Decision Criteria

| Criterion | Pass | Fail | Action on Fail |
|-----------|------|------|----------------|
| Max DD <5% | Continue | Stop canary | Review parameters, restart |
| Win Rate >55% | Continue | Flag for review | Extend canary or adjust strategy |
| 7-day duration met | Eligible | Not eligible | Continue until met |
| Min 10 trades | Valid WR | Invalid WR | Extend canary |
| Monitoring >99% uptime | Valid evidence | Incomplete | Fix monitoring, restart clock |

---

## Rollback Plan

### Trigger Conditions

1. Drawdown exceeds 5% (automatic)
2. Kill-switch triggered (automatic)
3. Data feeds stale >30 minutes (manual review)
4. Human override requested

### Rollback Steps

1. Kill-switch triggers (or manual trigger): all positions closed
2. Canary allocation set to 0%
3. Incident logged in Redis: `bmad:chiseai:iterlog:story:PAPER-GATE-001:incidents`
4. Post-mortem analysis within 24 hours
5. Restart decision requires human approval

---

*Document created: 2026-02-13*
*Last updated: 2026-02-13*
