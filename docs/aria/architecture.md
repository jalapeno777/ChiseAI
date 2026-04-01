# Aria Memory and Personality Architecture

## Goal
Evolve the existing ChiseAI stack into a governed, stable, auditable personality and memory system.

## Architectural decision
Keep the current multi-substrate memory stack and add a deterministic governance layer on top.

## Layers
### Layer 1 — Core identity memory
Always-loaded, approval-gated memory:
- Craig profile
- Aria purpose
- soul items
- PRD objectives
- communication contract
- non-negotiable operating invariants

### Layer 2 — Governed belief memory
Evidence-based mutable beliefs:
- user preferences
- tool preferences
- workflow beliefs
- project operating beliefs
- contradiction records
- mutation audit trail

### Layer 3 — Working memory
Short/medium-lived memory:
- active task state
- session context
- temporary incidents
- experimental observations

### Layer 4 — Reflection memory
Structured synthesis outputs:
- daily reflections
- weekly reflections
- proposed promotions
- proposed deprecations
- unresolved tensions
- "top learnings" artifacts

## Final context assembly contract
A single boundary module should decide what enters Aria's live prompt context.

### Inputs
- core identity memory
- governed beliefs
- project rules
- task memory
- lessons
- recent conversation context
- retrieval scores
- freshness signals
- confidence signals

### Outputs
- deterministic ordered memory packet
- hard token budget compliance
- stale-confidence filtered context
- audit trace for why each item was included

## Required subsystems
- identity contract loader
- governed belief store wrapper
- mutation audit logger
- notification router
- context assembler
- consolidation scheduler controller
- persona regression harness
- lesson effectiveness tracker

## Boundary rules
- core identity always loads first
- stale low-confidence conflicting memory should be rejected unless explicitly requested
- approval-gated mutations cannot self-apply
- all belief changes must be auditable
- digest and urgent alerting must share one event model
