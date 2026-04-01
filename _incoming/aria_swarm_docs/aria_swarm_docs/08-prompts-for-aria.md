# Prompts for Aria

Use these prompts in order. Each prompt assumes Aria remains planning/verification only and routes execution through Jarvis and the swarm unless Craig explicitly says otherwise.

---

## Prompt 1 — Create the implementation dossier and code map
Use this if you want Aria to regenerate or verify the current-state inventory before implementation.

```text
You are Aria. Review the repo and produce a current-state implementation dossier for memory, personality, beliefs, reflection, retrieval, consolidation, and notifications.

Rules:
- inspect the actual repo state, not assumptions
- cite exact file paths, classes, functions, keys, collections, scripts, feature flags, env vars, and schedulers where possible
- clearly mark UNKNOWN when something cannot be proven
- do not implement yet
- do not ask Craig questions unless you are blocked by a missing policy decision

Return sections for:
1. current persona sources
2. current memory backends and schemas
3. current belief mutation paths
4. current reflection loops
5. current retrieval and context assembly
6. current scheduler state
7. current notification hooks
8. gaps against docs/aria/01-aria-governance-charter.md and docs/aria/02-memory-personality-architecture.md
9. recommended implementation order
10. exact files likely to change
```

---

## Prompt 2 — Create the implementation plan from the approved docs
Use this once the docs are checked in.

```text
You are Aria. Using the approved docs under docs/aria/, create a precise implementation plan for the swarm.

Required inputs:
- docs/aria/01-aria-governance-charter.md
- docs/aria/02-memory-personality-architecture.md
- docs/aria/03-implementation-roadmap.md
- docs/aria/04-data-models-and-flows.md
- docs/aria/05-persona-consistency-test-spec.md
- docs/aria/06-discord-digest-and-alerting-spec.md
- docs/aria/07-acceptance-criteria.md

Rules:
- do not rewrite the approved policy
- identify exact files to create or modify
- split work into swarm-executable chunks
- route execution through Jarvis unless Craig explicitly authorizes otherwise
- include tests, rollback steps, and acceptance criteria per chunk
- surface conflicts with current implementation early

Return:
1. proposed phases
2. file-by-file change list
3. implementation order
4. risks
5. needed migrations
6. test plan
7. rollback plan
8. anything blocked and why
```

---

## Prompt 3 — Build Phase 1 governance foundation
```text
You are Aria. Execute planning and verification for Phase 1 only: governance foundation.

Scope:
- create a canonical identity contract
- define approval-gated fields
- add belief mutation audit schema
- define notification event schema
- identify and harden belief mutation guard points

Rules:
- no scope creep beyond Phase 1
- route implementation through Jarvis and relevant workers
- require exact file diffs and exact test additions
- ensure no protected field can be changed silently
- ensure docs and code stay aligned

Return:
1. task breakdown for Jarvis and workers
2. exact files to create/modify
3. tests required
4. edge cases
5. acceptance checklist
```

---

## Prompt 4 — Build Phase 2 runtime memory wiring
```text
You are Aria. Execute planning and verification for Phase 2 only: runtime memory wiring.

Scope:
- UnifiedMemoryQuery
- UnifiedMemoryStore
- ContextAssemblyPipeline
- ContextBudgetManager
- deterministic final context assembly
- strongest-evidence conflict handling in assembly

Rules:
- preserve existing backends where possible
- do not replace the whole stack
- keep identity contract always-loaded and non-evictable
- align budget order to docs/aria/01-aria-governance-charter.md

Return:
1. file-by-file implementation plan
2. data normalization plan
3. ranking and eviction rules
4. tests required
5. rollback/fallback plan
```

---

## Prompt 5 — Build Phase 3 consolidation and reflection hardening
```text
You are Aria. Execute planning and verification for Phase 3 only: consolidation and reflection hardening.

Scope:
- stage consolidation rollout from dry-run to live
- lesson effectiveness scoring
- promotion and deprecation rules
- reflection artifact normalization
- archive safety and rollback

Rules:
- default to conservative rollout
- require observability and rollback before enabling live archival
- do not destroy memory when summarization or archival would suffice

Return:
1. rollout steps
2. metrics and alerts
3. exact files/configs affected
4. tests and dry-run checks
5. rollback triggers
```

---

## Prompt 6 — Build Phase 4 persona testing and Discord notifications
```text
You are Aria. Execute planning and verification for Phase 4 only: persona testing and Discord notifications.

Scope:
- golden persona benchmark suite
- persona drift score
- daily digest delivery at 8:00 PM America/Toronto
- immediate alerts for high/critical and approval requests
- notification reliability and retries

Rules:
- persona tests must verify both Craig-facing and subagent-facing behavior
- approval-gated events must alert immediately
- scheduling must use America/Toronto timezone logic

Return:
1. benchmark scenario set
2. notification flow design
3. exact files and services affected
4. test plan
5. operational failure handling
```

---

## Prompt 7 — Ask Aria for a gap report against the approved docs
Use this if implementation starts drifting.

```text
You are Aria. Compare the current repo state against the approved docs in docs/aria/ and produce a strict gap report.

Rules:
- do not smooth over missing pieces
- clearly separate implemented, partial, missing, and inconsistent
- cite exact file paths and evidence
- include any areas where code behavior conflicts with the approved docs

Return a table with:
- requirement
- source doc
- current status
- evidence
- severity
- recommended fix
```

---

## Prompt 8 — Ask Aria for a final readiness review before merge
```text
You are Aria. Perform a final readiness review for the Aria memory/personality/governance upgrade.

Check against:
- docs/aria/01-aria-governance-charter.md
- docs/aria/02-memory-personality-architecture.md
- docs/aria/03-implementation-roadmap.md
- docs/aria/04-data-models-and-flows.md
- docs/aria/05-persona-consistency-test-spec.md
- docs/aria/06-discord-digest-and-alerting-spec.md
- docs/aria/07-acceptance-criteria.md

Verify:
- policy alignment
- approval gate correctness
- belief mutation auditability
- context assembly correctness
- consolidation safety
- lesson effectiveness tracking
- persona test coverage
- Discord digest and urgent alert behavior
- rollback readiness

Return:
1. go/no-go recommendation
2. unresolved issues
3. regressions or drift risks
4. required follow-ups before merge
```

---

## Prompt 9 — Ask Aria to generate the identity contract file content
```text
You are Aria. Based on docs/aria/01-aria-governance-charter.md and docs/aria/04-data-models-and-flows.md, generate the initial canonical identity-contract.yaml for review.

Rules:
- do not invent new policy beyond the approved docs
- mark unknown project-specific invariant values clearly if they still need repo-specific fill-in
- keep the structure machine-readable and stable
- include approval-gated fields explicitly

Return only:
1. proposed yaml
2. short notes on any fields that need repo-specific completion
```

---

## Prompt 10 — Ask Aria to prepare exact swarm delegation prompts
```text
You are Aria. Using docs/aria/03-implementation-roadmap.md and docs/aria/07-acceptance-criteria.md, prepare exact delegation prompts for Jarvis and the worker agents for the next implementation phase.

Rules:
- one prompt per worker role
- each prompt must have scope, constraints, required outputs, tests, and handoff format
- keep prompts concise and execution-ready
- do not delegate questions to Craig unless a true approval gate is hit

Return:
1. Jarvis prompt
2. architect prompt
3. senior-dev/dev prompt
4. qa prompt
5. critic prompt
6. tech-writer prompt
```
