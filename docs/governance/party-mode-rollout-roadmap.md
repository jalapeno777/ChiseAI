# Party Mode Governance Rollout Roadmap

## Executive Summary

**Document ID**: ROLLOUT-PM-001  
**Created**: 2026-02-22  
**Role**: Merlin - Integration Authority & Merge Orchestrator  
**Target Launch**: March 14, 2026 (Paper Trading → Live Transition)  

This roadmap defines a phased rollout strategy for additive governance features that enhance the AI Swarm Autonomous PR Pipeline (EP-AUTO-GIT-001) while maintaining operational safety during the paper-to-live trading transition.

---

## Current State Assessment

### System Status (as of 2026-02-22)

| Component | Status | Notes |
|-----------|--------|-------|
| **EP-NS-008: Autonomous Control Plane** | ✅ COMPLETED | Deployed to paper trading (PR #223) |
| **EP-AUTO-GIT-001: AI Swarm PR Pipeline** | 🔄 IN PROGRESS | 3 of 8 stories complete |
| **Path Analyzer Module** | ✅ DONE | ST-AUTO-001 (Safe/Standard/Complex classification) |
| **Safe Path Auto-Approval** | ✅ DONE | ST-AUTO-002 (Auto-merge with safety checks) |
| **GitReviewBot Integration** | ✅ DONE | ST-AUTO-003 (Dual-role AI review) |
| **10-Agent Parallel Support** | 📋 PLANNED | ST-AUTO-007 (Future work) |
| **Observability & Metrics** | 📋 PLANNED | ST-AUTO-008 (Grafana dashboards) |
| **Feedback Loop** | 📋 PLANNED | ST-AUTO-005 (Outcome tracking) |

### Completed Foundation (Day 0)

```
┌─────────────────────────────────────────────────────────────┐
│ FOUNDATION LAYER (COMPLETED - Feb 21, 2026)                │
├─────────────────────────────────────────────────────────────┤
│ • Path Analyzer (semantic classification)                   │
│ • Safe Path Auto-Approval (CI-gated merges)                │
│ • GitReviewBot (dual-role AI review)                       │
│ • Circuit Breaker Registry (EP-NS-008)                     │
│ • Incident Manager (automated logging)                     │
│ • Rollback Coordinator (automatic recovery)                │
└─────────────────────────────────────────────────────────────┘
```

---

## Phased Rollout Timeline

### Overview

| Phase | Timeline | Focus | Key Deliverables |
|-------|----------|-------|------------------|
| **Day 0** | Feb 21, 2026 | Foundation | Path Analyzer, Auto-Approval, GitReviewBot |
| **Day 30** | Mar 22, 2026 | Governance Core | Memory pipeline, Constitution v0, Sentinels |
| **Day 60** | Apr 21, 2026 | Control Systems | Self-review loop, Enhanced sentinels, Metrics v1 |
| **Day 90** | May 21, 2026 | Full Autonomy | Meta-observability, Learning loops, Human-in-loop refinement |

---

## PHASE 1: Day 0-30 — Governance Foundation

**Target Date**: March 22, 2026  
**Focus**: Establish governance infrastructure with memory pipeline and constitution  
**Risk Level**: LOW (additive only, no live trading changes)

### Deliverables

#### 1.1 Memory Pipeline Enhancement (Week 1-2)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| Redis Memory Store Schema | `scripts/memory/redis_schema.py` | No | 📋 Planned |
| Qdrant Vector Memory Index | `scripts/memory/vector_store.py` | No | 📋 Planned |
| Memory Consistency Checker | `scripts/memory/consistency_check.py` | No | 📋 Planned |
| Cross-Agent Memory Sharing | `scripts/memory/shared_context.py` | No | 📋 Planned |

**Acceptance Criteria:**
- Memory writes complete in <100ms
- Vector similarity search returns top-5 matches in <500ms
- Memory consistency verified hourly with 99.9% accuracy
- Cross-agent context sharing supports 10 concurrent agents

#### 1.2 Constitution v0 — Governance Rules (Week 2-3)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| Constitution YAML Schema | `docs/governance/constitution.yaml` | **YES** | 📋 Planned |
| Rule Engine Implementation | `src/governance/rule_engine.py` | No | 📋 Planned |
| Rule Validation Pipeline | `scripts/governance/validate_rules.py` | No | 📋 Planned |
| Constitution Versioning | `src/governance/constitution_version.py` | No | 📋 Planned |

**Constitution v0 Contents:**
```yaml
version: "0.1.0"
effective_date: "2026-03-22"
governance_rules:
  trading_gates:
    - rule: "No live trading without human approval"
      severity: critical
      check: "redis-cli GET trading:mode == 'paper'"
    - rule: "Position size max 10% of portfolio"
      severity: high
      check: "position.size / portfolio.value <= 0.10"
  
  code_gates:
    - rule: "Execution code requires 2-person review"
      severity: critical
      paths: ["src/execution/**", "src/risk/**"]
    - rule: "Infrastructure changes require Merlin approval"
      severity: critical
      paths: [".woodpecker.yml", "infrastructure/**"]
  
  agent_gates:
    - rule: "Max 10 agents in parallel"
      severity: high
      check: "active_agent_count <= 10"
    - rule: "Agent ownership must be claimed"
      severity: medium
      check: "redis-cli EXISTS bmad:chiseai:ownership:*"
```

**Acceptance Criteria:**
- All rules load from YAML in <1 second
- Rule violations logged to Redis with full context
- Constitution changes require human approval
- Rule engine supports 100+ rules with <10ms evaluation time

#### 1.3 Basic Sentinels (Week 3-4)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| Trading Sentinel | `src/sentinels/trading_sentinel.py` | No | 📋 Planned |
| Code Safety Sentinel | `src/sentinels/code_sentinel.py` | No | 📋 Planned |
| Resource Sentinel | `src/sentinels/resource_sentinel.py` | No | 📋 Planned |
| Sentinel Dashboard | `infrastructure/grafana/dashboards/sentinels.json` | No | 📋 Planned |

**Sentinel Functions:**
- **Trading Sentinel**: Monitor trading mode, position limits, circuit breaker status
- **Code Safety Sentinel**: Enforce code review rules, check for banned patterns
- **Resource Sentinel**: Monitor CPU, memory, Redis connection pools

**Acceptance Criteria:**
- Sentinels run every 30 seconds
- Alerts sent to Discord within 5 seconds of violation
- False positive rate <1%
- All sentinels have documented kill switches

### Go/No-Go Criteria for Day 30

**MUST PASS (All Required):**
- [ ] Constitution v0 loaded and validated
- [ ] Memory pipeline operational with 99.9% uptime
- [ ] All 3 sentinels active and alerting
- [ ] Zero false positives in sentinel alerts (48-hour burn-in)
- [ ] Rollback procedures tested and documented

**SHOULD PASS (At least 3 of 4):**
- [ ] Memory query latency <500ms (p95)
- [ ] Rule evaluation latency <10ms (p95)
- [ ] Sentinel alert latency <5 seconds (p95)
- [ ] Documentation complete for all components

**GO Decision Authority**: Merlin (with Craig consultation for constitution changes)

### Risk Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Constitution rule conflicts | Medium | High | Rule conflict detection in validation pipeline |
| Memory pipeline overload | Low | Medium | Circuit breaker on memory writes, automatic failover |
| Sentinel alert fatigue | Medium | Medium | Tuning period, severity levels, digest mode |
| Rollback failure | Low | Critical | Tested rollback procedures, Merlin override capability |

---

## PHASE 2: Day 30-60 — Control Systems

**Target Date**: April 21, 2026  
**Focus**: Self-review capabilities and enhanced control systems  
**Risk Level**: MEDIUM (extends automation, introduces self-monitoring)

### Deliverables

#### 2.1 Self-Review Loop (Week 1-2)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| PR Self-Review Agent | `scripts/pr_lifecycle/self_review.py` | No | 📋 Planned |
| Review Quality Scorer | `scripts/pr_lifecycle/review_scorer.py` | No | 📋 Planned |
| Confidence Calibration | `scripts/pr_lifecycle/confidence_calibration.py` | No | 📋 Planned |
| Review Feedback Store | `scripts/pr_lifecycle/review_memory.py` | No | 📋 Planned |

**Self-Review Process:**
```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ PR Submitted │───▶│ Self-Review Agent│───▶│ Quality Score   │
└──────────────┘    └──────────────────┘    └────────┬────────┘
                                                      │
                           ┌──────────────────────────┼──────────┐
                           │                          │          │
                           ▼                          ▼          ▼
                    ┌─────────────┐           ┌────────────┐ ┌──────────┐
                    │ Score >= 0.9│           │0.7-0.9     │ │ < 0.7    │
                    │ Auto-merge  │           │GitReviewBot│ │ Escalate │
                    │ (Safe Path) │           │ Required   │ │ to Human │
                    └─────────────┘           └────────────┘ └──────────┘
```

**Acceptance Criteria:**
- Self-review completes in <3 minutes
- Quality scores correlate with human review (r > 0.8)
- Review feedback stored in Qdrant for learning
- Calibration updates weekly based on outcomes

#### 2.2 Enhanced Sentinels (Week 2-3)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| Predictive Sentinel | `src/sentinels/predictive_sentinel.py` | No | 📋 Planned |
| Anomaly Detection | `src/sentinels/anomaly_detector.py` | No | 📋 Planned |
| Cross-Sentinel Correlation | `src/sentinels/correlation_engine.py` | No | 📋 Planned |
| Sentinel Learning Loop | `src/sentinels/learning_loop.py` | No | 📋 Planned |

**Enhanced Capabilities:**
- **Predictive Sentinel**: ML-based anomaly prediction (5-minute forecast horizon)
- **Correlation Engine**: Cross-signal correlation to detect complex failure modes
- **Learning Loop**: Sentinel thresholds auto-adjust based on false positive/negative rates

**Acceptance Criteria:**
- Predictive accuracy >85% for critical events
- False positive rate <2% (improved from Phase 1)
- Correlation detection latency <60 seconds
- Learning loop updates thresholds weekly

#### 2.3 Metrics & Observability v1 (Week 3-4)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| PR Pipeline Dashboard v2 | `infrastructure/grafana/dashboards/pr_pipeline_v2.json` | No | 📋 Planned |
| Governance Metrics Exporter | `src/governance/metrics_exporter.py` | No | 📋 Planned |
| SLO Tracking | `src/governance/slo_tracker.py` | No | 📋 Planned |
| Audit Log Viewer | `src/governance/audit_viewer.py` | No | 📋 Planned |

**Key Metrics:**
- PR throughput by path type (SAFE/STANDARD/COMPLEX)
- Auto-merge success rate (target: >95%)
- GitReviewBot accuracy vs human (target: >85% agreement)
- Agent productivity (PRs/agent/day)
- Governance rule violations (target: 0 critical)
- Self-review quality scores
- Sentinel alert efficacy (precision/recall)

**Acceptance Criteria:**
- Dashboard updates every 10 seconds
- SLO breach alerts within 30 seconds
- Audit log queryable by story_id, agent, time range
- All metrics retained for 90 days

### Go/No-Go Criteria for Day 60

**MUST PASS (All Required):**
- [ ] Self-review quality score correlates with human review (r > 0.8)
- [ ] Enhanced sentinels active with <2% false positive rate
- [ ] All PRs have quality scores attached
- [ ] Metrics dashboard operational with 7-day burn-in
- [ ] SLO tracking identifies breaches within 30 seconds
- [ ] No critical governance violations in past 14 days

**SHOULD PASS (At least 4 of 5):**
- [ ] Predictive sentinel accuracy >85%
- [ ] Self-review latency <3 minutes (p95)
- [ ] Agent productivity >3 PRs/agent/day average
- [ ] GitReviewBot agreement with human >85%
- [ ] Constitution v0 violations: 0 critical, <5 high/14 days

**GO Decision Authority**: Merlin + Craig (joint decision for live trading enablement)

### Risk Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Self-review quality degradation | Medium | High | Human validation sample (10%), rollback to manual |
| Sentinel ML model drift | Medium | Medium | Weekly retraining, human validation |
| Metrics blind spots | Low | High | Comprehensive metric coverage review |
| Automation over-confidence | Medium | Critical | Mandatory human gates for execution changes |

---

## PHASE 3: Day 60-90 — Full Autonomy

**Target Date**: May 21, 2026  
**Focus**: Meta-observability, learning loops, and refined human-in-loop  
**Risk Level**: HIGH (approaches full autonomy, live trading consideration)

### Deliverables

#### 3.1 Meta-Observability (Week 1-2)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| System-of-Systems Dashboard | `infrastructure/grafana/dashboards/meta_observability.json` | No | 📋 Planned |
| Autonomy Health Score | `src/governance/autonomy_health.py` | No | 📋 Planned |
| Cross-System Correlation | `src/governance/cross_system_analyzer.py` | No | 📋 Planned |
| Autonomy Report Generator | `src/governance/autonomy_report.py` | No | 📋 Planned |

**Meta-Observability Concept:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    META-OBSERVABILITY LAYER                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │ PR Pipeline   │  │ Trading       │  │ Autonomous        │   │
│  │ Health        │  │ Performance   │  │ Control Plane     │   │
│  └───────┬───────┘  └───────┬───────┘  └─────────┬─────────┘   │
│          │                  │                    │             │
│          └──────────────────┼────────────────────┘             │
│                             ▼                                  │
│              ┌──────────────────────────────┐                  │
│              │   Cross-System Correlation   │                  │
│              │   - PR rate vs trading volume│                  │
│              │   - Agent load vs system health│                │
│              │   - Code changes vs incidents │                 │
│              └──────────────┬───────────────┘                  │
│                             ▼                                  │
│              ┌──────────────────────────────┐                  │
│              │   Autonomy Health Score      │                  │
│              │   0-100 composite metric     │                  │
│              └──────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- Autonomy health score calculated every 5 minutes
- Cross-system correlations identify patterns within 15 minutes
- Dashboard displays 30-day trends
- Weekly autonomy report generated automatically

#### 3.2 Learning Loops (Week 2-3)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| PR Outcome Learner | `src/learning/pr_outcome_learner.py` | No | 📋 Planned |
| Review Pattern Optimizer | `src/learning/review_optimizer.py` | No | 📋 Planned |
| Sentinel Threshold Optimizer | `src/learning/sentinel_optimizer.py` | No | 📋 Planned |
| Agent Coaching System | `src/learning/agent_coach.py` | No | 📋 Planned |

**Learning Loop Process:**
```
┌──────────────────────────────────────────────────────────────┐
│                    LEARNING LOOP                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  PR Merged  │───▶│  Outcome    │───▶│  Feature        │  │
│  │  or Declined│    │  Captured   │    │  Extraction     │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│                                               │              │
│                                               ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  Update     │◀───│  Weight     │◀───│  Model          │  │
│  │  Patterns   │    │  Update     │    │  Inference      │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│                                                               │
│  Continuous learning from:                                    │
│  • PR review outcomes (approve/decline)                       │
│  • Post-merge incidents                                       │
│  • Agent performance metrics                                  │
│  • Sentinel alert efficacy                                    │
└──────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- Learning updates applied weekly
- Review patterns improve agent success rate by >10%
- Sentinel thresholds optimize automatically (precision/recall)
- Agent coaching provides actionable feedback

#### 3.3 Refined Human-in-Loop (Week 3-4)

| Item | Scope | Global-Lock | Status |
|------|-------|-------------|--------|
| Smart Escalation Engine | `src/governance/smart_escalation.py` | No | 📋 Planned |
| Human Review Optimizer | `src/governance/human_review_optimizer.py` | No | 📋 Planned |
| Approval Workload Balancer | `src/governance/workload_balancer.py` | No | 📋 Planned |
| Human Override Audit | `src/governance/override_audit.py` | No | 📋 Planned |

**Human-in-Loop Refinement:**
- **Smart Escalation**: Only escalate when automation confidence < threshold
- **Review Optimizer**: Prioritize PRs by risk score, complexity, urgency
- **Workload Balancer**: Distribute reviews among humans to prevent bottlenecks
- **Override Audit**: Track all human overrides for pattern analysis

**Acceptance Criteria:**
- Human review load reduced by >50% from Day 0
- Escalated PRs have clear risk rationale
- Override audit identifies automation gaps
- Workload balanced across available reviewers

### Go/No-Go Criteria for Day 90

**MUST PASS (All Required):**
- [ ] Autonomy health score >80/100 sustained for 14 days
- [ ] Learning loops active and improving metrics
- [ ] Human review load reduced >50% from baseline
- [ ] Zero critical incidents attributed to automation in 30 days
- [ ] All components have documented kill switches
- [ ] Emergency stop tested and operational (<30s response)

**SHOULD PASS (At least 4 of 5):**
- [ ] Meta-observability dashboard identifies issues before they become critical
- [ ] Learning loops improve agent success rate >10%
- [ ] Smart escalation accuracy >90% (correctly identifies need for human)
- [ ] Autonomy report generated automatically weekly
- [ ] Human override rate <5% of escalated PRs

**GO Decision Authority**: Craig (final decision for full autonomy enablement)

### Risk Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Learning loop amplifies bias | Medium | High | Human validation of learned patterns, diversity metrics |
| Meta-observability blind spots | Medium | High | Regular manual audits, red team exercises |
| Automation complacency | High | Critical | Mandatory human involvement for critical changes |
| Cascading learning failures | Low | Critical | Circuit breakers, learning rate limits, human gates |

---

## Dependency & Parallelization Matrix

### Phase 1 (Day 0-30) Dependencies

```
┌────────────────────────────────────────────────────────────────┐
│ PHASE 1: FOUNDATION                                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Week 1-2: Memory Pipeline                                     │
│  ┌─────────────────┐                                           │
│  │ Redis Schema    │ ─┐                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │ PARALLEL                               │
│  │ Qdrant Index    │ ─┤                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Consistency     │ ─┘                                        │
│  │ Checker         │                                           │
│  └─────────────────┘                                           │
│           │                                                    │
│           ▼                                                    │
│  ┌─────────────────┐                                           │
│  │ Cross-Agent     │ DEPENDS ON: All memory components         │
│  │ Sharing         │                                           │
│  └─────────────────┘                                           │
│                                                                │
│  Week 2-3: Constitution v0                                     │
│  ┌─────────────────┐                                           │
│  │ YAML Schema     │ ─┐                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │ PARALLEL (global-lock: schema)         │
│  │ Rule Engine     │ ─┤                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Versioning      │ ─┘                                        │
│  └─────────────────┘                                           │
│                                                                │
│  Week 3-4: Sentinels                                           │
│  ┌─────────────────┐                                           │
│  │ Trading         │ ─┐                                        │
│  │ Sentinel        │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on constitution loaded)       │
│  │ Code Safety     │ ─┤                                        │
│  │ Sentinel        │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Resource        │ ─┘                                        │
│  │ Sentinel        │                                           │
│  └─────────────────┘                                           │
│           │                                                    │
│           ▼                                                    │
│  ┌─────────────────┐                                           │
│  │ Dashboard       │ DEPENDS ON: All sentinels                 │
│  └─────────────────┘                                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Phase 2 (Day 30-60) Dependencies

