---
title: Paper Trading Operations - Enhanced
category: operations
severity: standard
estimated_time_to_resolve: 15-45 minutes
last_updated: 2026-03-11
maintainers: ops-team
story_id: PAPER-GOVERNANCE-001
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
  - name: "Execute governance checkpoint G1"
    script: "scripts/ops/governance_check.sh --gate=G1"
    description: "Environment and permissions validation"
  - name: "Execute governance checkpoint G2"
    script: "scripts/ops/governance_check.sh --gate=G2"
    description: "Strategy configuration validation"
  - name: "Execute governance checkpoint G3"
    script: "scripts/ops/governance_check.sh --gate=G3"
    description: "Data source and connectivity validation"
  - name: "Execute governance checkpoint G4"
    script: "scripts/ops/governance_check.sh --gate=G4"
    description: "Risk parameters and limits validation"
  - name: "Execute governance checkpoint G5"
    script: "scripts/ops/governance_check.sh --gate=G5"
    description: "Trade budgeter and turnover validation"
  - name: "Execute governance checkpoint G6"
    script: "scripts/ops/governance_check.sh --gate=G6"
    description: "Execution readiness validation"
  - name: "Execute governance checkpoint G7"
    script: "scripts/ops/governance_check.sh --gate=G7"
    description: "Monitoring and alerting validation"
  - name: "Execute governance checkpoint G8"
    script: "scripts/ops/governance_check.sh --gate=G8"
    description: "Final authorization and sign-off"
  - name: "Generate daily summary"
    script: "scripts/ops/daily_summary.sh"
    description: "Runs daily summary report for paper trading with governance metrics"
  - name: "Backup paper trading state"
    command: "redis-cli -p 6380 BGSAVE"
---

# Paper Trading Operations - Enhanced

## Overview

This enhanced runbook provides comprehensive operational procedures for the paper trading environment with integrated governance checkpoint automation, enhanced monitoring capabilities, and structured risk management procedures. It supersedes the standard paper trading runbook with additional validation gates, automated compliance checks, and detailed incident response protocols.

### Key Enhancements

| Feature | Standard Runbook | Enhanced Runbook |
|---------|-----------------|------------------|
| Governance Checkpoints | Manual verification | Automated G1-G8 gate validation |
| Monitoring | Basic health checks | Integrated Grafana, Redis, InfluxDB analytics |
| Risk Management | Static limits | Dynamic budgeter with real-time enforcement |
| Rollback Procedures | Manual intervention | Automated checkpoint-based recovery |
| Compliance | Basic logging | Comprehensive audit trails and sign-offs |

### Purpose and Scope

This runbook covers:
- Pre-flight checklist with automated governance validation
- Real-time monitoring of G1-G8 gates during trading sessions
- Enhanced risk management with trade budgeter integration
- Structured incident response with predefined escalation paths
- Automated rollback and recovery procedures
- Post-trade analysis with compliance reporting
- Integration with checkpoint module for state management

### Target Audience

- Operations team members responsible for paper trading oversight
- Risk managers monitoring trading limits and compliance
- Strategy developers validating backtest-to-paper carryover
- Incident response teams handling trading halts and recoveries

## Pre-Flight Checklist

### Comprehensive Startup Validation

Before commencing any paper trading session, all items in this checklist must pass. The enhanced runbook introduces automated validation through the G1-G8 governance gates, ensuring systematic verification of environment, configuration, data, risk, and operational readiness.

#### Phase 1: Infrastructure Verification (G1 - Environment Gate)

**1.1 Container Health Check**

Verify all required services are running and healthy:

```bash
# Check all ChiseAI containers
docker ps --filter "name=chiseai" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Expected output should show all containers as "Up"
# - chiseai-api: Up X hours, port 8001
# - chiseai-redis: Up X hours, port 6380
# - chiseai-postgres: Up X hours, port 5434
# - chiseai-influxdb: Up X hours, port 18087
# - chiseai-qdrant: Up X hours, port 6334
# - chiseai-grafana: Up X hours, port 3001
```

**1.2 Network Connectivity Validation**

```bash
# Verify inter-container connectivity on chiseai network
docker network inspect chiseai --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{println}}{{end}}'

# Test API responsiveness
for i in {1..5}; do
  curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://localhost:8001/api/v1/health
done

# Expected: All return 200 status codes with < 0.5s response time
```

**1.3 Resource Utilization Check**

```bash
# Check system resources
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Verify disk space for logging and data persistence
df -h /var/lib/docker /var/log/chiseai

# Alert thresholds:
# - CPU: > 80% sustained for > 5 minutes
# - Memory: > 85% sustained
# - Disk: < 20% free space
```

**1.4 G1 Gate Validation Script**

```bash
# Execute automated G1 validation
./scripts/ops/governance_check.sh --gate=G1 --verbose

# Expected output:
# G1 - Environment Gate: PASSED
# - Container health: ✓ 6/6 running
# - Network connectivity: ✓ All services reachable
# - Resource utilization: ✓ Within limits
# - Execution mode: ✓ Paper trading confirmed
```

#### Phase 2: Configuration Validation (G2 - Strategy Gate)

**2.1 Trading Mode Verification**

```bash
# Confirm paper trading mode is active
curl -s http://localhost:8001/api/v1/execution/mode | jq '.'

# Expected response:
# {
#   "mode": "paper",
#   "live_trading": false,
#   "execution_engine": "paper_simulator",
#   "risk_engine": "enabled"
# }
```

**2.2 Strategy Configuration Audit**

```bash
# List all configured strategies
curl -s http://localhost:8001/api/v1/strategies/config | jq '.strategies[] | {name: .name, version: .version, status: .status}'

# Verify strategy parameters match approved configuration
curl -s http://localhost:8001/api/v1/strategies/validate | jq '.validation_results'

# Check for any unapproved strategy modifications
./scripts/ops/config_audit.sh --mode=paper --compare-approved
```

**2.3 API Credentials Validation**

```bash
# Verify exchange API connectivity (paper credentials)
curl -s http://localhost:8001/api/v1/exchanges/health | jq '.exchanges[] | {name: .name, connected: .connected, mode: .mode}'

# All exchanges should show: connected=true, mode=paper
```

**2.4 G2 Gate Validation Script**

```bash
# Execute automated G2 validation
./scripts/ops/governance_check.sh --gate=G2 --verbose

# Expected output:
# G2 - Strategy Gate: PASSED
# - Trading mode: ✓ Paper trading confirmed
# - Strategy configs: ✓ All validated
# - API credentials: ✓ All exchanges connected
# - Parameter drift: ✓ No unauthorized changes
```

#### Phase 3: Data Source Validation (G3 - Data Gate)

**3.1 Market Data Freshness**

```bash
# Check data freshness across all sources
curl -s http://localhost:8001/api/v1/health/data-freshness | jq '.'

# Healthy thresholds per source:
# - Market data: < 60 seconds
# - Order book: < 5 seconds
# - Trade feed: < 1 second
# - Funding rates: < 300 seconds
```

**3.2 Data Source Connectivity**

