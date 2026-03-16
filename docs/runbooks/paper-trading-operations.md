---
title: Paper Trading Operations Runbook
category: operations
severity: standard
estimated_time_to_resolve: 10-30 minutes
last_updated: 2026-02-17
maintainers: ops-team
story_id: PAPER-004
executable: true
steps:
  - name: "Check all services status"
    command: "docker ps --filter 'name=chiseai' --format '{{.Names}}: {{.Status}}'"
  - name: "Verify paper trading mode"
    command: "curl -s http://localhost:8001/api/v1/execution/mode | jq -r '.mode'"
    verify: "paper"
  - name: "Check data freshness"
    command: "curl -s http://localhost:8001/api/v1/health/data-freshness | jq '.sources | length'"
  - name: "Check kill-switch status"
    command: "./scripts/ops/kill_switch_check.sh"
    verify: "ARMED"
  - name: "Generate daily summary"
    script: "scripts/ops/daily_summary.sh"
    description: "Runs daily summary report for paper trading"
  - name: "Backup paper trading state"
    command: "redis-cli -p 6380 BGSAVE"
---

# Paper Trading Operations Runbook

## Overview

This runbook covers daily operational procedures for the paper trading environment, including health checks, common issue resolution, and monitoring guidelines.

## Prerequisites

Before using this runbook, ensure you have:

- [ ] Docker CLI access and appropriate permissions
- [ ] Redis CLI installed and configured (port 6380)
- [ ] curl command-line tool
- [ ] jq JSON processor installed
- [ ] Access to the ChiseAI API (localhost:8001)
- [ ] Grafana dashboard access for monitoring
- [ ] Scripts directory permissions (./scripts/ops/)

## Daily Operational Checks

### Morning Startup Checklist (9:00 AM)

#### 1. System Health Verification

**Check All Services:**
```bash
# Verify all containers are running
docker ps --filter "name=chiseai" --format "{{.Names}}: {{.Status}}"

# Expected output:
# chiseai-api: Up 12 hours
# chiseai-redis: Up 12 hours
# chiseai-postgres: Up 12 hours
# chise-dashboard: Up 12 hours
```

**Verify Paper Trading Mode:**
```bash
# Check execution mode
curl http://localhost:8001/api/v1/execution/mode

# Expected: {"mode": "paper", "live_trading": false}
```

#### 2. Data Freshness Check

**Market Data:**
```bash
# Check data freshness for all exchanges
curl http://localhost:8001/api/v1/health/data-freshness | jq '.'

# All sources should show: {"age_seconds": < 60}
```

**Redis Sync Status:**
```bash
# Check Redis connectivity
redis-cli -p 6380 PING

# Expected: PONG

# Check key count
redis-cli -p 6380 DBSIZE
```

#### 3. Position and Order Status

**Current Positions:**
```bash
# List all paper positions
curl http://localhost:8001/api/v1/paper/positions | jq '.positions | length'

# Check position values
curl http://localhost:8001/api/v1/paper/positions | jq '.total_notional_value'
```

**Pending Orders:**
```bash
# Check for stuck orders
curl http://localhost:8001/api/v1/paper/orders/pending | jq '.orders | length'

# Should be: 0 (or minimal during active trading)
```

#### 4. Kill-Switch Panel Verification

**Verify Kill-Switch Status:**
```bash
# Quick kill-switch status check
./scripts/ops/kill_switch_check.sh

# Expected: ARMED (green) - ready for trading
```

**Grafana Panel Check:**
- Navigate to: `Grafana > Dashboards > ChiseAI - Paper Trading`
- Locate the **Kill-Switch Status** panel
- Verify indicator shows: **ARMED** (green)
- Check that no alerts are active for kill-switch triggers

### Mid-Day Check (1:00 PM)

#### 1. Performance Metrics

**PnL Summary:**
```bash
# Get daily PnL
curl http://localhost:8001/api/v1/paper/pnl/daily | jq '{realized_pnl: .realized_pnl, unrealized_pnl: .unrealized_pnl, total_trades: .total_trades}'
```

**Risk Metrics:**
```bash
# Current risk exposure
curl http://localhost:8001/api/v1/risk/metrics | jq '{exposure_pct: .exposure_pct, margin_utilization: .margin_utilization.utilization_pct, concentration_risk: .concentration_risk}'
```

#### 2. Alert Review

**Check Active Alerts:**
```bash
# List all active alerts
curl http://localhost:8001/api/v1/alerts/active | jq '.alerts[] | {type: .alert_type, severity: .severity, message: .message}'
```

**Kill-Switch Specific Alerts:**
```bash
# Check for kill-switch related alerts
curl http://localhost:8001/api/v1/alerts/active | jq '.alerts[] | select(.alert_type | contains("kill") or contains("circuit"))'
```

**Review Alert History:**
```bash
# Alerts in last 4 hours
curl "http://localhost:8001/api/v1/alerts/history?hours=4" | jq '.alerts | length'

# Kill-switch alerts in last 24 hours
curl "http://localhost:8001/api/v1/alerts/history?hours=24" | jq '.alerts[] | select(.alert_type | contains("kill")) | {time: .created_at, type: .alert_type, message: .message}'
```

