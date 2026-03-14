# TEMPO-2026-001 Git Merge Protocol

**Sprint ID:** TEMPO-2026-001
**Branch Pattern:** `feature/TEMPO-2026-001-*`
**Base Branch:** `main`
**Merge Authority:** merlin (after senior-dev review)

---

## Pre-Flight Checklist

Before any git operation:

```bash
# 1. Verify current state
git status -sb
git branch --show-current
git log --oneline -3

# 2. Confirm story ID in branch name
git branch --show-current | grep -E "TEMPO-2026-001"

# 3. Verify session (if using worktrees)
python3 scripts/swarm/session.py verify \
  --story-id=TEMPO-2026-001 \
  --branch=$(git branch --show-current) \
  --worktree-path=$(pwd)

# 4. Confirm main synced to origin/main
git fetch origin
git status -sb  # Must show: ## main...origin/main
```

---

## Phase 0: Preflight - Git Protocol

**Phase Objective:** Validate infrastructure readiness for Grafana Tempo and OpenTelemetry integration.

### Pre-Phase Sync

```bash
# Ensure clean state on main
git checkout main
git fetch origin
git status -sb  # Must show: ## main...origin/main
git pull origin main

# Verify main is up to date
git log --oneline -1 origin/main
git log --oneline -1 HEAD
git branch --contains $(git rev-parse origin/main) | grep "main"
```

### Branch Creation (Per Task)

```bash
# Task 0.1: Verify Tempo container status
git checkout -b feature/TEMPO-2026-001-verify-tempo-container
git push -u origin feature/TEMPO-2026-001-verify-tempo-container

# Task 0.2: Verify OpenTelemetry SDK dependencies
git checkout -b feature/TEMPO-2026-001-verify-otel-deps
git push -u origin feature/TEMPO-2026-001-verify-otel-deps

# Task 0.3: Validate network connectivity (chiseai network)
git checkout -b feature/TEMPO-2026-001-validate-network
git push -u origin feature/TEMPO-2026-001-validate-network
```

### End-Phase Commit/Push

```bash
# For each completed task branch
git add -A
git commit -m "chore(tempo): Phase 0 preflight complete (TEMPO-2026-001)

- Verify Grafana Tempo container running on chiseai network
- Validate OpenTelemetry SDK dependencies in requirements
- Confirm network connectivity between services

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-verify-tempo-container

# Verify push
git status -sb  # Must show: ## feature/...origin/feature/...
git log --oneline -3 origin/feature/TEMPO-2026-001-verify-tempo-container
```

### Phase 0 Merge Verification

```bash
# After PR merge to main (merlin only)
git checkout main
git pull origin main

# CRITICAL: Verify commit is on main
git branch --contains <COMMIT_SHA> | grep "main"
# Expected output: * main

git status -sb  # Must show: ## main...origin/main

# Verify Phase 0 files present
git log --oneline --all --graph --decorate | head -20
```

---

## Phase 1: Infrastructure - Git Protocol

**Phase Objective:** Deploy and configure Grafana Tempo distributed tracing infrastructure with OpenTelemetry collectors.

### Pre-Phase Sync

```bash
git checkout main
git fetch origin
git pull origin main

# Verify Phase 0 is merged
git log --oneline --grep="TEMPO-2026-001" | grep -i "preflight"
git branch --contains $(git log --oneline --grep="preflight" | head -1 | cut -d' ' -f1) | grep main
```

### Branch Creation (Per Task)

```bash
# Task 1.1: Tempo configuration (tempo.yaml)
git checkout -b feature/TEMPO-2026-001-tempo-config
git push -u origin feature/TEMPO-2026-001-tempo-config

# Task 1.2: OpenTelemetry Collector configuration
git checkout -b feature/TEMPO-2026-001-otel-collector-config
git push -u origin feature/TEMPO-2026-001-otel-collector-config

# Task 1.3: Docker Compose updates for chiseai network
git checkout -b feature/TEMPO-2026-001-docker-compose-updates
git push -u origin feature/TEMPO-2026-001-docker-compose-updates

# Task 1.4: Terraform infrastructure updates
git checkout -b feature/TEMPO-2026-001-terraform-tempo
git push -u origin feature/TEMPO-2026-001-terraform-tempo
```

