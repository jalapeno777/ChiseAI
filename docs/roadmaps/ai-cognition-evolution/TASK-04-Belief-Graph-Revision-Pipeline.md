# TASK-04: Belief Graph & Revision Pipeline

## Summary

Turn beliefs into a durable graph-backed system with contradiction detection, revision eligibility, explanation artifacts, and escalation for uncertain or high-impact changes.

## Why This Is Necessary

If the system cannot represent and revise its own beliefs safely, it cannot truly reason across time. It only reacts.

## Scope

- `src/autonomous_cognition/beliefs/*`
- graph storage integration
- revision artifacts
- contradiction and supersession lineage

## Deliverables

1. belief entities with relation graph,
2. contradiction groups and causal/evidence links,
3. revision packets with rationale and diff,
4. blocked revision queue for human or orchestrator review.

## Best Practices

- separate observation from belief from policy,
- track evidence recency and source family,
- preserve superseded beliefs for audit,
- prefer escalation over confident weak revision.

## Hardening Requirements

- immutable revision history,
- no destructive overwrite of old beliefs,
- high-impact revisions require approval,
- low-evidence auto-revisions forbidden.

## Telemetry

- `belief_active_total`
- `belief_conflict_total`
- `belief_revision_applied_total`
- `belief_revision_blocked_total`
- `belief_source_diversity_score`

## Quantified Success

- `100%` of revisions carry evidence refs,
- `0` hidden supersessions,
- blocked-revision reasons categorized and reportable,
- contradiction recurrence trend decreases over time.

## Testing

- unit: evidence scoring, threshold gating, supersession lineage
- integration: conflict detection -> revision packet -> store -> notification
- adversarial: LLM-only evidence, stale evidence, single-source evidence

## Research Links

- GraphRAG: https://arxiv.org/abs/2404.16130
- Constitutional AI: https://arxiv.org/abs/2212.08073

## Swarm Notes

Belief graph should become a first-class source in reasoning and post-mortem analysis, not just a side store.
