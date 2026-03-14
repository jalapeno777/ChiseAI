---
title: Tempo Incident Response Runbook
category: incident-response
severity: critical
estimated_time_to_resolve: 10-60 minutes
last_updated: 2026-03-14
maintainers: platform-team
story_id: TEMPO-2026-001
executable: true
---

# Tempo Incident Response Runbook

> **Story:** TEMPO-2026-001  
> **Last Updated:** 2026-03-14  
> **Owner:** Platform Operations Team  
> **Severity:** P1-P2 (See classification below)  
> **Alert Acknowledgment SLA:** < 15 minutes

---

## Overview

This runbook provides emergency procedures for critical incidents involving Grafana Tempo, the distributed tracing system. These procedures should be followed when Tempo experiences outages, storage issues, or performance degradation that impacts observability.

## Incident Classification

### Severity Levels for Tempo Incidents

| Severity | Criteria | Response Time | Examples |
|----------|----------|---------------|----------|
| **P0** | Complete outage, no trace ingestion | Immediate | All Tempo services down, disk full |
| **P1** | Partial degradation, slow queries | < 15 min | High latency, intermittent failures |
| **P2** | Minor impact, workaround exists | < 1 hour | Single component failure |
| **P3** | Cosmetic/Non-urgent | < 4 hours | Dashboard issues only |

### Impact Assessment Questions

1. **Is trace ingestion affected?** (New traces not being stored)
2. **Are queries failing?** (Cannot search existing traces)
3. **Is storage at risk?** (Disk > 90% full)
4. **Are multiple services affected?** (Beyond just Tempo)

---

## 1. Tempo Service Down - Restart Procedure

### 1.1 Symptom Detection

- Grafana showing "Data source error" for Tempo
- `curl http://host.docker.internal:3200/ready` returns error or timeout
- All trace searches failing
- PagerDuty alert: "Tempo Unhealthy"

### 1.2 Initial Assessment (First 5 minutes)

**Step 1: Confirm Service Status**
```bash
# Check container status
docker ps --filter "name=chiseai-tempo" --format "table {{.Names}}\t{{.Status}}\t{{.State}}"

# Expected: Either "Up" or not running
```

**Step 2: Quick Health Check**
```bash
# Test readiness endpoint
curl -s --max-time 10 http://host.docker.internal:3200/ready
echo "Exit code: $?"

# Expected: "ready" with exit code 0
# If failed, proceed to restart
```

**Step 3: Check Recent Logs**
```bash
# Get last 20 log lines
docker logs chiseai-tempo --tail 20 2>&1

# Look for:
# - OOM errors
# - Disk full errors
# - Configuration errors
# - Panic/crash messages
```

### 1.3 Restart Procedure

**Step 1: Document Current State**
```bash
# Capture current state before restart
INCIDENT_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "Incident Time: $INCIDENT_TIME" > /tmp/tempo_incident_$INCIDENT_TIME.log

docker ps --filter "name=chiseai-tempo" >> /tmp/tempo_incident_$INCIDENT_TIME.log
curl -s http://host.docker.internal:3200/status >> /tmp/tempo_incident_$INCIDENT_TIME.log 2>&1 || echo "Status check failed" >> /tmp/tempo_incident_$INCIDENT_TIME.log
```

**Step 2: Restart Tempo Container**
```bash
# Graceful restart
echo "Restarting Tempo at $(date)..."
docker restart chiseai-tempo

# Wait for startup
echo "Waiting for Tempo to initialize (30 seconds)..."
sleep 30
```

**Step 3: Verify Restart Success**
```bash
# Check container is running
docker ps --filter "name=chiseai-tempo" --format "{{.Names}}: {{.Status}}"

# Verify readiness
curl -s http://host.docker.internal:3200/ready
# Expected: "ready"

# Check component status
curl -s http://host.docker.internal:3200/status | jq -r '.components | to_entries | .[] | "\(.key): \(.value)"'
# Expected: All components "Healthy"
```

**Step 4: Verify Trace Ingestion**
```bash
# Wait for services to reconnect
echo "Waiting 60 seconds for services to reconnect..."
sleep 60

# Generate test trace
curl -s http://localhost:8001/api/v1/health > /dev/null
sleep 10

# Verify trace was ingested
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=5&start=$(date -d '5 minutes ago' +%s)" | jq '.traces | length'
# Expected: > 0
```

