# AI Cognition & Evolution Implementation Roadmap

## Document Information

| Field | Value |
|-------|-------|
| Document ID | ROADMAP-AI-COG-EVO-001 |
| Version | 1.0.0 |
| Created | 2026-03-25 |
| Owner | Codex for Craig review |
| Status | Draft |
| Scope | AI reasoning, cognition, memory, evolution, governance hardening |

## Executive Summary

This roadmap converts ChiseAI's AI reasoning and evolution vision into an executable implementation program. The target system is not just "more automated"; it is a safety-bounded cognitive trading platform that can:

1. reason through a live neuro-symbolic path,
2. maintain durable beliefs with evidence-based revision,
3. retrieve the right memory with measurable quality,
4. evolve strategies and policies through verifier-backed experiments,
5. harden itself with explicit constitutional and objective controls,
6. prove improvement through telemetry and decision scorecards.

The current repo is strong in architecture, governance, and partial cognition modules, but it does not yet have a closed implementation loop from reasoning -> action -> outcome -> revision -> promotion.

## Goals

### Primary Goals

1. Make neuro-symbolic reasoning a first-class live signal contributor.
2. Replace heuristic self-improvement with verifier-backed evolution.
3. Turn memory and belief management into dependable production systems.
4. Add objective-state and constitutional control strong enough to support higher autonomy.
5. Create telemetry and eval loops that quantify whether cognition is improving or degrading.

### Operating Constraint

The implementation and operation model for this roadmap is autonomous by default.

Human approval is required only for:

1. critical evolution items,
2. live-scope promotions,
3. constitutional or objective-state changes,
4. other explicitly high-impact actions already governed elsewhere in ChiseAI policy.

### Non-Goals

1. Unbounded self-modification.
2. Direct live-trading self-promotion without staged gates.
3. Silent degradation to weak cognition in production.
4. Research work with no measurable operational output.

## Target Capability Model

| Layer | Required End State |
|-------|--------------------|
| Runtime Reasoning | Neuro-symbolic outputs affect live signal confidence/direction under shadow/canary/full gates |
| Beliefs | Contradictions detected, revisions evidence-backed, uncertain cases escalated |
| Memory | Redis + Qdrant + graph/hybrid retrieval with measurable retrieval quality |
| Evolution | Strategy/model mutations go through backtest, paper, stress, verifier, promotion |
| Soul/Governance | Immutable objective hierarchy and constitutional checks on all high-impact actions |
| Telemetry | Leading, lagging, and safety indicators show cognition quality in near real time |

## Phase Plan

### Phase 1: Foundation Closure

- TASK-01 Strategy Substrate
- TASK-04 Belief Graph & Revision Pipeline
- TASK-05 Memory & Retrieval Hardening
- TASK-10 Telemetry, Evals, Decision Scorecards

Exit criteria:

- strategy runtime no longer stubbed
- belief revisions artifacted with evidence
- production memory paths stop silently degrading
- baseline cognition scorecards visible in Grafana and artifacts

### Phase 2: Runtime Cognition Activation

- TASK-02 Neuro-Symbolic Shadow Integration
- TASK-03 Neuro-Symbolic Canary/Full Activation
- TASK-06 Verifier-Driven Reasoning
- TASK-07 World/Regime Model

Exit criteria:

- shadow divergence measured and bounded
- canary path influences decisions safely
- verifier catches bad reasoning steps
- regime/world model improves calibration or carryover

### Phase 3: Self-Improvement Engine

- TASK-08 Autonomous Experimentation & Promotion
- TASK-12 Research Acceleration Program

Exit criteria:

- experiment loop is reproducible
- candidate promotion is evidence-backed
- failed experiments produce reusable learnings
- research backlog is feeding implementation decisions

### Phase 4: High-Autonomy Hardening

- TASK-09 Soul, Objective, Governance Hardening
- TASK-11 Testing, Chaos, Regression Harness

Exit criteria:

- objective hierarchy is machine-checkable
- chaos tests prove safe degradation
- autonomy raises only when scorecards support it

## Task Sequence

