# ChiseAI Observability Infrastructure Audit

**Audit Date:** 2026-03-13  
**Auditor:** senior-dev  
**Story ID:** TEMPO-2026-001  
**Sprint:** TEMPO-2026-001 (Grafana Tempo + OpenTelemetry Integration)

---

## Executive Summary

The ChiseAI platform currently has a **metrics-centric observability stack** with Grafana for visualization and InfluxDB for time-series data storage. However, **distributed tracing is completely absent**, creating significant gaps in request flow visibility, latency analysis, and service dependency mapping. This audit identifies critical gaps that the Tempo integration will address.

### Current State at a Glance

| Component | Status | Technology | Gaps |
|-----------|--------|------------|------|
| Metrics | ✅ Operational | InfluxDB + Grafana | Limited custom app metrics |
| Logging | ⚠️ Basic | Python stdlib logging | No centralized log aggregation |
| Tracing | ❌ Missing | None | No distributed tracing |
| Alerting | ⚠️ Partial | Grafana alerts | Limited trace-derived alerts |
| Dashboards | ✅ Operational | 15+ dashboards | No trace visualization |

---

## Detailed Infrastructure Inventory

### 1. Metrics Infrastructure

#### 1.1 Time-Series Database: InfluxDB 2.x

**Deployment:**
- Container: `chiseai-influxdb`
- Image: `influxdb:2`
- Network: `chiseai` (172.27.0.0/16)
- Port: `18087:18087`
- Status: ✅ Healthy (Up 2 weeks)

**Configuration:**
- Organization: `chiseai`
- Default Bucket: `chiseai`
- Retention: Infinite (`everySeconds: 0`)
- System Buckets: `_monitoring` (7-day retention)

**Data Sources:**
| Source | Measurement | Frequency | Volume |
|--------|-------------|-----------|--------|
| OHLCV Ingestion | market_data | 60s | High |
| Data Quality Monitor | data_quality | 60s | Medium |
| Datasource Health | datasource_health | 30s | Low |
| Daily Summary | daily_metrics | Daily | Low |

**Storage Estimate:**
- Current bucket count: 2 (chiseai, _monitoring)
- Retention policy: Infinite for main data
- No compression or downsampling configured

#### 1.2 Visualization: Grafana 10.4.2

**Deployment:**
- Container: `chiseai-grafana`
- Image: `grafana/grafana:10.4.2`
- Network: `chiseai`
- Port: `3001:3001`
- Status: ✅ Healthy (commit: 701c851)

**Datasources:**
- InfluxDB (Flux) - Default datasource
- URL: `http://chiseai-influxdb:18087`

**Dashboards (15+ identified):**
| Dashboard | Purpose | Location |
|-----------|---------|----------|
| data-freshness.json | Data freshness monitoring | provisioning/dashboards/ |
| backtest-kpis.json | Backtest performance KPIs | provisioning/dashboards/ |
| paper-execution.json | Paper trading execution | provisioning/dashboards/ |
| live-execution.json | Live trading execution | provisioning/dashboards/ |
| datasource-health.json | Datasource health status | provisioning/dashboards/ |
| autonomous_control_plane.json | ACP monitoring | provisioning/dashboards/ |
| training_metrics.json | Model training metrics | dashboards/ |
| paper_trading_monitoring.json | Paper trading overview | dashboards/ |
| governance_metrics.json | Governance metrics | dashboards/ |
| risk-management.json | Risk metrics | dashboards/ |
| unified-health.json | System health overview | dashboards/ |
| calibration_monitoring.json | Model calibration | dashboards/ |
| signal-analytics.json | Signal generation analytics | dashboards/ |
| trading-overview.json | Trading overview | dashboards/ |
| system-health.json | System health | dashboards/ |

**Terraform Management:**
- Dashboards provisioned via `infrastructure/terraform/dashboards.tf`
- Grafana folder: "ChiseAI"
- Auto-provisioning from JSON files

### 2. Logging Infrastructure

#### 2.1 Application Logging

**Current State:**
- Framework: Python stdlib `logging`
- Pattern: `logging.getLogger(__name__)`
- No structured logging (JSON)
- No centralized aggregation

