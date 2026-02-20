# PR Lifecycle Management for Autonomous AI Swarm

## Executive Summary

This document designs a comprehensive PR lifecycle management system that enables the autonomous AI swarm to monitor, recover, and manage PRs from creation to terminal state (merged/failed/escalated) without human intervention. The system works 24/7 and only escalates to humans when AI cannot resolve the issue.

## 1. Current State Analysis

### Existing Components

1. **gitea_pr_automerge.py** (lines 182-214)
   - Retry logic only for merge API calls
   - Basic polling for CI status
   - No automatic failure recovery
   - No PR state tracking

2. **merge_reconciler.py** (lines 300-393)
   - Merge queue processing with incident logging
   - Detects stale head, CI failures, merge conflicts
   - Emits incidents but no automatic recovery
   - Limited retry logic (max_retries parameter)

3. **gitea_pr_review.py**
   - Posts PR reviews (APPROVED/REQUEST_CHANGES)
   - Used for automating approval gates

4. **woodpecker_triage.py**
   - CI root cause analysis
   - Generates failure bundles for diagnosis

5. **session.py**
   - Branch/worktree ownership tracking
   - Redis-based lease management

### Current Gaps

- No systematic PR state tracking in Redis
- No health monitoring service for stuck PRs
- No automatic retry/rebase on merge conflicts
- No dirty branch cleanup automation
- No escalation when max retries exceeded
- Agents don't monitor PRs after enabling automerge

## 2. PR State Machine

### State Diagram (Text Format)

```
                            +------------------+
                            |     created      |
                            +--------+---------+
                                     |
                                     v
+------------------+       +---------+----------+
|  needs_approval  +<------+   pending_ci       |
+--------+---------+       +---------+----------+
         |                           |
         v                           v
+--------+---------+       +---------+----------+
|    approved      +------>+   running_ci       |
+--------+---------+       +---------+----------+
         |                           |
         |              +------------+------------+
         |              |                         |
         v              v                         v
+--------+---------+  +---------+----------+  +---+--------------+
|  mergeable       |  |   ci_failed        |  | ci_timeout       |
+--------+---------+  +---------+----------+  +---+--------------+
         |                      |                  |
         v                      v                  v
+--------+---------+  +---------+----------+  +---+--------------+
|   merging        |  | auto_analyzing     |  | manual_escalate  |
+--------+---------+  +---------+----------+  +---+--------------+
         |                      |                  |
         v                      v                  v
+--------+---------+  +---------+----------+  +---+--------------+
|    merged        |  | auto_fix_attempt   |  | human_notified   |
+--------+---------+  +---------+----------+  +---+--------------+
         |                      |                  |
         v              +-------+-------+          v
+--------+---------+  |               |     +----+-------------+
| branch_cleaned   |  v               v     | waiting_human    |
+------------------+ +---+-------+ +---+----+-------+          |
                     |fix_success| |fix_failed|                |
                     +-----+-----+ +----+-----+                |
                           |          |                       |
                           v          v                       v
                     +-----+-----+ +---+----+-----+  +--------+--------+
                     |requeued   | |escalated     |  | human_resolved  |
                     +-----------+ +--------------+  +--------+--------+
                                                          |
                                                          v
                                                   +------+--------+
                                                   | terminal_state  |
                                                   +-----------------+

Additional States:
- conflict_detected → rebasing → conflict_resolved → requeued
- blocked_external_dependency → waiting_dependency → dependency_resolved
- abandoned (no activity > 2 hours) → auto_cleanup_warning → auto_deleted
```

### State Definitions

