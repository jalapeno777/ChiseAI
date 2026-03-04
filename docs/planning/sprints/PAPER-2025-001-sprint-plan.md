# Bybit-Only Paper Trading Sprint Plan
## Sprint ID: PAPER-2025-001
## Target Date: March 14, 2026 (Launch Readiness)
## Epic: EP-PAPER-002 (New Epic for Bybit-Only Paper Trading)

---

## Executive Summary

This sprint plan addresses the gap between the existing paper trading infrastructure and production-ready Bybit-only paper trading. The focus is on three critical invariants:

1. **One Active Trade Per Symbol**: Enforce maximum 1 open position per symbol at any time
2. **Signal Provenance & Reason Codes**: Track why every entry and exit occurred
3. **Comprehensive Trade Journal**: Capture complete trade lifecycle with audit trail

**Total Story Points**: 47 points across 14 stories
**Estimated Duration**: 3 weeks (with parallel workstreams)
**Team Size**: 4 agents (senior-dev, dev, critic, merlin oversight)

---

# A) SPRINT BACKLOG

## Epic: EP-PAPER-002 - Bybit-Only Paper Trading Production Readiness

**Epic ID**: EP-PAPER-002  
**Status**: Planned  
**Target Sprint**: PAPER-2025-001  
**Total Points**: 47  
**Dependencies**: EP-PAPER-001 (completed), EP-LAUNCH-001 (completed)

---

## Story 1: PAPER-2025-001 - One-Trade-Per-Symbol Invariant Engine

**Points**: 3  
**Priority**: P0-CRITICAL  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Implement a robust invariant engine that enforces maximum one active trade per symbol at any given time. This prevents over-concentration and ensures clean position management.

### Tasks

#### Task 1.1: Symbol Position Registry (1 point)
**Owner**: senior-dev  
**Scope**: `src/execution/paper/symbol_registry.py`

- Create `SymbolPositionRegistry` class
- Redis-backed state storage with atomic operations
- Track: symbol → position_id mapping
- Handle edge cases: position close race conditions, partial fills
- TTL on registry entries to prevent stale state

**Acceptance Criteria**:
```python
# Registry provides atomic check-and-set operations
registry = SymbolPositionRegistry(redis_client)

# Returns True if no position exists, False otherwise
acquired = await registry.try_acquire_symbol(
    symbol="BTCUSDT",
    position_id="pos-123",
    ttl_seconds=3600
)

# Release symbol when position closes
await registry.release_symbol("BTCUSDT", "pos-123")

# Query current position for symbol
current_pos = await registry.get_position_for_symbol("BTCUSDT")
```

**Tests**:
- Unit: `tests/test_execution/test_paper/test_symbol_registry.py`
  - Test concurrent acquisition attempts
  - Test TTL expiration
  - Test release with wrong position_id (should fail)
  - Test Redis failure handling

---

#### Task 1.2: Orchestrator Integration (1 point)
**Owner**: senior-dev  
**Depends On**: Task 1.1  
**Scope**: `src/execution/paper/orchestrator.py`

- Integrate SymbolPositionRegistry into PaperTradingOrchestrator
- Check registry BEFORE risk validation
- Skip signal with SKIPPED status if symbol already has position
- Add metric: `paper:symbols:positions_blocked`

**Acceptance Criteria**:
```python
# In process_signal(), before risk validation:
if await self.symbol_registry.get_position_for_symbol(signal.token):
    logger.info(f"Symbol {signal.token} already has active position, skipping")
    return PaperTradeResult(
        signal=signal,
        status=TradeStatus.SKIPPED,
        skip_reason="SYMBOL_ALREADY_HAS_POSITION",
        correlation_id=correlation_id,
    )
```

**Tests**:
- Integration: `tests/test_execution/test_paper/test_one_symbol_invariant.py`
  - Test second signal for same symbol is skipped
  - Test position close allows new signal
  - Test metrics are recorded

---

#### Task 1.3: Grafana Dashboard Panel (1 point)
**Owner**: dev  
**Depends On**: Task 1.2  
**Scope**: `infrastructure/grafana/dashboards/paper_trading.json`

- Panel: "Active Symbols with Positions"
- Panel: "Signals Skipped - Symbol Conflict"
- Alert: High skip rate (>10% in 5 min window)

**Acceptance Criteria**:
- Dashboard shows real-time count of symbols with positions
- Table shows which symbols have active positions
- Alert fires if skip rate exceeds threshold

---

### Story Acceptance Criteria
- [ ] SymbolPositionRegistry implemented with atomic operations
- [ ] Orchestrator checks registry before processing signals
- [ ] Second signal for same symbol is SKIPPED with proper reason code
- [ ] Metrics exported to InfluxDB
- [ ] Grafana panels visible and functional
- [ ] All tests pass (unit + integration)

---

## Story 2: PAPER-2025-002 - Signal Provenance Tracking System

**Points**: 5  
**Priority**: P0-CRITICAL  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Implement comprehensive signal provenance tracking that captures the complete lineage of every signal from generation through execution, including why signals were accepted, rejected, or skipped.

### Tasks

#### Task 2.1: Provenance Data Model (1 point)
**Owner**: senior-dev  
**Scope**: `src/execution/paper/provenance.py`

- Create `SignalProvenance` dataclass
- Track: signal_id, generation_time, source_strategy, confidence_factors, market_conditions
- Reason codes enum: SIGNAL_ACCEPTED, RISK_REJECTED, LOW_CONFIDENCE, SYMBOL_OCCUPIED, KILL_SWITCH_ACTIVE

**Acceptance Criteria**:
```python
@dataclass
class SignalProvenance:
    provenance_id: str
    signal_id: str
    generation_timestamp: datetime
    source_strategy: str
    source_version: str
    confidence_factors: dict[str, float]  # RSI, MACD, Markov, etc.
    market_conditions: dict[str, Any]  # volatility_regime, trend_state
    
@dataclass
class ExecutionDecision:
    decision_id: str
    signal_id: str
    decision_timestamp: datetime
    decision_reason: DecisionReason  # Enum
    decision_details: dict[str, Any]  # Additional context
```

---

#### Task 2.2: Provenance Capture Pipeline (2 points)
**Owner**: senior-dev  
**Depends On**: Task 2.1  
**Scope**: `src/execution/paper/provenance_pipeline.py`

- Hook into orchestrator process_signal()
- Capture provenance at each decision point:
  1. Signal received (generation provenance)
  2. Kill-switch check (if rejected)
  3. Symbol registry check (if skipped)
  4. Risk validation (if rejected)
  5. Order placement (if executed)
- Persist to Redis with 30-day TTL
- Export to InfluxDB for Grafana

**Acceptance Criteria**:
```python
# Provenance is captured for every signal
provenance = await self.provenance_pipeline.capture_signal(
    signal=signal,
    stage=ProvenanceStage.RECEIVED
)

# Decision reasons are tracked
if result.status == TradeStatus.REJECTED:
    await self.provenance_pipeline.capture_decision(
        signal_id=signal.signal_id,
        decision=DecisionReason.RISK_REJECTED,
        details={"violations": assessment.violations}
    )
```

---

#### Task 2.3: Exit Reason Tracking (1 point)
**Owner**: dev  
**Depends On**: Task 2.2  
**Scope**: `src/execution/paper/exit_reasons.py`

- Define exit reason codes:
  - STOP_LOSS_HIT
  - TAKE_PROFIT_HIT
  - SIGNAL_REVERSE (opposite signal received)
  - TIME_LIMIT (max hold time)
  - MANUAL_CLOSE
  - KILL_SWITCH
  - RISK_REDUCTION
- Capture exit reasons when positions close
- Link exit to entry via signal_id/provenance_id

