# Sprint Plan: Paper-Trading Gate Activation

## Sprint Information

| Field | Value |
|-------|-------|
| **Sprint ID** | PAPER-GATE-001 |
| **Sprint Name** | Paper-Trading Gate Activation |
| **Phase** | Phase 1 (Foundation) - Execution Gate |
| **Status** | planned |
| **Start Date** | 2026-02-13 |
| **Target Duration** | 14-21 days (canary period: 7 days + setup/validation) |

## Sprint Goal

Activate paper-trading canary with full monitoring pipeline and evidence collection for human approval packets. This sprint completes the Phase 1 execution gating foundation by:

1. **Activating paper-trading canary** at 10% portfolio allocation
2. **Implementing gate criteria monitoring** (5% max DD, 55% min WR, 7-day duration)
3. **Setting up 15-minute monitoring intervals** for canary health checks
4. **Building evidence collection pipeline** for promotion packets

## Key Success Criteria

| Criterion | Target | Verification |
|-----------|--------|--------------|
| Paper canary activates | 10% portfolio | Grafana dashboard shows active canary position |
| Gate criteria enforced | 5% DD, 55% WR, 7d | Automated checks every 15 minutes |
| Monitoring pipeline functional | 15-min intervals | Logs show regular health checks |
| Evidence collection works | Complete packet | Promotion packet generated on gate completion |
| Kill-switch integration verified | Armed state | Grafana shows kill-switch armed/triggered |

---

## Problem Statement

Phase 1 execution foundation is nearly complete (ST-EX-001, ST-EX-003, ST-BT-002, ST-BT-003 all completed). However, the paper-trading canary has not been activated, and we cannot validate the gating system or collect evidence for human approval packets without live execution.

## Proposed Solution

This sprint activates the paper-trading canary and builds the complete monitoring/evidence pipeline:

1. **Pre-flight checks**: Verify all dependencies are in place (data feeds, Grafana panels, kill-switch)
2. **Canary activation**: Start paper-trading at 10% portfolio allocation
3. **Gate monitoring**: Implement automated 15-minute health checks against gate criteria
4. **Evidence pipeline**: Build automated evidence collection for promotion packets
5. **Validation run**: Complete one full 7-day canary cycle to validate the system

## Scope Boundaries

**Included:**
- Paper canary activation and monitoring
- Gate criteria enforcement automation
- Evidence collection for promotion packets
- Integration with existing kill-switch (ST-EX-003)
- Grafana dashboard updates for canary visibility

**Excluded:**
- Live trading activation (ST-EX-002) - blocked on paper validation
- ML optimization stories (ST-ML-*) - can run in parallel
- Brain operations (ST-CHISE-*) - can run in parallel
- Confidence scoring (ST-CONF-001, ST-CONF-002) - can run in parallel

---

## Execution Order

### Phase 1: Pre-Flight Checks (Days 1-3)

| Day | Task | Story Dependencies | Output |
|-----|------|-------------------|--------|
| 1 | Verify data feeds functional | ST-DATA-001, ST-DATA-002 | Data freshness report |
| 2 | Verify Grafana panels ready | ST-OPS-001, ST-OPS-002 | Dashboard validation |
| 3 | Verify kill-switch integration | ST-EX-003 | Kill-switch state check |

### Phase 2: Canary Activation (Days 4-7)

| Day | Task | Story Dependencies | Output |
|-----|------|-------------------|--------|
| 4 | Configure canary parameters | ST-BT-002 | Canary config deployed |
| 5 | Start paper-trading at 10% | ST-EX-001 | First canary trade |
| 6 | Verify monitoring interval | ST-BT-002 | 15-min check logs |
| 7 | First milestone review | All above | Status report |

### Phase 3: Gate Monitoring (Days 8-14)

| Day | Task | Story Dependencies | Output |
|-----|------|-------------------|--------|
| 8-10 | Monitor gate criteria | ST-BT-002 | Daily KPI reports |
| 11-13 | Evidence collection test | ST-BT-003 | Draft promotion packet |
| 14 | Canary completion review | All | Final report + lessons |

### Phase 4: Validation & Handoff (Days 15-21)

| Day | Task | Story Dependencies | Output |
|-----|------|-------------------|--------|
| 15-18 | Full 7-day cycle validation | All | Complete evidence package |
| 19-20 | Promotion packet finalization | ST-BT-003 | Final promotion packet |
| 21 | Human approval review | - | Approval/rejection decision |

---

## Story Dependencies

### Critical Path (Must Complete Sequentially)

