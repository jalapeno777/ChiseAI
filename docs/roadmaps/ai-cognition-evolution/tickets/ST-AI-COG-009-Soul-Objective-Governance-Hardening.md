# ST-AI-COG-009: Soul / Objective / Governance Hardening

- Story ID: `ST-AI-COG-009`
- Priority: `P1`
- Default execution mode: `autonomous` for implementation/testing, `approval-gated` for objective-state changes
- Dependencies: `ST-AI-COG-003`, `ST-AI-COG-004`, `ST-AI-COG-010`

## Owned Scope

- objective graph or soul-state runtime
- `tests/contract/test_autocog_interfaces.py`
- `tests/unit/governance/test_week1_audit_snapshot.py`

## Acceptance Evidence

- machine-readable objective-state contract exists
- governance events emitted for checks and violations
- human-readable objective artifact produced

## Validation Commands

```bash
pytest -q tests/contract/test_autocog_interfaces.py
pytest -q tests/unit/governance/test_week1_audit_snapshot.py
pytest -q tests/unit/governance/verify_memory_stewardship.py
```

## Human Approval Gate

Any objective-state or constitution change requires approval.
