# ICT Two-Layer Pipeline Architecture

## Document Information

| Field            | Value                 |
| ---------------- | --------------------- |
| **Document ID**  | ARCH-ICT-PIPELINE-001 |
| **Version**      | 1.0.0                 |
| **Created**      | 2026-03-25            |
| **Last Updated** | 2026-03-25            |
| **Owner**        | Jarvis (Agent Swarm)  |
| **Status**       | Implemented           |
| **Story ID**     | ST-ICT-008            |

---

## Executive Summary

This document describes the two-layer pipeline architecture for ICT/SMC signal generation. The architecture separates structural context (Layer 1) from mathematical confirmation (Layer 2), enabling ICT concepts to enhance existing signals while maintaining backward compatibility.

**Key Design Principles:**

1. **Layer 2 is the foundation** - Must function independently as the baseline
2. **Layer 1 is additive** - Provides contextual modifiers, never creates signals alone
3. **Confluence modification** - Layer 1 adjusts Layer 2 weights based on structural context
4. **Backward compatible** - Feature flag ensures instant reversion to Layer 2 only

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SIGNAL GENERATION PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              MARKET DATA INPUT                                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │   │
│  │  │   OHLCV     │  │   Trades    │  │ Order Book  │  │    Funding  │                   │   │
│  │  │  Candles    │  │    (CVD)   │  │   Depth     │  │    Rate     │                   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                   │   │
│  └─────────┼────────────────┼────────────────┼────────────────┼───────────────────────────┘   │
│            │                │                │                │                                │
│            └────────────────┼────────────────┼────────────────┘                                │
│                             │                │                                                 │
│                             ▼                ▼                                                 │
│              ┌──────────────────────────┐  ┌──────────────────────────┐                       │
│              │      Regime Classifier   │  │    Zone Persistence      │                       │
│              │      (ST-ICT-005)        │  │    Manager (ST-ICT-006)   │                       │
│              │  TRENDING/RANGING/VOLATILE│  │  ACTIVE/TESTED/MITIGATED │                       │
│              └────────────┬─────────────┘  └──────────────┬───────────┘                       │
│                           │                               │                                    │
│                           ▼                               ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐     │
│  │                                    LAYER 1: STRUCTURAL CONTEXT                       │     │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │     │
│  │  │ Market Structure│  │  Order Blocks   │  │  Fair Value Gap │  │ Breaker Blocks  │    │     │
│  │  │    Detector     │  │    Detector     │  │    Detector     │  │    Detector     │    │     │
│  │  │   (ST-ICT-009)  │  │  (ST-ICT-012)   │  │  (ST-ICT-011)   │  │                 │    │     │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │     │
│  │           └───────────────────┼───────────────────┘                      │              │     │
│  │                               ▼                                              │              │     │
│  │                    ┌─────────────────────┐                                  │              │     │
│  │                    │  Structure Context  │                                  │              │     │
│  │                    │    Aggregator       │                                  │              │     │
│  │                    │ • Trend bias         │                                  │              │     │
│  │                    │ • Active zones       │                                  │              │     │
│  │                    │ • Structure strength │                                  │              │     │
│  │                    └──────────┬──────────┘                                  │              │     │
│  └────────────────────────────────┼──────────────────────────────────────────────┘              │
│                                  │                                                                     │
│                                  │  Layer 1 Output: Context                                            │
│                                  ▼                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐             │
│  │                                    LAYER 2: SIGNAL CONFIRMATION                      │             │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                     │             │
│  │  │    Technical    │  │    Statistical  │  │     Risk        │                     │             │
│  │  │   Indicators    │  │    Validation   │  │    Metrics      │                     │             │
│  │  │  RSI/MACD/BB    │  │ Coherence/Div.  │  │  SL/TP/Pos Size │                     │             │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                     │             │
│  │           └───────────────────┼───────────────────┘                                │             │
│  │                               ▼                                                     │             │
│  │                    ┌─────────────────────┐                                           │             │
│  │                    │   Confirmation      │                                           │             │
│  │                    │      Gate           │                                           │             │
│  │                    └──────────┬──────────┘                                           │             │
│  │                               │                                                      │             │
│  └───────────────────────────────┼──────────────────────────────────────────────────────┘             │
│                                  │                                                                    │
│                                  │  Layer 2 Output: Confirmed Signal                                     │
│                                  ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐             │
│  │                                 CONFLUENCE MODIFICATION                              │             │
│  │                                                                                      │             │
│  │   ┌────────────────────────────┐    ┌────────────────────────────┐                 │             │
│  │   │     Layer 1 Context        │    │    Layer 2 Signal          │                 │             │
│  │   │ • Trend alignment (+/-)   │    │ • Confluence score        │                 │             │
│  │   │ • Zone proximity (+/-)    │    │ • Direction               │                 │             │
│  │   │ • Structure strength (×)  │    │ • Risk parameters         │                 │             │
│  │   └────────────┬───────────────┘    └─────────────┬──────────────┘                 │             │
│  │                │                                   │                               │             │
│  │                └──────────────────┬──────────────────┘                               │             │
│  │                                   ▼                                                 │             │
│  │                        ┌─────────────────────┐                                      │             │
│  │                        │  Modifier Engine    │                                      │             │
│  │                        │                     │                                      │             │
│  │                        │  Apply rules:       │                                      │             │
│  │                        │  • Trend ± modifier │                                      │             │
│  │                        │  • Zone ± modifier  │                                      │             │
│  │                        │  • Structure × mult │                                      │             │
│  │                        └──────────┬──────────┘                                      │             │
│  │                                   │                                                 │             │
│  │                                   ▼                                                 │             │
│  │                        ┌─────────────────────┐                                      │             │
│  │                        │   Modified Signal   │                                      │             │
│  │                        │   (Final Output)    │                                      │             │
│  │                        └─────────────────────┘                                      │             │
│  └──────────────────────────────────────────────────────────────────────────────────────┘             │
│                                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────┐
                              │   Signal Emitter / Discord   │
                              │         Delivery             │
                              └─────────────────────────────┘
