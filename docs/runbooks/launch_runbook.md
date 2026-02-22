---
title: Launch Safety Runbook
category: safety
severity: critical
estimated_time_to_resolve: 5-15 minutes
last_updated: 2026-02-22
maintainers: ops-team, safety-team
story_id: ST-LAUNCH-021
executable: true
steps:
  - name: "Verify kill switch status"
    command: "curl -s http://localhost:8001/api/v1/safety/kill-switch/status | jq -r '.state'"
    verify: "ARMED"
  - name: "Check circuit breaker state"
    command: "curl -s http://localhost:8001/api/v1/safety/circuit-breaker/status | jq -r '.state'"
    verify: "CLOSED"
  - name: "Validate order idempotency"
    command: "curl -s http://localhost:8001/api/v1/safety/idempotency/check | jq -r '.status'"
    verify: "valid"
  - name: "Run pre-launch safety checklist"
    command: "python3 scripts/ops/validate_runbooks.py --scenario safety"
    verify: "PASS"
---

# Launch Safety Runbook

> **Story:** ST-LAUNCH-021  
> **Last Updated:** 2026-02-22  
> **Owner:** Platform Safety Team  
> **Rollout SLA:** < 5 minutes for safety rollback

---

## Overview

This runbook provides comprehensive safety procedures for the ChiseAI platform launch, including kill switch operations, circuit breaker management, and order idempotency verification. These procedures ensure rapid response to critical issues with a guaranteed < 5 minute rollback SLA.

---

## 1. Kill Switch Procedures

### 1.1 When to Trigger Kill Switch

**CRITICAL Triggers (Immediate Action Required):**

| Condition | Threshold | Auto-Trigger | Manual Override |
|-----------|-----------|--------------|-----------------|
| Critical margin utilization | ≥ 95% | Yes | Disabled during trigger |
| Extreme concentration risk | ≥ 80% single asset | Yes | Requires 2-person approval |
| Circuit breaker consecutive failures | ≥ 5 in 5 minutes | Yes | Immediate halt |
| Redis connectivity failure | > 30 seconds | Configurable | Manual only if configured |
| Manual emergency activation | N/A | N/A | Any operator with safety role |
| Risk threshold breach | Model-defined | Yes | 15-minute override window |

**WARNING Triggers (Evaluate within 2 minutes):**

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Elevated margin utilization | 85-94% | Alert + preparation |
| Moderate concentration risk | 60-79% single asset | Alert + position review |
| API latency spike | > 2 seconds p95 | Monitor closely |
| Unusual order rejection rate | > 10% | Investigate immediately |

### 1.2 How to Trigger Kill Switch

#### Automatic Trigger (System-Initiated)

```python
# The kill switch is automatically triggered when:
# - Any CRITICAL threshold is breached
# - Circuit breaker enters FAILED state
# - Manual activation API is called

# System trigger log pattern:
# [TIMESTAMP] KILL_SWITCH_AUTO_TRIGGER: reason=<reason> threshold=<value>
```

#### Manual Trigger (Operator-Initiated)

**Via API (Immediate):**
```bash
# Trigger kill switch with reason
curl -X POST http://localhost:8001/api/v1/safety/kill-switch/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SAFETY_TOKEN" \
  -d '{
    "reason": "manual_emergency",
    "operator_id": "<operator_id>",
    "justification": "<detailed_reason>",
    "require_confirmation": true
  }'

# Expected response:
# {
#   "status": "triggered",
#   "timestamp": "2026-02-22T12:00:00Z",
#   "trigger_id": "ks-20260222-001",
#   "confirmation_required": true
# }
```

**Via CLI (Scripted):**
```bash
# Use the trigger script
./scripts/ops/trigger_kill_switch.sh \
  --reason="manual_emergency" \
  --operator="<operator_id>" \
  --justification="<reason>"

# Script will prompt for confirmation unless --force is used
```

