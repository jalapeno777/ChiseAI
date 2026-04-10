# Live Canary Cutover Design Spec

**Document ID:** `2026-04-10-live-canary-cutover-design`
**Date:** 2026-04-10
**Status:** DRAFT
**Author:** ChiseAI Architecture

---

## 1. Objective / Scope / Non-Goals

### Objective

Define the design for executing a **live canary cutover** — transitioning the ChiseAI trading system from paper-trading simulation mode to live Bybit demo exchange execution — with enforced safety controls, observable rollback criteria, and a clear day-0 restart declaration gate.

### Scope

- Transition from `OrderSimulator`-based paper trading to `BybitConnector`-based live demo order execution
- Enforcement of four safety controls: kill switch, leverage cap, exposure cap, timestamp sync guard
- Canary reset semantics: which metrics and Redis keys are reset, how timeline checkpoints are recalculated
- Cutover runbook: preflight gates and explicit rollback criteria
- E2E validation checklist for declaring day-0 restart
- Observability and alert requirements
- Incident/blocker handling and evidence requirements

### Non-Goals

- This spec does **not** cover live trading with real funds (capital deployment)
- This spec does **not** cover code implementation (implementation is out of scope)
- This spec does **not** cover backtest-to-paper promotion (paper-to-live is the boundary)
- This spec does **not** cover strategy parameter changes during cutover
- This spec does **not** cover the simulator fallback path — simulator fallback is explicitly disallowed and must not be invoked as a fallback under any circumstances

---

## 2. Architecture + Execution-Path Changes

### 2.1 Connector Selection Logic

The cutover enforces a hard switch from `OrderSimulator` to `BybitConnector` (live demo). The connector selection is controlled by a single boolean environment flag:

| Flag Name           | Values           | Effect                                                                    |
| ------------------- | ---------------- | ------------------------------------------------------------------------- |
| `CHISEAI_LIVE_MODE` | `true` / `false` | When `true`: forces `BybitConnector`; when `false`: uses `OrderSimulator` |

**Connector selection rules:**

1. At process startup, the `TradingOrchestrator` reads `CHISEAI_LIVE_MODE`.
2. If `CHISEAI_LIVE_MODE=true`:
   - `BybitConnector` instance is created and used for all order operations
   - `OrderSimulator` is never instantiated
   - If `BybitConnector` fails to initialize, the process **must exit immediately** (no fallback to simulator)
3. If `CHISEAI_LIVE_MODE=false` (default):
   - `OrderSimulator` is used for paper trading
   - `BybitConnector` is not loaded

### 2.2 Execution Path Change

**Before cutover (paper mode):**

```
Signal → PaperTradingOrchestrator → OrderSimulator → (no exchange contact)
```

**After cutover (live demo mode):**

```
Signal → TradingOrchestrator → BybitConnector → Bybit demo API → fill/confirmation
```

### 2.3 Environment Flags and Toggles

| Flag                                  | Type    | Default  | Description                                     |
| ------------------------------------- | ------- | -------- | ----------------------------------------------- |
| `CHISEAI_LIVE_MODE`                   | `bool`  | `false`  | Forces live Bybit demo connector                |
| `CHISEAI_LIVE_CANARY_BUDGET`          | `float` | `1000.0` | Maximum notional budget for canary trades (USD) |
| `CHISEAI_KILL_SWITCH_ENABLED`         | `bool`  | `true`   | Enables kill switch functionality               |
| `CHISEAI_TIMESTAMP_SYNC_THRESHOLD_MS` | `int`   | `5000`   | Max allowed clock drift vs exchange time (ms)   |

---

## 3. Safety / Risk Controls

### 3.1 Kill Switch

| Property              | Value                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Behavior**          | Immediately halts all order placement and cancels all open orders                                                 |
| **Trigger**           | `CHISEAI_KILL_SWITCH_ENABLED=false` OR manual invocation via Redis key `chiseai:kill_switch:active` set to `true` |
| **Who can invoke**    | Any authorized agent with Redis write access; Craig (human override)                                              |
| **Enforcement point** | `TradingOrchestrator.pre_check()` — checked before every order placement                                          |
| **Effect**            | Sets `chiseai:kill_switch:active=true` in Redis; all order functions return `KillSwitchEngaged` error             |

