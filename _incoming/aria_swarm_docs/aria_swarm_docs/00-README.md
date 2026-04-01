# Aria Swarm Documentation Pack

This pack is the reference set for formalizing Aria's personality, memory, reflection, belief mutation, retrieval, and notification systems inside the OpenCode harness.

## Recommended reading order
1. `01-aria-governance-charter.md`
2. `02-memory-personality-architecture.md`
3. `03-implementation-roadmap.md`
4. `04-data-models-and-flows.md`
5. `05-persona-consistency-test-spec.md`
6. `06-discord-digest-and-alerting-spec.md`
7. `07-acceptance-criteria.md`
8. `08-prompts-for-aria.md`

## What this pack assumes
- The existing ChiseAI stack stays in place.
- Redis, Qdrant, Serena, tempmemories, reflection loops, contradiction handling, retrieval evaluation, and lessons remain part of the architecture.
- The system is upgraded, not replaced.
- Aria stays the primary orchestrator and Jarvis remains the default execution/delegation path unless Craig explicitly requests Aria-direct behavior.

## Main build goals
- Stabilize Aria's personality and behavior.
- Separate core identity memory from normal mutable beliefs.
- Make belief changes evidence-based, auditable, and properly gated.
- Add a real context assembly and context budget system.
- Enable safe consolidation/archival instead of unbounded growth.
- Add persona drift tests and lesson effectiveness scoring.
- Add daily digest plus urgent Discord alerting.

## File map
- `01-aria-governance-charter.md` — final approved policy and operating rules.
- `02-memory-personality-architecture.md` — target runtime architecture.
- `03-implementation-roadmap.md` — rollout plan by phase.
- `04-data-models-and-flows.md` — schemas, state flow, and mutation rules.
- `05-persona-consistency-test-spec.md` — persona benchmark and drift test system.
- `06-discord-digest-and-alerting-spec.md` — notification logic and payload rules.
- `07-acceptance-criteria.md` — done criteria for each major feature.
- `08-prompts-for-aria.md` — operational prompts Craig can hand to Aria.

## Suggested location in repo
Suggested long-term placement in the ChiseAI repo:
- `docs/aria/00-README.md`
- `docs/aria/01-aria-governance-charter.md`
- `docs/aria/02-memory-personality-architecture.md`
- `docs/aria/03-implementation-roadmap.md`
- `docs/aria/04-data-models-and-flows.md`
- `docs/aria/05-persona-consistency-test-spec.md`
- `docs/aria/06-discord-digest-and-alerting-spec.md`
- `docs/aria/07-acceptance-criteria.md`
- `docs/aria/08-prompts-for-aria.md`