| State | Description | Transitions |
|-------|-------------|-------------|
| `created` | PR just opened | → pending_ci, needs_approval |
| `pending_ci` | CI not yet started | → running_ci, ci_failed, ci_timeout |
| `running_ci` | CI in progress | → ci_passed, ci_failed, ci_timeout |
| `ci_passed` | All required contexts green | → mergeable (if approved) |
| `ci_failed` | One or more contexts failed | → auto_analyzing, manual_escalate |
| `needs_approval` | Review required before merge | → approved |
| `approved` | Has required approvals | → mergeable (if CI passed) |
| `mergeable` | Ready to merge (CI + approval) | → merging, conflict_detected |
| `merging` | Merge API call in progress | → merged, merge_failed |
| `merged` | Successfully merged | → branch_cleaned (terminal) |
| `conflict_detected` | Merge conflict with base | → rebasing |
| `rebasing` | Auto-rebase in progress | → conflict_resolved, rebase_failed |
| `auto_analyzing` | Root cause analysis running | → auto_fix_attempt, manual_escalate |
| `auto_fix_attempt` | Attempting automatic fix | → fix_success, fix_failed |
| `fix_success` | Auto-fix worked | → requeued |
| `fix_failed` | Auto-fix failed | → escalated |
| `escalated` | Requires human intervention | → human_resolved (terminal), waiting_human |
| `abandoned` | No activity > threshold | → auto_cleanup_warning |
| `branch_cleaned` | Branch deleted post-merge | (terminal) |

## 3. Agent Monitoring Pattern

### Responsibility Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENT PR OWNERSHIP MODEL                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Agent opens PR → Agent monitors until terminal state                       │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Open PR    │───>│   Monitor    │───>│   Terminal   │                   │
│  │              │    │              │    │   State      │                   │
│  │ - Create PR  │    │ - Poll Gitea │    │ - Merged     │                   │
│  │ - Enable     │    │ - Check CI   │    │ - Failed     │                   │
│  │   automerge  │    │ - Watch for  │    │ - Escalated  │                   │
│  │ - Register   │    │   failures   │    │              │                   │
│  │   in Redis   │    │ - Trigger    │    │ Agent reports │                   │
│  │              │    │   recovery   │    │ back to       │                   │
│  └──────────────┘    └──────────────┘    │   Jarvis      │                   │
│                                              └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Polling Strategy

```python
# Polling Configuration
POLL_INTERVALS = {
    "ci_check": 30,          # Check CI status every 30 seconds
    "merge_status": 60,      # Check merge status every 60 seconds  
    "health_scan": 300,      # Full PR health scan every 5 minutes
    "stuck_threshold": 1800, # PR stuck if no activity > 30 minutes
}

# Exponential Backoff for Retries
RETRY_BACKOFF = {
    "initial_delay": 60,
    "max_delay": 1800,
    "multiplier": 2,
    "max_retries": 5,
}
```

### Agent Monitoring Workflow (Step-by-Step)

```
Step 1: PR CREATION
┌──────────────────────────────────────────────────────────────┐
│ 1. Agent creates PR via gitea_pr_automerge.py                │
│ 2. Agent registers PR in Redis:                              │
│    HSET bmad:chiseai:pr:<pr_number> <state_data>             │
│ 3. Agent starts monitoring task (async/background)           │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 2: ACTIVE MONITORING
┌──────────────────────────────────────────────────────────────┐
│ Loop until terminal state:                                   │
│                                                              │
│ 1. Read PR state from Redis                                  │
│ 2. Query Gitea API for current status                        │
│ 3. Query Woodpecker API for CI status                        │
│ 4. Update state if changed                                   │
│ 5. Check for failures requiring action                       │
│ 6. If failure detected:                                      │
│    - Update state to appropriate failure state               │
│    - Trigger recovery handler                                │
│ 7. Sleep for poll_interval                                   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 3: FAILURE HANDLING
┌──────────────────────────────────────────────────────────────┐
│ 1. Log failure in Redis with timestamp                       │
│ 2. Increment failure counter                                 │
│ 3. Determine failure type                                    │
│ 4. Route to appropriate handler:                             │
│    - CI Failure → auto_analyze_ci()                          │
│    - Merge Conflict → auto_rebase()                          │
│    - API Error → exponential backoff retry                   │
│ 5. If max retries exceeded → escalate to human               │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 4: TERMINAL STATE
┌──────────────────────────────────────────────────────────────┐
│ 1. Update Redis state to terminal state                      │
│ 2. Set terminal timestamp                                    │
│ 3. If merged: queue branch for cleanup                       │
│ 4. If escalated: notify humans (Discord/Slack)               │
│ 5. Report outcome to parent agent/Jarvis                     │
│ 6. Archive PR state to Qdrant for learning                   │
└──────────────────────────────────────────────────────────────┘
```

