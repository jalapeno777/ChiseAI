---
title: Kill Switch Trigger Runbook
category: emergency
severity: emergency
estimated_time_to_resolve: 15 minutes
last_updated: 2026-02-17
maintainers: ops-team
story_id: PAPER-004
executable: true
steps:
  - name: "Check execution status"
    command: "curl -s http://localhost:8001/api/v1/execution/status | jq -r '.status'"
    verify: "paused"
  - name: "Cancel pending orders"
    command: "curl -s -X POST http://localhost:8001/api/v1/orders/cancel-all -H 'Content-Type: application/json' -d '{\"reason\": \"kill_switch_triggered\"}'"
  - name: "Log incident"
    script: "scripts/ops/log_incident.sh"
    description: "Creates incident record for post-mortem analysis"
  - name: "Capture portfolio state"
    command: "curl -s http://localhost:8001/api/v1/portfolio/state > /tmp/kill_switch_state_$(date +%Y%m%d_%H%M%S).json"
---

# Kill Switch Trigger Runbook

## Problem Description

The kill switch has been activated due to critical risk conditions. All trading operations must be immediately halted to prevent further losses.

**Kill Switch Triggers:**
- Critical margin utilization (≥95%)
- Extreme concentration risk (≥80%)
- Manual activation by operator
- Automated risk threshold breach
- Circuit breaker activation (consecutive failures)
- Redis connectivity failure (if configured)

## Kill-Switch Panel Indicators

The kill-switch panel in Grafana provides visual indicators of the current system state.

### Visual States

| State | Color | Indicator | Meaning |
|-------|-------|-----------|---------|
| **ARMED** | 🟢 Green | Large green badge | System is ready for trading. Kill switch is active and monitoring. |
| **TRIGGERED** | 🔴 Red | Large red badge with alert icon | Kill switch has been activated. Trading is halted. Immediate action required. |
| **DISABLED** | ⚪ Gray | Grayed-out badge | Kill switch is manually disabled. Trading continues without kill-switch protection. |

### Panel Metrics

The kill-switch panel displays the following metrics:

- **Current State**: ARMED, TRIGGERED, or DISABLED
- **Last Trigger**: Timestamp of the last kill-switch activation
- **Positions Closed**: Number of positions automatically closed
- **Trigger Reason**: Why the kill switch was activated
- **Circuit Breaker State**: OPEN or CLOSED
- **Consecutive Failures**: Count of consecutive trigger conditions

### Grafana Panel Location

```
[Grafana Panel: ChiseAI > Paper Trading > Kill-Switch Status]

Navigation:
1. Open Grafana (http://localhost:3001)
2. Navigate to Dashboards > ChiseAI - Paper Trading
3. Locate the "Kill-Switch Status" panel (top row)
4. Panel refreshes every 5 seconds
```

## Pre-Trigger Checklist

Before manually triggering the kill switch, review the panel metrics:

- [ ] Check kill-switch panel shows **ARMED** (not already triggered)
- [ ] Verify circuit breaker is **CLOSED** (green)
- [ ] Review consecutive failures count (should be 0)
- [ ] Confirm no recent triggers in last 5 minutes
- [ ] Check risk metrics dashboard for trigger conditions

**If panel already shows TRIGGERED:**
- Do not attempt to trigger again
- Follow the recovery procedures below
- Investigate why it was already triggered

## Immediate Actions (0-2 minutes)

### 1. Confirm Kill Switch Activation

**Check Alert Details:**
```bash
# View recent kill switch alerts
docker logs chiseai-api --tail 50 | grep -i "kill.switch\|emergency"

# Check alert in Redis
redis-cli -p 6380 HGETALL "alerts:kill_switch:latest"
```

**Verify System State:**
- Grafana Dashboard: `Grafana > Dashboards > ChiseAI - Risk Alerts`
- Look for: 🚨 KILL SWITCH ACTIVATED alert
- Note: Portfolio ID, trigger reason, current values