```bash
# Verify all data feeds are active
for source in binance coinbase kraken; do
  status=$(curl -s "http://localhost:8001/api/v1/health/data-source/${source}" | jq -r '.status')
  echo "${source}: ${status}"
done

# Expected: All sources return "healthy"
```

**3.3 Historical Data Availability**

```bash
# Verify required historical data is loaded
curl -s http://localhost:8001/api/v1/data/availability | jq '.symbols[] | {symbol: .symbol, days_available: .days_available}'

# Minimum requirements:
# - 30 days of 1-minute OHLCV data
# - 7 days of tick-level trade data
# - Full order book snapshots for last 24 hours
```

**3.4 G3 Gate Validation Script**

```bash
# Execute automated G3 validation
./scripts/ops/governance_check.sh --gate=G3 --verbose

# Expected output:
# G3 - Data Gate: PASSED
# - Market data freshness: ✓ All sources < 60s
# - Data connectivity: ✓ All feeds active
# - Historical data: ✓ Minimum thresholds met
# - Data quality: ✓ No anomalies detected
```

#### Phase 4: Risk Parameters Validation (G4 - Risk Gate)

**4.1 Position Limits Verification**

```bash
# Check current position limits configuration
curl -s http://localhost:8001/api/v1/risk/limits | jq '.'

# Verify key limits:
# - Max position size per symbol
# - Max total exposure
# - Max leverage per position
# - Max open orders per symbol
```

**4.2 Risk Engine Status**

```bash
# Verify risk engine is operational
curl -s http://localhost:8001/api/v1/risk/status | jq '.'

# Expected:
# - status: "active"
# - pre_trade_checks: "enabled"
# - post_trade_checks: "enabled"
# - kill_switch: "armed"
```

**4.3 Circuit Breaker Configuration**

```bash
# Check circuit breaker thresholds
curl -s http://localhost:8001/api/v1/risk/circuit-breakers | jq '.'

# Key thresholds to verify:
# - Daily loss limit: 5% of capital
# - Max drawdown: 10% from peak
# - Volatility spike: 3x average
# - Order failure rate: > 10%
```

**4.4 G4 Gate Validation Script**

```bash
# Execute automated G4 validation
./scripts/ops/governance_check.sh --gate=G4 --verbose

# Expected output:
# G4 - Risk Gate: PASSED
# - Position limits: ✓ All configured
# - Risk engine: ✓ Active and operational
# - Circuit breakers: ✓ Armed with valid thresholds
# - Kill switch: ✓ ARMED and tested
```

#### Phase 5: Trade Budgeter Validation (G5 - Budget Gate)

**5.1 Daily Token Allocation**

```bash
# Check trade budgeter status
curl -s http://localhost:8001/api/v1/risk/budgeter/status | jq '.'

# Expected configuration:
# - daily_tokens: 20
# - tokens_used: 0 (or current day's count)
# - tokens_remaining: 20
# - reset_time: "00:00 UTC"
```

**5.2 Turnover Metrics Baseline**

```bash
# Get current turnover metrics
curl -s http://localhost:8001/api/v1/risk/turnover/metrics | jq '.'

# Verify against ceilings:
# - avg_trades_per_day: ≤ 20
# - p95_trades_per_day: ≤ 30
# - max_trades_per_day: ≤ 45
```

**5.3 Budget Enforcement Check**

```bash
# Verify budgeter enforcement is active
curl -s http://localhost:8001/api/v1/risk/budgeter/config | jq '.enforcement_enabled'

# Expected: true
```

**5.4 G5 Gate Validation Script**

```bash
# Execute automated G5 validation
./scripts/ops/governance_check.sh --gate=G5 --verbose

# Expected output:
# G5 - Budget Gate: PASSED
# - Daily tokens: ✓ 20 allocated
# - Budgeter state: ✓ Active
# - Turnover tracking: ✓ Enabled
# - Enforcement: ✓ Strict mode
```

#### Phase 6: Execution Readiness (G6 - Execution Gate)

**6.1 Order Management System Status**

```bash
# Check OMS operational status
curl -s http://localhost:8001/api/v1/execution/oms-status | jq '.'

# Verify:
# - Order submission: enabled
# - Order cancellation: enabled
# - Order modification: enabled
# - Fill processing: enabled
```

**6.2 Pending Orders Check**

```bash
# Clear any stale pending orders from previous session
curl -s http://localhost:8001/api/v1/paper/orders/pending | jq '.orders | length'

# Expected: 0 (or minimal if resuming mid-session)

# If stale orders exist:
curl -X POST http://localhost:8001/api/v1/paper/orders/cancel-all \
  -H "Content-Type: application/json" \
  -d '{"reason": "pre_flight_cleanup"}'
```

**6.3 Execution Engine Configuration**

```bash
# Verify execution parameters
curl -s http://localhost:8001/api/v1/execution/config | jq '.'

# Key settings:
# - Slippage model: enabled
# - Fill simulation: realistic
# - Latency simulation: enabled (for paper)
# - Market impact: modeled
```

**6.4 G6 Gate Validation Script**

```bash
# Execute automated G6 validation
./scripts/ops/governance_check.sh --gate=G6 --verbose

# Expected output:
# G6 - Execution Gate: PASSED
# - OMS status: ✓ Operational
# - Pending orders: ✓ Cleared
# - Execution config: ✓ Valid
# - Simulation mode: ✓ Paper realistic
```

#### Phase 7: Monitoring and Alerting Validation (G7 - Monitoring Gate)

**7.1 Grafana Dashboard Health**

```bash
# Verify Grafana is accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/api/health

# Expected: 200

# Check dashboard availability
curl -s http://localhost:3001/api/search?query=paper | jq '.[].title'

# Expected dashboards:
# - ChiseAI - Paper Trading
# - ChiseAI - Risk Metrics
# - ChiseAI - Data Freshness
```

**7.2 Alert Manager Status**

```bash
# Check alert routing configuration
curl -s http://localhost:8001/api/v1/alerts/config | jq '.'

# Verify channels:
# - Slack notifications: enabled
# - PagerDuty integration: enabled
# - Email alerts: configured
# - Webhook endpoints: responsive
```

**7.3 InfluxDB Metrics Pipeline**

```bash
# Verify metrics are flowing to InfluxDB
curl -s http://localhost:18087/ping

# Expected: 204 No Content (InfluxDB health check)

# Check recent metric writes
curl -s -G "http://localhost:18087/query" \
  --data-urlencode "db=chiseai" \
  --data-urlencode "q=SELECT COUNT(*) FROM trades WHERE time > now() - 1h"
```

**7.4 G7 Gate Validation Script**

```bash
# Execute automated G7 validation
./scripts/ops/governance_check.sh --gate=G7 --verbose

# Expected output:
# G7 - Monitoring Gate: PASSED
# - Grafana: ✓ Accessible
# - Alert manager: ✓ Configured
# - InfluxDB pipeline: ✓ Active
# - Notification channels: ✓ Tested
```

#### Phase 8: Authorization and Sign-off (G8 - Authorization Gate)

**8.1 Pre-Flight Sign-off Checklist**

All items must be verified and signed off before trading begins:

