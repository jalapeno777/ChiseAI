# ICT/SMC Integration Roadmap

## Document Information

| Field            | Value                |
| ---------------- | -------------------- |
| **Document ID**  | ROADMAP-ICT-SMC-001  |
| **Version**      | 2.3.0                |
| **Created**      | 2026-03-24           |
| **Last Updated** | 2026-03-24           |
| **Owner**        | Jarvis (Agent Swarm) |
| **Status**       | Planned              |

## Executive Summary

This roadmap defines the phased integration of ICT (Inner Circle Trader) and SMC (Smart Money Concepts) methodology into the ChiseAI signal generation pipeline. The plan encompasses 37 SP of committed work across 8 sprints (16 weeks), plus 24 SP of deferred expansion work contingent on validation results.

**Key Metrics:**

- **Total Committed SP:** 37
- **Deferred SP:** 24
- **Sprint Duration:** 2 weeks
- **Parallel Workers:** 2-3
- **Estimated Timeline:** 16-18 weeks
- **Go/No-Go Decision:** End of Sprint ICT-S8 (Week 18)

## Background

### Current System

The existing signal generation pipeline uses mathematical indicators (RSI, MACD, Bollinger Bands) combined with Markov chain trend detection. Signals are scored via a confluence algorithm and filtered by confidence thresholds before Discord delivery.

### What's Missing

1. **Structural Context:** No awareness of market structure (BOS/CHoCH)
2. **Zone-Based Analysis:** No tracking of liquidity zones (FVG, Order Blocks)
3. **Volume Imbalance:** No cumulative volume delta analysis
4. **Regime-Awareness:** Fragmented regime detection across modules
5. **Lookahead Safety:** No systematic protection against repainting

### Why ICT/SMC

ICT/SMC provides a price-action-based framework that complements mathematical indicators:

- **Market Structure:** BOS/CHoCH identifies trend continuation vs reversal
- **Liquidity Zones:** FVG and OB mark high-probability reaction areas
- **Volume Analysis:** CVD confirms or diverges from price action
- **Regime Gating:** Structural analysis naturally segments trending vs ranging markets

### Data Source Decisions

| Data Type        | Primary Source                 | Backup Source                   | Auth Required | Notes                            |
| ---------------- | ------------------------------ | ------------------------------- | ------------- | -------------------------------- |
| OHLCV Candles    | Binance fapi                   | Bybit demo                      | No            | Existing infrastructure          |
| Trade Data (CVD) | Binance fapi `/fapi/v1/trades` | Bybit `/v5/market/recent-trade` | No            | Public endpoint, 1000 trades/req |
| Order Book       | Binance fapi `/fapi/v1/depth`  | Existing                        | No            | Already implemented              |
| Funding Rate     | Existing connectors            | —                               | No            | Already implemented              |

**Rationale for Binance as primary CVD source:**

- Highest volume exchange globally → most representative trade data
- Public trades endpoint (`/fapi/v1/trades`) requires no API key
- Returns 1,000 trades per request with `isBuyerMaker` field for side detection
- Existing Binance client (`exchange_data/binance/client.py`) already uses `fapi.binance.com` base URL
- WebSocket trade streaming available via `wss://fstream.binance.com/ws/<symbol>@trade`

## Plan Overview

### Phase Breakdown

| Phase     | Name                         | SP           | Stories | Timeline     |
| --------- | ---------------------------- | ------------ | ------- | ------------ |
| 0A        | Bug Fixes & Data Foundation  | 3.5          | 4       | Week 1-2     |
| 0B        | Infrastructure Prerequisites | 8            | 4       | Week 3-6     |
| 1         | Core ICT Components          | 12           | 4       | Week 7-10    |
| 1.5       | Component Validation         | 1            | 1       | Week 11      |
| 2         | Confluence v2 Integration    | 10           | 5       | Week 12-14   |
| 3+4       | Statistical Validation       | 5.5          | 4       | Week 15-18   |
| 5         | Post-Validation Expansion    | 24           | 8       | Deferred     |
| **Total** |                              | **37 (+24)** | **30**  | **18 weeks** |

## Sprint Breakdown

### Sprint ICT-S1 (Weeks 1-2): Phase 0A — Bug Fixes & Data Assessment

**Stories:**

- **ST-ICT-001:** Fix DISCORD_BYPASS_CONFIDENCE_FILTER env var risk (1 SP)
  - Acceptance Criteria:
    - Remove or guard the bypass in signal_emitter.py:136
    - Add audit logging for any bypass event
    - Feature flag controls bypass availability
