# First Sprint Contract: ST-AI-COG-005

## Worker Slices

### Worker A

- ownership keys:
  - `src:strong_system:belief_search`
  - `scripts:governance:retrieval`
- scope globs:
  - `src/strong_system/belief_embeddings/search.py`
  - `scripts/governance/retrieval_baseline.py`
  - `tests/unit/governance/test_retrieval_baseline.py`

### Worker B

- ownership keys:
  - `src:governance:qdrant_health`
  - `src:governance:memory_stewardship`
- scope globs:
  - `src/governance/memory/**`
  - `tests/unit/governance/test_qdrant_health.py`
  - `tests/unit/governance/test_memory_stewardship.py`

### Worker C

- ownership keys:
  - `src:governance:reflection`
  - `bmad-output:autocog:retrieval`
- scope globs:
  - `tests/unit/governance/test_reflection.py`
  - `tests/unit/governance/test_reflection_standalone.py`
  - `_bmad-output/autocog/retrieval/**`
