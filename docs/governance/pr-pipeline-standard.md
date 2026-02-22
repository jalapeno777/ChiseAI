# PR Pipeline: Standard Path Specification

> **Story**: ST-AUTO-004  
> **Epic**: EP-AUTO-GIT-001: AI Swarm Autonomous PR Pipeline  
> **Status**: In Progress

## Overview

The Standard Path is the primary review flow for PRs that require GitReviewBot analysis but are not eligible for automatic merging. This path balances automation speed with review quality.

## Target Metrics

| Metric | Target |
|--------|--------|
| Review completion time | < 12 minutes |
| GitReviewBot response | < 10 minutes |
| Escalation rate | < 5% of standard path PRs |

## Path Flow

```
┌─────────────────┐
│   PR Created    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Classify PR    │──► COMPLEX ──► Escalate to Human
└────────┬────────┘
         │ STANDARD
         ▼
┌─────────────────┐
│ GitReviewBot    │
│   Review        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Timeout
│  Wait for       │─────────────► Escalate to Human
│  Completion     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Return Result  │
│  (approved/     │
│   changes_req)  │
└─────────────────┘
```

## Components

### StandardPathHandler

Primary class for managing standard path reviews.

```python
from src.governance.pr_pipeline import StandardPathHandler

handler = StandardPathHandler()
result = await handler.review_pr(pr_number=123)

if result.status == ReviewStatus.COMPLETED and result.approved:
    print("PR approved by GitReviewBot")
elif result.status == ReviewStatus.ESCALATED:
    print(f"Escalated: {result.escalation_reason}")
```

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `review_timeout_seconds` | 720 (12 min) | Max time to wait for review |
| `max_review_retries` | 3 | Retry attempts for failed reviews |
| `escalation_enabled` | True | Allow escalation to humans |
| `git_review_bot_timeout_seconds` | 600 (10 min) | Timeout for bot response |

## Classification Rules

### TRIVIAL (Fast Path Eligible)
- Single file changed
- < 10 lines modified
- No logic changes (typo fixes, comments)
- Not security-sensitive files

### STANDARD (This Path)
- Normal code changes
- Test additions/modifications
- Documentation updates
- Feature additions within scope

### COMPLEX (Escalate Immediately)
- Architecture changes
- Security-sensitive code (auth, crypto)
- > 500 lines changed
- Cross-module dependencies
- Database schema changes

## Integration Points

### GitReviewBot API (TODO)

```python
# Stub - actual integration pending
POST /api/v1/review
{
    "pr_number": 123,
    "repository": "chiseai/chiseai",
    "timeout_seconds": 600
}
```

### GitHub API for Escalation (TODO)

```python
# Actions on escalation:
# 1. Add label: "needs-human-review"
# 2. Assign reviewers
# 3. Post comment with context
# 4. Notify via configured channels
```

## Error Handling

| Error | Action |
|-------|--------|
| GitReviewBot timeout | Escalate with reason |
| GitReviewBot error | Retry (max 3), then escalate |
| Classification failure | Default to STANDARD |
| GitHub API error | Log, retry with backoff |

## Testing

Test file: `tests/test_governance/test_pr_standard_path.py`

Coverage requirements:
- [x] Handler initialization
- [x] Custom configuration
- [x] Classification stub
- [x] Review status tracking
- [x] Escalation logic
- [ ] GitReviewBot integration (TODO)
- [ ] Timeout enforcement (TODO)
- [ ] Concurrent review handling (TODO)

## Future Enhancements

1. **Fast Path**: Auto-merge for trivial changes
2. **Batch Reviews**: Process multiple PRs efficiently
3. **Review Quality Metrics**: Track approval accuracy
4. **Learning Loop**: Improve classification from outcomes

## Related Stories

- ST-AUTO-005: PR Pipeline - Fast Path
- ST-AUTO-006: PR Pipeline - Complex Path
- ST-GOV-001: Governance Framework Foundation

---

*Last updated: 2026-02-22*
*Author: AI Swarm Agent (ST-AUTO-004)*