**Check Kill-Switch Panel:**
```bash
# Quick status check using the kill-switch script
./scripts/ops/kill_switch_check.sh

# Or query directly
curl http://localhost:8001/api/v1/execution/kill-switch/status | jq '.'
```
- Verify panel shows **TRIGGERED** (red) status
- Check Grafana: `[Grafana Panel: ChiseAI > Paper Trading > Kill-Switch Status]`

### 2. Immediate Position Freeze

**Stop All Order Placement:**
```bash
# Disable order execution
curl -X POST http://localhost:8001/api/v1/execution/pause \
  -H "Content-Type: application/json" \
  -d '{"reason": "kill_switch_activated", "duration_minutes": 30}'
```

**Cancel Pending Orders:**
```bash
# Cancel all pending orders
curl -X POST http://localhost:8001/api/v1/orders/cancel-all \
  -H "Content-Type: application/json" \
  -d '{"reason": "kill_switch_triggered"}'
```

**Verify Panel Updates:**
```bash
# Wait 5 seconds for panel refresh
sleep 5

# Check panel shows TRIGGERED status
./scripts/ops/kill_switch_check.sh

# Expected: State: TRIGGERED (red)
# Verify Grafana panel updates to red within 10 seconds
```

### 3. Manual Trigger Procedure (If Not Auto-Triggered)

If you need to manually trigger the kill switch:

**Step 1: Verify Panel State**
```bash
# Check current status before triggering
./scripts/ops/kill_switch_check.sh

# Confirm state is ARMED (not already triggered)
```

**Step 2: Execute Manual Trigger**
```bash
# Trigger kill switch via API
curl -X POST http://localhost:8001/api/v1/execution/kill-switch/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "manual_operator_trigger",
    "operator_id": "[YOUR_OPERATOR_ID]",
    "justification": "[BRIEF_REASON]"
  }'
```

**Step 3: Verify Panel Update**
```bash
# Wait for panel to update
sleep 5

# Confirm TRIGGERED state
./scripts/ops/kill_switch_check.sh

# Check Grafana panel shows red TRIGGERED status
```

## Verification Steps (2-5 minutes)

### 1. Confirm Trading Halted

**Check Execution Status:**
```bash
# Verify execution is paused
curl http://localhost:8001/api/v1/execution/status

# Expected response:
# {"status": "paused", "reason": "kill_switch_activated", "paused_at": "..."}
```

**Verify No Active Orders:**
```bash
# Check for any remaining pending orders
curl http://localhost:8001/api/v1/orders/pending | jq '.orders | length'

# Should return: 0
```

### 2. Document Trigger Conditions

**Record in Incident Log:**
```bash
# Create incident record
./scripts/ops/log_incident.sh \
  --type "kill_switch" \
  --severity "emergency" \
  --reason "[REASON_FROM_ALERT]" \
  --portfolio "[PORTFOLIO_ID]"
```

**Capture Current State:**
```bash
# Save current portfolio state
curl http://localhost:8001/api/v1/portfolio/state > /tmp/kill_switch_state_$(date +%Y%m%d_%H%M%S).json
```

## Assessment Phase (5-10 minutes)

### 1. Analyze Trigger Cause

**Review Risk Metrics:**
```bash
# Get current risk metrics
curl http://localhost:8001/api/v1/risk/metrics | jq '.'
```

**Check Historical Context:**
- Grafana: `Risk Metrics` dashboard
- Time range: Last 1 hour before trigger
- Look for: Gradual degradation vs sudden spike

### 2. Determine Recovery Path

| Trigger Cause | Recovery Action |
|---------------|----------------|
| Margin Utilization ≥95% | Close largest losing positions |
| Concentration ≥80% | Reduce oversized position |
| Manual Activation | Review with triggering operator |
| System Error | Investigate root cause first |

## Recovery Procedures (10-15 minutes)

### 1. Address Root Cause

**For High Margin Utilization:**
```bash
# Identify largest positions
curl http://localhost:8001/api/v1/positions | jq '.positions | sort_by(-.notional_value) | .[0:5]'

# Close specific position (if needed)
curl -X POST http://localhost:8001/api/v1/positions/close \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-USDT", "reason": "kill_switch_recovery"}'
```

