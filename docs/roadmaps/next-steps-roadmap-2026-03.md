# ChiseAI Next Steps Roadmap

**Date:** 2026-03-24  
**Status:** Draft - Ready for Craig Review  
**Paper Trading Age:** 31 days (running since 2026-02-22)

---

## Executive Summary

ChiseAI has reached a significant milestone: 22 of 24 epics complete, governance fully deployed, and paper trading running autonomously for 31 days. The system is operationally mature but has accumulated technical debt across testing (249 failures), observability (no live P&L dashboard), infrastructure (no container health checks/restart policies), and a critical strategy module that remains a 2-file stub. The highest-impact starting points are: (1) fixing the strategy engine foundation to enable strategy development, (2) adding container health/restart infrastructure, and (3) addressing the 249 pre-existing test failures to restore CI signal confidence. All changes must preserve paper trading operations.

---

## System Health Snapshot

| Area                  | Status                                   | Confidence | Evidence                     |
| --------------------- | ---------------------------------------- | ---------- | ---------------------------- |
| Core trading pipeline | ✅ Mature, operational                   | High       | 31 days paper trading        |
| ML/Feedback loop      | ✅ Operational (retraining active)       | High       | ECE tracking, model registry |
| Governance            | ✅ 100% complete                         | High       | EP-GOV-001 (2026-03-22)      |
| Paper trading uptime  | ✅ 31 days                               | High       | Discord verified by Craig    |
| Test suite            | ⚠️ 77.6% pass (249 failures)             | Medium     | Pre-existing, not blocking   |
| LLM provider chain    | ⚠️ Degraded (1/4 disabled)               | High       | MiniMax disabled             |
| CI/CD                 | ⚠️ Could not verify (Grafana 401)        | Low        | API auth issue               |
| Observability         | ⚠️ Dashboards exist, alerts uncertain    | Low        | Grafana 401                  |
| Code coverage         | ⚠️ 6.56% overall (80-98% on key modules) | Medium     | Targeted modules healthy     |

---

## Opportunity Inventory

### Trading Strategy Opportunities

| #    | Opportunity                            | Impact | Effort (SP) | Risk | Dependencies                             | Priority |
| ---- | -------------------------------------- | ------ | ----------- | ---- | ---------------------------------------- | -------- |
| S-01 | Strategy Engine Foundation             | HIGH   | 5           | MED  | Walk-forward analysis (833 lines exists) | P0       |
| S-02 | Strategy Registry & A/B Testing        | HIGH   | 3           | LOW  | S-01 first                               | P1       |
| S-03 | Bridge Walk-Forward to Strategy Engine | MED    | 3           | LOW  | S-01                                     | P1       |
| S-04 | Signal Type Performance Dashboard      | MED    | 2           | LOW  | 31 days paper data exists                | P1       |
| S-05 | Fill Model Calibration                 | MED    | 2           | LOW  | Paper trading data                       | P1       |
| S-06 | Adaptive Confidence Thresholds         | MED    | 2           | MED  | Risk of threshold flapping               | P1       |

### Infrastructure & Operations Opportunities

| #    | Opportunity                       | Impact | Effort (SP) | Risk | Dependencies         | Priority |
| ---- | --------------------------------- | ------ | ----------- | ---- | -------------------- | -------- |
| I-01 | Fix Grafana API auth (401)        | HIGH   | 1           | LOW  | Token issue          | P0       |
| I-02 | Docker container health checks    | HIGH   | 2           | LOW  | None                 | P0       |
| I-03 | Container restart policies        | HIGH   | 1           | LOW  | None                 | P0       |
| I-04 | InfluxDB retention policies       | HIGH   | 2           | LOW  | Disk exhaustion risk | P0       |
| I-05 | Fix datetime.utcnow() in scripts/ | MED    | 1           | LOW  | 54 matches           | P1       |
| I-06 | Remove Woodpecker privileged mode | HIGH   | 2           | MED  | CI testing           | P1       |
| I-07 | Live Strategy P&L Dashboard       | HIGH   | 3           | MED  | I-01 first           | P1       |
| I-08 | Backup/Restore Procedures         | MED    | 3           | LOW  | None                 | P1       |
| I-09 | Container resource limits         | MED    | 2           | LOW  | None                 | P2       |
| I-10 | Secret management migration       | MED    | 5           | MED  | Container restarts   | P2       |

### Developer Experience & Quality Opportunities

| #    | Opportunity                                  | Impact | Effort (SP) | Risk | Dependencies         | Priority |
| ---- | -------------------------------------------- | ------ | ----------- | ---- | -------------------- | -------- |
| D-01 | Wire prebuilt CI Docker images               | HIGH   | 2           | LOW  | None                 | P0       |
| D-02 | Fix 249 pre-existing test failures           | HIGH   | 5           | MED  | Categorization first | P0       |
| D-03 | Silent pip install failure detection         | MED    | 1           | LOW  | None                 | P1       |
| D-04 | Test categorization (smoke/unit/integration) | MED    | 2           | LOW  | None                 | P1       |
| D-05 | Flaky test detection expansion               | MED    | 2           | LOW  | ci.yaml cron         | P1       |
| D-06 | CI pipeline consolidation (31→20 steps)      | MED    | 3           | MED  | D-01 first           | P1       |
| D-07 | Swarm observability dashboard                | MED    | 3           | LOW  | Grafana              | P2       |
| D-08 | Integration test fixture standardization     | MED    | 3           | MED  | D-04                 | P2       |

---

## Recommended Roadmap

### Phase 1: Quick Wins (1-2 SP each) — Start Immediately