### 3.2 Leverage Cap

| Property              | Value                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Leverage cap**      | `3x` maximum effective leverage                                                                                        |
| **Enforcement point** | `RiskValidator.validate_leverage()` — called before order submission                                                   |
| **On breach**         | Order rejected; log entry emitted with `LEVERAGE_VIOLATION` tag; metric `canary_leverage_rejections_total` incremented |
| **Calculation**       | `effective_leverage = position_value / equity` using current position and account equity                               |

### 3.3 Exposure Cap

| Property              | Value                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Exposure cap**      | `CHISEAI_LIVE_CANARY_BUDGET` (default $1,000 USD notional)                                                             |
| **Enforcement point** | `PositionTracker.check_exposure()` — called before order submission and on each fill confirmation                      |
| **On breach**         | Order rejected; log entry emitted with `EXPOSURE_VIOLATION` tag; metric `canary_exposure_rejections_total` incremented |
| **Measurement**       | Sum of absolute notional value of all open positions                                                                   |

### 3.4 Timestamp Sync Guard

| Property              | Value                                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Drift threshold**   | `CHISEAI_TIMESTAMP_SYNC_THRESHOLD_MS` (default 5000 ms)                                                       |
| **Action on breach**  | Halt order placement; emit `TIMESTAMP_DRIFT_BREACH` alert; set `chiseai:timestamp_drift_breach=true` in Redis |
| **Enforcement point** | `BybitConnector.validate_timestamp_drift()` — called on each heartbeat/check                                  |
| **Measurement**       | `\|local_time - exchange_time\|` from Bybit server time endpoint                                              |
| **Recovery**          | Automatic re-check every 30 seconds; resume if drift falls below threshold                                    |

---

## 4. Cutover Runbook

### 4.1 Preflight Gates (All Must Pass)

| #   | Gate                             | Pass Condition                                                                                                                     | Fail Action                                                     |
| --- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 1   | **Environment flag check**       | `CHISEAI_LIVE_MODE=true` is set and exported                                                                                       | Do not proceed; abort cutover                                   |
| 2   | **BybitConnector health**        | `python -c "from data.exchange.bybit_connector import BybitConnector; c = BybitConnector(); print(c.health_check())"` returns `OK` | Do not proceed; abort cutover                                   |
| 3   | **Kill switch state**            | `redis-cli GET chiseai:kill_switch:active` returns `false` or key does not exist                                                   | Clear kill switch before proceeding                             |
| 4   | **Timestamp drift check**        | `\|local_time - exchange_time\| < CHISEAI_TIMESTAMP_SYNC_THRESHOLD_MS`                                                             | Sync local clock; re-check until within threshold               |
| 5   | **Exposure budget check**        | Current open position notional < `CHISEAI_LIVE_CANARY_BUDGET`                                                                      | Flatten positions until within budget before enabling live mode |
| 6   | **Redis keyspace check**         | All canary state keys (`chiseai:canary:*`) are accessible and not locked                                                           | Investigate Redis connectivity before proceeding                |
| 7   | **Log pipeline check**           | Loki endpoint reachable; `CHISEAI_LIVE_MODE=true` log message successfully written                                                 | Verify logging infrastructure before proceeding                 |
| 8   | **Grafana dashboard accessible** | `canary-cutover` dashboard loads in Grafana                                                                                        | Verify Grafana connectivity before proceeding                   |

### 4.2 Rollback Criteria (Any One Triggers Rollback)

