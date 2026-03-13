# AUTOCOG Phase 0 Backlog (2026-03-13)

Source: `docs/architecture/autonomous-cognitive-self-improvement-spec.md`

## Objective

Stabilize core memory, dedup, and governance notification paths so autonomous cognitive cycles can run safely and verifiably without manual prompting.

## Stories

1. `AUTOCOG-001` Real Qdrant writes for iteration learnings
2. `AUTOCOG-002` Real Qdrant writes for tempmemory migration
3. `AUTOCOG-003` Dedup vector TypeError fix + re-enable daily sweep
4. `AUTOCOG-004` Discord governance notifier hardening + channel validation

## Exit Criteria

1. No simulated "would store" behavior in production-enabled Qdrant paths.
2. Dedup sweep job re-enabled and protected by passing tests.
3. Governance and constitution notifications use real Discord send path when configured.
4. Evidence bundle includes passing tests and scheduler update.
