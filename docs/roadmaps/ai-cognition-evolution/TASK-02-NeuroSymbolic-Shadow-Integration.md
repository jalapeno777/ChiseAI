# TASK-02: Neuro-Symbolic Shadow Integration

## Summary

Run the neuro-symbolic stack in shadow mode on the live signal path, logging divergences, confidence shifts, explanations, and failure causes without changing production decisions.

## Why This Is Necessary

You cannot safely activate cognition that is not already measured on the real path. Shadow mode is the only defensible way to establish whether the reasoning stack is additive, redundant, or harmful.

## Scope

- `src/signal_generation/signal_generator.py`
- `src/autonomous_cognition/runtime_integration.py`
- `src/neuro_symbolic/orchestrator/orchestrator.py`
- signal telemetry and dashboard panels

## Deliverables

1. feature-flagged shadow invocation in signal generation,
2. divergence logs for direction, confidence, and rationale,
3. failure-safe fallback behavior,
4. artifact outputs for shadow evaluations.

## Best Practices

- keep legacy path authoritative in shadow mode,
- log structured divergence reasons, not just booleans,
- separate model error from data-quality error,
- keep timing overhead visible.

## Hardening Requirements

- no silent shadow failures,
- explicit mode tags on every signal,
- bounded latency overhead,
- immutable audit field proving legacy decision remained authoritative.

## Telemetry

- `neuro_symbolic_shadow_total`
- `neuro_symbolic_shadow_error_total`
- `neuro_symbolic_divergence_rate`
- `neuro_symbolic_latency_overhead_ms`
- `neuro_symbolic_explanation_missing_total`

## Quantified Success

- shadow coverage on `>95%` of candidate signals,
- latency overhead p95 `<100ms`,
- unexplained divergence `<5%`,
- shadow pipeline failure rate `<1%`.

## Testing

- unit: flag behavior, divergence calculation, fallback semantics
- integration: live signal generation emits both legacy and shadow records
- regression: stale data, missing indicators, malformed reasoning payloads

## Research Links

- Reflexion: https://arxiv.org/abs/2303.11366
- CRITIC: https://arxiv.org/abs/2305.11738

## Swarm Notes

Completion requires a dashboard or report that shows divergence distributions by regime and token.
