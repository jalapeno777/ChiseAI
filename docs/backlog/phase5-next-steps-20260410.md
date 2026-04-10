---
type: backlog
story_id: PHASE5-NEXT-001
created: 2026-04-10
tags: [canary, paper-trading, r2a, memory-audit, phase5]
author: jarvis
priority: high
---

# Phase 5 Next Steps — R2a Canary Period

> **Story**: PHASE5-NEXT-001
> **Date**: 2026-04-10
> **Status**: Active — R2a Canary Running (2026-04-08 to 2026-04-29)

---

## 1. R2a Canary Post-Monitoring (PAPER-001)

**Story ID**: PAPER-001  
**Priority**: P0  
**Story Points**: 2  
**Depends**: None  
**Status**: planned  
**Target Date**: 2026-04-29 (canary end)

**Description**: Conduct post-canary monitoring check at canary end date 2026-04-29. Collect final 21-day metrics from Grafana r2a-canary-health dashboard:

- Net profit after costs
- Turnover (avg/p95/max trades/day)
- Max drawdown, worst day
- OHLCV ingestion health verification
- Signal generation throughput (target >600 signals)
- Consumer polling lag
- Redis durable storage status
- Trade budgeter behavior (token consumption trajectory, exhaustion events)

**Acceptance Criteria**:

- [ ] Grafana r2a-canary-health dashboard URL confirmed and accessible
- [ ] 21-day metrics extracted and stored in `data/canary/r2a-final-metrics-YYYYMMDD.json`
- [ ] Trade budgeter behavior documented (20 tokens/day enforcement)
- [ ] Signal generation sustained >600 signals throughout run
- [ ] No Redis write failures during canary period

---

## 2. R2a Canary Pass/Fail Decision Gate (PAPER-002)

**Story ID**: PAPER-002  
**Priority**: P0  
**Story Points**: 3  
**Depends**: PAPER-001  
**Status**: planned  
**Target Date**: 2026-04-30

**Description**: Evaluate R2a against promotion criteria per strategy-cicd-gates framework.

**Promotion Criteria** (PRIMARY):

- Net profit after costs > champion OR within ε=3% band with tie-break
- Tie-break: lower avg/p95/max turnover, lower max drawdown

**Hard Risk Caps** (must enforce):

- DD cap: portfolio-level max drawdown cap enforced
- Daily loss: daily loss limit enforced
- Exposure/leverage: position size and leverage limits enforced

**Turnover Ceilings** (MUST NOT exceed):

- avg ≤ 20 trades/day
- p95 ≤ 30 trades/day
- max ≤ 45 trades/day

**Trade Budgeter Constraints**:

- 20 tokens/day budget enforcement documented
- Token exhaustion events logged if any

**Decision Output**:

- APPROVE with version_id for promotion
- REJECT with explicit reasons + fixes required

**Acceptance Criteria**:

- [ ] All metrics computed against promotion criteria
- [ ] Decision documented with evidence for each criterion
- [ ] APPROVE or REJECT with version_id or reasons
- [ ] Notification sent to stakeholders

---

## 3. R2a Canary Promotion Packet (PAPER-003)

**Story ID**: PAPER-003  
**Priority**: P0  
**Story Points**: 5  
**Depends**: PAPER-002 (only if APPROVED)  
**Status**: planned  
**Target Date**: 2026-05-01

**Description**: Produce human-facing promotion packet per chiseai-promotion-packet skill.

**Required Sections**:

1. Executive summary with pass/fail recommendation
2. Champion vs candidate metrics comparison
3. Turnover + budgeter behavior evidence
4. Worst day / worst regime snapshot
5. Operational notes (spike days, symbols involved)
6. Risks and known failure modes
7. Rollback plan with champion restore steps
8. Monitoring plan specifying exact Grafana alerts to watch post-promotion

**Acceptance Criteria**:

- [ ] Promotion packet artifact created at `docs/promotion/r2a-promotion-packet-YYYYMMDD.md`
- [ ] All 8 sections completed with evidence
- [ ] Rollback plan tested/documented
- [ ] Monitoring plan specifies exact Grafana alert thresholds

---

## 4. R2a Scale-Up Path (PAPER-004)

**Story ID**: PAPER-004  
**Priority**: P1  
**Story Points**: 5  
**Depends**: PAPER-003 (APPROVED only)  
**Status**: planned  
**Target Date**: 2026-05-07