**Via Dashboard (Emergency Button):**
```
1. Navigate to: http://localhost:8502/safety
2. Click "EMERGENCY STOP" button (red, top-right)
3. Confirm in modal dialog
4. Enter operator credentials
5. Click "CONFIRM EMERGENCY STOP"
```

### 1.3 Kill Switch Verification Steps

After trigger (within 30 seconds):

```bash
# 1. Verify kill switch state
curl -s http://localhost:8001/api/v1/safety/kill-switch/status | jq '.'

# Expected output:
# {
#   "state": "TRIGGERED",
#   "triggered_at": "2026-02-22T12:00:00Z",
#   "trigger_id": "ks-20260222-001",
#   "reason": "manual_emergency",
#   "operator_id": "<operator_id>"
# }

# 2. Verify trading halted
curl -s http://localhost:8001/api/v1/execution/status | jq -r '.status'

# Expected: "halted" or "paused"

# 3. Verify no new orders accepted
curl -s http://localhost:8001/api/v1/orders/recent | jq '.orders | length'

# Expected: 0 new orders since trigger timestamp

# 4. Check kill-switch panel in Grafana
echo "Verify Grafana panel shows: TRIGGERED (red)"
# Navigate to: http://localhost:3001/d/chiseai/safety

# 5. Verify alert notifications sent
docker logs chiseai-api --tail 20 | grep -i "kill.switch\|alert.sent"
```

**Kill Switch State Machine:**

```
ARMED → TRIGGERED → (RECOVERY) → VERIFY → ARMED
  ↑                              ↓
  └──────────────────────────────┘
        (Manual reset only)
```

---

## 2. Circuit Breaker Management

### 2.1 Circuit Breaker States

| State | Description | Behavior | Recovery |
|-------|-------------|----------|----------|
| **CLOSED** | Normal operation | Requests flow through | N/A |
| **OPEN** | Failure threshold exceeded | All requests rejected | Automatic after cooldown |
| **HALF_OPEN** | Testing recovery | Limited requests allowed | Transition to CLOSED or OPEN |
| **FORCED_CLOSED** | Manual override | Requests forced through | Manual only |

### 2.2 State Transitions

```
CLOSED ──[failures >= threshold]──→ OPEN
  ↑                                  │
  │                                  │ [cooldown expires]
  │                                  ↓
  └──────[success >= threshold]──── HALF_OPEN
         [failures detected] ──────→ OPEN
```

**Transition Thresholds:**
- CLOSED → OPEN: 5 consecutive failures OR 50% error rate over 1 minute
- OPEN → HALF_OPEN: 60 second cooldown period
- HALF_OPEN → CLOSED: 3 consecutive successes
- HALF_OPEN → OPEN: Any failure during test

### 2.3 Manual Override Procedures

**Force Close (Emergency Only):**
```bash
# CAUTION: Bypasses all safety checks
# Requires: safety_admin role

curl -X POST http://localhost:8001/api/v1/safety/circuit-breaker/force-close \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SAFETY_ADMIN_TOKEN" \
  -d '{
    "service": "<service_name>",
    "duration_seconds": 300,
    "justification": "Emergency bypass for critical operation",
    "operator_id": "<operator_id>",
    "two_person_approval": {
      "primary": "<operator_id>",
      "secondary": "<approver_id>"
    }
  }'

# Response:
# {
#   "status": "forced_closed",
#   "service": "<service_name>",
#   "expires_at": "2026-02-22T12:05:00Z",
#   "override_id": "cb-override-001"
# }
```

**Manual Reset (After Issue Resolution):**
```bash
# Reset circuit breaker to CLOSED state
curl -X POST http://localhost:8001/api/v1/safety/circuit-breaker/reset \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SAFETY_TOKEN" \
  -d '{
    "service": "<service_name>",
    "operator_id": "<operator_id>",
    "verification_check": true
  }'
```

### 2.4 Health Checks

