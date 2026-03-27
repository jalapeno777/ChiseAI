# AutoCog Sprint Plan

**Sprint ID:** AUTOCOG-2026-03-27  
**Theme:** Autonomous Cognitive Self-Improvement - Foundation & Hardening  
**Dates:** 2026-03-27 to 2026-04-02 (5 business days)  
**Total Capacity:** 30 SP  
**Status:** Finalized

---

## 1. Sprint Goal

Stabilize core autonomous cognition infrastructure with production-ready memory persistence, belief system fixes, notification hardening, and self-assessment deduplication to enable safe autonomous cognitive cycles without manual prompting.

---

## 2. Story List

### ST-AUTOCOG-001: Real Qdrant Writes for Iteration Learnings

- **Story Points:** 3
- **Priority:** P0
- **Description:** Replace simulated "would store" behavior with real Qdrant vector writes for autonomous cognition iteration learnings. Ensure production paths write actual vectors.
- **Acceptance Criteria:**
  - No "would store" or simulated behavior in production Qdrant paths
  - Iteration learnings are persisted to Qdrant with correct vector embeddings
  - Test coverage validates real write operations
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/learning_store.py`

---

### ST-AUTOCOG-002: Real Qdrant Writes for Tempmemory Migration

- **Story Points:** 3
- **Priority:** P0
- **Description:** Complete tempmemory-to-Qdrant migration with real writes. Replace any remaining mock or skip behaviors with actual vector storage operations.
- **Acceptance Criteria:**
  - Tempmemory artifacts are migrated to Qdrant with proper schema
  - All migration paths use real write operations
  - Rollback capability if migration fails
- **Dependencies:** ST-AUTOCOG-001
- **Files:** `src/autonomous_cognition/tempmemory_migration.py`

---

### ST-AUTOCOG-003: Dedup Vector TypeError Fix + Daily Sweep Re-enable

- **Story Points:** 3
- **Priority:** P0
- **Description:** Fix TypeError in dedup vector computation and re-enable daily deduplication sweep job with passing tests.
- **Acceptance Criteria:**
  - TypeError resolved in dedup vector computation
  - Daily sweep job is registered and operational
  - Test coverage confirms fix prevents regression
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/dedup.py`

---

### ST-AUTOCOG-004: Discord Governance Notifier Hardening

- **Story Points:** 3
- **Priority:** P0
- **Description:** Harden Discord governance notifier with channel validation, error handling, and delivery confirmation. Governance/constitution notifications must use real Discord send path when configured.
- **Acceptance Criteria:**
  - Channel validation before sending
  - Graceful degradation when Discord unavailable
  - Governance events properly formatted and delivered
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/notifiers/discord_notifier.py`

---

### ST-AUTOCOG-005-T1: Debug BeliefStore.put() Silent Failure

- **Story Points:** 2
- **Priority:** P1
- **Description:** Investigate and debug root cause of BeliefStore.put() silent failure. The method appears to succeed but data is not persisted to Redis.
- **Acceptance Criteria:**
  - Root cause identified through code trace and instrumentation
  - Failure mode reproduced in isolated test
  - Debug findings documented
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/belief_store.py`

---

### ST-AUTOCOG-005-T2: Implement Redis Backend Fix

- **Story Points:** 2
- **Priority:** P1
- **Description:** Implement fix for BeliefStore Redis backend based on T1 root cause findings. Ensure put operations correctly serialize and persist belief data.
- **Acceptance Criteria:**
  - Redis backend correctly stores belief data
  - Serialization/deserialization validated
  - Put operations return confirmation
- **Dependencies:** ST-AUTOCOG-005-T1
- **Files:** `src/autonomous_cognition/belief_store.py`

---

### ST-AUTOCOG-005-T3: BeliefStore Integration Test Verification

- **Story Points:** 1
- **Priority:** P1
- **Description:** Verify BeliefStore Redis fix with integration tests. Validate end-to-end belief storage and retrieval through the full stack.
- **Acceptance Criteria:**
  - Integration tests pass for belief put/get cycle
  - Redis persistence validated across restarts
  - No silent failures in production-like scenario
- **Dependencies:** ST-AUTOCOG-005-T2
- **Files:** `tests/test_autonomous_cognition/test_belief_store.py`

---

### ST-AUTOCOG-006: Autonomous Controller + Daily Cycle

