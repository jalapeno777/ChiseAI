# ChiseAI Paper Trading Grafana Monitoring

## Dashboard Overview

The **ChiseAI - Paper Trading Enhanced Monitoring** dashboard provides real-time visibility into the paper trading system's performance, health, and operational metrics.

**Dashboard ID:** `chiseai-paper-trading-monitoring`

**Refresh Interval:** 5 seconds

**Default Time Range:** Last 1 hour (UTC)

## Data Source

This dashboard uses the **Redis Data Source** plugin to query metrics stored in Redis TimeSeries and key-value structures.

### Required Redis Keys

| Metric | Redis Key Pattern | Type |
|--------|-------------------|------|
| Signal Throughput | `chise:paper:metrics:throughput:*` | TimeSeries |
| Latency Percentiles | `chise:paper:metrics:throughput:latency:*` | TimeSeries |
| Error Rate | `chise:paper:metrics:error_rate:*` | TimeSeries |
| Health Probe | `bmad:chiseai:health:probe` | String |
| Checkpoint Status | `bmad:chiseai:checkpoint:status` | String |
| Active Alerts | `bmad:chiseai:alerts:active` | List |

## Panel Descriptions

### 1. Signal Throughput

**Type:** Graph Panel

**Description:** Displays the rate of trading signals processed per minute.

**Metrics:**
- Signals per minute (aggregated)

**Thresholds:**
- Warning: Below 10 signals/minute

**Query:**
```redis
TS.MRANGE - + FILTER metric=throughput
```

**Interpretation:**
- Normal: Steady throughput with expected fluctuations
- Warning: Sudden drops may indicate upstream issues
- Critical: Zero throughput indicates system failure

### 2. Latency Percentiles

**Type:** Graph Panel

**Description:** Shows latency distribution across p50, p95, and p99 percentiles.

**Metrics:**
- p50 (median): Green line - typical latency
- p95: Yellow line - 95th percentile latency
- p99: Red line - 99th percentile latency (tail latency)

**Thresholds:**
- Warning: > 100ms
- Critical: > 500ms

**Queries:**
```redis
TS.MRANGE - + FILTER percentile=p50
TS.MRANGE - + FILTER percentile=p95
TS.MRANGE - + FILTER percentile=p99
```

**Interpretation:**
- Low spread between percentiles: Consistent performance
- High p99 vs p50: Performance degradation for some requests
- All percentiles elevated: System under stress

### 3. Error Rate by Category

**Type:** Stacked Graph Panel

**Description:** Tracks error rates categorized by type (connection, timeout, validation).

**Categories:**
- Connection (Red): Network or connectivity errors
- Timeout (Orange): Request timeout errors
- Validation (Dark Red): Data validation errors

**Thresholds:**
- Warning: > 1%
- Critical: > 5%

**Queries:**
```redis
TS.MRANGE - + FILTER category=connection
TS.MRANGE - + FILTER category=timeout
TS.MRANGE - + FILTER category=validation
```

**Interpretation:**
- Connection errors: Check network, Redis connectivity
- Timeout errors: Review timeout configurations
- Validation errors: Examine input data quality

### 4. Health Probe Status

**Type:** Stat Panel

**Description:** Displays current health probe status.

**States:**
- HEALTHY (Green): System responding normally
- UNHEALTHY (Red): Health check failing

**Query:**
```redis
GET bmad:chiseai:health:probe
```

**Interpretation:**
- Green: All systems operational
- Red: Immediate investigation required

### 5. Checkpoint Status

**Type:** Stat Panel

**Description:** Shows the last checkpoint completion status.

**States:**
- OK (Green): Last checkpoint successful
- FAILED (Red): Last checkpoint failed
- PENDING (Orange): Checkpoint in progress

**Query:**
```redis
GET bmad:chiseai:checkpoint:status
```

**Interpretation:**
- OK: State persistence working
- FAILED: Data loss risk, check storage
- PENDING: Normal during checkpoint window

### 6. Active Alerts

**Type:** Table Panel

**Description:** Lists active alerts from the monitoring system.

