# Sprint Q2-2 Plan: Signal Generation & Portfolio Risk

**Sprint ID:** q2-2  
**Sprint Name:** Signal Generation & Portfolio Risk  
**Status:** Planned  
**Epics:** EP-NS-002, EP-NS-003  
**Original Story Points:** 58 (23 from EP-NS-002 + 35 from EP-NS-003)  
**Split Story Points:** 58 (maintained)  
**Total Sub-Stories:** 12 (5 original stories split into 12 sub-stories)  

---

## Executive Summary

This sprint plan addresses the requirement that all stories must be ≤5 SP. The original 5 stories from EP-NS-003 (Portfolio Risk Management) exceeded this limit:

| Original Story | Original SP | Split Into | New SP Distribution |
|---------------|-------------|------------|---------------------|
| ST-NS-012 | 8 SP | 012A, 012B | 4 SP + 4 SP |
| ST-NS-013 | 7 SP | 013A, 013B | 4 SP + 3 SP |
| ST-NS-014 | 7 SP | 014A, 014B | 4 SP + 3 SP |
| ST-NS-015 | 7 SP | 015A, 015B | 4 SP + 3 SP |
| ST-NS-016 | 6 SP | 016A, 016B | 3 SP + 3 SP |

**Note:** Stories from EP-NS-002 (ST-NS-007 through ST-NS-011) are already ≤5 SP and do not require splitting.

---

## EP-NS-002: Signal Generation & Delivery (No Split Required)

These stories are already within the 5 SP limit:

| Story ID | Title | SP | Status | FR Coverage |
|----------|-------|-----|--------|-------------|
| ST-NS-007 | Real-time Signal Generation | 5 | Completed | FR-007 |
| ST-NS-008 | Dashboard Pre-market Briefing | 5 | Completed | FR-008 |
| ST-NS-009 | Discord Alert Integration | 5 | Completed | FR-009 |
| ST-NS-010 | Signal Detail Breakdown | 5 | Completed | FR-010 |
| ST-NS-011 | Historical Context Panel | 3 | Completed | FR-011 |

---

## EP-NS-003: Portfolio Risk Management (Split Stories)

### ST-NS-012: Position Sizing Engine → Split into 012A + 012B

**Original:** 8 SP | **Rationale for Split:** Position sizing involves both core calculation logic and integration with portfolio state. These are separable concerns with distinct testing requirements.

---

#### ST-NS-012A: Position Sizing Core Engine (4 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-012 (partial)  
**Dependencies:** None  

**Description:**  
Implement the core position sizing calculation engine with Kelly Criterion, fixed fractional, and volatility-based sizing methods.

**Acceptance Criteria:**
1. Kelly Criterion sizing is calculated correctly (f* = (bp - q) / b)
2. Fixed fractional sizing supports configurable risk percentage (default 1-2%)
3. Volatility-based sizing uses ATR or historical volatility
4. Position size is calculated as: (Account Balance × Risk %) / (Stop Distance × Tick Value)
5. Maximum position size limits are enforced per token and portfolio-wide
6. Unit tests cover all sizing methods with edge cases (zero volatility, extreme prices)

**Rationale for 4 SP:**
- Mathematical implementation of 3 sizing algorithms (2 SP)
- Unit testing with edge cases (1 SP)
- Documentation and validation (1 SP)

---

#### ST-NS-012B: Position Sizing Integration & API (4 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-012 (remaining)  
**Dependencies:** ST-NS-012A (Position Sizing Core Engine)  

**Description:**  
Integrate position sizing engine with portfolio state, signal generation, and expose via API for dashboard consumption.

**Acceptance Criteria:**
1. Position sizing recommendations are generated automatically with each signal
2. Current portfolio exposure is factored into sizing calculations
3. API endpoint `/api/v1/position-size` returns sizing recommendation for a given signal
4. Sizing recommendations include: suggested size, sizing method used, risk amount, max position check
5. Integration with signal detail breakdown (ST-NS-010) to display sizing
6. Sizing is recalculated when portfolio balance changes >5%

**Rationale for 4 SP:**
- API design and implementation (1 SP)
- Portfolio state integration (2 SP)
- Signal generation integration and testing (1 SP)

---

### ST-NS-013: Stop-Loss Recommendation System → Split into 013A + 013B

**Original:** 7 SP | **Rationale for Split:** Stop-loss calculation (technical analysis) and recommendation delivery (integration) are distinct phases that can be developed and tested independently.

---

#### ST-NS-013A: Stop-Loss Calculation Engine (4 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-013 (partial)  
**Dependencies:** ST-NS-001 (Multi-timeframe Analysis)  

**Description:**  
Implement stop-loss calculation engine using multiple methods: technical levels (support/resistance), ATR-based, and percentage-based.

**Acceptance Criteria:**
1. ATR-based stop-loss calculates at 2× ATR(14) from entry price
2. Technical level stops use nearest support (long) / resistance (short) from key levels
3. Percentage-based stops support configurable % (default 2-5%)
4. Stop-loss distance respects minimum risk:reward ratio (default 1:1.5)
5. Multiple stop methods can be compared and the optimal selected
6. Unit tests validate stop calculations across market conditions