**Acceptance Criteria**:
```python
# Exit reasons captured in position close
await self.position_tracker.close_position(
    position_id=pos_id,
    exit_price=current_price,
    reason=ExitReason.SIGNAL_REVERSE,
    linked_signal_id=new_signal.signal_id  # The signal that caused exit
)
```

---

#### Task 2.4: Provenance Query API (1 point)
**Owner**: dev  
**Depends On**: Task 2.2  
**Scope**: `src/execution/paper/provenance_api.py`

- REST API endpoints:
  - GET `/api/v1/provenance/signal/{signal_id}`
  - GET `/api/v1/provenance/position/{position_id}`
  - GET `/api/v1/provenance/symbol/{symbol}?start=&end=`
- Support filtering by date range, symbol, decision reason

**Acceptance Criteria**:
```python
# Query provenance for a signal
curl /api/v1/provenance/signal/sig-123

# Response
{
  "signal_id": "sig-123",
  "generation": {...},
  "decisions": [
    {"stage": "RECEIVED", "timestamp": "..."},
    {"stage": "RISK_VALIDATION", "decision": "REJECTED", "reason": "MAX_POSITION_SIZE"}
  ]
}
```

---

### Story Acceptance Criteria
- [ ] Provenance data model defined and documented
- [ ] Every signal has provenance captured at generation
- [ ] Every decision (accept/reject/skip) has reason code
- [ ] Exit reasons linked to entry signals
- [ ] API endpoints functional
- [ ] Data persisted to Redis with 30-day TTL
- [ ] Metrics exported to Grafana

---

## Story 3: PAPER-2025-003 - Comprehensive Trade Journal

**Points**: 8  
**Priority**: P0-CRITICAL  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Build a comprehensive trade journal that captures every detail of trade lifecycle: entries, exits, partial fills, position adjustments, and all associated metadata for post-trade analysis.

### Tasks

#### Task 3.1: Trade Journal Data Model (2 points)
**Owner**: senior-dev  
**Scope**: `src/execution/paper/trade_journal.py`

- Create `TradeJournalEntry` dataclass
- Fields:
  - Entry details: symbol, side, entry_price, entry_time, position_size
  - Signal provenance: signal_id, confidence, strategy
  - Exit details: exit_price, exit_time, exit_reason
  - PnL: realized_pnl, fees, net_pnl
  - Lifecycle: fills[], adjustments[], events[]
  - Metadata: correlation_id, session_id, market_conditions

**Acceptance Criteria**:
```python
@dataclass
class TradeJournalEntry:
    entry_id: str
    symbol: str
    side: str
    entry_price: float
    entry_time: datetime
    position_size: float
    
    # Signal provenance
    signal_id: str
    signal_confidence: float
    signal_strategy: str
    
    # Exit (populated on close)
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: ExitReason | None = None
    exit_signal_id: str | None = None  # Signal that triggered exit
    
    # PnL
    realized_pnl: float = 0.0
    fees: float = 0.0
    net_pnl: float = 0.0
    
    # Lifecycle
    fills: list[FillRecord] = field(default_factory=list)
    events: list[TradeEvent] = field(default_factory=list)
    
    # Audit
    correlation_id: str = ""
    session_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

---

#### Task 3.2: Journal Persistence Layer (2 points)
**Owner**: senior-dev  
**Depends On**: Task 3.1  
**Scope**: `src/execution/paper/journal_store.py`

- Implement `JournalStore` with PostgreSQL backend
- Tables:
  - `trade_journal_entries` - Main trade records
  - `trade_fills` - Individual fill events
  - `trade_events` - Position adjustments, margin changes
- Write-ahead logging to Redis (async buffer)
- Daily rollup and archival

**Acceptance Criteria**:
```python
# Journal store operations
store = JournalStore(postgres_pool, redis_client)

# Create entry on position open
entry = await store.create_entry(
    position=position,
    signal=signal,
    correlation_id=corr_id
)

# Update on each fill
await store.record_fill(entry_id, fill_event)

# Close entry on position close
await store.close_entry(
    entry_id=entry_id,
    exit_price=price,
    exit_reason=ExitReason.STOP_LOSS_HIT,
    pnl=realized_pnl
)
```

---

#### Task 3.3: Journal Query and Reporting (2 points)
**Owner**: dev  
**Depends On**: Task 3.2  
**Scope**: `src/execution/paper/journal_reports.py`

- Query capabilities:
  - By date range, symbol, strategy, exit reason
  - Aggregate: win rate by strategy, avg hold time, max drawdown per symbol
- Reports:
  - Daily trade summary
  - Strategy performance report
  - Symbol analysis (which symbols perform best)
  - Exit reason analysis (why trades closed)

**Acceptance Criteria**:
```python
# Generate daily report
report = await journal.generate_daily_report(
    date=datetime(2025, 3, 1),
    symbols=["BTCUSDT", "ETHUSDT"]
)

# Report includes
{
  "summary": {
    "total_trades": 25,
    "win_rate": 0.52,
    "total_pnl": 1250.50,
    "avg_hold_time_minutes": 45.2
  },
  "by_symbol": {...},
  "by_exit_reason": {...}
}
```

---

#### Task 3.4: Grafana Trade Journal Dashboard (1 point)
**Owner**: dev  
**Depends On**: Task 3.2  
**Scope**: `infrastructure/grafana/dashboards/trade_journal.json`

- Panels:
  - Recent trades table (last 20)
  - Trade distribution by symbol
  - Win rate by strategy
  - Exit reason breakdown (pie chart)
  - Hold time distribution
  - PnL by entry time (heatmap)

**Acceptance Criteria**:
- Dashboard loads in <3 seconds
- Real-time updates within 10 seconds of trade close
- Drill-down to individual trade details

---

#### Task 3.5: Journal Integrity Tests (1 point)
**Owner**: critic  
**Depends On**: Task 3.2  
**Scope**: `tests/test_execution/test_paper/test_journal_integrity.py`

- Verify every position open creates journal entry
- Verify every fill is recorded
- Verify entry/exit PnL matches
- Verify no orphaned entries (open without close after 7 days)
- Verify data consistency under concurrent operations

---

### Story Acceptance Criteria
- [ ] Trade journal schema created in PostgreSQL
- [ ] Every trade creates journal entry on open
- [ ] Every fill recorded in journal
- [ ] Every exit updates journal with reason and PnL
- [ ] Query API supports filtering and aggregation
- [ ] Grafana dashboard shows trade history
- [ ] Reports generated automatically
- [ ] Integrity tests pass

---

## Story 4: PAPER-2025-004 - Bybit-Only Mode Enforcement

**Points**: 3  
**Priority**: P0-CRITICAL  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Enforce Bybit-only trading mode at the system level. Block any attempts to trade on other venues and ensure all paper trading operations use Bybit market data and simulation parameters.

### Tasks

#### Task 4.1: Bybit-Only Configuration (1 point)
**Owner**: senior-dev  
**Scope**: `src/execution/paper/config.py`

- Add `ALLOWED_VENUES` configuration (default: `["bybit"]`)
- Add venue enforcement flag
- Fail fast on startup if Bybit connector unavailable
- Environment variable: `PAPER_TRADING_VENUES=bybit`

**Acceptance Criteria**:
```python
@dataclass
class PaperTradingConfig:
    allowed_venues: list[str] = field(default_factory=lambda: ["bybit"])
    enforce_single_venue: bool = True
    
    def validate_venue(self, venue: str) -> bool:
        if venue not in self.allowed_venues:
            raise VenueNotAllowedError(f"Venue {venue} not in allowed list: {self.allowed_venues}")
        return True
