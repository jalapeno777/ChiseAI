# Task Decomposition Sentinel

**Story:** ST-GOV-003
**Phase:** Week 1 Batch 1B
**Status:** In Progress

## Overview

The Task Decomposition Sentinel enforces task size limits and requires approval for oversized tasks. This prevents scope creep and ensures tasks remain decomposable and actionable.

## Behavior Specification

### Core Functionality

| Function | Behavior |
|----------|----------|
| `validate_task_size(task)` | Returns `ValidationResult` indicating if task is valid or requires approval |
| `requires_decomposition(task)` | Returns `True` if task should be split into smaller tasks |
| `get_pending_approvals()` | Returns list of tasks awaiting decomposition approval |
| `request_approval(task, justification)` | Submits approval request for oversized task |
| `approve_task(task_id, approver)` | Records approval for blocked task |

### Task Size Rules

| Story Points | Action |
|--------------|--------|
| 1-5 SP | ✅ Valid - No action required |
| 6-8 SP | ⚠️ Warning - Decomposition recommended |
| 9+ SP | 🚫 Blocked - Approval required |

### Feature Flag

- **Key:** `chise:feature_flags:governance:task_sentinel_active`
- **Default:** `false` (disabled)
- **Rollout:** Enable per environment after validation

### Configuration

```python
SentinelConfig(
    max_story_points=5,           # Threshold for approval requirement
    approval_timeout_hours=24,    # Hours before approval expires
    require_justification=True,   # Require reason for oversized tasks
    blocked_task_ttl_days=7,      # Days to keep blocked task records
    redis_prefix="chise:governance:sentinel"
)
```

## Integration Points

### Redis Keys

| Key Pattern | Purpose |
|-------------|---------|
| `chise:feature_flags:governance:task_sentinel_active` | Feature flag |
| `chise:governance:sentinel:pending_approvals` | Approval queue |
| `chise:governance:sentinel:blocked:{task_id}` | Blocked task records |
| `chise:governance:sentinel:approvals:{task_id}` | Approval records |

### API Integration (Future)

```python
# Integration with task creation hooks
@task_created.connect
def validate_on_create(task):
    sentinel = TaskSentinel(redis_client=redis)
    result = sentinel.validate_task_size(task)
    if result.requires_approval:
        notify_approvers(task, result)
        block_task(task)
```

## Approval Workflow

1. **Task Created:** Sentinel validates size
2. **Oversized Detected:** Task blocked, notification sent
3. **Justification Submitted:** Request logged with reason
4. **Approver Review:** Approver reviews and decides
5. **Resolution:**
   - **Approved:** Task unblocked, audit trail created
   - **Decomposition Required:** Task split, children inherit constraints
   - **Rejected:** Task must be decomposed

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Redis unavailable | Sentinel disabled, tasks proceed |
| Feature flag missing | Disabled by default |
| Approval timeout | Task auto-decomposes or rejected |

## Testing Strategy

- **Unit Tests:** Core validation logic
- **Integration Tests:** Redis feature flag integration
- **E2E Tests:** Full approval workflow
- **Load Tests:** High-volume task creation

## Metrics & Observability

| Metric | Description |
|--------|-------------|
| `sentinel.tasks.validated` | Total tasks validated |
| `sentinel.tasks.blocked` | Tasks requiring approval |
| `sentinel.approvals.granted` | Approvals granted |
| `sentinel.approvals.rejected` | Approvals rejected |
| `sentinel.approvals.timeout` | Expired approvals |

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Core classes | ✅ Skeleton | `TaskSentinel`, `SentinelConfig`, `TaskInfo` |
| `validate_task_size()` | ✅ Implemented | Basic threshold check |
| `is_enabled()` | ✅ Implemented | Feature flag integration |
| `requires_decomposition()` | ⏳ Stub | TODO: Pattern analysis |
| `get_pending_approvals()` | ⏳ Stub | TODO: Redis queue query |
| `request_approval()` | ⏳ Stub | TODO: Notification integration |
| `approve_task()` | ⏳ Stub | TODO: Audit logging |
| Test coverage | ✅ Skeleton | 15+ test cases |
| Documentation | ✅ Initial | This document |

## Future Enhancements (Post-ST-GOV-003)

1. **ML-Based Size Prediction:** Predict story points from task description
2. **Decomposition Suggestions:** AI-assisted task splitting
3. **Pattern Library:** Common decomposition patterns
4. **Approval Analytics:** Insights on approval patterns
5. **Slack/Discord Integration:** Real-time approval notifications

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-22 | 0.1.0 | Initial skeleton implementation |
