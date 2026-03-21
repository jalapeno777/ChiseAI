---
name: "chise-validate-status-sync"
description: "ChiseAI: validate status file synchronization (docs/bmm-workflow-status.yaml matches implementations)."
disable-model-invocation: true
---

Validate that docs/bmm-workflow-status.yaml is synchronized with actual implementation state.

## Prerequisites
- Python 3.11+
- scripts/validate_status_sync.py exists

## Execution

```bash
python3 scripts/validate_status_sync.py
```

## Success Criteria
- Exit code 0
- No output = valid
- Warnings displayed but don't fail

## Failure Handling

If validation fails:
1. Review output for mismatched stories
2. Update `docs/bmm-workflow-status.yaml` and, when status semantics/evidence mappings changed, co-update `docs/validation/validation-registry.yaml`
3. Re-run this command
4. Only then proceed with commit/PR

## CI Integration

This validation runs automatically in Woodpecker for all PRs.