```
┌────────────────────────────────────────────────────────────────┐
│ PHASE 2: CONTROL SYSTEMS                                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Week 1-2: Self-Review Loop                                    │
│  ┌─────────────────┐                                           │
│  │ PR Self-Review  │ ─┐                                        │
│  │ Agent           │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on Phase 1 complete)          │
│  │ Quality Scorer  │ ─┤                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Confidence      │ ─┘                                        │
│  │ Calibration     │                                           │
│  └─────────────────┘                                           │
│           │                                                    │
│           ▼                                                    │
│  ┌─────────────────┐                                           │
│  │ Review Feedback │ DEPENDS ON: All self-review components   │
│  │ Store           │                                           │
│  └─────────────────┘                                           │
│                                                                │
│  Week 2-3: Enhanced Sentinels                                  │
│  ┌─────────────────┐                                           │
│  │ Predictive      │ ─┐                                        │
│  │ Sentinel        │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on basic sentinels)           │
│  │ Anomaly         │ ─┤                                        │
│  │ Detection       │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Correlation     │ ─┘                                        │
│  │ Engine          │                                           │
│  └─────────────────┘                                           │
│                                                                │
│  Week 3-4: Metrics v1                                          │
│  ┌─────────────────┐                                           │
│  │ Dashboard v2    │ ─┐                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │ PARALLEL                                │
│  │ Metrics         │ ─┤ (depends on Phase 1 + self-review)     │
│  │ Exporter        │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ SLO Tracker     │ ─┘                                        │
│  └─────────────────┘                                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Phase 3 (Day 60-90) Dependencies

```
┌────────────────────────────────────────────────────────────────┐
│ PHASE 3: FULL AUTONOMY                                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Week 1-2: Meta-Observability                                  │
│  ┌─────────────────┐                                           │
│  │ Cross-System    │ ─┐                                        │
│  │ Analyzer        │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on all prior metrics)         │
│  │ Autonomy Health │ ─┤                                        │
│  │ Score           │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Report          │ ─┘                                        │
│  │ Generator       │                                           │
│  └─────────────────┘                                           │
│           │                                                    │
│           ▼                                                    │
│  ┌─────────────────┐                                           │
│  │ Meta-Observ     │ DEPENDS ON: All analysis components      │
│  │ Dashboard       │                                           │
│  └─────────────────┘                                           │
│                                                                │
│  Week 2-3: Learning Loops                                      │
│  ┌─────────────────┐                                           │
│  │ PR Outcome      │ ─┐                                        │
│  │ Learner         │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on feedback store)            │
│  │ Review          │ ─┤                                        │
│  │ Optimizer       │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Sentinel        │ ─┤                                        │
│  │ Optimizer       │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Agent Coach     │ ─┘                                        │
│  └─────────────────┘                                           │
│                                                                │
│  Week 3-4: Human-in-Loop Refinement                            │
│  ┌─────────────────┐                                           │
│  │ Smart           │ ─┐                                        │
│  │ Escalation      │  │                                        │
│  └─────────────────┘  │ PARALLEL                                │
│  ┌─────────────────┐  │ (depends on all learning loops)        │
│  │ Review          │ ─┤                                        │
│  │ Optimizer       │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Workload        │ ─┤                                        │
│  │ Balancer        │  │                                        │
│  └─────────────────┘  │                                        │
│  ┌─────────────────┐  │                                        │
│  │ Override Audit  │ ─┘                                        │
│  └─────────────────┘                                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Parallelization Summary

