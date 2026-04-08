---
story_id: R2a
type: canary-handoff
created: 2026-04-08
status: READY_FOR_EXECUTION
epic_ref: EP-LAUNCH-004
canary_type: paper-trading
required_duration_days: 21
earliest_decision_days: 21
minimum_decision_days: 14
---

# R2a — Canary Execution Handoff Packet

## 1. Overview

**Story ID**: R2a  
**Canary Type**: Paper Trading Execution  
**Epic Reference**: EP-LAUNCH-004 (Launch Readiness & Validation)  
**Created**: 2026-04-08  
**Status**: READY FOR EXECUTION

This canary requires a sustained 21-day paper trading run with real exchange data. Due to the required duration, execution cannot be completed in-session and must be handed off for external execution with decision review at day 21.

---

## 2. Canary Execution Command

### Primary Command

```bash
# Start paper trading continuous emitter
./scripts/paper_trading_manager.sh start

# Verify health after startup
./scripts/paper_trading_manager.sh health
```

### Alternative: Docker Compose (if script unavailable)

```bash
# Start paper trading via docker-compose
docker-compose up -d chiseai-paper-trading

# Verify status
docker-compose ps chiseai-paper-trading
```

### Prerequisites Check

Before starting, verify:

```bash
# 1. Verify paper trading mode is active
curl -s http://localhost:8001/api/v1/execution/mode | jq -r '.mode'
# Expected: "paper"

# 2. Check kill-switch status
./scripts/ops/kill_switch_check.sh
# Expected: ARMED

# 3. Verify Redis connectivity
redis-cli -p 6380 PING
# Expected: PONG

# 4. Check data freshness
curl -s http://localhost:8001/api/v1/health/data-freshness | jq '.sources | length'
# Expected: > 0 (data sources connected)
```

---

## 3. Required Duration & Decision Timeline

| Milestone             | Timing                 | Notes                              |
| --------------------- | ---------------------- | ---------------------------------- |
| **Canary Start**      | Day 0 (execution date) | Record start timestamp             |
| **Minimum Duration**  | 14 days                | EP-LAUNCH-004 minimum for decision |
| **Full Duration**     | 21 days                | Full canary period                 |
| **Earliest Decision** | Start + 21 days        | After 21 days of data              |
| **Decision Review**   | Start + 21-28 days     | Human review window                |

### Decision Criteria

The canary may be evaluated at day 14 if all success criteria are exceeded by 2x, but formal promotion decision requires day 21 data.

---

## 4. Success Criteria (EP-LAUNCH-004)

The canary must demonstrate the following metrics over the 21-day period:

| Metric               | Threshold   | Measurement                                      |
| -------------------- | ----------- | ------------------------------------------------ |
| **Win Rate**         | ≥ 60%       | (Winning trades / Total trades) × 100            |
| **Net Return**       | ≥ 5%        | Total PnL / Initial capital                      |
| **Maximum Drawdown** | ≤ 15%       | Peak-to-trough decline                           |
| **Sharpe Ratio**     | ≥ 1.0       | (Return - Risk-free rate) / StdDev of returns    |
| **Trade Count**      | ≥ 30 trades | Minimum sample size for statistical significance |

### Supporting Criteria (EP-LAUNCH-004)

- Trade execution rate: > 95% sustained for 24h
- System uptime: > 99.5%
- All safety assertions passing
- No duplicate orders
- No circuit breaker false triggers

---

## 5. Monitoring Guide

### Daily Monitoring Checklist

**Morning (9:00 AM)**:

```bash
# Check all services status
docker ps --filter 'name=chiseai' --format '{{.Names}}: {{.Status}}'

# Verify paper trading mode
curl -s http://localhost:8001/api/v1/execution/mode | jq '.'

# Check kill-switch status
./scripts/ops/kill_switch_check.sh
```

**Mid-Day (1:00 PM)**:

```bash
# Get daily PnL
curl -s http://localhost:8001/api/v1/paper/pnl/daily | jq '{
  realized_pnl: .realized_pnl,
  unrealized_pnl: .unrealized_pnl,
  total_trades: .total_trades
}'

# Check risk metrics
curl -s http://localhost:8001/api/v1/risk/metrics | jq '{
  exposure_pct: .exposure_pct,
  margin_utilization: .margin_utilization.utilization_pct
}'
```

**End-of-Day (5:00 PM)**:

```bash
# Generate daily summary
./scripts/ops/daily_summary.sh --mode=paper --date=$(date +%Y-%m-%d)

# Backup paper trading state
redis-cli -p 6380 BGSAVE
```

### Grafana Dashboard Monitoring

**URL**: `Grafana > Dashboards > ChiseAI - Paper Trading`

Key panels to monitor:

- **PnL Chart**: Realized and unrealized PnL over time
- **Position Table**: Current positions with sizes and values
- **Order Flow**: Orders executed in last hour
- **Risk Gauges**: Exposure, margin, concentration
- **Kill-Switch Status**: ARMED (green) indicator