### End-of-Day Checklist (5:00 PM)

#### 1. Daily Summary

**Generate Daily Report:**
```bash
# Run daily summary script
./scripts/ops/daily_summary.sh --mode=paper --date=$(date +%Y-%m-%d)
```

**Key Metrics to Record:**
- Total trades executed
- Win/loss ratio
- Gross PnL
- Max drawdown
- Risk metrics at close

#### 2. Data Backup

**Backup Paper Trading State:**
```bash
# Export positions
curl http://localhost:8001/api/v1/paper/positions > backups/paper_positions_$(date +%Y%m%d).json

# Export order history
curl http://localhost:8001/api/v1/paper/orders/history > backups/paper_orders_$(date +%Y%m%d).json

# Redis backup
redis-cli -p 6380 BGSAVE
```

## Common Issues and Resolutions

### Issue 1: Redis Sync Divergence

**Symptoms:**
- Alert: "PAPER SYNC DIVERGENCE"
- Memory state differs from Redis state
- Position values don't match

**Diagnosis:**
```bash
# Check divergence details
curl http://localhost:8001/api/v1/paper/sync-status | jq '.'
```

**Resolution:**
```bash
# Force resync from Redis
curl -X POST http://localhost:8001/api/v1/paper/sync/force \
  -H "Content-Type: application/json" \
  -d '{"source": "redis", "reason": "divergence_detected"}'

# Verify sync
sleep 5
curl http://localhost:8001/api/v1/paper/sync-status | jq '.divergence_pct'
# Should be: < 1.0
```

### Issue 2: High Validation Failure Rate

**Symptoms:**
- Alert: "VALIDATION FAILURE RATE"
- Orders being rejected
- >10% failure rate in 5-minute window

**Diagnosis:**
```bash
# Get failure breakdown
curl http://localhost:8001/api/v1/orders/validation-failures | jq '.breakdown'

# Common reasons:
# - insufficient_funds
# - price_stale
# - size_too_small
# - market_closed
```

**Resolution by Cause:**

**Insufficient Funds:**
```bash
# Check available balance
curl http://localhost:8001/api/v1/account/balance | jq '.available'

# May need to reset paper balance if depleted
```

**Stale Prices:**
```bash
# Check data freshness
curl http://localhost:8001/api/v1/health/data-freshness

# Restart data feed if stale
./scripts/ops/reconnect_data_source.sh --exchange [EXCHANGE]
```

**Size Too Small:**
- Review minimum order sizes in config
- Adjust strategy parameters

### Issue 3: Paper Trading Latency

**Symptoms:**
- Slow order execution
- Delayed position updates
- High API response times

**Diagnosis:**
```bash
# Check API latency
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8001/api/v1/health

# Check Redis latency
redis-cli -p 6380 --latency-history
```

**Resolution:**
```bash
# Restart paper trading service
docker restart chiseai-api

# Monitor recovery
docker logs chiseai-api --tail 50 -f
```

### Issue 4: Incorrect PnL Calculation

**Symptoms:**
- PnL values seem incorrect
- Unrealized PnL not updating
- Discrepancy with manual calculation

**Diagnosis:**
```bash
# Get detailed PnL breakdown
curl http://localhost:8001/api/v1/paper/pnl/detailed | jq '.'

# Check mark prices
curl http://localhost:8001/api/v1/mark/prices | jq '.[] | select(.symbol == "BTC-USDT")'
```

**Resolution:**
```bash
# Force PnL recalculation
curl -X POST http://localhost:8001/api/v1/paper/pnl/recalculate

# Verify with manual check
```

## Kill-Switch Panel Monitoring

### How to Check Kill-Switch Status from Grafana

The kill-switch panel provides real-time visibility into the emergency stop system status.

#### Step-by-Step: Checking Kill-Switch Status

**1. Navigate to the Dashboard:**
```
Grafana > Dashboards > ChiseAI - Paper Trading
```

**2. Locate the Kill-Switch Panel:**
- Panel Name: **Kill-Switch Status**
- Location: Typically in the top row of the dashboard
- Visual Indicator: Large colored status badge

**3. Interpret the Status:**

| Status | Color | Meaning | Action Required |
|--------|-------|---------|-----------------|
| **ARMED** | 🟢 Green | System ready, trading enabled | None - normal state |
| **TRIGGERED** | 🔴 Red | Kill switch activated, trading halted | Immediate investigation required |
| **DISABLED** | ⚪ Gray | Kill switch manually disabled | Review why disabled, consider re-enabling |

**4. Check Supporting Metrics:**
- Last trigger timestamp
- Positions closed count
- Circuit breaker status
- Consecutive failure count

### Daily Checklist: Kill-Switch Panel

**Morning (9:00 AM):**
- [ ] Navigate to Grafana > Paper Trading Dashboard
- [ ] Verify kill-switch panel shows **ARMED** (green)
- [ ] Check that last trigger timestamp is not recent
- [ ] Verify circuit breaker is closed (green)

