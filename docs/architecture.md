---
# Architecture Overview - ChiseAI

**Status:** Placeholder (to be expanded)
**Related Documents:**
- PRD: docs/prd.md
- Workflow Status: docs/bmm-workflow-status.yaml
- Validation Registry: docs/validation/validation-registry.yaml

## High-Level Components

ChiseAI uses a microservices architecture with event-driven processing.

**Core Services:**
- Market Data Service (Binance API integration)
- Analysis Service (multi-timeframe technical indicators, Markov chains)
- Signal Service (confidence-based signal generation)
- Risk Management (position sizing, stop-loss, portfolio-level monitoring)
- Learning System (ML-LLM feedback, outcome analysis, calibration)

**Data Stores:**
- InfluxDB: Time-series market data
- PostgreSQL: Relational data (users, signals, outcomes)
- Redis: Cache and pub/sub

**Interfaces:**
- Streamlit Dashboard (user interface)
- Discord Bot (alerts and notifications)

## POC Mode Constraints

- **Recommendation Only:** No live trading execution
- **Live Validation Gate:** Sandbox → Paper Trading → Limited Live → Production
- **Risk Caps:** ≤2% worst-case per grid, ≤3x leverage
- **Rollback Triggers:** >10% drawdown, <55% win rate over 20 trades

## Live Validation Gate Phases

| Phase | Environment | Scope | Success Criteria |
|-------|-------------|-------|------------------|
| Phase 1 | Sandbox/Binance Testnet | Historical backtesting | Walk-forward validation |
| Phase 2 | Paper Trading | Live market data, no real funds | 60% win rate, 5% net gain (simulated) |
| Phase 3 | Limited Live | Real funds, capped position size | 60% win rate, 5% net gain with rollback triggers |
| Phase 4 | Production | Full deployment | All success criteria met |
