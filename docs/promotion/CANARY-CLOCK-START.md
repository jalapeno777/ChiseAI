---
story_id: R2a
type: canary-clock
created: 2026-04-08
status: IN_PROGRESS
canary_type: paper-trading
start_utc: "2026-04-08T11:24:49+00:00"
expected_end_utc: "2026-04-29T11:24:49+00:00"
decision_window_utc: "2026-04-29T11:24:49+00:00 - 2026-05-06T11:24:49+00:00"
emitter_pid: 1559035
---

# R2a — Canary Clock Start Record

## Canary Execution Record

| Field                   | Value                                                 |
| ----------------------- | ----------------------------------------------------- |
| **Canary Start UTC**    | 2026-04-08T11:24:49+00:00                             |
| **Expected End UTC**    | 2026-04-29T11:24:49+00:00                             |
| **Decision Window UTC** | 2026-04-29T11:24:49+00:00 — 2026-05-06T11:24:49+00:00 |
| **Emitter PID**         | 1559035                                               |
| **Status**              | ACTIVE — running                                      |
| **Verification**        | health check passed 2026-04-08T11:24:49Z              |

## Checkpoint Schedule

| Milestone             | UTC Timestamp             | Days From Start |
| --------------------- | ------------------------- | --------------- |
| **Canary Start**      | 2026-04-08T11:24:49+00:00 | Day 0           |
| **Day 3 Checkpoint**  | 2026-04-11T11:24:49+00:00 | Day 3           |
| **Day 7 Checkpoint**  | 2026-04-15T11:24:49+00:00 | Day 7           |
| **Day 14 Checkpoint** | 2026-04-22T11:24:49+00:00 | Day 14          |
| **Day 21 Final**      | 2026-04-29T11:24:49+00:00 | Day 21          |

## Checkpoint Collection Commands

### Day 3 (2026-04-11) — Quick Health + Early Signal Check

```bash
# Emitter health
./scripts/paper_trading_manager.sh health

# Win rate
curl -s http://localhost:8001/api/v1/paper/metrics/win-rate | jq '.'

# Trade count
curl -s http://localhost:8001/api/v1/paper/positions | jq '.total_trades'

# Daily PnL
curl -s http://localhost:8001/api/v1/paper/pnl/daily | jq '{realized_pnl, unrealized_pnl, total_trades}'
```

### Day 7 (2026-04-15) — Weekly Milestone Check

```bash
# Full health
./scripts/paper_trading_manager.sh health

# Win rate
curl -s http://localhost:8001/api/v1/paper/metrics/win-rate | jq '.'

# Net return
curl -s http://localhost:8001/api/v1/paper/pnl/total | jq '.net_return_pct'

# Max drawdown
curl -s http://localhost:8001/api/v1/paper/risk/max-drawdown | jq '.'

# Sharpe ratio
curl -s http://localhost:8001/api/v1/paper/metrics/sharpe-ratio | jq '.'

# Total trade count
curl -s http://localhost:8001/api/v1/paper/positions | jq '.total_trades'

# Weekly summary
./scripts/ops/daily_summary.sh --mode=paper --date=2026-04-15
```

### Day 14 (2026-04-22) — Minimum Decision Point

```bash
# Full health
./scripts/paper_trading_manager.sh health

# All success criteria metrics
curl -s http://localhost:8001/api/v1/paper/metrics/win-rate | jq '.'
curl -s http://localhost:8001/api/v1/paper/pnl/total | jq '.net_return_pct'
curl -s http://localhost:8001/api/v1/paper/risk/max-drawdown | jq '.'
curl -s http://localhost:8001/api/v1/paper/metrics/sharpe-ratio | jq '.'
curl -s http://localhost:8001/api/v1/paper/positions | jq '.total_trades'

# Weekly summary
./scripts/ops/daily_summary.sh --mode=paper --date=2026-04-22
```

### Day 21 Final (2026-04-29) — Full Decision

```bash
# Full health
./scripts/paper_trading_manager.sh health

# All success criteria
curl -s http://localhost:8001/api/v1/paper/metrics/win-rate | jq '.'
curl -s http://localhost:8001/api/v1/paper/pnl/total | jq '.net_return_pct'
curl -s http://localhost:8001/api/v1/paper/risk/max-drawdown | jq '.'
curl -s http://localhost:8001/api/v1/paper/metrics/sharpe-ratio | jq '.'
curl -s http://localhost:8001/api/v1/paper/positions | jq '.total_trades'

# Generate final validation report
# See docs/promotion/R2a-canary-validation.md
```

## Pass/Fail Interim Rules

| Milestone | Pass Criteria                        | Action if Failed          |
| --------- | ------------------------------------ | ------------------------- |
| Day 3     | At least 3 trades executed           | Investigate execution gap |
| Day 7     | Win rate observable, no crashes      | Review and remediate      |
| Day 14    | ≥30 trades, no circuit breaker trips | Escalate to Aria          |
| Day 21    | All 5 criteria met (see below)       | Decision: GO or NO-GO     |

## Day 21 Success Criteria (from EP-LAUNCH-004)

| Metric               | Threshold   | Measurement                           |
| -------------------- | ----------- | ------------------------------------- |
| **Win Rate**         | ≥ 60%       | (Winning trades / Total trades) × 100 |
| **Net Return**       | ≥ 5%        | Total PnL / Initial capital           |
| **Maximum Drawdown** | ≤ 15%       | Peak-to-trough decline                |
| **Sharpe Ratio**     | ≥ 1.0       | (Return - Risk-free rate) / StdDev    |
| **Trade Count**      | ≥ 30 trades | Minimum for statistical significance  |

## Supporting Criteria

- Trade execution rate: > 95% for 24h
- System uptime: > 99.5%
- All safety assertions passing
- No duplicate orders
- No circuit breaker false triggers

## Canary Start Evidence

```
Execution Date: 2026-04-08
Start Timestamp (UTC): 2026-04-08T11:24:49+00:00
Initial Capital: (from paper account at start)
Execution Owner: R2a session (Jarvis)
Expected End Date: 2026-04-29
Decision Date: 2026-04-29 — 2026-05-06
```

**Started by**: R2a session on 2026-04-08
**Command used**: `./scripts/paper_trading_manager.sh start`
**Health verification**: `./scripts/paper_trading_manager.sh health` — ALL CHECKS PASSED