**Rollback Procedure (If Restart Fails):**
```bash
# If restart fails, check for:
# 1. Disk space
docker exec chiseai-tempo df -h /tmp/tempo

# 2. Port conflicts
netstat -tlnp | grep -E "3200|4317|4318"

# 3. Recreate container if needed
docker stop chiseai-tempo
docker rm chiseai-tempo

# Recreate from Terraform or docker-compose
# See: infrastructure/terraform/tempo.tf or docker-compose.yml
```

**Verification Steps:**
- [ ] Container status shows "Up"
- [ ] Readiness check returns "ready"
- [ ] All components report "Healthy"
- [ ] Test trace successfully ingested and searchable
- [ ] Grafana can query Tempo datasource

---

## 2. Storage Full - Emergency Cleanup

### 2.1 Symptom Detection

- Alert: "Disk usage > 90%"
- Tempo logs showing "no space left on device"
- Traces failing to ingest
- Container in "unhealthy" state

### 2.2 Immediate Assessment

**Step 1: Verify Disk Usage**
```bash
# Check disk usage
docker exec chiseai-tempo df -h /tmp/tempo

# Expected output:
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/sda1        50G   48G  2.0G  96% /tmp/tempo

# Calculate usage percentage
USAGE=$(docker exec chiseai-tempo df /tmp/tempo | tail -1 | awk '{print $5}' | tr -d '%')
echo "Current disk usage: ${USAGE}%"

if [ "$USAGE" -gt 95 ]; then
    echo "CRITICAL: Storage is > 95% full"
    SEVERITY="P0"
elif [ "$USAGE" -gt 90 ]; then
    echo "WARNING: Storage is > 90% full"
    SEVERITY="P1"
fi
```

**Step 2: Identify Large Files/Blocks**
```bash
# List largest block directories
docker exec chiseai-tempo du -sh /tmp/tempo/blocks/* 2>/dev/null | sort -hr | head -20

# Check wal directory
docker exec chiseai-tempo du -sh /tmp/tempo/wal 2>/dev/null

# Check compactor directory
docker exec chiseai-tempo du -sh /tmp/tempo/compactor 2>/dev/null
```

**Step 3: Check Retention Settings**
```bash
# View current retention
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 3 "block_retention"
# Default: 168h (7 days)
```

### 2.3 Emergency Cleanup Procedure

**Option A: Aggressive Retention Reduction (Recommended First)**

```bash
# 1. Stop Tempo (to prevent corruption)
docker stop chiseai-tempo

# 2. Backup current config
docker cp chiseai-tempo:/etc/tempo/tempo.yaml /tmp/tempo-backup-$(date +%Y%m%d-%H%M%S).yaml

# 3. Edit config to reduce retention
cat > /tmp/tempo-emergency.yaml << 'EOF'
# Emergency retention config - 24 hours only
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

ingester:
  max_block_duration: 30m
  max_block_bytes: 100_000_000
  trace_idle_period: 30m

compactor:
  compaction:
    block_retention: 24h  # Reduced from 168h
    compacted_block_retention: 1h

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
    pool:
      max_workers: 50
      queue_depth: 200

overrides:
  max_traces_per_user: 10000
  max_bytes_per_trace: 5000000
EOF

# 4. Copy emergency config
docker cp /tmp/tempo-emergency.yaml chiseai-tempo:/etc/tempo/tempo.yaml

# 5. Manually remove old blocks (older than 24 hours)
CUTOFF=$(date -d '24 hours ago' +%s)
for block in $(docker exec chiseai-tempo ls /tmp/tempo/blocks 2>/dev/null); do
  # Extract timestamp from block ID (format: uuid-ulid)
  # This is approximate - blocks use ULID which encodes timestamp
  docker exec chiseai-tempo rm -rf "/tmp/tempo/blocks/$block" 2>/dev/null
done

# 6. Clear WAL
docker exec chiseai-tempo rm -rf /tmp/tempo/wal/* 2>/dev/null

# 7. Start Tempo
docker start chiseai-tempo

# 8. Monitor recovery
echo "Monitoring Tempo startup..."
sleep 30
docker logs chiseai-tempo --tail 20

# 9. Verify disk usage
docker exec chiseai-tempo df -h /tmp/tempo
```

**Option B: Manual Block Deletion (If Option A Insufficient)**