```

---

## Confluence Modification Rules

### Rule Priority

When Layer 1 and Layer 2 conflict, the following priority rules apply:

| Priority | Layer 1 Condition           | Layer 2 Condition | Result                           |
| -------- | --------------------------- | ----------------- | -------------------------------- |
| 1        | Strong trend against signal | Strong coherence  | Signal rejected (trend wins)     |
| 2        | Price in opposing zone      | High confluence   | Score reduced 50%                |
| 3        | Trend aligns with signal    | Low coherence     | Score maintained (trend carries) |
| 4        | No structural context       | Any               | Pure Layer 2 behavior            |

### Modification Formulas

#### Trend Alignment Modifier

```python
def trend_modifier(trend_bias: TrendBias, signal_dir: SignalDirection) -> float:
    """Calculate trend alignment modifier."""
    if trend_bias == TrendBias.BULLISH and signal_dir == SignalDirection.BULLISH:
        return +0.10  # Trend supports bullish signal
    elif trend_bias == TrendBias.BEARISH and signal_dir == SignalDirection.BEARISH:
        return +0.10  # Trend supports bearish signal
    elif trend_bias == TrendBias.BULLISH and signal_dir == SignalDirection.BEARISH:
        return -0.20  # Trend opposes bearish signal
    elif trend_bias == TrendBias.BEARISH and signal_dir == SignalDirection.BULLISH:
        return -0.20  # Trend opposes bullish signal
    return 0.0  # No trend bias or neutral
```

#### Zone Proximity Modifier

```python
def zone_modifier(zones: list[Zone], entry_price: float, direction: SignalDirection) -> float:
    """Calculate zone proximity modifier."""
    modifier = 0.0
    for zone in zones:
        if zone.contains(entry_price):
            if zone.type == direction:
                modifier += 0.05  # Favorable zone
            else:
                modifier -= 0.08  # Opposing zone
    return modifier
```

#### Structure Strength Multiplier

```python
def structure_multiplier(structure_strength: float) -> float:
    """Calculate structure-based multiplier."""
    if structure_strength >= 0.7:
        return 1.2  # Strong structure amplifies
    elif structure_strength <= 0.3:
        return 0.8  # Weak structure dampens
    return 1.0  # Normal
```

#### Combined Modifier

```python
def total_modifier(
    trend_bias: TrendBias,
    signal_dir: SignalDirection,
    zones: list[Zone],
    entry_price: float,
    structure_strength: float
) -> float:
    """Calculate total Layer 1 modifier for Layer 2 signal."""
    t_mod = trend_modifier(trend_bias, signal_dir)
    z_mod = zone_modifier(zones, entry_price, signal_dir)
    s_mult = structure_multiplier(structure_strength)

    # Combined: additive modifiers then multiply
    additive_mod = t_mod + z_mod
    final_modifier = (1.0 + additive_mod) * s_mult

    # Clamp to prevent extreme values
    return max(0.5, min(1.5, final_modifier))
