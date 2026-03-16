---
title: Redis Failure Response Runbook
category: infrastructure
severity: critical
estimated_time_to_resolve: 10-20 minutes
last_updated: 2026-02-17
maintainers: ops-team
story_id: PAPER-004
executable: true
steps:
  - name: "Check Redis container status"
    command: "docker ps --filter 'name=redis' --format '{{.Names}}: {{.Status}}'"
  - name: "Test Redis connectivity"
    command: "redis-cli -p 6380 PING"
    verify: "PONG"
  - name: "Check Redis memory usage"
    command: "redis-cli -p 6380 INFO memory | grep used_memory_human"
  - name: "Reconnect Redis if needed"
    script: "scripts/ops/reconnect_redis.sh"
    description: "Automated Redis reconnection script"
  - name: "Verify application reconnection"
    command: "docker logs chiseai-api --tail 20 | grep -i 'redis.*connected' || echo 'Check logs manually'"
---

# Redis Failure Response Runbook

## Prerequisites

Before following procedures in this runbook, ensure you have:

- [ ] Docker access (`docker ps` shows running containers)
- [ ] Redis CLI installed (`redis-cli --version` works)
- [ ] Access to chiseai Docker network
- [ ] Application logs access (`docker logs chiseai-api` works)
- [ ] Grafana dashboard access for kill-switch panel
- [ ] Kill-switch check script executable
- [ ] Understanding of circuit breaker indicators

## Problem Description

Redis failures can cause:
- State synchronization issues between components
- Alert system failures
- Position tracking discrepancies
- Circuit breaker activation

**This runbook covers:**
- Redis connectivity issues
- Memory exhaustion
- High latency/degraded performance
- Data corruption scenarios

## Symptoms and Indicators

### Primary Symptoms

1. **REDIS_FAILURE Alert Triggered**
   - Circuit breaker opens
   - Error rate >50%
   - Affected operations logged

2. **Application Errors**
   ```
   ERROR: RedisConnectionError: Connection refused
   ERROR: RedisTimeoutError: Command timed out after 5000ms
   ERROR: CircuitBreakerOpen: Redis circuit breaker is OPEN
   ```

3. **Monitoring Indicators**
   - Grafana: Redis dashboard shows connection failures
   - Data freshness panels show stale data
   - Position sync status shows divergence

### Secondary Indicators

- High memory usage on Redis container
- Increased API response times
- Fallback to in-memory state only
- Missing real-time updates

## Diagnosis Steps

### Phase 1: Initial Assessment (1-2 minutes)

#### 1. Check Redis Container Status

```bash
# Verify container is running
docker ps --filter "name=redis" --format "{{.Names}}: {{.Status}}"

# Check container logs
docker logs chiseai-redis --tail 50
```

#### 2. Test Redis Connectivity

```bash
# Basic connectivity test
redis-cli -p 6380 PING
```

**Expected Output:**
```
PONG
```

```bash
# If no response, check network
docker network inspect chiseai | grep -A 5 redis
```

#### 3. Check Application Logs

```bash
# Look for Redis errors
docker logs chiseai-api --tail 100 | grep -i "redis\|circuit\|timeout"

# Check specific error patterns
docker logs chiseai-api --tail 200 | grep -E "(RedisError|ConnectionError|Timeout)"
```

### Phase 2: Detailed Diagnosis (2-5 minutes)

#### 1. Redis Health Check

```bash
# Server info
redis-cli -p 6380 INFO server | grep -E "redis_version|uptime"

# Memory usage
redis-cli -p 6380 INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio"

# Client connections
redis-cli -p 6380 INFO clients | grep -E "connected_clients|blocked_clients"

# Statistics
redis-cli -p 6380 INFO stats | grep -E "total_connections_received|total_commands_processed|instantaneous_ops_per_sec"
```

#### 2. Check for Memory Issues

```bash
# Memory usage details
redis-cli -p 6380 INFO memory

# If used_memory is near maxmemory, OOM is likely
# Check eviction policy
redis-cli -p 6380 CONFIG GET maxmemory-policy

# Key count and sizes
redis-cli -p 6380 DBSIZE
redis-cli -p 6380 --bigkeys
```

#### 3. Check for Performance Issues

```bash
# Slow queries
redis-cli -p 6380 SLOWLOG GET 10

# Latency test
redis-cli -p 6380 --latency-history

# Command stats
redis-cli -p 6380 INFO commandstats
```

### Phase 3: Application Impact Assessment (2-3 minutes)

#### 1. Check Circuit Breaker Status