### End-Phase Commit/Push

```bash
# Tempo configuration
git add -A
git commit -m "infra(tempo): Grafana Tempo configuration (TEMPO-2026-001)

- Add tempo.yaml with trace storage backend configuration
- Configure trace retention and compaction policies
- Set up OTLP receivers for OpenTelemetry ingestion

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-tempo-config

# OpenTelemetry Collector
git add -A
git commit -m "infra(otel): OpenTelemetry Collector configuration (TEMPO-2026-001)

- Add otel-collector-config.yaml with pipelines
- Configure OTLP receivers and exporters
- Set up batch processing and resource detection

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-otel-collector-config

# Docker Compose
git add -A
git commit -m "infra(docker): Docker Compose updates for Tempo (TEMPO-2026-001)

- Add Grafana Tempo service to chiseai network
- Add OpenTelemetry Collector service
- Configure volume mounts for trace storage
- Add health checks and restart policies

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-docker-compose-updates

# Terraform
git add -A
git commit -m "infra(terraform): Terraform updates for Tempo infrastructure (TEMPO-2026-001)

- Add Tempo container resource definitions
- Add OpenTelemetry Collector container resources
- Configure network attachments for chiseai network
- Add port mappings for OTLP endpoints

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-terraform-tempo
```

### Phase 1 Merge Verification

```bash
# After all PRs merged
git checkout main
git pull origin main

# Verify each commit
git branch --contains <TEMPO_CONFIG_SHA> | grep main
git branch --contains <OTEL_COLLECTOR_SHA> | grep main
git branch --contains <DOCKER_COMPOSE_SHA> | grep main
git branch --contains <TERRAFORM_SHA> | grep main

git status -sb  ## main...origin/main
```

---

## Phase 2: Grafana Wiring - Git Protocol

**Phase Objective:** Configure Grafana dashboards and data sources for distributed tracing visualization.

### Pre-Phase Sync

```bash
git checkout main
git fetch origin
git pull origin main

# Verify Phase 1 is merged
git log --oneline --grep="TEMPO-2026-001" | grep -i "infra"
git branch --contains $(git log --oneline --grep="tempo.yaml\|otel-collector" | head -1 | cut -d' ' -f1) | grep main
```

### Branch Creation (Per Task)

```bash
# Task 2.1: Tempo data source provisioning
git checkout -b feature/TEMPO-2026-001-grafana-datasource
git push -u origin feature/TEMPO-2026-001-grafana-datasource

# Task 2.2: Trace exploration dashboard
git checkout -b feature/TEMPO-2026-001-trace-dashboard
git push -u origin feature/TEMPO-2026-001-trace-dashboard

# Task 2.3: Service dependency graph dashboard
git checkout -b feature/TEMPO-2026-001-service-graph
git push -u origin feature/TEMPO-2026-001-service-graph
```

### End-Phase Commit/Push

```bash
# Grafana data source
git add -A
git commit -m "feat(grafana): Tempo data source provisioning (TEMPO-2026-001)

- Add Tempo data source YAML configuration
- Configure trace-to-logs linking
- Set up service graph data source

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-grafana-datasource

# Trace dashboard
git add -A
git commit -m "feat(grafana): Trace exploration dashboard (TEMPO-2026-001)

- Add distributed trace search panel
- Configure trace timeline visualization
- Add span details and metadata panels

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-dashboard

# Service graph
git add -A
git commit -m "feat(grafana): Service dependency graph (TEMPO-2026-001)

- Add service graph visualization panel
- Configure node coloring by error rate
- Add edge metrics for request latency

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-service-graph
```

### Phase 2 Merge Verification

```bash
# After all PRs merged
git checkout main
git pull origin main

# Verify each commit
git branch --contains <DATASOURCE_SHA> | grep main
git branch --contains <DASHBOARD_SHA> | grep main
git branch --contains <SERVICE_GRAPH_SHA> | grep main

git status -sb
```

---

## Phase 3: App Instrumentation - Git Protocol

**Phase Objective:** Implement OpenTelemetry instrumentation in ChiseAI application code.

### Pre-Phase Sync