```

---

#### Task 4.2: Venue Enforcement in Orchestrator (1 point)
**Owner**: senior-dev  
**Depends On**: Task 4.1  
**Scope**: `src/execution/paper/orchestrator.py`

- Check venue in process_signal()
- Reject signals with invalid venue
- Ensure order simulator uses Bybit market data only
- Log venue enforcement metrics

**Acceptance Criteria**:
```python
# In process_signal() - early validation
if signal.venue and signal.venue not in self.config.allowed_venues:
    logger.warning(f"Signal venue {signal.venue} not allowed")
    return PaperTradeResult(
        signal=signal,
        status=TradeStatus.REJECTED,
        reject_reason=[f"VENUE_NOT_ALLOWED:{signal.venue}"],
        correlation_id=correlation_id,
    )
```

---

#### Task 4.3: Bybit Market Data Validation (1 point)
**Owner**: dev  
**Depends On**: Task 4.2  
**Scope**: `src/execution/paper/market_data_validator.py`

- Validate all market data comes from Bybit
- Check data freshness (<5 seconds)
- Alert on stale data or non-Bybit sources
- Fail trades if Bybit data unavailable

---

### Story Acceptance Criteria
- [ ] Configuration supports venue allowlist
- [ ] Orchestrator validates signal venue
- [ ] Only Bybit market data used for pricing
- [ ] Non-Bybit signals rejected with clear error
- [ ] Alert on venue violation attempts

---

## Story 5: PAPER-2025-005 - Redis State Consistency Hardening

**Points**: 3  
**Priority**: P0-CRITICAL  
**Owner**: dev  
**Status**: Not Started

### Description
Ensure Redis state remains consistent across restarts, crashes, and concurrent operations. This is critical for maintaining the one-trade-per-symbol invariant.

### Tasks

#### Task 5.1: Redis State Recovery on Startup (1 point)
**Owner**: dev  
**Scope**: `src/execution/paper/state_recovery.py`

- On startup, scan Redis for existing positions
- Reconcile with PostgreSQL journal
- Clear orphaned registry entries
- Recover position tracker state

**Acceptance Criteria**:
```python
# Startup recovery procedure
recovery = StateRecovery(redis_client, postgres_pool)
await recovery.recover_on_startup()

# Steps:
# 1. Load all open positions from tracker
# 2. Verify symbol registry matches positions
# 3. Clear registry entries for closed positions
# 4. Log recovery summary
```

---

#### Task 5.2: Redis Transaction Integrity (1 point)
**Owner**: dev  
**Scope**: `src/execution/paper/redis_transactions.py`

- Use Redis Lua scripts for atomic multi-key operations
- Ensure symbol registry + position tracker updates are atomic
- Handle Redis failures gracefully (circuit breaker)
- Implement retry logic with exponential backoff

---

#### Task 5.3: State Consistency Monitoring (1 point)
**Owner**: critic  
**Depends On**: Task 5.1, Task 5.2  
**Scope**: `src/execution/paper/state_monitor.py`

- Periodic consistency checks (every 60 seconds)
- Verify: symbol registry positions == open positions in tracker
- Verify: no duplicate symbol entries
- Alert on inconsistencies
- Auto-heal minor inconsistencies

---

### Story Acceptance Criteria
- [ ] Startup recovery procedure implemented
- [ ] Redis operations use transactions where needed
- [ ] Consistency monitoring runs continuously
- [ ] Alerts on state mismatches
- [ ] Auto-heal common inconsistencies

---

## Story 6: PAPER-2025-006 - Kill Switch Integration for Paper Trading

**Points**: 2  
**Priority**: P0-CRITICAL  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Integrate the existing kill switch system with paper trading to ensure positions can be immediately closed in emergency situations.

### Tasks

#### Task 6.1: Kill Switch Wire-Up (1 point)
**Owner**: senior-dev  
**Scope**: `src/execution/paper/kill_switch_integration.py`

- Subscribe to kill switch Redis channels
- Close all positions immediately on kill switch trigger
- Record kill switch exit reason in journal
- Export kill switch metrics to Grafana

**Acceptance Criteria**:
```python
# Kill switch listener
class PaperTradingKillSwitchListener:
    async def on_kill_switch_triggered(self, reason: str):
        # Close all positions immediately
        for position in await self.tracker.get_open_positions():
            await self.orchestrator.close_position(
                position.position_id,
                exit_price=await self.get_current_price(position.symbol),
                reason="KILL_SWITCH",
                kill_switch_reason=reason
            )
