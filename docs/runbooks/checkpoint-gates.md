---
title: Checkpoint Gates Runbook
category: operations
severity: critical
estimated_time_to_resolve: 5-30 minutes
last_updated: 2026-03-15
maintainers: platform-team
story_id: BATCH3-DOCS-004
---

# Checkpoint Gates Runbook

## Overview

This runbook covers the checkpoint gate system (G1-G12) used to validate system health and readiness during trading operations. Checkpoint gates provide automated governance validation at key transition points in the trading pipeline.

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
| G10 | Chain Integrity | Validates order/position chain consistency | Chain validation check |
| G11 | Provenance | Validates data lineage and source tracking | Provenance registry |
| G12 | Bybit Freshness | Validates market data freshness from Bybit | API timestamp check |

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

### 2.2 G2 Paper-Aware Mode

The G2 gate supports paper-aware validation to distinguish between paper trading and live trading signals.

**Format:** `PAPER:X LIVE:Y`

Where:
- `X` = count of paper trading signals in the window
- `Y` = count of live trading signals in the window

**Redis Data:**
```
Key: bmad:chiseai:scheduler:heartbeat
Fields:
  - signals_15m: "PAPER:8 LIVE:3"
  - actionable_15m: "PAPER:2 LIVE:1"
  - paper_mode: "mixed" | "paper_only" | "live_only"
```

**Status Logic:**

| Paper Signals | Live Signals | Status | Interpretation |
|---------------|--------------|--------|----------------|
| 0 | 0 | NO_SIGNALS | No signals in either mode |
| >0 | 0 | PAPER_ONLY | Paper trading only (safe testing) |
| 0 | >0 | LIVE_ONLY | Live trading only (production mode) |
| >0 | >0 | MIXED | Both modes active (transition/testing) |

**Example Outputs:**

**Paper-Only Mode:**
```
✅ PASS: PAPER_ONLY: PAPER:12 LIVE:0 (paper testing mode)
```

**Live-Only Mode:**
```
✅ PASS: HEALTHY: PAPER:0 LIVE:8, 3 actionable, backlog 2 (live production)
```

**Mixed Mode:**
```
✅ PASS: MIXED: PAPER:6 LIVE:4, total 10 signals (transition mode)
⚠️ CHECK: MIXED: PAPER:2 LIVE:15 (high live ratio, verify intended)
```

**Paper-Aware Troubleshooting:**

**Symptom: Unexpected live signals during paper testing**
```
⚠️ CHECK: MIXED: PAPER:2 LIVE:5 (unexpected live signals detected)
```

**Investigation Steps:**
1. Check current trading mode configuration:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:trading:config mode
   ```

2. Verify scheduler mode flags:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:scheduler:heartbeat | grep -E "(paper_mode|live_enabled)"
   ```

3. Check recent signal routing:
   ```bash
   redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:signals:*' | xargs -I {} redis-cli HGET {} routing_mode
   ```

**Common Causes:**
- Scheduler accidentally started with live mode enabled
- Configuration mismatch between components
- Signal router misconfiguration
- Unintended mode transition during deployment

**Remediation:**
```bash
# Verify trading mode
python -c "from src.governance.checkpoint import GateChecker; result = GateChecker().check_g2_signal_cadence(); print(result)"

# If live signals are unintended, disable live routing
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:trading:config live_enabled 0

# Restart scheduler in paper-only mode
docker restart chiseai-scheduler
```

### 2.3 G2 Troubleshooting Guide

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

## 5. G10 Chain Integrity Gate

### 5.1 Purpose

The G10 gate validates the integrity of order and position chains to ensure:
- No orphaned orders without parent positions
- No positions without corresponding orders
- Consistent state across the trading lifecycle
- Detection of chain breaks that could indicate data loss or corruption

### 5.2 How It Works

**Validation Logic:**
1. Scan all orders in Redis
2. Verify each order has a valid parent position
3. Verify each position has at least one associated order
4. Check for duplicate or conflicting order states
5. Validate order sequence numbers are contiguous