```bash
git checkout main
git fetch origin
git pull origin main

# Verify Phase 2 is merged
git log --oneline --grep="TEMPO-2026-001" | grep -i "grafana"
git branch --contains $(git log --oneline --grep="datasource\|dashboard" | head -1 | cut -d' ' -f1) | grep main
```

### Branch Creation (Per Task)

```bash
# Task 3.1: OpenTelemetry SDK initialization
git checkout -b feature/TEMPO-2026-001-otel-sdk-init
git push -u origin feature/TEMPO-2026-001-otel-sdk-init

# Task 3.2: FastAPI instrumentation middleware
git checkout -b feature/TEMPO-2026-001-fastapi-instrumentation
git push -u origin feature/TEMPO-2026-001-fastapi-instrumentation

# Task 3.3: Database query instrumentation
git checkout -b feature/TEMPO-2026-001-db-instrumentation
git push -u origin feature/TEMPO-2026-001-db-instrumentation

# Task 3.4: Redis instrumentation
git checkout -b feature/TEMPO-2026-001-redis-instrumentation
git push -u origin feature/TEMPO-2026-001-redis-instrumentation
```

### End-Phase Commit/Push

```bash
# OpenTelemetry SDK initialization
git add -A
git commit -m "feat(otel): OpenTelemetry SDK initialization (TEMPO-2026-001)

- Add tracer provider configuration
- Configure OTLP exporter for Grafana Tempo
- Set up resource attributes (service.name, version, env)
- Implement trace context propagation

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-otel-sdk-init

# FastAPI instrumentation
git add -A
git commit -m "feat(otel): FastAPI instrumentation middleware (TEMPO-2026-001)

- Add OpenTelemetry FastAPI instrumentation
- Configure automatic span creation for endpoints
- Add custom attributes for request/response
- Implement exception tracking in spans

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-fastapi-instrumentation

# Database instrumentation
git add -A
git commit -m "feat(otel): Database query instrumentation (TEMPO-2026-001)

- Add SQLAlchemy OpenTelemetry instrumentation
- Configure query span naming and attributes
- Track query execution time and row counts
- Implement slow query detection

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-db-instrumentation

# Redis instrumentation
git add -A
git commit -m "feat(otel): Redis instrumentation (TEMPO-2026-001)

- Add Redis OpenTelemetry instrumentation
- Track command execution times
- Add span attributes for Redis operations
- Implement connection pool metrics

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-redis-instrumentation
```

### Phase 3 Merge Verification

```bash
# After all PRs merged
git checkout main
git pull origin main

# Verify each commit
git branch --contains <SDK_INIT_SHA> | grep main
git branch --contains <FASTAPI_SHA> | grep main
git branch --contains <DB_SHA> | grep main
git branch --contains <REDIS_SHA> | grep main

git status -sb
```

---

## Phase 4: Service Coverage - Git Protocol

**Phase Objective:** Extend OpenTelemetry instrumentation to all ChiseAI services and background workers.

### Pre-Phase Sync

```bash
git checkout main
git fetch origin
git pull origin main

# Verify Phase 3 is merged
git log --oneline --grep="TEMPO-2026-001" | grep -i "instrumentation"
git branch --contains $(git log --oneline --grep="FastAPI\|SDK" | head -1 | cut -d' ' -f1) | grep main
```

### Branch Creation (Per Task)

```bash
# Task 4.1: API service instrumentation
git checkout -b feature/TEMPO-2026-001-api-service-traces
git push -u origin feature/TEMPO-2026-001-api-service-traces

# Task 4.2: Worker/background task instrumentation
git checkout -b feature/TEMPO-2026-001-worker-traces
git push -u origin feature/TEMPO-2026-001-worker-traces

# Task 4.3: Strategy execution instrumentation
git checkout -b feature/TEMPO-2026-001-strategy-traces
git push -u origin feature/TEMPO-2026-001-strategy-traces

# Task 4.4: Cross-service trace propagation
git checkout -b feature/TEMPO-2026-001-trace-propagation
git push -u origin feature/TEMPO-2026-001-trace-propagation
```

### End-Phase Commit/Push