```

### Confluence Matrix

| Layer 1 Trend | Layer 2 Signal | Zone Alignment | Structure | Final Score Adjustment |
| ------------- | -------------- | -------------- | --------- | ---------------------- |
| BULLISH       | BULLISH        | Favorable      | Strong    | +20% (1.2×)            |
| BULLISH       | BULLISH        | Favorable      | Normal    | +15% (1.15×)           |
| BULLISH       | BULLISH        | Neutral        | Strong    | +10% (1.1×)            |
| BULLISH       | BULLISH        | Neutral        | Normal    | +10% (1.1×)            |
| BULLISH       | BEARISH        | Opposing       | Strong    | -50% (0.5×)            |
| BULLISH       | BEARISH        | Opposing       | Normal    | -40% (0.6×)            |
| NEUTRAL       | BULLISH        | Favorable      | Normal    | +5%                    |
| NEUTRAL       | BULLISH        | Neutral        | Normal    | 0%                     |
| RANGING       | ANY            | ANY            | ANY       | 0% (suppressed)        |

---

## Backward Compatibility Plan

### Feature Flag Architecture

```python
# Configuration
ICT_CONFLUENCE_ENABLED: bool = False  # Default to disabled for safety

# Signal computation
def compute_final_signal(market_data: MarketData) -> Signal:
    layer1_context = compute_layer1_context(market_data) if ICT_CONFLUENCE_ENABLED else None

    layer2_signal = compute_layer2_signal(market_data)

    if layer1_context is not None:
        return apply_confluence_modification(layer2_signal, layer1_context)

    return layer2_signal  # Pure Layer 2
```

### Migration Path

```
Phase 1: ICT_CONFLUENCE_ENABLED = False (all traffic)
    └── Baseline: Pure Layer 2 signals

Phase 2: ICT_CONFLUENCE_ENABLED = True (shadow mode)
    └── Layer 1 computed but not applied
    └── Logging: modifier values, score differences

Phase 3: Gradual rollout (10% → 50% → 100%)
    └── Monitor: error rates, signal quality

Phase 4: Full deployment
    └── ICT_CONFLUENCE_ENABLED = True for all
```

### Rollback Procedures

| Scenario                    | Trigger                    | Action                           |
| --------------------------- | -------------------------- | -------------------------------- |
| Performance degradation     | Latency > 500ms            | Set ICT_CONFLUENCE_ENABLED=false |
| Signal quality drop         | Win rate drop > 5%         | Set ICT_CONFLUENCE_ENABLED=false |
| Statistical validation fail | p > 0.05 after 100 signals | Set ICT_CONFLUENCE_ENABLED=false |
| Critical bug                | Exception in Layer 1 code  | Set ICT_CONFLUENCE_ENABLED=false |

**Rollback Command:**

```bash
redis-cli SET chiseai:feature:ict_confluence:enabled false
```

---

## Integration Points

### 1. Indicator Registry

All ICT components must register in the indicator registry:

```python
@dataclass
class ICTIndicatorRegistry:
    market_structure: MarketStructureDetector
    order_blocks: OrderBlockDetector
    fair_value_gaps: FairValueGapDetector

    indicators: dict[str, Indicator] = {
        "market_structure": market_structure,
        "order_block": order_blocks,
        "fvg": fair_value_gaps,
    }
```

### 2. Signal Aggregator Integration

```python
# In signal_aggregator.py
class SignalAggregator:
    def __init__(self, config: SignalAggregatorConfig):
        self.layer1 = Layer1Components() if ICT_CONFLUENCE_ENABLED else None
        self.layer2 = Layer2Components()
        self.confluence_modifier = ConfluenceModifier() if ICT_CONFLUENCE_ENABLED else None

    def aggregate(self, market_data: MarketData) -> list[Signal]:
        layer1_ctx = self.layer1.compute(market_data) if self.layer1 else None
        layer2_signals = self.layer2.compute(market_data)

        if layer1_ctx:
            return [self.confluence_modifier.apply(s, layer1_ctx) for s in layer2_signals]
        return layer2_signals
