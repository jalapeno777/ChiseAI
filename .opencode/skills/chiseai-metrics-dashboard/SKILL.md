---
name: chiseai-metrics-dashboard
description: Grafana dashboard interaction guide and metrics reference for ChiseAI observability.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-metrics-dashboard

## Goal

Provide standardized guidance for interacting with Grafana dashboards and understanding ChiseAI metrics for monitoring, debugging, and performance analysis.

## When To Use

- Monitoring system health and performance
- Debugging issues using metrics
- Setting up alerts for critical thresholds
- Reviewing trading system performance
- Analyzing agent swarm activity
- Capacity planning and resource optimization

## When Not To Use

- Log analysis (use logging tools instead)
- Code debugging (use debugger)
- Data analysis (use analytics tools)
- Configuration changes (use config files)

## Dashboard Overview

### Primary Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| System Overview | `http://localhost:3001/d/system` | High-level system health |
| Trading Performance | `http://localhost:3001/d/trading` | Strategy execution metrics |
| Agent Activity | `http://localhost:3001/d/agents` | Swarm agent operations |
| Data Pipeline | `http://localhost:3001/d/pipeline` | Data ingestion health |
| Infrastructure | `http://localhost:3001/d/infra` | Resource utilization |

### Access Information

- **Host**: `chiseai-grafana` (Docker network) or `localhost:3001` (host)
- **Default Credentials**: Check `infrastructure/terraform/` for configured credentials
- **Data Sources**: InfluxDB, PostgreSQL, Redis

## Key Metrics Reference

### System Health Metrics

| Metric | Source | Description | Alert Threshold |
|--------|--------|-------------|-----------------|
| `system_cpu_percent` | InfluxDB | CPU utilization | >80% for 5min |
| `system_memory_percent` | InfluxDB | Memory utilization | >85% for 5min |
| `system_disk_percent` | InfluxDB | Disk utilization | >90% |
| `system_uptime` | InfluxDB | System uptime | N/A |

### Trading Metrics

| Metric | Source | Description | Alert Threshold |
|--------|--------|-------------|-----------------|
| `trading_orders_total` | InfluxDB | Total orders placed | N/A |
| `trading_orders_success` | InfluxDB | Successful orders | <95% success rate |
| `trading_latency_ms` | InfluxDB | Order execution latency | >500ms p99 |
| `trading_pnl_daily` | InfluxDB | Daily P&L | Custom |
| `trading_drawdown_pct` | InfluxDB | Current drawdown | >10% |

### Agent Swarm Metrics

| Metric | Source | Description | Alert Threshold |
|--------|--------|-------------|-----------------|
| `agent_stories_active` | Redis | Active story count | N/A |
| `agent_ownership_locks` | Redis | Current ownership locks | >50 locks |
| `agent_iterations_total` | Redis | Total iterations today | N/A |
| `agent_incidents_total` | Redis | Incident count today | >5 incidents |
| `agent_parallel_workers` | Redis | Active parallel workers | N/A |

### Data Pipeline Metrics

| Metric | Source | Description | Alert Threshold |
|--------|--------|-------------|-----------------|
| `pipeline_ingestion_rate` | InfluxDB | Data points/second | <100/s degraded |
| `pipeline_lag_seconds` | InfluxDB | Data freshness lag | >60s stale |
| `pipeline_errors_total` | InfluxDB | Ingestion errors | >0 in 5min |
| `pipeline_queue_depth` | Redis | Queue backlog | >1000 items |

### Infrastructure Metrics

| Metric | Source | Description | Alert Threshold |
|--------|--------|-------------|-----------------|
| `infra_redis_connections` | Redis | Active connections | >100 |
| `infra_redis_memory_mb` | Redis | Memory usage | >500MB |
| `infra_postgres_connections` | PostgreSQL | DB connections | >50 |
| `infra_postgres_size_mb` | PostgreSQL | DB size | Growing unexpectedly |

