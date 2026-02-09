---
# ChiseAI Product Requirements Document - Canonical Entry Point

**Author:** Craig
**Date:** 2025-12-07
**Version:** 1.2.1
**Status:** Active
**Canonical PRD:** Yes
**Replaces:** docs/startingprd.md (legacy - superseded by canonical PRD)

---

classification:
  domain: fintech
  projectType: blockchain_web3
---

# ChiseAI - Crypto Grid Trend & Strategy System

**Project Name:** ChiseAI (GridAI - legacy codename)
**Technical Type:** blockchain_web3
**Domain:** fintech
**Complexity:** high

---

## Executive Summary

ChiseAI is a sophisticated crypto trading analysis system that transforms emotional, time-intensive trading into data-driven, profitable market insights. By leveraging advanced multi-timeframe analysis, Markov chain predictions, and intelligent trend detection, ChiseAI identifies high-probability trading opportunities while maintaining rigorous portfolio-level risk management. The system addresses the critical gap between basic trading bots and complex analysis needed for consistent profitability in volatile crypto markets, specifically designed for solo human operators with AI team support.

The MVP focuses on 10 specific tokens (BTC, ETH, SOL, LINK, TAO, XRP, BNB, SUI, ONDO, KAS) across three execution stages: continuous historical backtesting, Bybit demo paper trading, and Bitget live trading. Binance is used as a high-liquidity reference venue for broader market structure signals (e.g., order book / liquidity / open interest), while Bybit and Bitget market data are used for execution-specific sizing, stop-loss/TP placement, and realized fill analytics. Results are surfaced via Grafana (primary ops/debug UI) with Discord notifications for key events and signals.

### Autonomous Development System (Chise)

ChiseAI is built and maintained by an **autonomous development system** (internally referred to as **Chise**) that continuously plans, implements, tests, and deploys improvements with minimal human involvement.

- **Primary orchestration**: Aria is the primary orchestrator and delegates planning/execution to Jarvis and implementation agents per `.opencode/agent/*.md`.
- **Single source of truth**: The repo (PRD + `docs/bmm-workflow-status.yaml` + `docs/validation/validation-registry.yaml`) is canonical; Taiga is a synchronized monitoring surface with strict conflict rules.
- **Always via PR**: All changes land via PRs, pass Woodpecker CI, and are auto-merged to `main` when checks are green.
- **Traceability**: Every PR title must include a story ID (e.g. `ST-NS-001 ...`, `CH-OPS-001 ...`). CI enforces this.
- **Planning visibility**: Repo-canonical story metadata is synced to Taiga so humans can monitor progress without duplicative manual status updates.

### What Makes This Special

ChiseAI's unfair advantage lies in its sophisticated multi-layered analysis approach and accuracy-first philosophy. Unlike competitors' basic indicator-based systems, ChiseAI combines comprehensive market analysis with Markov chain trend detection, confidence scoring, and community-driven transparency through Discord integration. The system transforms volatility from a risk into a profit-generating asset through intelligent trend prediction, making sophisticated trading accessible while maintaining complexity needed for real market success. The accuracy-first approach prioritizes signal quality over quantity, minimizing false positives while accepting missed opportunities as acceptable trade-offs.

---

## 1. Success Criteria

| ID | Criterion | Measurement | Target |
|----|-----------|-------------|--------|
| SC-001 | Win Rate | Percentage of profitable trades | ≥60% MVP, ≥80% target |
| SC-002 | Backtest/Paper-Trading Net Return | Simulated portfolio return in backtests/paper trading | ≥5% MVP simulation, ≥10-15% target simulation |
| | | | **Note:** Real-money performance to be validated through Phase 2-4 live validation gate |
| SC-003 | Maximum Drawdown | Peak-to-trough decline | ≤15% catastrophic threshold |
| SC-004 | Confidence Threshold | Minimum confidence for signals | ≥75% for execution |
| SC-005 | Prediction Accuracy | Correct trend predictions | ≥60% MVP, improving to 80% |
| SC-006 | User Retention | 6-month retention rate | ≥80% |
| SC-007 | System Uptime | Availability of critical functions | ≥99.9% |
| SC-008 | Response Time | Dashboard load time | <3 seconds |
| SC-009 | Signal Delivery Latency | Time from signal to notification | <1 second |
| SC-010 | Test Coverage | Automated test coverage | ≥80% |
| SC-011 | Sharpe Ratio | Risk-adjusted return per unit of risk | ≥1.5 target |
| SC-012 | Sortino Ratio | Downside-adjusted return measure | ≥2.0 target |