```bash
# WARNING: This deletes trace data. Use only as last resort.

echo "WARNING: This will delete trace data!"
echo "Press Ctrl+C to cancel, or wait 10 seconds to continue..."
sleep 10

# Stop Tempo
docker stop chiseai-tempo

# Delete oldest blocks (keep only last 6 hours)
CUTOFF=$(date -d '6 hours ago' +%s)
docker exec chiseai-tempo bash -c "cd /tmp/tempo/blocks && ls -t | tail -n +10 | xargs -r rm -rf"

# Clear all WAL data
docker exec chiseai-tempo rm -rf /tmp/tempo/wal/*

# Clear compactor temp data
docker exec chiseai-tempo rm -rf /tmp/tempo/compactor/*

# Start Tempo
docker start chiseai-tempo

# Verify
echo "New disk usage:"
docker exec chiseai-tempo df -h /tmp/tempo
```

**Option C: Expand Storage (If Possible)**

```bash
# If using volume, expand it
# This depends on storage driver - example for standard Docker:

# 1. Stop and remove container
docker stop chiseai-tempo
docker rm chiseai-tempo

# 2. Create larger volume
docker volume create --driver local \
  --opt type=none \
  --opt o=bind \
  --opt device=/path/to/larger/storage \
  tempo-data-new

# 3. Copy existing data (optional - may be too slow)
# Or start fresh if data loss is acceptable

# 4. Recreate container with new volume
# (Use Terraform or docker-compose for proper recreation)
```

### 2.4 Post-Cleanup Verification

**Step 1: Verify Disk Usage**
```bash
docker exec chiseai-tempo df -h /tmp/tempo
# Expected: < 70% usage
```

**Step 2: Verify Tempo Health**
```bash
curl -s http://host.docker.internal:3200/ready
# Expected: "ready"
```

**Step 3: Test Trace Ingestion**
```bash
# Generate test traces
for i in {1..5}; do
  curl -s http://localhost:8001/api/v1/health > /dev/null
  sleep 2
done

sleep 10

# Verify traces are being stored
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=10" | jq '.traces | length'
# Expected: > 0
```

**Rollback (If Cleanup Causes Issues):**
```bash
# Restore original config
docker stop chiseai-tempo
docker cp /tmp/tempo-backup-*.yaml chiseai-tempo:/etc/tempo/tempo.yaml
docker start chiseai-tempo
```

---

## 3. High Ingestion Rate - Sampling Adjustment

### 3.1 Symptom Detection

- Tempo lagging behind ingestion
- Increasing WAL size
- Slow query performance
- Alerts: "High ingestion rate"
- Storage growing rapidly

### 3.2 Assessment

**Step 1: Measure Current Ingestion Rate**
```bash
# Get traces per second
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[5m])" | jq '.data.result[].value[1]'

# Get spans per second
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_spans_total[5m])" | jq '.data.result[].value[1]'

# Check if rate is increasing
curl -s "http://host.docker.internal:9090/api/v1/query?query=deriv(tempo_ingester_traces_created_total[30m])" | jq '.data.result[].value[1]'
```

**Step 2: Check Current Sampling Rates**
```bash
# Check application sampling
docker exec chiseai-api env | grep OTEL_TRACES_SAMPLER_ARG

# Expected: Value between 0.0 and 1.0
# If missing, default may be 1.0 (100% - very high)
```

### 3.3 Emergency Sampling Reduction

**Step 1: Reduce Application Sampling (Immediate)**
```bash
# Set very low sampling rate
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.01  # 1% sampling

# Apply to main application
docker restart chiseai-api

# If multiple applications, apply to all:
docker restart chiseai-executor chiseai-worker 2>/dev/null || true
```

**Step 2: Monitor Impact**
```bash
# Wait 5 minutes
echo "Waiting 5 minutes for sampling change to take effect..."
sleep 300

# Check new ingestion rate
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[5m])" | jq '.data.result[].value[1]'

# Rate should have decreased significantly
```

**Step 3: Verify System Recovery**
```bash
# Check WAL is being processed
docker exec chiseai-tempo du -sh /tmp/tempo/wal

# Check compactor is catching up
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempodb_compaction_objects_written[5m])" | jq '.data.result[].value[1]'
```

**Rollback (When Ready to Restore Normal Sampling):**
```bash
# Restore normal sampling rate
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sampling
docker restart chiseai-api
```

---

## 4. Contact Escalation Path

### 4.1 Escalation Matrix

| Severity | First Response | Escalation 1 | Escalation 2 | Escalation 3 |
|----------|----------------|--------------|--------------|--------------|
| **P0** | On-call Engineer | Platform Lead (15 min) | Engineering Manager (30 min) | VP Engineering (1 hour) |
| **P1** | On-call Engineer | Platform Lead (30 min) | Engineering Manager (1 hour) | - |
| **P2** | On-call Engineer | Platform Lead (2 hours) | - | - |
| **P3** | Ticket System | - | - | - |

