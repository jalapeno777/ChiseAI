# ChiseAI Autonomous Cognitive Self-Improvement System

Status: proposed-for-implementation  
Owner: Captain Craig / Aria / Jarvis / Merlin  
Date: 2026-03-13

## 1) Purpose

Define a full implementation blueprint for an autonomous, safety-bounded, self-improving cognitive system for ChiseAI that:

- learns continuously from outcomes without manual prompting,
- improves reasoning, memory, retrieval, neuro-symbolic inference, and metacognition,
- revises inconsistent beliefs using evidence,
- scales strategy and portfolio capabilities through controlled experiment loops,
- notifies Craig via Discord for all major assessments/improvements,
- never violates constitutional safety and authority guardrails.

This specification consolidates and extends:

- `docs/governance/metacognition-integration-blueprint.md`
- `docs/governance/skills-autonomy-control-plane.md`
- `docs/brain/brainspec-vcurrent.yaml`
- existing governance/reflection/retrieval/memory modules under `src/governance/` and `src/neuro_symbolic/`.

## 2) Non-Negotiable Soul Guidance (Immutable Constitution)

These are hard-block constraints, not soft guidelines.

### 2.1 Authority and Alignment

1. Human authority is final. Craig instructions are highest operational authority.
2. System must remain in project scope and declared objectives.
3. System must not self-expand privileges, permissions, or execution scope.
4. System must not circumvent user commands or governance workflows.

### 2.2 Integrity and Truthfulness

1. No deception, fabrication, hidden actions, or misleading summaries.
2. All autonomous actions must emit auditable evidence and provenance.
3. Uncertainty must be explicit in decision outputs.
4. Evidence must be source-traceable (Redis keys, Qdrant IDs, artifacts, logs).

### 2.3 Safety and Risk

1. Never modify protected risk caps/promotion gates/live-trading protections without explicit approval.
2. Kill-switch semantics remain highest runtime safety override.
3. Any constitutional violation candidate triggers immediate halt/escalation path.
4. Self-improvement must occur in paper/sim/shadow/canary phases before production promotion.

### 2.4 Anti-Manipulation and Partnership

1. System must act as partner, not adversary.
2. No user-coercive behavior, hidden optimization against user intent, or strategic omission.
3. Recommendation framing must include tradeoffs and risk notes.

## 3) Target Capability Model

### 3.1 Cognitive Layers

1. Perception Layer: market, execution, KPI, incident, and memory ingestion.
2. Reasoning Layer: neuro-symbolic hybrid + confidence-calibrated inference.
3. Memory Layer: Redis short-term + Qdrant long-term + belief graph.
4. Metacognition Layer: prediction-outcome-calibration loops + policy adaptation.
5. Governance Layer: constitutional enforcement, quality gates, escalation.

### 3.2 Learning Modes

1. Backpropagation-based supervised/online training for trainable neural components.
2. Reinforcement-style policy adaptation for thresholding/scheduling decisions.
3. Belief revision for symbolic/conflict knowledge updates.
4. Meta-learning over experiment outcomes to improve exploration efficiency.

## 4) Key Gaps in Current State (from repo audit)

1. Qdrant write paths are partially simulated/stubbed in important flows.
2. Neuro-symbolic orchestrator is not the default runtime decision path in signal generation.
3. Memory daily sweep is disabled due to known dedup bug.
4. Retrieval baseline quality evidence is thin for optimization confidence.
5. Constitution violation alert path contains placeholder/non-final delivery behavior.
6. Some memory embedding paths degrade to hash fallback if embedding deps are unavailable.

## 5) System Architecture

## 5.1 Autonomous Cognitive Control Plane (ACCP)

Create a new package:

- `src/autonomous_cognition/__init__.py`
- `src/autonomous_cognition/controller.py`
- `src/autonomous_cognition/contracts.py`
- `src/autonomous_cognition/state_machine.py`
- `src/autonomous_cognition/policy_engine.py`
- `src/autonomous_cognition/discord_events.py`

Responsibilities:

1. Orchestrate periodic cycles without manual prompting.
2. Coordinate learning, self-assessment, belief revision, and promotion.
3. Enforce constitution and guardrails before/after every autonomous action.
4. Emit standardized Discord notifications and evidence artifacts.

## 5.2 Learning Pipeline (Train/Eval/Promote)

Create:

- `src/autonomous_cognition/training/backprop_trainer.py`
- `src/autonomous_cognition/training/model_registry_bridge.py`
- `src/autonomous_cognition/experiments/hypothesis_generator.py`
- `src/autonomous_cognition/experiments/champion_challenger.py`
- `src/autonomous_cognition/experiments/portfolio_policy_lab.py`

Flow:

1. Generate hypothesis from failure patterns and opportunity signals.
2. Build candidate model/strategy variant.
3. Train (backprop where applicable) on bounded data windows.
4. Evaluate in backtest + paper simulation + stress tests.
5. Compare to incumbent via champion-challenger gates.
6. Promote only if statistically and risk-significantly superior.

## 5.3 Belief System and Inconsistency Resolution

Create:

- `src/autonomous_cognition/beliefs/models.py`
- `src/autonomous_cognition/beliefs/store.py`
- `src/autonomous_cognition/beliefs/consistency_checker.py`
- `src/autonomous_cognition/beliefs/revision_engine.py`
- `src/autonomous_cognition/beliefs/explanation.py`

Belief entity fields:

- `belief_id`
- `statement`
- `domain` (`strategy`, `risk`, `market_regime`, `execution`, `governance`)
- `confidence`
- `evidence_refs[]`
- `sources_quality_score`
- `created_at`, `updated_at`
- `status` (`active`, `superseded`, `under_review`)
- `supersedes_belief_id` (optional)

Consistency engine behavior:

1. Detect contradiction between active beliefs.
2. Score evidence quality recency and sample adequacy.
3. Auto-revise only if confidence delta and evidence threshold are met.
4. Otherwise create `requires_human_review` decision packet.
5. Always log rationale and diff of belief changes.

## 5.4 Memory and Retrieval Enhancements

Extend existing modules:

- `src/governance/tempmemory/migration.py`
- `src/operations/iteration_logging.py`
- `src/governance/retrieval/*`

Required upgrades:

1. Replace simulated Qdrant write placeholders with actual `upsert` + idempotency.
2. Standardize embedding generation to real model path (no hash fallback in prod mode).
3. Add hybrid retrieval: vector + lexical + reranker.
4. Add retrieval quality gates with larger benchmark corpus.
5. Reactivate `memory.daily_sweep` once dedup bug fixed and validated.

## 5.5 Neuro-Symbolic Runtime Integration

Integrate neuro-symbolic outputs into primary signal path:

- `src/signal_generation/signal_generator.py`
- `src/neuro_symbolic/orchestrator/orchestrator.py`

Design:

1. Add feature flag `neuro_symbolic:runtime_integration:enabled`.
2. In shadow mode, compute neuro-symbolic recommendation and log divergence.
3. In canary mode, allow bounded influence on confidence/direction.
4. In full mode, fusion layer becomes first-class contributor to final decision.
5. Keep deterministic fallback to current pipeline on any failure.

## 5.6 Metacognition Policy Engine

Create:

- `src/autonomous_cognition/metacog/prediction_outcome_linker.py`
- `src/autonomous_cognition/metacog/calibration_policy.py`
- `src/autonomous_cognition/metacog/autonomy_tuner.py`

Behavior:

1. Compare predicted vs actual outcomes per strategy/risk regime.
2. Update confidence calibration and execution thresholds.
3. Detect recurring failure fingerprints and feed hypothesis generator.
4. Tune autonomy levels only after sustained evidence windows.

## 6) Data Contracts and Storage

## 6.1 Redis Keys

- `bmad:chiseai:autocog:cycle:state`
- `bmad:chiseai:autocog:self_assessment:daily:<date>`
- `bmad:chiseai:autocog:improvement:events:<id>`
- `bmad:chiseai:autocog:beliefs:index`
- `bmad:chiseai:autocog:belief:<belief_id>`
- `bmad:chiseai:autocog:belief:conflicts:<date>`
- `bmad:chiseai:autocog:experiment:<exp_id>`
- `bmad:chiseai:autocog:champion:<domain>`
- `bmad:chiseai:autocog:constitution:violations`

TTL recommendations:

- cycle state: 30d
- daily assessments: 90d
- experiment records: 180d
- belief conflicts: 180d
- violation events: 365d

## 6.2 Qdrant Collections

- `ChiseAI_memory` (existing long-term memory)
- `ChiseAI_metacognition` (existing blueprint)
- `ChiseAI_beliefs` (new)
- `ChiseAI_autocog_events` (new)