## 4. Failure Recovery Decision Tree

```
                        ┌──────────────────────┐
                        │    FAILURE TYPE?     │
                        └──────────┬───────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│   CI FAILURE    │    │   MERGE CONFLICT    │    │   TRANSIENT API  │
│                 │    │                     │    │   ERROR          │
└────────┬────────┘    └──────────┬──────────┘    └────────┬─────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│Run woodpecker_  │    │Check if auto-rebase │    │Exponential       │
│triage.py to get │    │is enabled for branch│    │backoff retry     │
│root cause       │    └──────────┬──────────┘    │(max 5 retries)   │
└────────┬────────┘               │               └────────┬─────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│Auto-fixable?    │    │Rebase from main     │    │Success?          │
│(lint, typo, etc)│    │└──────────┬──────────┘    └────────┬─────────┘
└────────┬────────┘               │                        │
         │              ┌─────────┴──────────┐              │
    ┌────┴────┐         │                    │         ┌────┴────┐
    │         │         ▼                    ▼         │         │
    ▼         ▼    ┌────────────┐     ┌──────────┐     ▼         ▼
┌───────┐ ┌───────┐│Rebase      │     │Conflict  │┌───────┐ ┌──────────┐
│YES    │ │NO     ││succeeded?  │     │persists  ││YES    │ │NO        │
└───┬───┘ └───┬───┘└──────┬─────┘     └────┬─────┘└───┬───┘ └───┬──────┘
    │         │           │                │          │         │
    ▼         ▼           ▼                ▼          ▼         ▼
┌───────┐ ┌───────────────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────┐
│Auto-  │ │Escalate to human  │ │Re-run CI    │ │Continue │ │Escalate  │
│apply  │ │with analysis      │ │monitoring   │ │monitoring│ │if max    │
│fix    │ │bundle             │ └─────────────┘ └─────────┘ │retries   │
└───┬───┘ └───────────────────┘                             │exceeded  │
    │                                                       └──────────┘
    ▼
┌──────────┐
│Re-run CI │
└──────────┘

                        ┌──────────────────────┐
                        │  APPROVAL MISSING?   │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                               │
                    ▼                               ▼
          ┌─────────────────────┐     ┌─────────────────────┐
          │ Auto-approve enabled│     │ Auto-approve disabled│
          │ for this branch?    │     │                      │
          └──────────┬──────────┘     └──────────┬──────────┘
                     │                           │
              ┌──────┴──────┐                    ▼
              │             │          ┌─────────────────────┐
              ▼             ▼          │ Post comment        │
       ┌──────────┐  ┌──────────┐      │ requesting review   │
       │   YES    │  │    NO    │      │ from merlin         │
       └────┬─────┘  └────┬─────┘      └──────────┬──────────┘
            │             │                       │
            ▼             ▼                       ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
     │Use dedicated │  │Post comment  │  │Wait 10 min   │
     │review token  │  │requesting    │  │then re-check │
     │to approve    │  │human review  │  └──────┬───────┘
     └──────────────┘  └──────────────┘         │
                                                ▼
                                         ┌──────────────┐
                                         │Max retries?  │
                                         │(3 attempts)  │
                                         └──────┬───────┘
                                                │
                                         ┌──────┴──────┐
                                         │             │
                                         ▼             ▼
                                  ┌──────────┐  ┌──────────┐
                                  │YES       │  │NO        │
                                  │Escalate  │  │Continue  │
                                  └──────────┘  └──────────┘
```

## 5. Dirty Branch Management

### Dirty Branch Detection Criteria

A branch is considered "dirty" if ANY of the following are true:

