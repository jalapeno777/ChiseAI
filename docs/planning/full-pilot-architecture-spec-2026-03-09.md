# Full Pilot Architecture Spec (2026-03-09)

## 1. Scope and Decisions

This spec defines the **Full Pilot** architecture for ChiseAI autonomy with these confirmed decisions:

- Security and governance controls are required as first-class constraints.
- Legacy artifacts may be exempt from strict conformance gates.
- Full pilot scope includes memory, planning, execution, reflection, metacognition, and self-evolution loops.

Primary business objective:

- Increase probability of **ongoing recurring profitable paper/live trading** while enforcing safety, risk, and governance boundaries.

## 2. Current-State Capability Map

### 2.1 Memory

Implemented (strong):

- Redis + Qdrant plumbing exists across governance and tempmemory modules.
- Memory lifecycle and consolidation tooling exists (`scripts/ops/memory_sweep.py`, `src/governance/tempmemory/*`).
- Reflection and skill-autonomy artifacts are already storable and queryable.

Partial / gaps:

- Host defaults are inconsistent across scripts/modules (`localhost`, `host.docker.internal`, `chiseai-redis`).
- Memory TTL policy drift exists between blueprint and command execution guidance.
- Some report metrics labelled `*_24h` are computed from full corpus scans, not strict rolling windows.

### 2.2 Planning

Implemented (strong):

- BMAD planning docs/roadmaps exist (`docs/prd.md`, `docs/product-brief.md`, `docs/roadmaps/*`, `docs/planning/*`).
- Iteration lifecycle commands exist (`chise-iterloop-start`, `chise-iterloop-close`).
- Status/gate validation framework exists (`docs/validation/validation-registry.yaml`, `scripts/validation/*`).

Partial / gaps:

- Compliance validation indicates many legacy iterlogs do not satisfy current metacog/insight schema.
- Planning artifacts are rich but not fully wired into one always-on orchestrator loop.

### 2.3 Execution

Implemented (strong):

- Autonomous control plane modules exist (`src/autonomous_control_plane/*`).
- Trading safety and canary/promotion patterns exist (`src/execution/*`, `docs/promotion/*`).
- Incident and rollback scripts/runbooks exist.

Partial / gaps:

- Single orchestrated runtime loop for operations/governance/learning remains fragmented across cron + manual triggers.
- Scheduler currently focuses on BrainEval cadence and does not cover all governance-evolution tasks.

### 2.4 Reflection

Implemented (strong):

- Reflection artifacts, loops, policies, and runner exist.
- Daily/weekly reflection reporting tooling exists.

Partial / gaps:

- Feature flag behavior is inconsistent across modules (fail-open vs fail-closed defaults).
- Reflection runtime defaults and docs are not fully aligned on connectivity conventions.

### 2.5 Metacognition

Implemented (strong):

- Metacognition blueprint, commands, weekly process, and compliance checker exist.

Partial / gaps:

- TTL policy mismatch: blueprint policy vs command instructions.
- Compliance checker output indicates non-trivial legacy non-conformance.

### 2.6 Skill Autonomy / Self-Evolution

Implemented (strong):

- Skill autonomy command stack and scripts exist (tick, ingest, promote, rollback).
- Model/strategy promotion infrastructure exists (`src/ml/model_registry`, `src/ml/validation/promotion.py`, execution canary modules).

Partial / gaps:

- Command/skill docs reference some missing scripts (stale links / insufficient wiring).
- No single “always-on improvement governor” that continuously prioritizes and executes improvement work under budget/risk constraints.

### 2.7 Commands, Skills, and Script Wiring Audit

Command audit snapshot:

- `.opencode/command/*.md` script refs scanned: 34 unique.
- Missing refs detected: 4.
- Missing command refs:
  - `scripts/check_ttl.lua`
  - `scripts/discord/post_message.py`
  - `scripts/discord/test_webhook.py`
  - `scripts/taiga_sync.py`

Skill audit snapshot (`.opencode/skills/chiseai-*`):

- Script refs scanned: 10 unique.
- Missing refs detected: 4.
- Missing skill refs:
  - `scripts/validate_docker_connectivity.py`
  - `scripts/validate_skill.py`
  - `scripts/swarm/ci_pr_status.py`
  - `scripts/swarm/ci_root_cause.py`

Interpretation:

- Significant autonomy building blocks exist, but command/skill docs and script reality are partially out of sync.
- This is not an architecture absence; it is a **wiring and reliability gap** that should be resolved in Phase 0.

## 3. Verified Technical Gaps to Close Before Pilot Reliability

### P0 (must-fix pre-pilot go-live)

- Remove hardcoded secrets from code defaults (e.g., Influx token in ACP settings).
- Normalize host resolution policy for Redis/Qdrant across all scripts/modules.
- Unify feature-flag storage/lookup semantics and default fail mode by environment.
- Fix command/skill reference drift for missing scripts or update docs to canonical replacements.

### P1 (pilot start + first 2 weeks)

