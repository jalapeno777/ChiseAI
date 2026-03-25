# ICT Layer 1: Structural Context (SMC)

## Document Information

| Field            | Value                |
| ---------------- | -------------------- |
| **Document ID**  | ARCH-ICT-LAYER1-001  |
| **Version**      | 1.0.0                |
| **Created**      | 2026-03-25           |
| **Last Updated** | 2026-03-25           |
| **Owner**        | Jarvis (Agent Swarm) |
| **Status**       | Implemented          |
| **Story ID**     | ST-ICT-008           |

---

## Overview

Layer 1 implements the Structural Context component of the ICT/SMC (Smart Money Concepts) methodology. This layer provides market structure awareness and liquidity zone detection that establishes the contextual framework within which Layer 2 mathematical signals are evaluated.

**Purpose:** Layer 1 answers the question "Where are we in the market?" by identifying structural position, key price levels, and institutional activity zones.

---

## Components

### 1. Market Structure Detector

**Description:** Identifies Break of Structure (BOS) and Change of Character (CHoCH) patterns to determine trend direction and potential reversals.

**Implementation Requirements:**

- Swing pivot detection algorithm identifies local highs and lows
- BOS Classification: Continuation move that breaks previous swing structure
- CHoCH Classification: Reversal move that breaks previous swing structure
- Non-repainting: Uses confirmed bars only (closed candles)
- Regime-gated: Only emits signals in TRENDING regime

**Data Flow:**

```
OHLCV Candles → Swing Pivot Detection → Structure Classification → Market Structure Output
                                               ↓
                                         Trend Bias Signal
```

**Output Schema:**

```python
@dataclass
class MarketStructureOutput:
    regime: MarketRegime  # TRENDING, RANGING, VOLATILE, UNKNOWN
    trend_bullish: bool
    last_swing_high: float
    last_swing_low: float
    bos_level: float | None  # Break of Structure level
    choh_level: float | None  # Change of Character level
    structure_age_bars: int  # Bars since last significant structure
```

**Thresholds:**

- Minimum swing size: 5 pips (configurable per token)
- Confirmation bars: 1 (close beyond swing point)
- Structure lookback: 50 bars default

---

### 2. Order Block Detector

**Description:** Identifies institutional order zones where significant buying or selling occurred, creating potential support/resistance areas.

**Types:**

- **Bullish Order Block:** Last bearish candle before a bullish impulse
- **Bearish Order Block:** Last bullish candle before a bearish impulse

**Implementation Requirements:**

- Detect the "trigger candle" (impulse move following the OB)
- Mark the OB zone as price range between trigger candle open/close
- Smart mitigation: Invalidate when close exceeds zone
- Volume confirmation (optional enhancement)
- Regime-gated: SUPPRESS in RANGING, EMIT in TRENDING

**Data Flow:**

```
OHLCV + Volume → Trigger Candle Detection → OB Zone Identification → Order Block Zone
                                              ↓
                                        Zone Status: ACTIVE | TESTED | MITIGATED | INVALIDATED
```

**Output Schema:**

```python
@dataclass
class OrderBlock:
    id: UUID
    block_type: Literal["BULLISH", "BEARISH"]
    token: str
    timeframe: Timeframe
    trigger_candle_time: datetime
    high: float
    low: float
    trigger_impulse: float  # Size of impulse move
    status: ZoneStatus  # ACTIVE, TESTED, MITIGATED, INVALIDATED
    mitigation_history: list[datetime]
    created_at: datetime
```

**Thresholds:**

- Minimum impulse size: 10 pips
- OB zone width: Trigger candle body + 50% buffer
- Invalidation: Close beyond OB zone high/low

---

### 3. Fair Value Gap (FVG) Detector

**Description:** Identifies gaps in price where volume was insufficient to establish fair value, creating mean-reversion opportunities.

**Detection Rules:**

- **Bullish FVG:** candle3.low > candle1.high (gap up)
- **Bearish FVG:** candle3.high < candle1.low (gap down)

**Implementation Requirements:**