**Chain Structure:**
```
Position (parent)
  ├── Order 1 (open)
  ├── Order 2 (modify)
  ├── Order 3 (close)
  └── Position State: OPEN → MODIFIED → CLOSED
```

**Redis Keys Involved:**
```
Orders:
  - bmad:chiseai:orders:{order_id} (hash with order details)
  - bmad:chiseai:orders:index (set of all order IDs)
  - bmad:chiseai:orders:by_position:{position_id} (set of orders per position)

Positions:
  - bmad:chiseai:positions:{position_id} (hash with position details)
  - bmad:chiseai:positions:index (set of all position IDs)
  - bmad:chiseai:positions:active (set of active position IDs)
```

### 5.3 Status Logic

| Condition | Status | Detail |
|-----------|--------|--------|
| All chains valid, no orphans | ✅ PASS | "X orders, Y positions, all chains valid" |
| Orphaned orders found | ❌ FAIL | "Z orphaned orders without positions" |
| Orphaned positions found | ⚠️ CHECK | "Z positions without orders (may be pending)" |
| Sequence gaps detected | ⚠️ CHECK | "Sequence gap: expected N, found M" |
| Conflicting states | ❌ FAIL | "X orders with conflicting states" |

### 5.4 Example Outputs

**PASS Example:**
```
✅ PASS: Chain integrity: 145 orders, 48 positions, all chains valid
```

**Orphaned Orders:**
```
❌ FAIL: Chain integrity: 3 orphaned orders without positions (order_ids: ord_123, ord_124, ord_125)
```

**Sequence Gap:**
```
⚠️ CHECK: Chain integrity: Sequence gap detected: expected seq 45, found seq 47 (missing: 2 orders)
```

**Conflicting States:**
```
❌ FAIL: Chain integrity: 2 orders with conflicting states (position pos_789: both OPEN and CLOSE orders active)
```

### 5.5 Troubleshooting Guide

**Symptom: Orphaned orders detected**
```
❌ FAIL: Chain integrity: 3 orphaned orders without positions
```

**Investigation Steps:**
1. Identify orphaned orders:
   ```bash
   redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:orders:*' | while read key; do
     position_id=$(redis-cli -h host.docker.internal -p 6380 HGET "$key" position_id)
     if [ -z "$position_id" ] || [ "$(redis-cli -h host.docker.internal -p 6380 EXISTS bmad:chiseai:positions:$position_id)" = "0" ]; then
       echo "Orphan: $key"
     fi
   done
   ```

2. Check order creation timestamps:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:orders:ord_123 created_at
   ```

3. Review order service logs:
   ```bash
   docker logs chiseai-order-service --tail 500 | grep -E "(ord_123|ord_124|ord_125)"
   ```

**Common Causes:**
- Position deletion without order cleanup
- Race condition between position and order creation
- Database transaction rollback leaving partial data
- Manual data manipulation without referential integrity

**Remediation:**
```bash
# Option 1: Reconcile orphaned orders (if safe)
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
checker.reconcile_orphaned_orders(dry_run=False)
"

# Option 2: Mark orphaned orders for cleanup (safer)
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:orders:ord_123 orphan_marked 1

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g10_chain_integrity())"
```

**Symptom: Sequence gaps detected**
```
⚠️ CHECK: Chain integrity: Sequence gap detected: expected seq 45, found seq 47
```

**Investigation Steps:**
1. Query missing sequence numbers:
   ```bash
   redis-cli -h host.docker.internal -p 6380 SORT bmad:chiseai:orders:index
   ```

2. Check for deleted orders in logs:
   ```bash
   docker logs chiseai-order-service --tail 1000 | grep -i "delete\|remove\|purge"
   ```

3. Verify backup/restore history:
   ```bash
   ls -la /backups/redis/orders/
   ```

**Common Causes:**
- Orders manually deleted during incident response
- Cleanup job removing orders by mistake
- Database restore from backup with gaps
- Sequence counter reset

**Remediation:**
```bash
# If gap is acceptable (known deletion), acknowledge
echo "Sequence gap acknowledged: orders 45-46 intentionally deleted (incident #123)" | \
  redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:chain:acknowledgments seq_gap_45_46 "$(cat)"