**Description**: If PAPER-002 passes APPROVE, scale R2a per promotion decision.

**Path A — Paper Full**:

- Expand to broader symbol set
- Extend time horizon validation
- Verify backtest→paper carryover remains stable

**Path B — Human-Approved Live**:

- Prepare live deployment package with execution realism evidence
- Fill rate, slippage, rejects documented
- All gates passed, rollback tested
- Coordinate with Merlin for merge authority if code changes required

**Acceptance Criteria**:

- [ ] Scale path identified (A or B)
- [ ] Expanded validation executed
- [ ] Carryover stability confirmed
- [ ] Code changes merged via Merlin if applicable

---

## 5. R2a Rollback (If Canary Fails) (PAPER-005)

**Story ID**: PAPER-005  
**Priority**: P0  
**Story Points**: 3  
**Depends**: PAPER-002 (if REJECTED)  
**Status**: planned  
**Target Date**: 2026-04-30

**Description**: If PAPER-002 fails or kill criteria triggered, execute rollback procedure.

**Rollback Steps**:

1. Halt paper canary trading
2. Block new entries, allow exits only
3. Diagnose root cause against strategy-cicd-gates constraints
4. Document failure mode with evidence (which constraint breached, magnitude)
5. Produce revised strategy candidate if recoverable, else return to backtest
6. Do NOT proceed to paper full or live
7. Submit failure report to Aria with recommendations

**Kill Criteria That Trigger Rollback**:

- Net profit negative beyond ε band
- DD cap breached
- Turnover ceiling exceeded (avg >20, p95 >30, max >45)
- Trade budgeter exhaustion without recovery
- Any critical infrastructure failure (Redis loss, data ingestion failure >1h)

**Acceptance Criteria**:

- [ ] Canary halted gracefully
- [ ] Root cause documented with evidence
- [ ] Failure report submitted to Aria
- [ ] Revised candidate produced OR back-to-backtest decision made

---

## 6. MiniMax Re-Enable Evaluation (ST-001)

**Story ID**: ST-001  
**Priority**: P1  
**Story Points**: 2  
**Depends**: PAPER-001  
**Status**: planned  
**Target Date**: 2026-05-01

**Description**: Evaluate MiniMax re-enablement eligibility after R2a canary completes. PAPER-LLM-DIAG-001 cited initialization delays as reason for disable.

**Research Questions**:

- Did MiniMax impact signal latency during canary?
- OOHLCV processing time affected?
- Signal generation throughput impact?
- Initialization delays recurring or resolved?

**Recommendation Options**:

- RE-ENABLE: with latency SLA defined
- KEEP DISABLED: risks outweigh benefits
- PARTIAL ENABLE: specific symbols only

**Acceptance Criteria**:

- [ ] MiniMax behavior during canary documented
- [ ] Recommendation with evidence produced
- [ ] Aria decision captured

---

## 7. Memory Audit Phase 1 PoC — Observer Dry Run (ST-002)

**Story ID**: ST-002  
**Priority**: P1  
**Story Points**: 5  
**Depends**: None  
**Status**: planned  
**Target Date**: 2026-05-07

**Description**: Execute Phase 1 PoC of memory-audit-framework-20260409. Run Observer Agent on last 10 completed iterlogs (stored in Redis).

**Phase Gate Metrics** (ALL must pass for Phase 2):

- Observation quality (human-scored): mean ≥ 3.5/5 on accuracy/completeness/actionability/non-redundancy
- Compression ratio: median ≥ 5x
- Information retention: median ≥ 80%
- False positive rate: < 5%
- Processing latency: median < 30s/batch

**A/B Test Protocol** (per memory-audit-framework Section 4):

- 10 dry-run iterlogs
- 3-5 questions per iterlog
- Blind human scoring on 4 dimensions
- Wilcoxon signed-rank test (p < 0.05)
- Observer must win ≥ 7/10 AND p < 0.05

**Acceptance Criteria**:

- [ ] 10 observation sets collected
- [ ] Phase Gate metrics measured and stored in Redis
- [ ] A/B test executed with statistical results
- [ ] Phase Gate decision documented (proceed/rework/kill)

---

## 8. Memory Audit Phase 1 — A/B Test Execution (ST-003)

**Story ID**: ST-003  
**Priority**: P1  
**Story Points**: 3  
**Depends**: ST-002  
**Status**: planned  
**Target Date**: 2026-05-10