**Rationale for 4 SP:**
- Implementation of 3 stop calculation methods (2 SP)
- Key levels integration from market analysis (1 SP)
- Testing and optimization logic (1 SP)

---

#### ST-NS-013B: Stop-Loss Integration & Signal Delivery (3 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-013 (remaining)  
**Dependencies:** ST-NS-013A (Stop-Loss Calculation Engine), ST-NS-010 (Signal Detail Breakdown)  

**Description:**  
Integrate stop-loss recommendations with signal generation and deliver via dashboard and alerts.

**Acceptance Criteria:**
1. Stop-loss level is included in every generated signal
2. Stop-loss is displayed in signal detail breakdown panel
3. Discord alerts include stop-loss level when signal is actionable
4. Stop-loss updates dynamically if key levels change before entry
5. Trailing stop option is calculated and offered when trend is strong
6. Stop-loss hit tracking is implemented for outcome correlation

**Rationale for 3 SP:**
- Signal generation integration (1 SP)
- Dashboard/Discord integration (1 SP)
- Dynamic update and trailing stop logic (1 SP)

---

### ST-NS-014: Portfolio Risk Exposure Monitor → Split into 014A + 014B

**Original:** 7 SP | **Rationale for Split:** Data collection/monitoring infrastructure and risk calculation/reporting are separable layers with different testing approaches.

---

#### ST-NS-014A: Portfolio Data Collection & State Management (4 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-014 (partial)  
**Dependencies:** ST-DATA-002 (Execution Market Data Ingestion)  

**Description:**  
Implement real-time portfolio data collection, position tracking, and state management infrastructure.

**Acceptance Criteria:**
1. Portfolio positions are tracked in real-time with current PnL
2. Position updates are received within 1 second of exchange confirmation
3. Portfolio state includes: positions, balances, margin used, available equity
4. Historical portfolio snapshots are stored for trend analysis
5. Data persistence handles connection failures gracefully with replay capability
6. State is queryable via API with <100ms latency

**Rationale for 4 SP:**
- Real-time data ingestion and state management (2 SP)
- Data persistence and fault tolerance (1 SP)
- API implementation (1 SP)

---

#### ST-NS-014B: Risk Exposure Calculation & Dashboard (3 SP)

**Epic:** EP-NS-003  
**Priority:** P0-CRITICAL  
**FR Coverage:** FR-014 (remaining)  
**Dependencies:** ST-NS-014A (Portfolio Data Collection)  

**Description:**  
Calculate portfolio-level risk metrics and expose via dashboard panels and alerting.

**Acceptance Criteria:**
1. Total portfolio exposure is calculated as sum of position notionals
2. Margin utilization percentage is displayed (used / total)
3. Portfolio heat map shows exposure by token and direction
4. Risk metrics update in real-time on dashboard (<5s latency)
5. Maximum exposure alerts trigger at configurable thresholds (default 80%)
6. Risk report is generated on-demand with current exposure breakdown

**Rationale for 3 SP:**
- Risk metric calculations (1 SP)
- Dashboard panel implementation (1 SP)
- Alerting integration (1 SP)

---

### ST-NS-015: Correlation Analysis Engine → Split into 015A + 015B

**Original:** 7 SP | **Rationale for Split:** Correlation calculation (statistical/mathematical) and correlation application (risk management features) are distinct domains.

---

#### ST-NS-015A: Correlation Calculation Engine (4 SP)

**Epic:** EP-NS-003  
**Priority:** P1-HIGH  
**FR Coverage:** FR-015 (partial)  
**Dependencies:** ST-NS-001 (Multi-timeframe Analysis)  

**Description:**  
Implement correlation calculation engine for portfolio positions using multiple timeframes and correlation methods.

**Acceptance Criteria:**
1. Pearson correlation is calculated between all token pairs
2. Rolling correlation windows: 24h, 7d, 30d with configurable lookback
3. Correlation matrix is updated every hour with latest price data
4. Correlation significance is tested (p-value < 0.05)
5. Spearman rank correlation is available for non-linear relationships
6. Correlation data is stored with timestamp for historical analysis

**Rationale for 4 SP:**
- Statistical calculation implementation (2 SP)
- Multiple timeframe and method support (1 SP)
- Data storage and scheduling (1 SP)

---

#### ST-NS-015B: Correlation Risk Integration & Alerts (3 SP)

**Epic:** EP-NS-003  
**Priority:** P1-HIGH  
**FR Coverage:** FR-015 (remaining)  
**Dependencies:** ST-NS-015A (Correlation Calculation Engine), ST-NS-014 (Portfolio Risk Exposure Monitor)  

**Description:**  
Integrate correlation analysis with risk management to detect concentration risk and provide diversification recommendations.

**Acceptance Criteria:**
1. Highly correlated positions (>0.8) are flagged as concentration risk
2. Diversification score is calculated for the portfolio (0-100)
3. Correlation alerts trigger when new high-correlation positions are added
4. Position sizing is adjusted downward for correlated assets
5. Correlation matrix is visualized in dashboard heat map
6. Recommendations suggest uncorrelated alternatives when concentration is high

