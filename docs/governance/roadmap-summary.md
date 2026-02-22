# Party Mode Rollout Roadmap - Executive Summary

**Created**: 2026-02-22  
**Role**: Merlin (Integration Authority)  
**Status**: Roadmap Defined, Awaiting Phase 1 Implementation

---

## 30/60/90-Day Phased Roadmap

### Phase 1: Day 0-30 — Governance Foundation (Target: Mar 22, 2026)

| Deliverable | Scope | Points | Global-Lock |
|-------------|-------|--------|-------------|
| Memory Pipeline Enhancement | Redis schema, Qdrant index, consistency checker, cross-agent sharing | 11 | No |
| Constitution v0 | YAML schema, rule engine, validation pipeline, versioning | 12 | **YES** (schema) |
| Basic Sentinels | Trading, code safety, resource sentinels + dashboard | 11 | No |
| **Phase 1 Total** | | **34 points** | |

**Go/No-Go Criteria**:
- [MUST] Constitution v0 loaded and validated
- [MUST] Memory pipeline operational (99.9% uptime)
- [MUST] All 3 sentinels active with zero false positives (48h burn-in)
- [SHOULD] Memory query latency <500ms (p95)

**Decision Authority**: Merlin (with Craig consultation for constitution)

---

### Phase 2: Day 30-60 — Control Systems (Target: Apr 21, 2026)

| Deliverable | Scope | Points | Global-Lock |
|-------------|-------|--------|-------------|
| Self-Review Loop | PR self-review agent, quality scorer, calibration, feedback store | 13 | No |
| Enhanced Sentinels | Predictive, anomaly detection, correlation, learning loop | 16 | No |
| Metrics & Observability v1 | Dashboard v2, metrics exporter, SLO tracker, audit viewer | 11 | No |
| **Phase 2 Total** | | **37 points** | |

**Go/No-Go Criteria**:
- [MUST] Self-review quality correlates with human (r > 0.8)
- [MUST] Enhanced sentinels <2% false positive rate
- [MUST] Zero critical governance violations (14 days)
- [SHOULD] Predictive sentinel accuracy >85%

**Decision Authority**: Merlin + Craig (joint for live trading enablement)

---

### Phase 3: Day 60-90 — Full Autonomy (Target: May 21, 2026)

| Deliverable | Scope | Points | Global-Lock |
|-------------|-------|--------|-------------|
| Meta-Observability | Cross-system analyzer, health score, report generator, dashboard | 14 | No |
| Learning Loops | PR outcome learner, review optimizer, sentinel optimizer, agent coach | 14 | No |
| Refined Human-in-Loop | Smart escalation, review optimizer, workload balancer, override audit | 9 | No |
| **Phase 3 Total** | | **37 points** | |

**Go/No-Go Criteria**:
- [MUST] Autonomy health score >80/100 (14 days sustained)
- [MUST] Human review load reduced >50% from baseline
- [MUST] Zero critical incidents from automation (30 days)
- [SHOULD] Meta-observability identifies issues before critical

**Decision Authority**: Craig (final for full autonomy)

---

## Global-Lock vs Parallel-Safe Classification

### Global-Lock (Merlin Approval Required)
- `.woodpecker.yml` — CI/CD affects all builds
- `docs/governance/constitution.yaml` — Governance authority
- `docs/bmm-workflow-status.yaml` — Project state authority
- `infrastructure/terraform/*` — Docker network, shared infrastructure
- `scripts/ci/*`, `scripts/swarm/session.py` — Shared tooling
- `AGENTS.md` — Agent authority and roles

### Parallel-Safe (Standard PR Process)
- `src/**/*` — Source code (except execution/, risk/)
- `tests/**/*` — All tests
- `docs/**/*` — Documentation (except workflow-status.yaml)
- `infrastructure/grafana/dashboards/*` — Dashboards
- `scripts/memory/*` — New memory components
- `src/sentinels/*` — New sentinel components
- `src/learning/*` — New learning components

---

## Dependency/Parallelization Matrix

| Phase | Workstreams | Max Agents | Bottleneck |
|-------|-------------|------------|------------|
| Phase 1 | Memory, Constitution, Sentinels | 6-8 | Constitution schema (global-lock) |
| Phase 2 | Self-review, Sentinels, Metrics | 6-8 | None (all parallel-safe) |
| Phase 3 | Meta-observ, Learning, Human-in-loop | 6-8 | None (all parallel-safe) |

---

## Key Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Constitution rule conflicts | Conflict detection in validation pipeline |
| Sentinel alert fatigue | Severity levels, tuning period |
| Self-review quality degradation | Human validation sample (10%), rollback |
| Learning loop bias amplification | Human validation, diversity metrics |
| Automation over-confidence | Mandatory human gates for execution |
| Cascading autonomy failures | Circuit breakers, iteration limits |

---

## Emergency Stop

```bash
# Disables all autonomy features
redis-cli SET bmad:chiseai:emergency_stop:active 1
redis-cli SET bmad:chiseai:pr:auto_approve:enabled 0
redis-cli SET bmad:chiseai:pr:gitreviewbot:enabled 0
redis-cli SET bmad:chiseai:sentinels:enabled 0
redis-cli SET bmad:chiseai:learning:enabled 0
redis-cli SET bmad:chiseai:autonomy:active 0
```

**Target Response Time**: <30 seconds

---

## Success Metrics

| Metric | Day 30 | Day 60 | Day 90 |
|--------|--------|--------|--------|
| Constitution compliance | 100% | 100% | 100% |
| Automation coverage | N/A | >70% | >85% |
| Self-review accuracy | N/A | >85% | >90% |
| Autonomy health score | N/A | >70 | >80 |
| Human review reduction | N/A | >30% | >50% |
| System uptime | >99.5% | >99.9% | >99.9% |

---

## Story ID Allocation

### Phase 1 (Day 0-30)
- PM-GOV-001 through PM-GOV-012 (12 stories, 34 points)

### Phase 2 (Day 30-60)
- PM-GOV-013 through PM-GOV-023 (11 stories, 37 points)

### Phase 3 (Day 60-90)
- PM-GOV-024 through PM-GOV-035 (12 stories, 37 points)

**Total**: 35 stories, 108 points (~12 points/week)

---

## Full Document

Complete roadmap available at:
`docs/governance/party-mode-rollout-roadmap.md`

---

**Next Steps**:
1. Review roadmap with Craig
2. Allocate Phase 1 stories to agents
3. Begin PM-GOV-005 (Constitution YAML Schema) - global-lock, requires Merlin
4. Schedule Day 30 checkpoint review

**Next Review**: 2026-03-22