```
ST-DATA-002 (completed) --> ST-EX-001 (completed) --> ST-EX-003 (completed)
                                                        |
                              ST-BT-002 (completed) --> [CANARY ACTIVATION]
                                                        |
                              ST-BT-003 (completed) --> [EVIDENCE COLLECTION]
                                                        |
                              [GATE COMPLETION] ------> ST-EX-002 (unlocks)
```

### Parallelizable Stories (No Dependencies on Canary)

| Story ID | Title | Points | Reason |
|----------|-------|--------|--------|
| ST-ML-001 | Walk-Forward Evaluation Framework | 4 | ML infrastructure, no execution dependency |
| ST-ML-002 | Hyperparameter Optimization | 4 | ML infrastructure, no execution dependency |
| ST-ML-003 | ML Optimization Cadence | 3 | ML infrastructure, no execution dependency |
| ST-CHISE-001 | Brain CI/CD Pipeline | 4 | Brain versioning, no execution dependency |
| ST-CHISE-002 | Brain Evaluation Framework | 4 | Brain eval, no execution dependency |
| ST-CHISE-003 | Brain Promotion Packet | 4 | Brain packets, no execution dependency |
| ST-CHISE-005 | Chise v1 Rollback Plan | 3 | Rollback planning, no execution dependency |
| ST-CONF-001 | ECE Calculation | 4 | Confidence scoring, no execution dependency |
| ST-CONF-002 | Confidence Threshold Calibration | 3 | Confidence scoring, no execution dependency |

### Blocked Stories (Dependent on Canary Validation)

| Story ID | Title | Blocked By | Unblocks |
|----------|-------|------------|----------|
| ST-EX-002 | Bitget Live Trading Gating | Paper canary validation | Live trading |

---

## Risk Register

| Risk ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---------|------|------------|--------|------------|-------|
| R001 | Data feeds stale during canary | Medium | High | Pre-flight checks, alert on >5min stale | Data Eng |
| R002 | Kill-switch false trigger | Low | High | Configurable thresholds, manual override | Lead Eng |
| R003 | Gate criteria too strict | Medium | Medium | Adjustable parameters, documented rationale | Lead Eng |
| R004 | Insufficient trade volume for WR | Medium | Medium | Minimum trade count requirement in gate | Lead Eng |
| R005 | Grafana panel errors | Low | Medium | Pre-flight dashboard validation | QA Eng |
| R006 | Promotion packet incomplete | Low | High | Schema validation, required field checks | Lead Eng |
| R007 | 7-day canary too long | High | Low | Document need for statistical significance | PM |

---

## Parallelization Strategy

### Workstreams

| Workstream | Lead | Stories | Parallel? |
|------------|------|---------|-----------|
| Canary Activation | Lead Engineer | Pre-flight, config, start | Sequential |
| Gate Monitoring | Lead Engineer | Monitoring, evidence | Sequential |
| ML Optimization | ML Engineer | ST-ML-001, ST-ML-002, ST-ML-003 | Parallel |
| Brain Operations | ML Engineer | ST-CHISE-001, ST-CHISE-002, ST-CHISE-003, ST-CHISE-005 | Parallel |
| Confidence Scoring | Data Engineer | ST-CONF-001, ST-CONF-002 | Parallel |

---

## Definition of Done

### Sprint-Level DoD

- [ ] Paper canary activated at 10% allocation
- [ ] Gate monitoring runs every 15 minutes for 7+ days
- [ ] Kill-switch integration verified (armed state visible)
- [ ] Promotion packet generated with complete evidence
- [ ] All parallel stories have made progress (or completed)
- [ ] Sprint retrospective completed

### Quality Gates

| Gate | Criteria | Blocking? |
|------|----------|-----------|
| CI | All tests pass | Yes |
| Pre-flight | Data feeds <5min stale | Yes (blocks canary start) |
| Canary Start | First trade executes | Yes (blocks monitoring) |
| Evidence | Packet has required fields | Yes (blocks promotion) |

---

## Key Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Drawdown | <5% | >3% |
| Win Rate | >55% | <50% |
| Trade Count | >10/week | <5/week |
| Monitoring Uptime | 100% | <99% |

---

## Open Questions / Assumptions

| ID | Question/Assumption | Resolution Needed |
|----|-------------------|------------------|
| Q1 | Is 7-day canary duration sufficient for statistical significance? | May need to extend to 14 days |
| Q2 | What is the minimum trade count for valid win rate? | Need to define (suggest: 10 trades) |
| Q3 | Can we start with single token or need multiple? | Start with single token (BTC) |
| Q4 | Do we need explicit human approval to START canary? | Yes, per ST-BT-002 AC |
| Q5 | What happens if canary fails gates before 7 days? | Automatic rollback per ST-BT-002 |

---

*Document created: 2026-02-13*
*Sprint owner: TBD*
