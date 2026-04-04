# ST-ICT-S9-001 CHoCH Architecture Findings

**Story**: ST-ICT-S9-001  
**Decision Reference**: AD-ST-ICT-S9-001-20260403T120100Z-aria  
**Date**: 2026-04-03  
**Status**: ARCHITECTURE FINDINGS DOCUMENTED — DEFER with evidence

---

## 1. Root Cause

The CHoCH (Change of Character) detection logic uses the comparison:

```python
swing_high.price > swing_low.price
```

This comparison is **trivially true** in virtually all market conditions because:

- Swing highs are, by definition, price pivots that are higher than surrounding pivots
- Swing lows are, by definition, price pivots that are lower than surrounding pivots
- Therefore `swing_high.price > swing_low.price` is always true in any trending or ranging market

The logic was intended to detect when price _breaks_ a structure level, but instead it merely confirms that highs are higher than lows — which is always the case and provides no signal.

---

## 2. Honest Baseline

| Metric         | Value                                                |
| -------------- | ---------------------------------------------------- |
| Detection Rate | **42.3%**                                            |
| Source         | senior-dev pass 1 evaluation (before CHoCH "fix")    |
| Interpretation | Near-random detection — barely better than coin flip |

This baseline represents the system's actual structural detection capability when evaluated without the broken CHoCH overlay.

---

## 3. Inflated Baseline

| Metric         | Value                                              |
| -------------- | -------------------------------------------------- |
| Detection Rate | **98.1%**                                          |
| Source         | merlin pass evaluation                             |
| Interpretation | Test artifact from trivially-true comparison logic |

This inflated number is not a real improvement — it is an artifact of the broken comparison `swing_high.price > swing_low.price` which is always true, making CHoCH detection appear near-universal when it is actually non-functional.

---

## 4. Recommended Redesign

CHoCH detection must compare the **break of a structure level** (price crossing a previously established swing high/low) rather than comparing two arbitrary swing prices.

### Option (a): Explicit Structure Level Tracking

- Track structure levels explicitly in state
- Detect CHoCH when price **closes beyond** a previously established swing high/low
- Requires: Level management state, close price vs. level comparison

### Option (b): Higher-Timeframe Confirmation

- Use HTF (e.g., 4H, Daily) to establish key structure levels
- Detect CHoCH on lower timeframe when price breaks HTF structure
- Requires: Multi-timeframe price tracking, HTF level extraction

### Option (c): Multi-Timeframe Structure Analysis (Recommended)

- Confirm CHoCH only when lower-TF structure breaks in direction of higher-TF bias
- Example: On 15Min chart, CHoCH detected only when:
  1. Price breaks a 15Min swing high/low
  2. 4H/H4 timeframe shows alignment with the break direction
- Requires: HTF bias calculation, TF alignment check

### Comparison Table

| Option               | Complexity | Signal Quality | Implementation Effort |
| -------------------- | ---------- | -------------- | --------------------- |
| (a) Explicit Levels  | Medium     | High           | Medium                |
| (b) HTF Confirmation | Medium     | High           | Medium                |
| (c) MTF Alignment    | High       | Highest        | High                  |

---

## 5. Estimated Effort

| Phase               | Effort   | Description                           |
| ------------------- | -------- | ------------------------------------- |
| Architecture Review | ~1SP     | Design decision on Option (a)/(b)/(c) |
| Implementation      | ~3SP     | Core logic redesign                   |
| Validation          | ~1SP     | Backtest + live validation            |
| **Total**           | **~5SP** | Requires architecture review first    |

---

## 6. Target Phase

**EP-ICT-007 Phase 2**

This work is deferred until EP-ICT-007 Phase 2 based on Aria decision AD-ST-ICT-S9-001-20260403T120100Z-aria.

---

## 7. Decision Reference

```
Decision: DEFER with evidence. Accept 42.3% honest baseline.
Root Cause: CHoCH comparison logic trivially true (swing_high.price > swing_low.price)
Decision Reference: AD-ST-ICT-S9-001-20260403T120100Z-aria
```

**Decision Summary**: The 42.3% honest baseline is accepted as the current CHoCH capability. The 98.1% figure from merlin pass is a test artifact. CHoCH redesign is deferred to EP-ICT-007 Phase 2 with ~5SP estimated effort.

---

## Evidence Links

- Root Cause Analysis: `docs/evidence/ST-ICT-S9-001-rc.md`
- Aria Decision: `AD-ST-ICT-S9-001-20260403T120100Z-aria` (Redis)
- Story: `ST-ICT-S9-001`

---

_Document created: 2026-04-03_  
_Author: quickdev_  
_Classification: Architecture Findings_