| Item | Status | Sign-off |
|------|--------|----------|
| G1 - Environment Gate | ☐ PASSED ☐ FAILED | ___________ |
| G2 - Strategy Gate | ☐ PASSED ☐ FAILED | ___________ |
| G3 - Data Gate | ☐ PASSED ☐ FAILED | ___________ |
| G4 - Risk Gate | ☐ PASSED ☐ FAILED | ___________ |
| G5 - Budget Gate | ☐ PASSED ☐ FAILED | ___________ |
| G6 - Execution Gate | ☐ PASSED ☐ FAILED | ___________ |
| G7 - Monitoring Gate | ☐ PASSED ☐ FAILED | ___________ |
| Kill-Switch Status | ☐ ARMED | ___________ |
| Emergency Contacts | ☐ VERIFIED | ___________ |

**8.2 Authorization Command**

```bash
# Execute G8 authorization check
./scripts/ops/governance_check.sh --gate=G8 --sign-off-required

# This will:
# - Verify all G1-G7 gates passed
# - Record authorization timestamp
# - Log operator identity
# - Enable trading mode
```

**8.3 G8 Gate Validation Script**

```bash
# Execute automated G8 validation
./scripts/ops/governance_check.sh --gate=G8 --verbose

# Expected output:
# G8 - Authorization Gate: PASSED
# - G1-G7 status: ✓ All gates passed
# - Sign-off recorded: ✓ [timestamp]
# - Operator: ✓ [operator_id]
# - Trading: ✓ ENABLED
```

## Governance Checkpoint Procedures

### Automated Governance Checkpoint System

The governance checkpoint system provides automated validation at critical stages of the paper trading lifecycle. Each gate (G1-G8) represents a specific domain of validation, with automated scripts performing comprehensive checks and recording results for audit purposes.

### Checkpoint Module Integration

The checkpoint module provides state management and persistence for governance checkpoints:

```python
# Checkpoint module API usage
from chiseai.checkpoint import CheckpointManager

# Initialize checkpoint manager
cpm = CheckpointManager(
    environment="paper",
    story_id="PAPER-GOVERNANCE-001"
)

# Create pre-flight checkpoint
checkpoint = cpm.create_checkpoint(
    checkpoint_type="pre_flight",
    gates=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]
)

# Validate individual gate
result = cpm.validate_gate(
    gate_id="G1",
    checks=["containers", "network", "resources"]
)

# Persist checkpoint state
cpm.save_checkpoint(checkpoint)
```

### G1-G8 Gate Explanations

#### G1: Environment Gate

**Purpose:** Validate infrastructure and environment readiness

**Validation Checks:**
- Container health and status
- Network connectivity between services
- Resource utilization (CPU, memory, disk)
- Execution mode confirmation (paper vs live)
- Service dependency verification

**Pass Criteria:**
- All required containers running and healthy
- Network latency < 100ms between critical services
- Resource utilization < 80% for all metrics
- Paper trading mode explicitly confirmed

**Failure Actions:**
- Halt trading initialization
- Alert operations team
- Log detailed failure diagnostics
- Provide specific remediation steps

**Checkpoint Integration:**
```bash
# Checkpoint state storage
redis-cli -p 6380 HSET "checkpoint:G1:$(date +%s)" \
  status "passed" \
  timestamp "$(date -Iseconds)" \
  operator "$OPERATOR_ID" \
  checks_passed "6" \
  checks_total "6"
```

#### G2: Strategy Gate

**Purpose:** Validate strategy configurations and parameters

**Validation Checks:**
- Trading mode verification (paper only)
- Strategy configuration against approved baseline
- API credential validity and permissions
- Parameter drift detection
- Version compatibility

**Pass Criteria:**
- Paper trading mode explicitly set
- All strategies match approved configurations
- All exchange APIs connected and responding
- No unauthorized parameter changes detected

**Failure Actions:**
- Block strategy deployment
- Quarantine modified strategies
- Require explicit re-approval for changes
- Audit trail for configuration drift

**Configuration Audit Trail:**
```bash
# Generate configuration diff
./scripts/ops/config_audit.sh --mode=paper --generate-diff > \
  logs/config_diff_$(date +%Y%m%d_%H%M%S).json

# Store in checkpoint
curl -X POST http://localhost:8001/api/v1/checkpoint/config \
  -H "Content-Type: application/json" \
  -d @logs/config_diff_$(date +%Y%m%d_%H%M%S).json
```

#### G3: Data Gate

**Purpose:** Validate data sources and market data quality

**Validation Checks:**
- Market data freshness (< 60 seconds)
- Order book depth and quality
- Trade feed continuity
- Historical data completeness
- Data source connectivity

**Pass Criteria:**
- All data sources reporting within freshness thresholds
- No gaps in trade feed for last hour
- Minimum 30 days historical data available
- All exchange feeds responsive

**Failure Actions:**
- Degrade trading to reduced symbol set
- Alert data engineering team
- Implement fallback data sources
- Log data quality issues

**Data Quality Metrics:**
```bash
# Automated data quality report
curl -s http://localhost:8001/api/v1/data/quality-report | jq '.'

# Expected metrics:
# - freshness_score: 0.0-1.0
# - completeness_score: 0.0-1.0
# - accuracy_score: 0.0-1.0
# - overall_quality: "excellent" | "good" | "fair" | "poor"
```

#### G4: Risk Gate

**Purpose:** Validate risk management systems and limits

**Validation Checks:**
- Position limit configurations
- Risk engine operational status
- Circuit breaker thresholds
- Kill-switch armed status
- Exposure limit validation

**Pass Criteria:**
- All position limits configured and active
- Risk engine status: "active"
- Circuit breakers armed with valid thresholds
- Kill-switch: ARMED
- No pending risk alerts

**Failure Actions:**
- Do not proceed with trading
- Escalate to risk management team
- Require manual risk system verification
- Document risk system anomalies

**Risk System Health Dashboard:**
```bash
# Comprehensive risk health check
curl -s http://localhost:8001/api/v1/risk/health | jq '.'

# Response includes:
# - engine_status: "active" | "degraded" | "inactive"
# - limit_compliance: "compliant" | "warning" | "breach"
# - kill_switch_state: "ARMED" | "TRIGGERED" | "DISABLED"
# - active_alerts: [...]
```

#### G5: Budget Gate

**Purpose:** Validate trade budgeter and turnover constraints

**Validation Checks:**
- Daily token allocation (20 tokens)
- Budgeter enforcement status
- Turnover metrics baseline
- Historical turnover patterns
- Token consumption rate

**Pass Criteria:**
- 20 daily tokens allocated
- Budgeter enforcement enabled
- Turnover metrics within ceilings:
  - avg ≤ 20 trades/day
  - p95 ≤ 30 trades/day
  - max ≤ 45 trades/day

**Failure Actions:**
- If budget exhausted: Block new entries, allow exits
- If turnover exceeding: Alert and review strategy
- Document budget consumption patterns
- Adjust token allocation if needed (requires approval)

**Trade Budgeter Monitoring:**
```bash
# Real-time budgeter status
curl -s http://localhost:8001/api/v1/risk/budgeter/status | jq '.'

# Response includes:
# {
#   "daily_tokens": 20,
#   "tokens_used": 5,
#   "tokens_remaining": 15,
#   "reset_time": "00:00:00Z",
#   "enforcement": "strict",
#   "action_on_exhaustion": "block_entries_allow_exits"
# }
```