```bash
# API service traces
git add -A
git commit -m "feat(tracing): API service distributed tracing (TEMPO-2026-001)

- Instrument all API endpoints with OpenTelemetry spans
- Add trace context to request/response logging
- Implement distributed trace ID propagation
- Add custom business logic spans

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-api-service-traces

# Worker traces
git add -A
git commit -m "feat(tracing): Background worker tracing (TEMPO-2026-001)

- Instrument Celery/background task execution
- Add trace context to job queue messages
- Track job duration and retry attempts
- Implement worker health span reporting

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-worker-traces

# Strategy execution traces
git add -A
git commit -m "feat(tracing): Strategy execution tracing (TEMPO-2026-001)

- Instrument strategy evaluation pipeline
- Add spans for signal generation and validation
- Track backtest execution with detailed traces
- Implement performance bottleneck identification

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-strategy-traces

# Trace propagation
git add -A
git commit -m "feat(tracing): Cross-service trace propagation (TEMPO-2026-001)

- Implement W3C trace context propagation
- Configure baggage for cross-service attributes
- Add traceparent header handling
- Ensure trace continuity across service boundaries

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-propagation
```

### Phase 4 Merge Verification

```bash
# After all PRs merged
git checkout main
git pull origin main

# Verify each commit
git branch --contains <API_TRACES_SHA> | grep main
git branch --contains <WORKER_TRACES_SHA> | grep main
git branch --contains <STRATEGY_TRACES_SHA> | grep main
git branch --contains <PROPAGATION_SHA> | grep main

git status -sb
```

---

## Phase 5: Hardening - Git Protocol

**Phase Objective:** Validate, optimize, and harden the distributed tracing implementation.

### Pre-Phase Sync

```bash
git checkout main
git fetch origin
git pull origin main

# Verify Phase 4 is merged
git log --oneline --grep="TEMPO-2026-001" | grep -i "tracing"
git branch --contains $(git log --oneline --grep="service\|worker\|strategy" | head -1 | cut -d' ' -f1) | grep main
```

### Branch Creation (Per Task)

```bash
# Task 5.1: Trace sampling configuration
git checkout -b feature/TEMPO-2026-001-trace-sampling
git push -u origin feature/TEMPO-2026-001-trace-sampling

# Task 5.2: Performance optimization
git checkout -b feature/TEMPO-2026-001-trace-performance
git push -u origin feature/TEMPO-2026-001-trace-performance

# Task 5.3: Alerting and SLO dashboards
git checkout -b feature/TEMPO-2026-001-trace-alerts
git push -u origin feature/TEMPO-2026-001-trace-alerts

# Task 5.4: Documentation and runbooks
git checkout -b feature/TEMPO-2026-001-trace-docs
git push -u origin feature/TEMPO-2026-001-trace-docs
```

### End-Phase Commit/Push

```bash
# Trace sampling
git add -A
git commit -m "feat(tracing): Trace sampling configuration (TEMPO-2026-001)

- Implement head-based sampling for high-volume traces
- Configure tail-based sampling for error traces
- Add sampling rate environment configuration
- Implement adaptive sampling based on load

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-sampling

# Performance optimization
git add -A
git commit -m "perf(tracing): Trace performance optimization (TEMPO-2026-001)

- Optimize span batching and export
- Reduce memory overhead of trace context
- Implement async span exporters
- Add trace buffer overflow handling

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-performance

# Alerting
git add -A
git commit -m "feat(tracing): Trace-based alerting and SLOs (TEMPO-2026-001)

- Add error rate alerting from trace data
- Configure latency SLO dashboards
- Implement trace-derived metrics
- Add anomaly detection for trace patterns

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-alerts

# Documentation
git add -A
git commit -m "docs(tracing): OpenTelemetry and Tempo documentation (TEMPO-2026-001)

- Add distributed tracing runbook
- Document span naming conventions
- Add troubleshooting guide for missing traces
- Create onboarding guide for trace instrumentation

Refs: TEMPO-2026-001"

git push origin feature/TEMPO-2026-001-trace-docs
```

### Phase 5 Merge Verification

