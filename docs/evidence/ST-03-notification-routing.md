# ST-03 Notification Routing and Severity Matrix

## Summary

This evidence documents the PR-local story `ST-03` for the notification routing
and severity matrix work behind PR #891.

### Scope

- Policy-driven notification routing for governance and belief mutation events
- Shared severity mapping for low/medium/high/critical routing
- Immediate alerts for approval requests and critical paths
- Daily digest fallback for lower-severity events

### Implemented Files

- `src/autonomous_cognition/beliefs/audit_writer.py`
- `src/autonomous_cognition/beliefs/__init__.py`
- `src/governance/notifications/event_router.py`
- `src/governance/notifications/severity_mapper.py`
- `src/governance/notifications/__init__.py`
- `tests/unit/autonomous_cognition/beliefs/test_audit_writer.py`
- `tests/unit/governance/notifications/test_event_router.py`
- `tests/unit/governance/notifications/test_severity_mapper.py`

### Verification

- `pytest -q tests/unit/autonomous_cognition/beliefs/test_audit_writer.py tests/unit/governance/notifications`
- `python3 scripts/ci/pre_push_gate.py`

### Result

- 34 tests passed
- Local pre-push gate passed
- Story registered in `docs/bmm-workflow-status.yaml` as `ST-03`

