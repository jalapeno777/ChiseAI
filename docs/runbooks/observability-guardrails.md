---
title: Observability Guardrails Runbook
category: operations
severity: critical
estimated_time_to_resolve: 10-30 minutes
last_updated: 2026-03-14
maintainers: platform-team
story_id: BATCH3-DOCS-004
---

# Observability Guardrails Runbook

## Overview

This runbook covers observability guardrails designed to detect anomalies in the trading pipeline before they escalate to failures. These guardrails provide automated monitoring and alerting for:

1. **Actionable-Zero Alert** - Detects when signals are generated but none are actionable
2. **Metric Integrity Check** - Validates that heartbeat aggregates match raw data

## Prerequisites

- Access to Redis (`host.docker.internal:6380`)
- Access to Grafana (http://localhost:3001)
- Docker environment with `chiseai` network
- Python 3.11+ with `redis` package

**Required Permissions:**
- Redis: Read access to monitoring keys
- Grafana: Viewer or higher
- Alertmanager: Acknowledge alerts

---

## 1. Actionable-Zero Alert

### 1.1 Purpose

The actionable-zero alert detects when the signal pipeline is generating signals but none are passing confidence filters to become actionable. This indicates:
- Confidence thresholds may be too aggressive
- Market conditions may not be suitable for trading
- Potential issues with signal quality

### 1.2 Alert Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Trigger Condition** | 3 consecutive windows with signals > 0 AND actionable = 0 | Alert fires after 45 minutes of filtered-only signals |
| **Window Size** | 15 minutes | Aggregation window for signal counting |
| **Suppression** | Max 1 alert per hour | Prevents alert spam |
| **Severity** | WARNING | Non-blocking but requires investigation |

### 1.3 Alert Logic

```python
# Pseudo-code for alert logic
consecutive_filtered_windows = 0

for window in last_n_windows(n=3):
    signals = get_signals_count(window)
    actionable = get_actionable_count(window)
    
    if signals > 0 and actionable == 0:
        consecutive_filtered_windows += 1
    else:
        consecutive_filtered_windows = 0

if consecutive_filtered_windows >= 3:
    fire_alert("ActionableZeroDetected")
```

### 1.4 Redis Keys Monitored

```
Key: bmad:chiseai:scheduler:heartbeat
Fields:
  - signals_15m: Number of signals in last 15 minutes
  - actionable_15m: Number of actionable signals in last 15 minutes
  - pipeline_status: Current pipeline state

Key: bmad:chiseai:alerts:actionable_zero
Fields:
  - last_triggered: ISO timestamp
  - suppressed_until: ISO timestamp
  - consecutive_windows: Current streak count
```

### 1.5 Common Causes and Remediation

#### Cause 1: Confidence Threshold Too High

**Symptoms:**
- Signals generated consistently
- Zero actionable for extended periods
- Market volatility within normal range

**Investigation:**
```bash
# Check current confidence threshold
redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:config confidence_threshold

# Review signal confidence distribution
python -c "
import redis
r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)
signal_ids = r.smembers('bmad:chiseai:signals:index')
confidences = []
for sid in list(signal_ids)[:50]:
    conf = r.hget(f'bmad:chiseai:signals:{sid}', 'confidence')
    if conf:
        confidences.append(float(conf))
print(f'Sample confidences: {confidences[:10]}')
print(f'Range: {min(confidences):.2f} - {max(confidences):.2f}')
"
```

**Remediation:**
```bash
# Adjust confidence threshold (requires approval)
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:config confidence_threshold 0.65

# Verify change
redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:config confidence_threshold
```

#### Cause 2: Poor Market Conditions

**Symptoms:**
- Signals generated but low quality
- Market volatility very high or very low
- Other strategies also showing reduced activity

**Investigation:**
```bash
# Check market conditions
python -c "
import redis
r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)
heartbeat = r.hgetall('bmad:chiseai:scheduler:heartbeat')
print(f'Pipeline status: {heartbeat.get(\"pipeline_status\")}')
print(f'Signals 15m: {heartbeat.get(\"signals_15m\")}')
print(f'Actionable 15m: {heartbeat.get(\"actionable_15m\")}')
"
```

**Remediation:**
- No action required - this is expected behavior
- Monitor for market condition changes
- Consider reducing position sizes during uncertain periods

#### Cause 3: Signal Generation Issue

**Symptoms:**
- Signals generated but malformed
- Missing confidence scores
- Invalid signal data structure

**Investigation:**
```bash
# Inspect recent signals
python -c "
import redis
r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)
signal_ids = list(r.smembers('bmad:chiseai:signals:index'))[-5:]
for sid in signal_ids:
    data = r.hgetall(f'bmad:chiseai:signals:{sid}')
    print(f'Signal {sid}: {data}')
"
```

**Remediation:**
```bash
# Restart signal generation service
docker restart chiseai-scheduler

# Verify recovery
sleep 60
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g2_signal_cadence())"
```

### 1.6 Alert Suppression

**Manual Suppression (Emergency Only):**
```bash
# Suppress for 4 hours
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:alerts:actionable_zero suppressed_until "2026-03-14T20:00:00Z"

# Verify suppression
redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:alerts:actionable_zero suppressed_until
```

**Acknowledge Alert:**
```bash
# Mark as acknowledged
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:alerts:actionable_zero acknowledged_by "oncall-engineer"
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:alerts:actionable_zero acknowledged_at "$(date -Iseconds)"
```

### 1.7 Grafana Dashboard

**Dashboard URL:** http://localhost:3001/d/actionable-zero/actionable-zero-monitoring

**Key Panels:**
- Signals vs Actionable (15m rate)
- Filtered Ratio (% signals filtered)
- Consecutive Filtered Windows
- Alert History

### 1.8 Example Alert Output

**Discord Notification:**
```
🟡 WARNING: Actionable-Zero Detected

The system has generated signals but none have been actionable 
for 45+ minutes (3 consecutive 15m windows).

Current State:
• Signals (15m): 24
• Actionable (15m): 0
• Filtered Ratio: 100%
• Consecutive Windows: 3/3

Possible Causes:
1. Confidence threshold too high
2. Poor market conditions
3. Signal generation issue

Runbook: docs/runbooks/observability-guardrails.md
Acknowledge: Click 👍 to acknowledge
```

---

## 2. Metric Integrity Check

### 2.1 Purpose

The metric integrity check validates that heartbeat aggregates (used for fast monitoring) match raw signal data (source of truth). This ensures:
- No signals are lost in aggregation pipeline
- Monitoring metrics are accurate
- Data consistency between components

### 2.2 Check Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Sampling Window** | 15 minutes | Time window for comparison |
| **Sample Size** | 100 signals | Number of signals to validate (or all if fewer) |
| **Tolerance Threshold** | 5% | Maximum allowed variance |
| **Check Frequency** | Every 6 hours | Aligned with checkpoint-audit cron |
| **Severity** | CRITICAL | Blocking issue if failed |

### 2.3 Sampling Methodology

**Step 1: Collect Raw Data**
```python
# Query all signal IDs
signal_ids = redis.smembers('bmad:chiseai:signals:index')

# Filter to 15-minute window
window_start = now - 15 minutes
raw_signals = []
for sid in signal_ids:
    ts = redis.hget(f'bmad:chiseai:signals:{sid}', 'timestamp')
    if ts and ts >= window_start:
        raw_signals.append(sid)

raw_count = len(raw_signals)
```

**Step 2: Get Aggregate Data**
```python
# Read from heartbeat (fast path)
aggregate_count = int(redis.hget(
    'bmad:chiseai:scheduler:heartbeat', 
    'signals_15m'
))
```

**Step 3: Calculate Variance**
```python
if raw_count == 0 and aggregate_count == 0:
    variance = 0  # Both zero is a match
else:
    variance = abs(raw_count - aggregate_count) / max(raw_count, aggregate_count)

status = "PASS" if variance <= 0.05 else "FAIL"
```

### 2.4 Redis Keys Used

| Key | Type | Purpose |
|-----|------|---------|
| `bmad:chiseai:signals:{id}` | Hash | Individual signal data with timestamp |
| `bmad:chiseai:signals:index` | Set | Index of all signal IDs |
| `bmad:chiseai:scheduler:heartbeat` | Hash | Aggregated metrics including `signals_15m` |
| `bmad:chiseai:metric_integrity:latest` | Hash | Latest integrity check results |

### 2.5 Running Integrity Checks

**Manual Check:**
```bash
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
result = checker.check_g9_metric_integrity()
print(f'{result.gate}: {result.status} - {result.detail}')
"
```

**Expected Output:**
```
G9: ✅ PASS - Metric integrity: Raw 142 vs aggregate 140 (variance 1.4% ≤ 5%)
```

**Failure Output:**
```
G9: ❌ FAIL - Metric integrity: Raw 150 vs aggregate 120 (variance 20.0% > 5%)
```

### 2.6 Common Causes and Remediation

#### Cause 1: Signal Cleanup Race Condition

**Symptoms:**
- Raw count > aggregate count
- Recently started seeing discrepancies
- Signal cleanup job running frequently

**Investigation:**
```bash
# Check cleanup job schedule
docker logs chiseai-scheduler --tail 1000 | grep -i "cleanup\|expire"

# Check Redis TTLs
redis-cli -h host.docker.internal -p 6380 TTL bmad:chiseai:signals:sample-id

# Review cleanup timing
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:config | grep -i cleanup
```

**Remediation:**
```bash
# Adjust cleanup window to be longer than aggregation window
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:config signal_ttl_seconds 1800

# Restart scheduler to apply
docker restart chiseai-scheduler
```

#### Cause 2: Clock Skew

**Symptoms:**
- Intermittent mismatches
- Variance changes over time
- Multiple components involved

**Investigation:**
```bash
# Check system times
docker exec chiseai-scheduler date
docker exec chiseai-consumer date
docker exec chiseai-redis date

# Check Redis time
redis-cli -h host.docker.internal -p 6380 TIME
```

**Remediation:**
```bash
# Sync clocks (if using NTP)
docker exec chiseai-scheduler ntpdate -s time.google.com

# Or restart containers to sync
docker restart chiseai-scheduler chiseai-consumer
```

#### Cause 3: Aggregation Logic Error

**Symptoms:**
- Consistent under-counting
- Variance pattern is regular
- Recent code changes to scheduler

**Investigation:**
```bash
# Review scheduler aggregation code
git log --oneline -20 -- src/governance/checkpoint/gates.py

# Check for recent changes
ls -la src/governance/checkpoint/

# Review scheduler logs for errors
docker logs chiseai-scheduler --tail 500 | grep -i "aggregate\|count\|error"
```

**Remediation:**
```bash
# Rollback recent changes if needed
git revert HEAD  # If recent commit caused issue

# Or fix and redeploy
# [Edit gates.py to fix aggregation logic]
docker-compose up -d --build chiseai-scheduler
```

#### Cause 4: Redis Memory Pressure

**Symptoms:**
- Sudden drop in raw count
- Redis INFO shows high memory usage
- Eviction policy active

**Investigation:**
```bash
# Check Redis memory
redis-cli -h host.docker.internal -p 6380 INFO memory | grep -E "used_memory|evicted_keys"

# Check key count trend
redis-cli -h host.docker.internal -p 6380 DBSIZE

# Review Redis logs
docker logs chiseai-redis --tail 200 | grep -i "evict\|memory\|maxmemory"
```

**Remediation:**
```bash
# Increase Redis memory limit
docker update --memory 2g chiseai-redis

# Or reduce signal retention
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:config signal_ttl_seconds 600

# Clear old signals immediately
python -c "
import redis
r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)
signal_ids = r.smembers('bmad:chiseai:signals:index')
for sid in list(signal_ids)[:1000]:
    r.delete(f'bmad:chiseai:signals:{sid}')
    r.srem('bmad:chiseai:signals:index', sid)
"
```

### 2.7 Tolerance Thresholds

| Variance | Status | Action |
|----------|--------|--------|
| 0% | Perfect match | None required |
| 0-2% | Excellent | Monitor trends |
| 2-5% | Acceptable | Investigate if persistent |
| 5-10% | Warning | Immediate investigation |
| >10% | Critical | Halt and investigate |

### 2.8 Actions on Mismatch

**Automatic Actions (When G9 FAILS):**
1. Log incident to `bmad:chiseai:incidents:metric_integrity`
2. Notify on-call via Discord
3. Set checkpoint gate G9 to FAIL status
4. Trigger data consistency repair job (if configured)

**Manual Investigation Steps:**
1. Run manual integrity check to confirm
2. Review recent signal generation logs
3. Compare raw vs aggregate counts over time
4. Identify which specific signals are missing from aggregate
5. Determine root cause (see Common Causes above)

**Rollback Procedures:**
```bash
# Force heartbeat refresh from raw data
python -c "
import redis
from datetime import datetime, timedelta, UTC

r = redis.Redis(host='host.docker.internal', port=6380, decode_responses=True)

# Count raw signals in last 15m
window_start = datetime.now(UTC) - timedelta(minutes=15)
signal_ids = r.smembers('bmad:chiseai:signals:index')
count = 0
for sid in signal_ids:
    ts_str = r.hget(f'bmad:chiseai:signals:{sid}', 'timestamp')
    if ts_str:
        ts = datetime.fromisoformat(ts_str)
        if ts >= window_start:
            count += 1

# Update heartbeat
r.hset('bmad:chiseai:scheduler:heartbeat', 'signals_15m', count)
r.hset('bmad:chiseai:scheduler:heartbeat', 'integrity_fixed_at', datetime.now(UTC).isoformat())
print(f'Updated signals_15m to {count}')
"
```

---

## 3. Integration with Checkpoint Gates

### 3.1 G2 Signal Cadence + Actionable-Zero

The G2 gate provides the real-time state that feeds into the actionable-zero alert:

```
G2 Output: FILTERED: 12 signals generated, 0 actionable (filters active)
    ↓
Actionable-Zero Alert: Counts consecutive FILTERED states
    ↓
Alert fires after 3 consecutive windows (45 minutes)
```

### 3.2 G9 Metric Integrity + G2 Signal Cadence

G9 validates the data that G2 relies on:

```
G9 Output: PASS - Raw count matches aggregate
    ↓
G2 uses validated aggregate: signals_15m, actionable_15m
    ↓
Reliable signal cadence assessment
```

### 3.3 Monitoring Dashboard

**Checkpoint Gates Dashboard:** http://localhost:3001/d/checkpoint/checkpoint-gates

**Panels:**
- G2 Signal Cadence State (NO_SIGNALS/FILTERED/BOTTLENECK/HEALTHY)
- Actionable-Zero Alert Status
- Metric Integrity Variance %
- Raw vs Aggregate Count

---

## 4. Troubleshooting Summary

### 4.1 Quick Diagnostic Commands

```bash
# Check all guardrail statuses
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
print('G2:', checker.check_g2_signal_cadence().detail)
print('G9:', checker.check_g9_metric_integrity().detail)
"

# Check alert status
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:alerts:actionable_zero

# Check integrity results
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:metric_integrity:latest
```

### 4.2 Decision Tree

**Actionable-Zero Alert Fired:**
```
Is market volatile?
├── Yes → Expected behavior, monitor
└── No → Check confidence threshold
    ├── Threshold recently changed? → Revert or adjust
    └── Threshold unchanged? → Check signal quality
        ├── Signals malformed? → Restart scheduler
        └── Signals normal? → Lower threshold slightly
```

**Metric Integrity Failed:**
```
Is variance sudden or gradual?
├── Sudden → Check Redis memory/cleanup
│   ├── Memory pressure? → Increase memory/clear old data
│   └── Cleanup job issue? → Adjust TTLs
└── Gradual → Check clock skew/aggregation logic
    ├── Clock skew? → Sync clocks
    └── Logic error? → Review recent changes
```

---

## 5. Related Documentation

- [Checkpoint Gates](./checkpoint-gates.md) - Full gate reference
- [Incident Response](./incident_response.md) - Incident handling
- [Kill Switch Trigger](./kill-switch-trigger.md) - Emergency procedures
- [Scheduler Operations](./autonomy-cadence-operations.md) - Scheduler management

---

## 6. Appendix: Redis Key Reference

| Key | Type | Description |
|-----|------|-------------|
| `bmad:chiseai:alerts:actionable_zero` | Hash | Alert state and suppression |
| `bmad:chiseai:metric_integrity:latest` | Hash | Latest integrity check results |
| `bmad:chiseai:metric_integrity:history` | List | Historical variance readings |
| `bmad:chiseai:config` | Hash | Configuration including thresholds |

---

## 3. Bybit Freshness Watchdog

### 3.1 Purpose

The Bybit Freshness Watchdog provides automated monitoring and recovery for Bybit truth data freshness (G12 gate). It ensures:
- Continuous monitoring of truth data collection timestamps
- Early warning before data becomes stale (45-minute threshold)
- Alert and optional auto-recovery when data goes stale (60-minute threshold)
- Prevention of G12 failures due to stale truth data

### 3.2 Watchdog Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Check Interval** | 5 minutes | How often to check freshness |
| **Warning Threshold** | 45 minutes | 75% of G12 threshold |
| **Fail Threshold** | 60 minutes | G12 threshold for stale data |
| **Recovery Lock TTL** | 5 minutes | Prevents concurrent recovery attempts |
| **Recovery Timeout** | 2 minutes | Subprocess timeout for collector |

### 3.3 Alert Logic

```python
# Pseudo-code for watchdog logic
minutes_since = calculate_minutes_since_last_collection()

if minutes_since > 60:
    status = "STALE"
    alert()
    if auto_recover:
        trigger_collector()
elif minutes_since > 45:
    status = "WARNING"
    warn()
else:
    status = "FRESH"
```

### 3.4 Redis Keys Monitored

**Collection Metadata (from collector):**
```
Key: bmad:chiseai:bybit_truth:last_collection_timestamp
Key: bmad:chiseai:bybit_truth:last_collection_count
Key: bmad:chiseai:bybit_truth:last_collection_status
```

**Watchdog State:**
```
Key: bmad:chiseai:bybit_truth:watchdog:last_check
Key: bmad:chiseai:bybit_truth:watchdog:status
Key: bmad:chiseai:bybit_truth:watchdog:alert_count
Key: bmad:chiseai:bybit_truth:recovery_lock
```

### 3.5 Running the Watchdog

**Manual Check:**
```bash
# Single check
python3 scripts/monitoring/bybit_freshness_watchdog.py

# With verbose output
python3 scripts/monitoring/bybit_freshness_watchdog.py -v

# JSON output for automation
python3 scripts/monitoring/bybit_freshness_watchdog.py --output json
```

**With Auto-Recovery:**
```bash
# Check and recover if stale
python3 scripts/monitoring/bybit_freshness_watchdog.py --auto-recover

# Continuous loop with auto-recovery
python3 scripts/monitoring/bybit_freshness_watchdog.py --loop --auto-recover
```

**Custom Thresholds:**
```bash
# Adjust thresholds (useful for testing)
python3 scripts/monitoring/bybit_freshness_watchdog.py \
  --warning-threshold 30 \
  --fail-threshold 45
```

### 3.6 Common Causes and Remediation

#### Cause 1: Collector Not Running

**Symptoms:**
- Last collection timestamp old or missing
- No collection status in Redis
- Watchdog shows "STALE_NO_COLLECTION"

**Investigation:**
```bash
# Check if collector is in cron jobs
redis-cli -h host.docker.internal -p 6380 GET chise:cron:bybit-truth-collector:last_run

# Check cron evidence for collector
python3 -c "from scripts.monitoring.cron_evidence import check_cron_cadence; print(check_cron_cadence())"
```

**Remediation:**
```bash
# Start collector manually
python3 scripts/validation/bybit_truth_collector.py --dry-run

# Or trigger via cron evidence
python3 -c "from scripts.monitoring.cron_evidence import write_cron_evidence; write_cron_evidence('bybit-truth-collector')"
```

#### Cause 2: API Errors

**Symptoms:**
- Collection status shows "api_error"
- Error message mentions Bybit API
- Intermittent failures

**Investigation:**
```bash
# Check error details
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:bybit_truth:last_collection_error

# Check API connectivity
curl -s "https://api.bybit.com/v5/market/time" | jq '.time'
```

**Remediation:**
```bash
# Check if API is globally down
curl -s "https://status.bybit.com/api/v2/status.json"

# Restart collector after API recovers
python3 scripts/validation/bybit_truth_collector.py
```

#### Cause 3: Redis Connection Issues

**Symptoms:**
- Collection status shows "redis_error"
- Cannot read/write to Redis
- Watchdog cannot acquire lock

**Investigation:**
```bash
# Check Redis connectivity
redis-cli -h host.docker.internal -p 6380 PING

# Check Redis memory
redis-cli -h host.docker.internal -p 6380 INFO memory | grep used_memory_human
```

**Remediation:**
```bash
# Restart Redis if needed
docker restart chiseai-redis

# Verify recovery
redis-cli -h host.docker.internal -p 6380 PING
```

### 3.7 Recovery Lock Behavior

The recovery lock prevents multiple concurrent recovery attempts:

**Lock Acquisition:**
```python
# Try to acquire lock with 5-minute TTL
lock_acquired = redis.set(
    "bmad:chiseai:bybit_truth:recovery_lock",
    timestamp,
    nx=True,  # Only if not exists
    ex=300    # 5-minute expiry
)
```

**Lock Release:**
- Lock is released after recovery completes (success or failure)
- Lock expires automatically after 5 minutes (TTL)
- Stale locks (> 5 minutes) are force-acquired

**Monitoring Lock State:**
```bash
# Check if recovery is in progress
redis-cli -h host.docker.internal -p 6380 GET bmad:chiseai:bybit_truth:recovery_lock

# Check lock TTL
redis-cli -h host.docker.internal -p 6380 TTL bmad:chiseai:bybit_truth:recovery_lock
```

### 3.8 Integration with G12

The watchdog integrates with G12 (Bybit Freshness Gate):

```
Watchdog Monitors: bmad:chiseai:bybit_truth:last_collection_timestamp
                           ↓
                   Compares against 60-minute threshold
                           ↓
         ┌──────────────────┼──────────────────┐
         ↓                  ↓                  ↓
     Fresh (<45m)    Warning (45-60m)    Stale (>60m)
         ↓                  ↓                  ↓
       PASS            G12 CHECK           G12 FAIL
         ↓                  ↓                  ↓
       Green            Yellow               Red
```

### 3.9 Example Output

**Fresh Status:**
```
======================================================================
BYBIT TRUTH FRESHNESS WATCHDOG
======================================================================
Check Time: 2026-03-15T10:30:00+00:00
Warning Threshold: 45 minutes
Fail Threshold: 60 minutes
----------------------------------------------------------------------

📊 STATUS: ✓ FRESH
  Minutes since collection: 12.34

📋 LAST COLLECTION
  Timestamp: 2026-03-15T10:17:40+00:00
  Count: 5

======================================================================
```

**Warning Status:**
```
======================================================================
BYBIT TRUTH FRESHNESS WATCHDOG
======================================================================
Check Time: 2026-03-15T11:05:00+00:00
Warning Threshold: 45 minutes
Fail Threshold: 60 minutes
----------------------------------------------------------------------

📊 STATUS: ⚠ WARNING
  Minutes since collection: 47.50

📋 LAST COLLECTION
  Timestamp: 2026-03-15T10:17:30+00:00
  Count: 5

⚠️  ERROR MESSAGE
  Data is aging: 47.50m since last collection (warning: 45m, fail: 60m)

======================================================================
```

**Stale with Auto-Recovery:**
```
======================================================================
BYBIT TRUTH FRESHNESS WATCHDOG
======================================================================
Check Time: 2026-03-15T11:20:00+00:00
Warning Threshold: 45 minutes
Fail Threshold: 60 minutes
----------------------------------------------------------------------

📊 STATUS: ✗ STALE
  Minutes since collection: 62.50

📋 LAST COLLECTION
  Timestamp: 2026-03-15T10:17:30+00:00
  Count: 5

🔄 RECOVERY ATTEMPT
  Status: success
  Output: Collection successful: 5 executions (execution_id: abc123)...

======================================================================
```

---

## 4. Integration with Checkpoint Gates

### 4.1 G2 Signal Cadence + Actionable-Zero

The G2 gate provides the real-time state that feeds into the actionable-zero alert:

```
G2 Output: FILTERED: 12 signals generated, 0 actionable (filters active)
    ↓
Actionable-Zero Alert: Counts consecutive FILTERED states
    ↓
Alert fires after 3 consecutive windows (45 minutes)
```

### 4.2 G9 Metric Integrity + G2 Signal Cadence

G9 validates the data that G2 relies on:

```
G9 Output: PASS - Raw count matches aggregate
    ↓
G2 uses validated aggregate: signals_15m, actionable_15m
    ↓
Reliable signal cadence assessment
```

### 4.3 G12 Bybit Freshness + Watchdog

The watchdog provides early warning and auto-recovery for G12:

```
Watchdog Monitors: bmad:chiseai:bybit_truth:last_collection_timestamp
    ↓
Warning at 45m → G12 remains PASS (but flagged)
    ↓
Stale at 60m → G12 FAIL (unless auto-recovery succeeds)
```

### 4.4 Monitoring Dashboard

**Checkpoint Gates Dashboard:** http://localhost:3001/d/checkpoint/checkpoint-gates

**Panels:**
- G2 Signal Cadence State (NO_SIGNALS/FILTERED/BOTTLENECK/HEALTHY)
- Actionable-Zero Alert Status
- Metric Integrity Variance %
- Raw vs Aggregate Count
- G12 Bybit Freshness Status
- Watchdog Status (last check, alert count)

---

## 5. Troubleshooting Summary

### 5.1 Quick Diagnostic Commands

```bash
# Check all guardrail statuses
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
print('G2:', checker.check_g2_signal_cadence().detail)
print('G9:', checker.check_g9_metric_integrity().detail)
print('G12:', checker.check_g12_bybit_freshness().detail)
"

# Check alert status
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:alerts:actionable_zero

# Check integrity results
redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:metric_integrity:latest

# Check watchdog status
python3 scripts/monitoring/bybit_freshness_watchdog.py --output json

# Check Bybit freshness
python3 scripts/validation/bybit_freshness_check.py
```

### 5.2 Decision Tree

**Actionable-Zero Alert Fired:**
```
Is market volatile?
├── Yes → Expected behavior, monitor
└── No → Check confidence threshold
    ├── Threshold recently changed? → Revert or adjust
    └── Threshold unchanged? → Check signal quality
        ├── Signals malformed? → Restart scheduler
        └── Signals normal? → Lower threshold slightly
```

**Metric Integrity Failed:**
```
Is variance sudden or gradual?
├── Sudden → Check Redis memory/cleanup
│   ├── Memory pressure? → Increase memory/clear old data
│   └── Cleanup job issue? → Adjust TTLs
└── Gradual → Check clock skew/aggregation logic
    ├── Clock skew? → Sync clocks
    └── Logic error? → Review recent changes
```

**Bybit Freshness Stale (G12):**
```
Is collector running?
├── Yes → Check for API errors
│   ├── API error? → Wait for API recovery, restart collector
│   └── No API error? → Check Redis connectivity
│       ├── Redis down? → Restart Redis
│       └── Redis OK? → Trigger manual collection
└── No → Start collector
    ├── Via cron: Trigger bybit-truth-collector job
    └── Manual: python3 scripts/validation/bybit_truth_collector.py
```

---

## 6. Related Documentation

- [Checkpoint Gates](./checkpoint-gates.md) - Full gate reference including G12
- [Incident Response](./incident_response.md) - Incident handling
- [Kill Switch Trigger](./kill-switch-trigger.md) - Emergency procedures
- [Scheduler Operations](./autonomy-cadence-operations.md) - Scheduler management

---

## 7. Appendix: Redis Key Reference

| Key | Type | Description |
|-----|------|-------------|
| `bmad:chiseai:alerts:actionable_zero` | Hash | Alert state and suppression |
| `bmad:chiseai:metric_integrity:latest` | Hash | Latest integrity check results |
| `bmad:chiseai:metric_integrity:history` | List | Historical variance readings |
| `bmad:chiseai:config` | Hash | Configuration including thresholds |
| `bmad:chiseai:bybit_truth:last_collection_timestamp` | String | Last collector timestamp |
| `bmad:chiseai:bybit_truth:last_collection_status` | String | Last collector status |
| `bmad:chiseai:bybit_truth:watchdog:last_check` | String | Last watchdog check time |
| `bmad:chiseai:bybit_truth:watchdog:status` | String | Current watchdog status |
| `bmad:chiseai:bybit_truth:watchdog:alert_count` | String | Number of stale alerts |
| `bmad:chiseai:bybit_truth:recovery_lock` | String | Recovery lock timestamp |

---

## 8. Change Log

| Date | Change | Story |
|------|--------|-------|
| 2026-03-14 | Initial documentation | BATCH3-DOCS-004 |
| 2026-03-14 | Added G2 taxonomy | BATCH3-DOCS-004 |
| 2026-03-14 | Added G9 metric integrity | BATCH3-DOCS-004 |
| 2026-03-15 | Added Bybit Freshness Watchdog section | ST-BYBIT-FRESHNESS-001 |