---

## 2. Scope

### 2.1 In Scope

| Category | Items |
|----------|-------|
| **Tokens (MVP)** | BTC, ETH, SOL, LINK, TAO, XRP, BNB, SUI, ONDO, KAS (10 tokens) |
| **Data Sources** | Binance (reference market structure: OI/order books/liquidity); Bybit (paper execution + execution-market data); Bitget (live execution + execution-market data) |
| **Analysis Methods** | Multi-timeframe technical indicators, Markov chain trend detection, ML confidence scoring, Hedging strategies and market-neutral positions |
| **Execution Modes** | Backtest (continuous), Paper (Bybit demo), Live (Bitget), with hedging/market-neutral options when evidence supports it; shadow-modes kept running in parallel |
| **Output Channels** | Grafana dashboards (primary), Discord bot (alerts/notifications). Optional: Streamlit for research/explainability UI (non-blocking) |
| **Risk Management** | Position sizing, stop-loss, portfolio-level risk, max 1% per trade risk, ≤2% per-grid worst-case, 3x leverage cap |
| **Learning System** | Closed-loop ML feedback, prediction outcome tracking, confidence calibration |
| **Autonomous Engineering (Chise)** | Agent-driven planning/implementation/testing; PR-only changes; CI-gated auto-merge; story-id traceability; repo->Taiga sync for monitoring |

### 2.2 Out of Scope

| Category | Items |
|----------|-------|
| **Custody** | Non-custodial architecture (users maintain fund control) |
| **Tokens (Phase 2)** | Expansion beyond 10 tokens (after $1,000/month profit threshold) |
| **Leverage** | Max 3x (no higher leverage options) |
| **Spot Execution** | Spot execution is out-of-scope initially (perps-first); revisit after paper/live perps stability gate |
| **Regulatory/Compliance** | Out of scope for this project; operator handles exchange/jurisdiction requirements externally |

---

## User Journeys

### Journey 1: Daily Trading Routine

| Aspect | Description |
|--------|-------------|
| **Description** | User starts day with automated morning briefing, receives real-time signals during trading hours, and reviews performance in evening |
| **User Goal** | Receive high-confidence setups (75%+) with clear risk parameters to make informed trading decisions efficiently |
| **Key Touchpoints** | Dashboard morning briefing (<3s load), Discord real-time alerts, risk assessment display, evening performance report |
| **Success Metrics** | Daily active engagement, signal action rate >60%, win rate tracking, time saved vs manual analysis |

### Journey 2: New Opportunity Discovery

| Aspect | Description |
|--------|-------------|
| **Description** | User explores new trading opportunities through system-detected signals with detailed analysis and historical context |
| **User Goal** | Evaluate opportunities with comprehensive data: confidence scores, risk parameters, similar situation outcomes |
| **Key Touchpoints** | Signal detail dashboard, historical context panel, risk/reward visualization, decision support explanation |
| **Success Metrics** | Signal exploration rate, confidence threshold alignment, user decision turnaround time |

### Journey 3: Portfolio Risk Management

| Aspect | Description |
|--------|-------------|
| **Description** | User monitors portfolio-level risk exposure, receives automated alerts for threshold breaches, and reviews learning outcomes |
| **User Goal** | Maintain capital preservation through continuous risk monitoring, correlation analysis, and systematic risk responses |
| **Key Touchpoints** | Real-time exposure dashboard, correlation matrix, automated Discord alerts, post-event analysis reports |
| **Success Metrics** | Drawdown prevention rate, risk alert response time, portfolio correlation optimization, prediction accuracy improvement |

### Journey 4: Community & Transparency

