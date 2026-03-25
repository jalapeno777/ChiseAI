# TASK-03: Neuro-Symbolic Canary / Full Activation

## Summary

Progress the neuro-symbolic path from shadow to bounded canary and then to first-class signal contribution when scorecards support activation.

## Why This Is Necessary

Reasoning does not matter until it changes real decisions. Activation must happen in stages and under hard gates so cognition improves outcomes without eroding safety.

## Scope

- runtime gating and feature flags
- bounded fusion logic
- canary segmentation by token/timeframe/regime
- rollback hooks

## Deliverables

1. canary mode with capped confidence influence,
2. activation criteria tied to measured uplift,
3. immediate rollback switch,
4. full mode only after paper carryover and calibration gates pass.

## Best Practices

- activate on narrow scopes first,
- compare canary vs control on the same market windows,
- force human-readable rationale into activation decisions,
- keep rollback simpler than activation.

## Hardening Requirements

- canary must be segment-limited,
- auto-disable on drawdown, calibration, or divergence breach,
- no full activation without promotion packet,
- every activation change logged as a governance event.

## Telemetry

- `ns_canary_signals_total`
- `ns_canary_uplift_delta`
- `ns_canary_false_positive_delta`
- `ns_activation_state`
- `ns_rollback_total`

## Quantified Success

- canary improves precision or carryover without worsening drawdown,
- false positive rate improves by `>=10%` relative,
- rollback mean time `<5m`,
- no unapproved full-mode activations.

## Testing

- simulated canary vs control split
- activation gate tests
- rollback trigger tests
- kill-switch and feature-flag interaction tests

## Research Links

- Self-Consistency: https://arxiv.org/abs/2203.11171
- Process supervision: https://cdn.openai.com/improving-mathematical-reasoning-with-process-supervision/Lets_Verify_Step_by_Step.pdf

## Swarm Notes

Do not merge full activation behind ambiguous thresholds. Thresholds must be explicit and observable.
