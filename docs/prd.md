---
# ChiseAI Product Requirements Document - Canonical Entry Point

**Author:** Craig
**Date:** 2025-12-07
**Version:** 1.0.2
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

The MVP focuses on 10 specific tokens (BTC, ETH, SOL, LINK, TAO, XRP, BNB, SUI, ONDO, KAS) using Binance API for uncapped real-time data. The system analyzes tokens across multiple timeframes using a blend of technical indicators, Markov chain trend detection, and confidence scoring to generate high-probability trading insights. Results are delivered through both a Streamlit dashboard and Discord bot integration for community transparency and engagement.

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

---

## 2. Scope

### 2.1 In Scope

| Category | Items |
|----------|-------|
| **Tokens (MVP)** | BTC, ETH, SOL, LINK, TAO, XRP, BNB, SUI, ONDO, KAS (10 tokens) |
| **Data Source** | Binance API for real-time data |
| **Analysis Methods** | Multi-timeframe technical indicators, Markov chain trend detection, ML confidence scoring |
| **Output Channels** | Streamlit dashboard, Discord bot |
| **Risk Management** | Position sizing, stop-loss, portfolio-level risk, max 2% per grid, 3x leverage cap |
| **Learning System** | Closed-loop ML feedback, prediction outcome tracking, confidence calibration |

### 2.2 Out of Scope

| Category | Items |
|----------|-------|
| **Trading Execution** | No live trading (POC mode only - recommendations only) |
| **Custody** | Non-custodial architecture (users maintain fund control) |
| **Tokens (Phase 2)** | Expansion beyond 10 tokens (after $1,000/month profit threshold) |
| **Leverage** | Max 3x (no higher leverage options) |
| **Jurisdictions** | US-only at launch (EU/APAC in future phases) |
| **Regulated Products** | No live trading execution (POC mode - recommendations only) |
| | **Note:** Perpetual futures and spot strategy recommendations ARE in-scope (phased approach) |

---

## 2. User Journeys

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
| NFR-011 | Security breaches | Count | Zero | Security incident tracking + audit logs | Protects user data and maintains regulatory compliance |
| NFR-012 | Critical vulnerabilities | Count | Zero | Vulnerability scanning (weekly automated, monthly third-party) | Prevents exploitation of system weaknesses |
| NFR-013 | Regulatory compliance | Jurisdiction coverage | 100% | Compliance audit tracking | Ensures legal operation across supported jurisdictions |
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

| Constraint | Value | Enforcement |
|------------|-------|-------------|
| Maximum per-grid risk | ≤2% worst-case | Hard limit in signal generation |
| Portfolio drawdown | ≤15% catastrophic threshold | Kill-switch trigger |
| Confidence threshold | ≥75% minimum | Signal filtering |

### 5.2 Leverage Constraints

| Constraint | Value | Enforcement |
|------------|-------|-------------|
| Maximum leverage | 3x | Hard limit |
| Higher leverage options | Not available | Design constraint |
| Margin requirements | Tiered by volatility | Dynamic adjustment |

### 5.3 Safety Systems

| System | Trigger | Action |
|--------|---------|--------|
| **Kill-Switch** | 15% drawdown OR 3 consecutive losses | Immediate position closure |
| **Circuit Breaker** | API failure rate >10% | Fallback to cached data |
| **Panic Shutdown** | Manual trigger | All positions close, alerts disabled |
| **Safety Monitoring** | Continuous | 61/61 safety tests required |
| **Position Limits** | Per-token max | 10% of portfolio per token |
| **Correlation Limits** | Cross-position | Max 40% correlated exposure |

---

## 6. Live Validation Gate

### 6.1 Validation Phases

| Phase | Environment | Scope | Success Criteria |
|-------|-------------|-------|-------------------|
| **Phase 1** | Sandbox/Binance Testnet | Historical backtesting | Walk-forward validation through Jan 31, 2025 |
| **Phase 2** | Paper Trading | Live market data, no real funds | 60% win rate, 5% net gain in simulated environment |
| **Phase 3** | Limited Live | Real funds, capped position size | 60% win rate, 5% net gain with rollback triggers |
| **Phase 4** | Production | Full deployment | SC-001 through SC-010 met |

### 6.2 Rollback Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| Drawdown | >10% from entry | Reduce position size by 50% |
| Win Rate | <55% over 20 trades | Pause signal generation |
| Confidence Drift | ECE >0.10 | Recalibrate thresholds |
| Safety Test Failure | Any test fail | Rollback to previous version |

---

## 7. Traceability Matrix

### 7.1 Success Criteria → User Journeys → FR/NFR

