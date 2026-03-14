---
title: Tempo Troubleshooting Runbook
category: troubleshooting
severity: standard
estimated_time_to_resolve: 10-30 minutes
last_updated: 2026-03-14
maintainers: platform-team
story_id: TEMPO-2026-001
---

# Tempo Troubleshooting Runbook

## Overview

This runbook provides step-by-step procedures for diagnosing and resolving common issues with Grafana Tempo distributed tracing system.

## Prerequisites

- Access to Docker environment
- Access to Grafana (http://localhost:3001)
- Understanding of Tempo architecture (distributor, ingester, querier, compactor)
- Access to application logs

**Required Tools:**
- `curl` for API testing
- `docker` and `docker-compose` for container management
- `jq` for JSON parsing (optional but recommended)

## 1. Traces Not Appearing

### 1.1 Symptom

- No traces visible in Grafana
- Search returns empty results
- Applications report successful span creation but traces not found

### 1.2 Diagnostic Steps

**Step 1: Verify Tempo is Running**
```bash
# Check container status
docker ps --filter "name=chiseai-tempo" --format "table {{.Names}}\t{{.Status}}"

# Expected: Status should show "Up"
# If not running:
docker logs chiseai-tempo --tail 50
```

**Step 2: Check Ingestion Pipeline**
```bash
# Verify Tempo is accepting traces
curl -s http://host.docker.internal:3200/ready
# Expected: "ready"

# Check distributor metrics
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_distributor_traces_per_total[5m])" | jq '.data.result[].value[1]'
# Expected: Positive value indicating traces are being received
```

**Step 3: Verify Application Sampling**
```bash
# Check if application is sending traces
# For OpenTelemetry applications:
docker logs chiseai-api --tail 100 | grep -i "trace\|span\|otel"

# Look for messages like:
# - "Trace exporter initialized"
# - "Span created"
# - "Exporting spans"
```

**Step 4: Test OTLP Endpoint Connectivity**
```bash
# Test gRPC endpoint (OTLP)
curl -v http://host.docker.internal:4317 2>&1 | grep -i "connected\|refused"

# Test HTTP endpoint (OTLP/HTTP)
curl -v http://host.docker.internal:4318/v1/traces 2>&1 | grep -i "200\|404\|refused"

# If connection refused, check network:
docker network inspect chiseai | grep -A 5 "chiseai-tempo"
```

**Step 5: Check Sampling Configuration**
```bash
# Verify sampling rate is not 0
# In application config:
docker exec chiseai-api env | grep -i OTEL_TRACES_SAMPLER

# Expected: OTEL_TRACES_SAMPLER=parentbased_traceidratio
#           OTEL_TRACES_SAMPLER_ARG=0.1 (or similar, not 0)

# If OTEL_TRACES_SAMPLER_ARG=0, traces are being dropped
```

### 1.3 Resolution Steps

**Resolution A: Restart Tempo Container**
```bash
# If Tempo is not responding
docker restart chiseai-tempo

# Wait for startup
echo "Waiting 30 seconds for Tempo to initialize..."
sleep 30

# Verify
curl -s http://host.docker.internal:3200/ready
# Expected: "ready"
```

**Resolution B: Fix Application Sampling**
```bash
# Set correct sampling rate
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1

# Apply to application
docker restart chiseai-api

# Verify traces are now appearing
echo "Wait 2 minutes for traces to be ingested..."
sleep 120

# Check Grafana for new traces
```

**Resolution C: Fix Network Connectivity**
```bash
# Reconnect container to chiseai network
docker network connect chiseai chiseai-tempo

# Verify connectivity
docker exec chiseai-api curl -s http://chiseai-tempo:3200/ready
# Expected: "ready"
```

**Verification Step:**
```bash
# Generate test traces
for i in {1..10}; do
  curl -s http://localhost:8001/api/v1/health > /dev/null
  sleep 1
done

# Wait 30 seconds for ingestion
sleep 30

# Search for traces
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=10" | jq '.traces | length'
# Expected: > 0 traces found
```

## 2. High Storage Usage

### 2.1 Symptom

- Disk usage alerts for Tempo storage
- Slow query performance
- Compactor falling behind

### 2.2 Diagnostic Steps

**Step 1: Check Current Storage Usage**
```bash
# Check disk usage
docker exec chiseai-tempo df -h /tmp/tempo

# Check block sizes
docker exec chiseai-tempo du -sh /tmp/tempo/blocks/* 2>/dev/null | sort -hr | head -10

# Expected: Usage should be < 80% of allocated space
```

**Step 2: Analyze Ingestion Rate**
```bash
# Check traces per second
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[1h])" | jq '.data.result[].value[1]'

# Check if rate has increased recently
curl -s "http://host.docker.internal:9090/api/v1/query?query=tempo_ingester_traces_created_total" | jq '.data.result[].value[1]'

# Expected: Compare current vs historical to identify spikes
```

**Step 3: Check Compaction Status**
```bash
# Verify compaction is running
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempodb_compaction_objects_written[1h])" | jq '.data.result[].value[1]'

# Expected: Should show positive values (blocks being compacted)

# Check for compaction errors
docker logs chiseai-tempo --tail 200 | grep -i "compaction\|error" | tail -20
```

**Step 4: Review Retention Settings**
```bash
# Check retention configuration
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 3 "block_retention"

# Expected: block_retention should be set (default: 168h = 7 days)
```

**Step 5: Check Sampling Rate**
```bash
# Verify sampling isn't too high
docker exec chiseai-api env | grep OTEL_TRACES_SAMPLER_ARG

# Expected: Should be <= 0.5 (50%)
# If > 0.5, high storage usage is expected
```

### 2.3 Resolution Steps

**Resolution A: Reduce Sampling Rate**
```bash
# Lower sampling rate to reduce ingestion
export OTEL_TRACES_SAMPLER_ARG=0.05  # 5% sampling

# Apply to application
docker restart chiseai-api

# Monitor impact
echo "Monitor ingestion rate for 30 minutes..."
```

**Resolution B: Adjust Retention Period**
```bash
# Edit Tempo configuration
# Note: Requires configuration file edit and restart

# 1. Edit tempo.yaml
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml > /tmp/tempo.yaml

# 2. Modify retention (reduce from 7 days to 3 days)
sed -i 's/block_retention: 168h/block_retention: 72h/' /tmp/tempo.yaml

# 3. Copy back and restart
docker cp /tmp/tempo.yaml chiseai-tempo:/etc/tempo/tempo.yaml
docker restart chiseai-tempo

# Wait for retention to apply (may take hours for old blocks)
```

**Resolution C: Emergency Cleanup (If Disk Full)**
```bash
# WARNING: This will delete traces - use only in emergency

# 1. Stop Tempo
docker stop chiseai-tempo

# 2. Remove old blocks (keep last 2 days)
find /tmp/tempo/blocks -type d -mtime +2 -exec rm -rf {} \;

# 3. Restart Tempo
docker start chiseai-tempo

# 4. Monitor recovery
docker logs chiseai-tempo -f --tail 50
```

**Resolution D: Increase Storage Allocation**
```bash
# If using Docker volumes, increase size
# This requires stopping and recreating the container

docker stop chiseai-tempo
docker rm chiseai-tempo

# Recreate with larger volume (example)
docker run -d \
  --name chiseai-tempo \
  --network chiseai \
  -v tempo-data-new:/tmp/tempo \
  -p 3200:3200 \
  -p 4317:4317 \
  -p 4318:4318 \
  grafana/tempo:latest \
  -config.file=/etc/tempo/tempo.yaml
```

**Verification Step:**
```bash
# Check disk usage after resolution
docker exec chiseai-tempo df -h /tmp/tempo

# Monitor for 24 hours
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[1h])" | jq '.data.result[].value[1]'
```

## 3. Slow Trace Queries

### 3.1 Symptom

- Grafana queries timing out
- "Loading traces" taking > 10 seconds
- Search results slow to return

### 3.2 Diagnostic Steps

**Step 1: Measure Current Query Latency**
```bash
# Check query duration metrics
curl -s "http://host.docker.internal:9090/api/v1/query?query=tempo_querier_query_duration_seconds" | jq '.data.result[] | {quantile: .metric.quantile, value: .value[1]}'

# Expected: p99 < 5 seconds, p95 < 2 seconds
```

**Step 2: Check Time Range**
```bash
# Queries over large time ranges are slower
# Check Grafana: what time range is selected?

# Test specific time ranges:
# Last 1 hour - should be fast
curl -w "\nTime: %{time_total}s\n" -s -o /dev/null \
  "http://host.docker.internal:3200/api/search?q={}&start=$(date -d '1 hour ago' +%s)"

# Last 24 hours - may be slower
curl -w "\nTime: %{time_total}s\n" -s -dev/null \
  "http://host.docker.internal:3200/api/search?q={}&start=$(date -d '24 hours ago' +%s)"
```

**Step 3: Check Resource Usage**
```bash
# Check CPU usage
docker stats chiseai-tempo --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Check for resource throttling
docker inspect chiseai-tempo | grep -A 10 "Memory\|Cpu"
```

**Step 4: Analyze Query Patterns**
```bash
# Check for expensive queries in logs
docker logs chiseai-tempo --tail 500 | grep -i "query\|search" | grep -i "slow\|timeout\|error"

# Look for patterns:
# - Large trace IDs being queried
# - Broad tag searches
# - Very old time ranges
```

**Step 5: Check Backend Storage Performance**
```bash
# If using local storage:
docker exec chiseai-tempo iostat -x 1 5 2>/dev/null || echo "iostat not available"

# Check for I/O wait
docker exec chiseai-tempo top -bn1 | grep -i "cpu\|wa"
```

### 3.3 Resolution Steps

**Resolution A: Optimize Query Time Range**
```bash
# In Grafana:
# 1. Reduce time range from "Last 7 days" to "Last 1 hour"
# 2. Use specific time ranges instead of broad ones
# 3. Add more specific filters (service name, operation)
```

**Resolution B: Add Query Limits**
```bash
# Limit number of results returned
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=20" | jq '.traces | length'

# In Grafana:
# - Set "Limit" to 20-50 traces instead of 100+
```

**Resolution C: Increase Tempo Resources**
```bash
# Restart with more resources
docker update --cpus=2 --memory=4g chiseai-tempo

# Or recreate with resource limits
docker run -d \
  --name chiseai-tempo \
  --network chiseai \
  --cpus=2 \
  --memory=4g \
  -v tempo-data:/tmp/tempo \
  grafana/tempo:latest \
  -config.file=/etc/tempo/tempo.yaml
```

**Resolution D: Enable Query Frontend (If Not Enabled)**
```bash
# Check if query frontend is configured
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 5 "query_frontend"

# If not present, query frontend can help with query performance
# This requires configuration change and restart
```

**Verification Step:**
```bash
# Test query performance
echo "Testing query latency..."
for i in {1..5}; do
  curl -w "%{time_total}\n" -s -o /dev/null \
    "http://host.docker.internal:3200/api/search?q={}&limit=20&start=$(date -d '1 hour ago' +%s)"
done

# Average should be < 2 seconds for recent traces
```

## 4. OTLP Endpoint Issues

### 4.1 Symptom

- Applications cannot connect to Tempo
- "Connection refused" errors in application logs
- Traces not being exported
- Network timeout errors

### 4.2 Diagnostic Steps

**Step 1: Verify Endpoint Accessibility**
```bash
# Test gRPC endpoint
curl -v telnet://host.docker.internal:4317 2>&1 | head -10
# Should show connection established

# Test HTTP endpoint
curl -v http://host.docker.internal:4318/v1/traces 2>&1 | head -20
# Should return 400 (bad request) or 200, not connection refused
```

**Step 2: Check Port Bindings**
```bash
# Verify ports are bound
docker port chiseai-tempo

# Expected:
# 3200/tcp -> 0.0.0.0:3200
# 4317/tcp -> 0.0.0.0:4317
# 4318/tcp -> 0.0.0.0:4318

# Check listening ports
netstat -tlnp | grep -E "3200|4317|4318"
```

**Step 3: Check Network Configuration**
```bash
# Verify containers are on same network
docker network inspect chiseai | jq '.[0].Containers | keys[]'

# Both chiseai-tempo and chiseai-api should be listed

# Test connectivity from application container
docker exec chiseai-api curl -v http://chiseai-tempo:4318/v1/traces 2>&1 | head -10
```

**Step 4: Check Firewall/Routing**
```bash
# Check if ports are blocked
iptables -L | grep -E "4317|4318"

# Check host firewall
sudo ufw status | grep -E "4317|4318"
```

**Step 5: Verify OTLP Configuration in Tempo**
```bash
# Check if OTLP receiver is enabled
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 10 "distributor"

# Should show:
# receiver:
#   otlp:
#     protocols:
#       grpc:
#         endpoint: 0.0.0.0:4317
#       http:
#         endpoint: 0.0.0.0:4318
```

### 4.3 Resolution Steps

**Resolution A: Restart Tempo with Correct Ports**
```bash
# Stop and remove
docker stop chiseai-tempo
docker rm chiseai-tempo

# Recreate with port mappings
docker run -d \
  --name chiseai-tempo \
  --network chiseai \
  -p 3200:3200 \
  -p 4317:4317 \
  -p 4318:4318 \
  -v tempo-data:/tmp/tempo \
  -v /path/to/tempo.yaml:/etc/tempo/tempo.yaml \
  grafana/tempo:latest \
  -config.file=/etc/tempo/tempo.yaml
```

**Resolution B: Fix Network Connectivity**
```bash
# Disconnect and reconnect to network
docker network disconnect chiseai chiseai-tempo
docker network connect chiseai chiseai-tempo

# Verify
docker network inspect chiseai | grep chiseai-tempo
```

**Resolution C: Update Application Configuration**
```bash
# Ensure application points to correct endpoint
# In application config or environment:

export OTEL_EXPORTER_OTLP_ENDPOINT=http://chiseai-tempo:4317
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://chiseai-tempo:4317

# For HTTP instead of gRPC:
export OTEL_EXPORTER_OTLP_ENDPOINT=http://chiseai-tempo:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

# Restart application
docker restart chiseai-api
```

**Resolution D: Open Firewall Ports**
```bash
# If using UFW
sudo ufw allow 4317/tcp
sudo ufw allow 4318/tcp
sudo ufw reload

# If using iptables
sudo iptables -A INPUT -p tcp --dport 4317 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 4318 -j ACCEPT
```

**Verification Step:**
```bash
# Test connectivity from application
docker exec chiseai-api curl -s http://chiseai-tempo:4318/v1/traces -X POST \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[]}'

# Should return 200 OK (empty spans accepted)

# Generate test trace and verify ingestion
curl http://localhost:8001/api/v1/health
sleep 5
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=5" | jq '.traces | length'
# Expected: > 0
```

## 5. Additional Diagnostic Commands

### 5.1 Full Health Check Script
```bash
#!/bin/bash
echo "=== Tempo Health Check ==="
echo ""
echo "1. Container Status:"
docker ps --filter "name=chiseai-tempo" --format "{{.Names}}: {{.Status}}"
echo ""
echo "2. Readiness Check:"
curl -s http://host.docker.internal:3200/ready
echo ""
echo "3. Component Status:"
curl -s http://host.docker.internal:3200/status | jq -r '.components | to_entries | .[] | "\(.key): \(.value)"'
echo ""
echo "4. Storage Usage:"
docker exec chiseai-tempo df -h /tmp/tempo 2>/dev/null || echo "N/A"
echo ""
echo "5. Recent Logs (last 5 lines):"
docker logs chiseai-tempo --tail 5 2>&1
echo ""
echo "=== End Health Check ==="
```

### 5.2 Quick Metrics Check
```bash
# All key metrics in one command
echo "Traces/sec: $(curl -s 'http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[5m])' | jq -r '.data.result[0].value[1] // 0')"
echo "Query latency (p99): $(curl -s 'http://host.docker.internal:9090/api/v1/query?query=histogram_quantile(0.99,rate(tempo_querier_query_duration_seconds_bucket[5m]))' | jq -r '.data.result[0].value[1] // 0')s"
echo "Active blocks: $(curl -s 'http://host.docker.internal:9090/api/v1/query?query=tempodb_blocklist_length' | jq -r '.data.result[0].value[1] // 0')"
```

## Related Runbooks

- [Tempo Operations](tempo-operations.md) - Day-to-day procedures
- [Tempo Incident Response](tempo-incident-response.md) - Emergency procedures
- [Redis Connectivity](redis-connectivity-runbook.md) - Redis troubleshooting
- [Incident Response](incident_response.md) - General incident management

## Support Contacts

- **Platform Team**: #platform-ops Slack channel
- **Observability Team**: #observability Slack channel
- **On-Call Engineer**: PagerDuty rotation

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-14 | Platform Team | Initial creation for TEMPO-2026-001 |