- **ST-ICT-002:** Fix rate-limited signals marked ACTIONABLE (1 SP)
  - Acceptance Criteria:
    - Add RATE_LIMITED status to SignalStatus enum
    - signal_generator.py:486-488 sets RATE_LIMITED not ACTIONABLE
    - Tests verify correct status assignment
- **ST-ICT-003:** Add explicit order_book_imbalance weight + validate wiring (1 SP)
  - Acceptance Criteria:
    - Add "order_flow" entry to indicator_weights defaults
    - Validate order_flow module integration with confluence scorer
    - Test confluence calculation with order flow component
- **ST-ICT-004:** CVD Data Availability Assessment (0.5 SP)
  - Acceptance Criteria:
    - Binance fapi `/fapi/v1/trades` endpoint verified accessible without API key
    - Trade data includes `isBuyerMaker` field for side detection
    - Bybit `/v5/market/recent-trade` identified as backup source
    - Note: "trades_url property added to BinanceConfig class"

**Total:** 3.5 SP  
**Milestone:** All pre-existing bugs fixed, CVD data path confirmed

> **Note:** Since Binance client already exists at `exchange_data/binance/client.py`, CVD data assessment is lower effort (0.5 SP confirmed). Primary source identified as Binance fapi `/fapi/v1/trades` with no API key required.

---

### Sprint ICT-S2 (Weeks 3-4): Phase 0B Part 1 — Regime & Zone Foundation

**Stories:**

- **ST-ICT-005:** MarketRegimeClassifier — Consolidate regime detection (2 SP)
  - Acceptance Criteria:
    - Unify MarketRegime, VolatilityRegime, Markov is_trending() into single classifier
    - Output: TRENDING, RANGING, VOLATILE, UNKNOWN
    - Backward compatible with existing regime checks
- **ST-ICT-006:** Zone Persistence Architecture (2 SP)
  - Acceptance Criteria:
    - Define Zone data model (UUID, type, timeframe, token, price_range, creation_time, status, mitigation_history)
    - Redis storage: sorted sets + hashes
    - Zone lifecycle: ACTIVE → TESTED → MITIGATED → INVALIDATED
    - Storage estimate validation (~600KB for 10 tokens × 6 TFs × 20 zones)

**Total:** 4 SP  
**Milestone:** Regime detection unified, zone store operational

---

### Sprint ICT-S3 (Weeks 5-6): Phase 0B Part 2 — Safety & Design

**Stories:**

- **ST-ICT-007:** Repainting/Lookahead Guard Framework (2 SP)
  - Acceptance Criteria:
    - lookahead_guard decorator validates no future data in indicator computation
    - repainting_detector test suite: 0% tolerance for incremental consistency violations
    - Applied to all existing indicators as baseline
- **ST-ICT-008:** Two-Layer Pipeline Design Document (2 SP)
  - Acceptance Criteria:
    - Layer 1: Structural Context documented (SMC)
    - Layer 2: Signal Confirmation documented (Mathematical)
    - Confluence modification: Layer 1 provides +/- modifiers to Layer 2 weights
    - Architecture review and approval

**Total:** 4 SP  
**Milestone:** Safety framework ready, architecture documented

---

### Sprint ICT-S4 (Weeks 7-8): Phase 1 Part 1 — Market Structure & CVD

**Stories:**

- **ST-ICT-009:** Market Structure Detector — BOS/CHoCH (3 SP)
  - Acceptance Criteria:
    - Swing pivot detection algorithm implemented
    - BOS classification (continuation) vs CHoCH (reversal)
    - Regime-gated: only emit in TRENDING regime
    - Non-repainting: use confirmed bars only
    - Test accuracy >90% on labeled data
- **ST-ICT-010:** Cumulative Volume Delta (CVD) (3 SP)
  - Acceptance Criteria:
    - Tick-level volume delta calculation (buy volume - sell volume)
    - CVD divergence detection (price vs CVD)
    - Binance client at `exchange_data/binance/client.py`
    - `get_recent_trades(symbol, limit)` method added to Binance client
    - `trades_url` property added to `BinanceConfig` pointing to `/fapi/v1/trades`
    - Fallback to order book delta if trade API unavailable

**Total:** 6 SP  
**Milestone:** Two most impactful ICT signals operational

---

### Sprint ICT-S5 (Weeks 9-10): Phase 1 Part 2 — FVG & Order Blocks

**Stories:**

- **ST-ICT-011:** Fair Value Gap Detector (2.5 SP)
  - Acceptance Criteria:
    - 3-candle FVG detection (bullish: candle3.low > candle1.high)
    - 50% CE (Consequent Encroachment) tracking
    - Mitigation modes: wick-based and close-based
    - Regime-gated: EMIT in TRENDING, SUPPRESS in RANGING
    - Zone lifecycle integration with 0B.2 persistence