These items can begin this week with minimal risk to paper trading:

1. **I-01: Fix Grafana API auth** (1 SP) — Unblocks all alert management and observability work
2. **I-05: Fix datetime.utcnow() in scripts/** (1 SP) — 54 matches remain, Python 3.14+ compatibility
3. **I-04: InfluxDB retention policies** (2 SP) — Prevents disk exhaustion from unbounded growth
4. **D-03: Silent pip install failure detection** (1 SP) — Prevents phantom CI passes (Lesson #22)
5. **I-03: Container restart policies** (1 SP) — Auto-recovery for trading daemons
6. **I-02: Docker health checks** (2 SP) — Enables Docker-native monitoring
7. **ST-CI-EVIDENCE-001: Backfill ST-CI-001 evidence** (1 SP) — Fix completion-evidence-gate for orphaned PR #25
8. **ST-CI-TESTPATH-001: Fix missing tests/test_risk/ ref** (1 SP) — Remove dead CI path reference, fix local-ci gate
9. **ST-GOV-DRIFT-001: Fix governance drift check** (2 SP) — Backfill 4 missing stories in governance evidence file

### Phase 2: High-Value Infrastructure (3 SP) — Next 2-3 Weeks

10. **I-07: Live Strategy P&L Dashboard** (3 SP) — Closes biggest observability blind spot
11. **I-08: Backup/Restore Procedures** (3 SP) — Safety net for Redis/Postgres/InfluxDB
12. **D-01: Wire prebuilt CI Docker images** (2 SP) — Saves ~5min per pipeline run
13. **D-04: Test categorization** (2 SP) — Unblocks smoke tests and targeted runs

### Phase 3: Strategy Development (3-5 SP) — Critical Path

14. **S-01: Strategy Engine Foundation** (5 SP) — The `strategy/` module is a 2-file stub; this is the #1 architectural gap
15. **S-02: Strategy Registry & A/B Testing** (3 SP) — Enables strategy comparison and selection
16. **S-03: Bridge Walk-Forward to Strategy Engine** (3 SP) — Wires existing `ml/walk_forward.py` (833 lines)

### Phase 4: Quality & Reliability (5+ SP) — Ongoing

17. **D-02: Fix 249 pre-existing test failures** (5 SP) — Restores CI signal confidence; requires categorization first
18. **D-06: CI pipeline consolidation** (3 SP) — Reduce 31 steps to ~20
19. **I-06: Remove Woodpecker privileged mode** (2 SP) — Security hardening
20. **I-10: Secret management migration** (5 SP) — Move secrets from terraform.tfvars

---

## Quick Wins (Start This Week)

| ID                 | What                             | Why                              | SP  | Risk |
| ------------------ | -------------------------------- | -------------------------------- | --- | ---- |
| I-01               | Fix Grafana API auth             | Unblocks all observability work  | 1   | LOW  |
| I-05               | Fix datetime.utcnow()            | Python 3.14+ compat, CI warnings | 1   | LOW  |
| I-04               | InfluxDB retention               | Prevent disk exhaustion          | 2   | LOW  |
| D-03               | Pip install failure detection    | Prevent phantom CI passes        | 1   | LOW  |
| I-03               | Container restart policies       | Auto-recovery                    | 1   | LOW  |
| ST-CI-EVIDENCE-001 | Backfill ST-CI-001 evidence      | Fix completion-evidence-gate     | 1   | LOW  |
| ST-GOV-DRIFT-001   | Fix governance drift check       | Fix governance-drift-check gate  | 2   | LOW  |
| ST-CI-TESTPATH-001 | Fix missing tests/test_risk/ ref | Fix local-ci gate                | 1   | LOW  |

---

## Medium-Term Initiatives (2-4 Weeks)

| ID   | What                        | SP  | Dependencies |
| ---- | --------------------------- | --- | ------------ |
| S-01 | Strategy Engine Foundation  | 5   | None         |
| I-07 | Live Strategy P&L Dashboard | 3   | I-01         |
| I-08 | Backup/Restore Procedures   | 3   | None         |
| D-01 | Wire prebuilt CI images     | 2   | None         |
| D-04 | Test categorization         | 2   | None         |
| S-02 | Strategy Registry & A/B     | 3   | S-01         |

---

## Long-Term Considerations (Keep on Radar)

These are important but should not be started until Phase 1-3 are complete:

| Item                             | Why Defer                             | Trigger                                |
| -------------------------------- | ------------------------------------- | -------------------------------------- |
| Seccomp profiles                 | High effort, risk of breaking runtime | After container hardening complete     |
| High availability (multi-node)   | Premature for paper trading           | When moving to live trading            |
| InfluxDB → TimescaleDB migration | Current scale is fine                 | When write throughput exceeds capacity |
| Zero-trust network policies      | Overkill for single-host              | When adding external collaborators     |
| Blue/green deployments           | Paper trading allows downtime         | When approaching live trading          |

---

## Open Questions for Craig

1. **Strategy development scope**: Is building a new strategy engine the top priority, or should we focus on improving the existing signal pipeline first?
2. **Test failure tolerance**: Should we accept the 249 failures as "known tech debt" or prioritize fixing them before new development?
3. **Live trading timeline**: Are there plans to move from paper to live trading? This affects risk tolerance for infrastructure changes.
4. **Resource constraints**: What's the expected development capacity (agents per week) for the next 4-6 weeks?

---

## Blockers

None currently identified. All quick wins can start immediately.

---

_Document synthesized from parallel research by analyst, architect, and QA agents. System state verified against docs/bmm-workflow-status.yaml and recent evidence._
# CI skip test