# If gap is unexpected, investigate data loss
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
missing = checker.find_missing_sequences()
print(f'Missing orders: {missing}')
"
```

## 6. G11 Provenance Gate

### 6.1 Purpose

The G11 gate validates data provenance and lineage tracking to ensure:
- All data has traceable source attribution
- Data transformations are documented
- Compliance with audit requirements
- Detection of untracked or unverified data sources

### 6.2 How It Works

**Validation Logic:**
1. Scan recent signals, orders, and positions
2. Verify each record has provenance metadata
3. Check data source certificates are valid
4. Validate transformation chain is complete
5. Ensure no gaps in lineage tracking

**Provenance Structure:**
```
Provenance Record:
  - source_system: Origin system (e.g., "bybit_api", "simulator")
  - source_timestamp: When data was created at source
  - ingestion_timestamp: When data entered our system
  - transformation_chain: List of transformations applied
  - data_certificate: Cryptographic signature of source data
  - lineage_id: UUID linking related records
```

**Redis Keys Involved:**
```
Provenance Store:
  - bmad:chiseai:provenance:{record_id} (hash with provenance details)
  - bmad:chiseai:provenance:index (set of tracked record IDs)
  - bmad:chiseai:provenance:by_source:{source} (set of records by source)
  
Source Certificates:
  - bmad:chiseai:provenance:cert:{source} (hash with certificate info)
  - bmad:chiseai:provenance:cert:expiry (sorted set of certificate expiry times)
```

### 6.3 Status Logic

| Condition | Status | Detail |
|-----------|--------|--------|
| All records have provenance | ✅ PASS | "X records, full provenance coverage" |
| Missing provenance < 5% | ⚠️ CHECK | "Y% records missing provenance (X/Y)" |
| Missing provenance >= 5% | ❌ FAIL | "Y% records missing provenance (X/Y)" |
| Expired certificates | ❌ FAIL | "Z expired certificates (sources: ...)" |
| Certificate expires < 24h | ⚠️ CHECK | "Certificates expiring soon: ..." |
| Incomplete transformation chain | ⚠️ CHECK | "X records with incomplete lineage" |

### 6.4 Example Outputs

**PASS Example:**
```
✅ PASS: Provenance: 1,247 records, full provenance coverage, 5 sources, all certificates valid
```

**Missing Provenance:**
```
❌ FAIL: Provenance: 8% records missing provenance (103/1,247), sources affected: bybit_api, internal_sim
```

**Expired Certificates:**
```
❌ FAIL: Provenance: 2 expired certificates (sources: bybit_api, coinbase_api)
```

**Certificate Expiring Soon:**
```
⚠️ CHECK: Provenance: Certificate for bybit_api expires in 12 hours (renewal required)
```

**Incomplete Lineage:**
```
⚠️ CHECK: Provenance: 23 records with incomplete transformation chain (orphaned mid-processing)
```

### 6.5 Troubleshooting Guide

**Symptom: Missing provenance records**
```
❌ FAIL: Provenance: 8% records missing provenance (103/1,247)
```

**Investigation Steps:**
1. Identify records without provenance:
   ```bash
   # Get all record IDs
   redis-cli -h host.docker.internal -p 6380 SMEMBERS bmad:chiseai:signals:index > /tmp/all_records.txt
   
   # Check which ones lack provenance
   while read record_id; do
     if [ "$(redis-cli -h host.docker.internal -p 6380 EXISTS bmad:chiseai:provenance:$record_id)" = "0" ]; then
       echo "Missing provenance: $record_id"
     fi
   done < /tmp/all_records.txt | head -20
   ```

2. Check ingestion pipeline:
   ```bash
   docker logs chiseai-ingestion-service --tail 500 | grep -i "provenance\|lineage"
   ```

3. Verify provenance service health:
   ```bash
   docker ps --filter name=provenance
   docker logs chiseai-provenance-service --tail 200
   ```

**Common Causes:**
- Provenance service downtime during data ingestion
- Pipeline configuration missing provenance step
- Race condition: record created before provenance tracked
- Database replication lag

**Remediation:**
```bash
# Option 1: Backfill provenance for affected records
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
backfilled = checker.backfill_provenance(source_system='bybit_api')
print(f'Backfilled {backfilled} records')
"