```bash
# After all PRs merged
git checkout main
git pull origin main

# Verify each commit
git branch --contains <SAMPLING_SHA> | grep main
git branch --contains <PERFORMANCE_SHA> | grep main
git branch --contains <ALERTS_SHA> | grep main
git branch --contains <DOCS_SHA> | grep main

git status -sb
```

---

## Emergency Rollback Protocol

### Single Task Rollback

```bash
# Identify commit to revert
git log --oneline --all --grep="TEMPO-2026-001" | grep <TASK_NAME>

# Revert specific commit
git revert <COMMIT_SHA> --no-edit

# Push revert
git push origin main

# Verify rollback
git branch --contains <REVERT_SHA> | grep main
git status -sb
```

### Full Phase Rollback

```bash
# Tag current state before rollback
git tag rollback-point-TEMPO-2026-001-$(date +%Y%m%d-%H%M%S)

# Find last good commit before phase
git log --oneline --grep="TEMPO-2026-001" | grep -B1 <PHASE_START>

# Reset to last good state
git reset --hard <LAST_GOOD_COMMIT>

# Force push (emergency only - coordinate with team)
git push origin main --force-with-lease

# Verify
git status -sb
git log --oneline -5
```

---

## Worktree Session Commands

### Start Session

```bash
python3 scripts/swarm/session.py start \
  --story-id=TEMPO-2026-001 \
  --branch=feature/TEMPO-2026-001-<task-name> \
  --worktree-path=/tmp/worktrees/TEMPO-2026-001-<agent>
```

### Verify Session

```bash
python3 scripts/swarm/session.py verify \
  --story-id=TEMPO-2026-001 \
  --branch=feature/TEMPO-2026-001-<task-name> \
  --worktree-path=/tmp/worktrees/TEMPO-2026-001-<agent>
```

### Close Session

```bash
python3 scripts/swarm/session.py close \
  --story-id=TEMPO-2026-001 \
  --branch=feature/TEMPO-2026-001-<task-name> \
  --worktree-path=/tmp/worktrees/TEMPO-2026-001-<agent>
```

---

## PR Handoff Template

When handing off to merlin for PR creation:

```markdown
## PR Handoff: TEMPO-2026-001 <Task Name>

**Story ID:** TEMPO-2026-001
**Branch:** feature/TEMPO-2026-001-<task-name>
**Head SHA:** <COMMIT_SHA>
**Base:** main

### Files Changed
- `src/...` (+N/-M lines)
- `infrastructure/...` (+N/-M lines)
- `docs/...` (+N/-M lines)

### Validation
- [ ] pytest: PASS (N tests)
- [ ] black: PASS
- [ ] ruff: PASS
- [ ] Tempo connectivity: PASS
- [ ] OpenTelemetry export: PASS
- [ ] status sync: PASS

### Verification Commands
```bash
git branch --contains <COMMIT_SHA>  # Verify on feature branch
git status -sb  # Verify clean
git log --oneline -3  # Show recent commits
```

### Blockers
None / <describe blockers>
```

---

## Final Sprint Sign-Off Checklist

Before declaring sprint complete:

```bash
# 1. All commits on main
git checkout main
git pull origin main
for sha in $(git log --oneline --grep="TEMPO-2026-001" | cut -d' ' -f1); do
  git branch --contains $sha | grep -q "main" && echo "✓ $sha on main" || echo "✗ $sha NOT on main"
done

# 2. Clean working tree
git status -sb  # MUST show: ## main...origin/main

# 3. Sync with origin
git fetch origin
git log --oneline HEAD...origin/main  # MUST be empty

# 4. Verify Grafana Tempo integration
# - Tempo container running on chiseai network
# - OpenTelemetry traces exporting successfully
# - Grafana dashboards displaying traces

# 5. Tag release
git tag -a tempo-2026-001-complete -m "TEMPO-2026-001 sprint complete - Grafana Tempo + OpenTelemetry integration"
git push origin tempo-2026-001-complete

# 6. Verify tag
git show tempo-2026-001-complete --stat
```

---

## Document History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-03-13 | 2.0 | Jarvis | Rewritten for Grafana Tempo + OpenTelemetry integration |
| 2026-03-13 | 1.0 | Jarvis | Initial protocol (incorrect TEMPO framework content) |