**Alert Thresholds**:

- PnL Drawdown: >5% (Warning), >10% (Critical)
- Position Count: >20 (Warning)
- Order Failure Rate: >5% (Warning), >10% (Critical)

### Key Metrics to Record Weekly

| Week   | Win Rate | Net Return | Max DD | Sharpe | Trade Count |
| ------ | -------- | ---------- | ------ | ------ | ----------- |
| Week 1 |          |            |        |        |             |
| Week 2 |          |            |        |        |             |
| Week 3 |          |            |        |        |             |

---

## 6. Evidence Artifacts Created by R2a Session

### Implementation Evidence

| Artifact              | Path                                          | Status      |
| --------------------- | --------------------------------------------- | ----------- |
| This Canary Handoff   | `docs/promotion/R2a-CANARY-HANDOFF.md`        | ✅ Created  |
| R2 Decision Document  | `docs/promotion/R2-CANARY-REGATE-DECISION.md` | ✅ Existing |
| Paper Trading Runbook | `docs/runbooks/paper-trading-operations.md`   | ✅ Existing |

### Required Evidence Files (To Be Created During Canary)

| Artifact                 | Path                                          | Created During Canary |
| ------------------------ | --------------------------------------------- | --------------------- |
| Daily Summary Reports    | `logs/daily_summary_YYYY-MM-DD.json`          | Weekly                |
| Weekly Metrics Report    | `docs/evidence/R2a-weekly-metrics-WEEK{N}.md` | Weekly                |
| Canary Validation Report | `docs/promotion/R2a-canary-validation.md`     | Day 21                |

### Success Criteria Evidence Collection

At day 21, collect and document:

```bash
# Win rate calculation
curl -s http://localhost:8001/api/v1/paper/metrics/win-rate | jq '.'

# Net return
curl -s http://localhost:8001/api/v1/paper/pnl/total | jq '.net_return_pct'

# Max drawdown
curl -s http://localhost:8001/api/v1/paper/risk/max-drawdown | jq '.'

# Sharpe ratio
curl -s http://localhost:8001/api/v1/paper/metrics/sharpe-ratio | jq '.'

# Total trade count
curl -s http://localhost:8001/api/v1/paper/positions | jq '.total_trades'
```

---

## 7. Canary Execution Log

Record the following at execution start:

| Field                     | Value                        |
| ------------------------- | ---------------------------- |
| **Execution Date**        | (fill in)                    |
| **Start Timestamp (UTC)** | (fill in)                    |
| **Initial Capital**       | (fill in from paper account) |
| **Execution Owner**       | (assign responsibility)      |
| **Expected End Date**     | (start + 21 days)            |
| **Decision Date**         | (start + 21-28 days)         |

### Execution Start Record

```
Execution Date: _________________
Start Timestamp (UTC): _________________
Initial Capital: _________________
Execution Owner: _________________
Expected End Date: _________________
Decision Date: _________________
```

---

## 8. Post-Canary Actions

### If All Criteria Met (GO)

1. Generate final validation report: `docs/promotion/R2a-canary-validation.md`
2. Submit promotion packet for human approval
3. Proceed with EP-LAUNCH-004 story completion (ST-LAUNCH-017)

### If Criteria Not Met (NO-GO)

1. Document failure reasons in `docs/promotion/R2a-canary-validation.md`
2. Identify root causes and remediation items
3. Create follow-up story for re-canary or fix iteration
4. Do not proceed with launch readiness until criteria met

---

## 9. Related Documentation

### EP-LAUNCH-004 Stories

| Story ID      | Title                                 | SP  | Status        |
| ------------- | ------------------------------------- | --- | ------------- |
| ST-LAUNCH-015 | Load Testing & Performance Validation | 3   | (in progress) |
| ST-LAUNCH-016 | Runbook Validation & Documentation    | 2   | (planned)     |
| ST-LAUNCH-017 | Final E2E Validation & Go/No-Go       | 2   | (planned)     |

### Supporting Documents

- [Paper Trading Operations Runbook](docs/runbooks/paper-trading-operations.md)
- [LAUNCH Architecture Plan](docs/architecture/LAUNCH-ARCHITECTURE-PLAN.md)
- [EP-NS-008 Canary-Close Packet](docs/promotion/EP-NS-008-canary-close-packet.md) (reference pattern)
- [R2 Canary Re-Gate Decision](docs/promotion/R2-CANARY-REGATE-DECISION.md)

---

**Document Control**

| Version | Date       | Author      | Changes                       |
| ------- | ---------- | ----------- | ----------------------------- |
| 1.0     | 2026-04-08 | R2a Session | Initial canary handoff packet |

---

_This packet was generated for out-of-session canary execution. Record execution start and monitor daily per Section 5._
