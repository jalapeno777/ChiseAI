# AUTOCOG Sprint Deferred Backlog

**Sprint ID:** AUTOCOG-2026-03-27  
**Theme:** Autonomous Cognitive Self-Improvement - Foundation & Hardening  
**Closeout Date:** 2026-03-27  
**Deferred Reason:** Sprint closed without implementation - scope not reached during sprint window

---

## Deferred Stories

| ID                | Title                                       | SP  | Priority | Rationale                                                                                                                                  | Dependencies                                  |
| ----------------- | ------------------------------------------- | --- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| ST-AUTOCOG-002    | Real Qdrant Writes for Tempmemory Migration | 3   | P0       | Infrastructure hardening blocked by upstream Qdrant write verification; required before production tempmemory promotion                    | Qdrant connection, write permissions verified |
| ST-AUTOCOG-003    | Dedup Vector TypeError Fix + Daily Sweep    | 3   | P0       | TypeError in vector deduplication prevents clean tempmemory compaction; data integrity risk if unfixed                                     | ST-AUTOCOG-002 (same Qdrant stack)            |
| ST-AUTOCOG-005-T1 | Debug BeliefStore.put() Silent Failure      | 2   | **P1**   | **Critical Next** - BeliefStore.put() failures are silent (no exception, no log), causing belief drift that undermines autocog correctness | None - isolated debugging task                |
| ST-AUTOCOG-007    | Belief Expansion (Timeboxed)                | 5   | P1       | Belief store expansion logic needs hardening; depends on ST-AUTOCOG-005-T1 fix for accurate failure detection                              | ST-AUTOCOG-005-T1                             |
| ST-AUTOCOG-014    | Autonomy Tuning + Constitution Audit        | 2   | P2       | Constitution parameters need review post-sprint data; lower urgency than P0/P1 items                                                       | None                                          |

**Total Deferred:** 5 stories, 15 SP

---

## Next Sprint Recommendation

### Ordered by Priority

1. **ST-AUTOCOG-005-T1** (2 SP) — **CRITICAL NEXT**
   - **Reasoning:** Silent failures in BeliefStore.put() undermine all downstream cognition work. Without fixing this, any belief-dependent story (including ST-AUTOCOG-007) will have undetected data loss. Debugging is isolated and low-risk.
   - **Recommended Sprint:** Begin immediately as first story.

2. **ST-AUTOCOG-002** (3 SP) — P0
   - **Reasoning:** Qdrant write infrastructure is foundational. All tempmemory migration and vector operations depend on this. Must complete before any Qdrant-dependent work proceeds.
   - **Recommendation:** Pair with ST-AUTOCOG-003 for shared Qdrant debugging session.

3. **ST-AUTOCOG-003** (3 SP) — P0
   - **Reasoning:** Same Qdrant stack as ST-AUTOCOG-002. Fixing TypeError in dedup prevents data corruption during compaction sweeps. Can run in parallel with ST-AUTOCOG-002 after initial Qdrant write verification.
   - **Recommendation:** Group with ST-AUTOCOG-002 for efficient Qdrant debugging pass.

4. **ST-AUTOCOG-007** (5 SP) — P1
   - **Reasoning:** Belief expansion hardening depends on ST-AUTOCOG-005-T1 fix to properly detect and log failures. Timeboxed to limit scope creep.
   - **Recommendation:** Start after ST-AUTOCOG-005-T1 is verified closed.

5. **ST-AUTOCOG-014** (2 SP) — P2
   - **Reasoning:** Constitution audit is valuable but lower urgency. Can be deferred until P0/P1 items are stable.
   - **Recommendation:** Schedule in subsequent sprint after P0/P1 stabilization.

---

## P1 Critical Next: ST-AUTOCOG-005-T1

**Story:** ST-AUTOCOG-005-T1: Debug BeliefStore.put() Silent Failure  
**Priority:** P1  
**Story Points:** 2

### Problem Statement

BeliefStore.put() silently fails without raising exceptions or logging errors. This causes:

- Belief drift (beliefs appear to save but are lost)
- Corrupted belief state that undermines autocog correctness
- No visibility into failure rate or patterns

### Recommended Approach

1. Add instrumentation to BeliefStore.put() to capture return values and exceptions
2. Trace all call sites to verify error handling
3. Add integration test that verifies beliefs persist after put() returns success
4. Implement shadow logging (write to separate log channel) for debugging

### Success Criteria

- [ ] All BeliefStore.put() failures are logged with stack trace
- [ ] Return value is verified at all call sites
- [ ] Integration test confirms beliefs survive put() → get() cycle
- [ ] No silent failures in 100 consecutive test iterations

---

## Metadata

- **File:** `docs/backlog/BL-AUTOCOG-DEFERRED-2026-03-27.md`
- **Created:** 2026-03-27
- **Sprint Total Stories:** 16 (48 SP)
- **Deferred Stories:** 5 (15 SP)
- **Next Sprint Target:** SPRINT-2026-03-31
