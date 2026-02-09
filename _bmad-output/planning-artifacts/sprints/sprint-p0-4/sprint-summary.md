# Sprint Summary: Execution (Perps-First)

## Sprint Information

| Field | Value |
|-------|-------|
| **Sprint ID** | p0-4 |
| **Sprint Name** | Execution (Perps-First) |
| **Phase** | Phase 1 (Foundation) |
| **Status** | planned |
| **Start Date** | 2026-02-08 |
| **Target Finish** | 2026-05-09 (90-day window) |

## Epics Covered

| Epic ID | Epic Name | Stories | Points |
|---------|-----------|---------|--------|
| EP-EX-001 | Execution (Perps-First) | 3 | 13 |

## Stories

### EP-EX-001: Execution (Perps-First) (3 stories, 13 points)

| Story ID | Title | Points | Priority | Status |
|----------|-------|--------|----------|--------|
| ST-EX-001 | Bybit Demo Paper Trading Integration | 5 | P0-CRITICAL | planned |
| ST-EX-002 | Bitget Live Trading Gating | 4 | P0-CRITICAL | planned |
| ST-EX-003 | Execution Risk Management - Kill Switch | 4 | P0-CRITICAL | planned |

## Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Stories** | 3 |
| **Total Story Points** | 13 |
| **P0-CRITICAL Stories** | 3 |
| **P1-HIGH Stories** | 0 |

## Dependencies

### Internal Dependencies
- ST-EX-001 (Bybit Paper) should complete before ST-EX-002 (Bitget Live)
- ST-EX-003 (Kill Switch) can be developed in parallel but must integrate with both

### External Dependencies
- Bybit API credentials (demo environment)
- Bitget API credentials (live trading)
- Exchange connectivity and health monitoring

### Sprint Dependencies
- Sprint p0-2 (Data & Backtesting) must complete - provides data infrastructure
- Sprint p0-3 (Confidence Scoring) should complete - provides confidence filtering
- Paper trading performance data needed before live trading gates

## Success Criteria

1. **All P0-CRITICAL stories completed** (3 stories)
2. **Bybit paper trading operational** - Demo trades executing with KPI tracking
3. **Trade budget enforced** - Max 10% portfolio exposure per trade
4. **Paper kill-switch active** - Triggers on >=10% drawdown
5. **Live trading gated** - Human approval required with promotion packet
6. **Live kill-switch operational** - Triggers on >=15% drawdown, requires re-authorization
7. **Order lifecycle tracked** - Pending, filled, partial, cancelled states visible

## Risk Controls

| Control | Threshold | Action |
|---------|-----------|--------|
| Paper kill-switch | >=10% drawdown | Close all positions, disable paper trading |
| Live kill-switch | >=15% drawdown (24h) | Close all positions, disable live trading |
| Trade budget | 10% per trade | Reject orders exceeding limit |
| Live approval gate | Min 30 days paper, positive Sharpe | Require human approval packet |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Exchange API failures | High | Circuit breaker pattern, fallback to paper |
| Live trading approval delays | Medium | Clear criteria, automated packet generation |
| Kill-switch false triggers | Medium | Configurable thresholds, manual override |
| Order execution latency | Medium | Monitor and alert on latency >5s |

## Notes

- This sprint focuses on perps (perpetual futures) execution only
- Bybit demo paper trading is the first execution environment
- Bitget live trading requires strict gating - no direct path from backtest to live
- Kill-switch is critical for capital preservation - test thoroughly in paper first
- All live trading requires human approval with signed promotion packet