| Order | Task | SP | Priority | Dependency |
|------:|------|----|----------|------------|
| 1 | TASK-01 Strategy Substrate | 5 | P0 | None |
| 2 | TASK-10 Telemetry, Evals, Decision Scorecards | 3 | P0 | None |
| 3 | TASK-05 Memory & Retrieval Hardening | 5 | P0 | 2 |
| 4 | TASK-04 Belief Graph & Revision Pipeline | 4 | P0 | 3 |
| 5 | TASK-02 Neuro-Symbolic Shadow Integration | 5 | P0 | 1,2,3 |
| 6 | TASK-06 Verifier-Driven Reasoning | 4 | P1 | 2,5 |
| 7 | TASK-07 World / Regime Model | 4 | P1 | 2 |
| 8 | TASK-03 Neuro-Symbolic Canary / Full Activation | 5 | P1 | 5,6,7 |
| 9 | TASK-08 Autonomous Experimentation & Promotion | 5 | P1 | 1,2,4,6 |
| 10 | TASK-09 Soul / Objective / Governance Hardening | 4 | P1 | 4,8 |
| 11 | TASK-11 Testing, Chaos, Regression Harness | 4 | P1 | 1-10 |
| 12 | TASK-12 Research Acceleration Program | 3 | P2 | Continuous |

## Quantified Success Measures

### Leading Indicators

| Metric | Good | Warning | Bad |
|-------|------|---------|-----|
| Shadow divergence rate | <10% | 10-20% | >20% |
| Retriever top-5 evidence hit rate | >85% | 70-85% | <70% |
| Belief revision block rate due to weak evidence | 20-60% | 5-20% or 60-80% | <5% or >80% |
| Reasoning verifier rejection rate | 10-35% | 5-10% or 35-50% | <5% or >50% |
| Experiment reproducibility rate | >95% | 85-95% | <85% |

### Lagging Indicators

| Metric | Good | Warning | Bad |
|-------|------|---------|-----|
| Paper carryover rate | improving QoQ | flat | declining |
| False positive rate | <0.30 | 0.30-0.40 | >0.40 |
| Calibration error | <0.08 | 0.08-0.15 | >0.15 |
| Strategy promotion win rate after paper | >60% | 40-60% | <40% |
| Kill-switch events from reasoning defects | 0 | 1 near miss | >=1 real |

### Hard Stop Indicators

1. neuro-symbolic canary increases drawdown or false positives materially,
2. memory silently degrades to fallback in production mode,
3. verifier bypass is detected,
4. objective graph and constitutional state diverge,
5. experiment promotion occurs without evidence packet.

## Swarm Implementation Guidance

### Required Work Packet for Every Task

Each implementation packet should contain:

- scope and owned files
- acceptance criteria
- test commands
- telemetry to add
- rollback note
- evidence artifact path

### Approval Policy For This Roadmap

- default: autonomous execution
- medium-risk implementation and hardening: autonomous
- research spikes and measurement work: autonomous
- critical evolution promotions or objective-changing actions: human approval required
- if a worker is unsure whether something is "critical evolution", it must default to autonomous shadow/paper/canary work and escalate only the promotion or irreversible step

### Required Completion Evidence

1. file list
2. tests run
3. metric outputs
4. screenshots or artifact files for dashboards/reports where relevant
5. residual risks

### Parallelization Rules

Allowed in parallel:

- TASK-01 with TASK-10
- TASK-04 after memory contracts stabilize
- TASK-12 continuously as a sidecar

Not safe in parallel:

- TASK-02 and TASK-03
- TASK-08 before TASK-01
- TASK-09 before the runtime behavior is understood

## Deliverables In This Package

- master roadmap
- one artifact per task
- one execution-ready ticket per story
- research links embedded per task
- telemetry and testing requirements embedded per task

## Recommended First Sprint

1. TASK-01 Strategy Substrate
2. TASK-10 Telemetry, Evals, Decision Scorecards
3. TASK-05 Memory & Retrieval Hardening

Reason:

- these unlock the rest of the program,
- they reduce the risk of false confidence,
- they create the measurement layer needed for all later autonomy claims.