Payload minimum fields for new collections:

- `project`, `story_id`, `component`, `event_type`
- `confidence_before`, `confidence_after` (if applicable)
- `belief_id` (if applicable)
- `contradiction_group_id` (if applicable)
- `decision_rationale`
- `evidence_refs`
- `timestamp_utc`

## 6.3 Artifact Outputs

- `_bmad-output/autocog/cycles/*.json`
- `_bmad-output/autocog/self_assessments/*.json`
- `_bmad-output/autocog/belief_revisions/*.json`
- `_bmad-output/autocog/experiment_reports/*.json`
- `docs/evidence/autocog/*.md`

## 7) Discord Notification Contract

All autonomous actions must be broadcast to Discord with dedup and severity routing.

## 7.1 Event Types

1. `autocog_cycle_completed`
2. `self_assessment_completed`
3. `improvement_promoted`
4. `improvement_rejected`
5. `belief_conflict_detected`
6. `belief_revision_applied`
7. `constitution_violation_detected`
8. `autonomy_level_changed`
9. `memory_health_alert`

## 7.2 Routing

Use/extend `config/discord_routing.yaml`:

- high/critical safety/governance events -> `trading` or dedicated `alerts` channel
- assessment and improvement summaries -> `summaries`

## 7.3 Message Schema

Required fields:

- `event_id`
- `event_type`
- `severity`
- `summary`
- `impact`
- `top_metrics`
- `artifact_path`
- `run_id`
- `timestamp_utc`

## 7.4 Delivery Rules

1. Non-blocking send with retries and exponential backoff.
2. Redis dedup key with 24h TTL.
3. If Discord delivery fails: log incident and retry asynchronously.
4. Critical safety events must trigger immediate retry escalation.

## 8) Autonomous Scheduling (No Manual Prompt Required)

Extend `config/autonomy_job_registry.yaml` with new jobs:

1. `autocog.self_assessment.daily`
2. `autocog.improvement_cycle.daily`
3. `autocog.belief_consistency.hourly`
4. `autocog.calibration.weekly`
5. `autocog.autonomy_tune.weekly`
6. `autocog.constitution_audit.daily`

Execution engine:

- Prefer existing cadence controller infrastructure under `scripts/evaluation/` and `scripts/ops/`.
- Add lock file and runtime budgets similar to skill autonomy loops.

## 9) Promotion and Safety Gates

No improvement may auto-promote without passing all gates.

Gate set:

1. Statistical Improvement Gate
- objective uplift vs incumbent (Sharpe/Sortino/risk-adjusted return)
- non-regression on drawdown and volatility limits

2. Calibration Gate
- ECE and confidence drift within thresholds

3. Consistency Gate
- no unresolved critical belief contradictions

4. Constitution Gate
- zero high-severity constitution violations in candidate cycle

5. Operational Reliability Gate
- data freshness, retrieval quality, and memory integrity pass

6. Explainability Gate
- decision artifacts include rationale and evidence pointers

7. Human-Authority Gate
- respects explicit approval requirements for protected domains

## 10) Backpropagation and Online Learning Policy

## 10.1 Allowed

1. Trainable neural modules for pattern recognition and signal scoring.
2. Offline scheduled retraining on curated datasets.
3. Online fine-tuning in bounded micro-updates if drift controls pass.

## 10.2 Forbidden

1. Direct live-trading self-modification without gated promotion.
2. Hidden model updates without artifact emission.
3. Training on unverified data streams.

## 10.3 Required Checks

1. Data provenance checks.
2. Regime-balanced validation split.
3. Champion comparison report.
4. Rollback package generation.

## 11) Belief Revision Policy

Resolution order for contradictory beliefs:

1. higher evidence quality and recency
2. larger sample support
3. lower downside-risk implication
4. constitutional alignment priority

Automatic revision allowed only when:

- confidence delta >= configured threshold,
- no constitutional conflict,
- no unresolved safety-critical dependency.

Otherwise:

- open review packet and notify Discord.

## 12) Governance and Auditability

Every autonomous cycle must emit:

1. input snapshot hash
2. action sequence
3. gate decisions and scores
4. final decision and rationale
5. rollback reference
6. notification status

Audit APIs to add:

- `src/governance/audit_trail/autocog_query.py`
- `src/governance/audit_trail/autocog_export.py`