## Alerting Guide

### Alert Severity Levels

| Level | Color | Response Time | Example |
|-------|-------|---------------|---------|
| Critical | Red | Immediate | System down, data loss risk |
| Warning | Orange | <15 minutes | High latency, resource pressure |
| Info | Blue | <1 hour | Threshold approaching |
| OK | Green | N/A | All normal |

### Standard Alert Rules

#### Critical Alerts

```yaml
# Trading system down
- alert: TradingSystemDown
  expr: up{job="trading"} == 0
  for: 1m
  severity: critical
  annotations:
    summary: "Trading system is down"
    description: "No heartbeat from trading system for 1 minute"

# Database connection failure
- alert: DatabaseConnectionLost
  expr: pg_up == 0
  for: 30s
  severity: critical
  annotations:
    summary: "Database connection lost"
    description: "Cannot connect to PostgreSQL"
```

#### Warning Alerts

```yaml
# High CPU usage
- alert: HighCPUUsage
  expr: system_cpu_percent > 80
  for: 5m
  severity: warning
  annotations:
    summary: "High CPU usage"
    description: "CPU usage above 80% for 5 minutes"

# High drawdown
- alert: HighDrawdown
  expr: trading_drawdown_pct > 10
  for: 1m
  severity: warning
  annotations:
    summary: "Trading drawdown exceeds 10%"
    description: "Current drawdown at {{ $value }}%"
```

### Alert Notification Channels

| Channel | Use Case | Configuration |
|---------|----------|---------------|
| Discord | Team notifications | Webhook configured in Grafana |
| Email | Critical alerts only | SMTP configured |
| Slack | Development alerts | Webhook optional |

### Creating Custom Alerts

1. Navigate to Alerting → Alert Rules
2. Click "New Alert Rule"
3. Define query (PromQL/InfluxQL)
4. Set condition and duration
5. Add notification channel
6. Save and test

## Exit Conditions

- Metrics reviewed for task-relevant systems
- Alerts understood for monitored thresholds
- Dashboard accessible and functional
- Issues reported if metrics indicate problems

## Troubleshooting/Safety

### Common Issues

| Issue | Symptoms | Resolution |
|-------|----------|------------|
| Dashboard not loading | Blank page, errors | Check Grafana container status |
| Metrics missing | Gaps in charts | Verify data source connectivity |
| Alerts not firing | No notifications | Check alert rule configuration |
| High latency | Slow dashboard | Check InfluxDB query performance |

### Grafana Container Issues

```bash
# Check container status
docker ps --filter name=chiseai-grafana

# View container logs
docker logs chiseai-grafana --tail 100

# Restart container
docker restart chiseai-grafana

# Check network connectivity
docker exec chiseai-grafana curl http://chiseai-influxdb:8086/health
```

### Data Source Issues

```bash
# Test InfluxDB connection
curl http://localhost:18087/health

# Test PostgreSQL connection
psql -h chiseai-postgres -p 5434 -U chiseai -d chiseai -c "SELECT 1"

# Test Redis connection
redis-cli -h chiseai-redis -p 6380 ping
```

## Templates

### Template 1: Metrics Query Examples

```sql
-- InfluxQL: CPU usage over last hour
SELECT mean("usage_percent") 
FROM "cpu" 
WHERE time > now() - 1h 
GROUP BY time(1m)

-- InfluxQL: Order latency percentiles
SELECT percentile("latency_ms", 99) 
FROM "orders" 
WHERE time > now() - 24h 
GROUP BY time(5m)

-- InfluxQL: Trading volume by symbol
SELECT sum("volume") 
FROM "trades" 
WHERE time > now() - 1d 
GROUP BY "symbol"
```

