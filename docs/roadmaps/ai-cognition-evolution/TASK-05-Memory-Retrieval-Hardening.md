# TASK-05: Memory & Retrieval Hardening

## Summary

Eliminate weak production fallbacks and implement measurable hybrid retrieval across Redis, Qdrant, and graph/lexical layers.

## Why This Is Necessary

Long-horizon reasoning depends on retrieving the right evidence. Weak retrieval makes the system look intelligent in architecture but brittle in operation.

## Scope

- tempmemory ingestion and migration paths
- belief embedding and search paths
- retrieval benchmarks and reranking
- production-mode contracts

## Deliverables

1. production retrieval contract,
2. vector + lexical + graph retrieval pipeline,
3. reranking layer,
4. retrieval benchmark corpus and score reports,
5. explicit prod-mode failure behavior.

## Best Practices

- evaluate retrieval on real ChiseAI artifacts,
- benchmark by task type: incident, strategy, calibration, belief, governance,
- prefer idempotent writes,
- separate online retrieval latency budget from offline indexing.

## Hardening Requirements

- no silent in-memory fallback in production mode,
- idempotent Qdrant writes,
- explicit degraded state and alerts,
- dedup bug fixed before re-enabling daily sweep.

## Telemetry

- `retrieval_request_total`
- `retrieval_hit_rate_top1`
- `retrieval_hit_rate_top5`
- `retrieval_latency_ms`
- `memory_daily_sweep_state`
- `memory_fallback_total`

## Quantified Success

- top-5 evidence hit rate `>85%`,
- p95 retrieval latency `<250ms`,
- production fallback rate `0`,
- daily sweep runs clean for `14` consecutive days before considered stable.

## Testing

- benchmark suite with labeled expected evidence,
- failover tests,
- duplicate write tests,
- daily sweep regression suite on dedup edge cases.

## Research Links

- GraphRAG: https://arxiv.org/abs/2404.16130
- Toolformer: https://arxiv.org/abs/2302.04761

## Swarm Notes

This task should produce a retrieval scorecard artifact on every meaningful retrieval change.