**Coverage Areas:**
| Module | Logging Level | Notes |
|--------|--------------|-------|
| src/api/cache/ | DEBUG/INFO | Cache operations |
| src/api/health_router.py | INFO/ERROR | Health checks |
| src/api/ece_router.py | EXCEPTION | Error tracking |

**Log Destinations:**
- Container stdout/stderr only
- No persistence beyond container lifecycle
- No log rotation or archival

#### 2.2 Container Logs

**Services with Logging:**
| Container | Log Strategy | Persistence |
|-----------|--------------|-------------|
| chiseai-api-final | stdout | None |
| chiseai-kimi-adapter | stdout | None |
| chiseai-brain-scheduler | stdout | None |
| chiseai-data-quality-monitor | stdout | None |
| chiseai-daily-summary | File (/app/logs) | Volume mounted |

**Gap:** No centralized log aggregation (Loki, ELK, etc.)

### 3. Tracing Infrastructure

#### 3.1 Current State: COMPLETELY ABSENT

**No distributed tracing exists in the platform:**
- No OpenTelemetry SDK
- No Jaeger/Tempo/Zipkin deployment
- No trace context propagation
- No span creation or export

**Impact Areas:**
| Service | Impact | Criticality |
|---------|--------|-------------|
| chiseai-api-final | Cannot trace request flows | HIGH |
| chiseai-kimi-adapter | Cannot trace LLM calls | HIGH |
| chiseai-brain-scheduler | Cannot trace job execution | MEDIUM |
| chiseai-ohlcv-ingestion | Cannot trace data pipeline | MEDIUM |

### 4. Alerting Infrastructure

#### 4.1 Grafana Alerts

**Current State:**
- Alert rules defined in JSON files
- Location: `infrastructure/grafana/alerts/`

**Existing Alerts:**
| Alert | Purpose | Status |
|-------|---------|--------|
| datasource-health.json | Datasource health monitoring | Active |
| tempmemory_ingestion.json | TempMemory ingestion alerts | Active |

**Gap:** No trace-derived alerts (p99 latency, error rates, etc.)

### 5. Service Inventory

#### 5.1 Core Services (Require Tracing)

| Service | Container | Port | Language | Instrumentation |
|---------|-----------|------|----------|-----------------|
| ChiseAI API | chiseai-api-final | 8001 | Python | None |
| Kimi Adapter | chiseai-kimi-adapter | 8002 | Python | None |
| Brain Scheduler | chiseai-brain-scheduler | - | Python | None |
| OHLCV Ingestion | chiseai-ohlcv-ingestion | - | Python | None |
| Data Quality Monitor | chiseai-data-quality-monitor | - | Python | None |
| Daily Summary | chiseai-daily-summary | - | Python | None |
| Datasource Health | chiseai-datasource-health-monitor | - | Python | None |

#### 5.2 Infrastructure Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Grafana | chiseai-grafana | 3001 | Visualization |
| InfluxDB | chiseai-influxdb | 18087 | Time-series DB |
| Redis | chiseai-redis | 6380 | Cache/State |
| PostgreSQL | chiseai-postgres | 5434 | Primary DB |
| Qdrant | chiseai-qdrant | 6334 | Vector DB |

### 6. Network Configuration

**Docker Network: `chiseai`**
- Subnet: `172.27.0.0/16`
- Gateway: `172.27.0.1`
- All services connected

**Port Allocations:**
| Service | Host Port | Container Port |
|---------|-----------|----------------|
| chiseai-redis | 6380 | 6380 |
| chiseai-postgres | 5434 | 5434 |
| chiseai-influxdb | 18087 | 18087 |
| chiseai-grafana | 3001 | 3001 |
| chiseai-api-final | 8001 | 8000 |
| chiseai-qdrant | 6334 | 6334 |
| chise-dashboard | 8502 | 8501 |

**Tempo Port Requirements (Planned):**
| Port | Protocol | Purpose |
|------|----------|---------|
| 3200 | HTTP | Tempo API/Query |
| 4317 | gRPC | OTLP Ingestion |
| 4318 | HTTP | OTLP Ingestion |