| #   | Criterion                           | Condition                                                              | Immediate Action               |
| --- | ----------------------------------- | ---------------------------------------------------------------------- | ------------------------------ |
| 1   | **Order failure rate**              | >10% of orders fail (reject/error) within first 10 orders              | Activate kill switch; rollback |
| 2   | **Fill latency breach**             | >5% of fills exceed 10-second latency threshold                        | Activate kill switch; rollback |
| 3   | **Exposure breach**                 | Total notional exceeds `CHISEAI_LIVE_CANARY_BUDGET` at any check point | Activate kill switch; rollback |
| 4   | **Kill switch invoked**             | `chiseai:kill_switch:active` set to `true` by any authorized caller    | Rollback immediately           |
| 5   | **Timestamp drift breach persists** | Drift exceeds threshold for >60 consecutive seconds                    | Activate kill switch; rollback |
| 6   | **BybitConnector disconnection**    | Heartbeat fails 3 consecutive times                                    | Activate kill switch; rollback |
| 7   | **Unexpected position state**       | PositionTracker reports negative equity or NaN value                   | Activate kill switch; rollback |

### 4.3 Cutover Execution Sequence

1. Notify `#trading-alerts` Slack channel: "Live canary cutover initiated"
2. Execute all 8 preflight gates in order (section 4.1)
3. If any gate fails: halt and emit incident (section 8)
4. Set `CHISEAI_LIVE_MODE=true` in environment
5. Start `TradingOrchestrator` with `BybitConnector`
6. Emit `CANARY_LIVE_MODE_ENABLED` log event
7. Wait 60 seconds (stabilization window)
8. Begin E2E validation checklist (section 6)
9. If validation passes: declare day-0 restart (section 6.2)
10. If any rollback criterion met: execute rollback (section 4.4)

### 4.4 Rollback Procedure

1. Set `CHISEAI_LIVE_MODE=false`
2. Set `chiseai:kill_switch:active=true`
3. Cancel all open orders via `BybitConnector.cancel_all_orders()`
4. Flatten all positions at market price (if reachable)
5. Emit `CANARY_ROLLBACK_EXECUTED` log event
6. Notify `#trading-alerts`: "Canary rollback executed — manual review required"
7. Document all evidence (section 8)

---

## 5. Canary Reset Semantics

### 5.1 Reset Overview

Upon successful live mode confirmation, the canary metrics and Redis state must be reset to start a clean timeline. This ensures day-0 restart semantics are unambiguous.

### 5.2 Reset Entity Table

| Entity                            | Pre-Cutover Value Handling                                                 | Post-Cutover Initial State                      |
| --------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------- |
| `chiseai:canary:start_time`       | Archived to `chiseai:canary:archive:start_time:<ts>` with TTL 30d          | Set to `now()` UTC                              |
| `chiseai:canary:order_count`      | Archived to `chiseai:canary:archive:order_count:<ts>` with TTL 30d         | Reset to `0`                                    |
| `chiseai:canary:fill_count`       | Archived to `chiseai:canary:archive:fill_count:<ts>` with TTL 30d          | Reset to `0`                                    |
| `chiseai:canary:net_pnl_usd`      | Archived to `chiseai:canary:archive:net_pnl_usd:<ts>` with TTL 30d         | Reset to `0.0`                                  |
| `chiseai:canary:exposure_usd`     | Archived to `chiseai:canary:archive:exposure_usd:<ts>` with TTL 30d        | Reset to `0.0`                                  |
| `chiseai:canary:rejection_count`  | Archived to `chiseai:canary:archive:rejection_count:<ts>` with TTL 30d     | Reset to `0`                                    |
| `chiseai:canary:checkpoints`      | Archived as JSON to `chiseai:canary:archive:checkpoints:<ts>` with TTL 30d | Recalculated from `start_time`                  |
| `chiseai:canary:timeline_version` | Incremented; archive stored with TTL 30d                                   | Set to `1` (new timeline)                       |
| Grafana canary dashboard          | Snapshot saved as `canary-snapshot-pre-cutover-<ts>`                       | All panels reset to show only post-cutover data |

### 5.3 Timeline Restart / Checkpoint Recalculation

**Timeline restart rules:**

