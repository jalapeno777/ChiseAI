# ST-AI-COG-004: Belief Graph & Revision Pipeline

- Story ID: `ST-AI-COG-004`
- Priority: `P0`
- Default execution mode: `autonomous` except high-impact revisions
- Dependencies: `ST-AI-COG-005`, `ST-AI-COG-010`

## Owned Scope

- `src/autonomous_cognition/beliefs/revision_engine.py`
- `src/strong_system/belief_embeddings/`
- `tests/contract/test_autocog_interfaces.py`
- `tests/unit/governance/test_notifications/test_formatters.py`

## Acceptance Evidence

- contradiction groups and revision packets exist
- supersession lineage retained
- blocked revision queue present
- evidence refs carried in artifacts

## Validation Commands

```bash
pytest -q tests/contract/test_autocog_interfaces.py
pytest -q tests/unit/governance/test_notifications/test_formatters.py
pytest -q tests/test_governance/test_reflection_llm_conformance.py
```

## Human Approval Gate

Protected live-policy revisions require approval.
