---
title: Tempo Operations Runbook
category: operations
severity: standard
estimated_time_to_resolve: 5-15 minutes
last_updated: 2026-03-14
maintainers: platform-team
story_id: TEMPO-2026-001
---

# Tempo Operations Runbook

## Overview

This runbook covers day-to-day operational procedures for Grafana Tempo, the distributed tracing backend used by ChiseAI. It includes procedures for searching traces, adjusting sampling rates, checking health status, and viewing retention metrics.

## Prerequisites

- Access to Grafana UI (http://localhost:3001)
- Docker environment with `chiseai` network
- Tempo container running on `chiseai` network
- Grafana with Tempo datasource configured

**Required Permissions:**
- Grafana: Viewer or higher
- Docker: Read access to chiseai containers
- Tempo: Query access

## 1. Searching for Traces in Grafana

### 1.1 Access the Tempo Datasource

**Step 1: Navigate to Grafana Explore**
1. Open Grafana in your browser: http://localhost:3001
2. Click **Explore** in the left sidebar (compass icon)
3. Select **Tempo** from the datasource dropdown at the top

**Step 2: Select Query Type**

Choose one of these query methods:

**Method A: Search by Service Name**
```
1. Select "Search" query type
2. Choose service name from dropdown (e.g., "chiseai-api", "chiseai-executor")
3. Optionally add:
   - Operation name (e.g., "GET /api/v1/health")
   - Tags (e.g., "http.status_code=200")
   - Time range (default: last 1 hour)
4. Click "Run Query"
```

**Method B: Search by Trace ID**
```
1. Select "TraceID" query type
2. Enter the trace ID (e.g., "abc123def456789")
3. Click "Run Query"
```

**Method C: Search by Tags**
```
1. Select "Search" query type
2. Leave service name empty (all services)
3. Add tag filters:
   - Key: http.method, Value: GET
   - Key: http.status_code, Value: 500
4. Adjust time range if needed
5. Click "Run Query"
```

### 1.2 Interpreting Trace Results

**Trace List View:**
| Column | Description |
|--------|-------------|
| Trace ID | Unique identifier for the trace |
| Started At | When the trace began |
| Duration | Total trace duration |
| Span Count | Number of spans in the trace |
| Error | Indicates if any span has an error |

**Trace Detail View:**
- **Timeline:** Visual representation of span timing
- **Spans:** Individual operations within the trace
- **Tags:** Key-value metadata for each span
- **Logs:** Log messages associated with spans

**Verification Step:**
```bash
# Verify Tempo is responding to queries
curl -s "http://host.docker.internal:3200/api/search?q={}&limit=10" | jq '.traces | length'
# Expected: Returns number of traces found (0 or more)
```

### 1.3 Advanced Search Techniques

**Search by Duration:**
```
1. In Search query type, expand "Advanced Options"
2. Set Min Duration: 100ms
3. Set Max Duration: 5s
4. Click "Run Query"
```

**Search by Time Range:**
```
1. Use the time picker in top right of Grafana
2. Select "Last 5 minutes" for recent traces
3. Or select "Custom range" for specific period
```

## 2. Adjusting Sampling Rates

### 2.1 View Current Sampling Configuration

**Step 1: Check Tempo Configuration**
```bash
# View current sampling configuration
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 10 "distributor"
```

**Step 2: Check Application Sampling**
```bash
# For applications using OpenTelemetry
curl -s http://localhost:8001/api/v1/config/tracing | jq '.sampling_rate'
# Expected: Value between 0.0 and 1.0 (e.g., 0.1 = 10%)
```

### 2.2 Adjust Sampling Rate

**Option A: Adjust in Application Config**

1. Edit application configuration:
```bash
# Edit the application config file
vi config/tracing.yaml
```

2. Modify sampling rate:
```yaml
# config/tracing.yaml
tracing:
  enabled: true
  sampler:
    type: probabilistic
    param: 0.1  # Change this value (0.0 to 1.0)
  tempo:
    endpoint: http://chiseai-tempo:4317
```

3. Apply changes:
```bash
# Restart the application to apply
docker restart chiseai-api
```

**Option B: Adjust via Environment Variable**
```bash
# Set sampling rate via environment
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1

# Apply to running container
docker exec chiseai-api env OTEL_TRACES_SAMPLER_ARG=0.5 ./restart-tracing.sh
```

### 2.3 Verify Sampling Rate Change

**Step 1: Generate Test Traces**
```bash
# Make several API calls to generate traces
for i in {1..100}; do
  curl -s http://localhost:8001/api/v1/health > /dev/null
done
```

**Step 2: Check Trace Volume**
```bash
# Count traces received in last 5 minutes
curl -s "http://host.docker.internal:3200/api/search?q={}&start=$(date -d '5 minutes ago' +%s)&end=$(date +%s)" | jq '.traces | length'

# Expected: Approximately (requests × sampling_rate) traces
# Example: 100 requests × 0.1 = ~10 traces
```

**Rollback Procedure:**
```bash
# If trace volume is too low or too high, revert to previous rate
export OTEL_TRACES_SAMPLER_ARG=0.1  # Revert to 10%
docker restart chiseai-api
```

## 3. Checking Tempo Health and Status

### 3.1 Container Health Check

**Step 1: Check Container Status**
```bash
# Check if Tempo container is running
docker ps --filter "name=chiseai-tempo" --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"

# Expected: Up and healthy
```

**Step 2: Check Container Logs**
```bash
# View recent logs
docker logs --tail 50 chiseai-tempo

# Watch logs in real-time
docker logs -f --tail 20 chiseai-tempo
```

### 3.2 Tempo API Health Check

**Step 1: Check Readiness**
```bash
# Check if Tempo is ready to accept requests
curl -s http://host.docker.internal:3200/ready

# Expected: "ready"
```

**Step 2: Check Overall Health**
```bash
# Check all component health
curl -s http://host.docker.internal:3200/status | jq '.'

# Expected: All components show "Healthy" status
```

**Step 3: Check Component Status**
```bash
# Check individual component health
curl -s http://host.docker.internal:3200/status | jq '.components'

# Expected output:
# {
#   "distributor": "Healthy",
#   "ingester": "Healthy",
#   "querier": "Healthy",
#   "compactor": "Healthy"
# }
```

### 3.3 Metrics Health Check

**Step 1: Check Ingestion Rate**
```bash
# View traces per second (via Prometheus)
curl -s "http://host.docker.internal:9090/api/v1/query?query=rate(tempo_ingester_traces_created_total[5m])" | jq '.data.result[].value[1]'

# Expected: Positive value indicating traces/second
```

**Step 2: Check Query Performance**
```bash
# Check query latency
curl -s "http://host.docker.internal:9090/api/v1/query?query=tempo_querier_query_duration_seconds" | jq '.data.result[] | {metric: .metric, value: .value[1]}'

# Expected: Values typically < 1 second for recent traces
```

**Step 3: Check Storage Metrics**
```bash
# Check storage backend health
curl -s "http://host.docker.internal:9090/api/v1/query?query=tempodb_compaction_objects_written" | jq '.data.result[].value[1]'

# Expected: Positive values indicating compaction is working
```

## 4. Viewing Trace Retention Metrics

### 4.1 Check Retention Configuration

**Step 1: View Retention Settings**
```bash
# Check configured retention period
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep -A 5 "compactor"

# Expected output:
# compactor:
#   compaction:
#     block_retention: 168h  # 7 days default
```

**Step 2: Check Current Block Retention**
```bash
# View block metadata
curl -s http://host.docker.internal:3200/api/status | jq '.tenantStats'

# Expected: Shows current block count and size
```

### 4.2 Monitor Retention Metrics in Grafana

**Step 1: Access Tempo Dashboard**
1. Navigate to: Grafana > Dashboards > Tempo
2. Or go directly to: http://localhost:3001/d/tempo-overview

**Step 2: View Key Retention Metrics**

| Panel | Description | Normal Range |
|-------|-------------|--------------|
| Block Count | Number of blocks in storage | Varies by ingestion rate |
| Block Size | Average block size | 100MB - 2GB |
| Retention Age | Oldest retained block | < configured retention |
| Compaction Rate | Blocks compacted per hour | Positive value |

**Step 3: Check Storage Usage**
```bash
# Check disk usage for Tempo storage
docker exec chiseai-tempo df -h /tmp/tempo

# Expected: Usage should be stable or slowly growing
```

### 4.3 Verify Retention Policy Compliance

**Step 1: Calculate Retention Compliance**
```bash
# Get oldest block timestamp
curl -s http://host.docker.internal:3200/api/status | jq '.tenantStats.oldestBlock'

# Calculate age in days
OLDEST=$(curl -s http://host.docker.internal:3200/api/status | jq '.tenantStats.oldestBlock')
NOW=$(date +%s)
AGE_DAYS=$(( (NOW - OLDEST) / 86400 ))
echo "Oldest block is $AGE_DAYS days old"

# Expected: Less than configured retention (default 7 days)
```

**Step 2: Check for Retention Errors**
```bash
# Look for compaction/retention errors
docker logs chiseai-tempo --tail 100 | grep -i "retention\|compaction\|error"

# Expected: No errors related to retention
```

## 5. Daily Operational Checklist

### Morning Checks (9:00 AM)

- [ ] **Container Status:** `docker ps | grep chiseai-tempo`
- [ ] **Health Check:** `curl http://host.docker.internal:3200/ready`
- [ ] **Ingestion Rate:** Check Grafana > Tempo > Ingestion Rate panel
- [ ] **Error Rate:** Check logs for errors in last 24h
- [ ] **Storage Usage:** Verify disk usage is stable

### Mid-Day Checks (1:00 PM)

- [ ] **Query Performance:** Check Grafana for query latency
- [ ] **Active Traces:** Verify recent traces are searchable
- [ ] **Compaction Status:** Check blocks are being compacted

### End-of-Day Checks (5:00 PM)

- [ ] **Daily Trace Volume:** Record traces ingested today
- [ ] **Retention Compliance:** Verify oldest block < 7 days
- [ ] **Error Summary:** Review any errors encountered
- [ ] **Metrics Snapshot:** Export key metrics to logs

## 6. Common Metrics Reference

### Key Tempo Metrics

| Metric | PromQL Query | Normal Range |
|--------|--------------|--------------|
| Traces/sec | `rate(tempo_ingester_traces_created_total[5m])` | > 0 |
| Spans/sec | `rate(tempo_ingester_spans_total[5m])` | > 0 |
| Query latency | `tempo_querier_query_duration_seconds` | < 1s |
| Active blocks | `tempodb_blocklist_length` | Varies |
| Compaction rate | `rate(tempodb_compaction_objects_written[1h])` | > 0 |

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Traces/sec | < 1 for > 10min | 0 for > 5min |
| Query latency | > 2s | > 5s |
| Disk usage | > 80% | > 90% |
| Errors | > 10/min | > 50/min |

## Troubleshooting Quick Reference

**Traces Not Appearing:**
```bash
# Check ingestion
curl http://host.docker.internal:3200/ready
# Check sampling rate in application
# Verify OTLP endpoint connectivity
```

**Slow Queries:**
```bash
# Check query latency
curl http://host.docker.internal:9090/api/v1/query?query=tempo_querier_query_duration_seconds
# Adjust time range to be more specific
```

**High Storage Usage:**
```bash
# Check retention settings
docker exec chiseai-tempo cat /etc/tempo/tempo.yaml | grep block_retention
# Adjust sampling rate if needed
# Verify compaction is running
```

## Related Runbooks

- [Tempo Troubleshooting](tempo-troubleshooting.md) - Common issues and resolutions
- [Tempo Incident Response](tempo-incident-response.md) - Emergency procedures
- [Incident Response](incident_response.md) - General incident management
- [Monitoring Setup](monitoring-setup.md) - Grafana configuration

## Support Contacts

- **Platform Team**: #platform-ops Slack channel
- **Observability Team**: #observability Slack channel
- **On-Call Engineer**: PagerDuty rotation

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-14 | Platform Team | Initial creation for TEMPO-2026-001 |