| Aspect | Description |
|--------|-------------|
| **Description** | User engages with community through Discord, shares experiences, and benefits from transparent performance tracking |
| **User Goal** | Build trust through transparent signal sharing, community discussion, and collective learning from system performance |
| **Key Touchpoints** | Discord signal feed, community discussion threads, performance attribution reports, feedback channels |
| **Success Metrics** | Community engagement rate, user retention correlation with community access, feedback incorporation rate |

---

## 3. Functional Requirements

### 3.1 Market Analysis Engine

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-001 | Multi-timeframe analysis (1m, 5m, 15m, 1h, 4h, 1d) | P0-CRITICAL | Journey 1 |
| FR-002 | Technical indicator calculation (RSI, MACD, Bollinger Bands) | P0-CRITICAL | Journey 1 |
| FR-003 | Markov chain trend detection and state inference | P0-CRITICAL | Journey 1 |
| FR-004 | Confluence-based signal scoring combining multiple indicators | P0-CRITICAL | Journey 1 |
| FR-004a | Order type execution support (market and limit orders) | P0-CRITICAL | Journey 1 |
| FR-005 | Confidence multiplier updates based on signal agreement | P1-HIGH | Journey 1 |
| FR-006 | Signal history tracking with outcome correlation | P1-HIGH | Journey 3 |

### 3.2 Signal Generation & Delivery

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-007 | Real-time signal generation meeting 75%+ confidence threshold | P0-CRITICAL | Journey 1, 2 |
| FR-008 | Dashboard display with pre-market briefing | P0-CRITICAL | Journey 1 |
| FR-009 | Discord alerts for high-confidence opportunities | P0-CRITICAL | Journey 1, 2 |
| FR-010 | Detailed signal breakdown with risk parameters | P1-HIGH | Journey 2 |
| FR-011 | Historical context for similar situations | P1-HIGH | Journey 2 |

### 3.3 Risk Management

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-012 | Position sizing recommendations based on portfolio | P0-CRITICAL | Journey 1, 2, 3 |
| FR-013 | Stop-loss recommendations with each signal | P0-CRITICAL | Journey 1, 2 |
| FR-014 | Portfolio-level risk exposure monitoring | P0-CRITICAL | Journey 3 |
| FR-015 | Correlation analysis across positions | P1-HIGH | Journey 3 |
| FR-016 | Automated alerts for risk threshold breaches | P1-HIGH | Journey 3 |

### 3.4 Learning & Improvement

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-017 | Prediction accuracy tracking over time | P0-CRITICAL | Journey 3 |
| FR-018 | ML feedback loop analyzing predictions vs outcomes | P0-CRITICAL | Journey 3 |
| FR-019 | Confidence threshold calibration | P1-HIGH | Journey 3 |
| FR-020 | Training data generation for model improvement | P1-HIGH | Journey 3 |

### 3.5 User Experience

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-021 | Mobile-responsive dashboard design | P1-HIGH | Journey 1, 2, 3 |
| FR-022 | User-configurable alert thresholds | P1-HIGH | Journey 1, 2 |
| FR-023 | Performance reporting (daily/weekly/monthly) | P1-HIGH | Journey 3 |
| FR-024 | Community discussion via Discord integration | P2-MEDIUM | Journey 4 |

### 3.6 Execution & Validation

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-025 | Continuous backtesting runner (walk-forward capable) | P0-CRITICAL | Journey 3 |
| FR-026 | Exchange adapter interface + connectors: Binance (reference), Bybit (paper), Bitget (live) | P0-CRITICAL | Journey 1, 3 |
| FR-027 | Paper trading orchestration (Bybit demo) with shadow backtests continuing | P0-CRITICAL | Journey 1, 3 |
| FR-028 | Live trading orchestration (Bitget) with explicit enable/disable gating | P0-CRITICAL | Journey 3 |
| FR-029 | Mode-specific kill-switch enforcement (paper self-eval/resume; live human re-auth) | P0-CRITICAL | Journey 3 |
| FR-030 | Direct perps execution for high-confidence setups when evidence supports non-grid strategies | P0-CRITICAL | Journey 3 |
| FR-030a | Hedging and market-neutral position support for risk management | P0-CRITICAL | Journey 3 |
| FR-031 | Grafana-first observability (KPIs, health, alerts) | P0-CRITICAL | Journey 3 |

