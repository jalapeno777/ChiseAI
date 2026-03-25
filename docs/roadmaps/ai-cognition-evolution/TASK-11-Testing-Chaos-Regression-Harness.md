# TASK-11: Testing, Chaos, Regression Harness

## Summary

Add an end-to-end harness that proves cognition systems fail safely, degrade explicitly, and avoid silent regressions.

## Why This Is Necessary

AI-heavy systems often regress in hidden ways. The harder the cognition stack becomes, the more important chaos, fault-injection, and slice-based regression testing become.

## Scope

- e2e cognition tests
- fault injection
- memory outage simulations
- verifier outage simulations
- rollback drills

## Deliverables

1. cognition regression suite,
2. production-like shadow replay harness,
3. chaos scenarios for Redis, Qdrant, retrieval, verifier, and regime model failures,
4. rollback and downgrade drills.

## Best Practices

- test real failure chains, not unit-only logic,
- include long-horizon and stateful test cases,
- snapshot telemetry before and after chaos runs,
- keep a stable gold-set for comparison.

## Hardening Requirements

- all production fallback modes must be explicitly tested,
- every chaos test must define expected safety behavior,
- regression failures block promotion.

## Telemetry

- `chaos_test_total`
- `chaos_test_failed_total`
- `safe_degradation_success_total`
- `rollback_drill_total`
- `regression_goldset_fail_total`

## Quantified Success

- safe degradation success `>95%`,
- rollback drill completion `100%`,
- gold-set regression detection catches seeded failures.

## Testing

- unit, integration, and e2e all required,
- nightly replay harness,
- pre-promotion chaos subset,
- weekly full cognition resilience sweep.

## Research Links

- CRITIC: https://arxiv.org/abs/2305.11738
- Reflexion: https://arxiv.org/abs/2303.11366

## Swarm Notes

This task closes the trust gap between "it worked once" and "it is safe to rely on."