**Rationale for 3 SP:**
- Risk integration logic (1 SP)
- Dashboard visualization (1 SP)
- Recommendation engine (1 SP)

---

### ST-NS-016: Risk Threshold Alert System → Split into 016A + 016B

**Original:** 6 SP | **Rationale for Split:** Alert rule engine and notification delivery are separable components with different integration points.

---

#### ST-NS-016A: Risk Threshold Rule Engine (3 SP)

**Epic:** EP-NS-003  
**Priority:** P1-HIGH  
**FR Coverage:** FR-016 (partial)  
**Dependencies:** ST-NS-014 (Portfolio Risk Exposure Monitor)  

**Description:**  
Implement configurable risk threshold rule engine with multiple alert levels and conditions.

**Acceptance Criteria:**
1. Threshold rules are configurable: exposure %, drawdown %, margin %, correlation
2. Multiple alert levels: INFO (70%), WARNING (80%), CRITICAL (90%)
3. Rule evaluation runs every minute against current portfolio state
4. Custom rules can be defined via configuration file
5. Rule conditions support AND/OR logic for complex thresholds
6. Threshold breaches are logged with timestamp, value, and severity

**Rationale for 3 SP:**
- Rule engine architecture (1 SP)
- Configuration and evaluation logic (1 SP)
- Testing with complex rule combinations (1 SP)

---

#### ST-NS-016B: Risk Alert Delivery & Management (3 SP)

**Epic:** EP-NS-003  
**Priority:** P1-HIGH  
**FR Coverage:** FR-016 (remaining)  
**Dependencies:** ST-NS-016A (Risk Threshold Rule Engine), ST-NS-009 (Discord Alert Integration)  

**Description:**  
Deliver risk alerts via multiple channels with throttling, acknowledgment, and escalation.

**Acceptance Criteria:**
1. Alerts are delivered to Discord #risk-alerts channel
2. Alert throttling prevents spam (max 1 alert per 15 min per threshold)
3. CRITICAL alerts require acknowledgment within 5 minutes
4. Unacknowledged CRITICAL alerts escalate to secondary channel
5. Alert history is queryable with filter by severity, time, threshold type
6. Alert delivery status is tracked (sent, delivered, acknowledged)

**Rationale for 3 SP:**
- Multi-channel delivery integration (1 SP)
- Throttling and acknowledgment logic (1 SP)
- Escalation and history tracking (1 SP)

---

## Sprint Execution Order

### Phase 1: Foundation (Weeks 1-2)
1. **ST-NS-012A** - Position Sizing Core Engine
2. **ST-NS-013A** - Stop-Loss Calculation Engine
3. **ST-NS-014A** - Portfolio Data Collection

### Phase 2: Core Integration (Weeks 3-4)
4. **ST-NS-012B** - Position Sizing Integration
5. **ST-NS-013B** - Stop-Loss Integration
6. **ST-NS-014B** - Risk Exposure Dashboard

### Phase 3: Advanced Risk (Weeks 5-6)
7. **ST-NS-015A** - Correlation Calculation Engine
8. **ST-NS-016A** - Risk Threshold Rule Engine

### Phase 4: Final Integration (Weeks 7-8)
9. **ST-NS-015B** - Correlation Risk Integration
10. **ST-NS-016B** - Risk Alert Delivery

---

## Dependencies Summary

```
ST-NS-012A ──┬──> ST-NS-012B
             │
ST-NS-013A ──┼──> ST-NS-013B
             │
ST-NS-014A ──┼──> ST-NS-014B ──┬──> ST-NS-015B
             │                  │
             └──> ST-NS-016A ────┴──> ST-NS-016B
             │
ST-NS-015A ──┘
```

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Split stories create integration complexity | Medium | Clear interface contracts between A/B components; integration tests required |
| Dependencies delay parallel work | Low | Phase-based execution allows sequential development within sprint |
| Acceptance criteria gaps in original stories | Medium | Inferred criteria based on FR references; validation with stakeholders needed |

---

## Validation Criteria

This sprint plan is valid when:
- [x] All sub-stories are ≤5 SP
- [x] Original story IDs are preserved with suffixes
- [x] Acceptance criteria are defined for each sub-story
- [x] Split rationale is documented
- [x] Dependencies are mapped
- [x] Execution order is defined

---

## Notes

1. **Original Story Preservation:** The original stories (ST-NS-012 through ST-NS-016) remain in `docs/bmm-workflow-status.yaml` as the canonical reference. This sprint plan provides the execution breakdown.

2. **FR Coverage:** Each sub-story maintains traceability to the original Functional Requirement (FR-012 through FR-016) as noted in the FR Coverage field.

3. **Future Status Updates:** When implementing, update the sub-story status in this document. The original story status in `docs/bmm-workflow-status.yaml` should reflect the aggregate status of its sub-stories.

4. **Story Point Totals:** The split maintains the original 35 SP total for EP-NS-003, ensuring no scope inflation or deflation.

---

*Document generated: 2026-02-10*  
*Plan version: 1.0*
