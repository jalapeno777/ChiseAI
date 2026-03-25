# ST-AI-COG-005: Memory & Retrieval Hardening

- Story ID: `ST-AI-COG-005`
- Priority: `P0`
- Default execution mode: `autonomous`
- Dependencies: `ST-AI-COG-010`

## Owned Scope

- `src/strong_system/belief_embeddings/search.py`
- governance memory and Qdrant health paths
- `tests/unit/governance/test_retrieval_baseline.py`
- `tests/unit/governance/test_qdrant_health.py`
- `tests/unit/governance/test_memory_stewardship.py`

## Acceptance Evidence

- explicit production retrieval contract
- degraded-state handling visible
- retrieval benchmark report generated
- no silent in-memory production fallback

## Validation Commands

```bash
pytest -q tests/unit/governance/test_retrieval_baseline.py
pytest -q tests/unit/governance/test_qdrant_health.py
pytest -q tests/unit/governance/test_memory_stewardship.py
```

## Human Approval Gate

Implementation is autonomous unless changing protected live retrieval policy.
