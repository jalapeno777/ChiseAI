# TASK-08: Autonomous Experimentation & Promotion

## Summary

Make self-improvement real by implementing a candidate generation, verification, comparison, and promotion loop for strategies and cognition policies.

## Why This Is Necessary

The system should improve because experiments prove it should, not because heuristics imply it might.

## Scope

- experiment contracts
- candidate registry
- champion/challenger comparison
- promotion packet generation

## Deliverables

1. experiment manifest with hypothesis, expected outcome, and budget,
2. replayable candidate runs,
3. champion/challenger comparison using real metrics,
4. promotion packet with backtest, paper, calibration, risk, and rollback.

## Best Practices

- require explicit hypothesis and falsification condition,
- compare against incumbent on same data windows,
- separate exploratory from promotable experiments,
- count failed experiments and learnings, not just wins.

## Hardening Requirements

- no candidate can become champion on proxy metrics alone,
- promotion requires paper-stage evidence where applicable,
- autonomous experimentation is the default for backtest, shadow, and paper scopes,
- auto-promotion disabled for live scope,
- failed candidate artifacts retained.

## Telemetry

- `experiment_total`
- `experiment_reproducible_total`
- `experiment_failed_total`
- `promotion_candidate_total`
- `promotion_approved_total`
- `promotion_rejected_total`

## Quantified Success

- experiment docs coverage `100%`,
- reproducibility `>95%`,
- false promotion rate declines,
- time-to-improvement measured and trending down.

## Testing

- integration: manifest -> run -> compare -> packet
- negative: missing hypothesis, missing rollback, missing baseline comparison
- statistical sanity tests for uplift claims.

## Research Links

- AlphaEvolve: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- Self-Play Fine-Tuning: https://arxiv.org/abs/2401.01335

## Swarm Notes

Promotion claims should be reviewable from artifact files alone.

Human approval is only required for critical evolution steps such as live-facing promotion, irreversible objective changes, or other explicitly high-impact gates. Everything else in this task should run autonomously.
