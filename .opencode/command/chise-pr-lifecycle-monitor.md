---
name: "chise-pr-lifecycle-monitor"
description: "ChiseAI: Monitor PR lifecycle status and trigger recovery actions for stuck or failed PRs."
disable-model-invocation: true
---

Use this command to monitor PR lifecycle status and manage autonomous PR handling.

## Prerequisites
- Redis available at host.docker.internal:6380
- GITEA_TOKEN set in environment
- PR registered in lifecycle system

## 1. Register a new PR for monitoring

Register a PR immediately after creation:

```bash
python3 scripts/pr_lifecycle/integration.py register \
  --pr-number "${PR_NUMBER}" \
  --story-id "${STORY_ID}" \
  --branch "${BRANCH_NAME}" \
  --head-sha "${HEAD_SHA}" \
  --agent "${AGENT_ID}"
```

## 2. Check PR status

Get current status of a monitored PR:

```bash
python3 scripts/pr_lifecycle/integration.py summary --pr-number "${PR_NUMBER}"
```

## 3. Monitor a single PR until terminal state

Poll a specific PR until merged/failed/escalated:

```bash
python3 scripts/pr_lifecycle/pr_monitor.py monitor \
  --pr-number "${PR_NUMBER}" \
  --timeout-sec 3600 \
  --poll-sec 30
```

## 4. Process all active PRs

One-time scan of all active PRs:

```bash
python3 scripts/pr_lifecycle/pr_monitor.py process-all
```

## 5. Run comprehensive health scan

Detect stuck PRs and systemic issues:

```bash
python3 scripts/pr_lifecycle/health_monitor.py scan
```

## 6. Check for systemic health issues

Quick check for fleet-wide problems:

```bash
python3 scripts/pr_lifecycle/health_monitor.py check
```

## 7. Trigger recovery actions

Based on health scan, trigger automatic recovery:

```bash
# Dry run first
python3 scripts/pr_lifecycle/health_monitor.py recovery --dry-run

# Actually trigger
python3 scripts/pr_lifecycle/health_monitor.py recovery
```

## 8. Handle specific failure types

### CI Failure
```bash
python3 scripts/pr_lifecycle/recovery_handlers.py ci-failure \
  --pr-number "${PR_NUMBER}" \
  --diagnosis '{"tool": "ruff", "kind": "format"}'
```

### Merge Conflict
```bash
python3 scripts/pr_lifecycle/recovery_handlers.py merge-conflict \
  --pr-number "${PR_NUMBER}"
```

### Missing Approval
```bash
python3 scripts/pr_lifecycle/recovery_handlers.py missing-approval \
  --pr-number "${PR_NUMBER}"
```

## 9. Manual escalation

Force escalate a PR to humans:

```bash
python3 scripts/pr_lifecycle/pr_state_manager.py escalate \
  --pr-number "${PR_NUMBER}" \
  --reason "Manual escalation: [reason]"
```

## 10. List PRs by state

Find all PRs in a specific state:

```bash
# List all active PRs
python3 scripts/pr_lifecycle/pr_state_manager.py list-active

# List PRs in specific state
python3 scripts/pr_lifecycle/pr_state_manager.py list-state --state "ci_failed"
```

## Environment Variables

- `CHISE_PR_POLL_INTERVAL_SEC`: Poll interval (default: 30)
- `CHISE_PR_HEALTH_SCAN_INTERVAL_SEC`: Health scan interval (default: 300)
- `CHISE_PR_STUCK_THRESHOLD_MIN`: Stuck threshold in minutes (default: 30)
- `CHISE_PR_MAX_RETRIES`: Max recovery retries (default: 5)
- `GITEA_TOKEN`: Gitea API token
- `GITEA_REVIEW_TOKEN`: Separate token for approvals (optional)

## Redis Schema

PR states stored in:
- `bmad:chiseai:pr:<pr_number>` - PR state hash
- `bmad:chiseai:pr:active` - Set of active PR numbers
- `bmad:chiseai:pr:state:<state_name>` - Sets of PRs by state
- `bmad:chiseai:pr:<pr_number>:events` - Event history list

## Notes

- All PRs should be registered immediately after creation
- Health monitor runs automatically every 5 minutes via Woodpecker
- Agents are responsible for monitoring their own PRs until terminal state
- Escalated PRs require human intervention to resolve
