---
stepsCompleted: [1, 2, 3]
inputDocuments: [docs/prd.md, _bmad-output/planning-artifacts/architecture.md]
---

# ChiseAI - Epic Breakdown

## Overview

This document provides complete epic and story breakdown for ChiseAI, decomposing requirements from PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-001: Multi-timeframe analysis (1m, 5m, 15m, 1h, 4h, 1d)
FR-002: Technical indicator calculation (RSI, MACD, Bollinger Bands)
FR-003: Markov chain trend detection and state inference
FR-004: Confluence-based signal scoring combining multiple indicators
FR-004a: Order type execution support (market and limit orders)
FR-005: Confidence multiplier updates based on signal agreement
FR-006: Signal history tracking with outcome correlation
FR-007: Real-time signal generation meeting 75%+ confidence threshold
FR-008: Dashboard display with pre-market briefing
FR-009: Discord alerts for high-confidence opportunities
FR-010: Detailed signal breakdown with risk parameters
FR-011: Historical context for similar situations
FR-012: Position sizing recommendations based on portfolio
FR-013: Stop-loss recommendations with each signal
FR-014: Portfolio-level risk exposure monitoring
FR-015: Correlation analysis across positions
FR-016: Automated alerts for risk threshold breaches
FR-017: Prediction accuracy tracking over time
FR-018: ML feedback loop analyzing predictions vs outcomes
FR-019: Confidence threshold calibration
FR-020: Training data generation for model improvement
FR-021: Mobile-responsive dashboard design
FR-022: User-configurable alert thresholds
FR-023: Performance reporting (daily/weekly/monthly)
FR-024: Community discussion via Discord integration
FR-025: Continuous backtesting runner (walk-forward capable)
FR-026: Exchange adapter interface + connectors: Binance (reference), Bybit (paper), Bitget (live)
FR-027: Paper trading orchestration (Bybit demo) with shadow backtests continuing
FR-028: Live trading orchestration (Bitget) with explicit enable/disable gating
FR-029: Mode-specific kill-switch enforcement (paper self-eval/resume; live human re-auth)
FR-030: Direct perps execution for high-confidence setups when evidence supports non-grid strategies
FR-030a: Hedging and market-neutral position support for risk management
FR-031: Grafana-first observability (KPIs, health, alerts)
FR-DEV-001: Standard PR workflow: all changes land via PRs and merge to main only after Woodpecker CI is green
FR-DEV-002: PR traceability: PR titles must include story IDs; CI blocks PRs missing a title or story ID
FR-DEV-003: Status discipline: repo state in docs/bmm-workflow-status.yaml and docs/validation/validation-registry.yaml must stay in sync; CI validates this
FR-DEV-004: Taiga monitoring view: repo-canonical story metadata (id/title/status/AC) is synced to Taiga; conflicts follow strict policy (repo is canonical)
FR-DEV-005: Iteration loop compliance: work is tracked via iterlogs (Redis/Qdrant when available; docs/tempmemories/ fallback) and validated in CI
FR-EVO-001: Constrained action space for evolution: strategies are mutated only via approved config/DSL interfaces (no arbitrary live code edits)
FR-EVO-002: Strategy DSL schema supports parameter and structural mutations, while remaining diffable and reproducible
FR-EVO-003: Strategy registry supports champion/challenger tracking and stores artifacts (config, diffs, backtest results, paper results)
FR-EVO-004: Strategy CI/CD promotion pipeline: candidate -> backtest gate -> paper canary -> paper full -> promotion packet -> human-approved live
FR-EVO-005: Promotion packets are generated for human approvals (paper->live; and optional brain upgrades), including evidence, risk invariants, and rollback steps
FR-EVO-006: Optional policy knobs: trade-frequency budgeting and turnover reporting (trades/day) can be enabled as a secondary control when it improves cost and stability

### NonFunctional Requirements

NFR-001: Dashboard load time: <3 seconds (95th percentile)
NFR-002: Signal delivery latency: <1 second (end-to-end)
NFR-003: API response time: <1 second (95th percentile)
NFR-004: Query performance (outcome analysis): <25ms (endpoints)
NFR-005: Cache performance: <200ms latency (Redis)
NFR-006: System uptime: ≥99.9% for critical functions
NFR-007: Maximum downtime per year: ≤8.76 hours
NFR-008: Failover recovery time: <4 hours (service disruption)
NFR-009: Data backup frequency: Automated daily with 100% coverage
NFR-010: Audit trail gaps: <1 minute maximum gap
NFR-011: Security breaches: Zero count
NFR-012: Critical vulnerabilities: Zero count
NFR-013: Regulatory/compliance automation: N/A (out of scope for this project)
NFR-014: Data encryption (at rest): AES-256 standard
NFR-015: Data encryption (in transit): TLS 1.3 standard
NFR-016: Penetration testing: Quarterly frequency
NFR-017: Test coverage: ≥80% automated tests
NFR-018: Lint errors: Zero count
NFR-019: Code documentation: All public APIs
NFR-020: CI/CD pipeline status: 100% green builds

### Additional Requirements

**Infrastructure and Deployment Requirements:**
- Neuro-symbolic hybrid architecture combining neural/LLM components with symbolic constraints
- Docker containerization with Terraform infrastructure as code
- PostgreSQL relational database with 7-year retention for signals, trades, outcomes, and registry state
- InfluxDB time-series database with 2-year retention for OHLCV, order book, and OI data
- Redis cache layer for real-time state and feature caching (ephemeral)
- Qdrant vector database for semantic memory, decisions, and patterns (persistent)
- PostgreSQL append-only event store for audit log with 7-year retention

**Integration Requirements:**
- Exchange connectors: Binance (reference market data), Bybit (paper trading), Bitget (live trading)
- Discord integration for alert delivery and notifications
- Grafana dashboards as primary observability UI

**Strategy CI/CD Requirements:**
- Strategy DSL with schema validation and versioning
- Strategy registry with champion/challenger tracking and artifact storage (config, diffs, backtest results, paper results)
- Promotion pipeline stages: candidate generation → backtest gate → paper canary → paper full → promotion packet → human-approved live
- Backtest gate with walk-forward validation, slippage/fee sensitivity sweeps, and stress tests
- Paper gate with max 5% drawdown, 55% win rate, and 7-day duration criteria
- Trade budgeter enforcing 20 trades/day ceiling
- Selection policy with lexicographic ranking: profit first, then turnover (3% epsilon), then complexity

**Brain CI/CD Requirements:**
- Brain registry for version management and BrainEval results
- Shadow mode for testing new brains without affecting live decisions
- Brain evaluation metrics: paper carryover rate, false positives, time-to-improvement, low turnover bias, compute cost, safety compliance
- Brain upgrade cadence: rapid (every 3 days), weekly, monthly phases with transition rules
- Promotion requires human approval with auto-deploy allowed to paper only