**Mid-Day (1:00 PM):**
- [ ] Quick visual check of kill-switch panel
- [ ] Confirm no state changes since morning

**End-of-Day (5:00 PM):**
- [ ] Final verification of ARMED status
- [ ] Document any kill-switch events in daily log

### Kill-Switch Alert Response

**If Panel Shows TRIGGERED (Red):**
1. Immediately check [Kill Switch Trigger Runbook](kill-switch-trigger.md)
2. Do not resume trading until root cause is identified
3. Follow escalation path in emergency procedures

**If Panel Shows DISABLED (Gray):**
1. Check who disabled the kill switch and why
2. Review recent operations log
3. Re-enable if conditions permit:
   ```bash
   curl -X POST http://localhost:8001/api/v1/execution/kill-switch/enable
   ```

### Grafana Panel Reference

```
### Kill-Switch Panel (Grafana > Paper Trading Dashboard)

Panel ID: kill-switch-status
Data Source: InfluxDB
Refresh Rate: 5 seconds

Metrics Displayed:
- kill_switch_state (ARMED=1, TRIGGERED=2, DISABLED=0)
- last_trigger_timestamp
- positions_closed_count
- circuit_breaker_state
- consecutive_failures

Alert Thresholds:
- State = TRIGGERED: Critical alert
- State = DISABLED: Warning alert
- Circuit breaker open: Critical alert
```

## Monitoring Dashboard Guide

### Grafana Dashboards

#### 1. Paper Trading Overview

**URL:** `Grafana > Dashboards > ChiseAI - Paper Trading`

**Key Panels:**
- **PnL Chart:** Realized and unrealized PnL over time
- **Position Table:** Current positions with sizes and values
- **Order Flow:** Orders executed in last hour
- **Risk Gauges:** Exposure, margin, concentration

**Alert Thresholds:**
- PnL Drawdown: >5% (Warning), >10% (Critical)
- Position Count: >20 (Warning)
- Order Failure Rate: >5% (Warning), >10% (Critical)

#### 2. Data Freshness Dashboard

**URL:** `Grafana > Dashboards > ChiseAI - Data Freshness`

**Key Metrics:**
- Last price update (per exchange)
- Order book age
- Trade feed latency

**Healthy Values:**
- All data sources: < 60 seconds
- Warning: 60-180 seconds
- Critical: > 180 seconds

#### 3. System Health Dashboard

**URL:** `Grafana > Dashboards > ChiseAI - System Health`

**Key Metrics:**
- API response times
- Redis memory usage
- Database connections
- Container resource usage

### Redis Monitoring

**Key Commands:**
```bash
# Memory usage
redis-cli -p 6380 INFO memory | grep used_memory_human

# Connected clients
redis-cli -p 6380 INFO clients | grep connected_clients

# Key statistics
redis-cli -p 6380 INFO keyspace

# Slow queries
redis-cli -p 6380 SLOWLOG GET 10
```

## Maintenance Procedures

### Weekly Maintenance

#### 1. Log Rotation

```bash
# Rotate application logs
docker exec chiseai-api logrotate -f /etc/logrotate.d/chiseai

# Clean old logs (>30 days)
find /var/log/chiseai -name "*.log.*" -mtime +30 -delete
```

#### 2. Redis Optimization

```bash
# Check memory fragmentation
redis-cli -p 6380 INFO memory | grep mem_fragmentation_ratio

# If > 1.5, restart Redis
docker restart chiseai-redis
```

#### 3. Database Cleanup

```bash
# Clean old order history (>90 days)
./scripts/ops/cleanup_old_orders.sh --days=90 --mode=paper
```

### Monthly Maintenance

#### 1. Performance Review

- Review win/loss ratios
- Analyze strategy performance
- Check for systematic issues

#### 2. Configuration Review

- Verify risk limits are appropriate
- Review alert thresholds
- Update exchange API credentials if needed

#### 3. Disaster Recovery Test

- Test backup restoration
- Verify failover procedures
- Update runbooks with lessons learned

## Troubleshooting Commands

```bash
# Quick health check
./scripts/ops/health_check.sh

# Check paper trading logs
docker logs chiseai-api --tail 100 | grep -i "paper\|order\|position"

# Redis connectivity test
redis-cli -p 6380 ping && echo "Redis OK" || echo "Redis FAIL"

# API latency test
for i in {1..5}; do curl -s -w "%{time_total}\n" -o /dev/null http://localhost:8001/api/v1/health; done

# Check for errors
docker logs chiseai-api --tail 200 | grep -i "error\|exception\|fail"
```

## Related Documentation

- [Kill Switch Trigger](kill-switch-trigger.md) - Emergency procedures
- [Redis Failure Response](redis-failure-response.md) - Redis-specific issues
- [API Disconnect](api-disconnect.md) - Exchange connectivity issues

## Support Contacts

- **Operations Team**: #ops-support Slack channel
- **Trading Team**: #trading-ops Slack channel
- **On-Call Engineer**: PagerDuty rotation