1. **Failed CI** - Last CI run failed and no fix attempted
2. **Merge Conflict** - Cannot be merged without rebase
3. **Abandoned** - No activity for > 2 hours and not merged
4. **Stale** - Behind main by > 50 commits
5. **Orphaned PR** - PR closed without merge but branch still exists

### Dirty Branch Actions

```python
DIRTY_BRANCH_ACTIONS = {
    "failed_ci": {
        "auto_action": "retry_with_backoff",
        "max_retries": 3,
        "escalate_after": "auto_fix_failed",
    },
    "merge_conflict": {
        "auto_action": "auto_rebase",
        "max_retries": 2,
        "escalate_after": "rebase_failed",
    },
    "abandoned": {
        "auto_action": "warn_then_delete",
        "warning_delay_minutes": 30,
        "delete_delay_minutes": 60,
        "preserve_if_escalated": True,
    },
    "stale": {
        "auto_action": "auto_rebase",
        "max_retries": 2,
    },
    "orphaned": {
        "auto_action": "delete_after_confirmation",
        "confirmation_delay_hours": 24,
    },
}
```

### Cleanup Workflow

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        DIRTY BRANCH CLEANUP WORKFLOW                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐                                                           │
│  │  PR Merged   │                                                           │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │ Queue Branch │────>│ Wait 5 min   │────>│ Delete Local │                │
│  │ for Cleanup  │     │ (grace)      │     │ Branch       │                │
│  └──────────────┘     └──────────────┘     └──────┬───────┘                │
│                                                   │                         │
│                                                   ▼                         │
│  ┌──────────────┐                          ┌──────────────┐                │
│  │PR Failed/    │                          │ Delete Remote│                │
│  │Escalated     │                          │ Branch       │                │
│  └──────┬───────┘                          └──────────────┘                │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────┐                                                           │
│  │ Preserve for │                                                           │
│  │ 7 days       │                                                           │
│  │ (debugging)  │                                                           │
│  └──────────────┘                                                           │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

## 6. Health Monitoring Service

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PR HEALTH MONITORING SERVICE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  Cron/Scheduler │ Every 5 minutes                                        │
│  │  (systemd/      │                                                        │
│  │   woodpecker)   │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │   Scan all open │────>│   For each PR:  │────>│   Health Check  │       │
│  │   PRs in Gitea  │     │   Check state   │     │   Actions       │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│                                                             │               │
│                          ┌──────────────────────────────────┼───────────┐   │
│                          │                                  │           │   │
│                          ▼                                  ▼           ▼   │
│                   ┌──────────────┐              ┌──────────────┐ ┌────────┐ │
│                   │PR stuck > 30 │              │State mismatch│ │Unknown │ │
│                   │min?          │              │detected      │ │state   │ │
│                   └──────┬───────┘              └──────┬───────┘ └───┬────┘ │
│                          │                            │             │      │
│                          ▼                            ▼             ▼      │
│                   ┌──────────────┐              ┌──────────────┐ ┌────────┐│
│                   │Trigger       │              │Update state  │ │Log     ││
│                   │recovery      │              │in Redis      │ │incident││
│                   └──────────────┘              └──────────────┘ └────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stuck PR Detection

```python
STUCK_CRITERIA = {
    "ci_pending_too_long": {
        "state": "running_ci",
        "max_duration_minutes": 45,
        "action": "check_woodpecker_for_stuck",
    },
    "no_activity": {
        "last_update_max_minutes": 30,
        "action": "poll_for_updates",
    },
    "retry_loop": {
        "same_state_transitions": 5,
        "time_window_minutes": 60,
        "action": "escalate_to_human",
    },
    "merge_blocked": {
        "state": "mergeable",
        "max_duration_minutes": 15,
        "action": "force_merge_attempt",
    },
}
```

## 7. Escalation Criteria

### Escalation Matrix

