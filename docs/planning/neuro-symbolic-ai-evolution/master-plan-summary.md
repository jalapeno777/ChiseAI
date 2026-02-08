# Neuro-Symbolic AI Evolution Master Plan Summary

## Goal
Build a constrained, auditable, self-improving trading R&D system that can autonomously propose, evaluate, and promote strategy changes through:
1. Continuous backtesting (always on)
2. Paper trading (canary -> full)
3. Live trading (human-approved enable/re-enable gates)

## Canonical V1 Spec
See `agentic_neurosymbolic_trading_rd_v1_spec.md` for the detailed V1 design (strategy DSL, registries, promotion packets, champion/challenger, and brain CI/CD concepts).

## Roadmap Principles
- Constrained action space: strategy evolution occurs via DSL/config interfaces; no "free-editing" live behavior.
- Strong auditability: every candidate is versioned, diffable, and tied to evidence (backtest + paper).
- Root of trust: risk invariants + promotion gates are not self-modifiable.