### 3.7 Autonomous Engineering System (Chise)

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-DEV-001 | Standard PR workflow: all changes land via PRs and merge to `main` only after Woodpecker CI is green | P0-CRITICAL | Journey 3 |
| FR-DEV-002 | PR traceability: PR titles must include story IDs; CI blocks PRs missing a title or story ID | P0-CRITICAL | Journey 3 |
| FR-DEV-003 | Status discipline: repo state in `docs/bmm-workflow-status.yaml` and `docs/validation/validation-registry.yaml` must stay in sync; CI validates this | P0-CRITICAL | Journey 3 |
| FR-DEV-004 | Taiga monitoring view: repo-canonical story metadata (id/title/status/AC) is synced to Taiga; conflicts follow strict policy (repo is canonical) | P1-HIGH | Journey 3 |
| FR-DEV-005 | Iteration loop compliance: work is tracked via iterlogs (Redis/Qdrant when available; `docs/tempmemories/` fallback) and validated in CI | P1-HIGH | Journey 3 |

### 3.8 Strategy Evolution & Promotion (Neuro-Symbolic R&D)

| ID | Requirement | Priority | User Journey |
|----|-------------|----------|--------------|
| FR-EVO-001 | Constrained action space for evolution: strategies are mutated only via approved config/DSL interfaces (no arbitrary live code edits) | P0-CRITICAL | Journey 3 |
| FR-EVO-002 | Strategy DSL schema supports parameter and structural mutations, while remaining diffable and reproducible | P0-CRITICAL | Journey 3 |
| FR-EVO-003 | Strategy registry supports champion/challenger tracking and stores artifacts (config, diffs, backtest results, paper results) | P0-CRITICAL | Journey 3 |
| FR-EVO-004 | Strategy CI/CD promotion pipeline: candidate -> backtest gate -> paper canary -> paper full -> promotion packet -> human-approved live | P0-CRITICAL | Journey 3 |
| FR-EVO-005 | Promotion packets are generated for human approvals (paper->live; and optional brain upgrades), including evidence, risk invariants, and rollback steps | P1-HIGH | Journey 3 |
| FR-EVO-006 | Optional policy knobs: trade-frequency budgeting and turnover reporting (trades/day) can be enabled as a secondary control when it improves cost and stability | P2-MEDIUM | Journey 3 |

**Canonical V1 design reference:** `docs/planning/neuro-symbolic-ai-evolution/agentic_neurosymbolic_trading_rd_v1_spec.md` and `docs/planning/neuro-symbolic-ai-evolution/architecture_diagram_outline.md`.

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement | Measurement | Target | Measurement Method | Context |
|----|-------------|-------------|--------|-------------------|---------|
| NFR-001 | Dashboard load time | 95th percentile | <3 seconds | APM monitoring (95th percentile) | Enables timely trading decisions during volatile markets |
| NFR-002 | Signal delivery latency | End-to-end | <1 second | Load testing with synthetic transactions | Critical for real-time signal delivery to Discord and dashboard |
| NFR-003 | API response time | 95th percentile | <1 second | APM monitoring (95th percentile) | Ensures responsive user experience during active trading |
| NFR-004 | Query performance (outcome analysis) | Endpoints | <25ms | Performance benchmarking suite | Supports real-time ML outcome analysis queries |
| NFR-005 | Cache performance | Latency | <200ms | Redis benchmark tool | Reduces database load and improves response times |

### 4.2 Reliability & Availability

| ID | Requirement | Measurement | Target | Measurement Method | Context |
|----|-------------|-------------|--------|-------------------|---------|
| NFR-006 | System uptime | Critical functions | ≥99.9% | Cloud provider APM + SLA monitoring | Critical functions must remain available for signal delivery |
| NFR-007 | Maximum downtime per year | Hours | ≤8.76 hours | SLA tracking dashboard | Calculated from 99.9% uptime target |
| NFR-008 | Failover recovery time | Service disruption | <4 hours | Disaster recovery testing | Ensures rapid recovery from infrastructure failures |
| NFR-009 | Data backup frequency | Automated daily | 100% coverage | Backup verification scripts | Guarantees data durability and recovery capability |
| NFR-010 | Audit trail gaps | Maximum gap | <1 minute | Audit log monitoring | Maintains complete compliance and forensic capability |