**Risk Management and Guardrails Requirements:**
- Hard risk caps: ≤1% per-trade risk, ≤2% per-grid risk, ≤15% portfolio drawdown, 3x leverage maximum
- Position limit: 10% of portfolio per token
- Correlation limit: Max 40% correlated exposure
- Confidence threshold: ≥75% minimum
- Kill-switch (Live): ≥15% drawdown triggers disable until human re-authorizes
- Kill-switch (Paper): ≥15% drawdown triggers close positions, suspend, self-eval, and auto-resume with adjusted params
- Circuit breaker: API failure rate >10% triggers fallback to cached data
- Panic shutdown: Manual trigger closes all positions and disables alerts
- Rollback triggers: drawdown approaching thresholds, win rate <55% over 20 trades, ECE >0.10, safety test failure

**Observability Requirements:**
- Grafana-first observability with dashboards for: data & ingest health, backtest KPIs, paper execution, live execution, strategy registry, brain registry
- Key metrics: dashboard load time (<3s), signal delivery latency (<1s), API response time (<1s), query performance (<25ms), cache performance (<200ms)
- Alerting channels: Discord #alerts for data freshness, kill-switch triggered, drawdown warning, API disconnect, model drift
- Runbooks for: API disconnect, data gaps, order rejects, model drift

**Data Store Requirements:**
- Market data store: InfluxDB with 2-year retention
- Feature store: PostgreSQL + Redis for computed features and technical indicators
- Event store/audit log: PostgreSQL (append-only) with 7-year retention

### FR Coverage Map

| FR | Epic | Description |
|-----|-------|-------------|
| FR-001 | Epic 1 | Multi-timeframe analysis (1m, 5m, 15m, 1h, 4h, 1d) |
| FR-002 | Epic 1 | Technical indicator calculation (RSI, MACD, Bollinger Bands) |
| FR-003 | Epic 1 | Markov chain trend detection and state inference |
| FR-004 | Epic 1 | Confluence-based signal scoring combining multiple indicators |
| FR-005 | Epic 1 | Confidence multiplier updates based on signal agreement |
| FR-006 | Epic 1 | Signal history tracking with outcome correlation |
| FR-007 | Epic 2 | Real-time signal generation meeting 75%+ confidence threshold |
| FR-008 | Epic 2 | Dashboard display with pre-market briefing |
| FR-009 | Epic 2 | Discord alerts for high-confidence opportunities |
| FR-010 | Epic 2 | Detailed signal breakdown with risk parameters |
| FR-011 | Epic 2 | Historical context for similar situations |
| FR-012 | Epic 3 | Position sizing recommendations based on portfolio |
| FR-013 | Epic 3 | Stop-loss recommendations with each signal |
| FR-014 | Epic 3 | Portfolio-level risk exposure monitoring |
| FR-015 | Epic 3 | Correlation analysis across positions |
| FR-016 | Epic 3 | Automated alerts for risk threshold breaches |
| FR-017 | Epic 4 | Prediction accuracy tracking over time |
| FR-018 | Epic 4 | ML feedback loop analyzing predictions vs outcomes |
| FR-019 | Epic 4 | Confidence threshold calibration |
| FR-020 | Epic 4 | Training data generation for model improvement |
| FR-021 | Epic 5 | Mobile-responsive dashboard design |
| FR-022 | Epic 5 | User-configurable alert thresholds |
| FR-023 | Epic 5 | Performance reporting (daily/weekly/monthly) |
| FR-024 | Epic 5 | Community discussion via Discord integration |
| FR-004a | Epic 6 | Order type execution support (market and limit orders) |
| FR-025 | Epic 6 | Continuous backtesting runner (walk-forward capable) |
| FR-026 | Epic 6 | Exchange adapter interface + connectors: Binance (reference), Bybit (paper), Bitget (live) |
| FR-027 | Epic 6 | Paper trading orchestration (Bybit demo) with shadow backtests continuing |
| FR-028 | Epic 6 | Live trading orchestration (Bitget) with explicit enable/disable gating |
| FR-029 | Epic 6 | Mode-specific kill-switch enforcement (paper self-eval/resume; live human re-auth) |
| FR-030 | Epic 6 | Direct perps execution for high-confidence setups when evidence supports non-grid strategies |
| FR-030a | Epic 6 | Hedging and market-neutral position support for risk management |
| FR-031 | Epic 7 | Grafana-first observability (KPIs, health, alerts) |
| FR-DEV-001 | Epic 8 | Standard PR workflow: all changes land via PRs and merge to main only after Woodpecker CI is green |
| FR-DEV-002 | Epic 8 | PR traceability: PR titles must include story IDs; CI blocks PRs missing a title or story ID |
| FR-DEV-003 | Epic 8 | Status discipline: repo state in docs/bmm-workflow-status.yaml and docs/validation/validation-registry.yaml must stay in sync; CI validates this |
| FR-DEV-004 | Epic 8 | Taiga monitoring view: repo-canonical story metadata (id/title/status/AC) is synced to Taiga; conflicts follow strict policy (repo is canonical) |
| FR-DEV-005 | Epic 8 | Iteration loop compliance: work is tracked via iterlogs (Redis/Qdrant when available; docs/tempmemories/ fallback) and validated in CI |
| FR-EVO-001 | Epic 9 | Constrained action space for evolution: strategies are mutated only via approved config/DSL interfaces (no arbitrary live code edits) |
| FR-EVO-002 | Epic 9 | Strategy DSL schema supports parameter and structural mutations, while remaining diffable and reproducible |
| FR-EVO-003 | Epic 9 | Strategy registry supports champion/challenger tracking and stores artifacts (config, diffs, backtest results, paper results) |
| FR-EVO-004 | Epic 9 | Strategy CI/CD promotion pipeline: candidate -> backtest gate -> paper canary -> paper full -> promotion packet -> human-approved live |
| FR-EVO-005 | Epic 9 | Promotion packets are generated for human approvals (paper->live; and optional brain upgrades), including evidence, risk invariants, and rollback steps |
| FR-EVO-006 | Epic 9 | Optional policy knobs: trade-frequency budgeting and turnover reporting (trades/day) can be enabled as a secondary control when it improves cost and stability |

## Epic List

### Epic 1: Market Intelligence Foundation
Multi-timeframe technical analysis, indicator calculations, Markov chain trend detection, confluence-based signal scoring, confidence multipliers, and signal history tracking.
**FRs covered:** FR-001, FR-002, FR-003, FR-004, FR-005, FR-006