- 3-candle pattern analysis
- 50% CE (Consequent Encroachment) tracking for mitigation
- Mitigation modes: wick-based and close-based
- Regime-gated: EMIT in TRENDING, SUPPRESS in RANGING

**Data Flow:**

```
OHLCV Candles → 3-Candle Pattern Analysis → FVG Detection → FVG Zone
                                                        ↓
                                                  50% CE Tracking
                                                        ↓
                                                  Zone Status Update
```

**Output Schema:**

```python
@dataclass
class FairValueGap:
    id: UUID
    gap_type: Literal["BULLISH", "BEARISH"]
    token: str
    timeframe: Timeframe
    high: float
    low: float
    middle: float  # 50% level
    created_at: datetime
    mitigated: bool
    mitigation_price: float | None
    status: ZoneStatus
```

**Thresholds:**

- Minimum gap size: 3 pips
- 50% CE level: (high + low) / 2
- Wick-based mitigation: Price crosses via wick
- Close-based mitigation: Candle closes beyond gap

---

### 4. Breaker Block Detector

**Description:** Identifies when previous structure is re-established after a mitigation, indicating potential continuation.

**Detection Rules:**

- Previous structure (OB or FVG) was mitigated
- Price returns to test the broken structure
- Rejection occurs at the breaker block level

**Implementation Requirements:**

- Track mitigation events on existing zones
- Detect return tests to broken structure levels
- Confirm rejection/acceptance at breaker block
- Update zone status accordingly

**Data Flow:**

```
Zone Lifecycle Events → Mitigation Detection → Return Test → Breaker Block Confirmation
                                                    ↓
                                              Rejection/Acceptance
                                                    ↓
                                              Structure Re-established / Invalidated
```

**Output Schema:**

```python
@dataclass
class BreakerBlock:
    id: UUID
    original_zone_id: UUID  # Reference to the zone that was mitigated
    breaker_type: Literal["BULLISH", "BEARISH"]
    token: str
    timeframe: Timeframe
    high: float
    low: float
    test_bar: datetime
    rejection_confirmed: bool
    created_at: datetime
```

---

## Zone Lifecycle

All Layer 1 zones follow this state machine:

```
┌─────────┐     price action     ┌─────────┐
│  ACTIVE │─────────────────────►│ TESTED  │
└─────────┘     touches zone     └─────────┘
     │                                   │
     │           ┌──────────────────────┘
     │           │ close beyond zone
     ▼           ▼
┌───────────────┐
│   MITIGATED   │◄────────── return test rejected
└───────────────┘
     │
     │ breaker block formed
     ▼
┌───────────────┐
│ INVALIDATED   │◄────────── sustained break
└───────────────┘
```

**State Transitions:**

| Current State | Event                     | Next State  |
| ------------- | ------------------------- | ----------- |
| ACTIVE        | Price touches zone        | TESTED      |
| TESTED        | Price closes beyond zone  | MITIGATED   |
| MITIGATED     | Return test rejected      | INVALIDATED |
| ACTIVE/TESTED | Sustained break confirmed | INVALIDATED |

---

## Data Flow Diagram

