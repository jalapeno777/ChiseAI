# R2A Canary Day 7 Checkpoint Plan

**Canary ID:** R2A-20260412  
**Checkpoint Date:** 2026-04-19 (Day 7)  
**Canary Start:** 2026-04-12  
**Canary Duration:** 21 days  
**Next Checkpoint:** Day 14 (2026-04-26)

---

## 1. Evaluation Criteria

### Signal Pipeline Health

- Signals generated in last 7 days
- Average signals/day trend
- Signal latency (generation to emission)

### Fill Tracking Accuracy

- Compare fills against Bybit demo API truth
- Fill rate percentage
- Tracking discrepancy rate (must be <10%)

### P&L Trajectory

- Daily P&L over 7 days
- Cumulative P&L
- P&L vs baseline expectation

### Max Drawdown

- Peak-to-trough drawdown measured daily
- Must remain within acceptable bounds (<5% target, >10% = No-Go)

### Container Uptime

- Target: >99.5%
- Measured across all containers in canary stack

### Data Freshness

- OHLCV data age consistently <60 seconds
- Check for any data gaps or staleness events

---

## 2. Data Sources

### Grafana Dashboard

- Dashboard UID: r2a-canary-health
- Panels: 11 panels covering health, trades, portfolio, data freshness

### InfluxDB Measurements

- `paper_emitter_health` — signal pipeline health metrics
- `paper_trades` — fill and trade records
- `paper_portfolio` — P&L and position tracking
- `data_freshness` — OHLCV data age metrics

### Redis Keys

- `bmad:chiseai:canary:R2A-20260412` — canary state and config
- `bmad:chiseai:canary:PAPER-CANARY-STRICT-002` — strict canary baseline

### Discord Evidence

- Channel: #trading
- Collect message IDs from relevant signal/fill/P&L events in the past 7 days

---

## 3. Go Criteria (Continue to Day 14)

| Metric           | Threshold                                          |
| ---------------- | -------------------------------------------------- |
| Signal pipeline  | Operational throughout week 1, no outages >2 hours |
| Fill tracking    | Discrepancy rate <10%                              |
| Fill rate        | >90% of expected fills received                    |
| Max drawdown     | <5% of paper budget                                |
| Container uptime | >99%                                               |
| Data freshness   | OHLCV age <60s consistently                        |

**If ALL criteria met:** → GO signal → Continue to Day 14

---

## 4. No-Go Criteria (Pause and Investigate)

| Metric                    | Threshold                    |
| ------------------------- | ---------------------------- |
| Signal pipeline           | Down for >2 hours cumulative |
| Fill tracking discrepancy | >10%                         |
| Max drawdown              | >10% of paper budget         |
| Capital safety invariant  | Any breach                   |

**If ANY criterion breached:** → NO-GO signal → Pause canary, escalate to Craig

---

## 5. Decision Authority

| Role  | Responsibility                                                       |
| ----- | -------------------------------------------------------------------- |
| Aria  | Evaluates all metrics, produces evidence packet, recommends GO/NO-GO |
| Craig | Reviews Aria's recommendation, makes final Go/No-Go decision         |

---

## 6. Evidence Packet (Produced by Aria)

The evidence packet for this checkpoint must contain:

1. **Signal Pipeline Report**
   - Total signals generated (7-day count)
   - Avg signals/day with trend indicator
   - Any pipeline interruptions and duration

2. **Fill Tracking Report**
   - Fill rate vs expected
   - Discrepancy count and percentage
   - Sample discrepancy events for audit

3. **P&L Report**
   - Day-by-day P&L table
   - Cumulative P&L chart description
   - Drawdown series

4. **Infrastructure Report**
   - Container uptime percentage per container
   - Any restarts or failures
   - Data freshness stats

5. **Go/No-Go Recommendation**
   - Summary of all metrics
   - Clear GO or NO-GO call with rationale
   - Required Craig approval

---

## 7. Day 14 Preview (Next Checkpoint)

Day 14 (2026-04-26) will evaluate:

- **Trend analysis:** 2-week signal consistency
- **P&L trajectory:** Continued paper performance
- **Drawdown accumulation:** Rolling 14-day max drawdown
- **Strategy turnover:** If any new strategies activated during week 2
- **Infrastructure stability:** Sustained uptime record

---

## 8. Emergency Contacts

| Role        | Contact       |
| ----------- | ------------- |
| On-call SRE | Via PagerDuty |
| Aria        | @aria         |
| Craig       | @craig        |

---

_Document generated: 2026-04-13_
_Framework reference: ST-LAUNCH-017 (Go/No-Go Framework)_