- Enforce rolling-window correctness for `*_24h` metrics.
- Consolidate scheduler into a unified “autonomy cadence controller” job registry.
- Add deterministic legacy-exempt handling so historical non-compliance does not block forward motion.

### P2 (pilot hardening)

- Strengthen integration tests for governance scripts in CI path context.
- Add richer reflection-to-action wiring (automatic story creation, prioritization, ownership routing).

## 4. Target Full Pilot Architecture

## 4.1 Control Plane Layers

### Layer A: Safety and Policy Gate (always first)

Inputs:

- Risk caps, venue constraints, human approval rules, feature flags.

Responsibilities:

- Block unsafe execution and unsafe self-modification.
- Enforce “canary before promotion” for strategy/model changes.
- Enforce policy schema before persistence of critical decisions.

Output:

- `ALLOW`, `DEGRADE`, or `BLOCK` decision token consumed by all downstream loops.

### Layer B: Operational Loop (6h cadence + event-driven)

Responsibilities:

- Data health checks, KPI ingest, issue detection, anomaly flags.
- Trigger tactical remediation playbooks and non-breaking fixes.

Existing base:

- `scripts/evaluation/kpi_scheduler.py`, `run_mini_eval.py`, trend/repeated-issue tooling.

### Layer C: Reflection + Metacog Loop (daily + per-story close)

Responsibilities:

- Generate meso/macro reflections.
- Compare prediction vs outcome, compute calibration deltas.
- Emit prevention rules and automation targets.

Existing base:

- `chise-metacog-start`, `chise-metacog-close`, `chise-metacog-weekly`, reflection runner.

### Layer D: Evolution Loop (weekly)

Responsibilities:

- Aggregate failures/drift/opportunity candidates.
- Rank by expected PnL impact, risk reduction, and implementation cost.
- Route to skill backlog / architecture backlog / experiment backlog.
- Launch champion-challenger experiments with governance checks.

Existing base:

- skill autonomy ingestion/promotion/rollback, model registry/promotion modules.

### Layer E: Executive Outcome Loop (weekly + monthly)

Responsibilities:

- Business KPI accountability: profitability consistency, drawdown, stability, operating reliability.
- Decide continue/pause/rollback/escalate for pilot scope.

## 4.2 Unified Job Registry (Autonomous Triggering)

Replace fragmented scheduling with one registry-driven runner:

- `job_id`
- `cadence` (event, 6h, daily, weekly)
- `preconditions`
- `risk_level`
- `required_flags`
- `required_approvals`
- `idempotency_key`
- `last_success_at`
- `retry_policy`

Mandatory first-wave jobs:

- `ops.kpi_ingest_6h`
- `ops.daily_trends`
- `governance.daily_reflection`
- `governance.metacog_weekly`
- `memory.daily_sweep`
- `skills.autonomy_weekly`
- `strategy.experiment_triage_weekly`
- `strategy.canary_review_weekly`

## 4.3 Event Bus Contract (Redis first, extensible)

Standard event envelope:

- `event_id`
- `event_type`
- `story_id` (optional)
- `timestamp_utc`
- `producer`
- `severity`
- `payload_schema_version`
- `payload`

Core event types:

- `reflection.generated`
- `metacog.closed`
- `incident.detected`
- `skill_gap.detected`
- `experiment.candidate.created`
- `promotion.candidate.ready`
- `promotion.approved`
- `promotion.rejected`
- `rollback.triggered`

## 4.4 Memory Architecture for Self-Reliance

- Working memory: short-horizon state for in-flight tasks and recent signals.
- Episodic memory: outcome-tagged run/incident/reflection packets.
- Semantic memory: deduplicated policies, runbook knowledge, strategy constraints.
- Procedural memory: executable skill and command routing patterns.

Rules:

- Every critical decision writes to episodic memory with provenance.
- Promotion decisions require linked evidence pointers.
- Automatic dedup + summarization reduces context bloat.

## 4.5 Reflection, Metacognition, and Self-Evolution Integration

Reflection is the observation layer, metacognition is calibration, self-evolution is action selection.

Pipeline:

1. Reflection captures what happened and candidate root causes.
2. Metacognition scores prediction quality and confidence calibration.
3. Evolution engine converts repeated misses into prioritized change candidates.
4. Candidates go through safety gate, then canary/promotion path.
5. Post-change outcomes feed back into reflection/metacog memory.

Autonomy policy:

- Low-risk automations: auto-execute.
- Medium-risk changes: auto-stage + human async approval window.
- High-risk changes (capital/risk behavior): explicit approval required.

## 5. External Technique Adoption Map (Pilot-Safe)

Adopted as patterns mapped onto Opencode CLI workflows.

### 5.1 Retrieval + Self-Correction

- Self-RAG and CRAG-style retrieval grading/correction for planning and runbook lookup quality.
- GraphRAG-inspired structured memory graph for cross-story dependency reasoning.

Pilot application:

- Improve root-cause retrieval quality before action selection.
- Reduce repeated false fixes from poor context retrieval.

### 5.2 Reflection-to-Action Learning

