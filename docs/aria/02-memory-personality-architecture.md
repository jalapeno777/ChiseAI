# Aria Memory and Personality Architecture

## 1. Architectural intent
The target architecture is an evolution of the current ChiseAI stack, not a replacement. Existing Redis, Qdrant, Serena, tempmemories, lessons, reflection loops, contradiction handling, retrieval evaluators, and governance modules remain in use.

The new architecture adds:
- a single machine-readable identity contract
- a clean split between core identity and mutable beliefs
- a unified memory query and assembly layer
- auditable belief mutation rules
- context budget enforcement
- persona drift testing
- scheduled consolidation and digesting

## 2. Memory layers

### Layer A — Core identity memory
Purpose: always-loaded, high-priority, low-mutation identity substrate.

Contains:
- Craig profile
- Aria role and purpose
- soul items
- hard project invariants
- PRD objectives that require approval to change
- communication contract with Craig
- communication contract for subagents
- approved severity model
- approved notification policy

Rules:
- loaded at every session start
- injected before any dynamic task memory
- no autonomous writes without Craig approval if a field is marked approval-gated
- stored in version-controlled markdown or yaml plus a normalized runtime representation

### Layer B — Governed belief memory
Purpose: mutable long-lived beliefs with evidence and auditability.

Contains:
- workflow beliefs
- tool preferences
- strategic preferences
- recurring coordination observations
- long-lived but non-core personal preferences
- project-level operating beliefs that do not override soul or PRD invariants

Rules:
- strongest evidence wins
- every mutation requires evidence, provenance, timestamp, and confidence
- conflicts trigger contradiction resolution
- all mutations are written to an audit log
- low/medium changes can be batched into digest
- high/critical or approval-gated changes alert immediately

### Layer C — Working memory
Purpose: task/session/short-lived operating state.

Contains:
- active task details
- recent decisions
- session-specific blockers
- temporary experiments
- transient failures
- in-progress observations

Rules:
- high churn
- TTL or scheduled archival expected
- compression/summarization preferred over indefinite retention
- eligible for promotion into governed beliefs or lessons only after evidence threshold is met

### Layer D — Reflection memory
Purpose: synthetic meta-memory produced by review loops.

Contains:
- daily reflections
- weekly reflections
- lesson candidates
- calibration summaries
- belief promotion proposals
- deprecation proposals
- contradiction summaries

Rules:
- reflection can propose changes to beliefs or lessons
- reflection cannot directly rewrite approval-gated identity fields
- reflection output should be structured and comparable over time

## 3. Core artifacts to create

### 3.1 Identity contract
Recommended file:
- `docs/aria/identity-contract.yaml`

Suggested sections:
- `craig_profile`
- `aria_identity`
- `communication_modes`
- `soul_invariants`
- `prd_invariants`
- `approval_gates`
- `severity_model`
- `notification_policy`
- `memory_priority_order`
- `evidence_resolution_policy`

### 3.2 Belief audit log
Recommended file and/or storage:
- append-only structured log, plus Redis/Qdrant metadata
- `docs/aria/audit/belief-mutations/`

Each record should include:
- belief_id
- old_state
- new_state
- mutation_type
- severity
- evidence list
- contradiction list
- initiated_by
- approval_required
- approval_status
- notification_status
- created_at

### 3.3 Unified memory interfaces
Recommended new interfaces:
- `UnifiedMemoryStore`
- `UnifiedMemoryQuery`
- `ContextAssemblyPipeline`
- `ContextBudgetManager`

Responsibilities:
- route reads and writes to correct backend
- normalize metadata across memory types
- enforce memory priority order
- filter stale or low-confidence items
- generate a final context package for Aria

## 4. Context assembly pipeline

### 4.1 Required assembly order
1. Core identity memory
2. Personal preferences
3. Project rules and architecture
4. Current task details
5. Relevant lessons
6. Historical conversation context

### 4.2 Required selection rules
- always include identity contract
- include only strongest-evidence beliefs when conflicts exist
- prefer structured summaries over raw large blobs
- exclude stale working memory unless directly relevant
- use freshness, confidence, access count, and evidence quality as ranking filters

### 4.3 Budget policy
Suggested initial per-category targets:
- identity and invariants: 15%
- preferences and beliefs: 15%
- project rules and architecture: 20%
- active task state: 30%
- lessons and reflection: 10%
- history reserve: 10%

The order above matters more than the exact percentages.

## 5. Belief mutation rules

### 5.1 Allowed autonomous changes
Aria may autonomously update non-core beliefs if:
- evidence is sufficient
- the change does not conflict with soul or PRD invariants
- contradiction resolution has either succeeded or clearly logged uncertainty

### 5.2 Approval-gated changes
Aria must pause and ask Craig before changing:
- core values
- soul items
- PRD objectives
- explicitly protected identity fields

### 5.3 Immediate alert conditions
Immediate alert is required if:
- severity is high or critical
- approval is needed
- a proposed change touches governance or identity invariants
- memory integrity or contradiction risk becomes material

## 6. Consolidation strategy

### 6.1 Rollout approach
- start with dry-run auditing
- compare proposed archive/promote actions for one week
- enable live mode conservatively
- monitor metrics and rollback triggers

### 6.2 Promotion rules
Promote a working-memory item into belief, lesson, or golden memory only when:
- repeated evidence exists
- it survived more than one session or review cycle
- it materially improves behavior or recall
- it is not contradicted by stronger evidence

### 6.3 Archive rules
Archive when:
- item is low-access and stale
- item is temporary by definition
- item has been summarized into a stronger canonical form
- item is superseded by a newer, stronger-evidence version

## 7. Persona consistency system
Aria's personality should be treated as a tested behavioral contract.

Core test dimensions:
- tone with Craig
- delegation style with subagents
- challenge vs compliance balance
- evidence-first reasoning
- risk posture
- uncertainty handling
- escalation discipline

Outputs:
- persona drift score
- scenario-level pass/fail
- benchmark deltas
- recommended remediation actions

## 8. Storage guidance

### Keep in version control
- identity contract
- governance charter
- persona benchmark cases
- approval gate rules
- notification rules
- context budget policy

### Keep in Redis/Qdrant/tempmemories
- mutable beliefs
- working memory
- reflection artifacts
- digest summaries
- runtime metrics
- retrieval data

## 9. What not to do
- do not scatter persona rules across many prompts without a canonical source
- do not let reflection directly rewrite identity invariants
- do not leave context selection entirely to ad hoc tool calls
- do not silently mutate beliefs that matter
- do not keep consolidation disabled long term