| Phase | Parallel Workstreams | Max Parallel Agents | Global-Lock Items |
|-------|---------------------|---------------------|-------------------|
| Phase 1 | 3 (Memory, Constitution, Sentinels) | 6-8 | Constitution YAML Schema |
| Phase 2 | 3 (Self-Review, Enhanced Sentinels, Metrics) | 6-8 | None |
| Phase 3 | 3 (Meta-Obs, Learning, Human-in-Loop) | 6-8 | None |

---

## Global-Lock vs Parallel-Safe Classification

### Global-Lock Areas (Merlin Approval Required)

| Area | Files/Paths | Reason |
|------|-------------|--------|
| **CI/CD Configuration** | `.woodpecker.yml`, `.github/workflows/*` | Affects all builds, shared infrastructure |
| **Constitution Schema** | `docs/governance/constitution.yaml` | Governance authority, rule of law |
| **Workflow Status** | `docs/bmm-workflow-status.yaml` | Project state authority |
| **Docker Network** | `infrastructure/terraform/*` | Connectivity, all containers affected |
| **Core Scripts** | `scripts/ci/*`, `scripts/swarm/session.py` | Shared tooling, session management |
| **Agent Configuration** | `.opencode/agent/*` | Core agent behavior |
| **AGENTS.md** | `AGENTS.md` | Agent authority and roles |

