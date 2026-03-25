# TASK-10: Telemetry, Evals, Decision Scorecards

## Summary

Create the measurement layer for AI reasoning quality, evolution quality, memory quality, and autonomy safety.

## Why This Is Necessary

Without scorecards, the swarm will optimize for visible activity instead of actual cognition improvement.

## Scope

- metrics definitions
- Grafana dashboards
- daily/weekly reports
- scorecard artifacts in repo outputs

## Deliverables

1. cognition KPI registry,
2. dashboard panels for runtime, memory, beliefs, verifiers, experiments,
3. daily and weekly scorecard artifacts,
4. go/no-go thresholds for autonomy level changes.

## Best Practices

- separate leading indicators from lagging indicators,
- track quality by slice: token, regime, strategy type, model version,
- include "bad direction" signals, not only success metrics.

## Hardening Requirements

- every high-impact AI subsystem must emit health plus quality metrics,
- dashboards must show stale-data state,
- reports must capture both wins and regressions.

## Telemetry

- shadow divergence
- verifier fail rate
- retrieval hit rates
- belief conflict rates
- calibration error
- carryover and false positive deltas
- autonomy level changes

## Quantified Success

- scorecards generated on schedule with `>99%` cadence compliance,
- dashboard freshness `<5m`,
- every autonomy raise backed by visible positive trend on scorecards.

## Testing

- metric emission tests
- dashboard query tests
- report generation tests
- stale data and missing metric simulations

## Research Links

- Agent-as-a-judge style evals are relevant but should be secondary to objective evals.
- DeepMind eval-centric optimization patterns: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/

## Swarm Notes

This task should be implemented first or second. It is the instrumentation layer for the rest of the roadmap.