### 4.2 Contact Information

**Platform Team:**
| Role | Slack | PagerDuty | Email |
|------|-------|-----------|-------|
| On-call Engineer | #incidents | Primary on-call | oncall@chiseai.com |
| Platform Lead | @platform-lead | Secondary rotation | platform@chiseai.com |
| Engineering Manager | @eng-manager | Escalation | eng-mgr@chiseai.com |

**Emergency Contacts:**
| Role | Phone | Slack |
|------|-------|-------|
| Platform Lead | +1-XXX-XXX-XXXX | @platform-lead |
| Engineering Manager | +1-XXX-XXX-XXXX | @eng-manager |
| VP Engineering | +1-XXX-XXX-XXXX | @vp-eng |

### 4.3 Notification Templates

**P0 Alert - Tempo Down:**
```
🚨 P0 INCIDENT: Tempo Service Down

Impact: Trace ingestion and querying unavailable
Time: $(date -u +"%Y-%m-%d %H:%M UTC")
Detection: Health check failure

Current Status: Investigating
Actions Taken:
- Confirmed service unresponsive
- Initiating restart procedure

Next Update: 15 minutes
Incident Commander: @oncall-engineer
```

**P1 Alert - Storage Critical:**
```
⚠️ P1 INCIDENT: Tempo Storage > 90%

Current Usage: XX%
Impact: Risk of ingestion failure
Time: $(date -u +"%Y-%m-%d %H:%M UTC")

Actions Taken:
- Initiating emergency cleanup
- Reducing retention to 24h

Next Update: 30 minutes
Assigned: @oncall-engineer
```

**Status Update Template:**
```
📊 Tempo Incident Update

Time: +XX minutes since start
Status: [Investigating/Mitigating/Monitoring/Resolved]

Progress:
- [What has been done]
- [Current state]

Next Steps:
- [Planned actions]

ETA: [Resolution estimate]
```

**Resolution Notice:**
```
✅ Tempo Incident Resolved

Duration: XX minutes
Resolution: [Brief description]

Impact:
- Traces lost: [Yes/No, timeframe]
- Services affected: [List]

Post-mortem: Scheduled for [Date/Time]
```

---

## 5. Related Runbooks and Resources

### 5.1 Related Runbooks

- [Tempo Operations](tempo-operations.md) - Day-to-day procedures
- [Tempo Troubleshooting](tempo-troubleshooting.md) - Diagnostic procedures
- [Incident Response](incident_response.md) - General incident management
- [Redis Failure Response](redis-failure-response.md) - If Redis also affected

### 5.2 Quick Reference Commands

```bash
# Full health check
./scripts/ops/tempo_health_check.sh

# Emergency restart
docker restart chiseai-tempo && sleep 30 && curl http://host.docker.internal:3200/ready

# Disk usage check
docker exec chiseai-tempo df -h /tmp/tempo

# Ingestion rate
curl -s 'http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[5m])' | jq -r '.data.result[0].value[1] // "N/A"'

# Query latency
curl -s 'http://host.docker.internal:9090/api/v1/query?query=histogram_quantile(0.99,rate(tempo_querier_query_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1] // "N/A"'
```

### 5.3 Important URLs

| Resource | URL |
|----------|-----|
| Grafana | http://localhost:3001 |
| Tempo API | http://host.docker.internal:3200 |
| Tempo OTLP gRPC | host.docker.internal:4317 |
| Tempo OTLP HTTP | http://host.docker.internal:4318 |
| Prometheus | http://host.docker.internal:9090 |

---

## 6. Post-Incident Actions

### 6.1 Required Post-Incident Steps

1. **Document the Incident**
   - Save incident timeline
   - Record all actions taken
   - Note any data loss

2. **Schedule Post-Mortem**
   - P0: Within 24 hours
   - P1: Within 48 hours
   - P2: Within 1 week

3. **Create Action Items**
   - Prevention measures
   - Monitoring improvements
   - Documentation updates

### 6.2 Post-Mortem Storage

Store post-mortem in: `docs/postmortems/postmortem-tempo-YYYYMMDD-XXX.md`

Template: See [Incident Response Runbook](incident_response.md) Section 5

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-14 | Platform Team | Initial creation for TEMPO-2026-001 |