| Criteria | Severity | Auto-Action | Human Notification |
|----------|----------|-------------|-------------------|
| Max retries exceeded (5x) | HIGH | Create incident, preserve branch | Discord + dashboard |
| Unknown failure type | HIGH | Log incident with full context | Discord + create ticket |
| Systemic failure (>3 PRs same error) | CRITICAL | Pause queue, alert immediately | Discord + page |
| CI infrastructure failure | CRITICAL | Log incident, retry in 1 hour | Discord alert |
| Merge conflict after rebase | MEDIUM | Log incident, request human | Dashboard only |
| Auto-fix failed | MEDIUM | Log incident with analysis | Dashboard + digest |
| Manual override requested | INFO | Process immediately | None |

### Escalation Workflow

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         ESCALATION WORKFLOW                                 │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Trigger: Max retries / Unknown failure / Systemic pattern                  │
│                              │                                              │
│                              ▼                                              │
│  ┌───────────────────────────────────────────────┐                          │
│  │ 1. Update Redis state to 'escalated'          │                          │
│  │ 2. Log incident to bmad:chiseai:incidents     │                          │
│  │ 3. Create failure bundle with full context    │                          │
│  │ 4. Post PR comment explaining situation       │                          │
│  └───────────────────────┬───────────────────────┘                          │
│                          │                                                  │
│              ┌───────────┴───────────┐                                      │
│              │                       │                                      │
│              ▼                       ▼                                      │
│  ┌───────────────────┐   ┌───────────────────┐                             │
│  │ HIGH severity?    │   │ MEDIUM severity?  │                             │
│  └─────────┬─────────┘   └─────────┬─────────┘                             │
│            │                       │                                       │
│      ┌─────┴─────┐           ┌─────┴─────┐                                 │
│      │           │           │           │                                 │
│      ▼           ▼           ▼           ▼                                 │
│  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐                                │
│  │Discord│  │Email  │  │Dash-  │  │Daily  │                                │
│  │alert  │  │alert  │  │board  │  │digest │                                │
│  │+ page │  │       │  │       │  │       │                                │
│  └───────┘  └───────┘  └───────┘  └───────┘                                │
│                                                                             │
│  Human Resolution Path:                                                     │
│  ┌─────────────────────────────────────────────────────────┐               │
│  │ - Fix issue manually                                     │               │
│  │ - Comment on PR with "@chiseai resolve" to re-queue      │               │
│  │ - Or close PR and let system clean up branch             │               │
│  │ - System monitors for human actions and updates state    │               │
│  └─────────────────────────────────────────────────────────┘               │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

## 8. Redis Schema for PR State Tracking

### Key Patterns

```
# PR State Hash (primary tracking)
bmad:chiseai:pr:<pr_number>  →  HASH

# PR Event History (audit trail)
bmad:chiseai:pr:<pr_number>:events  →  LIST

# Active PRs Index (for health monitoring)
bmad:chiseai:pr:active  →  SET of pr_numbers

# PRs by State (for filtering)
bmad:chiseai:pr:state:<state_name>  →  SET of pr_numbers

# Agent Assignment (who owns this PR)
bmad:chiseai:pr:<pr_number>:owner  →  STRING (story_id/agent)

# Failure Tracking
bmad:chiseai:pr:<pr_number>:failures  →  LIST of failure events

# Retry Counter
bmad:chiseai:pr:<pr_number>:retry_count  →  STRING (integer)

# Cleanup Queue
bmad:chiseai:cleanup:branches  →  LIST of branch names to clean

# Health Check Last Run
bmad:chiseai:pr:health:last_scan  →  STRING (ISO timestamp)
```

### PR State Hash Schema