### 4.3 Security & Compliance

| ID | Requirement | Measurement | Target | Measurement Method | Context |
|----|-------------|-------------|--------|-------------------|---------|
| NFR-011 | Security breaches | Count | Zero | Security incident tracking + audit logs | Protects secrets, portfolio state, and system integrity |
| NFR-012 | Critical vulnerabilities | Count | Zero | Vulnerability scanning (weekly automated, monthly third-party) | Prevents exploitation of system weaknesses |
| NFR-013 | Regulatory/compliance automation | Coverage | N/A | N/A | Out of scope for this project; operator handles exchange/jurisdiction requirements externally |
| NFR-014 | Data encryption (at rest) | Standard | AES-256 | Security audit verification | Protects sensitive user and market data |
| NFR-015 | Data encryption (in transit) | Standard | TLS 1.3 | Security scan verification | Secures all network communications |
| NFR-016 | Penetration testing | Frequency | Quarterly | Third-party security audit | Validates security posture against real-world attacks |

### 4.4 Maintainability & Quality

| ID | Requirement | Measurement | Target | Measurement Method | Context |
|----|-------------|-------------|--------|-------------------|---------|
| NFR-017 | Test coverage | Automated tests | ≥80% | Coverage reporting (pytest-cov) | Ensures code quality and prevents regressions |
| NFR-018 | Lint errors | Count | Zero | CI/CD lint checks (ruff/flake8) | Maintains consistent code style and catches issues early |
| NFR-019 | Code documentation | Coverage | All public APIs | Documentation generation (Sphinx) | Enables developer onboarding and API consumption |
| NFR-020 | CI/CD pipeline status | Green builds | 100% | Pipeline automation status | Ensures reliable and consistent deployments |

---

## 5. Safety Constraints

### 5.1 Risk Caps

| Constraint | Value | Enforcement | Related FRs |
|------------|-------|-------------|-------------|
| Maximum per-trade risk | ≤1% of portfolio (at stop-loss) | Hard limit in sizing/execution | FR-012, FR-013 |
| Maximum per-grid risk | ≤2% worst-case | Hard limit in signal generation | FR-004, FR-014 |
| Portfolio drawdown | ≤15% catastrophic threshold | Kill-switch trigger | FR-016, FR-029 |
| Confidence threshold | ≥75% minimum | Signal filtering | FR-004, FR-007 |

### 5.2 Leverage Constraints

| Constraint | Value | Enforcement | Related FRs |
|------------|-------|-------------|-------------|
| Maximum leverage | 3x | Hard limit | FR-012, FR-014 |
| Higher leverage options | Not available | Design constraint | Scope (Section 2.2) |
| Margin requirements | Tiered by volatility | Dynamic adjustment | FR-014 |

### 5.3 Safety Systems

| System | Trigger | Action | Related FRs |
|--------|---------|--------|-------------|
| **Kill-Switch (Live)** | ≥15% drawdown | Disable live trading until human re-authorizes reactivation | FR-029 |
| **Kill-Switch (Paper)** | ≥15% drawdown | Close paper positions; suspend paper; run self-eval and resume with adjusted parameters + notify human | FR-029 |
| **Circuit Breaker** | API failure rate >10% | Fallback to cached data | NFR-008 |
| **Panic Shutdown** | Manual trigger | All positions close, alerts disabled | FR-029 |
| **Safety Monitoring** | Continuous | Automated safety test suite required (scope grows with system) | NFR-011, NFR-012 |
| **Position Limits** | Per-token max | 10% of portfolio per token | FR-012, FR-014 |
| **Correlation Limits** | Cross-position | Max 40% correlated exposure | FR-014, FR-015 |

---

## 6. Live Validation Gate

