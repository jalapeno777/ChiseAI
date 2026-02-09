---
project: ChiseAI
scope: opencode-agents
type: iterlog
story_id: CH-AGENTS-003
story_title: "Harden parallel delegation rules between Aria and Jarvis"
phase: implementation
status: in_progress
started_at: "2026-02-09T15:31:01Z"
needs_manual_qdrant_import: true
mem_scan:
  - AGENTS.md
  - .opencode/agent/Aria.md
  - .opencode/agent/Jarvis.md
  - .opencode/agent/Dev.md
  - .opencode/agent/Quickdev.md
  - .opencode/agent/SeniorDev.md
acceptance_criteria:
  - "AC1: Aria delegation guidance requires an explicit parallelization plan (scope + locks + deps) before spawning multiple Jarvis tasks."
  - "AC2: Jarvis guidance defines 'parallel-safe' vs 'sequential' categories and requires a task contract per worker (allowed scope, no-overlap) and an integration/merge ordering."
  - "AC3: Executor agents (dev/quickdev/senior-dev) are updated to follow the task contract and to stop/escalate if asked to edit outside declared scope or when conflicts are detected."
  - "AC4: Guidance calls out global-lock files/areas (CI/infra/shared invariants) as sequential-by-default."
  - "AC5: Repo passes `python3 scripts/validate_iterloop_compliance.py --story-id=CH-AGENTS-003`."
---

## Decisions
- Redis/Qdrant MCPs are not available in this runtime; record decisions/learnings here for later manual import.
- Use an explicit delegation contract (`SCOPE_GLOBS`, `LOCKS_REQUIRED`, `depends_on`, sequential batches) to make "parallel when safe" enforceable in prompts.
- Treat CI/infra/governance/core-safety as "global-lock" scope: sequential-by-default with stricter verification.
- Add `.envrc` to `.gitignore` and provide `.envrc.example` (placeholders only) to prevent recurring "dirty tree from local env" issues.
- Make memory reuse enforceable by requiring a `MEMORY_CONTEXT` block in every executor delegation and an `INCIDENT_TEMPLATE` for conflicts/regressions (so learnings become structured and promotable).

## Learnings
- TBD

## Evidence
- `python3 scripts/validate_iterloop_compliance.py --story-id=CH-AGENTS-003` passed.
- Updated agent instruction files:
  - `.opencode/agent/Aria.md`
  - `.opencode/agent/Jarvis.md`
  - `.opencode/agent/Dev.md`
  - `.opencode/agent/Quickdev.md`
  - `.opencode/agent/SeniorDev.md`
  - Added a concrete batch-table template in `.opencode/agent/Jarvis.md` and a review checklist in `.opencode/agent/Aria.md`.