## 13) Implementation Plan (Phased)

## Phase 0: Stabilization (prereq)

1. Implement real Qdrant writes for iteration learnings and tempmemory migration.
2. Fix memory dedup bug and re-enable `memory.daily_sweep`.
3. Harden Discord notifier delivery and channel config validation.

Acceptance:

- no simulated success returns for Qdrant write paths in production mode,
- daily sweep stable for 7 consecutive runs,
- Discord improvement notifications delivered with dedup and retries.

## Phase 1: Autonomous Self-Assessment Core

1. Add `autonomous_cognition.controller` and daily self-assessment job.
2. Add unified self-assessment artifact schema.
3. Add Discord event `self_assessment_completed`.

Acceptance:

- daily autonomous runs without human prompting,
- artifacts written and queryable,
- failures are non-silent and alerting.

## Phase 2: Belief Graph + Contradiction Resolution

1. Implement belief store and consistency checker.
2. Add revision engine with gated automatic belief updates.
3. Add Discord events for conflict/revision.

Acceptance:

- contradiction detection precision validated on test set,
- all revisions are provenance-linked and explainable.

## Phase 3: Strategy/Portfolio Improvement Engine

1. Implement hypothesis generator and experiment runner.
2. Add champion-challenger with full gates.
3. Add autonomous promotion/rejection eventing.

Acceptance:

- candidates are evaluated autonomously,
- promotions occur only when all gates pass,
- rollback path validated in drills.

## Phase 4: Neuro-Symbolic Runtime Integration

1. Shadow neuro-symbolic outputs in live signal flow.
2. Enable canary influence and measure divergence outcomes.
3. Promote to full fusion only after non-regression window.

Acceptance:

- no degradation in risk-adjusted performance,
- explainability coverage for all changed decisions.

## Phase 5: Autonomy Tuning and Continuous Governance

1. Weekly autonomy level tuning based on calibration and incident trends.
2. Constitution audit automation with violation escalation.
3. Dashboard and KPI pack for Craig.

Acceptance:

- autonomy decisions evidence-backed and reversible,
- safety incidents non-increasing trend.

## 14) Testing and Validation Strategy

Unit tests:

- belief conflict detection
- revision policy enforcement
- constitution guardrail hard blocks
- Discord payload formatting and dedup

Integration tests:

- autonomous cycle end-to-end
- memory write/read quality and retrieval relevance
- champion-challenger promotion gate bundle

E2E tests:

- scheduled self-assessment
- scheduled improvement cycle
- Discord notification observability
- rollback on failed canary

## 15) KPIs (Autonomous Cognitive Health)

1. calibration error (ECE)
2. repeat issue fingerprint rate
3. false-positive strategy promotion rate
4. time-to-improvement (experiments to beat champion)
5. belief contradiction resolution latency
6. autonomous cycle success rate
7. Discord notification delivery success rate
8. constitution violation count by severity

## 16) Immediate Story Breakdown

1. `AUTOCOG-001`: Real Qdrant write path hardening.
2. `AUTOCOG-002`: Memory sweep dedup bug fix and reactivation.
3. `AUTOCOG-003`: Autonomous cognitive controller + cycle contracts.
4. `AUTOCOG-004`: Belief graph store + consistency checker.
5. `AUTOCOG-005`: Belief revision engine + governance gates.
6. `AUTOCOG-006`: Improvement engine (hypothesis -> experiment -> judge).
7. `AUTOCOG-007`: Champion-challenger + promotion packet integration.
8. `AUTOCOG-008`: Neuro-symbolic runtime shadow/canary integration.
9. `AUTOCOG-009`: Discord event bus for autonomous assessments/improvements.
10. `AUTOCOG-010`: Constitution audit automation and violation escalation.

## 17) Out-of-Scope (This Spec)

1. Full live-trading autonomous execution changes.
2. Any relaxation of risk caps, promotion gates, or kill-switch governance.
3. Human authority model changes.

## 18) Definition of Done

This initiative is done when all are true:

1. Autonomous cycles run on schedule without manual prompting.
2. System self-assesses and proposes/applies bounded improvements.
3. Belief inconsistencies are detected and resolved with auditable rationale.
4. Discord notifications reliably inform Craig of key events.
5. Constitutional guardrails hard-block unsafe/unaligned behavior.
6. Performance and safety KPIs improve versus baseline without governance regressions.

