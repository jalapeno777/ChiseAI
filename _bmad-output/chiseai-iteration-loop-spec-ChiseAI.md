---
workflow: chiseai-iteration-loop
project: ChiseAI
started: 2026-02-07
stepsCompleted: [1, 2, 3, 4, 5, 6]
---

# ChiseAI Iteration Loop Spec

## Purpose

Define the iterative implementation loop for ChiseAI with forced AGENTS.md scans, acceptance criteria locking, Redis iteration logs (TTL 5 days), and memory promotion rules.

## Scope

- Applies to Opencode agents and BMAD orchestrators
- Integrates with AGENTS.md and Redis
- Complements, but does not replace, validation registry gates

## MEM-SCAN: AGENTS.md Discovery Rules

**Trigger:** Before any edits, and after first file open within a new folder.

**Procedure:**
- Locate the nearest `AGENTS.md` by walking upward from the target file path.
- If none exists in the subtree, check repository root `AGENTS.md`.
- Record which `AGENTS.md` files were read in the iteration log.

**Opencode Behavior:**
- Do not edit files until MEM-SCAN is complete.
- If guidance conflicts, prefer folder-local AGENTS.md over root.

## Acceptance Criteria Lock (Pre-Work)

**Rule:** Each story must define acceptance criteria *before* implementation begins.

**Purpose:** Provide verifiable completion signals for the iteration loop. This is separate from `docs/validation/validation-registry.yaml`, which remains the final gate.

**Minimum Requirements:**
- Each criterion maps to one verification action (test, script, or manual check).
- Criteria must be specific, measurable, and binary (pass/fail).
- Each story must declare a `story_size` that fits in one iteration.

**Template:** Use `{acceptanceTemplate}` as the default structure.

## Redis Iteration Log (5-Day TTL)

**Primary Keys:**
- `bmad:chiseai:iterlog:story:<story_id>` (HASH) - latest snapshot
- `bmad:chiseai:iterlog:story:<story_id>:history` (LIST) - JSON entries
- `bmad:chiseai:iterlog:story:<story_id>:incidents` (LIST) - incident entries (append-only)

**Indexes:**
- `bmad:chiseai:iterlog:path:<path_slug>` (SET of story_ids)
- `bmad:chiseai:iterlog:agent:<agent_id>` (SET of story_ids)

**TTL:**
- Apply `EXPIRE 432000` (5 days) to all iterlog keys.
- Refresh TTL on each update.

**Path Slugging:**
- Use repo-relative path
- Lowercase; replace `/` with `:`
- Example: `src/neuro_symbolic/evolution` -> `src:neuro_symbolic:evolution`

**Iteration Entry Template:** `{iterationTemplate}`

**Lookup Flow:**
1) By story: `GET/HGETALL bmad:chiseai:iterlog:story:<story_id>`
2) By path: `SMEMBERS bmad:chiseai:iterlog:path:<path_slug>` -> story_ids -> read story hash
3) By agent: `SMEMBERS bmad:chiseai:iterlog:agent:<agent_id>` -> story_ids

## Scope Ownership (Parallel Safety)

**Goal:** prevent silent scope overlap when multiple agents execute in parallel.

**Preferred ownership key:**
- `bmad:chiseai:ownership` (HASH)
  - key: `<path_slug>` (example: `src:neuro_symbolic:evolution`)
  - value: `<story_id>/<agent>/<timestamp>`

**Rule:**
- Jarvis assigns ownership before delegating execution.
- Executors check ownership before editing; if owned by a different story/agent, they must STOP and report back.

## Memory Promotion Rules

**Tier 1: Iteration Log (Redis)**
- Default sink for learnings during a story loop.
- Expires in 5 days unless refreshed.

**Tier 2: AGENTS.md (Local Context Memory)**
Promote from iteration log when the learning is:
- Folder-specific and likely to recur
- A constraint, invariant, or known hazard
- A local test/command requirement

**Tier 3: Qdrant (Long-Term Decisions/Patterns)**
Promote when the learning:
- Affects multiple subsystems
- Represents a design decision or anti-pattern
- Must persist beyond a sprint

**Promotion Trigger:**
- At story completion, assess iteration log for promotion candidates.
- Record promoted items and destinations in the iteration log entry.

## Completion

The ChiseAI iteration loop workflow spec is complete. Use this workflow to enforce MEM-SCAN, acceptance criteria lock, Redis iteration logging, and memory promotion across Opencode agents and BMAD orchestrators.