### Parallel-Safe Areas (Standard PR Process)

| Area | Files/Paths | Notes |
|------|-------------|-------|
| **Source Code** | `src/**/*` | Except execution/, risk/ (require 2-person review) |
| **Tests** | `tests/**/*` | All test files |
| **Documentation** | `docs/**/*` | Except workflow-status.yaml, PRD |
| **Grafana Dashboards** | `infrastructure/grafana/dashboards/*` | Dashboard JSON files |
| **Scripts** | `scripts/*` | Except ci/, swarm/session.py |
| **Memory Pipeline** | `scripts/memory/*` | New components |
| **Sentinels** | `src/sentinels/*` | New components |
| **Learning** | `src/learning/*` | New components |

### Critical Path Enforcement

```yaml
# .woodpecker.yml excerpt for global-lock protection
global_lock_paths:
  - ".woodpecker.yml"
  - "docs/governance/constitution.yaml"
  - "docs/bmm-workflow-status.yaml"
  - "infrastructure/terraform/**"
  - "scripts/ci/**"
  - "scripts/swarm/session.py"
  - ".opencode/agent/**"
  - "AGENTS.md"

review_requirements:
  global_lock:
    min_reviewers: 2
    required_approvers: ["merlin", "craig"]
  execution_code:
    paths: ["src/execution/**", "src/risk/**"]
    min_reviewers: 2
    required_approvers: ["merlin"]
  standard:
    min_reviewers: 1
    auto_approve: true  # For SAFE path
```

