---
title: Checkpoint Gates Runbook
category: operations
severity: critical
estimated_time_to_resolve: 5-30 minutes
last_updated: 2026-03-14
maintainers: platform-team
story_id: BATCH3-DOCS-004
---

# Checkpoint Gates Runbook

## Overview

This runbook covers the checkpoint gate system (G1-G9) used to validate system health and readiness during trading operations. Checkpoint gates provide automated governance validation at key transition points in the trading pipeline.

## Prerequisites

- Access to Redis (`host.docker.internal:6380`)
- Docker environment with `chiseai` network
- Python 3.11+ with `redis` package
- Checkpoint module available at `src/governance/checkpoint/`

**Required Permissions:**
- Redis: Read access to checkpoint keys
- Docker: Read access to chiseai containers

## 1. Gate Overview

### 1.1 Gate Summary Table

| Gate | Name | Purpose | Status Key |
|------|------|---------|------------|
| G1 | Scheduler Continuity | Validates scheduler heartbeat freshness | `bmad:chiseai:scheduler:heartbeat` |
| G2 | Signal Cadence | Checks signal generation with taxonomy states | `bmad:chiseai:scheduler:heartbeat` |
| G3 | Data Flow Movement | Validates outcomes are being recorded | `bmad:chiseai:outcomes:index` |
| G4 | Kill Switch Active | Verifies kill switch is armed and ready | `bmad:chiseai:kill_switch` |
| G5 | Cron Job Cadence | Checks cron jobs execute on schedule | `bmad:chiseai:cron:*` |
| G6 | Bybit Connectivity | Tests API reachability | External API test |
| G7 | Observability Health | Validates Redis health and uptime | Redis INFO command |
| G8 | End-to-End Pipeline | Burn-in verdict integration | `bmad:chiseai:burnin:verdict` |
| G9 | Metric Integrity | Validates heartbeat aggregates match raw data | Sampling comparison |

### 1.2 Status Definitions

| Status | Emoji | Meaning | Action Required |
|--------|-------|---------|-----------------|
| PASS | ✅ | Gate passing, system healthy | None |
| FAIL | ❌ | Gate failed, blocking issue | Immediate investigation |
| CHECK | ⚠️ | Warning condition, non-blocking | Monitor and investigate |
| ALERT | 🚨 | Critical alert triggered | Immediate response |
| UNKNOWN | ❓ | Cannot determine status | Check data availability |

## 2. G2 Signal Cadence Gate

### 2.1 G2 Message Taxonomy

The G2 gate implements a 4-state taxonomy for signal pipeline health:

#### State 1: NO_SIGNALS
**Description:** No signals generated in the 15-minute window.

**Interpretation:**
- Normal idle state when market conditions don't trigger signals
- Healthy when pipeline_status is not "stale"
- Concerning when pipeline_status is "stale" (extended idle period)

**Redis Data:**
```
Key: bmad:chiseai:scheduler:heartbeat
Fields:
  - pipeline_status: "running" or "stale"
  - signals_15m: "0"
  - latest_signal_age_m: minutes since last signal
```

**Example Output:**
```
✅ PASS: NO_SIGNALS: No signals generated in 15m window (healthy idle state)
❌ FAIL: NO_SIGNALS: No signals generated in 15m window (pipeline stale, last age: 45m)
```

#### State 2: FILTERED
**Description:** Signals generated but none actionable.

**Interpretation:**
- Confidence filters are working as designed
- Signals are being generated but filtered out before action
- Normal behavior during low-confidence market periods

**Redis Data:**
```
Key: bmad:chiseai:scheduler:heartbeat
Fields:
  - signals_15m: ">0"
  - actionable_15m: "0"
```

**Example Output:**
```
✅ PASS: FILTERED: 12 signals generated, 0 actionable (filters active)
```