---

## Gap Analysis

### P0 (Critical) - Must Fix for Tempo Integration

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| **No distributed tracing** | Cannot trace requests across services | High | P0 |
| **No OpenTelemetry SDK** | No instrumentation framework | Medium | P0 |
| **No Tempo deployment** | No trace storage backend | Medium | P0 |
| **No trace context propagation** | Cannot link spans across services | Medium | P0 |

### P1 (High) - Should Fix for Production Readiness

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| **No centralized logging** | Cannot correlate logs with traces | Medium | P1 |
| **No trace-derived alerts** | Missing latency/error alerts | Low | P1 |
| **No service dependency map** | Cannot visualize service topology | Low | P1 |
| **No custom application metrics** | Limited business metrics | Medium | P1 |

### P2 (Medium) - Nice to Have

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| **No log-to-trace correlation** | Hard to debug issues | Medium | P2 |
| **No tail-based sampling** | May miss error traces | Low | P2 |
| **No trace retention policies** | Storage cost uncontrolled | Low | P2 |
| **No performance benchmarks** | Unknown tracing overhead | Low | P2 |

---

## Storage Requirements Calculation

### Tempo Storage Estimation

**Assumptions:**
- Span size: ~500 bytes (average)
- Request rate: 100 req/sec (API + internal)
- Spans per request: 5 (average)
- Sampling rate: 10% (head-based)
- Retention: 7 days

**Calculation:**
```
Spans per second = 100 req/sec × 5 spans/req × 10% sampling = 50 spans/sec
Bytes per second = 50 spans/sec × 500 bytes = 25,000 bytes/sec (24.4 KB/sec)
Daily volume = 24.4 KB/sec × 86,400 sec = 2.05 GB/day
7-day retention = 2.05 GB × 7 = 14.35 GB
With overhead (index, WAL): 14.35 GB × 1.5 = ~21.5 GB
```

**Storage Recommendation:**
- Minimum: 25 GB for 7-day retention
- Recommended: 50 GB (allows growth + 14-day retention)
- Growth factor: 2x annually

### Throughput Estimates

| Scenario | Spans/sec | Storage/day | Storage/7d |
|----------|-----------|-------------|------------|
| Conservative (5% sampling) | 25 | 1 GB | 7 GB |
**Normal (10% sampling)** | **50** | **2 GB** | **14 GB** |
| Aggressive (25% sampling) | 125 | 5 GB | 35 GB |
| Debug (100% sampling) | 500 | 20 GB | 140 GB |

---

## Recommendations for Tempo Integration

### Phase 0: Preflight (Current)

✅ **Complete:**
- Audit current observability gaps (this document)
- Identify services requiring instrumentation
- Calculate storage requirements

### Phase 1: Infrastructure

**Deploy Tempo Container:**
```hcl
resource "docker_container" "tempo" {
  name  = "chiseai-tempo"
  image = "grafana/tempo:latest"
  
  ports {
    internal = 3200
    external = 3200
  }
  
  ports {
    internal = 4317
    external = 4317
  }
  
  ports {
    internal = 4318
    external = 4318
  }
  
  networks_advanced {
    name = docker_network.chiseai.name
  }
  
  labels {
    label = "project"
    value = "chiseai"
  }
}
```

**Storage Backend:**
- Option A: Local filesystem (simpler, single-node)
- Option B: S3-compatible (scalable, multi-node)
- Recommendation: Start with local, migrate to S3 if needed

### Phase 2: Grafana Wiring

**Add Tempo Datasource:**
```yaml
apiVersion: 1
datasources:
  - name: Tempo
    type: tempo
    url: http://chiseai-tempo:3200
    isDefault: false
```

**Create Dashboards:**
- Service dependency graph
- Trace search/exploration
- Latency percentiles by service
- Error rate by operation

### Phase 3: Application Instrumentation

**Add OpenTelemetry Dependencies:**
```toml
[project.dependencies]
opentelemetry-api = "^1.20"
opentelemetry-sdk = "^1.20"
opentelemetry-exporter-otlp = "^1.20"
opentelemetry-instrumentation-fastapi = "^0.41"
```