# Option 2: If records are from untracked legacy source, mark as such
redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:provenance:legacy_ack legacy_batch_20260315 "Pre-provenance records acknowledged"

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g11_provenance())"
```

**Symptom: Expired certificates**
```
❌ FAIL: Provenance: 2 expired certificates (sources: bybit_api, coinbase_api)
```

**Investigation Steps:**
1. Check certificate details:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:provenance:cert:bybit_api
   ```

2. Verify certificate renewal job:
   ```bash
   redis-cli -h host.docker.internal -p 6380 KEYS 'bmad:chiseai:cron:*cert*'
   ```

3. Check certificate service logs:
   ```bash
   docker logs chiseai-cert-service --tail 300 | grep -i "expir\|renew\|error"
   ```

**Common Causes:**
- Certificate renewal job not running
- API credentials expired at source
- Network issues preventing certificate fetch
- Certificate service misconfiguration

**Remediation:**
```bash
# Manual certificate refresh
python -c "
from src.governance.provenance import CertificateManager
cm = CertificateManager()
cm.renew_certificate('bybit_api')
cm.renew_certificate('coinbase_api')
"

# Verify certificates
redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:provenance:cert:bybit_api expires_at

# Re-run gate check
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g11_provenance())"
```

**Symptom: Incomplete transformation chains**
```
⚠️ CHECK: Provenance: 23 records with incomplete transformation chain
```

**Investigation Steps:**
1. Identify incomplete records:
   ```bash
   python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
incomplete = checker.find_incomplete_lineage()
for record in incomplete[:5]:
    print(f'{record[\"id\"]}: {record[\"last_step\"]} -> missing')
"
   ```

2. Check transformation service:
   ```bash
   docker logs chiseai-transform-service --tail 500 | grep -i "error\|timeout\|retry"
   ```

**Common Causes:**
- Transformation service crash mid-processing
- Timeout during multi-step transformation
- Dead letter queue not processing retries
- Out of order message delivery

**Remediation:**
```bash
# Retry incomplete transformations
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
retried = checker.retry_incomplete_transformations()
print(f'Retried {retried} records')
"

# If unrecoverable, mark as having partial lineage
echo "Partial lineage acknowledged: transformation service outage 2026-03-15" | \
  redis-cli -h host.docker.internal -p 6380 HSET bmad:chiseai:provenance:partial_ack batch_20260315 "$(cat)"
```

## 7. G12 Bybit Freshness Gate

### 7.1 Purpose

The G12 gate validates the freshness of market data received from Bybit API to ensure:
- Trading decisions use current market prices
- Stale data doesn't lead to incorrect signals
- API connectivity issues are detected early
- Data lag issues are identified before they impact trades

### 7.2 How It Works

**Validation Logic:**
1. Query latest market data timestamp from Bybit API
2. Compare to current system time
3. Check multiple data types (ticker, orderbook, klines)
4. Calculate staleness for each data stream
5. FAIL if any stream exceeds maximum staleness threshold

**Freshness Thresholds:**

| Data Type | Max Staleness | Typical Latency |
|-----------|---------------|-----------------|
| Ticker | 30 seconds | 1-5 seconds |
| Orderbook | 10 seconds | <1 second |
| Klines (1m) | 90 seconds | 30-60 seconds |
| Funding Rate | 300 seconds | 60-120 seconds |