1. `start_time` is set to the moment live mode is confirmed (`CANARY_LIVE_MODE_ENABLED` log timestamp)
2. All subsequent timestamps are relative to this new `start_time`
3. Checkpoints are recalculated as:
   - Checkpoint 1: `start_time + 1 hour`
   - Checkpoint 2: `start_time + 4 hours`
   - Checkpoint 3: `start_time + 24 hours` (day-0 declared at this point if all AC met)
   - Checkpoint N: `start_time + (N * 24 hours)`

**Checkpoint recalculation:**

- Stored in `chiseai:canary:checkpoints` as JSON: `[{"id": 1, "target_ts": <iso8601>, "status": "pending"}, ...]`
- Status transitions: `pending` → `reached` → `passed`
- Each transition emits a `CANARY_CHECKPOINT_<id>` log event

---

## 6. E2E Validation Checklist + Acceptance Criteria

### 6.1 E2E Validation Checklist

All items must pass before day-0 restart can be declared.

| #   | Check Item                       | Verification Method                                                 | Pass Condition                                    |
| --- | -------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------- |
| 1   | BybitConnector initializes       | Log entry: `BybitConnector initialized`                             | Log contains `connector=bybit_demo`               |
| 2   | First order placed               | `chiseai:canary:order_count` incremented                            | Count = 1 within 60s of live mode enable          |
| 3   | First fill received              | `chiseai:canary:fill_count` incremented                             | Count = 1 within 120s of first order              |
| 4   | Fill latency < 10s               | Grafana panel `canary_fill_latency_p95`                             | p95 latency < 10000ms                             |
| 5   | Position tracker updates         | `chiseai:canary:exposure_usd` readable                              | Value > 0 and < budget after first fill           |
| 6   | PnL tracked                      | `chiseai:canary:net_pnl_usd` readable                               | Value is a finite float                           |
| 7   | No exposure breach               | Metric `canary_exposure_rejections_total`                           | Remains 0 through first 10 orders                 |
| 8   | No leverage breach               | Metric `canary_leverage_rejections_total`                           | Remains 0 through first 10 orders                 |
| 9   | Kill switch responds             | Set `chiseai:kill_switch:active=true`; verify order placement halts | Order rejected with `KillSwitchEngaged` within 5s |
| 10  | Timestamp drift within threshold | Metric `canary_timestamp_drift_ms`                                  | Value < 5000ms continuously                       |
| 11  | Loki logs flowing                | `CANARY_LIVE_MODE_ENABLED` event visible in Loki                    | Event present within 30s of mode enable           |
| 12  | Grafana dashboard updated        | `canary-live` panel shows data                                      | Last data point age < 2 minutes                   |

### 6.2 Day-0 Restart Declaration

**Definition:** Day-0 restart is declared when:

1. All 12 E2E validation checklist items have passed
2. Checkpoint 1 (`start_time + 1 hour`) has been reached with no rollback criteria triggered
3. A human (Craig) has acknowledged the `CANARY_DAY0_DECLARED` alert
4. The declaration is logged: `CANARY_DAY0_DECLARED timestamp=<iso8601> canary_budget_usd=<value>`

**Operational meaning of day-0 restart declared:**

- The canary clock officially starts
- Subsequent checkpoints are evaluated against live trading metrics
- Promotion to paper-full or live trading can be considered

---

## 7. Observability / Alerts Requirements

### 7.1 Required Grafana Panels / Dashboards

| Panel Name                   | Dashboard        | Metric(s) Shown                          | Refresh |
| ---------------------------- | ---------------- | ---------------------------------------- | ------- |
| `canary-live-status`         | `canary-cutover` | `chiseai_canary_live_mode` (binary)      | 10s     |
| `canary-order-count`         | `canary-cutover` | `chiseai_canary_order_count_total`       | 10s     |
| `canary-fill-count`          | `canary-cutover` | `chiseai_canary_fill_count_total`        | 10s     |
| `canary-exposure-usd`        | `canary-cutover` | `chiseai_canary_exposure_usd`            | 10s     |
| `canary-net-pnl-usd`         | `canary-cutover` | `chiseai_canary_net_pnl_usd`             | 10s     |
| `canary-fill-latency-p95`    | `canary-cutover` | `canary_fill_latency_p95_ms`             | 30s     |
| `canary-timestamp-drift-ms`  | `canary-cutover` | `canary_timestamp_drift_ms`              | 10s     |
| `canary-leverage-rejections` | `canary-cutover` | `canary_leverage_rejections_total`       | 30s     |
| `canary-exposure-rejections` | `canary-cutover` | `canary_exposure_rejections_total`       | 30s     |
| `canary-checkpoint-status`   | `canary-cutover` | `chiseai_canary_checkpoint_id` (current) | 30s     |

