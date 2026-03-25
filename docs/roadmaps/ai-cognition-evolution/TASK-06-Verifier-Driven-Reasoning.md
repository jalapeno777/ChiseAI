# TASK-06: Verifier-Driven Reasoning

## Summary

Add step-level and outcome-level verifiers so reasoning chains are checked before they influence promotions, policy changes, or high-confidence signals.

## Why This Is Necessary

Reasoning systems fail when they only optimize final answers. Frontier reliability improvements are increasingly verifier-driven.

## Scope

- reasoning chain representation
- verifier interfaces
- step scoring
- promotion and runtime gate integration

## Deliverables

1. structured reasoning trace format,
2. verifier modules for factuality, consistency, risk, and evidence sufficiency,
3. pass/fail thresholds for signal and promotion workflows,
4. rejection artifact with failure reasons.

## Best Practices

- keep verifiers independent from generators where possible,
- score both final answer and intermediate support,
- use external tools for evidence checks,
- keep verifier outputs compact and machine-readable.

## Hardening Requirements

- high-impact actions require verifier pass,
- verifier bypass forbidden except explicit emergency override,
- disagreement between verifiers logged and surfaced.

## Telemetry

- `reasoning_trace_total`
- `reasoning_verifier_fail_total`
- `reasoning_verifier_disagreement_total`
- `reasoning_trace_length`
- `high_impact_reasoning_bypass_total`

## Quantified Success

- verifier catch rate increases on known-bad cases,
- post-hoc failure rate for verifier-passed actions trends down,
- `0` untracked verifier bypasses.

## Testing

- gold-set reasoning cases,
- adversarial counterexamples,
- stale evidence tests,
- intentionally deceptive or weak-support traces.

## Research Links

- Let's Verify Step by Step: https://cdn.openai.com/improving-mathematical-reasoning-with-process-supervision/Lets_Verify_Step_by_Step.pdf
- CRITIC: https://arxiv.org/abs/2305.11738
- Monitoring Monitorability: https://cdn.openai.com/pdf/d57827c6-10bc-47fe-91aa-0fde55bd3901/monitoring-monitorability.pdf

## Swarm Notes

Verifiers should be calibrated on ChiseAI-specific failure modes, not generic reasoning benchmarks alone.
