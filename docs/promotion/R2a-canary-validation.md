# R2a Canary Validation Report

**Canary**: R2A-20260412
**Decision**: NO-GO
**Date**: 2026-05-02
**Epic**: EP-LAUNCH-004

---

## Decision Summary

The R2a canary has been evaluated and the result is **NO-GO**.

---

## Reasons for NO-GO

1. **Signal generator crash-loop**: The signal generator is in a continuous restart loop (421+ restarts recorded, still incrementing). No new signals can be generated until this is resolved.

2. **Infrastructure collapse**: Grafana, InfluxDB, and Postgres are all in Exited state. All 5 EP-LAUNCH-004 criteria (win rate ≥60%, net return ≥5%, max drawdown ≤15%, Sharpe ratio ≥1.0, trade count ≥30) are unmeasurable.

3. **Unavailable metrics**: Win rate, net return, max drawdown, Sharpe ratio, and trade count cannot be determined from available evidence.

---

## Root Causes

- Signal generator restart loop (421+ restarts)
- Redis 16-day downtime (restored 2026-05-02)
- Container failures (Grafana, InfluxDB, Postgres all Exited)

---

## Supporting Evidence

Full evidence is documented in: `docs/promotion/checkpoints/day21-final.md`

---

## Recommendation

Investigate and fix signal generator restart loop before any further evaluation. Current evidence is insufficient to recommend promotion due to inability to measure trading performance metrics and >5-day signal gap.
