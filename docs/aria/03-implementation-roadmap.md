# Aria Implementation Roadmap

## Goal
Upgrade Aria's memory, personality, and governance systems without replacing the current ChiseAI stack.

## Phase 0 — Baseline lock and discovery
Goal: freeze the design intent and verify exact current-state wiring.

Tasks:
1. Save this documentation pack into the repo.
2. Create an implementation branch.
3. Inventory all current persona sources, belief mutation paths, reflection outputs, and notification hooks.
4. Verify current Redis keys, Qdrant collections, tempmemory directories, and scheduler configuration.
5. Identify every code path that can mutate beliefs or lessons.

Deliverables:
- checked-in docs under `docs/aria/`
- current-state code map
- explicit implementation plan file

## Phase 1 — Governance foundation
Goal: create a single canonical contract and proper mutation governance.

Tasks:
1. Create `identity-contract.yaml`.
2. Mark approval-gated fields explicitly.
3. Create belief mutation audit schema and storage path.
4. Add notification severity mapping.
5. Add mutation guard that blocks approval-gated writes.
6. Add digest event collection format.

Deliverables:
- canonical identity contract
- mutation audit log
- approval gate middleware
- notification event schema

Exit criteria:
- no code path can silently change approval-gated fields
- every belief mutation becomes auditable
- severity calculation exists and is testable

## Phase 2 — Runtime memory wiring
Goal: unify memory access and deterministic context assembly.

Tasks:
1. Build `UnifiedMemoryQuery`.
2. Build `UnifiedMemoryStore`.
3. Build `ContextAssemblyPipeline`.
4. Build `ContextBudgetManager`.
5. Normalize metadata fields across Redis/Qdrant/tempmemories where practical.
6. Ensure identity contract is always loaded first.
7. Implement strongest-evidence conflict resolution in final assembly.

Deliverables:
- unified memory interface
- final context pack builder
- budget enforcement
- deterministic assembly order

Exit criteria:
- context assembly can be tested deterministically
- conflicting memory selection is explainable
- budget overflow causes priority-based eviction, not random loss

## Phase 3 — Consolidation and reflection hardening
Goal: stop unbounded growth and improve reflection usefulness.

Tasks:
1. Run consolidation in dry-run mode.
2. Review candidate archives and promotions.
3. Enable live consolidation conservatively.
4. Add lesson effectiveness scoring.
5. Add canonical memory promotion rules.
6. Add reflection artifact normalization.
7. Add daily and weekly reflection summaries suitable for digesting.

Deliverables:
- live consolidation scheduler
- archive/promotion reports
- lesson effectiveness tracker
- standardized reflection records

Exit criteria:
- archival and promotion happen safely on schedule
- lesson usefulness is measurable
- reflection outputs can drive promotion/deprecation decisions

## Phase 4 — Persona verification and alerting
Goal: make personality consistency measurable and notification behavior reliable.

Tasks:
1. Build golden persona scenarios.
2. Build persona regression harness.
3. Add drift scoring.
4. Wire Discord daily digest delivery.
5. Wire immediate approval/high/critical alerts.
6. Add tests for notification routing and failure handling.

Deliverables:
- persona benchmark set
- persona drift score
- Discord digest sender
- urgent alert sender

Exit criteria:
- Aria can be evaluated against canonical scenarios
- digest fires at 8:00 PM America/Toronto
- high/critical and approval-gated events alert immediately

## Phase 5 — Operationalization
Goal: make the system safe for long-term use.

Tasks:
1. Add dashboards for memory growth, consolidation, persona drift, lesson effectiveness, and notification success.
2. Add rollback playbooks for belief mutation errors and consolidation mistakes.
3. Add documentation for swarm agents on how to interact with new memory layers.
4. Add CI gates for identity contract integrity, persona tests, and mutation rules.

Deliverables:
- dashboards and alerts
- rollback docs
- CI protections
- swarm usage guidance

## Recommended implementation order inside the swarm
1. Aria plans and verifies.
2. Jarvis coordinates implementation.
3. Architect defines structures and contracts.
4. Senior Dev or Dev wires runtime modules.
5. QA validates edge cases.
6. Critic performs read-only challenge review.
7. Tech Writer updates docs and usage notes.

## Rollback triggers
Rollback or pause if:
- consolidation archives live-critical memory incorrectly
- identity contract breaks Aria session startup
- context assembly degrades decision quality materially
- notification routing causes noisy false critical alerts
- persona test scores materially regress
