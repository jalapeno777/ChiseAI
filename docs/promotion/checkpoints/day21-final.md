---
story_id: R2a
checkpoint: day21_final
scheduled_utc: "2026-04-29T11:24:49+00:00"
status: COMPLETED
completed_utc: "2026-05-02T14:35:00+00:00"
decision_window_utc: "2026-04-29T11:24:49+00:00 - 2026-05-06T11:24:49+00:00"
epic_ref: EP-LAUNCH-004
---

# R2a — Day 21 Final Checkpoint Report

**Scheduled**: 2026-04-29T11:24:49+00:00
**Status**: COMPLETED
**Decision Window**: 2026-04-29T11:24:49+00:00 — 2026-05-06T11:24:49+00:00

---

## Final Metrics

| Metric       | Value | Threshold | Pass? |
| ------------ | ----- | --------- | ----- |
| Win Rate     | TBD   | ≥ 60%     | —     |
| Net Return   | TBD   | ≥ 5%      | —     |
| Max Drawdown | TBD   | ≤ 15%     | —     |
| Sharpe Ratio | TBD   | ≥ 1.0     | —     |
| Trade Count  | TBD   | ≥ 30      | —     |

**Note on metrics**: Win rate, net return, max drawdown, Sharpe ratio, and trade count CANNOT be determined from available evidence. Grafana, InfluxDB, and Postgres are all down. Only Redis data is available, which contains signal pipeline data but not trade outcome data.

**Signals Generated**: 9,000 (over ~21 day period from 2026-04-07 to 2026-04-27)
**Signal Rate**: ~428 signals/day average
**Last Signal Timestamp**: 2026-04-27T04:52:51 UTC (Unix: 1777265571)
**Signal Gap**: 133.8 hours (5.6 days) — exceeds 2-hour threshold

---

## Signal Pipeline Analysis

### Signal Count by Day (Top 10)

```
25 signals on 2026-04-26T23:27:02
24 signals on 2026-04-27T04:40:19
24 signals on 2026-04-27T03:29:39
24 signals on 2026-04-27T01:39:59
24 signals on 2026-04-26T23:27:30
23 signals on 2026-04-27T00:27:28
21 signals on 2026-04-27T03:28:42
21 signals on 2026-04-27T00:27:54
20 signals on 2026-04-27T03:29:37
20 signals on 2026-04-27T03:28:17
```

### Signal Distribution

- Total signals: 9,000
- Timeframe distribution: 15m, 1h, 4h, 1d (based on sample)
- Token pairs: BTC/USDT, ETH/USDT
- Directions: LONG, SHORT
- Confidence range: 0.60 - 0.84 (sample)

### Most Recent Signals (from index)

Last 5 signals from `paper:index:signals`:

1. `9927abdb-b26a-40a2-a9b5-58afb72a4c15` — score 1777265571.797697 (2026-04-27T04:52:51 UTC)
2. `35c75656-8fdf-46fa-9e2f-17862bb452e9` — score 1777265571.745659
3. `8bf79e99-74f6-4e04-b46b-049cff8bb92f` — score 1777265571.797697

### Last Signal Content (Sample)

```
signal_id: 89b13a7a-7d1b-4033-8b9b-3ed31df3b3bc
token: BTC/USDT
direction: SHORT
confidence: 0.84
timestamp: 2026-04-27T04:51:51.271737+00:00
status: actionable
timeframe: 15m
mode: paper
stored_at: 2026-04-27T04:51:51.271790+00:00
```

---

## Health Status

### Docker Container Status (2026-05-02)

```
CONTAINER                          STATUS                          STATE
chiseai-signal-supervisor           Up 45 hours (healthy)          running
chiseai-paper-trading-consumer      Exited (255) 2 weeks ago        exited
chiseai-paper-trading-executor      Up 45 hours (healthy)          running
chiseai-ohlcv-ingestion             Restarting (0) 53 seconds ago  restarting
chiseai-brain-scheduler             Up 45 hours (healthy)          running
chiseai-redis                       Up 29 minutes                  running
chiseai-postgres                    Exited (255) 45 hours ago       exited
chiseai-influxdb                    Exited (255) 45 hours ago       exited
chiseai-grafana                     Exited (255) 2 weeks ago        exited
```

### Signal Supervisor Logs (Most Recent)

