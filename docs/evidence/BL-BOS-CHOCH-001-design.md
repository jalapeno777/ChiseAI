# BL-BOS-CHOCH-001: BOS/CHoCH Redesign — Design Document

**Story**: BL-BOS-CHOCH-001
**Design Option**: (a) Explicit StructureLevel State Tracking
**Date**: 2026-04-12
**Status**: DRAFT — awaiting review
**Parent Story**: ST-ICT-S9-001
**Evidence**: ST-ICT-S9-001-rc.md, ST-ICT-S9-001-choch-architecture-findings.md

---

## 1. Problem Statement

The current `BOSCHoCHClassifier` suffers from three interconnected issues identified in the root cause analysis (ST-ICT-S9-001-rc.md):

1. **Duplicate method**: `_check_bearish_break` is defined twice (lines 335–404 and 406–479). The second definition shadows the first, so only the simpler version runs.
2. **No explicit trend state**: The classifier has no concept of "current trend direction." It infers BOS vs CHoCH purely from which pivot type is broken, without tracking whether the market is structurally bullish or bearish.
3. **Structure levels not tracked across events**: `current_structure_high` and `current_structure_low` are only updated inside the classify loop as local variables and are not used to gate subsequent detections. Each break is evaluated independently against all prior swings.

Result: **42.3% honest detection rate** with bearish BOS and no-break scenarios at 0% accuracy.

---

## 2. Design Decision: Option (a) — Explicit StructureLevel State Tracking

From the architecture findings (ST-ICT-S9-001-choch-architecture-findings.md), three options were evaluated:

| Option               | Complexity | Signal Quality | Implementation Effort |
| -------------------- | ---------- | -------------- | --------------------- |
| (a) Explicit Levels  | Medium     | High           | Medium                |
| (b) HTF Confirmation | Medium     | High           | Medium                |
| (c) MTF Alignment    | High       | Highest        | High                  |

**Decision: Option (a)** — Explicit StructureLevel state tracking.

Rationale:

- Medium complexity with high signal quality — best effort-to-quality ratio.
- No multi-timeframe dependency (avoids HTF data pipeline changes).
- Can be validated against existing scenario test suite without new data sources.
- Option (c) can be layered on top later as an enhancement.

---

## 3. Core Definitions

### 3.1 BOS (Break of Structure)

> Price **closes beyond** an established swing high/low in the **same direction** as the current trend.

| Trend Direction | BOS Trigger Condition                                  |
| --------------- | ------------------------------------------------------ |
| Bullish         | Price closes above a previously established swing high |
| Bearish         | Price closes below a previously established swing low  |

### 3.2 CHoCH (Change of Character)

> Price **closes beyond** an established swing high/low in the **opposite direction** of the current trend.

| Trend Direction | CHoCH Trigger Condition                                                 |
| --------------- | ----------------------------------------------------------------------- |
| Bullish         | Price closes below a previously established swing low (structure low)   |
| Bearish         | Price closes above a previously established swing high (structure high) |

### 3.3 BOS vs CHoCH Prioritization

**BOS always takes priority over CHoCH.**

When a single price movement could qualify as both BOS and CHoCH (e.g., in a transitional market), the event is classified as BOS. This preserves the principle that trend continuation signals take precedence over reversal signals until the structure clearly reverses.

Implementation: evaluate BOS candidates first; only if no BOS candidate exists, evaluate CHoCH candidates.

---

## 4. StructureLevel State Management

### 4.1 State Variables

```
TrendDirection: enum { BULLISH, BEARISH, UNDEFINED }

active_structure_high: StructureLevel | None
    - The most recent swing high that defines the upper structural boundary
    - Updated when a new higher swing high forms OR when price closes above it (BOS)

active_structure_low: StructureLevel | None
    - The most recent swing low that defines the lower structural boundary
    - Updated when a new lower swing low forms OR when price closes below it (BOS)

last_bos_direction: "bullish" | "bearish" | None
    - Direction of the most recent BOS event
    - Used to determine current TrendDirection
```

### 4.2 State Transition Rules

```
Initial state:
    TrendDirection = UNDEFINED
    active_structure_high = None
    active_structure_low = None
    last_bos_direction = None

On new swing high detected:
    if active_structure_high is None OR swing.price > active_structure_high.price:
        active_structure_high = StructureLevel(swing)
    # Note: does NOT change TrendDirection

On new swing low detected:
    if active_structure_low is None OR swing.price < active_structure_low.price:
        active_structure_low = StructureLevel(swing)
    # Note: does NOT change TrendDirection

On BOS detected (bullish):
    TrendDirection = BULLISH
    last_bos_direction = "bullish"
    active_structure_high = StructureLevel(triggering_swing)

On BOS detected (bearish):
    TrendDirection = BEARISH
    last_bos_direction = "bearish"
    active_structure_low = StructureLevel(triggering_swing)

On CHoCH detected:
    TrendDirection remains unchanged (CHoCH is a signal, not a confirmation)
    # TrendDirection only changes on BOS confirmation
```

