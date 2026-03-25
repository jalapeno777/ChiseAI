# TASK-01: Strategy Substrate

## Summary

Replace the current traced strategy stub with a real execution substrate for strategy registration, validation, simulation, and artifact-backed mutation.

## Why This Is Necessary

Self-evolution is blocked without a real strategy runtime. Today the system cannot safely mutate, execute, compare, and roll back strategy variants as first-class entities.

## Scope

- `src/strategy/engine.py`
- `src/strategy/registry.py` new
- `src/strategy/contracts.py` new
- `src/strategy/validator.py` new
- `src/strategy/executors/` new
- `tests/...strategy...` new

## Deliverables

1. Strategy definition contract.
2. Executable strategy registry with IDs, versions, and provenance.
3. Validation pipeline for parameter, structure, and risk constraints.
4. Backtest, paper, and shadow execution adapters.
5. Diffable artifacts for every candidate strategy.

## Best Practices

- Use constrained configuration and DSL surfaces only.
- Separate strategy definition from execution environment.
- Require reproducible seeds and frozen input data windows.
- Make validation deterministic and fail closed.
- Emit machine-readable artifacts for every run.

## Hardening Requirements

- prevent arbitrary code mutation,
- enforce schema versioning,
- require rollback target for every promotion candidate,
- hash strategy config plus data window plus model refs,
- reject execution if provenance is incomplete.

## Telemetry

- `strategy_registry_total`
- `strategy_validation_fail_total`
- `strategy_execution_duration_ms`
- `strategy_execution_by_mode_total`
- `strategy_reproducibility_fail_total`

## Quantified Success

- `100%` of candidate strategies artifacted,
- `0` live-executable strategies without validation packet,
- `>95%` deterministic replay match rate,
- `0` schema-bypass executions.

## Testing

- unit: schema, validation, provenance hashing, replay determinism
- integration: strategy registration -> validation -> backtest -> artifact write
- negative: invalid risk caps, missing metadata, schema mismatch

## Research Links

- AlphaEvolve: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- Toolformer: https://arxiv.org/abs/2302.04761

## Swarm Notes

This task is the root dependency for meaningful self-evolution. Do not start autonomous promotion work before this is live.