```
2026-05-02 14:34:48,709 - __main__ - ERROR - Too many restarts (10 in last hour), backing off for 5 minutes
2026-05-02 14:29:57,413 - __main__ - ERROR - Too many restarts (10 in last hour), backing off for 5 minutes
2026-05-02 14:25:06,037 - __main__ - ERROR - Too many restarts (10 in last hour), backing off for 5 minutes
...
2026-05-02 13:55:44,452 - __main__ - INFO - Starting signal generator...
2026-05-02 13:55:44,453 - __main__ - INFO - Signal generator started with PID 29521
2026-05-02 13:55:44,453 - __main__ - INFO - Total restarts this session: 421
```

**Total restarts recorded**: 430+ (still incrementing)

### Key Health Indicators

- `paper_trading:status` = "active" (Redis)
- `bmad:chiseai:bybit_truth:watchdog:status` = "fresh" (Redis)
- Signal supervisor container is healthy but signal generator is in restart loop
- Paper trading consumer container is Exited (255)
- OHLCV ingestion is in restart loop

### Redis Data Health

- Redis restarted 2026-05-02 14:06:26 (after ~16 days downtime)
- RDB age at load: 1,371,979 seconds (~16 days)
- Keys loaded: 13,021
- Current accepting connections on port 6380

---

## Supporting Criteria

| Criteria                          | Status      |
| --------------------------------- | ----------- |
| Trade execution rate > 95%        | UNAVAILABLE |
| System uptime > 99.5%             | UNAVAILABLE |
| All safety assertions passing     | UNAVAILABLE |
| No duplicate orders               | UNAVAILABLE |
| No circuit breaker false triggers | UNAVAILABLE |

**Note**: Grafana, InfluxDB, and Postgres are all down/unavailable. Trade outcome data is not accessible via Redis. Only signal pipeline data (9,000 signals) is confirmed available.

---

## Signal Pipeline Status

**OPERATIONAL**: Signal generator was producing signals until 2026-04-27T04:52:51 UTC
**DEGRADED**: Signal generator is now in crash-loop restart mode
**DOWN**: No signals generated since 2026-04-27 (5.6 days ago)

**Signal Gap Analysis**:

- Last signal: 2026-04-27T04:52:51 UTC
- Current time: 2026-05-02T14:35:00 UTC
- Gap: 133.8 hours (exceeds 2-hour threshold)
- Signal generation: NOT OPERATIONAL (in restart loop)

All 5 EP-LAUNCH-004 criteria unmeasurable due to infrastructure collapse (Grafana, InfluxDB, Postgres all Exited). Supporting evidence: signal gap 133.8h, signal generator crash-loop (421+ restarts), paper-trading-consumer Exited (255).

---

## Final Verdict

**NO-GO** — Signal pipeline is not generating signals

### Reasons for NO-GO:

1. **Signal gap exceeds threshold**: 133.8 hours since last signal (threshold: 2 hours)
2. **Signal generator in restart loop**: chiseai-signal-supervisor logs show continuous restarts (421+ restarts recorded, still incrementing)
3. **Paper trading consumer down**: Container exited with code 255 two weeks ago
4. **Unavailable metrics**: Win rate, net return, max drawdown, Sharpe ratio, trade count cannot be determined from available data (Grafana, InfluxDB, Postgres all down)

### What's Working:

- Signal supervisor container is healthy
- Redis is operational with all signal data preserved
- Paper trading executor is healthy
- `paper_trading:status` in Redis = "active"
- `bybit_truth:watchdog:status` = "fresh"

### What's Broken:

- Signal generator (crash-loop restart)
- OHLCV ingestion (restarting)
- Grafana, InfluxDB, Postgres (all Exited)
- Trade outcome tracking (cannot measure)

---

## Promotion Packet

See: `docs/promotion/R2a-canary-validation.md`

---

## Notes

- Canary R2A-20260412 started 2026-04-08, expected end 2026-04-29 (TOMORROW)
- Day-7 checkpoint (2026-04-19): NOT EVALUATED — status was SCHEDULED, all metrics TBD, no health check run at scheduled time
- Day-14 checkpoint (2026-04-22): Never formally evaluated due to crash-loop fix mid-day
- Day-21 checkpoint (2026-04-29): Completed retroactively at 2026-05-02
- Redis was down for ~16 days and restarted 2026-05-02 14:06:26
- Signal data preserved in Redis (9,000 signals from period 2026-04-07 to 2026-04-27)
- All metric data (win rate, return, drawdown, Sharpe, trade count) requires Grafana/InfluxDB/Postgres which are all unavailable
- Signal generator crash-loop prevents new signal generation

**Recommendation**: Investigate and fix signal generator restart loop before any further evaluation. Current evidence is insufficient to recommend promotion due to inability to measure trading performance metrics and >5-day signal gap.
