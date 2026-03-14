# TEMPO-2026-001 Sprint Plan

**Sprint ID:** TEMPO-2026-001  
**Duration:** 2026-03-13 to 2026-03-27  
**Story Points:** 24 SP  
**Team Capacity:** 2 senior-dev, 1 quickdev, 1 merlin  

---

## Executive Summary

This sprint implements Grafana Tempo distributed tracing infrastructure with OpenTelemetry SDK instrumentation across ChiseAI services. The goal is end-to-end observability with trace visualization in Grafana, enabling latency analysis, error tracking, and service dependency mapping for the trading platform.

---

## Phase Overview Table

| Phase | Name | SP | Parallelization | Critical Path |
|-------|------|-----|-----------------|---------------|
| 0 | Preflight | 3 | Sequential | Yes |
| 1 | Infrastructure | 5 | Sequential | Yes |
| 2 | Grafana Wiring | 3 | Sequential | Yes |
| 3 | App Instrumentation | 6 | Safe parallel | Yes |
| 4 | Service Coverage | 4 | Safe parallel | No |
| 5 | Hardening | 3 | Sequential | Yes |

---

## Phase 0: Preflight

**Goal:** Validate prerequisites, plan architecture, and establish baseline metrics before infrastructure deployment.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 0.1 | Audit current observability gaps | 1 | senior-dev-A | `docs/observability/` | Yes | None |
| 0.2 | Design trace schema and sampling strategy | 1 | senior-dev-A | `docs/planning/sprints/` | No | 0.1 |
| 0.3 | Validate OpenTelemetry SDK compatibility | 1 | quickdev | `requirements*.txt` | Yes | 0.1 |

### Acceptance Criteria
- [ ] Current observability gaps documented with priority rankings
- [ ] Trace schema defined (span attributes, resource attributes, baggage)
- [ ] Sampling strategy documented (head-based vs tail-based decision)
- [ ] OpenTelemetry SDK versions validated against Python 3.11+
- [ ] Storage requirements calculated (retention × sampling rate × throughput)

### Validation Commands
```bash
# Verify OTel SDK compatibility
python3 -c "import opentelemetry; print(opentelemetry.__version__)"
python3 -c "from opentelemetry import trace; from opentelemetry.sdk.trace import TracerProvider"

# Calculate storage requirements
python3 scripts/calculate_tempo_storage.py --retention-days 7 --spans-per-sec 1000
```

### Rollback Procedure
```bash
# If prerequisites not met
git checkout origin/main -- docs/planning/sprints/TEMPO-2026-001-sprint-plan.md
echo "TEMPO-2026-001 blocked: prerequisites not met" >> docs/observability/blockers.md
```

### Merge Gate
- All validation commands pass
- Architecture design reviewed by senior-dev-B
- Storage budget approved

### Git/Worktree Sync Protocol
```bash
# Before Phase 0
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 0
git add docs/
git commit -m "docs(tempo): Phase 0 preflight complete (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Phase 1: Infrastructure

**Goal:** Deploy Grafana Tempo container with storage backend and network configuration on the `chiseai` network.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 1.1 | Add Tempo to Terraform configuration | 2 | senior-dev-A | `infrastructure/terraform/tempo.tf` | No | 0.2 |
| 1.2 | Configure object storage backend (local/S3) | 2 | senior-dev-A | `infrastructure/terraform/tempo-storage.tf` | No | 1.1 |
| 1.3 | Deploy and verify Tempo health | 1 | quickdev | `infrastructure/terraform/` | No | 1.2 |

### Acceptance Criteria
- [ ] Tempo container running on `chiseai` network with `project=chiseai` label
- [ ] Tempo listens on ports 3200 (HTTP), 4317 (OTLP gRPC), 4318 (OTLP HTTP)
- [ ] Object storage backend accessible (local filesystem or S3-compatible)
- [ ] Tempo `/ready` endpoint returns HTTP 200
- [ ] No port conflicts with existing services

### Validation Commands
```bash
# Verify Tempo container
docker ps --filter name=chiseai-tempo --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check network membership
docker network inspect chiseai --format '{{json .Containers}}' | grep tempo

# Test health endpoint
curl -s http://host.docker.internal:3200/ready | grep "ready"

# Verify OTLP ports
curl -s http://host.docker.internal:4318/v1/traces -X POST -H "Content-Type: application/json" \
  -d '{"resourceSpans":[]}' | head -1