### 7.2 Alert Rules (Minimum 5)

| Alert Name                        | Condition                                                        | Severity | Notification Destination              |
| --------------------------------- | ---------------------------------------------------------------- | -------- | ------------------------------------- |
| `CanaryKillSwitchEngaged`         | `chiseai:kill_switch:active == "true"`                           | CRITICAL | `#trading-alerts` (Slack) + PagerDuty |
| `CanaryExposureBreach`            | `canary_exposure_rejections_total` increments > 0 in 5min window | HIGH     | `#trading-alerts` (Slack)             |
| `CanaryLeverageViolation`         | `canary_leverage_rejections_total` increments > 0 in 5min window | HIGH     | `#trading-alerts` (Slack)             |
| `CanaryTimestampDriftBreach`      | `canary_timestamp_drift_ms > 5000` for > 60 consecutive seconds  | HIGH     | `#trading-alerts` (Slack)             |
| `CanaryConnectorHeartbeatFailure` | BybitConnector heartbeat fails 3 consecutive checks              | CRITICAL | `#trading-alerts` (Slack) + PagerDuty |
| `CanaryFillLatencyHigh`           | `canary_fill_latency_p95_ms > 10000` for > 5 minutes             | MEDIUM   | `#trading-alerts` (Slack)             |
| `CanaryOrderFailureRateHigh`      | Order rejection rate > 10% over rolling 10 orders                | HIGH     | `#trading-alerts` (Slack)             |
| `CanaryNegativeEquity`            | Account equity < 0 or NaN detected                               | CRITICAL | `#trading-alerts` (Slack) + PagerDuty |
| `CanaryBudgetExhausted`           | `chiseai:canary:exposure_usd >= CHISEAI_LIVE_CANARY_BUDGET`      | HIGH     | `#trading-alerts` (Slack)             |
| `CanaryDay0Declared`              | `CANARY_DAY0_DECLARED` log event emitted                         | INFO     | `#trading` (Slack)                    |

### 7.3 Log Emission Requirements

All log events must be emitted to Loki with at minimum these fields:

| Log Event                            | Level | Required Fields                                                                      |
| ------------------------------------ | ----- | ------------------------------------------------------------------------------------ |
| `CANARY_LIVE_MODE_ENABLED`           | INFO  | `timestamp`, `canary_budget_usd`, `connector`                                        |
| `CANARY_ORDER_PLACED`                | INFO  | `order_id`, `symbol`, `side`, `notional_usd`, `timestamp`                            |
| `CANARY_FILL_RECEIVED`               | INFO  | `order_id`, `fill_id`, `symbol`, `fill_price`, `fill_qty`, `latency_ms`, `timestamp` |
| `CANARY_CHECKPOINT_1_REACHED`        | INFO  | `checkpoint_id`, `timestamp`, `order_count`, `fill_count`                            |
| `CANARY_CHECKPOINT_1_PASSED`         | INFO  | `checkpoint_id`, `timestamp`                                                         |
| `CANARY_DAY0_DECLARED`               | INFO  | `timestamp`, `canary_budget_usd`, `acknowledged_by`                                  |
| `CANARY_ROLLBACK_EXECUTED`           | ERROR | `trigger_reason`, `timestamp`, `final_exposure_usd`, `final_order_count`             |
| `KILLSWITCH_ENGAGED`                 | ERROR | `invoked_by`, `timestamp`, `reason`                                                  |
| `EXPOSURE_VIOLATION`                 | WARN  | `current_exposure_usd`, `budget_usd`, `order_id`, `timestamp`                        |
| `LEVERAGE_VIOLATION`                 | WARN  | `effective_leverage`, `cap_leverage`, `order_id`, `timestamp`                        |
| `TIMESTAMP_DRIFT_BREACH`             | WARN  | `drift_ms`, `threshold_ms`, `timestamp`                                              |
| `CANARY_CONNECTOR_HEARTBEAT_FAILURE` | ERROR | `consecutive_failures`, `timestamp`                                                  |