**Related Alert:** See [Actionable-Zero Alert](#actionable-zero-alert) for monitoring this state.

#### State 3: BOTTLENECK
**Description:** Actionable signals present but downstream processing stalled.

**Interpretation:**
- Pipeline is generating actionable signals
- Consumer backlog exceeds threshold (default: 10)
- Downstream components may be slow or blocked

**Redis Data:**
```
Key: bmad:chiseai:scheduler:heartbeat
Fields:
  - actionable_15m: ">0"
  - consumer_backlog: ">10"
```

**Example Output:**
```
⚠️ CHECK: BOTTLENECK: 5 actionable signals, 15 backlog (downstream stalled, threshold: 10)
```

#### State 4: HEALTHY
**Description:** Normal operation with signals flowing through pipeline.

**Interpretation:**
- Signals are being generated
- Actionable signals are being processed
- Backlog is within acceptable limits

**Example Output:**
```
✅ PASS: HEALTHY: 12 signals, 3 actionable, backlog 2 (normal)
```

### 2.2 G2 Troubleshooting Guide

**Symptom: NO_SIGNALS with stale pipeline**
```
❌ FAIL: NO_SIGNALS: No signals generated in 15m window (pipeline stale)
```

**Investigation Steps:**
1. Check scheduler heartbeat:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:scheduler:heartbeat
   ```

2. Verify scheduler is running:
   ```bash
   docker ps --filter name=chiseai-scheduler
   ```

3. Check scheduler logs:
   ```bash
   docker logs chiseai-scheduler --tail 100
   ```

**Common Causes:**
- Scheduler process stopped or crashed
- Signal generation logic error
- External data source unavailable

**Remediation:**
```bash
# Restart scheduler
docker restart chiseai-scheduler

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g2_signal_cadence())"
```

**Symptom: BOTTLENECK detected**
```
⚠️ CHECK: BOTTLENECK: 5 actionable signals, 15 backlog (downstream stalled)
```

**Investigation Steps:**
1. Check consumer status:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:consumer:status
   ```

2. Monitor backlog trend:
   ```bash
   # Watch backlog over time
   watch -n 30 'redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:scheduler:heartbeat consumer_backlog'
   ```

3. Check consumer logs:
   ```bash
   docker logs chiseai-consumer --tail 200
   ```

**Common Causes:**
- Consumer processing too slow
- Database connection pool exhausted
- External API rate limiting

**Remediation:**
```bash
# Scale up consumers if supported
docker-compose up -d --scale consumer=3

# Or restart consumer
docker restart chiseai-consumer
```

## 3. G5 Cron Job Cadence Gate

### 3.1 Monitored Cron Jobs

| Job Name | Expected Interval | Redis Key Pattern | Purpose |
|----------|-------------------|-------------------|---------|
| pager | 5 minutes (300s) | `bmad:chiseai:cron:pager:*` | Alert paging system |
| signal-growth | 30 minutes (1800s) | `bmad:chiseai:cron:signal-growth:*` | Signal volume monitoring |
| hourly-health | 60 minutes (3600s) | `bmad:chiseai:cron:hourly-health:*` | System health checks |
| checkpoint-audit | 6 hours (21600s) | `bmad:chiseai:cron:checkpoint-audit:*` | Gate validation audit |

### 3.2 Cron Evidence Storage

Cron jobs store evidence in Redis with the following structure:
```
Key: bmad:chiseai:cron:{job_name}:{timestamp}
Fields:
  - executed_at: ISO timestamp
  - status: "success" | "failed"
  - duration_ms: execution time
  - output: job output (truncated)
```

### 3.3 G5 Output Interpretation

**PASS Example:**
```
✅ PASS: pager:PASS(45s) | signal-growth:PASS(12m) | hourly-health:PASS(35m)
```

**CHECK Example:**
```
⚠️ CHECK: pager:PASS(45s) | signal-growth:CHECK(35m,missed=1) | hourly-health:CHECK(75m,missed=1)
```