```

### Rollback Procedure
```bash
# If Tempo fails to start
cd infrastructure/terraform/
terraform destroy -target docker_container.chiseai-tempo
terraform destroy -target docker_volume.tempo-data

# Revert Terraform changes
git checkout origin/main -- infrastructure/terraform/tempo.tf
git commit -m "revert(tempo): rollback Tempo infrastructure (TEMPO-2026-001)"
```

### Merge Gate
- All validation commands pass
- Container logs show no errors
- Port connectivity verified from other containers

### Git/Worktree Sync Protocol
```bash
# Before Phase 1
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 1
git add infrastructure/terraform/
git commit -m "infra(tempo): Phase 1 Tempo deployment complete (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite
git checkout main
git merge feature/TEMPO-2026-001-sprint-plan-rewrite --no-ff -m "Merge Tempo infrastructure (TEMPO-2026-001)"
git push origin main

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Phase 2: Grafana Wiring

**Goal:** Configure Grafana Tempo datasource, create tracing dashboards, and set up trace-based alerts.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 2.1 | Provision Tempo datasource in Grafana | 1 | senior-dev-A | `infrastructure/terraform/grafana-datasources.tf` | No | 1.3 |
| 2.2 | Create service dependency dashboard | 1 | senior-dev-B | `grafana/dashboards/tempo-service-map.json` | Yes | 2.1 |
| 2.3 | Configure trace-derived alerts (p99 latency, error rate) | 1 | senior-dev-B | `grafana/alerts/tempo-alerts.yaml` | Yes | 2.1 |

### Acceptance Criteria
- [ ] Tempo datasource appears in Grafana UI with "Test" success
- [ ] Service dependency dashboard shows node graph with services
- [ ] Alerts configured for p99 latency >500ms and error rate >1%
- [ ] Trace search functional (by trace ID, service name, operation)
- [ ] Correlation between traces and logs demonstrated

### Validation Commands
```bash
# Verify datasource provisioning
curl -s http://host.docker.internal:3001/api/datasources/name/Tempo | jq '.name, .type, .url'

# Test trace query via API
curl -s "http://host.docker.internal:3001/api/datasources/proxy/1/api/search?tags=service.name%3Dchiseai-api" | jq '.traces | length'

# Check alert rules
curl -s http://host.docker.internal:3001/api/alert-rules | jq '.[] | select(.title | contains("tempo"))'
```

### Rollback Procedure
```bash
# If datasource fails
docker exec chiseai-grafana grafana-cli admin reset-datasources
git checkout origin/main -- infrastructure/terraform/grafana-datasources.tf
git checkout origin/main -- grafana/dashboards/tempo-service-map.json
git commit -m "revert(tempo): rollback Grafana wiring (TEMPO-2026-001)"
```

### Merge Gate
- Datasource test passes in Grafana UI
- Dashboard JSON valid and importable
- Alert rules syntactically correct

### Git/Worktree Sync Protocol
```bash
# Before Phase 2
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 2
git add infrastructure/terraform/ grafana/
git commit -m "feat(tempo): Phase 2 Grafana wiring complete (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite
git checkout main
git merge feature/TEMPO-2026-001-sprint-plan-rewrite --no-ff -m "Merge Tempo Grafana wiring (TEMPO-2026-001)"
git push origin main

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Phase 3: App Instrumentation

**Goal:** Integrate OpenTelemetry SDK into the ChiseAI Python application with auto-instrumentation and manual span creation.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 3.1 | Add OpenTelemetry SDK dependencies | 2 | senior-dev-A | `pyproject.toml`, `requirements.txt` | No | 0.3 |
| 3.2 | Create tracing initialization module | 2 | senior-dev-A | `src/observability/tracing.py` | No | 3.1 |
| 3.3 | Configure OTLP exporter to Tempo | 2 | quickdev | `src/observability/exporters.py` | Yes | 3.2 |

### Acceptance Criteria
- [ ] `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` in dependencies
- [ ] Tracing module initializes TracerProvider with resource attributes
- [ ] OTLP exporter configured with endpoint `http://chiseai-tempo:4317`
- [ ] Environment-based configuration (dev/staging/prod sampling rates)
- [ ] Auto-instrumentation for `requests`, `sqlalchemy`, `redis` libraries