### Epic 2: Actionable Signals, Briefings, and Alerts
Real-time signal generation meeting 75%+ confidence, pre-market briefings, Discord alerts, detailed signal breakdowns, and historical context panels.
**FRs covered:** FR-007, FR-008, FR-009, FR-010, FR-011

### Epic 3: Portfolio Risk Controls and Exposure Oversight
Position sizing recommendations, stop-loss recommendations, portfolio-level risk exposure monitoring, correlation analysis across positions, and automated risk threshold breach alerts.
**FRs covered:** FR-012, FR-013, FR-014, FR-015, FR-016

### Epic 4: Learning Loop and Calibration
Prediction accuracy tracking over time, ML feedback loop analyzing predictions vs outcomes, confidence threshold calibration, and training data generation for model improvement.
**FRs covered:** FR-017, FR-018, FR-019, FR-020

### Epic 5: Operator Experience, Reporting, and Community
Mobile-responsive dashboard design, user-configurable alert thresholds, performance reporting (daily/weekly/monthly), and community discussion via Discord integration.
**FRs covered:** FR-021, FR-022, FR-023, FR-024

### Epic 6: Safe Trading Execution and Validation Gates (Backtest->Paper->Live)
Order type execution support (market and limit orders), continuous backtesting runner (walk-forward capable), exchange adapter interface + connectors (Binance reference, Bybit paper, Bitget live), paper trading orchestration (Bybit demo) with shadow backtests, live trading orchestration (Bitget) with explicit enable/disable gating, mode-specific kill-switch enforcement, direct perps execution for high-confidence setups, and hedging/market-neutral position support.
**FRs covered:** FR-004a, FR-025, FR-026, FR-027, FR-028, FR-029, FR-030, FR-030a

### Epic 7: Observability and Operational Health
Grafana-first observability with KPIs, health monitoring, and alerts.
**FRs covered:** FR-031

### Epic 8: Chise Autonomy + Brain Operations (Governance)
Standard PR workflow, PR traceability, status discipline with repo state sync, Taiga monitoring view, iteration loop compliance with iterlogs (Redis/Qdrant when available; docs/tempmemories/ fallback). Notes: brain registry/versioning, shadow mode, BrainEval, cadence, paper-only auto-deploy; human gate for live.
**FRs covered:** FR-DEV-001, FR-DEV-002, FR-DEV-003, FR-DEV-004, FR-DEV-005

### Epic 9: Strategy Evolution and Promotion Pipeline
Constrained action space for evolution (approved config/DSL interfaces only), Strategy DSL schema supporting parameter and structural mutations, strategy registry with champion/challenger tracking and artifact storage, strategy CI/CD promotion pipeline (candidate -> backtest gate -> paper canary -> paper full -> promotion packet -> human-approved live), promotion packets for human approvals (paper->live; and optional brain upgrades), and optional policy knobs for trade-frequency budgeting and turnover reporting.
**FRs covered:** FR-EVO-001, FR-EVO-002, FR-EVO-003, FR-EVO-004, FR-EVO-005, FR-EVO-006

**Note:** Non-Functional Requirements (NFRs) are cross-cutting and apply across all epics.

## Epic 1: Market Intelligence Foundation

Build the foundational data and analysis layer for multi-timeframe technical analysis, indicator calculations, Markov chain trend detection, confluence scoring, confidence multipliers, and signal history tracking.

### Story 1.1: Multi-Timeframe Data Ingestion Pipeline (5 SP)

As a system analyst,
I want to ingest and store OHLCV data across multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d),
So that I have a complete data foundation for technical analysis.

**Acceptance Criteria:**

**Given** the system is configured with supported timeframes
**When** the data ingestion pipeline runs
**Then** OHLCV data is fetched and stored for all configured timeframes (1m, 5m, 15m, 1h, 4h, 1d)
**And** data freshness is validated with timestamps no older than 2x the timeframe interval
**And** missing data gaps are detected and backfilled automatically

---

### Story 1.2: Technical Indicator Calculation Engine (5 SP)

As a quantitative analyst,
I want automated calculation of RSI, MACD, and Bollinger Bands across all timeframes,
So that I have standardized technical indicators for signal generation.

**Acceptance Criteria:**

**Given** OHLCV data exists for a timeframe
**When** the indicator calculation job runs
**Then** RSI (14-period) is calculated and stored
**And** MACD (12, 26, 9) is calculated and stored with signal line
**And** Bollinger Bands (20-period, 2 std dev) are calculated and stored
**And** all indicators are computed for each configured timeframe
**And** FR-002 is satisfied

---

### Story 1.3: Markov Chain Trend State Detection (5 SP)

As a trend analyst,
I want Markov chain-based trend state inference (bullish, bearish, neutral, transitional),
So that I can identify market regimes and state transitions probabilistically.

**Acceptance Criteria:**

**Given** historical price data and calculated indicators
**When** the Markov chain model processes the data
**Then** current trend state is inferred as one of: bullish, bearish, neutral, or transitional
**And** state transition probabilities are calculated
**And** the most likely next state is predicted with confidence score
**And** state history is tracked for pattern analysis
**And** FR-003 is satisfied

---

### Story 1.4: Confluence-Based Signal Scoring (5 SP)

As a signal analyst,
I want a confluence scoring system that combines multiple indicator signals into a unified score,
So that I can identify high-probability trading opportunities.

**Acceptance Criteria:**

**Given** technical indicators and Markov states are available
**When** the confluence engine evaluates a market condition
**Then** individual indicator signals are weighted by timeframe importance
**And** a composite confluence score (0-100) is calculated
**And** signal direction (long/short) is determined
**And** contributing factors are logged for transparency
**And** FR-004 is satisfied

---

### Story 1.5: Confidence Multiplier System (3 SP)

As a risk manager,
I want confidence multipliers that adjust based on signal agreement across timeframes,
So that higher-confidence setups receive proportionally higher scores.

**Acceptance Criteria:**

**Given** confluence scores exist for multiple timeframes
**When** signals from different timeframes agree on direction
**Then** a confidence multiplier is applied (1.0x base, up to 1.5x for 4+ timeframe agreement)
**And** conflicting timeframe signals reduce the multiplier
**And** the final confidence score is capped at 100
**And** multiplier rationale is logged
**And** FR-005 is satisfied

---

### Story 1.6: Signal History and Outcome Tracking (5 SP)

As a performance analyst,
I want signal history tracking with outcome correlation,
So that I can measure prediction accuracy and improve future signals.

**Acceptance Criteria:**