**FAIL Example:**
```
❌ FAIL: pager:FAIL(400s,missed=3) | signal-growth:FAIL(95m,missed=4)
```

### 3.4 G5 Troubleshooting Guide

**Symptom: Multiple jobs missed**

**Investigation Steps:**
1. Check cron scheduler status:
   ```bash
   docker ps --filter name=woodpecker
   ```

2. View recent cron executions:
   ```bash
   redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:cron:*' | head -20
   ```

3. Check Woodpecker logs:
   ```bash
   docker logs woodpecker-server --tail 500 | grep -E "(error|fail|timeout)"
   ```

**Common Causes:**
- Woodpecker server unavailable
- Agent pool exhausted
- Job timeout exceeded
- Resource constraints

**Remediation:**
```bash
# Restart Woodpecker agent
docker restart woodpecker-agent

# Verify cron jobs resume
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g5_cron_cadence())"
```

## 4. G9 Metric Integrity Gate

### 4.1 Purpose

The G9 gate validates that heartbeat aggregates (stored in scheduler heartbeat) match raw signal data. This ensures:
- No signals are lost in aggregation
- Metrics are accurate for decision-making
- Data pipeline integrity is maintained

### 4.2 Sampling Methodology

**Sample Window:** Last 15 minutes
**Sample Size:** 100 signals (or all if fewer)
**Tolerance Threshold:** 5% variance allowed

**Validation Steps:**
1. Query raw signals from `bmad:chiseai:signals:*`
2. Count signals in 15-minute window
3. Compare to `signals_15m` in heartbeat
4. Calculate variance percentage
5. FAIL if variance > 5%

### 4.3 Redis Keys Involved

```
Raw Signals:
  - bmad:chiseai:signals:{signal_id} (hash with timestamp field)
  - bmad:chiseai:signals:index (set of all signal IDs)

Aggregates:
  - bmad:chiseai:scheduler:heartbeat (hash with signals_15m field)
```

### 4.4 G9 Troubleshooting Guide

**Symptom: Metric mismatch detected**
```
❌ FAIL: Metric integrity: Raw count 150 vs aggregate 120 (variance 20% > 5%)
```

**Investigation Steps:**
1. Check raw signal count:
   ```bash
   redis-cli -h host.docker.internal -p 6380 SCARD bmad:chiseai:signals:index
   ```

2. Verify aggregate value:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:scheduler:heartbeat signals_15m
   ```

3. Check for aggregation errors in scheduler logs:
   ```bash
   docker logs chiseai-scheduler --tail 500 | grep -i "aggregate\|count\|signal"
   ```

**Common Causes:**
- Signal cleanup job removing signals before aggregation
- Clock skew between components
- Race condition in signal recording
- Redis memory pressure causing evictions

**Remediation:**
```bash
# Force heartbeat refresh
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:scheduler:heartbeat force_refresh 1

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g9_metric_integrity())"
```

## 5. Running Checkpoint Checks

### 5.1 Manual Check Execution

**Run all gates:**
```bash
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
summary = checker.run_all_checks()

print(f'Overall Status: {summary.overall_status}')
print(f'Pass: {summary.pass_count}, Fail: {summary.fail_count}, Check: {summary.check_count}')
print()
for result in summary.results:
    print(f'{result.gate}: {result.status} - {result.detail}')
"
```

**Check specific gate:**
```bash
# Check only G2
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g2_signal_cadence())"

# Check only G5
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g5_cron_cadence())"
```

### 5.2 Expected Output Format

**Healthy System:**
```
Overall Status: PASS
Pass: 9, Fail: 0, Check: 0

