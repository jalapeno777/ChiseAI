# ADR-007: KPI Source of Truth for GO Gates

## Status
Accepted - 2026-03-10

## Context
KPI calculations were mixing paper simulation data with live Bybit execution data, resulting in incorrect GO gate decisions. This created data lineage confusion where:

1. **Journal entries** contained simulated trades with calculated PnL from price movements
2. **Bybit API** contained actual executed orders with real fees
3. **GO gates** were making promotion decisions based on simulation data instead of live trading results

The root cause was identified in `docs/evidence/PARTY-MODE-KPI-FIX-001-CORRECTED.md` where live reconciliation showed:
- Bybit: 27 executions, -$1.24 net PnL (actual fees)
- Journal: 33 entries, +$100.85 net PnL (simulated trades)
- Match rate: 0%

This mixing of sources led to false-positive GO decisions and broke the fundamental principle that live trading metrics must reflect actual execution reality.

## Decision

### 1. Source Separation

| Mode | Canonical Source | Data Type | Label |
|------|------------------|-----------|-------|
| Live Trading (demo/live) | Bybit API | Actual executions, real fees | `bybit_truth` |
| Paper Simulation | Redis journal | Simulated trades, calculated PnL | `paper_journal_sim` |

### 2. Explicit Source Labeling

All KPI artifacts MUST include explicit source metadata:

```json
{
  "source": "bybit_truth",
  "source_label": "CANONICAL FOR GO GATES",
  "data_type": "live_executions",
  "mode": "live"
}
```

```json
{
  "source": "paper_journal_sim",
  "source_label": "SIMULATION - NOT CANONICAL FOR GO",
  "data_type": "simulated_trades",
  "mode": "paper"
}
```

### 3. GO Gate Requirements

Live trading GO gates MUST:
- Use `bybit_truth` source for all metric calculations
- Reject any KPI report without explicit source labeling
- Validate source matches the intended trading mode
- Never mix sources within a single GO decision

### 4. Report Labeling Standards

**Bybit KPI Reports:**
```markdown
## Source
- **Type**: bybit_truth
- **Label**: CANONICAL FOR GO GATES
- **Verified**: Yes (via live reconciliation)
```

**Paper KPI Reports:**
```markdown
## Source
- **Type**: paper_journal_sim
- **Label**: SIMULATION - NOT CANONICAL FOR GO
- **Warning**: This report contains simulated data only
```

## Consequences

### Positive
- **Clear data lineage**: Source is explicit and unambiguous
- **Prevents mixing**: GO gates can validate source before promotion
- **Auditability**: All KPI artifacts traceable to their origin
- **Safety**: Prevents false-positive GO decisions on simulation data

### Negative
- **Additional complexity**: All KPI calculators must include source metadata
- **Migration effort**: Existing reports need labeling
- **Validation overhead**: GO gates must check source labels

### Migration Path

1. **Immediate**: All new KPI reports include source labels
2. **Short-term**: Mark legacy reports as "LEGACY - SOURCE UNSPECIFIED"
3. **Long-term**: Archive unlabeled reports; require labeled reports for GO

## References

- Live Reconciliation Evidence: `docs/validation/evidence/LIVE-RECONCILIATION-20260310.md`
- Root Cause Analysis: `docs/evidence/PARTY-MODE-KPI-FIX-001-CORRECTED.md`
- Source Separation Rule: `docs/evidence/KPI-SOURCE-SEPARATION-RULE.md`
- Evidence Index: `docs/validation/evidence/EVIDENCE-INDEX.md`

## Related ADRs

- ADR-003: GO Gate Criteria (updated to require source validation)
- ADR-005: Data Lineage Requirements

---

*Author: ChiseAI Team*  
*Date: 2026-03-10*  
*Status: Accepted*