#### G6: Execution Gate

**Purpose:** Validate order management and execution readiness

**Validation Checks:**
- OMS operational status
- Pending order clearance
- Execution engine configuration
- Order validation pipeline
- Fill processing capability

**Pass Criteria:**
- OMS status: "operational"
- No stale pending orders
- Execution config validated
- Order validation pipeline active
- Fill processing enabled

**Failure Actions:**
- Clear stale orders before proceeding
- Restart OMS if degraded
- Validate execution parameters
- Test order submission/cancellation

**Execution System Validation:**
```bash
# Test order lifecycle
curl -X POST http://localhost:8001/api/v1/paper/orders/test \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDT",
    "side": "buy",
    "quantity": 0.001,
    "order_type": "limit",
    "price": 50000
  }'

# Verify test order processed and canceled
curl -s http://localhost:8001/api/v1/paper/orders/test-status | jq '.'
```

#### G7: Monitoring Gate

**Purpose:** Validate monitoring, alerting, and observability systems

**Validation Checks:**
- Grafana dashboard accessibility
- Alert manager configuration
- InfluxDB metrics pipeline
- Notification channel responsiveness
- Log aggregation status

**Pass Criteria:**
- Grafana responding (HTTP 200)
- All alert channels configured
- InfluxDB receiving metrics
- Test alert successfully delivered
- Log aggregation active

**Failure Actions:**
- Fix monitoring gaps before trading
- Verify alert routing
- Test notification channels
- Document monitoring limitations

**Monitoring System Check:**
```bash
# Comprehensive monitoring validation
./scripts/ops/monitoring_check.sh --verbose

# Expected output:
# Grafana: ✓ HTTP 200 (15ms)
# AlertManager: ✓ Configured (12 rules)
# InfluxDB: ✓ Receiving metrics (1,247 series)
# Slack: ✓ Test notification delivered
# PagerDuty: ✓ Integration verified
```

#### G8: Authorization Gate

**Purpose:** Final authorization and sign-off before trading commences

**Validation Checks:**
- All G1-G7 gates passed
- Operator sign-off recorded
- Emergency contacts verified
- Trading authorization granted
- Audit trail initiated

**Pass Criteria:**
- G1-G7: All PASSED
- Operator identity verified
- Sign-off timestamp recorded
- Emergency procedures acknowledged

**Failure Actions:**
- Do not enable trading
- Require re-validation of failed gates
- Escalate to senior operations
- Document authorization denial

**Authorization Recording:**
```bash
# Record authorization in checkpoint system
redis-cli -p 6380 HSET "checkpoint:authorization:$(date +%Y%m%d)" \
  operator "$OPERATOR_ID" \
  timestamp "$(date -Iseconds)" \
  gates_passed "G1,G2,G3,G4,G5,G6,G7" \
  signature "$(echo -n "$OPERATOR_ID:$(date +%s)" | sha256sum | cut -d' ' -f1)"

# Enable trading
curl -X POST http://localhost:8001/api/v1/execution/enable \
  -H "Content-Type: application/json" \
  -d '{"authorized_by": "'"$OPERATOR_ID"'", "gates": "all"}'
```

### Checkpoint State Persistence

All checkpoint states are persisted to Redis for durability and audit:

```bash
# View today's checkpoints
redis-cli -p 6380 KEYS "checkpoint:*:$(date +%Y%m%d)*"

# Get checkpoint details
redis-cli -p 6380 HGETALL "checkpoint:G1:$(date +%s)"

# Checkpoint retention: 90 days
# Automated cleanup runs daily at 02:00 UTC
```

## Enhanced Monitoring

### Grafana Dashboard Integration

The enhanced monitoring system provides real-time visibility through integrated Grafana dashboards with customized panels for paper trading operations.

#### Primary Dashboard: ChiseAI - Paper Trading Enhanced

**URL:** `http://localhost:3001/d/chiseai-paper-enhanced`

**Panel Groups:**

1. **Governance Gates Status**
   - G1-G8 gate status indicators
   - Last validation timestamps
   - Gate failure alerts
   - Checkpoint state visualization

2. **Trade Budgeter Panel**
   - Daily token consumption gauge
   - Remaining tokens indicator
   - Token usage rate chart
   - Budget exhaustion alert

3. **Turnover Metrics**
   - Trades/day time series
   - Avg/p95/max turnover gauges
   - Ceiling violation alerts
   - Historical turnover comparison

4. **PnL and Performance**
   - Realized vs unrealized PnL
   - Daily performance chart
   - Win/loss ratio
   - Drawdown visualization

5. **Risk Metrics**
   - Exposure by symbol
   - Margin utilization gauge
   - Concentration risk heatmap
   - Kill-switch status indicator

**Dashboard Configuration:**
```json
{
  "dashboard": {
    "title": "ChiseAI - Paper Trading Enhanced",
    "tags": ["paper", "trading", "governance"],
    "timezone": "UTC",
    "refresh": "5s",
    "panels": [
      {
        "title": "Governance Gates",
        "type": "stat",
        "targets": [
          {
            "query": "SELECT last(\"status\") FROM \"governance_gates\" WHERE \"environment\" = 'paper'"
          }
        ]
      }
    ]
  }
}
```

### Redis Monitoring

Redis serves as the primary state store for paper trading operations. Enhanced monitoring tracks key metrics:

#### Key Metrics to Monitor

```bash
# Real-time Redis monitoring dashboard
watch -n 5 'redis-cli -p 6380 INFO stats | grep -E "keyspace_hits|keyspace_misses|total_commands_processed"'

# Memory usage trends
redis-cli -p 6380 INFO memory | grep -E "used_memory_human|used_memory_peak_human|mem_fragmentation_ratio"

# Client connections
redis-cli -p 6380 INFO clients | grep -E "connected_clients|blocked_clients|tracking_clients"
```

#### Critical Redis Alerts

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Memory Usage | > 70% | > 85% | Scale or restart |
| Fragmentation Ratio | > 1.3 | > 1.5 | Memory compaction |
| Connected Clients | > 80 | > 100 | Connection pool review |
| Key Evictions | > 100/min | > 500/min | Memory pressure |
| Command Latency | > 10ms | > 50ms | Performance investigation |

#### Redis Checkpoint Monitoring

```bash
# Monitor checkpoint writes
redis-cli -p 6380 MONITOR | grep -E "(HSET|checkpoint)"

# Checkpoint storage statistics
redis-cli -p 6380 EVAL "
  local keys = redis.call('keys', 'checkpoint:*')
  local total = 0
  for _,key in ipairs(keys) do
    total = total + redis.call('hlen', key)
  end
  return {#keys, total}
" 0
```

### InfluxDB Metrics Pipeline

InfluxDB provides time-series storage for operational metrics with enhanced retention policies and continuous queries.

#### Metrics Schema

