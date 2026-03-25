# AI Cognition & Evolution Roadmap Package

## Purpose

This package contains the implementation roadmap and task artifacts for building ChiseAI's next-stage AI cognition stack:

- neuro-symbolic runtime reasoning
- belief and memory systems
- verifier-driven self-improvement
- strategy evolution
- constitutional and objective hardening
- telemetry, testing, and research loops

## Primary Document

- [AI-Cognition-Evolution-Roadmap.md](./AI-Cognition-Evolution-Roadmap.md)

## Task Artifacts

1. [TASK-01-Strategy-Substrate.md](./TASK-01-Strategy-Substrate.md)
2. [TASK-02-NeuroSymbolic-Shadow-Integration.md](./TASK-02-NeuroSymbolic-Shadow-Integration.md)
3. [TASK-03-NeuroSymbolic-Canary-Full-Activation.md](./TASK-03-NeuroSymbolic-Canary-Full-Activation.md)
4. [TASK-04-Belief-Graph-Revision-Pipeline.md](./TASK-04-Belief-Graph-Revision-Pipeline.md)
5. [TASK-05-Memory-Retrieval-Hardening.md](./TASK-05-Memory-Retrieval-Hardening.md)
6. [TASK-06-Verifier-Driven-Reasoning.md](./TASK-06-Verifier-Driven-Reasoning.md)
7. [TASK-07-World-Regime-Model.md](./TASK-07-World-Regime-Model.md)
8. [TASK-08-Autonomous-Experimentation-Promotion.md](./TASK-08-Autonomous-Experimentation-Promotion.md)
9. [TASK-09-Soul-Objective-Governance-Hardening.md](./TASK-09-Soul-Objective-Governance-Hardening.md)
10. [TASK-10-Telemetry-Evals-Decision-Scorecards.md](./TASK-10-Telemetry-Evals-Decision-Scorecards.md)
11. [TASK-11-Testing-Chaos-Regression-Harness.md](./TASK-11-Testing-Chaos-Regression-Harness.md)
12. [TASK-12-Research-Acceleration-Program.md](./TASK-12-Research-Acceleration-Program.md)

## Execution Tickets

- [tickets/README.md](./tickets/README.md)
- One execution-ready ticket per planned story (`ST-AI-COG-001` through `ST-AI-COG-012`)
- First sprint worker contracts included for `ST-AI-COG-001`, `ST-AI-COG-010`, and `ST-AI-COG-005`

## Operating Rule

No task in this package should be marked complete on implementation effort alone. Completion requires:

- code landed
- tests passing
- telemetry emitting
- failure modes exercised
- artifact evidence captured
- scorecard deltas reviewed

## Retrieval Conventions

Swarm and oversight agents should use these stable lookup handles when retrieving this roadmap package from memory systems:

- Redis primary key: `roadmap:ai_cognition_evolution:2026-03-25`
- Redis epic alias: `roadmap:epic:EP-AI-COG-001`
- Redis story aliases: `roadmap:story:ST-AI-COG-001` through `roadmap:story:ST-AI-COG-012`
- Qdrant lookup terms: `EP-AI-COG-001`, `AI cognition and evolution roadmap`, `AI-Cognition-Evolution-Roadmap`

When this roadmap is revised materially, publish a new dated Redis primary key and update the alias keys to point at the newest record.
