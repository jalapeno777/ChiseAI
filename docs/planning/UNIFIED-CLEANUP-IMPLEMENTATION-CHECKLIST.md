# Unified Cleanup Plan - Implementation Checklist

Last updated: 2026-03-17  
Owner: Aria/Jarvis governance update stream  
Scope: `AGENTS.md` + `.opencode/agent/*.md` policy alignment

## Objective

Align swarm orchestration with the canonical workflow:
- plan-first execution
- strict escalation ladder `2/2/2/3`
- critic-per-task review and max two remediation rounds
- autonomous root-cause bug fixing
- lessons capture/readback loop
- soft deprecation of fast-agent default routing

## Phase 0 - Baseline and Drift Inventory

- [x] Capture current contradictions across policy files.
  - Files: `AGENTS.md`, `.opencode/agent/Aria*.md`, `.opencode/agent/Jarvis*.md`, `.opencode/agent/*dev*.md`, `.opencode/agent/Merlin.md`, `.opencode/agent/Critic.md`, `.opencode/agent/README.md`
- [x] Build a mismatch table with line references for:
  - escalation threshold mismatches
  - routing mismatches
  - completion gate mismatches
  - fast-agent routing references
- [x] Freeze baseline snapshot in `docs/tempmemories/` for rollback traceability.

## Phase 1 - Canonical Policy and Contracts

- [x] Update `AGENTS.md` as canonical source of truth for:
  - `quickdev` handles all 1SP
  - `dev` handles >1SP up to 3SP
  - escalation: `quickdev(2) -> dev(2) -> senior-dev(2) -> merlin(3) -> Aria blockers`
  - plan gate, replan gate, proof gate, bugfix autonomy, critic/remediation loop, lessons loop
- [x] Define required escalation metadata schema:
  - `attempt_count`
  - `escalation_from`
  - `escalation_reason`
  - `evidence_ref`
- [x] Define required completion evidence schema:
  - commands run
  - tests run + results
  - logs checked + findings
  - AC-to-evidence mapping
  - residual risk
  - no-test justification when applicable

## Phase 2 - Aria/Jarvis Orchestrator Alignment

- [x] Update `.opencode/agent/Aria.md` with explicit:
  - `PLAN_APPROVED=true` requirement before implementation
  - replan triggers and stop conditions
  - two-remediation cap with blocker return to Aria
  - lessons read-at-start / write-at-close enforcement
- [x] Update `.opencode/agent/AriaRuntime.md` with matching constraints.
- [x] Update `.opencode/agent/Jarvis.md` with:
  - strict `2/2/2/3` escalation
  - mandatory escalation metadata in handoff packets
  - critic-per-task parallel review contract
  - max two remediation rounds
  - autonomous bug-fix workflow contract
- [x] Update `.opencode/agent/JarvisRuntime.md` to mirror above behavior.

## Phase 3 - Worker Contract Alignment

- [x] Update `.opencode/agent/Quickdev.md`:
  - enforce max 2 passes before escalation to `dev`
- [x] Update `.opencode/agent/Dev.md`:
  - enforce max 2 passes before escalation to `senior-dev`
- [x] Update `.opencode/agent/SeniorDev.md`:
  - enforce max 2 passes before escalation to `merlin`
- [x] Update `.opencode/agent/Merlin.md`:
  - enforce max 3 passes before blocker return to Aria
- [x] Update `.opencode/agent/Critic.md`:
  - explicit task-level review output contract for remediation routing

## Phase 4 - Fast-Agent Soft Deprecation

- [x] Remove `quickdev-fast` from default Jarvis/JarvisRuntime routing tables.
- [x] Mark `.opencode/agent/QuickdevFast.md` as soft-deprecated fallback-only.
- [x] Decide and document whether `.opencode/agent/Juniordev.md` is:
  - fallback-only, or
  - soft-deprecated with same process
- [x] Update `.opencode/agent/README.md` routing matrix to reflect soft deprecation.

## Phase 5 - Lessons Loop Operationalization

- [x] Ensure `docs/tempmemories/lessons.md` exists with normalized rule format.
- [x] Add guidance for `LESSON_CANDIDATE` emission from workers.
- [x] Add Jarvis single-writer dedupe/append rule at session close.
- [x] Add start-of-session requirement for relevant lesson retrieval.

## Phase 6 - Machine-Checkable Hardening

- [x] Add a policy consistency checker script.
  - Suggested path: `scripts/validate_swarm_policy_consistency.py`
- [x] Validate no contradictions in escalation/routing/evidence rules across files.
- [x] Wire checker into CI and pre-commit (where appropriate).
- [x] Add budget guardrails to orchestrator contracts:
  - `max_total_attempts`
  - `max_wall_clock_minutes`
  - `max_token_budget`

## Phase 7 - Scenario Validation (Dry Runs)

- [x] Scenario A: 1SP happy path via `quickdev`.
- [x] Scenario B: quickdev fails twice -> escalates to dev.
- [x] Scenario C: dev fails twice -> escalates to senior-dev.
- [x] Scenario D: senior-dev fails twice -> escalates to merlin.
- [x] Scenario E: merlin fails three times -> returns blocker packet to Aria.
- [x] Scenario F: critic identifies defects -> remediation round 1 -> re-review.
- [x] Scenario G: round 2 remediation -> unresolved -> return blockers to Aria.

## Phase 8 - Cutover and Cleanup

- [x] Pilot the policy on one active story.
- [x] Confirm metrics and behavior stability.
- [x] Announce policy cutover in `AGENTS.md` and `.opencode/agent/README.md`.
- [x] After transition period, schedule removal of fully deprecated fast-agent routing references.

## Acceptance Criteria

- [x] No remaining references to legacy 5-attempt escalation for generic blocker routing.
- [x] All orchestrators enforce `PLAN_APPROVED=true` before implementation.
- [x] Escalation behavior matches `2/2/2/3` in all relevant files.
- [x] Critic-per-task review and max two remediation rounds are enforced.
- [x] Completion reports include required tests/log/evidence fields.
- [x] Lessons are read at start and written at close for each session.
- [x] CI policy checker blocks contradictory policy changes.