---

## Risk Register: Paper → Live Transition

### Pre-Transition Risks (Days 0-90)

| ID | Risk | Likelihood | Impact | Phase | Mitigation |
|----|------|------------|--------|-------|------------|
| R1 | Governance rules conflict | Medium | High | 1 | Conflict detection, validation pipeline |
| R2 | Sentinel alert fatigue | Medium | Medium | 1-2 | Severity levels, tuning period |
| R3 | Memory pipeline failure | Low | High | 1 | Circuit breaker, automatic failover |
| R4 | Self-review quality degradation | Medium | High | 2 | Human validation sample, rollback |
| R5 | Learning loop bias amplification | Medium | High | 3 | Human validation, diversity metrics |
| R6 | Automation over-confidence | Medium | Critical | 3 | Mandatory human gates for execution |
| R7 | Cascading autonomy failures | Low | Critical | 3 | Circuit breakers, iteration limits |

### Transition Risks (Day 90+)

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|------------|
| T1 | Live trading mode accidental enable | Low | Critical | Constitution enforcement, kill switch |
| T2 | Autonomy bypass of safety checks | Low | Critical | Immutable safety layer, hardware kill |
| T3 | Human complacency due to automation | High | High | Training, regular drills, override audit |
| T4 | Governance gap during transition | Medium | High | Parallel operation, gradual handover |
| T5 | Technical debt from rapid rollout | Medium | Medium | Refactoring sprints, tech debt tracking |