**Columns:**
- Time: Alert timestamp
- Severity: Alert priority (P0, P1, P2)
- Message: Alert description
- Source: Originating component

**Query:**
```redis
LRANGE bmad:chiseai:alerts:active 0 49
```

**Interpretation:**
- P0 (Critical): Immediate action required
- P1 (High): Address within 1 hour
- P2 (Medium): Address within 4 hours

---

## Phase 3 Pipeline Status Panels (New)

The following panels were added as part of **PAPER-DIAG-001-FOLLOWUP-001** for enhanced pipeline visibility:

### 7. Pipeline Status

**Type:** Stat Panel

**Description:** Shows current state of paper trading pipeline with color-coded status indicators.

**Status Values:**
- `running` (Green): Pipeline actively processing signals
- `paused` (Yellow): Pipeline temporarily paused
- `error` (Red): Pipeline in error state
- `recovering` (Blue): Pipeline recovering from error/stale state
- `stopped` (Gray): Pipeline stopped

**Query:**
```redis
GET chise:paper:status:pipeline
```

**Visual:** Background color changes based on status value with clear text label.

**Interpretation:**
- Green: Normal operation
- Yellow: Manual pause or scheduled maintenance
- Red: Investigation required
- Blue: Recovery in progress, monitor closely

### 8. Signals (15m)

**Type:** Time Series Panel

**Description:** Displays signal count over the last 15 minutes with trend indicators and statistical aggregations.

**Metrics:**
- Signal count per aggregation window
- Mean, max, min values shown in legend

**Query:**
```redis
TS.RANGE chise:paper:metrics:signals:count
```

**Visual:** Line chart with 15-minute time window, showing signal volume trends.

**Interpretation:**
- Steady signal flow: Normal operation
- Sudden drops: May indicate upstream data issues
- Spikes: High market activity or system stress
- Zero signals: Pipeline may be paused or stopped

### 9. Stale-Recovery Transitions

**Type:** Table Panel

**Description:** Tracks recovery events from stale state, showing the transition details and recovery duration.

**Columns:**
- **Timestamp**: When the recovery occurred
- **From State**: Previous state (stale, paused, running, error)
- **To State**: New state after recovery (recovering, running, paused)
- **Duration (ms)**: Time taken for recovery in milliseconds

**Query:**
```redis
LRANGE chise:paper:events:recovery 0 49
```

**Data Format:**
Each event is stored as JSON:
```json
{
  "timestamp": "2026-03-11T10:30:00Z",
  "from_state": "stale",
  "to_state": "recovering",
  "duration_ms": 1250
}
```

**Visual:** Table with color-coded state columns:
- From State: Red for stale/error, Yellow for paused, Green for running
- To State: Blue for recovering, Green for running

**Interpretation:**
- Frequent stale states: Check data source connectivity
- Long recovery durations: Investigate recovery mechanism performance
- Successful recoveries: System resilience working as expected

---

## Alert Configuration Guide

### Grafana Alert Rules

Configure the following alert rules in Grafana:

#### 1. Low Throughput Alert

```yaml
Name: Paper Trading Low Throughput
Condition: throughput < 10
For: 2m
Severity: Warning
Message: Signal throughput below threshold
```

#### 2. High Latency Alert

```yaml
Name: Paper Trading High Latency
Condition: p99 > 500ms
For: 1m
Severity: Critical
Message: 99th percentile latency exceeding 500ms
```

#### 3. High Error Rate Alert

```yaml
Name: Paper Trading High Error Rate
Condition: error_rate > 5%
For: 30s
Severity: Critical
Message: Error rate exceeding 5%
```

#### 4. Health Check Failure

```yaml
Name: Health Probe Failure
Condition: health_probe == 0
For: 10s
Severity: Critical
Message: Health probe reporting unhealthy
```

#### 5. Checkpoint Failure

```yaml
Name: Checkpoint Failure
Condition: checkpoint_status == "failed"
For: 0s
Severity: Warning
Message: Last checkpoint failed
```

### Notification Channels

Configure notification channels:

1. **Discord**: Webhook for immediate alerts
2. **Email**: For summary notifications
3. **PagerDuty**: For P0 critical alerts