- **ST-ICT-012:** Order Block Detector (2.5 SP)
  - Acceptance Criteria:
    - Bullish OB: last bearish candle before bullish impulse
    - Bearish OB: last bullish candle before bearish impulse
    - Volume confirmation (optional enhancement)
    - Smart mitigation: invalidated on close beyond zone
    - Regime-gated: EMIT in TRENDING, SUPPRESS in RANGING
    - Zone lifecycle integration

**Total:** 5 SP  
**Milestone:** All 4 core ICT signals operational

---

### Sprint ICT-S6 (Weeks 11-12): Phase 1.5 + Phase 2 Part 1

**Stories:**

- **ST-ICT-013:** Component Validation Framework (1 SP)
  - Acceptance Criteria:
    - Per-component paper shadow test (50+ signals, 1 week)
    - Success criteria: directional accuracy >52%
    - Pass → proceed to Phase 2; Fail → flag for redesign
- **ST-ICT-014:** Two-Layer Confluence Scorer (3 SP)
  - Acceptance Criteria:
    - Implement two-layer architecture from 0B.4 design
    - Layer 1 provides regime modifiers to Layer 2 weights
    - Backward compatibility: Layer 2 alone produces same output
    - Test coverage >85%

**Total:** 4 SP  
**Milestone:** Components validated, new scorer operational

---

### Sprint ICT-S7 (Weeks 13-14): Phase 2 Part 2 — Integration

**Stories:**

- **ST-ICT-015:** ICT Signal Registration (2 SP)
  - Acceptance Criteria:
    - Register BOS/CHoCH, CVD, FVG, OB in indicator registry
    - Define indicator_weights entries for ICT indicators
    - Wire ICT signals through signal_aggregator.py
- **ST-ICT-016:** ICT Signal Emission Integration (2 SP)
  - Acceptance Criteria:
    - Add ICT context to Discord messages (active zones, structural bias)
    - Add ICT context to dashboard payloads
    - Maintain backward compatibility with existing format
- **ST-ICT-017:** ML Feedback Analyzer Integration (2 SP)
  - Acceptance Criteria:
    - Route ICT zone events to ml/feedback/analyzer.py
    - Track win rate per zone type per regime per token
    - Add ICT-specific ECE calibration buckets
- **ST-ICT-018:** Feature Flag Implementation (1 SP)
  - Acceptance Criteria:
    - ICT_CONFLUENCE_ENABLED config flag
    - When false: reverts to Layer 2 only (baseline behavior)
    - Tested before Phase 2 deployment

**Total:** 7 SP  
**Milestone:** ICT fully integrated with feature flag, backward compatible

---

### Sprint ICT-S8 (Weeks 15-18): Phase 3 — Validation (4-week sprint)

**Stories:**

- **ST-ICT-019:** Hypothesis Design & Test Framework (1.5 SP)
  - Acceptance Criteria:
    - Null hypothesis: ICT signals add zero alpha
    - Control group: existing mathematical indicators only
    - Treatment group: mathematical + ICT with regime gating
    - Power analysis: minimum 100 signals per group
- **ST-ICT-020:** Paper Trading Data Collection (2 SP)
  - Acceptance Criteria:
    - 4+ weeks paper trading with both groups
    - Automated data collection pipeline
    - Early stopping: stop if p>0.3 after 50 signals
- **ST-ICT-021:** Statistical Analysis & Significance Testing (1.5 SP)
  - Acceptance Criteria:
    - Two-proportion z-test or Fisher's exact test
    - Bonferroni correction for multiple testing
    - MDE: 2% edge
    - Decision: Confirm edge / Partial edge / Null confirmed
- **ST-ICT-022:** Rollback Procedures (0.5 SP)
  - Acceptance Criteria:
    - Test ICT_CONFLUENCE_ENABLED=false reversion
    - Document rollback procedures for each failure scenario

**Total:** 5.5 SP  
**Milestone:** Statistical validation complete, GO/NO-GO decision

---

## Risk Register

| Risk                        | Impact | Likelihood | Mitigation                                              |
| --------------------------- | ------ | ---------- | ------------------------------------------------------- |
| CVD data unavailable        | High   | Medium     | Use order book delta as proxy; defer CVD to Phase 5     |
| Repainting in indicators    | High   | Low        | Lookahead guard framework; 0% tolerance testing         |
| Component validation fails  | Medium | Medium     | Fallback to existing indicators; flag for redesign      |
| Statistical validation null | Medium | Medium     | Feature flag disable; maintain backward compatibility   |
| Integration conflicts       | Medium | Low        | Feature flag isolation; incremental deployment          |
| Performance degradation     | Low    | Low        | Shadow testing; latency monitoring; rollback capability |