### Transition Gates

**Pre-Live Trading Checklist:**
- [ ] All Phase 3 go/no-go criteria passed
- [ ] 30-day burn-in period completed in paper trading
- [ ] Emergency stop tested under load (<30s response)
- [ ] Kill switch functional and monitored
- [ ] Human override procedures trained and documented
- [ ] Rollback to manual process tested
- [ ] Incident response plan updated for autonomy
- [ ] Insurance/legal review of autonomous operations

**Live Trading Enablement:**
- [ ] Constitution v1 ratified (human approval required)
- [ ] Autonomy health score >90/100 for 14 days
- [ ] Zero critical incidents in 30 days
- [ ] Human review rate >20% (sanity check level)
- [ ] Emergency contact chain verified
- [ ] Incremental position limits for first week

---

## Rollback Procedures

### Component Rollback

| Component | Rollback Command | Time to Complete |
|-----------|------------------|------------------|
| Memory Pipeline | `redis-cli SET bmad:chiseai:memory:enabled 0` | <5s |
| Constitution Rules | Revert to previous YAML version | <30s |
| Sentinels | `redis-cli SET bmad:chiseai:sentinels:enabled 0` | <5s |
| Self-Review | `redis-cli SET bmad:chiseai:self_review:enabled 0` | <5s |
| Learning Loops | `redis-cli SET bmad:chiseai:learning:enabled 0` | <5s |
| Meta-Observability | Stop metrics exporter | <10s |
| GitReviewBot | `redis-cli SET bmad:chiseai:pr:gitreviewbot:enabled 0` | <5s |
| Auto-Approval | `redis-cli SET bmad:chiseai:pr:auto_approve:enabled 0` | <5s |

