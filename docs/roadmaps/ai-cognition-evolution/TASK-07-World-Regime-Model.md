# TASK-07: World / Regime Model

## Summary

Build an explicit regime and counterfactual model so the AI can reason about latent market state, likely transitions, and action consequences.

## Why This Is Necessary

Without a world model, reasoning remains mostly reactive. Regime-aware planning is the difference between pattern matching and adaptive cognition.

## Scope

- regime state abstraction
- transition modeling
- counterfactual simulation hooks
- integration with signal and risk pipelines

## Deliverables

1. regime state model with confidence,
2. state transition estimator,
3. counterfactual action simulator for candidate signals,
4. explanation fields tying decisions to regime assumptions.

## Best Practices

- keep regime labels few and operationally meaningful,
- expose uncertainty in regime classification,
- log assumption drift over time,
- prefer narrow, testable state machines over vague latent labels.

## Hardening Requirements

- regime model must degrade to explicit `UNKNOWN`,
- no hidden assumption of stationarity,
- counterfactuals must be clearly marked as simulated.

## Telemetry

- `regime_state_distribution`
- `regime_transition_total`
- `regime_confidence_mean`
- `counterfactual_eval_total`
- `counterfactual_disagreement_with_realized_total`

## Quantified Success

- regime classifier stable enough to avoid frequent flapping,
- calibration improves by regime slice,
- false positives decrease in previously unstable regimes.

## Testing

- historical replay tests,
- regime transition boundary tests,
- unknown regime fallback tests,
- counterfactual replay against realized outcomes.

## Research Links

- Voyager: https://arxiv.org/abs/2305.16291
- Quiet-STaR: https://arxiv.org/abs/2403.09629

## Swarm Notes

This should produce slice-based scorecards: trending, ranging, volatile, unknown.
