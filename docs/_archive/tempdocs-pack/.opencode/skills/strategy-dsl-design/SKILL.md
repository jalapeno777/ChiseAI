---
name: strategy-dsl-design
description: Design and maintain a constrained Strategy DSL (schema) that supports safe parameter + structure evolution and auditability.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: dsl
---

## What I do
I guide the creation/maintenance of a Strategy DSL so the system can evolve strategies safely.

## DSL goals
- Constrain changes to approved modules
- Make diffs readable (config diffs, not arbitrary code)
- Make strategies reproducible and testable
- Support parameter mutations and structural mutations (toggle modules, swap exit logic, add filters)

## Recommended DSL sections
- metadata (name, version, tags)
- universe (symbols, sessions)
- signals (entry triggers)
- filters (regime, volatility, cooldown, news windows if used)
- exits (stop/take profit/trailing/time-based)
- sizing (risk-per-trade, vol targeting, DD-based scaling)
- execution_policy (order types, retries, min liquidity rules)
- risk_rules (caps and local limits)
- telemetry_tags (for audit logging)

## Mutation operators (approved “moves”)
- Parameter: thresholds, lookbacks, cooldowns, risk sizing
- Structural: add/remove a filter; swap entry family; swap exit family; add an ensemble wrapper

## Safety rules
- Changes must remain inside the schema constraints
- Risk caps are enforced outside the DSL by guardrails
- Any new module requires:
  - unit tests
  - backtest validation harness support
  - documentation entry