```

---

#### Task 6.2: Kill Switch Testing (1 point)
**Owner**: critic  
**Scope**: `tests/test_execution/test_paper/test_kill_switch_integration.py`

- Test kill switch closes all positions within 5 seconds
- Test journal records kill switch reason
- Test metrics exported correctly
- Test recovery after kill switch reset

---

### Story Acceptance Criteria
- [ ] Kill switch listener implemented
- [ ] All positions close within 5 seconds of trigger
- [ ] Journal records kill switch exits
- [ ] Grafana shows kill switch state
- [ ] Tests verify emergency closure

---

## Story 7: PAPER-2025-007 - Paper Trading E2E Test Suite

**Points**: 5  
**Priority**: P1-HIGH  
**Owner**: critic  
**Status**: Not Started

### Description
Comprehensive end-to-end test suite that validates the complete paper trading flow with all invariants.

### Tasks

#### Task 7.1: E2E Happy Path Tests (2 points)
**Owner**: critic  
**Scope**: `tests/e2e/test_paper_trading_happy_path.py`

- Test: Signal → Order → Fill → Position → Exit
- Test: Multiple symbols simultaneously
- Test: Partial fills
- Test: Position reversal (opposite signal closes and opens)

---

#### Task 7.2: E2E Invariant Violation Tests (2 points)
**Owner**: critic  
**Scope**: `tests/e2e/test_paper_trading_invariants.py`

- Test: Second signal for same symbol is skipped
- Test: Venue enforcement rejects non-Bybit signals
- Test: Kill switch closes all positions
- Test: Risk limits prevent oversized positions
- Test: Concurrent signals for same symbol (race condition)

---

#### Task 7.3: E2E Recovery Tests (1 point)
**Owner**: critic  
**Scope**: `tests/e2e/test_paper_trading_recovery.py`

- Test: Recovery after orchestrator restart mid-trade
- Test: Redis reconnection handling
- Test: State consistency after crash

---

### Story Acceptance Criteria
- [ ] E2E tests cover happy path
- [ ] E2E tests cover all invariant violations
- [ ] E2E tests cover recovery scenarios
- [ ] Tests run in CI pipeline
- [ ] All tests pass

---

## Story 8: PAPER-2025-008 - Performance and Latency Optimization

**Points**: 3  
**Priority**: P1-HIGH  
**Owner**: dev  
**Status**: Not Started

### Description
Ensure paper trading pipeline meets latency requirements and can handle sustained throughput.

### Tasks

#### Task 8.1: Latency Benchmarking (1 point)
**Owner**: dev  
**Scope**: `tests/performance/test_paper_latency.py`

- Benchmark: Signal → Order placement (<500ms target)
- Benchmark: Order → Fill (<200ms target)
- Benchmark: Total pipeline (<2s target)
- Load test: 100 signals/minute sustained

---

#### Task 8.2: Performance Optimization (1 point)
**Owner**: dev  
**Depends On**: Task 8.1  
**Scope**: Various

- Optimize Redis operations (pipelining)
- Optimize PostgreSQL writes (batching)
- Profile and optimize hot paths
- Implement connection pooling

---

#### Task 8.3: Load Testing (1 point)
**Owner**: critic  
**Depends On**: Task 8.2  
**Scope**: `tests/load/test_paper_trading_load.py`

- Load test with 10 symbols, 1 trade/minute each
- Monitor memory usage, Redis CPU, PostgreSQL connections
- Verify no position leaks under sustained load
- Verify journal consistency under load

---

### Story Acceptance Criteria
- [ ] Latency benchmarks meet targets
- [ ] Load test passes at 10 trades/minute
- [ ] No memory leaks detected
- [ ] Grafana performance metrics visible

---

## Story 9: PAPER-2025-009 - Paper Trading Health Monitoring

**Points**: 2  
**Priority**: P1-HIGH  
**Owner**: dev  
**Status**: Not Started

### Description
Implement comprehensive health monitoring for the paper trading system with alerting on anomalies.

### Tasks

#### Task 9.1: Health Check Service (1 point)
**Owner**: dev  
**Scope**: `src/execution/paper/health_monitor.py`

- Health checks:
  - Redis connectivity
  - PostgreSQL connectivity
  - Bybit market data freshness
  - Symbol registry consistency
  - Position tracker state
- Health endpoint: `/health/paper-trading`

---

#### Task 9.2: Alerting Rules (1 point)
**Owner**: dev  
**Depends On**: Task 9.1  
**Scope**: `infrastructure/grafana/alerts/paper_trading.yaml`

- Alert: No trades in 30 minutes (during market hours)
- Alert: High skip rate (>20%)
- Alert: Position registry inconsistency
- Alert: Stale market data (>10 seconds)
- Alert: Journal write failures

---

### Story Acceptance Criteria
- [ ] Health endpoint returns comprehensive status
- [ ] All critical components monitored
- [ ] Alerts configured and tested
- [ ] Runbook documented for each alert

---

## Story 10: PAPER-2025-010 - Documentation and Runbooks

**Points**: 3  
**Priority**: P1-HIGH  
**Owner**: dev  
**Status**: Not Started

### Description
Create comprehensive documentation and operational runbooks for the paper trading system.

### Tasks

#### Task 10.1: Architecture Documentation (1 point)
**Owner**: dev  
**Scope**: `docs/architecture/paper_trading.md`

- System architecture diagram
- Data flow: Signal → Order → Fill → Position → Journal
- Invariant enforcement explanation
- Component interactions

---

#### Task 10.2: Operational Runbooks (1 point)
**Owner**: dev  
**Scope**: `docs/runbooks/paper_trading/`

- Runbook: Investigating skipped signals
- Runbook: Recovering from position registry inconsistency
- Runbook: Handling kill switch triggers
- Runbook: Journal data export for analysis

---

#### Task 10.3: API Documentation (1 point)
**Owner**: dev  
**Scope**: `docs/api/paper_trading.md`

- Journal query API
- Provenance API
- Health check API
- Metrics and monitoring endpoints

---

### Story Acceptance Criteria
- [ ] Architecture document complete
- [ ] Runbooks cover common scenarios
- [ ] API documentation with examples
- [ ] All docs reviewed and approved

---

## Story 11: PAPER-2025-011 - Trade Journal Analytics

**Points**: 3  
**Priority**: P2-MEDIUM  
**Owner**: dev  
**Status**: Not Started

### Description
Build analytics capabilities on top of the trade journal to enable performance analysis and strategy improvement.

### Tasks

#### Task 11.1: Performance Metrics Calculation (1 point)
**Owner**: dev  
**Scope**: `src/execution/paper/analytics/metrics.py`

- Calculate: Sharpe ratio, Sortino ratio, max drawdown
- Calculate: Win rate, profit factor, expectancy
- Calculate: Average win/loss, R-multiples
- Time-weighted vs trade-weighted returns

---

#### Task 11.2: Strategy Comparison (1 point)
**Owner**: dev  
**Depends On**: Task 11.1  
**Scope**: `src/execution/paper/analytics/strategy_comparison.py`

- Compare performance across strategies
- Statistical significance testing
- Risk-adjusted returns
- Recommendation engine for strategy selection

---

#### Task 11.3: Analytics Dashboard (1 point)
**Owner**: dev  
**Depends On**: Task 11.1, Task 11.2  
**Scope**: `infrastructure/grafana/dashboards/paper_analytics.json`

- Cumulative PnL curve
- Drawdown chart
- Monthly performance table
- Strategy comparison radar chart

---

### Story Acceptance Criteria
- [ ] Performance metrics calculated correctly
- [ ] Strategy comparison reports generated
- [ ] Analytics dashboard functional
- [ ] Metrics validated against known benchmarks

---

## Story 12: PAPER-2025-012 - Backtest Integration

**Points**: 2  
**Priority**: P2-MEDIUM  
**Owner**: senior-dev  
**Status**: Not Started

### Description
Integrate paper trading journal with backtest system for unified performance tracking.

### Tasks

#### Task 12.1: Unified Trade Store (1 point)
**Owner**: senior-dev  
**Scope**: `src/execution/unified_trade_store.py`

- Store backtest trades alongside paper trades
- Tag trades with environment: "backtest", "paper", "live"
- Unified reporting across environments
- Environment comparison analytics

---

#### Task 12.2: Backtest-Paper Correlation (1 point)
**Owner**: dev  
**Depends On**: Task 12.1  
**Scope**: `src/execution/paper/backtest_correlation.py`

- Compare backtest results to paper trading
- Identify slippage differences
- Detect market impact effects
- Validate backtest assumptions

---

### Story Acceptance Criteria
- [ ] Backtest trades stored in journal
- [ ] Unified reports span environments
- [ ] Correlation analysis identifies gaps
- [ ] Backtest accuracy improved based on findings

---

## Story 13: PAPER-2025-013 - Discord Trade Notifications

**Points**: 2  
**Priority**: P2-MEDIUM  
**Owner**: dev  
**Status**: Not Started

### Description
Enhance Discord notifications for paper trading with rich trade details and journal links.

### Tasks

#### Task 13.1: Entry Notification Enhancement (1 point)
**Owner**: dev  
**Scope**: `src/discord_alerts/trade_notifier.py`

- Include signal confidence in entry alerts
- Include stop loss and take profit levels
- Link to trade journal entry
- Include position sizing rationale

---

#### Task 13.2: Exit Notification Enhancement (1 point)
**Owner**: dev  
**Scope**: `src/discord_alerts/trade_notifier.py`

- Include exit reason (stop loss, take profit, signal reverse)
- Include realized PnL and hold time
- Link to complete trade details
- Aggregate daily summary

---

### Story Acceptance Criteria
- [ ] Entry notifications show complete signal details
- [ ] Exit notifications show exit reason and PnL
- [ ] Links to journal entries work
- [ ] Daily summary posted automatically

---

## Story 14: PAPER-2025-014 - Paper Trading Cleanup and Hardening

**Points**: 4  
**Priority**: P1-HIGH  
**Owner**: merlin  
**Status**: Not Started

### Description
Final cleanup, code review, and hardening before production deployment. This story is owned by Merlin as merge authority.

### Tasks

#### Task 14.1: Code Review and Refactoring (1 point)
**Owner**: merlin  
**Scope**: All paper trading code

- Review all changes for code quality
- Ensure consistent error handling
- Verify logging is comprehensive
- Refactor any technical debt

---

#### Task 14.2: Security Review (1 point)
**Owner**: merlin  
**Scope**: All paper trading code

- Review for injection vulnerabilities
- Verify no secrets in logs
- Check SQL injection prevention
- Verify Redis command safety

---

#### Task 14.3: Integration Testing (1 point)
**Owner**: merlin  
**Depends On**: All other stories
**Scope**: `tests/integration/test_paper_full_system.py`

- Full system integration test
- Test with real Bybit market data
- Test for 24-hour burn-in period
- Verify all invariants hold

---

#### Task 14.4: Production Deployment Prep (1 point)
**Owner**: merlin  
**Depends On**: Task 14.3  
**Scope**: Deployment artifacts

- Create deployment checklist
- Prepare rollback procedures
- Document known limitations
- Schedule deployment window

---

### Story Acceptance Criteria
- [ ] All code reviewed and approved
- [ ] Security review passed
- [ ] 24-hour burn-in test passed
- [ ] Deployment checklist complete
- [ ] Rollback procedures tested

---

# B) PARALLELIZATION PLAN

## Execution Batches

### Batch 1: Foundation (Week 1)
**Goal**: Core infrastructure for invariants
**Parallel Workstreams**: 3

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 1.1 Symbol Registry | `src/execution/paper/symbol_registry.py` | None | None | senior-dev |
| 2.1 Provenance Model | `src/execution/paper/provenance.py` | None | None | senior-dev |
| 3.1 Journal Model | `src/execution/paper/trade_journal.py` | None | None | senior-dev |
| 4.1 Bybit Config | `src/execution/paper/config.py` | None | None | senior-dev |
| 5.1 State Recovery | `src/execution/paper/state_recovery.py` | None | None | dev |

**Batch 1 Exit Criteria**:
- All models defined and reviewed
- Database migrations ready
- Unit tests for models passing

---

### Batch 2: Core Integration (Week 1-2)
**Goal**: Integrate invariant enforcement into orchestrator
**Parallel Workstreams**: 4

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 1.2 Orchestrator Integration | `src/execution/paper/orchestrator.py` | `paper:orchestrator` | 1.1 | senior-dev |
| 2.2 Provenance Pipeline | `src/execution/paper/provenance_pipeline.py` | `paper:orchestrator` | 2.1 | senior-dev |
| 3.2 Journal Persistence | `src/execution/paper/journal_store.py` | `db:journal` | 3.1 | senior-dev |
| 4.2 Venue Enforcement | `src/execution/paper/orchestrator.py` | `paper:orchestrator` | 4.1 | senior-dev |
| 5.2 Redis Transactions | `src/execution/paper/redis_transactions.py` | `redis:paper` | 5.1 | dev |

**Lock Coordination**:
- `paper:orchestrator` - Only one agent modifies orchestrator at a time
- `db:journal` - Database schema changes coordinated
- `redis:paper` - Redis key structure changes coordinated

**Batch 2 Exit Criteria**:
- Orchestrator passes all existing tests
- New invariant checks functional
- No regression in existing functionality

---

### Batch 3: Exit Tracking and API (Week 2)
**Goal**: Complete provenance and journal features
**Parallel Workstreams**: 3

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 2.3 Exit Reasons | `src/execution/paper/exit_reasons.py` | None | 2.2 | dev |
| 2.4 Provenance API | `src/execution/paper/provenance_api.py` | None | 2.2 | dev |
| 3.3 Journal Reports | `src/execution/paper/journal_reports.py` | None | 3.2 | dev |
| 3.4 Grafana Journal | `infrastructure/grafana/dashboards/trade_journal.json` | None | 3.2 | dev |

**Batch 3 Exit Criteria**:
- All APIs functional
- Dashboards visible in Grafana
- Reports generate correctly

---

### Batch 4: Observability and Health (Week 2-3)
**Goal**: Monitoring, alerting, and health checks
**Parallel Workstreams**: 3

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 1.3 Grafana Panels | `infrastructure/grafana/dashboards/paper_trading.json` | None | 1.2 | dev |
| 5.3 State Monitor | `src/execution/paper/state_monitor.py` | None | 5.2 | critic |
| 6.1 Kill Switch | `src/execution/paper/kill_switch_integration.py` | `kill_switch:paper` | 1.2, 3.2 | senior-dev |
| 9.1 Health Monitor | `src/execution/paper/health_monitor.py` | None | All | dev |
| 9.2 Alerting Rules | `infrastructure/grafana/alerts/paper_trading.yaml` | None | 9.1 | dev |

**Batch 4 Exit Criteria**:
- All dashboards functional
- Alerts tested and firing
- Health endpoint returns OK

---

### Batch 5: Testing and Quality (Week 3)
**Goal**: Comprehensive test coverage
**Parallel Workstreams**: 2

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 1.4 Symbol Tests | `tests/test_execution/test_paper/test_one_symbol_invariant.py` | None | 1.3 | critic |
| 2.5 Provenance Tests | `tests/test_execution/test_paper/test_provenance.py` | None | 2.4 | critic |
| 3.5 Journal Integrity | `tests/test_execution/test_paper/test_journal_integrity.py` | None | 3.4 | critic |
| 6.2 Kill Switch Tests | `tests/test_execution/test_paper/test_kill_switch_integration.py` | None | 6.1 | critic |
| 7.1 E2E Happy Path | `tests/e2e/test_paper_trading_happy_path.py` | `paper:e2e` | All | critic |
| 7.2 E2E Invariants | `tests/e2e/test_paper_trading_invariants.py` | `paper:e2e` | All | critic |
| 7.3 E2E Recovery | `tests/e2e/test_paper_trading_recovery.py` | `paper:e2e` | All | critic |

**Batch 5 Exit Criteria**:
- Unit test coverage >85%
- E2E tests pass
- All invariant tests pass

---

### Batch 6: Performance and Hardening (Week 3)
**Goal**: Performance validation and final hardening
**Parallel Workstreams**: 2

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 8.1 Latency Benchmarks | `tests/performance/test_paper_latency.py` | None | All | dev |
| 8.2 Performance Opt | Various | None | 8.1 | dev |
| 8.3 Load Tests | `tests/load/test_paper_trading_load.py` | `paper:load` | 8.2 | critic |
| 10.1 Architecture Docs | `docs/architecture/paper_trading.md` | None | All | dev |
| 10.2 Runbooks | `docs/runbooks/paper_trading/` | None | All | dev |
| 14.1 Code Review | All | `paper:review` | All | merlin |
| 14.2 Security Review | All | `paper:security` | All | merlin |

**Batch 6 Exit Criteria**:
- Performance targets met
- Documentation complete
- Security review passed

---

### Batch 7: Final Validation (Week 3-4)
**Goal**: Production readiness validation
**Parallel Workstreams**: 1

| Task | Scope Globs | Locks Required | Depends On | Owner |
|------|-------------|----------------|------------|-------|
| 14.3 Integration Tests | `tests/integration/test_paper_full_system.py` | `paper:prod` | All | merlin |
| 14.4 Deployment Prep | Deployment artifacts | None | 14.3 | merlin |

**Batch 7 Exit Criteria**:
- 24-hour burn-in test passed
- All gates pass
- Ready for production deployment

---

# C) TEST STRATEGY

## Test Pyramid

```
                    /\
                   /  \
                  / E2E\         (14 tests - 5 stories)
                 /------\
                /Integration\    (28 tests - 7 stories)
               /--------------\
              /    Unit Tests   \  (150+ tests - all stories)
             /--------------------\
            /   Component Tests     \(40 tests - 4 stories)
           /---------------------------\
