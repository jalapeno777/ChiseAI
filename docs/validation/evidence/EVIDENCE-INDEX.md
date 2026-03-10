# Evidence Index - KPI Source of Truth (ST-KPI-FIX-001)

## Overview

This index catalogs all evidence artifacts related to the KPI source separation fix (ST-KPI-FIX-001). The canonical rule established:

> **Bybit truth is canonical for live trading GO gates.**  
> **Paper journal is simulation telemetry only.**

## Architecture Decision

| Document | Description | Status |
|----------|-------------|--------|
| `docs/architecture/ADR-007-kpi-source-of-truth.md` | Architecture Decision Record defining the canonical rule | ✅ Accepted |

## Canonical Rule Documentation

| Document | Description | Status |
|----------|-------------|--------|
| `docs/evidence/KPI-SOURCE-SEPARATION-RULE.md` | Detailed rule documentation, migration guide, and enforcement | ✅ Active |
| `docs/evidence/PARTY-MODE-KPI-FIX-001-CORRECTED.md` | Root cause analysis and resolution | ✅ Complete |

## KPI Artifacts by Source

### bybit_truth (Canonical for Live)

These reports are sourced from Bybit API and are **canonical for live trading GO gates**.

| Artifact | Description | Date | Status |
|----------|-------------|------|--------|
| `BYBIT-TRUTH-KPI-20260310.json` | Bybit KPI snapshot (to be generated) | 2026-03-10 | ⏳ Pending |
| `LIVE-RECONCILIATION-20260310.json` | Live reconciliation proving source separation | 2026-03-10 | ✅ Complete |
| `LIVE-RECONCILIATION-20260310.md` | Human-readable reconciliation report | 2026-03-10 | ✅ Complete |

### paper_journal_sim (Simulation Only)

These reports are sourced from Redis journal and are **for simulation only**.

| Artifact | Description | Date | Status |
|----------|-------------|------|--------|
| `PAPER-SIM-KPI-20260310.json` | Paper KPI snapshot (to be generated) | 2026-03-10 | ⏳ Pending |
| `PAPER-GO-REMEDIATION-001-KPI-SNAPSHOT-20260310.json` | Paper trading KPI metrics | 2026-03-10 | ✅ Complete |
| `PAPER-GO-REMEDIATION-001-KPI-REPORT-20260310.md` | Paper trading KPI report | 2026-03-10 | ✅ Complete |

## Superseded/Stale Artifacts

The following artifacts mixed sources and are now **superseded**:

| Artifact | Reason | Superseded By |
|----------|--------|---------------|
| Legacy KPI reports without source labels | Source ambiguity | ADR-007 labeled reports |
| Mixed-source calculations | Data lineage broken | Source-separated reports |

## Live Reconciliation Evidence

Evidence proving the need for source separation:

| Artifact | Description | Key Finding |
|----------|-------------|-------------|
| `LIVE-RECONCILIATION-20260310.json` | Full reconciliation data | 0% match between Bybit and journal |
| `LIVE-RECONCILIATION-20260310.md` | Human-readable summary | $102.08 PnL difference |

### Key Reconciliation Metrics

```
Bybit executions:     27
Journal entries:      33
Match rate:           0%
Bybit Net PnL:        -$1.24 (actual fees)
Journal Net PnL:      +$100.85 (simulated)
Difference:           $102.08
```

## GO Gate Evidence

Evidence supporting GO gate decisions:

| Artifact | Purpose | Source |
|----------|---------|--------|
| `PAPER-GO-LIVE-CHECKS-20260310.json` | Pre-promotion validation | Paper (simulation) |
| `PAPER-LIVE-E2E-d4bee679-evidence.json` | E2E test evidence | Paper (simulation) |

## Cross-References

### Related Stories

| Story | Description | Status |
|-------|-------------|--------|
| ST-KPI-FIX-001 | KPI source separation fix | ✅ Complete |
| PAPER-GO-REMEDIATION-001 | Paper trading validation | ✅ Complete |

### Related Documentation

| Document | Purpose |
|----------|---------|
| `docs/architecture/ADR-007-kpi-source-of-truth.md` | Architecture decision |
| `docs/evidence/KPI-SOURCE-SEPARATION-RULE.md` | Rule documentation |
| `docs/evidence/PARTY-MODE-KPI-FIX-001-CORRECTED.md` | Root cause analysis |

## Validation Checklist

Before using any KPI report for GO decisions, verify:

- [ ] Report has explicit `source` field
- [ ] Source is `bybit_truth` for live GO gates
- [ ] Source is `paper_journal_sim` for paper GO gates
- [ ] Report has `source_label` matching source type
- [ ] Report date is within validation window
- [ ] Cross-reference with this evidence index

## Maintenance

**Update this index when:**
- New KPI artifacts are generated
- Existing artifacts are superseded
- Source labels change
- New validation evidence is added

**Last Updated:** 2026-03-10  
**Owner:** ST-KPI-FIX-001  
**Next Review:** 2026-04-10

---

*This index is maintained as part of the KPI source separation initiative.*  
*See ADR-007 for the canonical rule definition.*