**Check Kill-Switch Panel Circuit Breaker Indicators:**

The kill-switch panel in Grafana displays circuit breaker status for critical components including Redis:

```bash
# Check kill-switch panel for circuit breaker indicators
./scripts/ops/kill_switch_check.sh

# Look for circuit breaker state in output
# - CLOSED: Normal operation (green)
# - OPEN: Circuit breaker tripped (red)
```

**Grafana Panel Reference:**
- Navigate to: `Grafana > Dashboards > ChiseAI - Paper Trading`
- Locate: **Kill-Switch Status** panel
- Check: Circuit breaker indicator color
  - 🟢 Green: CLOSED (normal)
  - 🔴 Red: OPEN (tripped)

**API Check:**
```bash
# If application exposes circuit breaker status
curl http://localhost:8001/api/v1/health/circuit-breakers | jq '.'

# Check for Redis-specific circuit breaker
curl http://localhost:8001/api/v1/execution/kill-switch/status | jq '.circuit_breaker'
```

#### 2. Verify State Divergence

```bash
# Check sync status between Redis and memory
curl http://localhost:8001/api/v1/paper/sync-status | jq '{
  divergence_pct: .divergence_pct,
  redis_connected: .redis_connected,
  last_sync: .last_sync_time
}'
```

#### 3. Check Alert Pipeline

```bash
# Verify alerts are still being generated
curl http://localhost:8001/api/v1/alerts/health

# Check if Discord notifications are working
```

## Recovery Procedures

### Scenario 1: Redis Container Down

**Symptoms:** Container not running, connection refused

**Resolution:**

```bash
# 1. Check if container exists
docker ps -a --filter "name=redis"

# 2. Start the container
docker start chiseai-redis

# 3. Wait for startup
sleep 5

# 4. Verify health
redis-cli -p 6380 PING

# 5. Check application reconnection
docker logs chiseai-api --tail 20 | grep -i "redis\|connected"
```

### Scenario 2: Redis Memory Exhaustion

**Symptoms:** OOM errors, high memory usage, evictions

**Resolution:**

```bash
# 1. Check current memory usage
redis-cli -p 6380 INFO memory | grep used_memory_human

# 2. Identify large keys
redis-cli -p 6380 --bigkeys

# 3. Clear non-essential keys (if safe)
# Example: Clear old alert history
redis-cli -p 6380 EVAL "return redis.call('del', unpack(redis.call('keys', 'alerts:history:*')))" 0

# 4. If still critical, restart Redis
docker restart chiseai-redis

# 5. Monitor recovery
watch -n 5 'redis-cli -p 6380 INFO memory | grep used_memory_human'
```

### Scenario 3: High Latency / Slow Performance

**Symptoms:** Slow queries, timeout errors, degraded response times

**Resolution:**

```bash
# 1. Check slow query log
redis-cli -p 6380 SLOWLOG GET 20

# 2. Clear slow log after review
redis-cli -p 6380 SLOWLOG RESET

# 3. Check for blocking operations
redis-cli -p 6380 CLIENT LIST | grep -i "blocked"

# 4. Kill blocking clients if necessary
redis-cli -p 6380 CLIENT KILL TYPE blocked

# 5. Restart if performance doesn't improve
docker restart chiseai-redis
```

### Scenario 4: Data Corruption

**Symptoms:** Invalid data returned, deserialization errors

**Resolution:**

```bash
# 1. Identify corrupted keys
# This requires application-specific knowledge

# 2. Backup current state (if possible)
redis-cli -p 6380 BGSAVE

# 3. Delete corrupted keys
redis-cli -p 6380 DEL "corrupted:key:name"

# 4. Force state resync from application
curl -X POST http://localhost:8001/api/v1/paper/sync/force \
  -d '{"source": "memory", "reason": "redis_data_corruption"}'

# 5. If widespread corruption, restore from backup
# Stop Redis, restore RDB file, start Redis
```

### Scenario 5: Network Connectivity Issues

**Symptoms:** Intermittent connections, timeout errors

**Resolution:**

```bash
# 1. Check Docker network
docker network inspect chiseai

# 2. Verify container is on correct network
docker inspect chiseai-redis | grep -A 10 "Networks"

# 3. Restart container on correct network if needed
docker stop chiseai-redis
docker network disconnect chiseai chiseai-redis 2>/dev/null || true
docker network connect chiseai chiseai-redis
docker start chiseai-redis

# 4. Test connectivity from application container
docker exec chiseai-api redis-cli -h chiseai-redis -p 6380 PING
```

## Failover Options

### Option 1: Application-Level Fallback

