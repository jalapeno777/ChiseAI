# AutoCog Phase 1 Backlog (2026-03-13)

## Goal
Implement the Autonomous Self-Assessment Core so the system can run daily autonomous cognition checks, persist artifacts, and notify Discord without manual prompting.

## Stories

1. `AUTOCOG-101` Autonomous controller + daily cycle
- Add `autonomous_cognition.controller`.
- Add daily runner script and register it in `config/autonomy_job_registry.yaml`.
- Persist assessment artifacts to file and Redis; opportunistically to Qdrant.

2. `AUTOCOG-102` Unified self-assessment artifact schema
- Add canonical schema for self-assessment outputs.
- Include status, overall score, dimensions, findings, recommendations, evidence, metadata.

3. `AUTOCOG-103` Discord completion event
- Add `self_assessment_completed` formatting and notifier method.
- Wire runner to send Discord notifications on completion/failure.
- Maintain dedup behavior.

## Definition of Done
- Daily self-assessment can run headlessly via job registry.
- Artifacts are stored and machine-queryable.
- Failures are non-silent and reported through logs + Discord event path.