```sql
-- Governance metrics
CREATE MEASUREMENT governance_gates (
  gate_id STRING,
  status STRING,  -- "passed", "failed", "pending"
  operator_id STRING,
  validation_time FLOAT
)

-- Trade budgeter metrics
CREATE MEASUREMENT trade_budgeter (
  tokens_used INTEGER,
  tokens_remaining INTEGER,
  daily_allocation INTEGER,
  reset_time TIMESTAMP
)

-- Turnover metrics
CREATE MEASUREMENT turnover (
  trades_count INTEGER,
  avg_per_day FLOAT,
  p95_per_day FLOAT,
  max_per_day FLOAT,
  ceiling_violation BOOLEAN
)
```

#### Continuous Queries

```sql
-- Hourly governance summary
CREATE CONTINUOUS QUERY cq_governance_hourly
ON chiseai
BEGIN
  SELECT count("status") AS gate_checks,
         sum(case when "status" = 'passed' then 1 else 0 end) AS passed_count
  INTO governance_summary
  FROM governance_gates
  GROUP BY time(1h), gate_id
END

-- Daily turnover aggregation
CREATE CONTINUOUS QUERY cq_turnover_daily
ON chiseai
BEGIN
  SELECT mean("trades_count") AS avg_trades,
         percentile("trades_count", 95) AS p95_trades,
         max("trades_count") AS max_trades
  INTO turnover_daily
  FROM turnover
  GROUP BY time(1d)
END
```

#### InfluxDB Query Examples

```bash
# Query governance gate history
curl -G "http://localhost:18087/query" \
  --data-urlencode "db=chiseai" \
  --data-urlencode "q=SELECT * FROM governance_gates WHERE time > now() - 24h"

# Query budget consumption trend
curl -G "http://localhost:18087/query" \
  --data-urlencode "db=chiseai" \
  --data-urlencode "q=SELECT derivative(mean(tokens_used)) FROM trade_budgeter WHERE time > now() - 6h GROUP BY time(1h)"
```

### Real-Time Alerting

Enhanced alerting with severity-based routing and automated response actions.

#### Alert Severity Levels

| Level | Response Time | Routing | Auto-Action |
|-------|---------------|---------|-------------|
| P0 - Critical | Immediate | PagerDuty + Slack + SMS | Kill-switch trigger |
| P1 - High | 15 minutes | PagerDuty + Slack | Trading pause |
| P2 - Medium | 1 hour | Slack + Email | Alert only |
| P3 - Low | 4 hours | Email digest | Log only |

#### Governance-Specific Alerts

```yaml
# Alert: Gate Failure
- alert: GovernanceGateFailure
  expr: governance_gates_status{status="failed"} > 0
  for: 1m
  labels:
    severity: P1
  annotations:
    summary: "Governance gate {{ $labels.gate_id }} failed"
    description: "Gate {{ $labels.gate_id }} failed validation"
    runbook_url: "docs/runbooks/paper-trading-operations-enhanced.md"

# Alert: Budget Exhaustion
- alert: TradeBudgetExhausted
  expr: trade_budgeter_tokens_remaining == 0
  for: 0s
  labels:
    severity: P1
  annotations:
    summary: "Trade budget exhausted"
    description: "All 20 daily tokens consumed"

# Alert: Turnover Ceiling Breach
- alert: TurnoverCeilingViolation
  expr: turnover_max_per_day > 45 or turnover_p95_per_day > 30
  for: 5m
  labels:
    severity: P2
  annotations:
    summary: "Turnover ceiling exceeded"
    description: "Turnover metrics exceeding configured ceilings"
```

## Automated Validation Gates (G1-G8)

### Gate Execution Automation

The G1-G8 gates are executed automatically through a scheduled validation system with configurable intervals and failure handling.

#### Automation Schedule

| Gate | Frequency | Execution Mode | Failure Action |
|------|-----------|----------------|----------------|
| G1 | Every 5 minutes | Automated | Alert + Log |
| G2 | Every 15 minutes | Automated | Alert + Log |
| G3 | Every 1 minute | Automated | Alert + Degrade |
| G4 | Every 5 minutes | Automated | Alert + Log |
| G5 | Every 1 minute | Automated | Alert + Block Entries |
| G6 | On order submission | Real-time | Reject Order |
| G7 | Every 5 minutes | Automated | Alert + Log |
| G8 | Pre-trading only | Manual | Block Trading |

#### Automated Gate Execution Script

```bash
#!/bin/bash
# /scripts/ops/governance_check.sh

GATE=$1
VERBOSE=${2:-""}

# Load checkpoint module integration
source /scripts/ops/checkpoint_lib.sh

# Execute gate-specific checks
case $GATE in
  G1)
    check_containers
    check_network
    check_resources
    check_execution_mode
    ;;
  G2)
    check_trading_mode
    check_strategy_configs
    check_api_credentials
    check_parameter_drift
    ;;
  G3)
    check_data_freshness
    check_data_connectivity
    check_historical_data
    ;;
  G4)
    check_position_limits
    check_risk_engine
    check_circuit_breakers
    check_kill_switch
    ;;
  G5)
    check_daily_tokens
    check_budgeter_enforcement
    check_turnover_metrics
    ;;
  G6)
    check_oms_status
    check_pending_orders
    check_execution_config
    ;;
  G7)
    check_grafana
    check_alert_manager
    check_influxdb
    ;;
  G8)
    verify_all_gates_passed
    record_operator_signoff
    enable_trading
    ;;
esac

# Record checkpoint
record_gate_checkpoint $GATE $RESULT

exit $EXIT_CODE
```

#### Gate Validation API

```python
# FastAPI endpoint for gate validation
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class GateValidationRequest(BaseModel):
    gate_id: str
    operator_id: str
    force: bool = False

class GateValidationResponse(BaseModel):
    gate_id: str
    status: str  # "passed", "failed", "warning"
    checks: list
    timestamp: str
    operator: str

@app.post("/api/v1/governance/validate-gate")
async def validate_gate(request: GateValidationRequest) -> GateValidationResponse:
    validator = GateValidator(request.gate_id)
    result = await validator.execute()
    
    # Persist to checkpoint
    checkpoint.record(result)
    
    return GateValidationResponse(
        gate_id=request.gate_id,
        status=result.status,
        checks=result.checks,
        timestamp=datetime.utcnow().isoformat(),
        operator=request.operator_id
    )
```

### Gate Dependency Graph

```
G8 (Authorization)
    ↓ (requires all below)
G1 (Environment) ←→ G2 (Strategy) ←→ G3 (Data)
    ↓                    ↓               ↓
    └────────────────→ G4 (Risk) ←──────┘
                           ↓
                    G5 (Budget) ←→ G6 (Execution)
                           ↓
                       G7 (Monitoring)
```

**Dependency Rules:**
- G8 requires all G1-G7 to pass
- G4 depends on G1, G2, G3 (infrastructure must be ready)
- G5 and G6 can run in parallel after G4
- G7 monitors all other gates

### Gate Failure Recovery

#### Recovery Procedures by Gate

**G1 Failure (Infrastructure):**
```bash
# Automated recovery sequence
1. Restart failed containers: docker restart <container>
2. Verify network connectivity: ping <service>
3. Clear resource pressure if needed
4. Re-run G1 validation
5. If still failing: Escalate to infrastructure team
```