### Emergency Stop (All Autonomy)

```bash
# EMERGENCY STOP - Disables all autonomous features
redis-cli SET bmad:chiseai:emergency_stop:active 1
redis-cli SET bmad:chiseai:pr:auto_approve:enabled 0
redis-cli SET bmad:chiseai:pr:gitreviewbot:enabled 0
redis-cli SET bmad:chiseai:pr:feedback:enabled 0
redis-cli SET bmad:chiseai:swarm:max_agents 1
redis-cli SET bmad:chiseai:sentinels:enabled 0
redis-cli SET bmad:chiseai:learning:enabled 0
redis-cli SET bmad:chiseai:self_review:enabled 0
redis-cli SET bmad:chiseai:memory:enabled 0
redis-cli SET bmad:chiseai:autonomy:active 0

# Notify humans
curl -X POST "$DISCORD_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"content": "🚨 EMERGENCY STOP ACTIVATED - All autonomy disabled"}'
```

**Emergency Stop Response Time Target**: <30 seconds from trigger to full disablement

---

## Success Metrics

### Phase Success Metrics

| Phase | Primary Metric | Target | Measurement |
|-------|---------------|--------|-------------|
| Day 30 | Constitution compliance | 100% | Zero violations of v0 rules |
| Day 30 | Sentinel alert efficacy | >95% | True positive rate |
| Day 60 | Self-review accuracy | >85% | Correlation with human |
| Day 60 | Automation coverage | >70% | PRs processed without human |
| Day 90 | Autonomy health score | >80/100 | Composite metric |
| Day 90 | Human review reduction | >50% | Compared to Day 0 |

### Ongoing SLOs

| SLO | Target | Measurement Window |
|-----|--------|-------------------|
| Safe path auto-merge | <5 minutes | 95th percentile |
| Standard path review | <12 minutes | 90th percentile |
| Sentinel alert latency | <5 seconds | 95th percentile |
| Memory query latency | <500ms | 95th percentile |
| Constitution rule eval | <10ms | 95th percentile |
| Emergency stop response | <30 seconds | 100% |
| System uptime | >99.9% | 30-day window |

---

## Implementation Timeline Summary

```
Feb 2026                                          May 2026
│                                                  │
├── Day 0 ──┼── Day 30 ──┼── Day 60 ──┼── Day 90 ──┤
│           │            │            │            │
│ FOUNDATION│ GOVERNANCE │ CONTROL    │ FULL       │
│ COMPLETE  │ FOUNDATION │ SYSTEMS    │ AUTONOMY   │
│           │            │            │            │
│ ✓ Path    │ • Memory   │ • Self-    │ • Meta-    │
│   Analyzer│   Pipeline │   Review   │   Observ   │
│ ✓ Auto-   │ • Const    │ • Enhanced │ • Learning │
│   Approve │   v0       │   Sentinels│   Loops    │
│ ✓ GitRev- │ • Basic    │ • Metrics  │ • Refined  │
│   iewBot  │   Sentinels│   v1       │   H-in-L   │
│           │            │            │            │
│ Mar 14:   │            │            │            │
│ Launch    │            │            │            │
│ Date      │            │            │            │
│           │            │            │            │
└──────────────────────────────────────────────────┘
```

---

## Appendix A: Story ID Allocation

### Phase 1 Stories (Day 0-30)

