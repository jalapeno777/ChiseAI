# Daily Operational Cycle Review - Standup Reminder

**Created:** 2026-03-10  
**Next Review Required:** Next daily standup  
**Priority:** HIGH  

---

## Reminder

The next daily standup MUST include a **"Daily Operational Cycle Review"** checkpoint.

## Review Checklist

- [ ] **Paper Trading Status**: Check paper trading health and any alerts
- [ ] **KPI Accuracy**: Verify KPI calculations are running correctly with fee deduction
- [ ] **Bybit-Journal Reconciliation**: Review any reconciliation discrepancies
- [ ] **LLM Provider Status**: Confirm Z.AI is operational as canonical provider
- [ ] **Skill System Health**: Check skill evaluation and promotion pipeline
- [ ] **Memory System**: Verify Redis/Qdrant ingestion is current
- [ ] **Branch Hygiene**: Review and cleanup merged branches
- [ ] **CI/CD Status**: Check Woodpecker CI health and any blocked PRs

## Canonical Rules

- **bybit_truth** is the GO-gate source of truth
- **paper_journal_sim** is non-canonical (reference only)
- **Z.AI** is the canonical primary LLM provider
- Other LLM provider cleanup deferred to future sprint

## Evidence Location

- KPI Fix Evidence: `docs/validation/evidence/PAPER-GO-REMEDIATION-001-KPI-REPORT-20260310.md`
- Skill Eval Summary: `docs/tempmemories/skill-eval-execution-summary-2026-03-10.md`
- Workflow Status: `docs/bmm-workflow-status.yaml`

---

*This reminder was created during remediation closeout on 2026-03-10*