**G2 Failure (Strategy):**
```bash
# Manual recovery required
1. Review configuration drift report
2. Quarantine modified strategies
3. Require explicit re-approval
4. Reset to approved baseline
5. Document changes in audit log
```

**G3 Failure (Data):**
```bash
# Semi-automated recovery
1. Switch to backup data sources
2. Reduce trading symbol set
3. Alert data engineering
4. Continue with degraded service
5. Full recovery when data restored
```

**G4 Failure (Risk):**
```bash
# Immediate halt required
1. Halt all trading immediately
2. Do not resume until risk system verified
3. Escalate to risk management
4. Manual verification required
5. Full audit of risk events
```

**G5 Failure (Budget):**
```bash
# Automated response
1. Block new entry orders
2. Allow exit orders to continue
3. Alert strategy team
4. Review token consumption pattern
5. Adjust strategy parameters
```

**G6 Failure (Execution):**
```bash
# Service restart
1. Clear pending orders
2. Restart OMS service
3. Verify order validation pipeline
4. Test with small orders
5. Gradual service restoration
```

**G7 Failure (Monitoring):**
```bash
# Continue with caution
1. Trading can continue
2. Increase manual monitoring
3. Fix monitoring gaps
4. Alert operations team
5. Document monitoring limitations
```

**G8 Failure (Authorization):**
```bash
# Block trading
1. Do not enable trading
2. Re-validate failed gates
3. Require senior approval
4. Document denial reason
5. Schedule follow-up review
```

## Risk Management Procedures

### Enhanced Risk Framework

The enhanced risk management framework integrates multiple layers of protection with automated enforcement and real-time monitoring.

#### Risk Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Pre-Trade Risk Checks (G4, G5 gates)              │
│ - Position limit validation                                 │
│ - Trade budgeter enforcement                                │
│ - Symbol eligibility checks                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Real-Time Risk Monitoring (Continuous)            │
│ - Exposure tracking                                         │
│ - Margin utilization monitoring                             │
│ - Concentration risk calculation                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Circuit Breakers (Automated triggers)             │
│ - Daily loss limits                                         │
│ - Drawdown thresholds                                       │
│ - Volatility spikes                                         │
│ - Order failure rates                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Kill Switch (Emergency stop)                      │
│ - Manual activation                                         │
│ - Automatic activation on critical events                   │
│ - Coordinated position closure                              │
└─────────────────────────────────────────────────────────────┘
```

#### Pre-Trade Risk Validation

Every order undergoes multi-layer validation before submission:

```python
# Risk validation pipeline
class RiskValidator:
    def validate_order(self, order: Order) -> ValidationResult:
        checks = [
            self.check_position_limits(order),
            self.check_trade_budget(order),
            self.check_symbol_eligibility(order),
            self.check_market_conditions(order),
            self.check_concentration_risk(order)
        ]
        
        failed_checks = [c for c in checks if not c.passed]
        
        if failed_checks:
            return ValidationResult(
                approved=False,
                rejections=failed_checks,
                checkpoint_id=self.record_checkpoint(order, checks)
            )
        
        return ValidationResult(approved=True)
```

**Position Limit Checks:**
- Maximum position size per symbol
- Maximum total exposure across all symbols
- Maximum leverage per position
- Maximum number of open orders per symbol

**Trade Budgeter Checks:**
- Verify tokens remaining > 0
- Check if order would exceed turnover ceilings
- Calculate projected token consumption
- Enforce daily budget allocation

#### Real-Time Risk Monitoring

Continuous monitoring of risk metrics with automated alerting:

```bash
# Real-time risk metrics stream
curl -s http://localhost:8001/api/v1/risk/metrics/stream | jq '.'

# Response includes:
# {
#   "timestamp": "2026-03-11T10:30:00Z",
#   "exposure": {
#     "total_notional": 125000.00,
#     "exposure_pct": 12.5,
#     "by_symbol": {...}
#   },
#   "margin": {
#     "utilized": 25000.00,
#     "available": 75000.00,
#     "utilization_pct": 25.0
#   },
#   "concentration": {
#     "max_single_symbol_pct": 8.5,
#     "top_3_concentration": 22.0,
#     "risk_rating": "low"
#   }
# }
```

**Risk Alert Thresholds:**

| Metric | Warning | Critical | Kill-Switch |
|--------|---------|----------|-------------|
| Exposure % | > 50% | > 70% | > 85% |
| Margin Utilization | > 40% | > 60% | > 80% |
| Concentration (top 3) | > 30% | > 50% | > 70% |
| Daily Loss | > 3% | > 5% | > 8% |
| Drawdown | > 7% | > 10% | > 15% |

#### Circuit Breaker Procedures

Circuit breakers automatically halt trading when thresholds are breached:

**Daily Loss Circuit Breaker:**
```python
# Circuit breaker logic
if daily_loss_pct > CIRCUIT_BREAKER_THRESHOLD:
    circuit_breaker.trigger(
        reason="daily_loss_limit",
        severity="critical",
        action="halt_new_positions"
    )
    
    # Actions:
    # 1. Block new entry orders
    # 2. Allow exit orders for 5 minutes
    # 3. Close all positions after 5 minutes
    # 4. Alert risk management
    # 5. Require manual reset
```

**Volatility Spike Circuit Breaker:**
```python
# Volatility-based circuit breaker
current_volatility = calculate_realized_volatility(window="1h")
avg_volatility = get_historical_avg_volatility(lookback="30d")

if current_volatility > avg_volatility * VOLATILITY_MULTIPLIER:
    circuit_breaker.trigger(
        reason="volatility_spike",
        severity="high",
        action="pause_trading",
        duration="15m"
    )
```

**Manual Circuit Breaker Reset:**
```bash
# Check circuit breaker status
curl -s http://localhost:8001/api/v1/risk/circuit-breakers | jq '.'

# Reset after verification (requires authorization)
curl -X POST http://localhost:8001/api/v1/risk/circuit-breakers/reset \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "breaker_id": "daily_loss",
    "reason": "manual_reset_after_review",
    "authorized_by": "operator_id"
  }'
```

#### Kill-Switch Procedures

The kill switch provides immediate emergency halt capability:

**Kill-Switch States:**
- **ARMED** (green): System ready, monitoring active
- **TRIGGERED** (red): Trading halted, positions closing
- **DISABLED** (gray): Kill switch manually disabled

**Automatic Kill-Switch Triggers:**
- Drawdown exceeds 15%
- Daily loss exceeds 8%
- Critical system failures (G1, G4)
- Manual operator activation
- Regulatory halt signal

**Kill-Switch Activation:**
```bash
# Automatic activation (system triggered)
# No manual intervention required

# Manual activation
curl -X POST http://localhost:8001/api/v1/execution/kill-switch/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "manual_emergency",
    "triggered_by": "operator_id",
    "description": "Emergency halt due to..."
  }'

# Verify activation
curl -s http://localhost:8001/api/v1/execution/kill-switch/status | jq '.'
```

**Kill-Switch Recovery:**
```bash
# Only after root cause identified and resolved