```

## Unit Tests (Coverage Target: 85%)

### Critical Path Tests (Must Pass)

```python
# tests/test_execution/test_paper/test_symbol_registry.py
class TestSymbolRegistry:
    """Test one-trade-per-symbol invariant."""
    
    async def test_acquire_available_symbol(self):
        """Should succeed when symbol has no position."""
        
    async def test_acquire_occupied_symbol_fails(self):
        """Should fail when symbol already has position."""
        
    async def test_concurrent_acquisition_race(self):
        """Only one should win in concurrent acquisition."""
        
    async def test_release_symbol(self):
        """Should allow new acquisition after release."""
        
    async def test_ttl_expiration(self):
        """Should auto-release after TTL."""

# tests/test_execution/test_paper/test_provenance.py
class TestSignalProvenance:
    """Test provenance tracking."""
    
    async def test_provenance_captured_on_signal(self):
        """Every signal should have provenance."""
        
    async def test_decision_reasons_tracked(self):
        """All decisions should have reason codes."""
        
    async def test_exit_reasons_linked(self):
        """Exit should link to entry provenance."""

# tests/test_execution/test_paper/test_journal.py
class TestTradeJournal:
    """Test journal integrity."""
    
    async def test_entry_created_on_position_open(self):
        """Journal entry created for every position."""
        
    async def test_all_fills_recorded(self):
        """Every fill recorded in journal."""
        
    async def test_entry_closed_with_pnl(self):
        """Exit updates entry with PnL."""
        
    async def test_exit_reason_captured(self):
        """Exit reason recorded."""