### 4.3 Classification Logic

For each candle close that exceeds a structure level:

```
function classify_break(trend_direction, break_type):
    if break_type == SAME_DIRECTION_AS_TREND:
        return BOS
    elif break_type == OPPOSITE_DIRECTION_OF_TREND:
        return CHoCH
    elif trend_direction == UNDEFINED:
        # No established trend; treat any break as BOS
        return BOS
```

---

## 5. Duplicate Method Removal

### Current Issue

`_check_bearish_break` is defined **twice** in `bos_choch.py`:

1. **Lines 335–404**: Full implementation with candidate collection and BOS priority
2. **Lines 406–479**: Simpler implementation using only most-recent swing

Python resolves this by using the **second definition** (the simpler one), which:

- Only checks the single most recent swing_low and swing_high
- Loses the candidate collection and priority logic from the first version
- Contributes to the 0% bearish BOS accuracy

### Resolution

Remove the second (shadow) definition entirely (lines 406–479). The first definition (lines 335–404) already implements the correct BOS-priority logic.

---

## 6. Interface Specification

### 6.1 Retained Types (unchanged)

```python
class BOSCHoCHType(Enum):
    BULLISH_BOS = "bullish_bos"
    BEARISH_BOS = "bearish_bos"
    BULLISH_CHOCH = "bullish_choch"
    BEARISH_CHOCH = "bearish_choch"
    NONE = "none"

@dataclass
class StructureLevel:
    pivot: SwingPivot
    price: float
    broken: bool = False
    broken_at: int | None = None

@dataclass
class BOSCHoCH:
    event_type: BOSCHoCHType
    broken_level: StructureLevel
    break_index: int
    break_price: float
    timestamp: datetime
    confirmation_index: int
    is_bos: bool
    strength: float
```

### 6.2 New: TrendDirection Enum

```python
class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    UNDEFINED = "undefined"
```

### 6.3 Modified: BOSCHoCHClassificationResult

```python
@dataclass
class BOSCHoCHClassificationResult:
    events: list[BOSCHoCH]
    bullish_bos_events: list[BOSCHoCH]
    bearish_bos_events: list[BOSCHoCH]
    bullish_choch_events: list[BOSCHoCH]
    bearish_choch_events: list[BOSCHoCH]
    current_structure_high: StructureLevel | None
    current_structure_low: StructureLevel | None
    last_bos_direction: str | None
    # NEW:
    trend_direction: TrendDirection  # Current tracked trend state
```

### 6.4 Modified: BOSCHoCHClassifier.classify()

```python
def classify(
    self,
    pivot_result: SwingPivotDetectionResult,
    data: list[OHLCVData],
) -> BOSCHoCHClassificationResult:
    """
    Classify BOS and CHoCH events from swing pivots.

    Algorithm:
    1. Build structure levels from swing pivots
    2. For each candle, check if close exceeds active structure levels
    3. Classify break as BOS or CHoCH based on trend direction
    4. Update state on BOS detection

    Args:
        pivot_result: Result from SwingPivotDetector
        data: Original OHLCV data

    Returns:
        BOSCHoCHClassificationResult with all events and current structure
    """
```

### 6.5 Modified: Internal Methods

```python
def _update_structure_levels(
    self,
    swing: SwingPivot,
    high: StructureLevel | None,
    low: StructureLevel | None,
) -> tuple[StructureLevel | None, StructureLevel | None]:
    """Update active structure levels when a new swing forms.

    Returns updated (high, low) tuple.
    """

def _classify_break(
    self,
    trend_direction: TrendDirection,
    level_type: str,  # "swing_high" or "swing_low"
    break_direction: str,  # "up" or "down"
) -> BOSCHoCHType:
    """Classify a break as BOS or CHoCH based on trend direction.

    BOS: break in same direction as trend
    CHoCH: break in opposite direction of trend
    UNDEFINED trend: default to BOS
    """

def _check_break(
    self,
    swing: SwingPivot,
    level: StructureLevel,
    data: list[OHLCVData],
) -> tuple[BOSCHoCH, bool] | None:
    """Check if price closes beyond a structure level.

    Unified replacement for separate _check_bullish_break / _check_bearish_break.
    Returns (event, is_bos) or None.
    """
```

---

## 7. Algorithm Pseudocode