# 1. Verify system health
curl -s http://localhost:8001/api/v1/health | jq '.status'

# 2. Check risk metrics normalized
curl -s http://localhost:8001/api/v1/risk/metrics | jq '.'

# 3. Re-arm kill switch (requires authorization)
curl -X POST http://localhost:8001/api/v1/execution/kill-switch/arm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "authorized_by": "operator_id",
    "verification_notes": "Root cause: ... Resolution: ..."
  }'
```

### Trade Budgeter Management

The trade budgeter enforces daily turnover limits to prevent excessive trading:

#### Token System

- **Daily Allocation**: 20 tokens per day
- **Token Cost**: 1 token per filled order (aggregated by order_id)
- **Reset Time**: 00:00 UTC daily
- **Enforcement**: Strict (block entries when exhausted)

#### Budget Monitoring

```bash
# Current budget status
curl -s http://localhost:8001/api/v1/risk/budgeter/status | jq '.'

# Historical consumption
curl -s "http://localhost:8001/api/v1/risk/budgeter/history?days=7" | jq '.'

# Token consumption by strategy
curl -s http://localhost:8001/api/v1/risk/budgeter/by-strategy | jq '.'
```

#### Budget Exhaustion Response

When tokens are exhausted:
1. **Immediate**: Block new entry orders
2. **Continued**: Allow exit orders (don't consume tokens)
3. **Alert**: Notify strategy team
4. **Analysis**: Review consumption pattern
5. **Next Day**: Tokens reset automatically

```python
# Budget exhaustion handler
class BudgetExhaustionHandler:
    def handle_exhaustion(self):
        # Block new entries
        order_gateway.block_entries(reason="budget_exhausted")
        
        # Allow exits to continue
        order_gateway.allow_exits()
        
        # Send alert
        alert_manager.send(
            level="P1",
            message="Trade budget exhausted. New entries blocked.",
            channels=["slack", "pagerduty"]
        )
        
        # Record checkpoint
        checkpoint.record_event(
            type="budget_exhaustion",
            timestamp=datetime.utcnow(),
            tokens_consumed=20
        )
```

## Incident Response Playbook

### Incident Classification

| Severity | Criteria | Response Time | Escalation |
|----------|----------|---------------|------------|
| SEV-1 | Trading halt, data loss, security breach | Immediate | On-call + Leadership |
| SEV-2 | Degraded service, partial outage | 15 minutes | On-call + Manager |
| SEV-3 | Minor issues, non-critical alerts | 1 hour | On-call |
| SEV-4 | Cosmetic issues, documentation | 4 hours | Ticket queue |

### Incident Response Procedures

#### SEV-1: Trading Halt Incident

**Immediate Actions (0-5 minutes):**
```bash
# 1. Verify kill-switch status
curl -s http://localhost:8001/api/v1/execution/kill-switch/status | jq '.state'

# If not triggered, activate manually
curl -X POST http://localhost:8001/api/v1/execution/kill-switch/trigger \
  -d '{"reason": "sev1_incident_response", "triggered_by": "operator"}'

# 2. Alert incident response team
./scripts/ops/alert_incident_team.sh --severity=SEV1 \
  --message="Trading halt incident" \
  --runbook="docs/runbooks/paper-trading-operations-enhanced.md"

# 3. Create incident record
redis-cli -p 6380 HSET "incident:$(date +%s)" \
  severity "SEV1" \
  status "active" \
  start_time "$(date -Iseconds)" \
  operator "$OPERATOR_ID"
```

**Assessment Phase (5-15 minutes):**
```bash
# 1. Run diagnostic suite
./scripts/ops/diagnostic_suite.sh --output=incident_$(date +%s).json

# 2. Check all G1-G8 gates
governance_check.sh --all-gates --output-format=json

# 3. Gather system state
curl -s http://localhost:8001/api/v1/system/state > incident_state_$(date +%s).json
```

**Resolution Phase (ongoing):**
- Apply fixes based on diagnostic results
- Re-validate all gates before resuming
- Document all actions in incident log
- Update runbook if new issues discovered

**Post-Incident:**
```bash
# Record resolution
redis-cli -p 6380 HSET "incident:$(date +%s)" \
  status "resolved" \
  end_time "$(date -Iseconds)" \
  resolution_summary "..."

# Schedule post-mortem
./scripts/ops/schedule_postmortem.sh --incident=$(date +%s) --within=48h
```

#### SEV-2: Degraded Service Incident

**Response Steps:**
1. Identify degraded components via G1-G7 gates
2. Implement degraded service mode if needed
3. Reduce trading scope (fewer symbols)
4. Increase monitoring frequency
5. Work on remediation without trading halt

```bash
# Enable degraded service mode
curl -X POST http://localhost:8001/api/v1/execution/mode/degraded \
  -d '{
    "reason": "sev2_service_degradation",
    "restricted_symbols": ["list", "of", "core", "symbols"],
    "reduced_position_limits": true
  }'
```

#### SEV-3: Minor Issues

**Response:**
- Log issue in ticket system
- Monitor for escalation
- Apply fix during next maintenance window
- No immediate trading impact

### Incident Communication

#### Internal Communication

**Slack Channels:**
- `#incidents-sev1`: SEV-1 incidents only
- `#incidents-general`: All other incidents
- `#trading-ops`: Trading team updates

**PagerDuty:**
- SEV-1: Immediate page + phone call
- SEV-2: Page within 5 minutes
- SEV-3: Page within 15 minutes

#### External Communication

For incidents with potential external impact:
1. Notify stakeholders per communication plan
2. Prepare status page update if applicable
3. Coordinate with communications team
4. Document all external communications

### Incident Documentation

Every incident must be documented with:

```yaml
incident:
  id: INC-YYYY-MM-DD-XXX
  severity: SEV-1|SEV-2|SEV-3|SEV-4
  status: active|resolved|closed
  timeline:
    detected: "2026-03-11T10:30:00Z"
    acknowledged: "2026-03-11T10:32:00Z"
    resolved: "2026-03-11T11:15:00Z"
  impact:
    trading_halted: true|false
    symbols_affected: ["BTC-USDT", "ETH-USDT"]
    duration_minutes: 45
  root_cause: "..."
  resolution: "..."
  follow_up:
    - action: "..."
      owner: "..."
      due_date: "..."
```

## Rollback Procedures

### Checkpoint-Based Recovery

The checkpoint module enables precise rollback to known good states:

#### Checkpoint Types

1. **Pre-Trade Checkpoint**: Captured before trading begins (G8)
2. **Periodic Checkpoint**: Captured every 15 minutes during trading
3. **Pre-Change Checkpoint**: Captured before configuration changes
4. **Manual Checkpoint**: On-demand state capture

#### Creating Checkpoints

```bash
# Manual checkpoint creation
curl -X POST http://localhost:8001/api/v1/checkpoint/create \
  -H "Content-Type: application/json" \
  -d '{
    "checkpoint_type": "manual",
    "description": "Before strategy parameter update",
    "include_state": ["positions", "orders", "risk_limits", "budgeter"]
  }'

# Response includes checkpoint_id for rollback
```

#### Rollback Scenarios