- Reflexion-style verbal reinforcement loop for repeated issue prevention rules.
- Voyager-style skill library growth pattern for reusable execution routines.

Pilot application:

- Convert recurring failure narratives into executable playbooks/skills automatically.

### 5.3 Architecture Search and Multi-Agent Orchestration

- AgentSquare-style modular search concept for evaluating planner/executor/reviewer compositions.
- Magentic-One-inspired orchestrator routing for dynamic specialist selection.

Pilot application:

- Choose cheapest-safe agent routing policy for each task category.

### 5.4 Memory Benchmarking and Governance Observability

- Long-horizon memory evaluation mindset (recent memory benchmark literature) for regression checks.
- OpenTelemetry GenAI semantic conventions for traceable autonomy decisions.

Pilot application:

- Track decision lineage, token/cost latency, and failure loops across the full autonomy stack.

## 6. Full Pilot Phased Delivery

## Phase 0 (Week 0-1): Foundation Hardening

Deliverables:

- Secret hygiene remediation and env-based config only.
- Host/feature-flag semantic unification.
- Command/skill/script reference reconciliation.
- Legacy-exempt rules codified in validators.

Exit criteria:

- P0 gaps closed.
- Forward strict mode enabled; legacy artifacts tagged exempt.

## Phase 1 (Week 1-2): Unified Autonomous Cadence

Deliverables:

- Job registry and unified scheduler controller.
- Daily/weekly loops auto-triggered without manual intervention.
- Alerting for missed cadence and stuck jobs.

Exit criteria:

- 7 consecutive days with all cadence jobs successful and auditable.

## Phase 2 (Week 2-4): Reflection-Metacog-Evolution Wiring

Deliverables:

- End-to-end event flow from reflection -> metacog -> backlog candidate generation.
- Automatic backlog triage by expected business impact and risk.
- Canary experiment queue integrated with existing promotion tooling.

Exit criteria:

- At least 2 autonomous improvement cycles executed with evidence and no safety breach.

## Phase 3 (Week 4-6): Strategy Improvement Autopilot (Guarded)

Deliverables:

- Champion-challenger orchestration for strategy/model updates.
- Risk-gated auto-promotion for low-risk classes; approval for high-risk classes.
- Rollback automation SLA and proof artifacts.

Exit criteria:

- Demonstrated net-positive pilot deltas on target KPIs with stable risk envelope.

## Phase 4 (Week 6+): Scale and Optimization

Deliverables:

- Cost/performance optimization of autonomous routing.
- Expanded skill library and memory quality controls.
- Monthly architecture scorecard and controlled expansion plan.

## 7. Legacy-Exempt Compliance Model

Policy:

- Historical artifacts are tagged `legacy_exempt=true` and excluded from block/merge gating.
- New/updated artifacts are strict-by-default.
- Exemptions are immutable-audited with timestamp + rationale + owner.

Validation behavior:

- Validators run in two views: `strict_forward` and `legacy_audit`.
- CI blocks only on forward strict failures.
- Legacy audit failures are reported as debt, not blockers.

## 8. Success Metrics (Pilot Scorecard)

Operational reliability:

- Scheduler success rate.
- Mean time to detect and recover from incidents.
- Percentage of automated loops completing without manual trigger.

Learning quality:

- Prediction calibration error trend.
- Reflection-to-action conversion rate.
- Repeat-incident recurrence rate.

Business outcomes (paper/live progression):

- Profitability consistency window compliance.
- Drawdown and risk-limit adherence.
- Signal-to-execution quality and regime resilience.

Governance:

- Approval SLA for gated changes.
- Provenance completeness and audit pass rate.

## 9. Immediate Implementation Backlog (Ordered)

1. Remove hardcoded ACP Influx token and enforce env-only secret retrieval.
2. Standardize Redis/Qdrant host resolution via shared config utility.
3. Align reflection feature-flag semantics across modules (single key model + default behavior).
4. Fix stale command/skill script references or provide canonical wrappers.
5. Correct `*_24h` KPI logic to use strict timestamp windows.
6. Implement unified job registry and migrate existing cadence scripts.
7. Wire daily reflection + metacog + skill-autonomy into autonomous cadence.
8. Add event envelope schema and producer/consumer validation tests.
9. Integrate evolution triage queue with canary/promotion gating.
10. Publish weekly pilot scorecard and go/no-go decision packet.

## 10. Source References for External Methods

- Self-RAG paper: https://arxiv.org/abs/2310.11511
- CRAG paper: https://arxiv.org/abs/2401.15884
- GraphRAG docs: https://microsoft.github.io/graphrag/index/overview/
- Reflexion paper: https://arxiv.org/abs/2303.11366
- Voyager paper: https://arxiv.org/abs/2305.16291
- AgentSquare paper: https://arxiv.org/abs/2410.06153
- Magentic-One overview: https://www.microsoft.com/en-us/research/publication/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/
- MCP spec: https://modelcontextprotocol.io/specification/
- OpenTelemetry GenAI semconv: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenAI eval best practices: https://platform.openai.com/docs/guides/evaluation-best-practices