**For High Concentration:**
```bash
# Check concentration by token
curl http://localhost:8001/api/v1/risk/concentration | jq '.'

# Reduce oversized position
curl -X POST http://localhost:8001/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "[OVERCONCENTRATED_TOKEN]",
    "side": "sell",
    "size": "[REDUCTION_SIZE]",
    "reason": "concentration_reduction"
  }'
```

### 2. Verify Risk Metrics Improved

**Re-check Thresholds:**
```bash
# Get updated risk metrics
curl http://localhost:8001/api/v1/risk/metrics | jq '{
  margin_utilization: .margin_utilization.utilization_pct,
  concentration_risk: .concentration_risk
}'
```

**Confirm Safe Levels:**
- Margin utilization: <90% (preferably <85%)
- Concentration risk: <70% (preferably <60%)

## Post-Trigger Recovery

### 1. Gradual Re-enablement

**Step 1: Resume in Paper Mode Only**
```bash
# Enable paper trading only
curl -X POST http://localhost:8001/api/v1/execution/resume \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper_only", "reason": "kill_switch_recovery"}'
```

**Step 2: Monitor for 5 Minutes**
- Watch risk metrics dashboard
- Verify no new alerts
- Confirm stable operation

**Step 3: Full Resume (if approved)**
```bash
# Resume full trading (requires operator approval)
curl -X POST http://localhost:8001/api/v1/execution/resume \
  -H "Content-Type: application/json" \
  -H "X-Approval-Code: [APPROVAL_CODE]" \
  -d '{"mode": "full", "reason": "kill_switch_recovery_complete"}'
```

### 2. Post-Recovery Verification

**System Health Check:**
```bash
# Run full health check
./scripts/ops/health_check.sh --verbose

# Check all services
docker ps --filter "name=chiseai" --format "{{.Names}}: {{.Status}}"
```

**Alert System Check:**
```bash
# Verify alert pipeline
curl http://localhost:8001/api/v1/alerts/health

# Check Discord webhook
curl -X POST [WEBHOOK_URL] -d '{"content": "Kill switch recovery test"}'
```

## Prevention Measures

### Early Warning Thresholds

Configure alerts BEFORE kill switch triggers:

| Metric | Warning | Critical | Kill Switch |
|--------|---------|----------|-------------|
| Margin Utilization | 85% | 90% | 95% |
| Concentration Risk | 60% | 70% | 80% |
| Drawdown | 10% | 12% | 15% |

### Automated Safeguards

1. **Position Size Limits:** Auto-reject orders exceeding limits
2. **Concentration Checks:** Block orders that increase concentration >70%
3. **Margin Buffer:** Maintain 10% margin buffer at all times

## Escalation Path

### Level 1: On-Call Engineer (0-5 minutes)
- Execute kill switch procedures
- Assess immediate risk
- Begin recovery process

### Level 2: Trading Lead (5-15 minutes)
- Review recovery plan
- Approve position adjustments
- Authorize trading resumption

### Level 3: Risk Committee (15+ minutes)
- Review if kill switch was appropriate
- Analyze for systemic issues
- Update risk parameters if needed

## Quick Reference Commands

```bash
# Emergency pause
curl -X POST http://localhost:8001/api/v1/execution/pause

# Check status
curl http://localhost:8001/api/v1/execution/status

# View recent alerts
docker logs chiseai-api --tail 100 | grep -i "alert\|kill\|emergency"

# Get risk metrics
curl http://localhost:8001/api/v1/risk/metrics | jq '.'

# Resume trading
curl -X POST http://localhost:8001/api/v1/execution/resume
```

## Related Runbooks

- [Redis Failure Response](redis-failure-response.md) - If Redis issues triggered kill switch
- [Paper Trading Operations](paper-trading-operations.md) - For paper mode verification
- [API Disconnect](api-disconnect.md) - If external factors contributed

## Contact Information

- **On-Call Engineer**: PagerDuty rotation
- **Trading Lead**: #trading-ops Slack channel
- **Risk Committee**: risk@chiseai.slack.com
- **Emergency Hotline**: +1-XXX-XXX-XXXX