### Alert Routing

| Severity | Channel | Response Time |
|----------|---------|---------------|
| P0 - Critical | PagerDuty + Discord | Immediate |
| P1 - High | Discord + Email | < 1 hour |
| P2 - Medium | Email | < 4 hours |

## Troubleshooting

### Dashboard Shows No Data

**Symptoms:** Panels display "No data" or empty graphs

**Diagnostic Steps:**

1. **Verify Redis connectivity:**
   ```bash
   redis-cli -h localhost -p 6380 PING
   ```

2. **Check if metrics are being written:**
   ```bash
   redis-cli -h localhost -p 6380 KEYS "chise:paper:metrics:*"
   ```

3. **Verify Redis Data Source configuration:**
   - URL: `redis://localhost:6380`
   - Database: 0 (or appropriate DB)
   - Authentication: If required

4. **Check Grafana logs:**
   ```bash
   docker logs chiseai-grafana
   ```

### High Latency Spikes

**Symptoms:** p95/p99 latency suddenly increases

**Diagnostic Steps:**

1. Check Redis slow log:
   ```bash
   redis-cli -h localhost -p 6380 SLOWLOG GET 10
   ```

2. Monitor system resources:
   ```bash
   docker stats chiseai-redis
   ```

3. Check for memory pressure:
   ```bash
   redis-cli -h localhost -p 6380 INFO memory
   ```

4. Review application logs for blocking operations

### Error Rate Increase

**Symptoms:** Error rate panel shows elevated values

**Diagnostic Steps:**

1. Identify error category from panel
2. Check category-specific logs:
   - Connection errors: Network, firewall, Redis availability
   - Timeout errors: Timeout configurations, resource limits
   - Validation errors: Input data format, schema changes

3. Query recent errors:
   ```bash
   redis-cli -h localhost -p 6380 LRANGE bmad:chiseai:alerts:active 0 10
   ```

### Health Probe Failures

**Symptoms:** Health Probe Status shows UNHEALTHY

**Diagnostic Steps:**

1. Check the health probe endpoint directly:
   ```bash
   curl http://paper-trading-service/health
   ```

2. Verify Redis health key:
   ```bash
   redis-cli -h localhost -p 6380 GET bmad:chiseai:health:probe
   ```

3. Review application health check implementation

### Checkpoint Failures

**Symptoms:** Checkpoint Status shows FAILED

**Diagnostic Steps:**

1. Check storage availability:
   ```bash
   df -h
   ```

2. Verify checkpoint key:
   ```bash
   redis-cli -h localhost -p 6380 GET bmad:chiseai:checkpoint:status
   ```

3. Review checkpoint logs for errors

## Performance Optimization

### Redis Optimization

1. **Enable persistence:**
   ```conf
   appendonly yes
   appendfsync everysec
   ```

2. **Configure memory limits:**
   ```conf
   maxmemory 2gb
   maxmemory-policy allkeys-lru
   ```

3. **Monitor key expiration:**
   ```bash
   redis-cli -h localhost -p 6380 INFO keyspace
   ```

### Grafana Optimization

1. **Adjust refresh intervals:**
   - Production: 30s - 1m
   - Development: 5s - 10s

2. **Use query caching:**
   - Enable in data source settings
   - Set appropriate cache TTL

3. **Limit time ranges:**
   - Default: 1h
   - Maximum: 24h for detailed panels

## Maintenance

### Regular Checks

- [ ] Verify all panels display data
- [ ] Check alert rule effectiveness
- [ ] Review threshold configurations
- [ ] Update documentation for new panels

### Dashboard Updates

When adding new panels:

1. Follow naming convention: `[Category] - [Metric Name]`
2. Add appropriate thresholds
3. Document in this guide
4. Update the panel count in version control

## References

- [Grafana Documentation](https://grafana.com/docs/)
- [Redis TimeSeries](https://redis.io/docs/data-types/timeseries/)
- [Redis Data Source Plugin](https://grafana.com/grafana/plugins/redis-datasource/)
- ChiseAI Architecture Documentation