**Given** a signal is generated with confidence ≥75%
**When** the signal outcome is determined (target hit, stop hit, or expired)
**Then** the signal is stored with timestamp, direction, confidence, and entry price
**And** outcome is recorded (win/loss, PnL, exit price, exit time)
**And** prediction accuracy is calculated per signal type
**And** historical performance is queryable by timeframe and indicator combination
**And** FR-006 is satisfied

---

## Epic 2: Actionable Signals, Briefings, and Alerts

Deliver real-time signal generation, dashboard briefings, Discord alerts, detailed signal breakdowns, and historical context to enable informed trading decisions.

### Story 2.1: Real-Time Signal Generation Engine (5 SP)

As a trader,
I want real-time signal generation that meets the 75%+ confidence threshold,
So that I receive only high-quality actionable trading signals.

**Acceptance Criteria:**

**Given** the confluence scoring and confidence multiplier systems are operational
**When** market conditions trigger a signal evaluation
**Then** signals with final confidence ≥75% are generated immediately
**And** signals below 75% are logged but not surfaced as actionable
**And** each signal includes direction, confidence score, timestamp, and token
**And** signal generation latency is <1 second end-to-end
**And** FR-007 is satisfied
**And** if data freshness checks fail (older than 2x timeframe interval), signals are not emitted as actionable and a health alert is raised (ties to Epic 7.2)

---

### Story 2.2: Dashboard Pre-Market Briefing (5 SP)

As a dashboard user,
I want a pre-market briefing displayed on the dashboard,
So that I can quickly understand market conditions before trading sessions.

**Acceptance Criteria:**

**Given** the dashboard loads
**When** the pre-market briefing component renders
**Then** overnight market summary is displayed (major moves, volume, volatility)
**And** key levels are shown (support/resistance from multiple timeframes)
**And** active signals meeting 75% threshold are listed
**And** market regime (trending/ranging) is indicated
**And** briefing updates automatically every 5 minutes
**And** FR-008 is satisfied

---

### Story 2.3: Discord Alert Integration (5 SP)

As a trader,
I want Discord alerts for high-confidence opportunities,
So that I receive timely notifications even when not actively monitoring the dashboard.

**Acceptance Criteria:**

**Given** a signal is generated with confidence score
**When** the alert system processes the signal
**Then** internal actionable signals are surfaced at ≥75% confidence (per FR-007)
**And** a Discord message is posted for signals meeting the configured Discord posting threshold (default 40%, configurable via FR-022)
**And** Discord alerts in the 40-74% range are posted as "watchlist" notifications
**And** each alert includes token, direction, confidence, key levels, and timestamp
**And** duplicate alerts within 15 minutes are suppressed
**And** FR-009 is satisfied

---

### Story 2.4: Detailed Signal Breakdown Panel (5 SP)

As a signal evaluator,
I want a detailed signal breakdown with risk parameters,
So that I can understand the rationale and risk before acting.

**Acceptance Criteria:**

**Given** a signal is selected on the dashboard
**When** the signal detail panel opens
**Then** confluence score components are displayed (each indicator contribution)
**And** confidence multiplier and timeframe agreement are shown
**And** recommended stop-loss level is displayed
**And** recommended position size is displayed
**And** risk/reward ratio is calculated and shown
**And** FR-010 is satisfied

---

### Story 2.5: Historical Context for Similar Signals (3 SP)

As a decision maker,
I want historical context for similar market situations,
So that I can compare current signals to past outcomes.

**Acceptance Criteria:**

**Given** a signal detail view is open
**When** historical context is requested
**Then** similar past signals are retrieved (same direction, comparable confidence)
**And** win rate for similar signals is displayed
**And** average PnL for similar signals is shown
**And** maximum drawdown experienced in similar setups is displayed
**And** sample size (number of similar signals) is indicated
**And** FR-011 is satisfied

---

## Epic 3: Portfolio Risk Controls and Exposure Oversight

Implement position sizing, stop-loss recommendations, portfolio risk monitoring, correlation analysis, and automated risk threshold alerts to protect capital.

### Story 3.1: Position Sizing Recommendations (5 SP)

As a portfolio manager,
I want position sizing recommendations based on portfolio value and risk parameters,
So that I can size trades appropriately for my account.

**Acceptance Criteria:**

**Given** a signal is generated and portfolio data is available
**When** position sizing is calculated
**Then** recommendation uses maximum 10% of portfolio per token
**And** sizing considers current exposure to the token
**And** risk-adjusted sizing reduces position for lower confidence signals
**And** recommendation is displayed in both token amount and USD value
**And** FR-012 is satisfied

---

### Story 3.2: Stop-Loss Recommendation Engine (3 SP)

As a risk-conscious trader,
I want stop-loss recommendations with each signal,
So that I have predefined exit points to limit downside.

**Acceptance Criteria:**

**Given** a signal is generated
**When** stop-loss is calculated
**Then** stop-loss is based on recent support/resistance levels
**And** maximum risk per trade is capped at 1% of portfolio
**And** ATR-based stops are available as an alternative method
**And** stop-loss price and percentage are displayed
**And** FR-013 is satisfied

---

### Story 3.3: Portfolio Risk Exposure Monitor (5 SP)

As a risk manager,
I want portfolio-level risk exposure monitoring,
So that I can track aggregate risk across all positions.

**Acceptance Criteria:**

**Given** positions exist in the portfolio
**When** the risk monitor runs
**Then** total portfolio exposure is calculated and displayed
**And** exposure per token is shown with percentage of portfolio
**And** unrealized PnL is tracked and displayed
**And** current drawdown from peak is calculated
**And** alerts trigger when drawdown approaches 15% threshold
**And** FR-014 is satisfied

---

### Story 3.4: Cross-Position Correlation Analysis (5 SP)

As a portfolio analyst,
I want correlation analysis across positions,
So that I can avoid over-concentration in correlated assets.

**Acceptance Criteria:**

**Given** multiple positions exist in the portfolio
**When** correlation analysis runs
**Then** pairwise correlation coefficients are calculated (30-day rolling)
**And** highly correlated positions (>40%) are flagged
**And** correlation matrix is visualized on the dashboard
**And** warnings are shown when correlation limits are exceeded
**And** FR-015 is satisfied

---

### Story 3.5: Risk Threshold Breach Alerts (3 SP)

As a risk overseer,
I want automated alerts when risk thresholds are breached,
So that I can take immediate action to protect capital.

**Acceptance Criteria:**

**Given** risk monitoring thresholds are configured
**When** a threshold is breached (drawdown ≥15%, correlation >40%, exposure >10% per token)
**Then** an immediate alert is sent via Discord
**And** the dashboard displays a prominent warning
**And** alert includes specific threshold breached and current value
**And** kill-switch is triggered for live mode when drawdown ≥15%
**And** FR-016 is satisfied

---

## Epic 4: Learning Loop and Calibration