**Check Circuit Breaker Status:**
```bash
# Get all circuit breakers
curl -s http://localhost:8001/api/v1/safety/circuit-breaker/status | jq '.'

# Get specific service
curl -s http://localhost:8001/api/v1/safety/circuit-breaker/status/<service_name> | jq '.'

# Example response:
# {
#   "service": "order_executor",
#   "state": "CLOSED",
#   "failure_count": 0,
#   "last_failure": null,
#   "consecutive_successes": 42,
#   "metrics": {
#     "requests_total": 1000,
#     "errors_total": 0,
#     "latency_p95_ms": 45
#   }
# }
```

---

## 3. Order Idempotency Verification

### 3.1 Duplicate Detection

**Detection Mechanisms:**

1. **Client-Generated Idempotency Keys**
   ```python
   # Clients must provide idempotency_key for all orders
   {
     "idempotency_key": "<uuid-v4>",
     "client_id": "<client_id>",
     "timestamp": "2026-02-22T12:00:00Z"
   }
   ```

2. **Server-Side Duplicate Detection**
   ```bash
   # Check for duplicate orders in last 24 hours
   curl -s "http://localhost:8001/api/v1/safety/idempotency/duplicates?window=24h" | jq '.'
   
   # Response includes:
   # - duplicate_count: Number of detected duplicates
   # - rejected_count: Number of rejected duplicates
   # - violation_details: List of duplicate order details
   ```

3. **Fingerprint-Based Detection**
   - Hash of: symbol + side + quantity + price + timestamp_window
   - Window: 5 seconds for market orders, 60 seconds for limit orders

### 3.2 Replay Protection

**Order Replay Prevention:**

```bash
# Verify replay protection is active
curl -s http://localhost:8001/api/v1/safety/idempotency/replay-protection | jq '.'

# Expected:
# {
#   "enabled": true,
#   "nonce_window_seconds": 300,
#   "max_nonce_age_seconds": 86400,
#   "rejected_replay_attempts": 0
# }
```

**Replay Detection Query:**
```sql
-- Query to detect potential replay attacks
SELECT 
  idempotency_key,
  COUNT(*) as attempt_count,
  MIN(created_at) as first_attempt,
  MAX(created_at) as last_attempt,
  COUNT(DISTINCT source_ip) as unique_sources
FROM orders
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY idempotency_key
HAVING COUNT(*) > 1 OR COUNT(DISTINCT source_ip) > 1;
```

### 3.3 Idempotency Verification Commands

**Run Full Verification:**
```bash
# Comprehensive idempotency check
python3 scripts/ops/validate_runbooks.py --scenario safety --check idempotency

# Or via API
curl -X POST http://localhost:8001/api/v1/safety/idempotency/verify \
  -H "Content-Type: application/json" \
  -d '{
    "window": "1h",
    "include_pending": true,
    "strict_mode": true
  }'
```

**Check Idempotency Key Store:**
```bash
# Check Redis for idempotency keys
redis-cli -p 6380 EVAL "
  local keys = redis.call('KEYS', 'idempotency:*')
  return {#keys, keys[1], keys[2]}
" 0

# Check key TTL distribution
redis-cli -p 6380 EVAL "
  local keys = redis.call('KEYS', 'idempotency:*')
  local ttls = {}
  for i=1,math.min(100,#keys) do
    table.insert(ttls, redis.call('TTL', keys[i]))
  end
  return ttls
" 0
```

---

## 4. Safety Rollback Procedures

### 4.1 Rollback Triggers

**Immediate Rollback Required:**
- Kill switch triggered and cannot be resolved within 5 minutes
- Circuit breaker stuck in OPEN state > 10 minutes
- Order idempotency violations > 1% of orders
- Safety system itself is compromised

### 4.2 Step-by-Step Rollback (5-Minute SLA)

**Minute 0-1: Immediate Actions**
```bash
# 1. Trigger kill switch (if not already triggered)
curl -X POST http://localhost:8001/api/v1/safety/kill-switch/trigger \
  -d '{"reason": "rollback_initiated", "operator_id": "<id>"}'

# 2. Verify all trading halted
curl -s http://localhost:8001/api/v1/execution/status | jq -r '.status'
# Expected: "halted"

# 3. Capture current state
./scripts/ops/rollback_deployment.sh --capture-state --tag="pre-rollback-$(date +%s)"
```

