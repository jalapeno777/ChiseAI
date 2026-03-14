# Tempo Alerting Runbook

## Overview

This runbook provides guidance for responding to Tempo (distributed tracing) alerts. Tempo is the tracing backend that stores and queries distributed traces for ChiseAI services.

**Story**: TEMPO-2026-001  
**Dashboard**: [Tempo SLO Alerts](/d/tempo-slo-alerts)  
**Trace Explorer**: [Trace Exploration](/d/tempo-trace-exploration)

---

## Alert Summary

| Alert | Threshold | Severity | Description |
|-------|-----------|----------|-------------|
| Trace Ingestion Rate | < 1000 spans/sec | Warning | Trace data ingestion has dropped below acceptable levels |
| Query Latency | > 2 seconds (p99) | Warning | Trace queries are taking too long to respond |
| Storage Utilization | > 80% | Critical | Tempo storage is nearing capacity |
| Ingest Error Rate | > 1% | Warning | Too many trace ingests are failing |

---

## Alert Details and Response Procedures

### 1. Trace Ingestion Rate Alert

**Alert Name**: `TempoTraceIngestionLow`  
**Threshold**: Ingestion rate < 1000 spans/second for 5 minutes  
**Severity**: Warning

#### What This Alert Means

Trace data ingestion from services has dropped below the acceptable threshold. This could indicate:
- Tempo ingester pods are down or restarting
- Network connectivity issues between services and Tempo
- Services have stopped sending trace data
- Tempo distributor is overloaded

#### How to Respond

**Immediate Actions** (within 5 minutes):

1. **Check Tempo pod status**:
   ```bash
   kubectl get pods -n observability | grep tempo
   ```

2. **Check distributor logs** for errors:
   ```bash
   kubectl logs -n observability deployment/tempo-distributor --tail=100
   ```

3. **Verify service connectivity**:
   ```bash
   # Check if services can reach Tempo
   kubectl exec -it <service-pod> -- curl -v http://tempo:4317
   ```

**Investigation Steps**:

1. **Check span metrics**:
   - Navigate to [Tempo SLO Alerts dashboard](/d/tempo-slo-alerts)
   - Look at "Trace Ingestion Rate Trend" panel
   - Identify when the drop started

2. **Check for errors in services**:
   ```bash
   # Look for OpenTelemetry errors
   kubectl logs -n chiseai deployment/chiseai-api | grep -i "opentelemetry\|trace"
   ```

3. **Verify ingester health**:
   ```bash
   kubectl logs -n observability deployment/tempo-ingester --tail=200 | grep -i error
   ```

**Resolution**:

- If ingesters are down: Restart them or scale up
- If services stopped sending traces: Check service configuration and restart
- If distributor is overloaded: Scale up distributor replicas
- If storage is full: See "Storage Utilization Alert" section

**Escalation**: Escalate to infrastructure team if pods are healthy but ingestion remains low.

---

### 2. Query Latency Alert

**Alert Name**: `TempoQueryLatencyHigh`  
**Threshold**: p99 latency > 2 seconds for 5 minutes  
**Severity**: Warning

#### What This Alert Means

Trace queries are taking longer than acceptable to complete. This affects:
- User experience in trace exploration
- Dashboard loading times
- Alert evaluation latency

Possible causes:
- High query volume or complex queries
- Compactor is behind on compaction
- Index is not optimized
- Insufficient querier resources
- Large time range queries

#### How to Respond

**Immediate Actions**:

1. **Check current query load**:
   - Navigate to [Tempo SLO Alerts dashboard](/d/tempo-slo-alerts)
   - Review "Query Rate by Type" panel
   - Identify unusual query patterns

2. **Check querier resource usage**:
   ```bash
   kubectl top pods -n observability | grep tempo-querier
   ```

3. **Check compactor status**:
   ```bash
   kubectl logs -n observability deployment/tempo-compactor --tail=100
   ```

**Investigation Steps**:

1. **Analyze slow queries**:
   ```bash
   # Check querier logs for slow queries
   kubectl logs -n observability deployment/tempo-querier | grep -i "slow\|timeout"
   ```

2. **Check blocklist size** (too many blocks = slower queries):
   ```bash
   # In Grafana, query: tempodb_blocklist_length
   ```

3. **Verify cache hit rates**:
   - Check if caching layer (if enabled) is working

**Resolution**:

- Scale up querier replicas if CPU/memory is saturated
- Reduce query time ranges in dashboards
- Wait for compactor to catch up if behind
- Enable or tune query caching
- Consider adding query limits for large time ranges

**Escalation**: Escalate if latency persists after scaling and no clear cause is found.

---

### 3. Storage Utilization Alert

**Alert Name**: `TempoStorageCritical`  
**Threshold**: Storage utilization > 80% for 10 minutes  
**Severity**: Critical

#### What This Alert Means

Tempo is running out of storage space. If storage reaches 100%:
- New traces cannot be ingested
- Compaction will fail
- Query performance degrades
- Risk of data loss

#### How to Respond

**Immediate Actions** (treat as P1 incident):

1. **Check current storage**:
   - Navigate to [Tempo SLO Alerts dashboard](/d/tempo-slo-alerts)
   - Review "Storage Utilization Trend" and "Storage by Component" panels

2. **Check retention settings**:
   ```bash
   # View Tempo config
   kubectl get configmap -n observability tempo-config -o yaml | grep -i retention
   ```

3. **Check compaction status**:
   ```bash
   kubectl logs -n observability deployment/tempo-compactor --tail=50
   ```

**Short-term Mitigation** (if storage > 90%):

1. **Reduce retention temporarily**:
   ```yaml
   # Edit tempo config
   compactor:
     compaction:
       block_retention: 24h  # Reduce from current value
   ```