### 6.1 Validation Phases

| Phase | Environment | Scope | Success Criteria |
|-------|-------------|-------|-------------------|
| **Phase 1** | Backtesting (historical) | Continuous backtesting + walk-forward validation built from exchange APIs | Backtest KPIs stable; invariants enforced; data pipelines healthy |
| **Phase 2** | Paper Trading (Bybit demo) | Live market data; paper execution; shadow backtests continue | 30 days continuous success; no invariant breaches; acceptable drawdown |
| **Phase 3** | Live Trading (Bitget) | Real execution with strict caps; paper + backtest continue | Live profitability improves vs baseline; invariant breaches handled as designed |
| **Phase 4** | Scaling | Token/strategy expansion | Sustained profitability with minimal drawdown; ops stability and observability proven |

### 6.2 Rollback Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| Drawdown | Approaching kill-switch thresholds | Reduce risk (sizing/leverage) and/or suspend affected mode |
| Win Rate | <55% over 20 trades | Pause signal generation |
| Confidence Drift | ECE >0.10 | Recalibrate thresholds |
| Safety Test Failure | Any test fail | Rollback to previous version |

---

## 7. Traceability Matrix

### 7.1 Success Criteria → User Journeys → FR/NFR

| Success Criteria | User Journey(s) | Functional Requirements | Non-Functional Requirements |
|------------------|-----------------|-------------------------|----------------------------|
| SC-001 (Win Rate) | Journey 1, 2 | FR-001, FR-004, FR-007 | NFR-003, NFR-017 |
| SC-002 (Backtest/Paper-Trading Net Return) | Journey 1, 2, 3 | FR-012, FR-013, FR-014 | NFR-002, NFR-004 |
| SC-003 (Drawdown) | Journey 3 | FR-014, FR-016 | NFR-006, NFR-007 |
| SC-004 (Confidence) | Journey 1, 2 | FR-005, FR-007 | NFR-003, NFR-004 |
| SC-005 (Prediction Accuracy) | Journey 3 | FR-017, FR-018, FR-019 | NFR-017 |
| SC-006 (User Retention) | Journey 1, 2, 3, 4 | FR-021, FR-022, FR-023, FR-024 | NFR-001, NFR-002 |
| SC-007 (Uptime) | All | All | NFR-006, NFR-008 |
| SC-008 (Response Time) | Journey 1, 2 | FR-008, FR-021 | NFR-001 |
| SC-009 (Latency) | Journey 1, 2 | FR-009 | NFR-002 |
| SC-010 (Test Coverage) | All | All | NFR-017, NFR-018 |
| SC-011 (Sharpe Ratio) | Journey 3 | FR-012, FR-014, FR-015, FR-030a | NFR-003 |
| SC-012 (Sortino Ratio) | Journey 3 | FR-012, FR-014, FR-015, FR-030a | NFR-003 |

### 7.2 User Journey → Functional Requirements

| User Journey | Epic | Functional Requirements |
|--------------|------|------------------------|
| Journey 1: Daily Trading Routine | EP-NS-001: Market Analysis Engine Foundation, EP-NS-002: Signal Generation & Delivery | FR-001, FR-002, FR-008, FR-009, FR-013, FR-021 |
| Journey 2: New Opportunity Discovery | EP-NS-001: Market Analysis Engine Foundation, EP-NS-002: Signal Generation & Delivery | FR-003, FR-004, FR-007, FR-010, FR-011, FR-012 |
| Journey 3: Portfolio Risk Management | EP-NS-003: Portfolio Risk Management | FR-012, FR-014, FR-015, FR-016, FR-017, FR-019, FR-030, FR-030a |
| Journey 4: Community & Transparency | EP-NS-005: User Experience & Interface | FR-009, FR-024 |

---

## 8. Implementation Status

ChiseAI is currently in **planning/foundation** for this repository. The authoritative work-state (epics/stories/status) lives in `docs/bmm-workflow-status.yaml`, paired with validation plans in `docs/validation/validation-registry.yaml`.

---

## 9. User Personas

### 9.1 Primary Persona: "Strategic Solo Trader" (Alex)