```python
PR_STATE_SCHEMA = {
    # Identification
    "pr_number": "123",
    "story_id": "ST-NS-001",
    "branch": "feature/ST-NS-001-foo",
    "head_sha": "abc123...",
    
    # Ownership
    "opened_by_agent": "dev-001",
    "owned_by_agent": "dev-001",  # May change during recovery
    
    # State
    "current_state": "running_ci",  # From state machine
    "previous_state": "pending_ci",
    "state_changed_at": "2026-02-19T12:00:00Z",
    
    # Timestamps
    "created_at": "2026-02-19T11:50:00Z",
    "last_updated_at": "2026-02-19T12:05:00Z",
    "terminal_at": "",  # Set when reaching terminal state
    
    # CI Status
    "ci_status": "pending",  # pending/running/success/failure
    "ci_contexts": '{"ci/woodpecker/pr": "pending", "lint": "success"}',
    "last_ci_pipeline_id": "456",
    
    # Merge Status
    "mergeable": "true",  # true/false/unknown
    "merge_attempts": "2",
    "last_merge_attempt_at": "2026-02-19T12:03:00Z",
    
    # Approval
    "approval_status": "pending",  # pending/approved/changes_requested
    "approvers": '["merlin"]',
    
    # Recovery
    "retry_count": "1",
    "max_retries": "5",
    "failure_type": "",  # Set when failure detected
    "recovery_action": "",  # Current recovery attempt
    
    # Escalation
    "escalated": "false",
    "escalated_at": "",
    "escalation_reason": "",
    
    # Cleanup
    "cleanup_scheduled": "false",
    "cleanup_after": "",
}
```

### Event Structure

```python
PR_EVENT_SCHEMA = {
    "timestamp": "2026-02-19T12:00:00Z",
    "event_type": "state_transition",  # state_transition/failure/recovery/escalation/merge
    "from_state": "pending_ci",
    "to_state": "running_ci",
    "triggered_by": "ci_webhook",  # ci_webhook/poll/merge_api/recovery_action
    "metadata": '{"pipeline_id": 456}',  # JSON blob
}
```

### Redis Operations Examples

```python
# Register new PR
redis.hset(f"bmad:chiseai:pr:{pr_number}", mapping=pr_state)
redis.sadd("bmad:chiseai:pr:active", pr_number)
redis.sadd("bmad:chiseai:pr:state:created", pr_number)

# Update state
pipe = redis.pipeline()
pipe.hset(f"bmad:chiseai:pr:{pr_number}", "current_state", new_state)
pipe.hset(f"bmad:chiseai:pr:{pr_number}", "previous_state", old_state)
pipe.hset(f"bmad:chiseai:pr:{pr_number}", "state_changed_at", now)
pipe.srem(f"bmad:chiseai:pr:state:{old_state}", pr_number)
pipe.sadd(f"bmad:chiseai:pr:state:{new_state}", pr_number)
pipe.rpush(f"bmad:chiseai:pr:{pr_number}:events", json.dumps(event))
pipe.execute()

# Get all PRs in failed state
failed_prs = redis.smembers("bmad:chiseai:pr:state:ci_failed")

# Get PRs stuck for > 30 minutes
# (requires scanning and checking last_updated_at field)

# Mark terminal and cleanup
pipe = redis.pipeline()
pipe.hset(f"bmad:chiseai:pr:{pr_number}", "current_state", "merged")
pipe.hset(f"bmad:chiseai:pr:{pr_number}", "terminal_at", now)
pipe.srem("bmad:chiseai:pr:active", pr_number)
pipe.rpush("bmad:chiseai:cleanup:branches", branch_name)
pipe.execute()
```

## 9. Implementation Plan

### Phase 1: Core Infrastructure (Day 1)

#### New Files to Create

1. **`scripts/pr_lifecycle/pr_state_manager.py`**
   - PRState dataclass
   - Redis operations for state tracking
   - State transition validation
   - Event logging

2. **`scripts/pr_lifecycle/pr_monitor.py`**
   - Polling logic for PR status
   - CI status checking
   - State update detection
   - Configurable poll intervals

3. **`scripts/pr_lifecycle/recovery_handlers.py`**
   - CI failure recovery (uses woodpecker_triage.py)
   - Merge conflict auto-rebase
   - Transient error retry with backoff
   - Approval request automation

4. **`scripts/pr_lifecycle/health_monitor.py`**
   - Background service to scan all PRs
   - Stuck PR detection
   - Systemic issue detection
   - Cron-friendly entry point