2. **Force compaction** (if not running):
   ```bash
   kubectl rollout restart deployment/tempo-compactor -n observability
   ```

3. **Scale up storage** (if using PVCs):
   ```bash
   # Expand PVC
   kubectl patch pvc tempo-data -n observability -p '{"spec":{"resources":{"requests":{"storage":"100Gi"}}}}'
   ```

**Long-term Resolution**:

- Adjust retention policy to sustainable levels
- Add storage capacity
- Review trace sampling rates (reduce if too high)
- Enable compression if not already enabled

**Escalation**: Page on-call infrastructure engineer immediately if storage > 95%.

---

### 4. Ingest Error Rate Alert

**Alert Name**: `TempoIngestErrorsHigh`  
**Threshold**: Error rate > 1% for 5 minutes  
**Severity**: Warning

#### What This Alert Means

More than 1% of trace ingests are failing. This results in:
- Incomplete trace data
- Gaps in distributed tracing
- Potential service issues

Common causes:
- Rate limiting on distributors
- Ingester overload
- Invalid trace data format
- Network timeouts
- Storage issues

#### How to Respond

**Immediate Actions**:

1. **Check error breakdown**:
   - Navigate to [Tempo SLO Alerts dashboard](/d/tempo-slo-alerts)
   - Review "Ingest Error Rate Trend" and "Error Breakdown by Type" panels

2. **Check distributor logs**:
   ```bash
   kubectl logs -n observability deployment/tempo-distributor --tail=200 | grep -i "error\|fail"
   ```

3. **Check ingester status**:
   ```bash
   kubectl get pods -n observability | grep tempo-ingester
   kubectl logs -n observability deployment/tempo-ingester --tail=100
   ```

**Investigation Steps**:

1. **Identify error types**:
   - `rate_limited`: Too many spans from a service
   - `invalid_data`: Malformed trace data
   - `timeout`: Network or processing timeouts
   - `full`: Ingester buffers are full

2. **Check service traces**:
   ```bash
   # Look for errors in service logs
   kubectl logs -n chiseai deployment/chiseai-api | grep -i "trace.*error"
   ```

3. **Verify OTLP endpoint**:
   ```bash
   # Test connectivity
   telnet tempo-distributor 4317
   ```

**Resolution**:

- **Rate limiting**: Increase distributor rate limits or reduce trace volume
- **Invalid data**: Fix service instrumentation
- **Timeouts**: Scale up ingesters or check network
- **Full buffers**: Scale up ingesters or reduce ingestion rate

**Escalation**: Escalate if error rate > 10% or if cause is unclear.

---

## Where to Find Alert History

### Grafana Alerting

1. **Navigate to**: Alerting → Alert Rules
2. **Filter by**: Tag = "tempo" or "TEMPO-2026-001"
3. **View**: State history for each alert rule

### Dashboard Annotations

- [Tempo SLO Alerts dashboard](/d/tempo-slo-alerts) shows alert annotations on panels
- Look for vertical lines indicating when alerts fired/resolved

### Logs

```bash
# Check Tempo component logs
kubectl logs -n observability deployment/tempo-distributor --since=1h
kubectl logs -n observability deployment/tempo-ingester --since=1h
kubectl logs -n observability deployment/tempo-querier --since=1h

# Search for specific errors
kubectl logs -n observability -l app.kubernetes.io/name=tempo --since=1h | grep -i error
```

### Metrics

Query in Grafana/InfluxDB:
```promql
# Alert evaluation history
ALERTS{alertname=~"Tempo.*"}

# Ingestion rate
sum(rate(traces_spanmetrics_latency_count{}[5m]))

# Query latency
histogram_quantile(0.99, sum(rate(traces_query_duration_seconds_bucket{}[5m])) by (le))

# Storage usage
(tempodb_blocklist_total_bytes / tempodb_retention_limit_bytes) * 100

# Error rate
sum(rate(tempo_distributor_ingester_appends_failures_total{}[5m])) / sum(rate(tempo_distributor_ingester_appends_total{}[5m])) * 100
```

---

## Related Resources

- **Tempo Documentation**: https://grafana.com/docs/tempo/latest/
- **TraceQL Query Guide**: https://grafana.com/docs/tempo/latest/traceql/
- **Architecture Diagram**: See `docs/architecture/tracing.md`
- **Deployment Config**: `infrastructure/terraform/tempo.tf`

---

## Escalation Contacts

| Situation | Contact | Response Time |
|-----------|---------|---------------|
| Storage > 95% | On-call infra | Immediate |
| Ingestion down > 15 min | On-call infra | 15 min |
| Unknown cause | Platform team | 30 min |

---

## Post-Incident Actions

After resolving any alert:

1. **Document** the incident in the incident log
2. **Update** this runbook if new patterns emerge
3. **Review** alert thresholds if false positives occur
4. **Tune** sampling rates if trace volume is too high
5. **Update** dashboards if new metrics become relevant

---

## Quick Reference Commands

```bash
# Get all Tempo pods
kubectl get pods -n observability | grep tempo

# View Tempo config
kubectl get configmap -n observability tempo-config -o yaml

# Restart Tempo components
kubectl rollout restart deployment/tempo-distributor -n observability
kubectl rollout restart deployment/tempo-ingester -n observability
kubectl rollout restart deployment/tempo-querier -n observability
kubectl rollout restart deployment/tempo-compactor -n observability

# Check storage usage
kubectl exec -it tempo-ingester-0 -n observability -- df -h

# Port-forward for debugging
kubectl port-forward -n observability svc/tempo-query-frontend 16686:16686
```

---

*Last Updated: 2026-03-14*  
*Owner: Platform Team*  
*Story: TEMPO-2026-001*