```sql
-- PostgreSQL: Recent story activity
SELECT story_id, status, updated_at 
FROM story_tracking 
WHERE updated_at > NOW() - INTERVAL '24 hours'
ORDER BY updated_at DESC;

-- PostgreSQL: Agent performance
SELECT agent_name, 
       COUNT(*) as tasks_completed,
       AVG(duration_seconds) as avg_duration
FROM agent_tasks
WHERE completed_at > NOW() - INTERVAL '7 days'
GROUP BY agent_name;
```

### Template 2: Dashboard Panel Configuration

```json
{
  "title": "Trading Latency",
  "type": "graph",
  "targets": [
    {
      "query": "SELECT percentile(\"latency_ms\", 50) FROM \"orders\" WHERE time > now() - 1h GROUP BY time(1m)",
      "alias": "p50"
    },
    {
      "query": "SELECT percentile(\"latency_ms\", 99) FROM \"orders\" WHERE time > now() - 1h GROUP BY time(1m)",
      "alias": "p99"
    }
  ],
  "yaxes": [
    {"format": "ms", "label": "Latency"}
  ],
  "alert": {
    "conditions": [
      {
        "evaluator": {"params": [500], "type": "gt"},
        "query": {"params": ["A", "1m", "now"]}
      }
    ]
  }
}
```

### Template 3: Alert Rule Template

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: chiseai-trading
    folder: Trading
    interval: 1m
    rules:
      - uid: alert-drawdown
        title: High Drawdown Warning
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            model:
              expr: trading_drawdown_pct
              instant: true
          - refId: B
            relativeTimeRange:
              from: 300
              to: 0
            model:
              expr: "10"
              instant: true
          - refId: C
            model:
              type: reduce
              reducer: last
              expression: A
          - refId: D
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [10]
                    type: gt
        noDataState: OK
        execErrState: Error
        for: 1m
        annotations:
          summary: "Drawdown at {{ $values.A.Value }}%"
          description: "Trading drawdown exceeds 10% threshold"
        labels:
          severity: warning
          team: trading
```

### Template 4: Health Check Query

```python
# Programmatic health check using metrics
import requests

def check_system_health():
    """Check overall system health via Grafana metrics"""
    
    health_status = {
        "timestamp": datetime.now().isoformat(),
        "checks": []
    }
    
    # Check CPU
    cpu_query = 'SELECT last("usage_percent") FROM "cpu"'
    cpu_result = query_influx(cpu_query)
    health_status["checks"].append({
        "name": "cpu",
        "value": cpu_result,
        "status": "OK" if cpu_result < 80 else "WARNING"
    })
    
    # Check Memory
    mem_query = 'SELECT last("used_percent") FROM "mem"'
    mem_result = query_influx(mem_query)
    health_status["checks"].append({
        "name": "memory",
        "value": mem_result,
        "status": "OK" if mem_result < 85 else "WARNING"
    })
    
    # Check Trading System
    trading_query = 'SELECT last("value") FROM "up" WHERE "job"=\'trading\''
    trading_result = query_influx(trading_query)
    health_status["checks"].append({
        "name": "trading",
        "value": trading_result,
        "status": "OK" if trading_result == 1 else "CRITICAL"
    })
    
    # Overall status
    critical_count = sum(1 for c in health_status["checks"] if c["status"] == "CRITICAL")
    warning_count = sum(1 for c in health_status["checks"] if c["status"] == "WARNING")
    
    if critical_count > 0:
        health_status["overall"] = "CRITICAL"
    elif warning_count > 0:
        health_status["overall"] = "WARNING"
    else:
        health_status["overall"] = "OK"
    
    return health_status
```

## Examples

### Example 1: Monitoring Trading Session

**Context**: Need to monitor active trading session

**Steps**:

1. Navigate to Trading Performance dashboard
2. Check key panels:
   - Orders per minute
   - Latency distribution
   - Position sizes
   - P&L chart

**Alerts to Watch**:
- `HighLatencyWarning`: >500ms p99
- `OrderFailureRate`: >5% failures
- `DrawdownWarning`: >10%

**Queries**:

```sql
-- Current session orders
SELECT COUNT(*) FROM orders 
WHERE session_id = 'current' AND time > now() - 1h