| Story ID | Title | Points | Owner |
|----------|-------|--------|-------|
| PM-GOV-001 | Redis Memory Schema | 3 | TBD |
| PM-GOV-002 | Qdrant Vector Memory Index | 3 | TBD |
| PM-GOV-003 | Memory Consistency Checker | 2 | TBD |
| PM-GOV-004 | Cross-Agent Memory Sharing | 3 | TBD |
| PM-GOV-005 | Constitution YAML Schema | 2 | Merlin |
| PM-GOV-006 | Rule Engine Implementation | 5 | TBD |
| PM-GOV-007 | Rule Validation Pipeline | 3 | TBD |
| PM-GOV-008 | Constitution Versioning | 2 | TBD |
| PM-GOV-009 | Trading Sentinel | 3 | TBD |
| PM-GOV-010 | Code Safety Sentinel | 3 | TBD |
| PM-GOV-011 | Resource Sentinel | 2 | TBD |
| PM-GOV-012 | Sentinel Dashboard | 3 | TBD |

**Phase 1 Total: 34 points**

### Phase 2 Stories (Day 30-60)

| Story ID | Title | Points | Owner |
|----------|-------|--------|-------|
| PM-GOV-013 | PR Self-Review Agent | 5 | TBD |
| PM-GOV-014 | Review Quality Scorer | 3 | TBD |
| PM-GOV-015 | Confidence Calibration | 3 | TBD |
| PM-GOV-016 | Review Feedback Store | 2 | TBD |
| PM-GOV-017 | Predictive Sentinel | 5 | TBD |
| PM-GOV-018 | Anomaly Detection | 5 | TBD |
| PM-GOV-019 | Cross-Sentinel Correlation | 3 | TBD |
| PM-GOV-020 | Sentinel Learning Loop | 3 | TBD |
| PM-GOV-021 | PR Pipeline Dashboard v2 | 3 | TBD |
| PM-GOV-022 | Governance Metrics Exporter | 2 | TBD |
| PM-GOV-023 | SLO Tracker | 3 | TBD |

**Phase 2 Total: 37 points**

### Phase 3 Stories (Day 60-90)

| Story ID | Title | Points | Owner |
|----------|-------|--------|-------|
| PM-GOV-024 | Cross-System Analyzer | 5 | TBD |
| PM-GOV-025 | Autonomy Health Score | 3 | TBD |
| PM-GOV-026 | Autonomy Report Generator | 3 | TBD |
| PM-GOV-027 | Meta-Observability Dashboard | 3 | TBD |
| PM-GOV-028 | PR Outcome Learner | 5 | TBD |
| PM-GOV-029 | Review Pattern Optimizer | 3 | TBD |
| PM-GOV-030 | Sentinel Threshold Optimizer | 3 | TBD |
| PM-GOV-031 | Agent Coaching System | 3 | TBD |
| PM-GOV-032 | Smart Escalation Engine | 3 | TBD |
| PM-GOV-033 | Human Review Optimizer | 2 | TBD |
| PM-GOV-034 | Approval Workload Balancer | 2 | TBD |
| PM-GOV-035 | Human Override Audit | 2 | TBD |

**Phase 3 Total: 37 points**

**Grand Total: 108 points across 90 days (~12 points/week)**

---

## Appendix B: Decision Log

| Date | Decision | Rationale | Decision Maker |
|------|----------|-----------|----------------|
| 2026-02-22 | 3-phase rollout (30/60/90 days) | Balances speed with safety, allows learning | Merlin |
| 2026-02-22 | Constitution v0 in Phase 1 | Establishes governance foundation early | Merlin |
| 2026-02-22 | Self-review in Phase 2 | Requires Phase 1 memory infrastructure | Merlin |
| 2026-02-22 | Meta-observability in Phase 3 | Requires sufficient data from prior phases | Merlin |
| 2026-02-22 | Merlin go/no-go for Phase 1 | Integration authority responsibility | Merlin |
| 2026-02-22 | Craig decision for full autonomy | Human accountability for live trading | Policy |

---

## Appendix C: Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Autonomous Control Plane Golden Plan | `docs/architecture/autonomous-control-plane-golden-plan.md` | EP-NS-008 reference |
| BMM Workflow Status | `docs/bmm-workflow-status.yaml` | Project state |
| Validation Registry | `docs/validation/validation-registry.yaml` | Quality gates |
| Emergency Merge Override | `.opencode/command/chise-emergency-merge-override.md` | Emergency procedures |
| CI Root Cause Analysis | `.opencode/command/chise-ci-root-cause.md` | Failure diagnosis |

---

**Document Control**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-02-22 | Initial roadmap | Merlin |

**Next Review Date**: 2026-03-22 (Day 30 checkpoint)

**Distribution**: Jarvis, Craig, all agent roles

---

*"Safety through transparency, autonomy through accountability."*
