# PR Lifecycle Management System

## Overview

This system provides comprehensive autonomous PR lifecycle management for the ChiseAI swarm, ensuring PRs are monitored from creation to terminal state (merged/failed/escalated) without human intervention.

## Problem Solved

**Before this system:**
- AI agents open PRs and enable automerge
- PRs may fail CI, have merge conflicts, or get stuck
- Agents might not check results and move to next task
- Failed PRs sit in queue indefinitely
- "Dirty" branches accumulate
- System depends on humans noticing failures

**With this system:**
- Agents register PRs in Redis state tracking
- Continuous monitoring detects failures automatically
- Automatic recovery for common failure types
- Escalation to humans only when AI cannot resolve
- 24/7 operation without human intervention

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PR LIFECYCLE ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │ Agent creates PR │                                                       │
│  └────────┬─────────┘                                                       │
│           │ register_pr()                                                   │
│           ▼                                                                 │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │  PR State Store  │────>│  PR Monitor      │────>│  Health Monitor  │    │
│  │  (Redis)         │     │  (Polling)       │     │  (Scheduled)     │    │
│  └────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘    │
│           │                        │                        │              │
│           ▼                        ▼                        ▼              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                      Recovery Handlers                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │    │
│  │  │ CI Failure   │  │ Merge        │  │ Missing      │             │    │
│  │  │ Handler      │  │ Conflict     │  │ Approval     │             │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                │                                           │
│                    ┌───────────┴───────────┐                               │
│                    │                       │                               │
│                    ▼                       ▼                               │
│           ┌──────────────┐        ┌──────────────┐                         │
│           │   Success    │        │  Escalate    │                         │
│           │   (Continue) │        │  (Human)     │                         │
│           └──────────────┘        └──────────────┘                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. `pr_state_manager.py`
**Purpose:** Redis-based state tracking for all PRs

**Key Classes:**
- `PRState` - Dataclass representing PR state
- `PREvent` - Event in PR lifecycle
- `PRStateManager` - CRUD operations for PR state

**Redis Keys:**
- `bmad:chiseai:pr:<pr_number>` - PR state hash
- `bmad:chiseai:pr:active` - Set of active PR numbers
- `bmad:chiseai:pr:state:<state_name>` - Sets of PRs by state
- `bmad:chiseai:pr:<pr_number>:events` - Event history

### 2. `pr_monitor.py`
**Purpose:** Continuous monitoring of individual PRs

**Key Classes:**
- `PRMonitor` - Polls PRs and detects state changes
- `GiteaAPI` - Simple Gitea API client

**Features:**
- Configurable poll intervals
- Stuck PR detection
- Automatic state transitions
- SHA change detection

### 3. `health_monitor.py`
**Purpose:** Fleet-wide health monitoring

**Key Classes:**
- `PRHealthMonitor` - Scans all PRs for issues

**Features:**
- Comprehensive PR scanning
- Systemic issue detection
- Recovery action triggering
- Human-readable reports

### 4. `recovery_handlers.py`
**Purpose:** Automatic recovery from failures

**Key Classes:**
- `RecoveryHandlers` - Routes failures to appropriate handlers
- `RecoveryResult` - Result of recovery attempt

**Handlers:**
- CI failure with auto-fix detection
- Merge conflict with auto-rebase
- Missing approval with auto-approval
- Transient errors with exponential backoff

### 5. `integration.py`
**Purpose:** Integration helpers for existing scripts

**Key Functions:**
- `register_new_pr()` - Register PR after creation
- `update_pr_on_merge_attempt()` - Record merge attempts
- `handle_ci_status_change()` - Handle CI updates

## State Machine

```
created → pending_ci → running_ci → ci_passed → needs_approval → approved → mergeable → merged
   │          │            │             │             │            │           │
   │          │            │             │             │            │           └───────> merging
   │          │            │             │             │            │
   │          │            │             │             │            └───────> conflict_detected
   │          │            │             │             │
   │          │            │             │             └───────> approval_requested
   │          │            │             │
   │          │            │             └───────> ci_failed → auto_analyzing → escalated
   │          │            │
   │          │            └───────> ci_timeout → escalated
   │          │
   │          └───────> needs_approval
   │
   └───────> closed_unmerged (terminal)
```

## Usage

### For Agent Developers

When creating a PR, register it immediately:

```python
from scripts.pr_lifecycle.integration import register_new_pr

# After creating PR
register_new_pr(
    pr_number=pr["number"],
    story_id=args.story_id,
    branch=args.head,
    head_sha=sha,
    agent_id=args.agent_id,
)
```

Then monitor until terminal state:

```python
from scripts.pr_lifecycle.pr_monitor import PRMonitor

monitor = PRMonitor()
result = monitor.monitor_single_pr(pr_number, timeout_sec=3600)
```

### For Operations

Check PR status:

```bash
python3 scripts/pr_lifecycle/integration.py summary --pr-number 123
```

Run health scan:

```bash
python3 scripts/pr_lifecycle/health_monitor.py scan
```

Trigger recovery:

```bash
python3 scripts/pr_lifecycle/health_monitor.py recovery --dry-run
python3 scripts/pr_lifecycle/health_monitor.py recovery
```

## Configuration

Environment variables:

```bash
# Feature flags
CHISE_PR_LIFECYCLE_ENABLED=true

# Timing
CHISE_PR_POLL_INTERVAL_SEC=30
CHISE_PR_HEALTH_SCAN_INTERVAL_SEC=300
CHISE_PR_STUCK_THRESHOLD_MIN=30

# Limits
CHISE_PR_MAX_RETRIES=5
CHISE_PR_SYSTEMIC_THRESHOLD=3

# Gitea
GITEA_BASE_URL=http://host.docker.internal:3000
GITEA_TOKEN=your_token_here
GITEA_REVIEW_TOKEN=review_token_here  # Separate token for approvals
GITEA_OWNER=craig
GITEA_REPO=ChiseAI

# Redis
CHISE_REDIS_HOST=host.docker.internal
CHISE_REDIS_PORT=6380
CHISE_REDIS_DB=0
```

## Automated Monitoring

The Woodpecker pipeline (`.woodpecker/pr-lifecycle-monitor.yaml`) runs every 5 minutes:

1. Scans all active PRs
2. Detects stuck PRs and systemic issues
3. Triggers automatic recovery actions
4. Notifies on critical issues

## Escalation Criteria

PRs are escalated to humans when:

1. **Max retries exceeded** (5 attempts) - Any recovery type
2. **Unknown failure type** - Cannot be automatically handled
3. **Systemic pattern** - >3 PRs failing with same error
4. **Auto-fix not implemented** - CI failure type we can't auto-fix yet
5. **Rebase failed** - Merge conflict could not be auto-resolved

## Redis Schema

### PR State Hash
```
Key: bmad:chiseai:pr:<pr_number>
Type: HASH
Fields:
  - pr_number, story_id, branch, head_sha
  - opened_by_agent, owned_by_agent
  - current_state, previous_state, state_changed_at
  - created_at, last_updated_at, terminal_at
  - ci_status, ci_contexts, last_ci_pipeline_id
  - mergeable, merge_attempts, last_merge_attempt_at
  - approval_status, approvers
  - retry_count, max_retries, failure_type, recovery_action
  - escalated, escalated_at, escalation_reason
  - cleanup_scheduled, cleanup_after
```

### Indexes
```
bmad:chiseai:pr:active - SET of active PR numbers
bmad:chiseai:pr:state:<state> - SET of PRs in each state
bmad:chiseai:pr:<pr_number>:events - LIST of event history
bmad:chiseai:pr:<pr_number>:failures - LIST of failure events
bmad:chiseai:pr:health:scan:<timestamp> - Latest scan results
bmad:chiseai:pr:health:last_scan - STRING of last scan time
```

## 24-Hour Deployment Checklist

### Day 1: Core Infrastructure

- [ ] Deploy `pr_state_manager.py`
- [ ] Deploy `pr_monitor.py`
- [ ] Deploy `health_monitor.py`
- [ ] Deploy `recovery_handlers.py`
- [ ] Deploy `integration.py`
- [ ] Test Redis connectivity
- [ ] Test Gitea API access

### Day 1: Integration

- [ ] Modify `gitea_pr_automerge.py` to register PRs
- [ ] Test PR creation flow
- [ ] Verify state tracking in Redis
- [ ] Test monitoring functions

### Day 2: Automation

- [ ] Deploy Woodpecker pipeline
- [ ] Verify scheduled runs
- [ ] Test health scan
- [ ] Test recovery triggers
- [ ] Verify escalation notifications

### Day 2: Testing

- [ ] Create test PR
- [ ] Verify monitoring picks it up
- [ ] Test failure scenario
- [ ] Verify escalation works
- [ ] Test successful merge flow

### Day 2: Documentation

- [ ] Update agent documentation
- [ ] Create runbook for human escalation
- [ ] Document recovery procedures
- [ ] Set up monitoring dashboards

## Success Metrics

Track these metrics to verify system health:

1. **PRs Reaching Terminal State** - 95%+ without human intervention
2. **Time to Detection** - Failed PRs detected within 5 minutes
3. **Time to Resolution** - Auto-recovered PRs fixed within 15 minutes
4. **Escalation Rate** - <5% of PRs require human escalation
5. **False Positive Rate** - Escalations that didn't need human help

## Troubleshooting

### PR Not Being Monitored

1. Check if registered in Redis:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGETALL bmad:chiseai:pr:<number>
   ```

2. Check if in active set:
   ```bash
   redis-cli -h host.docker.internal -p 6380 SMEMBERS bmad:chiseai:pr:active
   ```

### Recovery Not Triggering

1. Check retry count vs max_retries
2. Verify feature flags are enabled
3. Check recovery handler logs
4. Verify PR state allows recovery

### Stuck PRs Not Detected

1. Check health monitor logs
2. Verify stuck threshold configuration
3. Check last_updated_at timestamps
4. Verify monitoring is running

## Future Enhancements

Phase 2 enhancements planned:

1. **Auto-fix implementation** - Actually run fix commands (ruff --fix, etc.)
2. **Auto-rebase** - Implement git operations for conflict resolution
3. **Webhook integration** - Real-time updates from Gitea/Woodpecker
4. **Dashboard** - Web UI for PR lifecycle visualization
5. **Metrics export** - Prometheus metrics for monitoring
6. **ML-based classification** - Smarter auto-fix detection

## Support

For issues or questions:
1. Check the health scan results
2. Review PR event history in Redis
3. Consult the design doc: `docs/designs/pr-lifecycle-management.md`
4. Run manual recovery: `python3 scripts/pr_lifecycle/recovery_handlers.py`