**Scenario 1: Rollback to Start of Day**
```bash
# 1. Identify morning checkpoint
checkpoint_id=$(redis-cli -p 6380 KEYS "checkpoint:authorization:$(date +%Y%m%d)*" | head -1)

# 2. Execute rollback
curl -X POST http://localhost:8001/api/v1/checkpoint/rollback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\n    \"checkpoint_id\": \"${checkpoint_id}\",\n    \"reason\": \"rollback_due_to_strategy_failure\",\n    \"authorized_by\": \"${OPERATOR_ID}\"\n  }"

# 3. Verify rollback
curl -s http://localhost:8001/api/v1/checkpoint/verify | jq '.'
```

**Scenario 2: Rollback After Bad Trade**
```bash
# 1. Find checkpoint before bad trade
curl -s "http://localhost:8001/api/v1/checkpoint/before?time=2026-03-11T10:30:00Z" | jq '.checkpoint_id'

# 2. Execute partial rollback (positions only)
curl -X POST http://localhost:8001/api/v1/checkpoint/rollback \
  -d '{
    "checkpoint_id": "<id>",
    "scope": ["positions"],
    "preserve": ["orders", "budgeter"]
  }'
```

**Scenario 3: Complete State Reset**
```bash
# Nuclear option: reset to baseline
# WARNING: Destroys all current state

curl -X POST http://localhost:8001/api/v1/checkpoint/reset \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "reset_type": "complete",
    "preserve_audit_logs": true,
    "reason": "complete_state_corruption",
    "authorized_by": "operator_id"
  }'
```

#### Rollback Verification

After any rollback, verify state consistency:

```bash
# Run full validation suite
./scripts/ops/rollback_verification.sh --checkpoint=<checkpoint_id>

# Checks:
# - Positions match checkpoint
# - Orders cleared or restored
# - Risk limits consistent
# - Budgeter state valid
# - G1-G7 gates pass
```

### Configuration Rollback

```bash
# Rollback to approved configuration
curl -X POST http://localhost:8001/api/v1/config/rollback \
  -d '{
    "target_version": "approved_baseline_v2.3",
    "scope": ["strategies", "risk_limits"],
    "reason": "parameter_drift_detected"
  }'
```

### Gradual Rollback

For large-scale rollbacks, use gradual approach:

```bash
# Phase 1: Reduce position sizes by 50%
curl -X POST http://localhost:8001/api/v1/positions/reduce \
  -d '{"factor": 0.5}'

# Phase 2: Close remaining positions
curl -X POST http://localhost:8001/api/v1/positions/close-all

# Phase 3: Restore checkpoint state
# (See Scenario 1 above)
```

## Post-Trade Analysis

### Daily Summary Generation

Automated daily summary with governance metrics:

```bash
# Generate comprehensive daily report
./scripts/ops/daily_summary.sh \
  --mode=paper \
  --date=$(date +%Y-%m-%d) \
  --include-governance \
  --output-format=html

# Report includes:
# - Trading performance (PnL, win/loss)
# - Gate validation history
# - Budget consumption analysis
# - Turnover metrics vs ceilings
# - Risk events and responses
# - Incident log
```

### Governance Compliance Report

```bash
# Generate compliance report
curl -s "http://localhost:8001/api/v1/reports/compliance?date=$(date +%Y-%m-%d)" | jq '.'

# Report sections:
# 1. Gate Pass/Fail Summary
# 2. Checkpoint Verification
# 3. Budget Compliance
# 4. Turnover Ceiling Adherence
# 5. Risk Limit Compliance
# 6. Audit Trail Completeness
```

### Performance Analysis

```bash
# Strategy performance with governance context
curl -s "http://localhost:8001/api/v1/reports/strategy-performance?days=30" | jq '.'

# Metrics:
# - Net profit after costs
# - Turnover avg/p95/max
# - Budget efficiency (tokens per $ profit)
# - Gate failure correlation
# - Risk-adjusted returns
```

### Continuous Improvement

Weekly governance review process:

```bash
# Generate weekly governance review
./scripts/ops/weekly_governance_review.sh \
  --week=$(date +%Y-W%V) \
  --output=reports/governance_weekly_$(date +%Y-W%V).pdf

# Review agenda:
# 1. Gate failure analysis
# 2. Checkpoint effectiveness
# 3. Budget consumption patterns
# 4. Incident frequency and resolution
# 5. Proposed gate improvements
# 6. Runbook updates needed
```

## Appendix: Quick Reference Commands

### Governance Commands

```bash
# Run all governance gates
./scripts/ops/governance_check.sh --all-gates

# Run single gate
./scripts/ops/governance_check.sh --gate=G1

# Check gate status history
redis-cli -p 6380 KEYS "checkpoint:G1:*" | wc -l

# View checkpoint details
redis-cli -p 6380 HGETALL "checkpoint:authorization:$(date +%Y%m%d)"
```

### Risk Commands

```bash
# Kill-switch status
./scripts/ops/kill_switch_check.sh

# Trigger kill-switch
curl -X POST http://localhost:8001/api/v1/execution/kill-switch/trigger

# Check risk metrics
curl -s http://localhost:8001/api/v1/risk/metrics | jq '.'

# Check budgeter status
curl -s http://localhost:8001/api/v1/risk/budgeter/status | jq '.'
```

### Monitoring Commands

```bash
# Grafana health
curl -s http://localhost:3001/api/health

# InfluxDB query
curl -G "http://localhost:18087/query" \
  --data-urlencode "db=chiseai" \
  --data-urlencode "q=SELECT * FROM trades LIMIT 10"

# Redis status
redis-cli -p 6380 INFO server | grep -E "redis_version|uptime_in_seconds"
```

### Debugging Commands

```bash
# Container logs
docker logs chiseai-api --tail 100 -f
docker logs chiseai-redis --tail 50

# API latency test
for i in {1..10}; do
  curl -s -w "%{time_total}\n" -o /dev/null http://localhost:8001/api/v1/health
done

# Full diagnostic
./scripts/ops/diagnostic_suite.sh --verbose
```

### Emergency Contacts

| Role | Contact | Method |
|------|---------|--------|
| Operations Lead | ops-lead@chiseai.com | Slack: @ops-lead |
| Risk Manager | risk@chiseai.com | PagerDuty |
| On-Call Engineer | See PagerDuty rotation | PagerDuty + SMS |
| Trading Team | #trading-ops | Slack |
| Infrastructure | #infra-alerts | Slack + PagerDuty |

### Document References

- Kill Switch Trigger: `docs/runbooks/kill-switch-trigger.md`
- Redis Failure Response: `docs/runbooks/redis-failure-response.md`
- API Disconnect: `docs/runbooks/api-disconnect.md`
- Strategy CICD Gates: `.opencode/skills/chiseai-strategy-cicd-gates/SKILL.md`
- Paper Trading Canary: `.opencode/skills/chiseai-paper-trading-canary/SKILL.md`
- Risk Audit: `.opencode/command/chise-risk-audit.md`

---

*This runbook is maintained by the Operations Team. Last updated: 2026-03-11*
*Story ID: PAPER-GOVERNANCE-001*
*For updates or issues, contact ops-team@chiseai.com*