Implement prediction accuracy tracking, ML feedback loop analysis, confidence threshold calibration, and training data generation to continuously improve model performance.

### Story 4.1: Prediction Accuracy Tracking System (5 SP)

As a model performance analyst,
I want prediction accuracy tracked over time across all signal types,
So that I can measure how well the system predicts market movements.

**Acceptance Criteria:**

**Given** signals are generated with confidence scores and directions
**When** signal outcomes are determined (target hit, stop hit, or expired)
**Then** prediction accuracy is calculated per signal type and confidence bucket
**And** accuracy metrics are stored with timestamps for trend analysis
**And** rolling accuracy (7-day, 30-day, 90-day) is computed and displayed
**And** accuracy degradation triggers are configured (alert if <55% over 20 trades)
**And** FR-017 is satisfied

---

### Story 4.2: ML Feedback Loop Engine (5 SP)

As a machine learning engineer,
I want an automated feedback loop that analyzes predictions versus actual outcomes,
So that the system can learn from its mistakes and improve over time.

**Acceptance Criteria:**

**Given** prediction accuracy data is collected over time
**When** the feedback loop runs (daily batch process)
**Then** prediction errors are analyzed by feature combinations
**And** systematic biases are identified (e.g., overconfidence in ranging markets)
**And** feature importance is recalculated based on recent outcomes
**And** model performance reports are generated with actionable insights
**And** FR-018 is satisfied

---

### Story 4.3: Confidence Threshold Calibration (5 SP)

As a calibration engineer,
I want confidence thresholds dynamically calibrated based on observed accuracy,
So that stated confidence aligns with actual win rates.

**Acceptance Criteria:**

**Given** historical accuracy data exists for confidence buckets (e.g., 75-80%, 80-85%)
**When** calibration analysis runs
**Then** expected calibration error (ECE) is calculated per bucket
**And** confidence thresholds are adjusted to align with observed accuracy
**And** calibration drift >0.10 ECE triggers retraining recommendations
**And** calibration history is tracked for audit purposes
**And** FR-019 is satisfied

---

### Story 4.4: Training Data Generation Pipeline (5 SP)

As a data scientist,
I want automated training data generation from signal outcomes,
So that models can be retrained on fresh, labeled data.

**Acceptance Criteria:**

**Given** signal outcomes are tracked with features and results
**When** the training data pipeline runs
**Then** labeled training examples are generated (features + outcome label)
**And** data is balanced to avoid class imbalance issues
**And** training datasets are versioned and stored with metadata
**And** data quality checks validate feature completeness and label correctness
**And** FR-020 is satisfied

---

## Epic 5: Operator Experience, Reporting, and Community

Deliver mobile-responsive dashboard design, configurable alert thresholds, performance reporting, and Discord community integration to enhance operator experience.

### Story 5.1: Mobile-Responsive Dashboard Design (5 SP)

As a mobile operator,
I want a mobile-responsive dashboard that works on phones and tablets,
So that I can monitor signals and portfolio status on the go.

**Acceptance Criteria:**

**Given** the dashboard is accessed from a mobile device
**When** the page loads
**Then** layout adapts to screen size (responsive breakpoints: 320px, 768px, 1024px)
**And** critical information (active signals, portfolio PnL, risk alerts) is visible without scrolling
**And** touch-friendly controls replace hover interactions
**And** load time remains <3 seconds on 4G connections
**And** FR-021 is satisfied

---

### Story 5.2: User-Configurable Alert Thresholds (3 SP)

As a system operator,
I want configurable alert thresholds for different notification types,
So that I can customize alert sensitivity to my preferences.

**Acceptance Criteria:**

**Given** the alert configuration panel is accessible
**When** thresholds are adjusted
**Then** Discord posting threshold is configurable (default 40%, range 40-90%)
**And** internal trade signal threshold is configurable (default 75%, range 60-90%)
**And** risk breach alert thresholds are adjustable (drawdown, correlation, exposure)
**And** alert channels can be enabled/disabled per alert type
**And** configuration changes are persisted and take effect immediately
**And** FR-022 is satisfied

---

### Story 5.3: Performance Reporting Engine (5 SP)

As a portfolio manager,
I want automated performance reports (daily, weekly, monthly),
So that I can track trading performance over time.

**Acceptance Criteria:**

**Given** trading data exists in the system
**When** a report period ends (daily at 00:00 UTC, weekly on Monday, monthly on 1st)
**Then** a performance report is generated automatically
**And** report includes: total PnL, win rate, average trade return, max drawdown, turnover (trades/day)
**And** reports are delivered via Discord and stored in the dashboard history
**And** reports compare current period to previous period and benchmark
**And** FR-023 is satisfied

---

### Story 5.4: Discord Community Integration (5 SP)

As a community member,
I want Discord integration for community discussion and signal sharing,
So that I can engage with other operators and share insights.

**Acceptance Criteria:**

**Given** Discord bot is configured with appropriate permissions
**When** community features are enabled
**Then** signal alerts are posted to designated channels with discussion threads
**And** performance reports are shared with community context
**And** operators can query recent signals via Discord commands
**And** risk alerts are posted to #alerts channel with actionable context
**And** FR-024 is satisfied

---

## Epic 6: Safe Trading Execution and Validation Gates (Backtest->Paper->Live)

Implement safe trading execution with continuous backtesting, exchange adapters, paper trading orchestration, live trading gating, kill-switches, and hedging support.

### Story 6.1: Order Type Execution Support (3 SP)

As a trade execution engineer,
I want support for market and limit order types,
So that trades can be executed with appropriate order strategies.

**Acceptance Criteria:**

**Given** an exchange adapter is configured
**When** an order is submitted
**Then** market orders execute immediately at best available price
**And** limit orders are placed with specified price and timeout
**And** order status is tracked through lifecycle (pending, open, filled, cancelled, rejected)
**And** REST + WebSocket are used for order lifecycle management
**And** idempotent clientOrderId prevents duplicate orders
**And** FR-004a is satisfied

---

### Story 6.2: Continuous Backtesting Runner (5 SP)

As a strategy validator,
I want a continuous backtesting runner with walk-forward capability,
So that strategies are constantly validated against historical data.

**Acceptance Criteria:**

**Given** historical OHLCV data exists for supported timeframes
**When** the backtest runner executes
**Then** walk-forward analysis tests strategies on out-of-sample data
**And** slippage and fee sensitivity sweeps are performed
**And** stress tests simulate extreme market conditions
**And** backtest results include: win rate, profit factor, max drawdown, Sharpe ratio, turnover
**And** results are stored in the strategy registry for comparison
**And** FR-025 is satisfied

---

### Story 6.3: Exchange Adapter Interface and Connectors (5 SP)