| Success Criteria | User Journey(s) | Functional Requirements | Non-Functional Requirements |
|------------------|-----------------|-------------------------|----------------------------|
| SC-001 (Win Rate) | Journey 1, 2 | FR-001, FR-004, FR-007 | NFR-003, NFR-017 |
| SC-002 (Monthly Gains) | Journey 1, 2, 3 | FR-012, FR-013, FR-014 | NFR-002, NFR-004 |
| SC-003 (Drawdown) | Journey 3 | FR-014, FR-016 | NFR-006, NFR-007 |
| SC-004 (Confidence) | Journey 1, 2 | FR-005, FR-007 | NFR-003, NFR-004 |
| SC-005 (Prediction Accuracy) | Journey 3 | FR-017, FR-018, FR-019 | NFR-017 |
| SC-006 (User Retention) | Journey 1, 2, 3, 4 | FR-021, FR-022, FR-023, FR-024 | NFR-001, NFR-002 |
| SC-007 (Uptime) | All | All | NFR-006, NFR-008 |
| SC-008 (Response Time) | Journey 1, 2 | FR-008, FR-021 | NFR-001 |
| SC-009 (Latency) | Journey 1, 2 | FR-009 | NFR-002 |
| SC-010 (Test Coverage) | All | All | NFR-017, NFR-018 |

### 7.2 User Journey → Functional Requirements

| User Journey | Epic | Functional Requirements |
|--------------|------|------------------------|
| Journey 1: Daily Trading Routine | Epic 1: Daily Trading Workflow | FR-001, FR-002, FR-008, FR-009, FR-013, FR-021 |
| Journey 2: New Opportunity Discovery | Epic 1: Daily Trading Workflow | FR-003, FR-004, FR-007, FR-010, FR-011, FR-012 |
| Journey 3: Portfolio Risk Management | Epic 2: Portfolio Risk Management | FR-012, FR-014, FR-015, FR-016, FR-017, FR-019 |
| Journey 4: Community & Transparency | Epic 4: Community | FR-009, FR-024 |

---

## 8. Implementation Status

### 8.1 Completed Sprints (Q1 2025)

| Sprint | Name | Stories | Story Points | Status |
|--------|------|---------|--------------|--------|
| q1-1 | LLM Foundation - Core Interfaces | 11 | 66 | ✅ COMPLETED |
| q1-2 | ML-LLM Integration | 6 | 40 | ✅ COMPLETED |
| q1-3 | Confidence Calibration Foundation | 6 | 42 | ✅ COMPLETED |
| q1-4 | Multi-LLM Orchestration | 5 | 35 | ✅ COMPLETED |
| q1-5 | Dashboard Integration Phase 1 | 7 | 37 | ✅ COMPLETED |
| q1-6 | Data Layer Foundation | 2 | 12 | ✅ COMPLETED |
| q1-7 | Feature Store Foundation | 2 | 10 | ✅ COMPLETED |
| q1-8 | Error Handling Foundation | 2 | 9 | ✅ COMPLETED |
| **Q1 Total** | **8 Sprints** | **41** | **251** | **✅ COMPLETED** |

### 8.2 ML Outcome Analysis System (Q1 2026)

| Phase | Name | Stories | Story Points | Status |
|-------|------|---------|--------------|--------|
| phase-1 | Core Infrastructure | 3 | 18 | ✅ COMPLETE |
| phase-2 | Calibration Engines | 4 | 24 | ✅ COMPLETE |
| phase-3 | Training Data | 3 | 20 | ✅ COMPLETE |
| phase-4 | Model Integration | 5 | 24 | ✅ COMPLETE |
| **Total** | **ML Outcome Analysis** | **15** | **86** | **✅ COMPLETE** |

### 8.3 Planned Sprints (Q2 2025)

| Sprint | Name | Stories | Story Points | Status |
|--------|------|---------|--------------|--------|
| q2-1 | Markov Chain & Decision Engine | 10 | 67 | 🔵 READY |
| q2-2 | Paper Trading & Grading | 20 | 114 | 📋 PLANNED |

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
│         External Integrations: Binance API, Discord Bot         │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Technical Stack

- **Frontend:** Streamlit (dashboard), Discord bot
- **Backend:** Python, microservices architecture
- **Data:** InfluxDB (time-series), PostgreSQL (relational), Redis (cache)
- **ML/AI:** Multi-LLM orchestration (GLM-4.7, MiniMax, OpenAI, Anthropic)
- **Infrastructure:** Docker, Kubernetes-ready, Terraform IaC

---

## 11. Reference Documents

| Document | Location |
|----------|----------|
| Architecture | docs/architecture.md |
| Workflow Status | docs/bmm-workflow-status.yaml |
| Validation Registry | docs/validation/validation-registry.yaml |
| ML Outcome Analysis Design | docs/architecture/ml-outcome-analysis-system-design.md |
| User Journeys | docs/startingprd.md (Step 4) |
| Technical Specifications | docs/startingprd.md (Step 6) |

---

## 12. Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-07 | Craig | Initial canonical PRD |
| 1.0.1 | 2026-02-08 | CH-PRD-RESTRUCT-001 | Added FR/NFR/SC, Safety Constraints, Traceability Matrix |
| 1.0.2 | 2026-02-08 | CH-PRD-POLISH-001 | Fixed naming consistency, resolved scope contradiction, reframed success criteria for POC mode |