**Create Instrumentation Module:**
```python
# src/telemetry/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def init_tracing(service_name: str):
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint="http://chiseai-tempo:4317")
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
```

**Instrument Services:**
1. chiseai-api-final (FastAPI auto-instrumentation)
2. chiseai-kimi-adapter (manual spans for LLM calls)
3. chiseai-brain-scheduler (job execution spans)
4. chiseai-ohlcv-ingestion (pipeline spans)

### Phase 4: Sampling Strategy

**Head-Based Sampling (Default):**
- Rate: 10% for normal operations
- Rate: 100% for error conditions
- Configurable via environment variable

**Tail-Based Sampling (Future):**
- Keep all error spans
- Keep slow spans (>500ms)
- Keep specific user traces

### Phase 5: SLOs and Alerts

**Trace-Derived SLOs:**
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| p99 Latency | <500ms | >750ms |
| Error Rate | <1% | >2% |
| Trace Ingestion Rate | >90% of sampled | <80% |
| Tempo Query Latency | <100ms | >200ms |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tempo storage fills up | Medium | High | Set retention policies, monitor disk |
| Tracing overhead >5% | Low | Medium | Benchmark before production |
| OTLP port conflicts | Low | High | Verify port availability |
| Trace data loss | Low | Medium | Configure retry logic |
| Performance degradation | Medium | Medium | Start with low sampling rate |

---

## Success Criteria for Tempo Integration

- [ ] Tempo container running on `chiseai` network
- [ ] Traces visible in Grafana UI
- [ ] p99 latency alerts functional
- [ ] Service dependency map generated
- [ ] <5% performance overhead
- [ ] 7-day retention policy active
- [ ] All core services instrumented
- [ ] Trace-to-log correlation documented

---

## Appendix A: Current Container Inventory

| Container | Image | Status | Observability |
|-----------|-------|--------|---------------|
| chiseai-api-final | chiseai-api:latest | ✅ Healthy | Metrics only |
| chiseai-kimi-adapter | chiseai-kimi-adapter:latest | ✅ Healthy | Metrics only |
| chiseai-brain-scheduler | chiseai-brain-scheduler:latest | ✅ Healthy | None |
| chiseai-data-quality-monitor | chiseai-data-quality-monitor:latest | ✅ Healthy | Metrics only |
| chiseai-datasource-health-monitor | chiseai-data-quality-monitor:latest | ✅ Healthy | Metrics only |
| chiseai-daily-summary | chiseai-daily-summary:latest | ✅ Healthy | None |
| chiseai-grafana | grafana/grafana:10.4.2 | ✅ Running | Self-monitoring |
| chiseai-postgres | postgres:15 | ✅ Running | None |
| chiseai-redis | redis:7 | ✅ Running | None |
| chiseai-qdrant | qdrant/qdrant:v1.16.3 | ✅ Running | None |
| chiseai-influxdb | influxdb:2 | ✅ Running | Self-monitoring |
| chiseai-ohlcv-ingestion | chiseai-ohlcv-ingestion:latest | ✅ Healthy | Metrics only |

---

## Appendix B: Files Examined

| File | Purpose | Key Findings |
|------|---------|--------------|
| infrastructure/terraform/main.tf | Container definitions | No Tempo container |
| infrastructure/terraform/dashboards.tf | Grafana dashboards | 6 provisioned dashboards |
| infrastructure/terraform/variables.tf | Config variables | No Tempo config |
| src/api/ | API code | No tracing instrumentation |
| src/api/influx/ | InfluxDB queries | No trace correlation |
| docs/planning/sprints/TEMPO-2026-001-sprint-plan.md | Sprint plan | Detailed Tempo roadmap |
| docs/planning/sprints/TEMPO-2026-001-execution-tracker.md | Task tracker | Phase 0 in progress |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-13 | senior-dev | Initial audit document |

---

**Next Steps:**
1. Review audit with team
2. Approve storage budget (~25 GB)
3. Begin Phase 1: Tempo infrastructure deployment
4. Continue with Phase 2: Grafana wiring