## Success Criteria and Decision Gates

### Phase 0A Gate

- All pre-existing bugs resolved
- CVD data availability confirmed
- **Decision:** Proceed to Phase 0B / Defer CVD

### Phase 0B Gate

- MarketRegimeClassifier operational
- Zone persistence architecture validated
- Lookahead guard framework passing tests
- Two-layer design approved
- **Decision:** Proceed to Phase 1 / Redesign architecture

### Phase 1 Gate

- 4 core ICT signals operational
- Non-repainting validation passed
- **Decision:** Proceed to Phase 1.5 / Fix repainting issues

### Phase 1.5 Gate

- Component shadow testing complete
- Directional accuracy >52% per component
- **Decision:** Proceed to Phase 2 / Remove failing components

### Phase 2 Gate

- Two-layer confluence scorer operational
- Feature flag tested and functional
- Backward compatibility verified
- **Decision:** Deploy to paper / Fix integration issues

### Phase 3 Gate (FINAL)

- Statistical validation complete (4+ weeks data)
- Alpha confirmed (p<0.05, effect size >2%)
- **Decision:** Promote to Phase 5 expansion / Disable ICT features

## Phase 5: Deferred Expansion (24 SP)

Only proceeds if Phase 3 confirms ICT adds alpha.

| Story      | Title                                 | SP  |
| ---------- | ------------------------------------- | --- |
| ST-ICT-023 | Dynamic weight adjustment             | 3   |
| ST-ICT-024 | Zone-to-signal mapping                | 3   |
| ST-ICT-025 | Cross-timeframe zone awareness        | 2   |
| ST-ICT-026 | Liquidity Sweeps                      | 2   |
| ST-ICT-027 | Premium/Discount Zones                | 2   |
| ST-ICT-028 | Full ML pipeline integration          | 8   |
| ST-ICT-029 | StrongSystem hypothesis integration   | 2   |
| ST-ICT-030 | Neuro-symbolic explainability for ICT | 2   |

## Rollback Plan

### Immediate Rollback

```bash
# Disable ICT features
redis-cli SET chiseai:feature:ict_confluence:enabled false

# Verify fallback to baseline
python3 scripts/validation/verify_baseline_scorer.py
```

### Per-Scenario Rollback

| Scenario                | Trigger                  | Action                                  |
| ----------------------- | ------------------------ | --------------------------------------- |
| Repainting detected     | Lookahead guard failure  | Disable specific indicator; notify team |
| Performance degradation | Latency >500ms           | Disable Layer 1; use Layer 2 only       |
| Validation null         | p>0.05 after 100 signals | Disable ICT; maintain baseline          |
| Critical bug            | Production error         | Feature flag disable; emergency hotfix  |

## Dependency Graph

```
Phase 0A ──┬──► Phase 0B ──┬──► Phase 1 ───┬──► Phase 1.5 ───┬──► Phase 2 ───┬──► Phase 3+4
           │               │               │                 │               │
           │               ├──► ST-ICT-005  │                 │               │
           │               ├──► ST-ICT-006  │                 │               │
           │               ├──► ST-ICT-007  │                 │               │
           │               └──► ST-ICT-008  │                 │               │
           │                                │                 │               │
           ├──► ST-ICT-001                  │                 │               │
           ├──► ST-ICT-002                  │                 │               │
           ├──► ST-ICT-003                  │                 │               │
           └──► ST-ICT-004 ─────────────────┘                 │               │
                                                              │               │
                                            Phase 1:          │               │
                                            ├──► ST-ICT-009   │               │
                                            ├──► ST-ICT-010   │               │
                                            ├──► ST-ICT-011   │               │
                                            └──► ST-ICT-012 ──┘               │
                                                                              │
                                            Phase 1.5: ST-ICT-013             │
                                                                              │
                                            Phase 2:                          │
                                            ├──► ST-ICT-014                   │
                                            ├──► ST-ICT-015                   │
                                            ├──► ST-ICT-016                   │
                                            ├──► ST-ICT-017                   │
                                            └──► ST-ICT-018                   │
                                                                              │
                                            Phase 3+4:                        │
                                            ├──► ST-ICT-019                   │
                                            ├──► ST-ICT-020                   │
                                            ├──► ST-ICT-021                   │
                                            └──► ST-ICT-022                   │
                                                                              │
                                            Phase 5 (deferred):               │
                                            └──► ST-ICT-023..030              │
```

## Change Log

| Date       | Change                                        | Author |
| ---------- | --------------------------------------------- | ------ |
| 2026-03-24 | Initial creation with full sprint plan (v2.2) | Jarvis |