**Redis Keys Involved:**
```
Market Data Timestamps:
  - bmad:chiseai:market:bybit:ticker:{symbol}:timestamp
  - bmad:chiseai:market:bybit:orderbook:{symbol}:timestamp
  - bmad:chiseai:market:bybit:klines:{symbol}:{interval}:timestamp
  - bmad:chiseai:market:bybit:funding:{symbol}:timestamp

Freshness Tracking:
  - bmad:chiseai:market:bybit:freshness:status
  - bmad:chiseai:market:bybit:freshness:last_check
```

### 7.3 Status Logic

| Condition | Status | Detail |
|-----------|--------|--------|
| All streams fresh | ✅ PASS | "All data streams fresh (max lag: Xs)" |
| One stream stale < 2x threshold | ⚠️ CHECK | "{stream} stale: Xs (threshold: Ys)" |
| One stream stale >= 2x threshold | ❌ FAIL | "{stream} severely stale: Xs" |
| Multiple streams stale | ❌ FAIL | "X/Y streams stale" |
| API unreachable | ❌ FAIL | "Bybit API unreachable" |
| Clock skew detected | ⚠️ CHECK | "Clock skew: Xs (verify NTP)" |

### 7.4 Example Outputs

**PASS Example:**
```
✅ PASS: Bybit freshness: All data streams fresh (max lag: 3s)
Details: ticker=2s, orderbook=1s, klines=45s, funding=85s
```

**Single Stream Stale:**
```
⚠️ CHECK: Bybit freshness: klines stale: 95s (threshold: 90s)
Details: ticker=2s, orderbook=1s, klines=95s, funding=87s
```

**Severely Stale:**
```
❌ FAIL: Bybit freshness: orderbook severely stale: 45s (threshold: 10s)
Details: ticker=3s, orderbook=45s, klines=50s, funding=90s
```

**API Unreachable:**
```
❌ FAIL: Bybit freshness: Bybit API unreachable (last successful: 180s ago)
Error: Connection timeout after 30s
```

**Clock Skew:**
```
⚠️ CHECK: Bybit freshness: Clock skew detected: 125s (Bybit ahead of system)
Recommendation: Verify NTP synchronization
```

### 7.5 Troubleshooting Guide

**Symptom: Single data stream stale**
```
⚠️ CHECK: Bybit freshness: klines stale: 95s (threshold: 90s)
```

**Investigation Steps:**
1. Check specific stream status:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:market:bybit:klines:BTCUSDT:1m:timestamp
   ```

2. Verify Bybit API directly:
   ```bash
   curl -s "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=1" | \
     jq '.result.list[0][0]'
   ```

3. Check market data service logs:
   ```bash
   docker logs chiseai-market-data --tail 500 | grep -i "klines\|bybit\|error" | tail -50
   ```

**Common Causes:**
- Bybit API degradation for specific endpoints
- Rate limiting on klines endpoint
- WebSocket disconnection for orderbook stream
- Processing lag in market data service

**Remediation:**
```bash
# Check if issue is Bybit-wide or specific to our connection
curl -s "https://api.bybit.com/v5/market/time" | jq '.time'

# Restart market data service for affected stream
docker restart chiseai-market-data

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g12_bybit_freshness())"
```

**Symptom: Multiple streams stale**
```
❌ FAIL: Bybit freshness: 3/4 streams stale (ticker=35s, orderbook=42s, klines=180s)
```

**Investigation Steps:**
1. Check network connectivity:
   ```bash
   ping -c 5 api.bybit.com
   traceroute api.bybit.com
   ```

2. Verify Bybit API status:
   ```bash
   curl -s "https://api.bybit.com/v5/market/time"
   ```

3. Check market data service health:
   ```bash
   docker ps --filter name=market-data
   docker stats chiseai-market-data --no-stream
   ```

4. Review service logs for errors:
   ```bash
   docker logs chiseai-market-data --tail 1000 | grep -E "(error|timeout|disconnect|reconnect)"
   ```

**Common Causes:**
- Network partition or connectivity loss
- Bybit API outage
- Market data service crash or resource exhaustion
- DNS resolution failures
- Firewall blocking connections

**Remediation:**
```bash
# Option 1: Restart market data service
docker restart chiseai-market-data