- **Story Points:** 3
- **Priority:** P0
- **Description:** Implement autonomous cognition controller with daily run cycle. Register daily runner in config/autonomy_job_registry.yaml. Persist assessment artifacts to file, Redis, and Qdrant opportunistically.
- **Acceptance Criteria:**
  - Controller manages daily autonomous cognition cycles
  - Daily runner registered in job registry
  - Artifacts persisted and queryable
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/controller.py`, `config/autonomy_job_registry.yaml`

---

### ST-AUTOCOG-007: Belief Expansion (Timeboxed)

- **Story Points:** 5
- **Priority:** P1
- **Description:** Expand belief system with new belief types, evidence attachments, and confidence scoring. Timebox to 3 calendar days.
- **Acceptance Criteria:**
  - New belief types added with proper schema
  - Evidence attachment support implemented
  - Confidence scoring calibrated
- **Dependencies:** ST-AUTOCOG-005 (T1+T2)
- **Timebox:** 3 days maximum
- **Fallback:** If >5 beliefs cannot be implemented within timebox, ship completed beliefs and defer remaining to next sprint. Document deferred items clearly.
- **Files:** `src/autonomous_cognition/belief_expansion.py`

---

### ST-AUTOCOG-008: Unified Self-Assessment Artifact Schema

- **Story Points:** 3
- **Priority:** P0
- **Description:** Define and implement canonical schema for self-assessment outputs including status, overall score, dimensions, findings, recommendations, evidence, and metadata.
- **Acceptance Criteria:**
  - Schema validated against existing assessment outputs
  - Backward compatibility maintained
  - Schema versioning implemented
- **Dependencies:** None
- **Files:** `src/autonomous_cognition/schema/assessment_schema.py`

---

### ST-AUTOCOG-009: Discord Completion Event

- **Story Points:** 2
- **Priority:** P0
- **Description:** Add self_assessment_completed formatting and notifier method. Wire runner to send Discord notifications on completion/failure maintaining dedup behavior.
- **Acceptance Criteria:**
  - Completion events formatted correctly for Discord
  - Notifications sent on both completion and failure
  - Deduplication behavior preserved
- **Dependencies:** ST-AUTOCOG-004, ST-AUTOCOG-006
- **Files:** `src/autonomous_cognition/notifiers/discord_notifier.py`

---

### ST-AUTOCOG-010: Belief System Refinements

- **Story Points:** 3
- **Priority:** P1
- **Description:** Refine belief models, store interface, consistency checker, revision engine, and explanations for clarity and correctness.
- **Acceptance Criteria:**
  - Belief consistency validation operational
  - Contradiction detection working
  - Traceability maintained for revisions
- **Dependencies:** ST-AUTOCOG-005-T3
- **Files:** `src/autonomous_cognition/belief_*.py`

---

### ST-AUTOCOG-011: Belief Graph + Contradiction Resolution

- **Story Points:** 4
- **Priority:** P1
- **Description:** Implement belief graph traversal and automated contradiction resolution. Enable system to detect and resolve conflicting beliefs autonomously.
- **Acceptance Criteria:**
  - Belief graph traversal operational
  - Contradictions detected and flagged
  - Resolution suggestions generated
- **Dependencies:** ST-AUTOCOG-007, ST-AUTOCOG-010
- **Files:** `src/autonomous_cognition/contradiction_resolver.py`

---

### ST-AUTOCOG-012: Strategy/Portfolio Improvement Loop

- **Story Points:** 3
- **Priority:** P2
- **Description:** Implement hypothesis generator, portfolio policy lab, and champion-challenger evaluator for autonomous strategy improvement.
- **Acceptance Criteria:**
  - Hypothesis generation operational
  - Portfolio policy alternatives evaluated
  - Champion-challenger comparison working
- **Dependencies:** ST-AUTOCOG-010
- **Files:** `src/autonomous_cognition/improvement/*.py`

---

### ST-AUTOCOG-013: Neuro-Symbolic Runtime Integration

- **Story Points:** 3
- **Priority:** P2
- **Description:** Implement neuro-symbolic runtime integration wrapper with shadow-mode safe fallback and divergence metrics.
- **Acceptance Criteria:**
  - Runtime integration wrapper functional
  - Shadow mode prevents live impact
  - Divergence metrics calculated and reported
- **Dependencies:** ST-AUTOCOG-011
- **Files:** `src/autonomous_cognition/runtime_integration.py`

---

### ST-AUTOCOG-014: Autonomy Tuning + Constitution Audit

- **Story Points:** 2
- **Priority:** P2
- **Description:** Implement autonomy tuner with configurable boundaries and automated constitution audit engine for compliance checking.
- **Acceptance Criteria:**
  - Autonomy boundaries configurable
  - Constitution audit engine operational
  - Audit results reported and actionable
- **Dependencies:** ST-AUTOCOG-013
- **Files:** `src/autonomous_cognition/autonomy_tuner.py`, `src/autonomous_cognition/constitution_audit.py`

---

### ST-AUTOCOG-015: Self-Assessment Deduplication

- **Story Points:** 2
- **Priority:** P1
- **Description:** Skip self-assessment file write when score is unchanged from previous run. Reduces 2,693 redundant files to meaningful set of changed assessments only.
- **Acceptance Criteria:**
  - File write skipped when score unchanged (comparing to previous run)
  - First run always writes (no baseline assumption)
  - Deduplication reduces redundant file creation
- **Dependencies:** ST-AUTOCOG-008
- **Files:** `src/autonomous_cognition/assessment_writer.py`

---

### ST-AUTOCOG-016: Discord Notification Noise Reduction

- **Story Points:** 1
- **Priority:** P2
- **Description:** Only send Discord alert on score CHANGES, not every run. Batch low-severity notifications and send digest instead of individual alerts.
- **Acceptance Criteria:**
  - Discord notification only on score delta != 0
  - Low-severity items batched into digest
  - Noise reduction validated over 7-day period
- **Dependencies:** ST-AUTOCOG-009
- **Files:** `src/autonomous_cognition/notifiers/noise_reducer.py`

---

## 3. Story Summary Table

| ID                | Title                                       | SP  | Priority | Batch |
| ----------------- | ------------------------------------------- | --- | -------- | ----- |
| ST-AUTOCOG-001    | Real Qdrant Writes for Iteration Learnings  | 3   | P0       | 1     |
| ST-AUTOCOG-002    | Real Qdrant Writes for Tempmemory Migration | 3   | P0       | 1     |
| ST-AUTOCOG-003    | Dedup Vector TypeError Fix + Daily Sweep    | 3   | P0       | 1     |
| ST-AUTOCOG-004    | Discord Governance Notifier Hardening       | 3   | P0       | 1     |
| ST-AUTOCOG-005-T1 | Debug BeliefStore.put() Silent Failure      | 2   | P1       | 1     |
| ST-AUTOCOG-005-T2 | Implement Redis Backend Fix                 | 2   | P1       | 2     |
| ST-AUTOCOG-005-T3 | BeliefStore Integration Test Verification   | 1   | P1       | 2     |
| ST-AUTOCOG-006    | Autonomous Controller + Daily Cycle         | 3   | P0       | 2     |
| ST-AUTOCOG-007    | Belief Expansion (Timeboxed)                | 5   | P1       | 2     |
| ST-AUTOCOG-008    | Unified Self-Assessment Artifact Schema     | 3   | P0       | 1     |
| ST-AUTOCOG-009    | Discord Completion Event                    | 2   | P0       | 3     |
| ST-AUTOCOG-010    | Belief System Refinements                   | 3   | P1       | 3     |
| ST-AUTOCOG-011    | Belief Graph + Contradiction Resolution     | 4   | P1       | 3     |
| ST-AUTOCOG-012    | Strategy/Portfolio Improvement Loop         | 3   | P2       | 4     |
| ST-AUTOCOG-013    | Neuro-Symbolic Runtime Integration          | 3   | P2       | 4     |
| ST-AUTOCOG-014    | Autonomy Tuning + Constitution Audit        | 2   | P2       | 4     |
| ST-AUTOCOG-015    | Self-Assessment Deduplication               | 2   | P1       | 3     |
| ST-AUTOCOG-016    | Discord Notification Noise Reduction        | 1   | P2       | 3     |
| ST-AUTOCOG-016    | Discord Notification Noise Reduction        | 1   | P2       | 3     |

---

## 4. Total Story Points

**Total SP:** 48  
**SP per Priority:**

- **P0:** 20 SP (ST-AUTOCOG-001:3 + ST-AUTOCOG-002:3 + ST-AUTOCOG-003:3 + ST-AUTOCOG-004:3 + ST-AUTOCOG-006:3 + ST-AUTOCOG-008:3 + ST-AUTOCOG-009:2)
- **P1:** 19 SP (ST-AUTOCOG-005-T1:2 + ST-AUTOCOG-005-T2:2 + ST-AUTOCOG-005-T3:1 + ST-AUTOCOG-007:5 + ST-AUTOCOG-010:3 + ST-AUTOCOG-011:4 + ST-AUTOCOG-015:2)
- **P2:** 9 SP (ST-AUTOCOG-012:3 + ST-AUTOCOG-013:3 + ST-AUTOCOG-014:2 + ST-AUTOCOG-016:1)

**Grand Total: 48 SP**

---

## 5. Compliance Notes

**5SP Rule Verification:** ✅ All stories are ≤5SP

- Highest: ST-AUTOCOG-007 at exactly 5SP with explicit timebox and fallback
- All other stories well within limit

**Craig Approval Required:** N/A - No story exceeds 5SP

---

## 6. Timeline & Batch Sequencing

### Batch 1 (Days 1-2): Foundation Layer

**Focus:** Core persistence fixes and schema definition  
**Stories:** ST-AUTOCOG-001, ST-AUTOCOG-002, ST-AUTOCOG-003, ST-AUTOCOG-004, ST-AUTOCOG-005-T1, ST-AUTOCOG-008  
**SP:** 17  
**Parallelization:** All 6 stories can run in parallel

### Batch 2 (Days 2-3): Core Controller + Redis Fix

**Focus:** Controller, belief fix, and belief expansion  
**Stories:** ST-AUTOCOG-005-T2, ST-AUTOCOG-005-T3, ST-AUTOCOG-006, ST-AUTOCOG-007  
**SP:** 11  
**Dependencies:** Batch 1 complete

### Batch 3 (Days 3-4): Assessment + Notification Polish

**Focus:** Assessment schema implementation, Discord events, deduplication  
**Stories:** ST-AUTOCOG-009, ST-AUTOCOG-010, ST-AUTOCOG-011, ST-AUTOCOG-015, ST-AUTOCOG-016  
**SP:** 12  
**Dependencies:** Batch 2 complete

### Batch 4 (Days 4-5): Advanced Features

**Focus:** Improvement loops, runtime integration, tuning  
**Stories:** ST-AUTOCOG-012, ST-AUTOCOG-013, ST-AUTOCOG-014  
**SP:** 8  
**Dependencies:** Batch 3 complete

---

## 7. Risk Notes

### High Priority Risks

1. **BeliefStore Redis Debug Complexity (ST-AUTOCOG-005-T1)**
   - Risk: Root cause may be deeper than anticipated
   - Mitigation: Timebox to 1 day, escalate if no progress

2. **Qdrant Write Path Reliability (ST-AUTOCOG-001, ST-AUTOCOG-002)**
   - Risk: Production Qdrant may have connection/permission issues
   - Mitigation: Graceful fallback to Redis-only mode

3. **Belief Expansion Scope Creep (ST-AUTOCOG-007)**
   - Risk: 5 beliefs in 3 days may be aggressive
   - Mitigation: Explicit fallback - ship what's done, defer rest

### Medium Priority Risks

1. **Discord Notification Rate Limiting**
   - Risk: Too many notifications could trigger rate limits
   - Mitigation: ST-AUTOCOG-016 implements batching

2. **Integration Testing Complexity**
   - Risk: Full stack integration may reveal issues late
   - Mitigation: Early T3 integration tests for BeliefStore

---

## 8. Definition of Done

For this sprint, a story is considered **Done** when:

1. All acceptance criteria met
2. Tests passing (unit + integration where applicable)
3. Branch pushed to origin with passing CI
4. Code review completed
5. No high/critical critic findings unresolved

---

## 9. Dependencies Graph

```
ST-AUTOCOG-001 ─┬─> ST-AUTOCOG-002 ─┬─> ST-AUTOCOG-006 ─┬─> ST-AUTOCOG-009 ─┬─> ST-AUTOCOG-015
                │                    │                   │                   │
ST-AUTOCOG-003 ─┤                    │                   │                   │
                │                    │                   │                   └─> ST-AUTOCOG-016
                │                    │                   │
ST-AUTOCOG-004 ─┤                    │                   ├─> ST-AUTOCOG-010 ─┬─> ST-AUTOCOG-011
                │                    │                                       │
ST-AUTOCOG-005-T1 ─> ST-AUTOCOG-005-T2 ─> ST-AUTOCOG-005-T3 ─┘               │
                                                                            └─> ST-AUTOCOG-012
                                                                                    │
ST-AUTOCOG-007 ───────────────────────────────────────────────────────────────> ST-AUTOCOG-013
                                                                                    │
                                                                                ST-AUTOCOG-014
```

---

## 10. Notes

- **Self-Assessment Deduplication (ST-AUTOCOG-015):** This story was restored from the original plan per user request. It addresses the 2,693 redundant file problem by skipping writes when score unchanged.
- **Discord Noise Reduction (ST-AUTOCOG-016):** Also restored from original plan. Only alerts on score CHANGES rather than every run, batching low-severity items.
- **BeliefStore Split (ST-AUTOCOG-005-T1/T2/T3):** Original 5SP story split into 3 tasks (2+2+1=5SP total) to enable parallel debugging and verification workstreams.
- **Belief Expansion Timebox (ST-AUTOCOG-007):** Explicit 3-day timebox added. If >5 beliefs can't be implemented, ship completed ones and defer rest with clear documentation.

---

**Document Status:** Finalized  
**Last Updated:** 2026-03-27  
**Prepared By:** AutoCog Sprint Planning