```
                                    ┌──────────────────────────────────────────────┐
                                    │                  LAYER 1                     │
                                    │           Structural Context (SMC)          │
                                    └──────────────────────────────────────────────┘
                                                            │
         ┌──────────────────────────────────────────────────┼──────────────────────────────────────────────────┐
         │                                                  │                                                  │
         ▼                                                  ▼                                                  ▼
┌─────────────────────┐                        ┌─────────────────────┐                        ┌─────────────────────┐
│ Market Structure    │                        │   Order Block       │                        │   Fair Value Gap    │
│ Detector            │                        │   Detector          │                        │   Detector          │
├─────────────────────┤                        ├─────────────────────┤                        ├─────────────────────┤
│ • Swing pivots     │                        │ • Trigger candles   │                        │ • 3-candle pattern  │
│ • BOS/CHoCH        │                        │ • OB zones          │                        │ • Gap identification│
│ • Trend bias       │                        │ • Volume (optional) │                        │ • 50% CE tracking   │
└─────────┬───────────┘                        └──────────┬──────────┘                        └──────────┬──────────┘
          │                                                │                                                │
          └────────────────────────┬───────────────────────┘                                                │
                                   │                                                                       │
                                   ▼                                                                       │
                        ┌─────────────────────┐                                                            │
                        │  Zone Lifecycle      │                                                            │
                        │  Manager             │                                                            │
                        │  (Redis-backed)      │                                                            │
                        └──────────┬──────────┘                                                            │
                                   │                                                                       │
                                   ▼                                                                       │
                        ┌─────────────────────┐                                                            │
                        │  Structure Context   │                                                            │
                        │  Aggregator          │                                                            │
                        │  • Bias: BULL/BEAR   │                                                            │
                        │  • Active zones      │                                                            │
                        │  • Strength score    │                                                            │
                        └──────────┬──────────┘                                                            │
                                   │                                                                       │
                                   │  Layer 1 Output (Context)                                             │
                                   ▼                                                                       │
                        ┌─────────────────────────────────────────────┐                                    │
                        │  market_structure: TRENDING/RANGING           │                                    │
                        │  trend_bias: BULLISH/BEARISH                 │                                    │
                        │  active_zones: List[Zone]                     │                                    │
                        │  structure_strength: 0.0-1.0                   │                                    │
                        │  bos_level: float | None                      │                                    │
                        │  choch_level: float | None                    │                                    │
                        └─────────────────────────────────────────────┘                                    │
                                   │                                                                       │
                                   └────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                                    ┌───────────────────────┐
                                    │  Layer 2 (Confluence)  │
                                    │  Receives as input    │
                                    │  for weighting        │
                                    └───────────────────────┘
```

---

## Integration with Regime Classifier

Layer 1 components are gated by the MarketRegimeClassifier (ST-ICT-005):

```python
def should_emit_signal(component: str, regime: MarketRegime) -> bool:
    """Determine if ICT component should emit based on regime."""
    emit_in = {
        "market_structure": {MarketRegime.TRENDING},
        "order_block": {MarketRegime.TRENDING},
        "fvg": {MarketRegime.TRENDING},
        "breaker_block": {MarketRegime.TRENDING, MarketRegime.RANGING},
    }
    suppress_in = {
        "market_structure": {MarketRegime.RANGING, MarketRegime.VOLATILE},
        "order_block": {MarketRegime.RANGING, MarketRegime.VOLATILE},
        "fvg": {MarketRegime.RANGING, MarketRegime.VOLATILE},
        "breaker_block": set(),
    }
    return regime in emit_in.get(component, set()) and regime not in suppress_in.get(component, set())
```

---

## Redis Storage Schema

**Key Patterns:**

```
ict:zones:{token}:{timeframe}     → Sorted Set (zone IDs by creation time)
ict:zone:{zone_id}               → Hash (zone data)
ict:structure:{token}:{timeframe} → Hash (current structure state)
```

**Zone Hash Fields:**

```
type, token, timeframe, high, low, middle, status,
created_at, updated_at, mitigation_history, block_type
```

**TTL Policy:**

- Active zones: 4 hours
- Mitigated zones: 24 hours
- Invalidated zones: 1 hour

---

## Backward Compatibility

Layer 1 components are additive to the existing pipeline:

- Existing mathematical indicators continue to function independently
- Layer 1 output is optional context for the confluence scorer
- Feature flag `ICT_CONFLUENCE_ENABLED` controls Layer 1 integration
- When disabled: System operates on Layer 2 mathematical signals only

---

## Dependencies

| Component              | Dependency Story | Notes                      |
| ---------------------- | ---------------- | -------------------------- |
| MarketRegimeClassifier | ST-ICT-005       | Unify regime detection     |
| Zone Persistence       | ST-ICT-006       | Redis storage architecture |
| Lookahead Guard        | ST-ICT-007       | Repainting protection      |

---

## References

- ICT/SMC Integration Roadmap: `docs/roadmaps/ict-smc-integration.md`
- Phase 1 Gate Requirements: Roadmap Section "Phase 1 Gate"