As an integration engineer,
I want a unified exchange adapter interface with connectors for Binance, Bybit, and Bitget,
So that the system can interact with multiple exchanges consistently.

**Acceptance Criteria:**

**Given** exchange API credentials are configured
**When** the adapter interface is used
**Then** a common interface abstracts exchange-specific details
**And** Binance connector provides reference market data (read-only)
**And** Bybit connector supports paper trading (demo account)
**And** Bitget connector supports live trading (production account)
**And** each connector implements: get_balance, get_positions, place_order, cancel_order, get_order_status
**And** FR-026 is satisfied

---

### Story 6.4: Paper Trading Orchestration (5 SP)

As a risk manager,
I want paper trading orchestration on Bybit demo with shadow backtests continuing,
So that strategies can be validated without capital risk.

**Acceptance Criteria:**

**Given** Bybit demo credentials are configured
**When** paper trading mode is enabled
**Then** trades are executed on Bybit demo account
**And** shadow backtests continue running in parallel with live paper trades
**And** paper performance is tracked separately from backtest projections
**And** paper gate criteria are enforced: max 5% drawdown, 55% win rate, 7-day minimum duration
**And** turnover is reported as filled orders/day aggregated by order_id UTC
**And** FR-027 is satisfied

---

### Story 6.5: Live Trading Orchestration with Gating (5 SP)

As a trading operator,
I want live trading orchestration on Bitget with explicit enable/disable gating,
So that live trading only occurs after proper validation and human approval.

**Acceptance Criteria:**

**Given** Bitget live credentials are configured and strategy has passed paper gate
**When** live trading is explicitly enabled by authorized operator
**Then** trades are executed on Bitget live account
**And** live trading can be disabled immediately via dashboard or API
**And** live mode requires promotion packet approval with evidence, risk invariants, and rollback plan
**And** all live trades are logged to audit trail with 7-year retention
**And** FR-028 is satisfied

---

### Story 6.6: Mode-Specific Kill-Switch Enforcement (5 SP)

As a safety engineer,
I want mode-specific kill-switch enforcement (paper self-eval/resume; live human re-auth),
So that different trading modes have appropriate safety responses.

**Acceptance Criteria:**

**Given** kill-switch thresholds are configured (drawdown ≥15%)
**When** a kill-switch is triggered
**Then** for paper mode: positions are closed, trading is suspended, self-evaluation runs, auto-resume with adjusted params
**And** for live mode: positions are closed, trading is disabled, human re-authorization required before resume
**And** kill-switch events are logged with timestamp, trigger reason, and actions taken
**And** Discord alerts notify operators of kill-switch activation
**And** FR-029 is satisfied

---

### Story 6.7: Direct Perps Execution for High-Confidence Setups (3 SP)

As a high-confidence trader,
I want direct perps execution for setups when evidence supports non-grid strategies,
So that optimal strategies can be executed based on market conditions.

**Acceptance Criteria:**

**Given** a high-confidence signal (≥75%) is generated
**When** the strategy evaluator determines non-grid execution is appropriate
**Then** direct perps orders are placed (market or limit based on urgency)
**And** position sizing follows risk limits (≤1% per-trade risk, ≤10% per token)
**And** leverage is capped at 3x maximum
**And** execution is logged with rationale for non-grid strategy selection
**And** FR-030 is satisfied

---

### Story 6.8: Hedging and Market-Neutral Position Support (5 SP)

As a risk-conscious trader,
I want hedging and market-neutral position support for risk management,
So that I can reduce directional exposure when appropriate.

**Acceptance Criteria:**

**Given** multiple positions exist or are being considered
**When** hedging logic is triggered
**Then** offsetting positions can be opened to reduce net exposure
**And** market-neutral strategies are supported (long/short pairs in perps only)
**And** hedge ratios are calculated based on correlation and volatility
**And** hedging decisions respect portfolio risk limits (≤15% drawdown, ≤40% correlation)
**And** no spot positions are used for hedging (perps-only)
**And** FR-030a is satisfied

---

## Epic 7: Observability and Operational Health

Implement Grafana-first observability with comprehensive KPIs, health monitoring, and alerting to ensure system reliability and operational visibility.

### Story 7.1: Grafana Dashboard Infrastructure Setup (5 SP)

As an operations engineer,
I want Grafana dashboards configured for data ingest health, backtest KPIs, paper execution, live execution, strategy registry, and brain registry,
So that I can monitor system health and performance from a single observability interface.

**Acceptance Criteria:**

**Given** Grafana is deployed on the chiseai network with port 3001
**When** the dashboard infrastructure initializes
**Then** data source connections are established for InfluxDB, PostgreSQL, and Redis
**And** folder structure is created for: Data & Ingest, Backtest KPIs, Paper Execution, Live Execution, Strategy Registry, Brain Registry
**And** base dashboard templates are provisioned with standard time ranges and refresh intervals
**And** dashboard load time is <3 seconds (95th percentile)
**And** FR-031 is satisfied

---

### Story 7.2: Data and Ingest Health Monitoring (5 SP)

As a data operations engineer,
I want real-time monitoring of data freshness, ingestion pipeline health, and data quality metrics,
So that I can detect and respond to data gaps or pipeline failures immediately.

**Acceptance Criteria:**

**Given** OHLCV data is being ingested from exchanges
**When** the data health monitoring system runs
**Then** data freshness is tracked per timeframe (1m, 5m, 15m, 1h, 4h, 1d) with timestamps
**And** gaps are detected when data is older than 2x the timeframe interval
**And** API failure rate is calculated and alerts trigger when >10%
**And** Discord alerts are sent to #alerts channel for data freshness issues
**And** circuit breaker status is displayed on the dashboard
**And** FR-031 is satisfied

---

### Story 7.3: Backtest and Paper Trading KPI Dashboards (5 SP)

As a strategy performance analyst,
I want dedicated dashboards for backtest results and paper trading performance metrics,
So that I can compare projected vs actual performance and validate strategy effectiveness.

**Acceptance Criteria:**

**Given** backtest and paper trading data exists in the system
**When** the KPI dashboards are accessed
**Then** backtest dashboard displays: win rate, profit factor, max drawdown, Sharpe ratio, turnover (filled orders/day by order_id UTC)
**And** paper execution dashboard shows: realized PnL, win rate, drawdown, trade count, slippage vs backtest
**And** walk-forward validation results are visualized with in-sample vs out-of-sample comparisons
**And** paper gate criteria progress is tracked (max 5% drawdown, 55% win rate, 7-day duration)
**And** FR-031 is satisfied

---

### Story 7.4: Live Execution and Risk Alerting (5 SP)