G1: ✅ PASS - Heartbeat 12s ago, uptime: 45m
G2: ✅ PASS - HEALTHY: 12 signals, 3 actionable, backlog 2 (normal)
G3: ✅ PASS - 847 outcomes recorded
G4: ✅ PASS - Kill switch armed and ready
G5: ✅ PASS - pager:PASS(45s) | signal-growth:PASS(12m) | hourly-health:PASS(35m)
G6: ✅ PASS - Bybit API reachable
G7: ✅ PASS - Redis OK, 1247 keys, 48h uptime
G8: ✅ PASS - Burn-in verdict: GO | Pipeline: 45 signals → 847 outcomes
G9: ✅ PASS - Metric integrity: Raw count matches aggregate (0% variance)
```

**System with Issues:**
```
Overall Status: CHECK
Pass: 6, Fail: 1, Check: 2

G1: ✅ PASS - Heartbeat 8s ago, uptime: 45m
G2: ⚠️ CHECK - BOTTLENECK: 5 actionable signals, 15 backlog (downstream stalled)
G3: ✅ PASS - 847 outcomes recorded
G4: ✅ PASS - Kill switch armed and ready
G5: ⚠️ CHECK - signal-growth:CHECK(35m,missed=1) | hourly-health:CHECK(75m,missed=1)
G6: ✅ PASS - Bybit API reachable
G7: ✅ PASS - Redis OK, 1247 keys, 48h uptime
G8: ❌ FAIL - Burn-in verdict: NO-GO | Pipeline halted
G9: ✅ PASS - Metric integrity: Raw count matches aggregate (0% variance)
```

## 6. Integration Points

### 6.1 Pre-Trade Checks

Checkpoint gates are automatically run before:
- Strategy deployment
- Live trading activation
- Paper-to-live promotion

**Implementation:**
```python
from src.governance.checkpoint import GateChecker

def pre_trade_check():
    checker = GateChecker()
    summary = checker.run_all_checks()
    
    if summary.overall_status == "FAIL":
        failing = checker.get_failing_gates(summary)
        raise RuntimeError(f"Gates failing: {failing}")
    
    return summary
```

### 6.2 Monitoring Integration

Gate results are published to:
- Redis: `bmad:chiseai:checkpoint:latest`
- Grafana: Via Prometheus exporter
- Discord: Alert notifications

## 7. Rollback Procedures

### 7.1 Gate Failure Response

**Immediate Actions:**
1. Stop trading operations if G4 (kill switch) or G8 (pipeline) fail
2. Notify on-call via Discord
3. Document failure in incident log

**Recovery Steps:**
1. Identify failing gates
2. Follow gate-specific troubleshooting
3. Verify resolution with manual check
4. Resume operations only after PASS status

### 7.2 Emergency Override

⚠️ **Warning:** Override only in emergency situations with explicit approval.

```python
# Temporarily bypass gate check (requires human approval)
import os
os.environ["CHECKPOINT_BYPASS"] = "EMERGENCY-2026-03-14-001"

# Document override
# Required: Incident ticket, approver name, business justification
```

## 8. Related Documentation

- [Observability Guardrails](./observability-guardrails.md) - Actionable-zero alert and metric integrity
- [Kill Switch Runbook](./kill-switch-trigger.md) - Emergency halt procedures
- [Tempo Operations](./tempo-operations.md) - Distributed tracing
- [Incident Response](./incident_response.md) - Incident handling procedures

## 9. Appendix: Redis Key Reference

| Key | Type | Description |
|-----|------|-------------|
| `bmad:chiseai:scheduler:heartbeat` | Hash | Scheduler status and metrics |
| `bmad:chiseai:kill_switch` | Hash | Kill switch configuration |
| `bmad:chiseai:outcomes:index` | Set | Index of all outcome IDs |
| `bmad:chiseai:signals:*` | Hash | Individual signal data |
| `bmad:chiseai:signals:index` | Set | Index of all signal IDs |
| `bmad:chiseai:burnin:verdict` | String | Burn-in verdict (GO/NO-GO) |
| `bmad:chiseai:cron:*` | Hash | Cron job execution evidence |
| `bmad:chiseai:consumer:status` | Hash | Consumer backlog and status |
| `bmad:chiseai:checkpoint:latest` | Hash | Latest checkpoint results |