# Option 2: If DNS issue, flush and retry
sudo systemd-resolve --flush-caches

# Option 3: Check if Bybit is down globally
curl -s "https://api.bybit.com/v5/market/time" || echo "Bybit API unreachable"

# Verify recovery
watch -n 5 'python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g12_bybit_freshness())"'
```

**Symptom: Clock skew detected**
```
⚠️ CHECK: Bybit freshness: Clock skew detected: 125s (Bybit ahead of system)
```

**Investigation Steps:**
1. Check system time:
   ```bash
   date -u
   timedatectl status
   ```

2. Verify NTP synchronization:
   ```bash
   ntpq -p
   # or
   chronyc tracking
   ```

3. Compare with Bybit time:
   ```bash
   bybit_time=$(curl -s "https://api.bybit.com/v5/market/time" | jq -r '.time')
   local_time=$(date +%s%3N)
   skew=$(( (bybit_time - local_time) / 1000 ))
   echo "Skew: ${skew}s (positive = Bybit ahead)"
   ```

**Common Causes:**
- NTP service not running
- NTP servers unreachable
- VM clock drift (common in virtualized environments)
- Container time not synced with host

**Remediation:**
```bash
# Restart NTP service
sudo systemctl restart ntp
# or
sudo systemctl restart chronyd

# Force time sync
sudo ntpdate -s time.google.com
# or
sudo chronyc makestep

# Verify sync
ntpq -p

# Re-run gate check
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g12_bybit_freshness())"
```

**Symptom: API unreachable**
```
❌ FAIL: Bybit freshness: Bybit API unreachable (last successful: 180s ago)
```

**Investigation Steps:**
1. Test basic connectivity:
   ```bash
   curl -v --max-time 10 "https://api.bybit.com/v5/market/time"
   ```

2. Check SSL/TLS:
   ```bash
   openssl s_client -connect api.bybit.com:443 -servername api.bybit.com < /dev/null
   ```

3. Verify proxy settings:
   ```bash
   env | grep -i proxy
   cat /etc/environment | grep -i proxy
   ```

4. Check container network:
   ```bash
   docker network inspect chiseai
   docker exec chiseai-market-data nslookup api.bybit.com
   ```

**Common Causes:**
- Bybit API maintenance or outage
- Network firewall blocking HTTPS
- Proxy misconfiguration
- SSL certificate issues
- Container network isolation

**Remediation:**
```bash
# Check Bybit status page (if available)
curl -s "https://status.bybit.com/api/v2/status.json" | jq '.status.description' 2>/dev/null || echo "Status page unavailable"

# Test from host (bypass container networking)
curl -s "https://api.bybit.com/v5/market/time"

# If container network issue, recreate container
docker stop chiseai-market-data
docker rm chiseai-market-data
docker-compose up -d chiseai-market-data

# Verify recovery
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g12_bybit_freshness())"
```

## 8. Running Checkpoint Checks

### 8.1 Manual Check Execution

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

# Check only G10
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g10_chain_integrity())"

# Check only G11
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g11_provenance())"

# Check only G12
python -c "from src.governance.checkpoint import GateChecker; print(GateChecker().check_g12_bybit_freshness())"
```

### 8.2 Expected Output Format