```

## Integration Tests

### Component Integration

```python
# tests/test_execution/test_paper/test_orchestrator_integration.py
class TestOrchestratorIntegration:
    """Test orchestrator with real dependencies."""
    
    async def test_full_trade_flow(self):
        """End-to-end trade with real Redis/Postgres."""
        
    async def test_symbol_invariant_with_real_registry(self):
        """Test one-symbol rule with real Redis."""
        
    async def test_journal_persistence(self):
        """Verify journal entries in PostgreSQL."""
```

## E2E Tests

### Critical Invariant Tests

```python
# tests/e2e/test_paper_trading_invariants.py
class TestOneTradePerSymbolInvariant:
    """E2E test for one-trade-per-symbol rule."""
    
    async def test_second_signal_skipped(self):
        """
        Given: Position exists for BTCUSDT
        When: Second signal arrives for BTCUSDT
        Then: Signal is SKIPPED with reason SYMBOL_OCCUPIED
        """
        # Start orchestrator
        # Open position for BTCUSDT
        # Send second signal
        # Assert: SKIPPED status
        # Assert: Reason code is SYMBOL_OCCUPIED
        
    async def test_new_position_after_close(self):
        """
        Given: Position closed for BTCUSDT
        When: New signal arrives
        Then: New position opened
        """
        
    async def test_concurrent_signals_race(self):
        """
        Given: No position for symbol
        When: Two signals arrive simultaneously
        Then: Only one position opened
        """

class TestBybitOnlyInvariant:
    """E2E test for Bybit-only enforcement."""
    
    async def test_non_bybit_signal_rejected(self):
        """
        Given: Signal with venue='bitget'
        When: Processed by orchestrator
        Then: REJECTED with reason VENUE_NOT_ALLOWED
        """
```

## Specific Invariant Test Scenarios

### One-Trade-Per-Symbol Test Matrix

| Scenario | Expected Result | Test File |
|----------|-----------------|-----------|
| Signal for symbol with no position | EXECUTED | test_happy_path.py |
| Signal for symbol with open position | SKIPPED (SYMBOL_OCCUPIED) | test_invariants.py |
| Signal after position closed | EXECUTED | test_happy_path.py |
| Concurrent signals for same symbol | One EXECUTED, one SKIPPED | test_invariants.py |
| Position close race with new signal | Deterministic winner | test_invariants.py |

### Journal Integrity Test Matrix

| Check | Method | Frequency |
|-------|--------|-----------|
| Every position has journal entry | Redis scan + PostgreSQL query | Every 60s |
| Every fill recorded | Fill count == journal fill count | Every trade |
| Entry/exit PnL matches | Position PnL == journal PnL | Every close |
| No orphaned entries | Entries without closes > 7 days | Daily |
| Data consistency | Sum of fills == position size | Every fill |

## Performance Tests

### Latency Benchmarks

```python
# tests/performance/test_paper_latency.py
class TestLatencyBenchmarks:
    """Validate latency requirements."""
    
    async def test_signal_to_order_latency(self):
        """Signal → Order: <500ms (p99)"""
        
    async def test_order_to_fill_latency(self):
        """Order → Fill: <200ms (p99)"""
        
    async def test_total_pipeline_latency(self):
        """Signal → Position: <2000ms (p99)"""
        
    async def test_throughput_sustained(self):
        """100 trades/minute sustained for 10 minutes"""
```

### Load Test Scenarios

```python
# tests/load/test_paper_trading_load.py
class TestPaperTradingLoad:
    """Load testing for paper trading."""
    
    async def test_ten_symbols_concurrent(self):
        """
        10 symbols, 1 trade/minute each = 10 trades/minute
        Run for 30 minutes
        Verify: No position leaks, journal consistent
        """
        
    async def test_burst_trading(self):
        """
        50 signals in 1 minute burst
        Verify: All processed, latencies acceptable
        """
        
    async def test_long_running_stability(self):
        """
        Run for 24 hours
        Verify: No memory leaks, state consistent
        """
```

---

# D) LIVE VALIDATION CHECKLIST

## Pre-Deployment Smoke Checks

### Infrastructure Validation

- [ ] Redis accessible at `host.docker.internal:6380`
- [ ] PostgreSQL accessible at `host.docker.internal:5434`
- [ ] Bybit connector responding (demo environment)
- [ ] Grafana dashboards loading
- [ ] InfluxDB receiving metrics

### Configuration Validation

- [ ] `PAPER_TRADING_VENUES=bybit` set
- [ ] `PAPER_TRADING_ENABLED=true` set
- [ ] Bybit demo API keys configured
- [ ] Risk limits configured appropriately
- [ ] Kill switch enabled

### Service Startup Checks

```bash
# 1. Start paper trading orchestrator
docker compose up paper-trading

# 2. Verify health endpoint
curl http://localhost:8000/health/paper-trading
# Expected: {"status": "healthy", "components": {...}}

# 3. Verify symbol registry
curl http://localhost:8000/api/v1/paper/symbols
# Expected: {"active_symbols": [], "positions": []}

# 4. Verify market data freshness
curl http://localhost:8000/api/v1/paper/market-data/status
# Expected: {"bybit": {"last_update": "2025-03-03T...", "fresh": true}}
```

## Smoke Test Suite

### Test 1: Basic Trade Flow
```bash
# Send test signal
curl -X POST http://localhost:8000/api/v1/signals \
  -H "Content-Type: application/json" \
  -d '{
    "token": "BTCUSDT",
    "direction": "long",
    "confidence": 0.85,
    "venue": "bybit"
  }'

# Verify:
# 1. Position opened in tracker
# 2. Journal entry created
# 3. Symbol registry shows BTCUSDT occupied
# 4. Grafana metrics updated
# 5. Discord notification sent
```

### Test 2: One-Symbol Invariant
```bash
# Send second signal for same symbol (should be skipped)
curl -X POST http://localhost:8000/api/v1/signals \
  -d '{"token": "BTCUSDT", "direction": "long", ...}'

# Verify:
# 1. Second signal SKIPPED
# 2. Reason code: SYMBOL_OCCUPIED
# 3. Provenance recorded
# 4. Metrics incremented
```

### Test 3: Bybit Venue Enforcement
```bash
# Send signal with wrong venue
curl -X POST http://localhost:8000/api/v1/signals \
  -d '{"token": "ETHUSDT", "direction": "long", "venue": "bitget"}'

# Verify:
# 1. Signal REJECTED
# 2. Reason code: VENUE_NOT_ALLOWED
# 3. Alert logged
```

### Test 4: Kill Switch
```bash
# Trigger kill switch
redis-cli PUBLISH kill_switch:trigger "test emergency"