```

### 3. Discord Message Integration

ICT context is added to Discord messages:

```python
@dataclass
class DiscordSignalMessage:
    # Standard fields
    token: str
    direction: SignalDirection
    entry: float
    sl: float
    tp: float
    rr: float
    confidence: ConfidenceLevel

    # ICT Context (optional)
    ict_context: ICTContext | None = None

@dataclass
class ICTContext:
    trend_bias: str
    active_zones: list[str]
    structure_strength: float
    notable_levels: list[float]
```

### 4. Dashboard Payload Integration

```python
@dataclass
class DashboardSignalPayload:
    signal: Signal
    layer1_context: Layer1Context | None  # Included when ICT_CONFLUENCE_ENABLED
```

---

## Data Flow Summary

```
Market Data (OHLCV, Trades, Order Book)
         │
         ▼
┌────────────────┐
│ Regime Check   │ ──── determines if ICT components emit
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌────────────────┐
│    Layer 1     │     │    Layer 2     │
│  Structural    │     │  Mathematical  │
│   Context      │     │   Signals      │
└───────┬────────┘     └───────┬────────┘
        │                    │
        │    ┌────────────────┘
        │    │
        ▼    ▼
┌────────────────────┐
│ Confluence Modifier│
│  Apply rules:      │
│  • Trend ±         │
│  • Zone ±         │
│  • Structure ×     │
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Final Signal      │
│  (Modified)        │
└────────────────────┘
```

---

## Error Handling

### Layer 1 Failures

| Error Type                | Behavior                                        |
| ------------------------- | ----------------------------------------------- |
| Zone computation error    | Log error, continue with Layer 2 only           |
| Structure detection error | Log error, set structure_strength=1.0 (neutral) |
| Regime detection error    | Default to RANGING (suppress ICT)               |
| Redis unavailable         | Use in-memory fallback, log warning             |

### Layer 2 Failures

| Error Type                   | Behavior                                     |
| ---------------------------- | -------------------------------------------- |
| Indicator computation error  | Exclude indicator from confluence, continue  |
| Statistical validation error | Log error, skip validation (use base signal) |
| Risk metric error            | Use conservative defaults (1.5× ATR SL/TP)   |

---

## Testing Strategy

### Unit Tests

- Layer 1: Each detector tested independently
- Layer 2: Each indicator and validation tested independently
- Confluence Modifier: All rule combinations tested

### Integration Tests

- Full pipeline with mock market data
- Layer 1 disabled vs enabled comparison
- Feature flag toggle behavior

### Shadow Testing

- Production traffic: Layer 2 computed with and without Layer 1
- Compare signal quality metrics
- Monitor modifier distribution

---

## Performance Considerations

| Component           | Latency Budget | Mitigation                   |
| ------------------- | -------------- | ---------------------------- |
| Regime Classifier   | < 5ms          | Cached, updated on bar close |
| Zone Detection      | < 10ms         | Incremental updates          |
| Indicator Compute   | < 20ms         | Parallel computation         |
| Confluence Modifier | < 5ms          | Simple arithmetic            |
| **Total Budget**    | **< 50ms**     |                              |

---

## Dependencies

| Story      | Component                 | Blocking                    |
| ---------- | ------------------------- | --------------------------- |
| ST-ICT-005 | MarketRegimeClassifier    | All Layer 1 components      |
| ST-ICT-006 | Zone Persistence          | Order Blocks, FVG, Breakers |
| ST-ICT-007 | Lookahead Guard           | All components              |
| ST-ICT-009 | Market Structure Detector | Layer 1 aggregation         |
| ST-ICT-010 | CVD Integration           | Volume-based validation     |
| ST-ICT-011 | FVG Detector              | Layer 1 zone detection      |
| ST-ICT-012 | Order Block Detector      | Layer 1 zone detection      |
| ST-ICT-014 | Two-Layer Confluence      | Confluence modifier         |
| ST-ICT-018 | Feature Flag              | Rollback capability         |

---

## References

- Layer 1 Architecture: `docs/architecture/ict-layer-1-smc.md`
- Layer 2 Architecture: `docs/architecture/ict-layer-2-confirmation.md`
- ICT/SMC Integration Roadmap: `docs/roadmaps/ict-smc-integration.md`
- Phase 2 Gate Criteria: Roadmap Section "Phase 2 Gate"