- **Demographics:** 28-45 years old, technically sophisticated, 2-5 years crypto experience
- **Portfolio:** $25,000 - $250,000
- **Pain Points:** Analysis paralysis, emotional decisions, missed opportunities
- **Goals:** Consistent 5-15% monthly returns, capital preservation

### 9.2 Secondary Persona: "AI-Enhanced Portfolio Manager" (Jordan)

- **Demographics:** 32-50 years old, manages $100K - $1M+
- **Style:** Systematic, risk-managed, portfolio-level thinking
- **Goals:** Scalable systematic trading, risk-adjusted returns

---

## 10. Architecture Overview

### 10.1 Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway & Load Balancer                   │
├─────────────────────────────────────────────────────────────────┤
│            Authentication & Authorization Service                │
├─────────────────────────────────────────────────────────────────┤
│  Market Data │ Analysis Service │ Signal Service │ User Service │
├─────────────────────────────────────────────────────────────────┤
│              Message Queue (Redis Streams / RabbitMQ)            │
├─────────────────────────────────────────────────────────────────┤
│  Time Series DB  │  Relational DB  │  Cache Layer  │  Audit    │
│  (InfluxDB)       │  (PostgreSQL)   │  (Redis)      │  Store    │
├─────────────────────────────────────────────────────────────────┤
│ External Integrations: Binance (ref data), Bybit (paper), Bitget (live), Discord │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Technical Stack

- **Observability/UI:** Grafana (primary), Discord bot (alerts). Optional: Streamlit (research/explainability UI)
- **Backend:** Python, microservices architecture
- **Data:** InfluxDB (time-series), PostgreSQL (relational), Redis (cache)
- **ML/AI:** Multi-LLM orchestration (GLM-4.7, Kimi 2.5, MiniMax 2.1; configurable fallbacks)
- **Infrastructure:** Docker, Kubernetes-ready, Terraform IaC

---

## 11. Reference Documents

| Document | Location |
|----------|----------|
| Product Brief (canonical) | docs/product-brief.md |
| Architecture | docs/architecture.md |
| Workflow Status | docs/bmm-workflow-status.yaml |
| Validation Registry | docs/validation/validation-registry.yaml |
| User Journeys | docs/startingprd.md (Step 4) |
| Technical Specifications | docs/startingprd.md (Step 6) |

---

## 12. Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.2.1 | 2026-02-09 | CH-PRD-VALIDATION-001 | Added explicit FR references in Safety Constraints section (Section 5) for improved traceability. Split FR-004 into FR-004 (confluence scoring) and FR-004a (order type support). Added FR-030a for hedging/market-neutral support. Updated traceability matrix to include SC-011 (Sharpe) and SC-012 (Sortino) mappings. Verified obsolete reference removal. |
| 1.2.0 | 2026-02-08 | CH-PRD-PHASE1-ALIGN-001 | Added Phase 1 scope edits: hedging/market-neutral support, order types (market+limit), Sharpe/Sortino success criteria, direct perps execution allowance. Fixed epic naming in traceability matrix (Section 7.2) to match canonical epic IDs from docs/bmm-workflow-status.yaml. Removed ml-outcome-analysis-system-design.md reference. |
| 1.1.0 | 2026-02-08 | CH-PRD-CI-ALIGN-001 | Updated scope to phased execution (backtest→Bybit paper→Bitget live), Binance ref market-data role, Grafana-first ops UI, updated risk invariants and kill-switch rules. |
| 1.0.0 | 2025-12-07 | Craig | Initial canonical PRD |
| 1.0.1 | 2026-02-08 | CH-PRD-RESTRUCT-001 | Added FR/NFR/SC, Safety Constraints, Traceability Matrix |
| 1.0.2 | 2026-02-08 | CH-PRD-POLISH-001 | Fixed naming consistency, resolved scope contradiction, reframed success criteria for POC mode |
| 1.1.0 | 2026-02-08 | CH-PRD-CI-ALIGN-001 | Updated scope to phased execution (backtest→Bybit paper→Bitget live), Binance ref market-data role, Grafana-first ops UI, updated risk invariants and kill-switch rules |