When Redis is unavailable, the application can fall back to in-memory state:

```python
# This is handled automatically by the application
# Verify fallback is active:
curl http://localhost:8001/api/v1/health | jq '.redis_fallback_active'
```

**Limitations:**
- State not persisted across restarts
- No distributed coordination
- Limited to single instance

### Option 2: Read-Only Mode

If Redis is partially available:

```bash
# Enable read-only mode
curl -X POST http://localhost:8001/api/v1/config/redis-mode \
  -d '{"mode": "read_only"}'

# This allows reads but queues writes for later
```

### Option 3: Emergency Redis Restart

```bash
# Quick restart with data persistence
docker exec chiseai-redis redis-cli BGSAVE
docker restart chiseai-redis

# Verify data restored
redis-cli -p 6380 DBSIZE
```

## Post-Recovery Verification

### 1. Redis Health Verification

```bash
# Full health check script
redis-cli -p 6380 PING && \
redis-cli -p 6380 INFO server | grep uptime && \
redis-cli -p 6380 INFO memory | grep used_memory_human && \
echo "Redis health check: PASSED"
```

### 2. Application Reconnection

```bash
# Check application can connect
docker logs chiseai-api --tail 50 | grep -i "redis.*connected"

# Verify circuit breaker is closed
curl http://localhost:8001/api/v1/health/circuit-breakers | jq '.redis'
```

### 3. State Synchronization

```bash
# Force a sync to verify
curl -X POST http://localhost:8001/api/v1/paper/sync/force

# Check divergence
curl http://localhost:8001/api/v1/paper/sync-status | jq '.divergence_pct'
# Should be < 1.0
```

### 4. Alert Pipeline Test

```bash
# Send test alert
curl -X POST http://localhost:8001/api/v1/alerts/test \
  -d '{"message": "Redis recovery test", "severity": "info"}'

# Verify alert received in Discord
```

## Prevention Measures

### Monitoring Setup

**Key Metrics to Alert On:**

| Metric | Warning | Critical |
|--------|---------|----------|
| Memory Usage | >70% | >85% |
| Connection Failures | >5/min | >20/min |
| Latency (p99) | >10ms | >50ms |
| Evicted Keys | >100/min | >1000/min |

**Grafana Alerts:**
```yaml
# Example alert rule
- alert: RedisHighMemoryUsage
  expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.85
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Redis memory usage is above 85%"
```

### Configuration Best Practices

**Redis Configuration:**
```conf
# /etc/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
timeout 300
tcp-keepalive 60
```

**Application Configuration:**
```yaml
redis:
  host: chiseai-redis
  port: 6380
  socket_timeout: 5
  socket_connect_timeout: 5
  retry_on_timeout: true
  health_check_interval: 30
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout: 30
    expected_exception: redis.exceptions.RedisError
```

### Backup Strategy

**Automated Backups:**
```bash
# Add to crontab
0 */6 * * * docker exec chiseai-redis redis-cli BGSAVE

# Backup RDB file
0 0 * * * cp /var/lib/redis/dump.rdb /backups/redis/dump-$(date +%Y%m%d).rdb
```

## Quick Reference Commands

```bash
# Emergency restart
docker restart chiseai-redis

# Check status
redis-cli -p 6380 INFO | grep -E "uptime|connected_clients|used_memory"

# Monitor in real-time
redis-cli -p 6380 MONITOR

# Check slow queries
redis-cli -p 6380 SLOWLOG GET 10

# Memory analysis
redis-cli -p 6380 --bigkeys

# Force save
redis-cli -p 6380 BGSAVE

# Check replication (if configured)
redis-cli -p 6380 INFO replication
```

## Related Runbooks

- [Kill Switch Trigger](kill-switch-trigger.md) - If Redis failure triggers kill switch
- [Paper Trading Operations](paper-trading-operations.md) - Daily operations and sync issues
- [API Disconnect](api-disconnect.md) - Related connectivity issues

## Escalation Path

### Level 1: On-Call Engineer (0-10 minutes)
- Execute Redis recovery procedures
- Verify application functionality
- Document incident

### Level 2: Infrastructure Team (10-30 minutes)
- Investigate root cause
- Review configuration
- Plan preventive measures

### Level 3: Platform Architect (30+ minutes)
- Evaluate architecture changes
- Consider Redis clustering
- Review data persistence strategy

## Contact Information

- **On-Call Engineer**: PagerDuty rotation
- **Infrastructure Team**: #infrastructure Slack channel
- **Platform Architect**: platform@chiseai.slack.com