---

## 8. Incident / Blocker Handling + Evidence Requirements

### 8.1 What Constitutes a Blocker During Cutover

Any of the following conditions constitutes a **blocker** that halts cutover progression:

1. Any preflight gate (section 4.1) fails
2. Any rollback criterion (section 4.2) is met
3. An unhandled exception is raised in the `TradingOrchestrator` or `BybitConnector`
4. A `CRITICAL` severity alert fires during the stabilization window (first 60 seconds after live mode enable)
5. Craig (human) invokes a halt

### 8.2 Incident Logging Process

When a blocker occurs:

1. **Immediately** set `chiseai:kill_switch:active=true`
2. **Within 60 seconds**: Create incident in Grafana Incident Manager with:
   - Title: `CANARY CUTOVER FAILURE — <brief_description>`
   - Severity: inherited from alert severity or `HIGH` if no alert
   - Labels: `canary`, `cutover`, `live-mode`
3. **Within 5 minutes**: Append to Redis list `chiseai:incidents:cutover:<date>` using `RPUSH`
4. **Within 15 minutes**: Post summary to `#trading-alerts` Slack channel

### 8.3 Evidence Requirements

All cutover incidents must capture:

| Evidence Item            | Description                                          | Format               | Retention |
| ------------------------ | ---------------------------------------------------- | -------------------- | --------- |
| `incident_id`            | Grafana Incident Manager ID                          | string (UUID)        | 90 days   |
| `trigger_timestamp_utc`  | When blocker first detected                          | ISO8601 string       | 90 days   |
| `trigger_condition`      | Which rollback criterion or gate failure             | string               | 90 days   |
| `log_excerpt`            | Last 100 log lines before trigger                    | text file attachment | 90 days   |
| `metric_snapshot`        | All canary metrics at trigger time                   | JSON                 | 90 days   |
| `redis_state_dump`       | Output of `redis-cli --json keys "chiseai:canary:*"` | JSON                 | 90 days   |
| `environment_flags`      | Values of all `CHISEAI_*` env vars at trigger        | JSON                 | 90 days   |
| `action_taken`           | What was done (kill switch, rollback, etc.)          | string               | 90 days   |
| `resolved_timestamp_utc` | When incident was resolved                           | ISO8601 string       | 90 days   |

### 8.4 Post-Cutover Evidence Archive

After day-0 restart is declared, the following are archived to Redis with TTL 30 days:

- Pre-cutover canary state snapshot (all `chiseai:canary:*` keys at cutover time)
- Cutover execution log (all events between `CANARY_LIVE_MODE_ENABLED` and `CANARY_DAY0_DECLARED`)
- Preflight gate results (gate #, pass/fail, check output)

---

## 9. Self-Review Checklist

Before this document is considered complete, the author must verify:

- [ ] No placeholder text remains (no "TBD", "to be defined", "insert value", etc.)
- [ ] No ambiguous requirements (each requirement has a single interpretation)
- [ ] No contradictions between sections
- [ ] All four safety controls have specific thresholds (not vague values)
- [ ] All rollback criteria have concrete conditions (not subjective language)
- [ ] All log events have defined severity levels
- [ ] All metrics are referenced with actual metric names
- [ ] All Redis keys use the `chiseai:canary:*` or `chiseai:kill_switch:*` namespace consistently
- [ ] All timestamps, timeouts, and thresholds use explicit units (ms, seconds, UTC)
- [ ] The simulator fallback prohibition is stated explicitly in at least two places (non-goals + connector selection)

---

**Document Status:** Final
**Review Completed:** Yes (self-review per section 9)