**Healthy System:**
```
Overall Status: PASS
Pass: 12, Fail: 0, Check: 0

G1: ✅ PASS - Heartbeat 12s ago, uptime: 45m
G2: ✅ PASS - HEALTHY: 12 signals, 3 actionable, backlog 2 (normal)
G3: ✅ PASS - 847 outcomes recorded
G4: ✅ PASS - Kill switch armed and ready
G5: ✅ PASS - pager:PASS(45s) | signal-growth:PASS(12m) | hourly-health:PASS(35m)
G6: ✅ PASS - Bybit API reachable
G7: ✅ PASS - Redis OK, 1247 keys, 48h uptime
G8: ✅ PASS - Burn-in verdict: GO | Pipeline: 45 signals → 847 outcomes
G9: ✅ PASS - Metric integrity: Raw count matches aggregate (0% variance)
G10: ✅ PASS - Chain integrity: 145 orders, 48 positions, all chains valid
G11: ✅ PASS - Provenance: 1,247 records, full provenance coverage
G12: ✅ PASS - Bybit freshness: All data streams fresh (max lag: 3s)
```

**System with Issues:**
```
Overall Status: CHECK
Pass: 9, Fail: 1, Check: 2

G1: ✅ PASS - Heartbeat 8s ago, uptime: 45m
G2: ⚠️ CHECK - BOTTLENECK: 5 actionable signals, 15 backlog (downstream stalled)
G3: ✅ PASS - 847 outcomes recorded
G4: ✅ PASS - Kill switch armed and ready
G5: ⚠️ CHECK - signal-growth:CHECK(35m,missed=1) | hourly-health:CHECK(75m,missed=1)
G6: ✅ PASS - Bybit API reachable
G7: ✅ PASS - Redis OK, 1247 keys, 48h uptime
G8: ❌ FAIL - Burn-in verdict: NO-GO | Pipeline halted
G9: ✅ PASS - Metric integrity: Raw count matches aggregate (0% variance)
G10: ✅ PASS - Chain integrity: 145 orders, 48 positions, all chains valid
G11: ✅ PASS - Provenance: 1,247 records, full provenance coverage
G12: ⚠️ CHECK - Bybit freshness: klines stale: 95s (threshold: 90s)
```

## 9. Integration Points

### 9.1 Pre-Trade Checks

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

### 9.2 Monitoring Integration

Gate results are published to:
- Redis: `bmad:chiseai:checkpoint:latest`
- Grafana: Via Prometheus exporter
- Discord: Alert notifications

## 10. Rollback Procedures

### 10.1 Gate Failure Response

**Immediate Actions:**
1. Stop trading operations if G4 (kill switch) or G8 (pipeline) fail
2. Notify on-call via Discord
3. Document failure in incident log

**Recovery Steps:**
1. Identify failing gates
2. Follow gate-specific troubleshooting
3. Verify resolution with manual check
4. Resume operations only after PASS status

### 10.2 Emergency Override

⚠️ **Warning:** Override only in emergency situations with explicit approval.

```python
# Temporarily bypass gate check (requires human approval)
import os
os.environ["CHECKPOINT_BYPASS"] = "EMERGENCY-2026-03-15-001"

# Document override
# Required: Incident ticket, approver name, business justification
```

## 11. Related Documentation

- [Observability Guardrails](./observability-guardrails.md) - Actionable-zero alert and metric integrity
- [Kill Switch Runbook](./kill-switch-trigger.md) - Emergency halt procedures
- [Tempo Operations](./tempo-operations.md) - Distributed tracing
- [Incident Response](./incident_response.md) - Incident handling procedures

## 12. Appendix: Redis Key Reference

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
| `bmad:chiseai:orders:*` | Hash | Individual order data |
| `bmad:chiseai:orders:index` | Set | Index of all order IDs |
| `bmad:chiseai:positions:*` | Hash | Individual position data |
| `bmad:chiseai:positions:index` | Set | Index of all position IDs |
| `bmad:chiseai:provenance:*` | Hash | Provenance records |
| `bmad:chiseai:provenance:index` | Set | Index of tracked records |
| `bmad:chiseai:market:bybit:*` | Hash/String | Bybit market data timestamps |
