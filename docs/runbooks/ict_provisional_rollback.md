# ICT Provisional Rollback Runbook

## Overview

This runbook documents the rollback procedures for the `bos_choch` feature flag when deployed in provisional mode.

**Story**: ST-ICT-036  
**Epic**: EP-ICT-008 - Real data validation epic with provisional gating  
**Last Updated**: 2026-03-26

## Rollback Decision Criteria

A rollback should be considered when:

1. **ST-ICT-033 Outcome Label**: The outcome label is NOT `provisional_pass`
2. **Feature Flag Inconsistency**: The `ict:bos_choch:enabled` flag state is inconsistent with expected provisional state
3. **Time Violation**: Any operation exceeds the 30-second rollback requirement

## Feature Flag Configuration

| Setting         | Value                   |
| --------------- | ----------------------- |
| Redis Key       | `ict:bos_choch:enabled` |
| Default Value   | `false`                 |
| Rollback Window | 30 seconds maximum      |

## Rollback Procedures

### Method 1: Automated Rollback (Recommended)

Use the `ProvisionalRollback` class for automated rollback:

```python
from src.execution.paper.provisional_rollback import create_provisional_rollback

# Create rollback handler
rollback = create_provisional_rollback()

# Execute rollback
result = rollback.rollback_in_30_seconds()

# Verify
if result.success:
    verification = rollback.verify_rollback()
    print(f"Rollback successful: {verification}")
```

### Method 2: Manual Redis Rollback

If automated rollback is unavailable:

```bash
# Connect to Redis
redis-cli -h host.docker.internal -p 6380 -n 1

# Disable the feature flag
SET ict:bos_choch:enabled false

# Verify the change
GET ict:bos_choch:enabled
```

### Method 3: Emergency Kill Switch

For critical situations requiring immediate action:

```python
# Direct feature flag disable
rollback = ProvisionalRollback()
rollback.disable_bos_choch()
```

## Verification Steps

After executing rollback, verify the system state:

1. **Check Feature Flag State**:

   ```python
   status = rollback.get_rollback_status()
   assert status['current_flag_state'] == 'false'
   ```

2. **Confirm Verification**:

   ```python
   verification = rollback.verify_rollback()
   assert verification['all_checks_passed'] == True
   ```

3. **Monitor System Health**:
   - Check system logs for any errors
   - Verify no pending transactions are affected
   - Confirm service health endpoints return expected values

## Rollback Time Requirements

| Step                 | Maximum Time |
| -------------------- | ------------ |
| Feature flag disable | 5 seconds    |
| State verification   | 5 seconds    |
| Total rollback       | 30 seconds   |

## Decision Flowchart

```
Start
  │
  ▼
Check outcome_label
  │
  ├── If NOT provisional_pass ──────┐
  │                                 │
  ▼                                 ▼
Check flag state              Consider Rollback
  │
  ├── If flag is inconsistent ──────┐
  │                                 │
  ▼                                 ▼
Execute rollback in <30s      Document decision
  │
  ▼
Verify success
  │
  ├── If success ─────► Mark complete
  │
  └── If failure ──────► Escalate
```

## Rollback Decision Criteria (Documented)

Based on ST-ICT-036 acceptance criteria:

1. **Provisional Pass Only**: ST-ICT-033 requires outcome_label to be `provisional_pass` for provisional deployment to continue
2. **30-Second Capability**: Rollback must complete within 30 seconds per AC-3
3. **Feature Flag Disable**: The `disable_bos_choch()` method sets `ict:bos_choch:enabled=false` in Redis
4. **Decision Documentation**: All rollback decisions must be documented with reason

## Contact Information

For issues or escalations:

- **Primary**: On-call engineer
- **Secondary**: Platform team lead
- **Escalation**: Engineering manager

## Related Documentation

- [EP-ICT-008 Epic](../epics/EP-ICT-008.md)
- [ST-ICT-033 Story](../stories/ST-ICT-033.md)
- [Bos Choch Feature Flag](../features/bos_choch.md)