```
function classify(pivots, ohlcv_data):
    trend = UNDEFINED
    struct_high = None
    struct_low = None
    events = []
    detected_breaks = set()

    for each pivot in pivots (chronological):
        # Step 1: Update structure levels
        (struct_high, struct_low) = update_structure_levels(pivot, struct_high, struct_low)

        # Step 2: Check for breaks against active levels
        candle = ohlcv_data[pivot.index]

        if struct_high is not None:
            if candle.close > struct_high.price and candle.high > struct_high.price:
                # Price closed above structure high
                if trend == BULLISH or trend == UNDEFINED:
                    event = create_event(BULLISH_BOS, struct_high, pivot)
                elif trend == BEARISH:
                    event = create_event(BULLISH_CHOCH, struct_high, pivot)
                add_event_if_unique(event, detected_breaks, events)

        if struct_low is not None:
            if candle.close < struct_low.price and candle.low < struct_low.price:
                # Price closed below structure low
                if trend == BEARISH or trend == UNDEFINED:
                    event = create_event(BEARISH_BOS, struct_low, pivot)
                elif trend == BULLISH:
                    event = create_event(BEARISH_CHOCH, struct_low, pivot)
                add_event_if_unique(event, detected_breaks, events)

        # Step 3: Update trend direction on BOS
        for event in events_this_iteration:
            if event.is_bos:
                if event.event_type == BULLISH_BOS:
                    trend = BULLISH
                    struct_high = StructureLevel(pivot)
                elif event.event_type == BEARISH_BOS:
                    trend = BEARISH
                    struct_low = StructureLevel(pivot)

    return BOSCHoCHClassificationResult(events, ..., trend_direction=trend)
```

---

## 8. Test Scenario Coverage Targets

### 8.1 Current Baseline

| Category                 | Current      | Target   |
| ------------------------ | ------------ | -------- |
| Aggregate detection rate | 42.3%        | **≥60%** |
| Bullish BOS              | PASSING      | PASSING  |
| Bearish BOS              | 0%           | **≥50%** |
| No-break scenarios       | 0%           | **≥50%** |
| CHoCH scenarios          | Not measured | **≥40%** |

### 8.2 Specific Scenarios Requiring Fix

From ST-ICT-S9-001-rc.md, these scenarios currently fail and must pass after redesign:

| Scenario | Description                    | Expected      | Current |
| -------- | ------------------------------ | ------------- | ------- |
| 015      | Bearish BOS - gradual decline  | Bearish BOS   | FAIL    |
| 018      | Bearish BOS - distribution top | Bearish BOS   | FAIL    |
| 024      | Bearish BOS - tight range      | Bearish BOS   | FAIL    |
| 039      | Bearish CHoCH - double top     | Bearish CHoCH | FAIL    |
| 046      | No break - wide oscillation    | No event      | FAIL    |

### 8.3 New Scenarios to Add

The redesign should be validated against:

1. **Trend transition**: Bullish BOS → CHoCH → Bearish BOS sequence
2. **Ranging market**: Multiple false break attempts with no BOS/CHoCH
3. **Strong trend**: Consecutive BOS events in same direction
4. **CHoCH followed by BOS confirmation**: CHoCH signal, then BOS confirms new trend
5. **UNDEFINED initial state**: First break in market with no prior BOS

---

## 9. Implementation Scope

### In Scope

- Remove duplicate `_check_bearish_break` method
- Add `TrendDirection` enum
- Add trend state tracking to `classify()` method
- Modify break classification to use trend direction
- Add `trend_direction` field to `BOSCHoCHClassificationResult`
- Update/add unit tests to meet ≥60% detection rate target

### Out of Scope

- Multi-timeframe analysis (Option c)
- HTF confirmation (Option b)
- Changes to `SwingPivotDetector`
- Changes to OHLCV data pipeline
- Changes to downstream consumers of `BOSCHoCHClassificationResult`

---

## 10. Risk Assessment

| Risk                                                 | Likelihood | Impact | Mitigation                                                    |
| ---------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------- |
| Trend state lag causes missed CHoCH                  | Medium     | Medium | CHoCH evaluation uses active levels, not lagged state         |
| Removing duplicate method changes behavior           | Low        | High   | First definition already has correct logic; second shadows it |
| UNDEFINED state defaults to BOS may miss early CHoCH | Low        | Low    | First few bars rarely produce meaningful structure events     |
| Existing test expectations conflict with new logic   | Medium     | Medium | Review and update scenario expectations before implementation |

---

## 11. Files to Modify

| File                                                 | Change                                                           |
| ---------------------------------------------------- | ---------------------------------------------------------------- |
| `src/market_analysis/structure/bos_choch.py`         | Remove duplicate method, add TrendDirection, refactor classify() |
| `tests/test_bos_choch_classifier.py` (or equivalent) | Add/modify tests for ≥60% target                                 |

---

## 12. Evidence Links

- Root Cause: `docs/evidence/ST-ICT-S9-001-rc.md`
- Architecture Findings: `docs/evidence/ST-ICT-S9-001-choch-architecture-findings.md`
- Parent Story: `ST-ICT-S9-001`

---

_Document created: 2026-04-12_
_Author: dev (subagent)_
_Classification: Architecture Design Document_