-- Session P&L
SELECT SUM(realized_pnl) FROM trades
WHERE session_id = 'current'
```

### Example 2: Debugging High Latency

**Context**: Trading latency spiked

**Investigation Steps**:

1. Open Trading Performance dashboard
2. Identify latency spike in graph
3. Correlate with other metrics:
   - CPU usage at same time
   - Memory usage
   - Network I/O
   - Database query time

**Diagnostic Queries**:

```sql
-- Latency by operation type
SELECT operation, percentile(latency_ms, 99) as p99
FROM orders 
WHERE time > now() - 1h
GROUP BY operation

-- Slow database queries
SELECT query, mean_duration_ms
FROM pg_stat_statements
ORDER BY mean_duration_ms DESC
LIMIT 10
```

**Resolution**: Found database query causing lock contention. Added index to resolve.

### Example 3: Agent Swarm Monitoring

**Context**: Multiple agents running in parallel

**Monitoring Panels**:

- Active Stories: Shows all in-progress work
- Ownership Locks: Displays current claims
- Incident Rate: Tracks problems
- Throughput: Stories completed per hour

**Redis Metrics Check**:

```python
# Check active ownership locks
locks = redis_state_hgetall("bmad:chiseai:ownership")
print(f"Active locks: {len(locks)}")
for path, owner in locks.items():
    print(f"  {path} -> {owner}")

# Check iteration counts
story_keys = redis_state_scan_all_keys(pattern="bmad:chiseai:iterlog:story:*")
print(f"Active story iterations: {len(story_keys)}")
```

**Alert**: Too many parallel workers detected (>10). Jarvis notified to re-balance.

## Quick Reference

### Dashboard URLs (Docker Network)

| Dashboard | URL |
|-----------|-----|
| Grafana Home | `http://chiseai-grafana:3001` |
| System Overview | `http://chiseai-grafana:3001/d/system` |
| Trading | `http://chiseai-grafana:3001/d/trading` |
| Agents | `http://chiseai-grafana:3001/d/agents` |
| Pipeline | `http://chiseai-grafana:3001/d/pipeline` |

### Dashboard URLs (Host Access)

| Dashboard | URL |
|-----------|-----|
| Grafana Home | `http://localhost:3001` |
| System Overview | `http://localhost:3001/d/system` |
| Trading | `http://localhost:3001/d/trading` |

### Key Metric Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| CPU | >80% | >95% |
| Memory | >85% | >95% |
| Disk | >90% | >98% |
| Latency (p99) | >500ms | >1000ms |
| Drawdown | >10% | >20% |
| Order Failures | >5% | >10% |

### Common InfluxQL Queries

```sql
-- Last value
SELECT last("value") FROM "metric"

-- Average over time
SELECT mean("value") FROM "metric" WHERE time > now() - 1h GROUP BY time(5m)

-- Percentiles
SELECT percentile("value", 99) FROM "metric" WHERE time > now() - 24h

-- Rate (per second)
SELECT derivative(first("value"), 1s) FROM "metric" WHERE time > now() - 1h
```

### Redis Metrics Commands

```bash
# Memory usage
redis-cli INFO memory

# Connected clients
redis-cli CLIENT LIST

# Key count
redis-cli DBSIZE

# Slow log
redis-cli SLOWLOG GET 10
```

## Related Skills

- `chiseai-incident-response` - Respond to metric-based alerts
- `chiseai-data-first` - Gather metrics data for analysis
- `chiseai-docker-governance` - Container-based infrastructure

## Related Commands

- `.opencode/command/chise-incident-log.md` - Log incidents from alerts
- `.opencode/command/chise-precommit-gates.md` - Pre-commit validation includes metric checks
