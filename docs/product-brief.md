---
title: "ChiseAI Product Brief"
status: canonical
updated: 2026-02-08
owner: Craig
project: ChiseAI
---

# ChiseAI Product Brief (Canonical)

## One-Line Summary
An autonomous crypto perps trading system that continuously learns and evolves to maximize net profit while minimizing drawdown, with strict risk invariants and robust observability.

## Goals (Priority Order)
1. **Net profit**
2. **Max drawdown**
3. **Sharpe/Sortino**
4. **Zero kill-switch events** (as a stability target; enforced via invariants and gating)

## Target Operating Model
- **Autonomous by default**: agents handle research, implementation, testing, CI, and deployment via PR auto-merge.
- **Human involvement**: only required for roadmap adjustments and for re-authorizing live trading after a live kill-switch event.

## Trading Scope
- **Instruments**: perps only (initially).
- **Styles (initial)**:
  - Trend-following grid strategies.
  - Direct perps trades (non-grid) when the system’s evidence supports it.
- **Orders**: market and limit.
- **Hedging**: hedged/market-neutral mode must be supported on paper and live venues.
- **Token universe (MVP)**: BTC, ETH, SOL, LINK, TAO, XRP, BNB, SUI, ONDO, KAS (assuming availability on Binance/Bybit/Bitget).

## Venues and Data Policy
- **Binance**: reference market-structure data (order books, liquidity, open interest) to infer broader levels and regimes.
- **Bybit**: demo account for paper execution; use Bybit execution-market data for SL/TP placement and realized fills.
- **Bitget**: live execution; use Bitget execution-market data for SL/TP placement and realized fills.

## Phased Execution Roadmap (All Stages Run In Parallel)
1. **Continuous backtesting** (always on; never halted).
2. **Bybit demo paper trading** (gated; auto-suspend on paper kill-switch, then self-eval and resume).
3. **Bitget live trading** (gated; disables on live kill-switch until human re-authorizes).

## Risk Invariants (Hard Constraints)
- **Per-trade risk**: max 1% of portfolio at stop-loss (portfolio size * 0.01), with small tolerance.
- **Leverage**: max 3x.
- **Live kill-switch**: drawdown >= 15% disables live until human re-authorizes.
- **Paper kill-switch**: drawdown >= 15% closes paper positions, suspends paper, performs self-eval/adjustments, then resumes with explanation.

## Observability and Debugging
- **Grafana-first**: primary operational UI for agents/humans.
- Required visibility:
  - Data ingestion health and freshness per venue and token.
  - Backtest KPIs (PnL/DD/Sharpe/Sortino) and regime splits.
  - Paper/live execution health (orders/fills/rejects/slippage/funding/fees).
  - Risk invariant breaches and kill-switch state transitions.

## Non-Goals (For Now)
- Regulatory/compliance automation (handled externally by operator).
- Spot trading (revisit after perps stability).

## Definition of “Working”
- Backtests are continuous and producing stable KPIs.
- Paper trading runs for 30 consecutive days without invariant breaches.
- Live trading stays gated, is observable, and can be disabled instantly on invariant breach; live kill-switch requires explicit human re-authorization.

## Canonical References
- PRD: `docs/prd.md`
- Work state: `docs/bmm-workflow-status.yaml`
- Validation registry: `docs/validation/validation-registry.yaml`