As a live trading operator,
I want real-time monitoring of live trades, portfolio exposure, and risk thresholds with automated alerting,
So that I can respond immediately to risk breaches or operational issues.

**Acceptance Criteria:**

**Given** live trading is enabled on Bitget
**When** live execution monitoring is active
**Then** live PnL, positions, and exposure are displayed in real-time
**And** drawdown is tracked with alerts at 10% (warning) and ≥15% (kill-switch trigger)
**And** Discord alerts are sent for: kill-switch triggered, drawdown warnings, API disconnects, model drift
**And** kill-switch events are logged with timestamp, trigger reason, and actions taken
**And** runbook links are provided in alert messages for operational response
**And** FR-031 is satisfied

---

### Story 7.5: System Health and Alerting Integration (3 SP)

As a system reliability engineer,
I want integrated health checks and alerting across all system components,
So that operational issues are detected and escalated through appropriate channels.

**Acceptance Criteria:**

**Given** all ChiseAI services are deployed on the chiseai network
**When** the health monitoring system runs
**Then** service health checks verify: API responsiveness, database connectivity, Redis availability, exchange API status
**And** health status is displayed on Grafana with green/yellow/red indicators
**And** alerts are routed to Discord #alerts with severity levels (info, warning, critical)
**And** alert suppression prevents duplicate notifications within 15 minutes
**And** system uptime target of ≥99.9% is tracked and reported
**And** FR-031 is satisfied

---

## Epic 8: Chise Autonomy + Brain Operations (Governance)

Implement standard PR workflows, status discipline, Taiga synchronization, and Brain CI/CD operations including registry, shadow mode, evaluation metrics, and upgrade cadence with human approval gating.

### Story 8.1: PR Workflow and Traceability Enforcement (5 SP)

As a DevOps engineer,
I want standardized PR workflows with mandatory story ID traceability and Woodpecker CI gates,
So that all code changes are tracked, validated, and traceable to requirements.

**Acceptance Criteria:**