# Verify:
# 1. All positions closed within 5 seconds
# 2. Journal entries updated with KILL_SWITCH reason
# 3. Symbol registry cleared
# 4. Grafana alert fired
```

## Failure Mode Checks

### Redis Failure
```bash
# Simulate Redis failure
docker stop chiseai-redis

# Verify:
# 1. Orchestrator continues with cached state
# 2. Trades rejected (fail-safe)
# 3. Alert fired
# 4. Recovery when Redis back
```

### Bybit Data Stale
```bash
# Simulate stale market data
# (Block Bybit connection)

# Verify:
# 1. Trades rejected after 10s stale threshold
# 2. Alert fired for stale data
# 3. Recovery when data fresh
```

### Database Failure
```bash
# Simulate PostgreSQL failure
docker stop chiseai-postgres

# Verify:
# 1. Journal writes buffered to Redis
# 2. Alert fired
# 3. Recovery syncs buffered writes
```

## Rollback Checks

### Rollback Preparation
```bash
# 1. Tag current deployment
git tag paper-trading-v1.0

# 2. Create rollback snapshot
redis-cli SAVE
docker exec chiseai-postgres pg_dump > rollback_$(date +%Y%m%d).sql
```

### Rollback Test
```bash
# 1. Deploy new version
# 2. Run smoke tests
# 3. Simulate critical failure
# 4. Execute rollback:
   - Stop new orchestrator
   - Restore Redis from snapshot
   - Restore PostgreSQL from backup
   - Start previous version
# 5. Verify state consistent
```

## Bybit Connectivity Validation

### Demo Environment Verification
```bash
# Test Bybit demo API
curl https://api-demo.bybit.com/v5/market/time

# Test Bybit demo WebSocket
wscat -c wss://stream-demo.bybit.com/v5/public/linear

# Verify:
# - Connection successful
# - Market data flowing
# - Orders accepted (demo)
```

### Credentials Validation
```bash
# Verify credentials configured
echo $BYBIT_DEMO_API_KEY
echo $BYBIT_DEMO_API_SECRET

# Test authenticated endpoint
curl https://api-demo.bybit.com/v5/account/wallet-balance \
  -H "X-BAPI-API-KEY: $BYBIT_DEMO_API_KEY" \
  -H "X-BAPI-TIMESTAMP: $(date +%s)000" \
  -H "X-BAPI-SIGN: <generated_sign>"
```

---

# E) RISK REGISTER

## Risk Matrix

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|----|------|------------|--------|------------|-------|
| R1 | Symbol registry inconsistency (position exists but registry empty) | Medium | High | - Atomic Redis operations<br>- State recovery on startup<br>- Consistency monitoring | senior-dev |
| R2 | Race condition allows two positions for same symbol | Low | Critical | - Lua script atomic check-and-set<br>- Registry TTL<br>- E2E race condition tests | senior-dev |
| R3 | Journal data loss | Low | High | - Write-ahead to Redis<br>- PostgreSQL replication<br>- Daily backups<br>- Integrity checks | dev |
| R4 | Bybit data stale causing bad fills | Medium | Medium | - Data freshness checks (<5s)<br>- Reject trades if stale<br>- Alert on stale data | dev |
| R5 | Kill switch fails to close positions | Low | Critical | - Circuit breaker integration<br>- Manual override procedure<br>- Position audit after trigger | senior-dev |
| R6 | Memory leak under sustained load | Medium | Medium | - Load testing<br>- Memory profiling<br>- Connection pooling<br>- Periodic restarts | dev |
| R7 | PostgreSQL connection exhaustion | Medium | Medium | - Connection pooling<br>- Query timeouts<br>- Circuit breaker | dev |
| R8 | Redis memory exhaustion | Low | Medium | - Key TTLs<br>- Memory monitoring<br>- Archival of old data | dev |
| R9 | Non-Bybit signal slips through | Low | Critical | - Venue validation at orchestrator entry<br>- Config enforcement<br>- Audit logging | senior-dev |
| R10 | Test trades leak to production | Very Low | Critical | - Demo-only API keys<br>- Endpoint validation<br>- Paper trading flag | merlin |

## Risk Mitigation Details

### R1: Symbol Registry Inconsistency
**Mitigation Strategy**:
1. Use Redis Lua scripts for atomic operations
2. Implement startup recovery procedure
3. Run consistency checks every 60 seconds
4. Alert on inconsistency with auto-heal

**Monitoring**:
- Metric: `paper:symbol_registry:inconsistencies`
- Alert: `inconsistency_count > 0`

### R2: Race Condition
**Mitigation Strategy**:
```lua
-- Lua script for atomic check-and-set
local symbol = KEYS[1]
local position_id = ARGV[1]
local ttl = ARGV[2]

local existing = redis.call('GET', symbol)
if existing then
    return {false, existing}
end

redis.call('SETEX', symbol, ttl, position_id)
return {true, position_id}
```

**Testing**:
- Concurrent signal injection (100 simultaneous)
- Verify: Only one position opened

### R3: Journal Data Loss
**Mitigation Strategy**:
1. Write to Redis list first (buffer)
2. Async batch write to PostgreSQL
3. Acknowledge only after PostgreSQL commit
4. Replay Redis buffer on startup if needed

**Recovery**:
```python
# On startup
buffered_entries = redis.lrange("paper:journal:buffer", 0, -1)
for entry in buffered_entries:
    postgres.insert(entry)