**Minute 1-2: Stop Services**
```bash
# 4. Gracefully stop trading services
docker stop chiseai-api chiseai-executor

# 5. Verify no orders in flight
curl -s http://localhost:8001/api/v1/orders/pending 2>/dev/null | jq '.orders | length'
# Expected: Connection refused or 0 orders

# 6. Backup current state
redis-cli -p 6380 BGSAVE
docker exec chiseai-postgres pg_dump -U chiseai chiseai > /tmp/rollback-backup-$(date +%Y%m%d-%H%M%S).sql
```

**Minute 2-4: Restore Previous Version**
```bash
# 7. Identify rollback target
ROLLBACK_VERSION=$(curl -s http://localhost:8001/api/v1/system/last-stable-version)
echo "Rolling back to: $ROLLBACK_VERSION"

# 8. Rollback deployment
./scripts/ops/rollback_deployment.sh \
  --to-version="$ROLLBACK_VERSION" \
  --mode="safety-rollback" \
  --skip-tests

# 9. Verify rollback containers
docker ps --filter "name=chiseai" --format "{{.Names}}: {{.Status}}"
```

**Minute 4-5: Verification & Restore**
```bash
# 10. Verify safety systems online
curl -s http://localhost:8001/api/v1/safety/kill-switch/status | jq -r '.state'
# Expected: "TRIGGERED" (kill switch remains active)

curl -s http://localhost:8001/api/v1/safety/circuit-breaker/status | jq -r '.[].state'
# Expected: All "CLOSED"

curl -s http://localhost:8001/api/v1/safety/idempotency/check | jq -r '.status'
# Expected: "valid"

# 11. Clear kill switch (only after full verification)
curl -X POST http://localhost:8001/api/v1/safety/kill-switch/clear \
  -d '{"operator_id": "<id>", "post_rollback": true}'

# 12. Final verification
curl -s http://localhost:8001/api/v1/execution/status | jq -r '.status'
# Expected: "active" or "paper"
```

### 4.3 Rollback Verification Checklist

- [ ] Kill switch can be triggered and cleared
- [ ] All circuit breakers report CLOSED state
- [ ] Idempotency verification passes
- [ ] No orphaned orders in PENDING state
- [ ] Position reconciliation matches pre-rollback
- [ ] Risk metrics within normal bounds
- [ ] Logging and monitoring fully operational

---

## 5. Pre-Launch Safety Checklist

### 5.1 All 11 Items

**Checklist (All Must Pass):**

| # | Item | Verification Command | Pass Criteria |
|---|------|---------------------|---------------|
| 1 | Kill switch armed | `curl /safety/kill-switch/status` | state == "ARMED" |
| 2 | Circuit breakers closed | `curl /safety/circuit-breaker/status` | All states == "CLOSED" |
| 3 | Idempotency system active | `curl /safety/idempotency/check` | status == "valid" |
| 4 | Risk limits configured | `curl /safety/risk-limits` | All limits > 0 |
| 5 | Alert endpoints reachable | `curl /health/alerts` | status == "ok" |
| 6 | Safety logging enabled | Check log files | No errors, events logging |
| 7 | Rollback tested < 7 days | Check deployment logs | Last rollback within 7 days |
| 8 | Emergency contacts configured | `curl /safety/contacts` | All roles have contacts |
| 9 | Safety dashboard accessible | `curl -I http://localhost:8502/safety` | HTTP 200 |
| 10 | Operator permissions verified | Test auth endpoints | safety_role grants work |
| 11 | Runbook validation passed | `python scripts/ops/validate_runbooks.py --scenario safety` | Exit code 0 |

**Automated Checklist Runner:**
```bash
# Run all checks
./scripts/ops/validate_runbooks.py --scenario safety --checklist all

# Or individually
for i in {1..11}; do
  echo "Checking item $i..."
  ./scripts/ops/validate_runbooks.py --scenario safety --checklist $i
done
```