**Description**: Execute full A/B test protocol per memory-audit-framework Section 4.

**Process**:

1. For each of 10 dry-run iterlogs: generate 3-5 questions
2. Retrieve answers from current memories (A) vs Observer observations (B)
3. Human-score blind on 4 dimensions (accuracy, completeness, actionability, non-redundancy)
4. Run Wilcoxon signed-rank test

**Data Storage** (Redis keys):

- `bmad:chiseai:memory:ab_test:iterlog_set`
- `bmad:chiseai:memory:ab_test:scores_a`
- `bmad:chiseai:memory:ab_test:scores_b`
- `bmad:chiseai:memory:ab_test:statistical_result`

**Success Threshold**: Observer wins ≥ 7/10 AND p < 0.05

**Acceptance Criteria**:

- [ ] All 10 iterlogs tested
- [ ] Statistical significance confirmed or rejected
- [ ] Results stored in Redis with t-stat and p-value

---

## 9. Memory Audit Phase 1 — Phase Gate Decision (ST-004)

**Story ID**: ST-004  
**Priority**: P0  
**Story Points**: 2  
**Depends**: ST-003  
**Status**: planned  
**Target Date**: 2026-05-12

**Description**: Evaluate Phase Gate criteria per memory-audit-framework Section 5.

**ALL 8 Metrics Must Pass**:
| Metric | Threshold |
|--------|-----------|
| Observation quality (accuracy) | Mean ≥ 3.5/5 |
| Observation quality (completeness) | Mean ≥ 3.5/5 |
| Observation quality (actionability) | Mean ≥ 3.5/5 |
| Observation quality (non-redundancy) | Mean ≥ 3.5/5 |
| Compression ratio | Median ≥ 5x |
| Information retention | Median ≥ 80% |
| False positive rate | < 5% |
| Processing latency | Median < 30s/batch |
| A/B test | Observer wins ≥ 7/10 AND p < 0.05 |

**KILL CRITERIA** (any breach stops program):

- FP rate > 15% → stop immediately
- Compression < 2x after 2 rounds prompt tuning → stop
- Information retention < 60% → stop
- Observer loses 8/10 → no measurable improvement
- Observer prompt reaches round 3 without passing → re-evaluate approach

**If ALL pass**: Proceed to Phase 2 (Reflector Agent)
**If any kill triggered**: Submit BLOCKER_PACKET to Craig via Aria

**Acceptance Criteria**:

- [ ] All 8 metrics evaluated with evidence
- [ ] Kill criteria checked (all false = proceed)
- [ ] Decision documented: proceed to Phase 2 OR kill with evidence
- [ ] BLOCKER_PACKET submitted if kill triggered

---

## 10. Grafana r2a-canary-health Dashboard Hardening (REPO-001)

**Story ID**: REPO-001  
**Priority**: P1  
**Story Points**: 2  
**Depends**: None  
**Status**: planned  
**Target Date**: 2026-04-25 (before canary end)

**Description**: Before canary end 2026-04-29, add alerting panels and validate existing rules.

**Required Panels**:

1. Signal generation drop below 500 signals/hour → alert
2. Consumer lag exceeding 60s → alert
3. Redis write failures → alert
4. OHLCV ingestion gap > 5min → alert

**Validate Existing**:

- 4 existing alert rules fire correctly on test
- Dashboard URL documented in promotion packet

**Acceptance Criteria**:

- [ ] 4 new alert rules configured and tested
- [ ] Existing 4 rules validated
- [ ] Dashboard URL confirmed and accessible
- [ ] URL documented in `docs/promotion/r2a-promotion-packet-YYYYMMDD.md`

---

## Dependency Graph

```
PAPER-001 (post-monitoring)
  └─ PAPER-002 (decision gate)
       ├─ PAPER-003 (promotion packet) → PAPER-004 (scale-up)
       └─ PAPER-005 (rollback if fail)
  └─ ST-001 (MiniMax evaluation)

ST-002 (Observer dry run)
  └─ ST-003 (A/B test execution)
       └─ ST-004 (phase gate decision)
            └─ [Phase 2 proceeds or kill]

REPO-001 (Grafana hardening) — independent
```

---

_Generated by Jarvis (BMAD Orchestrator) — 2026-04-10_
_ClosEOUT-EXEC-20260410T0130Z_