redis.delete("paper:journal:buffer")
```

### R5: Kill Switch Failure
**Mitigation Strategy**:
1. Multiple kill switch triggers (Redis pub/sub, HTTP endpoint, file-based)
2. Position audit after kill switch
3. Manual override procedure documented
4. Circuit breaker on kill switch execution

**Escalation**:
- P0 incident if kill switch fails
- Immediate human intervention required

## Blocker Escalation Policy

### Escalation Levels

| Level | Trigger | Response Time | Action |
|-------|---------|---------------|--------|
| L1 | Test failure, minor bug | 4 hours | Dev fixes, Critic reviews |
| L2 | Invariant violation in tests | 2 hours | Senior-dev investigates, Merlin notified |
| L3 | Race condition, data loss | 30 minutes | Senior-dev + Merlin pair debug |
| L4 | Production issue, kill switch | 5 minutes | All-hands, Merlin leads |

### Escalation Contacts

| Role | Primary | Backup |
|------|---------|--------|
| Senior-dev | @senior-dev | @dev |
| Dev | @dev | @critic |
| Critic | @critic | @merlin |
| Merlin | @merlin | @captain-craig |

### Communication Channels

- **L1-L2**: Discord #dev-chat
- **L3**: Discord #urgent + voice channel
- **L4**: Discord #incident + emergency call

---

# F) DEFINITION OF DONE

## Sprint Completion Criteria

### Technical Completion

- [ ] All 14 stories marked complete
- [ ] All acceptance criteria met for each story
- [ ] Unit test coverage ≥85% for new code
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] All E2E tests passing
- [ ] Performance benchmarks meeting targets
- [ ] Load test passed (10 trades/min sustained)

### Invariant Validation

- [ ] **One-Trade-Per-Symbol**: Verified by E2E tests with concurrent signals
- [ ] **Signal Provenance**: Every signal has provenance record
- [ ] **Reason Codes**: All decisions have documented reason codes
- [ ] **Journal Integrity**: Every trade in journal, no orphaned entries
- [ ] **Bybit-Only**: Venue enforcement verified, non-Bybit signals rejected

### Observability Validation

- [ ] Grafana dashboards visible and functional
- [ ] All alerts configured and tested
- [ ] Health endpoint returning OK
- [ ] Metrics flowing to InfluxDB
- [ ] Trade journal queryable via API

### Documentation Validation

- [ ] Architecture document reviewed
- [ ] Runbooks cover common scenarios
- [ ] API documentation complete
- [ ] Deployment checklist ready

### Production Readiness

- [ ] 24-hour burn-in test passed
- [ ] Security review passed
- [ ] Code review completed by Merlin
- [ ] Rollback procedures tested
- [ ] No P0 or P1 bugs open

## Validation Gates

### Gate 1: Unit Test Gate
```bash
pytest tests/test_execution/test_paper/ -v --cov=src/execution/paper --cov-report=term-missing
# Threshold: coverage >= 85%
```

### Gate 2: Integration Test Gate
```bash
pytest tests/test_execution/test_paper/test_*_integration.py -v
# All tests must pass
```

### Gate 3: E2E Test Gate
```bash
pytest tests/e2e/test_paper_trading_*.py -v --tb=short
# All invariant tests must pass
```

### Gate 4: Performance Gate
```bash
pytest tests/performance/test_paper_latency.py -v
# Latencies: signal→order <500ms, order→fill <200ms, total <2000ms
```

### Gate 5: Load Test Gate
```bash
pytest tests/load/test_paper_trading_load.py -v
# Sustain 10 trades/minute for 30 minutes
# No memory leaks, no position leaks
```

### Gate 6: Smoke Test Gate
```bash
./scripts/smoke_test_paper_trading.sh
# All smoke tests pass
```

### Gate 7: 24-Hour Burn-in Gate
```bash
# Run paper trading for 24 hours
# Verify: No crashes, consistent state, all invariants hold
# Minimum: 100 trades executed
```

### Gate 8: Security Review Gate
```bash
bandit -r src/execution/paper/
# No HIGH or CRITICAL issues
```

### Gate 9: Documentation Gate
- Architecture document reviewed and approved
- All runbooks tested
- API docs validated with examples

### Gate 10: Sign-off Gate
- [ ] Senior-dev sign-off on technical implementation
- [ ] Critic sign-off on test coverage
- [ ] Dev sign-off on observability
- [ ] Merlin sign-off on production readiness

## Sign-off Requirements

### Required Approvals

| Role | Responsibility | Sign-off Criteria |
|------|---------------|-------------------|
| Senior-dev | Technical implementation | Code quality, architecture adherence |
| Critic | Test coverage | ≥85% coverage, all critical paths tested |
| Dev | Observability | Dashboards functional, alerts tested |
| Merlin | Production readiness | All gates pass, rollback ready |

### Sign-off Process

1. **Self-certification**: Each owner certifies their work
2. **Peer review**: Cross-review by other team members
3. **Merlin review**: Final technical review
4. **Go/No-Go decision**: Merlin makes final call

### Sign-off Template

```markdown
## Story: PAPER-2025-00X

### Owner Sign-off
- [ ] Implementation complete
- [ ] Unit tests passing
- [ ] Acceptance criteria met

### Reviewer Sign-off
- [ ] Code reviewed
- [ ] Tests reviewed
- [ ] Documentation reviewed

### Merlin Approval
- [ ] Technical quality acceptable
- [ ] Production ready
- [ ] Approved for merge

Signed: @merlin (YYYY-MM-DD)
```

---

## Appendix A: Story ID Reference

| Story ID | Title | Points | Status |
|----------|-------|--------|--------|
| PAPER-2025-001 | One-Trade-Per-Symbol Invariant Engine | 3 | Planned |
| PAPER-2025-002 | Signal Provenance Tracking System | 5 | Planned |
| PAPER-2025-003 | Comprehensive Trade Journal | 8 | Planned |
| PAPER-2025-004 | Bybit-Only Mode Enforcement | 3 | Planned |
| PAPER-2025-005 | Redis State Consistency Hardening | 3 | Planned |
| PAPER-2025-006 | Kill Switch Integration for Paper Trading | 2 | Planned |
| PAPER-2025-007 | Paper Trading E2E Test Suite | 5 | Planned |
| PAPER-2025-008 | Performance and Latency Optimization | 3 | Planned |
| PAPER-2025-009 | Paper Trading Health Monitoring | 2 | Planned |
| PAPER-2025-010 | Documentation and Runbooks | 3 | Planned |
| PAPER-2025-011 | Trade Journal Analytics | 3 | Planned |
| PAPER-2025-012 | Backtest Integration | 2 | Planned |
| PAPER-2025-013 | Discord Trade Notifications | 2 | Planned |
| PAPER-2025-014 | Paper Trading Cleanup and Hardening | 4 | Planned |

**Total**: 47 points across 14 stories

---

## Appendix B: File Structure

```
src/execution/paper/
├── __init__.py
├── orchestrator.py              # Existing - modified
├── models.py                    # Existing - minor additions
├── config.py                    # NEW - configuration
├── symbol_registry.py           # NEW - Task 1.1
├── provenance.py                # NEW - Task 2.1
├── provenance_pipeline.py       # NEW - Task 2.2
├── exit_reasons.py              # NEW - Task 2.3
├── provenance_api.py            # NEW - Task 2.4
├── trade_journal.py             # NEW - Task 3.1
├── journal_store.py             # NEW - Task 3.2
├── journal_reports.py           # NEW - Task 3.3
├── state_recovery.py            # NEW - Task 5.1
├── redis_transactions.py        # NEW - Task 5.2
├── state_monitor.py             # NEW - Task 5.3
├── kill_switch_integration.py   # NEW - Task 6.1
├── health_monitor.py            # NEW - Task 9.1
└── analytics/                   # NEW - Task 11.x
    ├── __init__.py
    ├── metrics.py
    └── strategy_comparison.py

tests/test_execution/test_paper/
├── test_symbol_registry.py      # NEW - Task 1.4
├── test_provenance.py           # NEW - Task 2.5
├── test_journal_integrity.py    # NEW - Task 3.5
├── test_kill_switch_integration.py  # NEW - Task 6.2
└── ...

tests/e2e/
├── test_paper_trading_happy_path.py   # NEW - Task 7.1
├── test_paper_trading_invariants.py   # NEW - Task 7.2
└── test_paper_trading_recovery.py     # NEW - Task 7.3

infrastructure/grafana/dashboards/
├── paper_trading.json           # MODIFIED - Task 1.3
├── trade_journal.json           # NEW - Task 3.4
└── paper_analytics.json         # NEW - Task 11.3

docs/
├── architecture/paper_trading.md    # NEW - Task 10.1
├── runbooks/paper_trading/          # NEW - Task 10.2
│   ├── investigating_skipped_signals.md
│   ├── registry_inconsistency.md
│   ├── kill_switch_handling.md
│   └── journal_export.md
└── api/paper_trading.md             # NEW - Task 10.3
```

---

## Appendix C: Dependencies and Prerequisites

### Technical Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| Redis | 7.x | State management, locking |
| PostgreSQL | 15.x | Trade journal persistence |
| InfluxDB | 2.x | Metrics and time-series |
| Bybit API | v5 | Market data and order simulation |

### Code Dependencies

| Module | Purpose |
|--------|---------|
| `src/data/exchange/bybit_connector.py` | Market data |
| `src/execution/kill_switch/` | Emergency stop |
| `src/execution/telemetry/` | Metrics export |
| `src/signal_generation/` | Signal consumption |

### External Services

| Service | Environment | Purpose |
|---------|-------------|---------|
| Bybit Demo | Demo | Market data, order simulation |
| Grafana | Production | Observability |
| Discord | Production | Notifications |

---

*Document Version*: 1.0  
*Created*: 2025-03-03  
*Author*: Merlin (Merge Authority)  
*Reviewers*: TBD  
*Approval*: Pending