### Validation Commands
```bash
# Verify dependencies installed
python3 -c "from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter; print('OK')"

# Test tracing initialization
python3 -c "from src.observability.tracing import init_tracing; init_tracing('test-service')"

# Verify exporter connectivity
python3 -c "from src.observability.exporters import get_tempo_exporter; print(get_tempo_exporter()._endpoint)"

# Run instrumentation tests
pytest tests/observability/test_tracing.py -v
```

### Rollback Procedure
```bash
# If instrumentation causes performance issues
git checkout origin/main -- pyproject.toml
git checkout origin/main -- requirements.txt
git checkout origin/main -- src/observability/
git commit -m "revert(tempo): rollback OpenTelemetry instrumentation (TEMPO-2026-001)"
pip uninstall opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp -y
```

### Merge Gate
- All tests pass
- No import errors on application startup
- Memory overhead <5% increase

### Git/Worktree Sync Protocol
```bash
# Before Phase 3
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 3
git add pyproject.toml requirements.txt src/observability/
git commit -m "feat(tempo): Phase 3 OpenTelemetry instrumentation (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite
git checkout main
git merge feature/TEMPO-2026-001-sprint-plan-rewrite --no-ff -m "Merge Tempo instrumentation (TEMPO-2026-001)"
git push origin main

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Phase 4: Service Coverage

**Goal:** Add distributed tracing to key ChiseAI services: API, strategy engine, and data ingestion pipeline.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 4.1 | Instrument API endpoints (FastAPI) | 2 | senior-dev-A | `src/api/routes/` | Yes | 3.3 |
| 4.2 | Instrument strategy engine | 1 | senior-dev-B | `src/strategy/engine.py` | Yes | 3.3 |
| 4.3 | Instrument data ingestion pipeline | 1 | senior-dev-B | `src/ingestion/` | Yes | 3.3 |

### Acceptance Criteria
- [ ] All FastAPI endpoints create spans with route name and HTTP method
- [ ] Strategy engine traces strategy execution with span per strategy
- [ ] Data ingestion traces per-batch processing with record counts
- [ ] Context propagation across service boundaries (traceparent header)
- [ ] Custom attributes: `service.version`, `deployment.environment`, `user.id`

### Validation Commands
```bash
# Generate test traces
curl -s http://host.docker.internal:8001/health

# Query traces via Tempo API
curl -s "http://host.docker.internal:3200/api/search?tags=service.name%3Dchiseai-api" | jq '.traces | length'

# Verify span attributes
curl -s "http://host.docker.internal:3200/api/traces/<trace-id>" | jq '.batches[0].instrumentationLibrarySpans[0].spans[0].attributes'

# Run service-specific trace tests
pytest tests/api/test_tracing_integration.py -v
pytest tests/strategy/test_tracing.py -v
pytest tests/ingestion/test_tracing.py -v
```

### Rollback Procedure
```bash
# If tracing causes errors in production
git checkout origin/main -- src/api/routes/
git checkout origin/main -- src/strategy/engine.py
git checkout origin/main -- src/ingestion/
git commit -m "revert(tempo): rollback service tracing (TEMPO-2026-001)"

# Disable via feature flag
export TEMPO_TRACING_ENABLED=false
```

### Merge Gate
- Traces visible in Grafana for all three services
- No errors in service logs related to tracing
- Performance impact <10% latency increase

### Git/Worktree Sync Protocol
```bash
# Before Phase 4
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 4
git add src/api/routes/ src/strategy/engine.py src/ingestion/
git commit -m "feat(tempo): Phase 4 service coverage complete (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite
git checkout main
git merge feature/TEMPO-2026-001-sprint-plan-rewrite --no-ff -m "Merge Tempo service coverage (TEMPO-2026-001)"
git push origin main

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Phase 5: Hardening

**Goal:** Optimize performance, configure sampling and retention policies, and create operational runbooks.

### Tasks

| Task | SP | Owner | Scope Globs | Parallel-Safe | Dependencies |
|------|-----|-------|-------------|---------------|--------------|
| 5.1 | Configure head-based sampling (10% prod, 100% dev) | 1 | senior-dev-A | `src/observability/tracing.py` | No | 4.1, 4.2, 4.3 |
| 5.2 | Set retention policies and storage limits | 1 | senior-dev-A | `infrastructure/terraform/tempo.tf` | No | 5.1 |
| 5.3 | Create operational runbooks | 1 | senior-dev-B | `docs/runbooks/tempo-*.md` | Yes | 5.2 |