### 5.2 Checklist Failure Procedures

If any item fails:

1. **Document the failure**
   ```bash
   ./scripts/ops/log_incident.sh \
     --severity="high" \
     --category="safety-checklist-failure" \
     --story="ST-LAUNCH-021"
   ```

2. **Do not proceed with launch**

3. **Escalate to safety team lead**

4. **Create remediation task**

---

## 6. Post-Incident Safety Verification

### 6.1 After Kill Switch Trigger

**Immediate (within 5 minutes):**
```bash
# Verify system stable
curl -s http://localhost:8001/api/v1/health | jq '.status'

# Check no data corruption
./scripts/ops/recovery_audit_query.sh --check-data-integrity

# Verify positions reconciled
curl -s http://localhost:8001/api/v1/portfolio/reconcile | jq '.reconciled'
```

**Before Resuming Trading:**
- [ ] Root cause of trigger identified and documented
- [ ] Fix implemented and tested in paper mode
- [ ] Safety systems verified operational
- [ ] Management approval obtained
- [ ] Communication sent to stakeholders

### 6.2 After Circuit Breaker Event

**Verification Steps:**
```bash
# 1. Check circuit breaker history
curl -s http://localhost:8001/api/v1/safety/circuit-breaker/history | jq '.'

# 2. Verify service recovered
curl -s http://localhost:8001/api/v1/health/<service> | jq '.status'

# 3. Check for data inconsistencies
./scripts/ops/recovery_audit_query.sh --service=<service>

# 4. Review impact metrics
curl -s http://localhost:8001/api/v1/safety/impact-metrics | jq '.'
```

### 6.3 After Idempotency Violation

**Investigation Procedure:**
```bash
# 1. Identify affected orders
./scripts/ops/validate_runbooks.py --scenario safety --check idempotency --detailed

# 2. Check for root cause
# - Review application logs
# - Check for clock skew issues
# - Verify idempotency key generation

# 3. Assess impact
curl -s http://localhost:8001/api/v1/safety/idempotency/impact | jq '.'

# 4. Implement fix if needed
# Typically: Fix client-side key generation or increase server-side window
```

---

## 7. Monitoring and Alerting

### 7.1 Key Safety Metrics

| Metric | Warning Threshold | Critical Threshold | Alert |
|--------|-------------------|-------------------|-------|
| Kill switch trigger rate | > 1/hour | > 3/hour | P1 |
| Circuit breaker open time | > 30 sec | > 5 min | P0/P1 |
| Idempotency violation rate | > 0.1% | > 1% | P1/P0 |
| Safety system latency | > 100ms | > 500ms | P2/P1 |
| Rollback execution time | > 3 min | > 5 min | P1 |

### 7.2 Dashboard URLs

- **Safety Overview:** http://localhost:3001/d/chiseai/safety
- **Kill Switch Panel:** http://localhost:3001/d/chiseai/safety/kill-switch
- **Circuit Breakers:** http://localhost:3001/d/chiseai/safety/circuit-breakers
- **Idempotency Metrics:** http://localhost:3001/d/chiseai/safety/idempotency

### 7.3 Alert Routing

| Alert Type | Primary | Secondary | Escalation |
|------------|---------|-----------|------------|
| Kill Switch Triggered | On-call Engineer | Safety Lead | Platform Lead (15 min) |
| Circuit Breaker Open > 5 min | Service Owner | Platform Engineer | VP Engineering (30 min) |
| Idempotency Violations | Backend Team | Data Team | CTO (1 hour) |
| Safety System Degraded | Platform Team | DevOps | Platform Lead (30 min) |

---

## 8. Related Runbooks

- [Kill Switch Trigger](kill-switch-trigger.md) - Detailed kill switch procedures
- [Circuit Breaker Management](autonomous_control_plane.md) - Circuit breaker alerts
- [Incident Response](incident_response.md) - General incident handling
- [Paper Trading Operations](paper-trading-operations.md) - Daily operations

---

## 9. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-22 | Platform Team | Initial creation for ST-LAUNCH-021 |