**Given** a PR is created in Gitea
**When** the PR validation runs
**Then** PR titles are validated to include a canonical story ID (ST-NS-###, CH-BG-###, FT-NS-###-###, or REWARD-###)
**And** PRs without story IDs in titles are blocked by CI
**And** Woodpecker CI must pass (green build) before merge is allowed
**And** required status check context `ci/woodpecker/push/woodpecker` is enforced
**And** merge to main only occurs after CI passes and human approval
**And** FR-DEV-001 and FR-DEV-002 are satisfied

---

### Story 8.2: Status Discipline and Validation (5 SP)

As a project governance engineer,
I want automated status synchronization between implementation state and workflow status files,
So that the repo state remains the single source of truth for project progress.

**Acceptance Criteria:**

**Given** code changes are made to story implementations
**When** status validation runs
**Then** `docs/bmm-workflow-status.yaml` is checked for alignment with actual implementation state
**And** `docs/validation/validation-registry.yaml` is validated for consistency
**And** CI blocks PRs where status files are out of sync with code changes
**And** `python3 scripts/validate_status_sync.py` passes before merge
**And** status vocabulary follows canonical definitions (planned|in_progress|completed|blocked|deprecated)
**And** FR-DEV-003 is satisfied

---

### Story 8.3: Taiga Synchronization and Monitoring (5 SP)

As a project coordinator,
I want bidirectional sync between repo-canonical story metadata and Taiga project management,
So that human stakeholders can monitor progress without manual copy/paste.

**Acceptance Criteria:**

**Given** stories exist in the repo with metadata (id, title, status, acceptance criteria)
**When** Taiga sync runs
**Then** repo story metadata is synchronized to Taiga with status mapping
**And** conflicts are resolved with repo as the canonical source of truth
**And** sync includes: story_id, title, status, acceptance criteria, sprint assignment
**And** sync command is available via `.opencode/command/chise-taiga-sync.md`
**And** sync runs automatically on PR merge or on-demand
**And** FR-DEV-004 is satisfied

---

### Story 8.4: Iteration Loop Compliance and Logging (5 SP)

As an iteration process engineer,
I want standardized iteration logging via Redis/Qdrant with CI validation,
So that work is tracked, decisions are recorded, and learnings are captured for continuous improvement.

**Acceptance Criteria:**

**Given** a story is in progress
**When** iteration tracking is active
**Then** iteration logs are stored in Redis at `bmad:chiseai:iterlog:story:<STORY_ID>` with 5-day TTL
**And** required fields are captured: story_id, story_title, phase, status, started_at
**And** decisions and learnings are appended to lists for promotion to Qdrant
**And** fallback to `docs/tempmemories/` when Redis/Qdrant unavailable
**And** CI validates iteration loop compliance via `python3 scripts/validate_iterloop_compliance.py --story-id=<id>`
**And** FR-DEV-005 is satisfied

---

### Story 8.5: Brain Registry and Version Management (5 SP)

As a brain operations engineer,
I want a Brain Registry for version management and BrainEval results tracking,
So that brain versions are auditable and performance history is maintained.

**Acceptance Criteria:**

**Given** brain models are deployed for signal generation
**When** brain registry is accessed
**Then** brain versions are tracked with semantic versioning (e.g., v1.2.3)
**And** each version stores: model artifacts, config, training data version, evaluation metrics
**And** BrainEval results are recorded: paper carryover rate, false positives, time-to-improvement, low turnover bias, compute cost, safety compliance
**And** registry supports champion/current and challenger candidate tracking
**And** brain metadata is queryable by version, date, and performance metrics
**And** FR-DEV-001 (brain operations) is satisfied

---

### Story 8.6: Brain Shadow Mode and Evaluation (5 SP)

As a brain validation engineer,
I want shadow mode testing for new brains without affecting live decisions,
So that brain upgrades can be validated safely before promotion.

**Acceptance Criteria:**

**Given** a new brain version is candidate for promotion
**When** shadow mode is enabled
**Then** new brain runs in parallel with current brain on live market data
**Then** shadow predictions are logged but not used for trading decisions
**And** shadow performance is compared against current brain: accuracy, latency, resource usage
**And** BrainEval metrics are calculated: paper carryover rate, false positive rate, improvement velocity
**And** shadow results feed into promotion packet for human review
**And** auto-deploy to paper is allowed; live requires explicit human approval
**And** FR-DEV-002 (brain operations) is satisfied

---

### Story 8.7: Brain Upgrade Cadence and Promotion (5 SP)

As a brain lifecycle manager,
I want structured upgrade cadences (rapid, weekly, monthly) with transition rules,
So that brain updates follow predictable schedules with appropriate validation gates.

**Acceptance Criteria:**

**Given** brain upgrade policies are configured
**When** upgrade cadence is determined
**Then** rapid phase: upgrades every 3 days with minimal validation
**And** weekly phase: upgrades every 7 days with full BrainEval
**And** monthly phase: upgrades every 30 days with comprehensive testing
**And** transition rules define when to move between phases based on stability metrics
**And** promotion requires human approval with evidence from BrainEval
**And** auto-deploy is allowed to paper only; live requires explicit human authorization
**And** rollback plan is included in every promotion packet
**And** FR-DEV-003 (brain operations) is satisfied

---

## Epic 9: Strategy Evolution and Promotion Pipeline

Implement constrained strategy evolution through DSL mutations, strategy registry with champion/challenger tracking, and a full CI/CD promotion pipeline from candidate to human-approved live trading.

### Story 9.1: Strategy DSL Schema and Validation (5 SP)

As a strategy DSL engineer,
I want a constrained strategy DSL schema supporting parameter and structural mutations,
So that strategies can evolve safely without arbitrary live code edits.

**Acceptance Criteria:**

**Given** strategy configurations are defined in DSL format
**When** DSL validation runs
**Then** schema supports parameter mutations (grid spacing, position sizing, entry/exit thresholds)
**And** schema supports structural mutations (indicator combinations, timeframe selections, condition logic)
**And** all DSL configs are diffable and reproducible (deterministic serialization)
**And** validation enforces: no arbitrary code execution, only approved config interfaces
**And** DSL version is tracked for backward compatibility
**And** FR-EVO-001 and FR-EVO-002 are satisfied

---

### Story 9.2: Strategy Registry and Champion/Challenger Tracking (5 SP)

As a strategy registry manager,
I want a strategy registry supporting champion/challenger tracking with artifact storage,
So that strategy evolution history is auditable and performance is comparable.

**Acceptance Criteria:**

**Given** strategies are registered in the system
**When** the strategy registry is accessed
**Then** champion (current best) and challenger (candidate) strategies are tracked
**And** artifacts are stored: config DSL, diffs vs parent, backtest results, paper results
**And** registry supports strategy lineage (parent-child relationships)
**And** metadata includes: creation date, author, mutation type, performance metrics
**And** registry is queryable by strategy ID, status, performance, and tags
**And** FR-EVO-003 is satisfied

---

### Story 9.3: Backtest Gate and Walk-Forward Validation (5 SP)

As a strategy validation engineer,
I want a backtest gate with walk-forward validation, slippage/fee sensitivity, and stress tests,
So that only robust strategies advance to paper trading.

**Acceptance Criteria:**

**Given** a strategy candidate is submitted for validation
**When** the backtest gate executes
**Then** walk-forward analysis tests on out-of-sample data (minimum 30% OOS)
**And** slippage sensitivity sweeps: 0bps, 5bps, 10bps, 20bps
**And** fee sensitivity sweeps: base, 1.5x, 2x fees
**And** stress tests simulate extreme market conditions (flash crashes, high volatility)
**And** results include: win rate, profit factor, max drawdown, Sharpe ratio, turnover (filled orders/day)
**And** strategies must achieve ≥55% win rate and <15% drawdown to pass
**And** FR-EVO-004 (backtest gate) is satisfied

---

### Story 9.4: Paper Canary and Paper Full Gates (5 SP)

As a paper trading validator,
I want paper canary and paper full gates with strict criteria,
So that strategies prove themselves in simulated live conditions before live deployment.

**Acceptance Criteria:**

**Given** a strategy has passed the backtest gate
**When** paper canary phase begins
**Then** canary runs with limited capital exposure for minimum 24 hours
**And** canary criteria: max 2% drawdown, no critical errors, order execution latency <1s
**And** upon canary success, paper full phase begins with full exposure
**And** paper full criteria: max 5% drawdown, ≥55% win rate over minimum 7 days
**And** turnover is tracked as filled orders/day aggregated by order_id UTC
**And** trade budgeter enforces 20 trades/day ceiling
**And** shadow backtests continue running in parallel with paper trades
**And** FR-EVO-004 (paper gates) is satisfied

---

### Story 9.5: Promotion Packet Generation (5 SP)

As a promotion coordinator,
I want automated promotion packets for human approvals,
So that live deployment decisions are informed by comprehensive evidence and risk assessment.

**Acceptance Criteria:**

**Given** a strategy has passed paper full gate
**When** promotion packet is generated
**Then** packet includes: strategy config DSL, diff from champion, backtest results, paper results
**And** evidence section: win rates, drawdowns, Sharpe ratios, turnover comparisons
**And** risk invariants: max risk per trade (≤1%), per grid (≤2%), portfolio drawdown (≤15%), leverage (≤3x)
**And** rollback plan: conditions for rollback, rollback steps, estimated time to rollback
**And** packet is generated via `.opencode/command/chise-promotion-packet.md`
**And** packet status tracked: pending review, approved, rejected
**And** FR-EVO-005 is satisfied

---

### Story 9.6: Trade Budgeting and Turnover Reporting (3 SP)

As a trading operations manager,
I want optional trade-frequency budgeting and standardized turnover reporting,
So that trading costs and stability can be managed as secondary controls.

**Acceptance Criteria:**

**Given** trading activity is occurring in paper or live mode
**When** trade budgeting is enabled
**Then** trade budgeter enforces 20 trades/day ceiling per strategy
**And** turnover is calculated as filled orders/day aggregated per order_id by UTC day buckets
**And** turnover reporting includes: average trades/day, p95 trades/day, max trades/day
**And** selection policy uses lexicographic ranking: profit first, then turnover (3% epsilon), then complexity
**And** budget alerts trigger at 80% and 100% of daily limit
**And** reporting is available via `.opencode/command/chise-turnover-report.md`
**And** FR-EVO-006 is satisfied

---

### Story 9.7: Strategy CI/CD Pipeline Orchestration (5 SP)

As a strategy CI/CD engineer,
I want a complete promotion pipeline from candidate to human-approved live,
So that strategy deployments follow a consistent, validated, and gated process.

**Acceptance Criteria:**

**Given** a strategy candidate is submitted
**When** the CI/CD pipeline executes
**Then** pipeline stages execute sequentially: candidate → backtest gate → paper canary → paper full → promotion packet → human-approved live
**And** each gate must pass before advancing to next stage
**And** human approval is required for live deployment with signed promotion packet
**And** pipeline status is visible in strategy registry and Grafana dashboard
**And** rollback is automatic on: drawdown approaching thresholds, win rate <55% over 20 trades, ECE >0.10, safety test failure
**And** pipeline supports `.opencode/command/chise-rd-iteration.md` for R&D loops
**And** FR-EVO-004 (full pipeline) is satisfied

---

(End of file - total 526 lines)