### Acceptance Criteria
- [ ] Sampling rate configurable via environment variable `TEMPO_SAMPLE_RATE`
- [ ] Retention policy: 7 days for traces, 30 days for aggregated metrics
- [ ] Storage quota alerts at 80% capacity
- [ ] Runbook covers: trace search, sampling adjustment, Tempo restart, incident response
- [ ] Performance benchmark: trace ingestion >1000 spans/second

### Validation Commands
```bash
# Verify sampling configuration
python3 -c "import os; os.environ['TEMPO_SAMPLE_RATE']='0.1'; from src.observability.tracing import get_sampler; print(get_sampler()._rate)"

# Check retention settings
docker exec chiseai-tempo cat /etc/tempo.yaml | grep -A5 "compactor"

# Performance benchmark
python3 scripts/benchmark_tempo_ingestion.py --duration 60 --rate 1000

# Verify runbooks exist
ls -la docs/runbooks/tempo-*.md
```

### Rollback Procedure
```bash
# If sampling causes trace gaps
export TEMPO_SAMPLE_RATE=1.0
systemctl restart chiseai-api  # or docker restart

# Full rollback
git checkout origin/main -- src/observability/tracing.py
git checkout origin/main -- infrastructure/terraform/tempo.tf
git checkout origin/main -- docs/runbooks/
git commit -m "revert(tempo): rollback hardening changes (TEMPO-2026-001)"
```

### Merge Gate
- Benchmark meets throughput target
- Runbooks reviewed by on-call engineer
- merlin approval for production readiness

### Git/Worktree Sync Protocol
```bash
# Before Phase 5
git checkout feature/TEMPO-2026-001-sprint-plan-rewrite
git pull origin main

# After Phase 5
git add src/observability/tracing.py infrastructure/terraform/tempo.tf docs/runbooks/
git commit -m "feat(tempo): Phase 5 hardening complete (TEMPO-2026-001)"
git push origin feature/TEMPO-2026-001-sprint-plan-rewrite
git checkout main
git merge feature/TEMPO-2026-001-sprint-plan-rewrite --no-ff -m "Merge Tempo hardening (TEMPO-2026-001)"
git push origin main

# Verify containment
git branch --contains $(git rev-parse HEAD)
```

---

## Critical Path Visualization

```
Phase 0: Preflight
    │
    ▼
Phase 1: Infrastructure ─────────────────────────────────┐
    │                                                      │
    ▼                                                      │
Phase 2: Grafana Wiring                                    │
    │                                                      │
    ▼                                                      │
Phase 3: App Instrumentation                               │
    │                                                      │
    ├──► Phase 4.1: API Tracing ◄──────────────────────────┤
    │                                                      │
    ├──► Phase 4.2: Strategy Tracing ◄─────────────────────┤
    │                                                      │
    └──► Phase 4.3: Ingestion Tracing ◄────────────────────┘
    │
    ▼
Phase 5: Hardening
    │
    ▼
Sprint Complete
```

---

## Risk Mitigation Table

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Tempo container resource exhaustion | Medium | High | Set memory limits; configure retention; monitor disk usage |
| OpenTelemetry SDK version conflicts | Medium | High | Pin versions; test in staging; use virtual environments |
| Sampling too aggressive (trace gaps) | Low | Medium | Start with 100% sampling; adjust based on volume |
| Trace context propagation failures | Medium | Medium | Validate traceparent headers; test cross-service calls |
| Performance overhead in hot paths | Medium | High | Benchmark before/after; use async exporters; sampling |
| Grafana datasource misconfiguration | Low | Medium | Use Terraform provisioning; test on deploy |

---

## Sprint Completion Definition

All phases complete when:
1. All acceptance criteria met for Phases 0-5
2. All validation commands pass
3. Traces visible in Grafana for API, strategy, and ingestion services
4. Sampling and retention policies configured
5. Operational runbooks created and reviewed
6. Performance benchmarks meet targets (>1000 spans/sec ingestion)
7. merlin approval for merge to main

---

## Document History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-03-13 | 1.0 | Jarvis | Initial sprint plan |
| 2026-03-13 | 2.0 | senior-dev | Rewritten for Grafana Tempo + OpenTelemetry integration |