#### Modifications to Existing Files

1. **`scripts/gitea_pr_automerge.py`**
   - Add PR registration to Redis after creation
   - Start monitoring task before returning
   - Update to use shared PR state
   - Lines to modify: 280-320 (PR creation flow)

2. **`scripts/ops/merge_reconciler.py`**
   - Add PR state updates during queue processing
   - Integrate with recovery handlers
   - Emit proper state transitions
   - Lines to modify: 300-393 (process_item)

3. **`scripts/gitea_pr_review.py`**
   - Add method to check approval status
   - Update PR state when approval posted
   - Minor enhancements only

### Phase 2: Automation & Recovery (Day 1-2)

#### New Files to Create

5. **`scripts/pr_lifecycle/auto_rebase.py`**
   - Git operations for rebase
   - Conflict detection
   - Force push with lease
   - Safety checks

6. **`scripts/pr_lifecycle/ci_auto_fix.py`**
   - Integrate with woodpecker_triage.py output
   - Common fix patterns (lint, format)
   - Apply fixes and re-commit
   - Safety checks

7. **`scripts/pr_lifecycle/escalation_manager.py`**
   - Human notification logic
   - Discord integration
   - Dashboard updates
   - Incident creation

#### New Commands

8. **`.opencode/command/chise-pr-monitor.md`**
   - Start monitoring a PR
   - Check PR status
   - Manual recovery trigger

9. **`.opencode/command/chise-pr-health-check.md`**
   - Run health scan on all PRs
   - Report stuck PRs
   - Manual cleanup

### Phase 3: Integration & Testing (Day 2)

#### Configuration

10. **`scripts/pr_lifecycle/config.py`**
    - Environment-based configuration
    - Feature flags for gradual rollout
    - Timeout and retry settings

#### Testing

11. **`tests/test_pr_lifecycle.py`**
    - Unit tests for state transitions
    - Mock Gitea/Woodpecker responses
    - Redis state verification

12. **Integration test script**
    - End-to-end PR lifecycle test
    - Simulated failure scenarios
    - Recovery validation

### Phase 4: Deployment (Day 2-3)

#### Woodpecker Pipeline

13. **`.woodpecker/pr-lifecycle-monitor.yml`**
    - Scheduled job every 5 minutes
    - Runs health_monitor.py
    - Alert on systemic issues

14. **Documentation updates**
    - Update AGENTS.md with PR monitoring requirements
    - Update workflow documentation
    - Runbook for human escalation

## 10. Integration Points

### With Existing Automerge Scripts

```python
# In gitea_pr_automerge.py, after creating PR:

from pr_lifecycle.pr_state_manager import PRStateManager
from pr_lifecycle.pr_monitor import PRMonitor

# Register PR in lifecycle system
state_mgr = PRStateManager()
state = PRState(
    pr_number=pr["number"],
    story_id=args.story_id,
    branch=args.head,
    head_sha=sha,
    opened_by_agent=args.agent_id,
)
state_mgr.register_pr(state)

# Start monitoring (non-blocking, returns immediately)
monitor = PRMonitor(pr_number=pr["number"])
monitor.start_background_monitoring()

# Continue with automerge logic as before...
```

### With Merge Reconciler

```python
# In merge_reconciler.py, process_item method:

from pr_lifecycle.pr_state_manager import PRStateManager

state_mgr = PRStateManager()

# Update state before processing
state_mgr.transition_state(
    pr_number=item.pr_number,
    to_state="processing_queue",
    triggered_by="reconciler"
)

# ... existing processing logic ...

# On success/failure, update state
if success:
    state_mgr.transition_state(
        pr_number=item.pr_number,
        to_state="merged",
        triggered_by="merge_api"
    )
else:
    state_mgr.transition_state(
        pr_number=item.pr_number,
        to_state="ci_failed",
        triggered_by="ci_check"
    )
```

### With CI Triage

```python
# In recovery_handlers.py:

from ci.woodpecker_triage import diagnose_pr

def handle_ci_failure(pr_number: int) -> RecoveryResult:
    # Get root cause
    diagnosis = diagnose_pr(pr_number)
    
    # Update state with diagnosis
    state_mgr.update_ci_failure(pr_number, diagnosis)
    
    # Route to appropriate handler
    if diagnosis.is_auto_fixable():
        return attempt_auto_fix(pr_number, diagnosis)
    else:
        return escalate(pr_number, diagnosis)
```

## 11. Monitoring & Observability

### Metrics to Track

```python
PR_LIFECYCLE_METRICS = {
    # Flow metrics
    "pr_created_total": Counter,
    "pr_merged_total": Counter,
    "pr_failed_total": Counter,
    "pr_escalated_total": Counter,
    
    # Time metrics
    "pr_time_to_merge": Histogram,  # From created to merged
    "pr_time_to_ci_pass": Histogram,  # From created to CI green
    "pr_time_stuck": Histogram,  # Time in stuck state before recovery
    
    # Recovery metrics
    "recovery_attempts_total": Counter,
    "recovery_success_total": Counter,
    "auto_fix_applied_total": Counter,
    
    # Error metrics
    "state_transition_errors": Counter,
    "recovery_handler_errors": Counter,
    "escalation_errors": Counter,
}
```

### Logging

All operations log structured JSON:

```json
{
  "timestamp": "2026-02-19T12:00:00Z",
  "level": "INFO",
  "component": "pr_lifecycle.monitor",
  "event": "state_transition",
  "pr_number": 123,
  "story_id": "ST-NS-001",
  "from_state": "pending_ci",
  "to_state": "running_ci",
  "triggered_by": "poll",
  "duration_ms": 150
}
```

## 12. Rollback Plan

If issues arise:

1. **Feature flags** - Disable auto-recovery via env var
2. **State preservation** - All states in Redis, no state lost on restart
3. **Manual override** - Human can always take over by commenting on PR
4. **Quick disable** - Set `CHISE_PR_LIFECYCLE_ENABLED=false`

## 13. Success Criteria

The system is successful when:

1. ✅ 95%+ of PRs reach terminal state without human intervention
2. ✅ No PR sits failed for > 30 minutes without action
3. ✅ All dirty branches cleaned up within 1 hour of PR merge/failure
4. ✅ Systemic issues detected within 15 minutes
5. ✅ Human escalations include full context for quick resolution
6. ✅ Zero "lost" PRs that agents forget about

## 14. 24-Hour Deployment Checklist

- [ ] Create core files (pr_state_manager.py, pr_monitor.py)
- [ ] Modify gitea_pr_automerge.py to register PRs
- [ ] Create health_monitor.py with cron job
- [ ] Test with 1-2 PRs manually
- [ ] Deploy to woodpecker with 5-min schedule
- [ ] Monitor first day closely
- [ ] Document any issues for Phase 2

---

## Appendices

### A. Environment Variables

```bash
# Feature flags
CHISE_PR_LIFECYCLE_ENABLED=true
CHISE_PR_AUTO_REBASE=true
CHISE_PR_AUTO_FIX_CI=true

# Timing
CHISE_PR_POLL_INTERVAL_SEC=30
CHISE_PR_HEALTH_SCAN_INTERVAL_SEC=300
CHISE_PR_STUCK_THRESHOLD_MIN=30

# Limits
CHISE_PR_MAX_RETRIES=5
CHISE_PR_MAX_AGE_HOURS=24

# Notifications
CHISE_PR_ESCALATION_WEBHOOK_URL=
CHISE_PR_DISCORD_CHANNEL=
```

### B. API Reference

See inline documentation in created Python files for full API.

### C. Troubleshooting Guide

1. **PR not being monitored** - Check Redis state exists, check agent_id matches
2. **Recovery not triggering** - Check max_retries not exceeded, check feature flags
3. **False escalations** - Review failure classification logic
4. **Branches not cleaning up** - Check cleanup queue processing
