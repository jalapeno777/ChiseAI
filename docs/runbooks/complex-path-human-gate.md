# Complex Path Human Gate Runbook

## Overview

The **Complex Path Human Gate** is a critical component of the AI Swarm Autonomous PR Pipeline. It ensures that PRs classified as **COMPLEX** (involving execution, infrastructure, or secrets changes) receive mandatory human approval before merging.

**Story**: ST-AUTO-004  
**Epic**: EP-AUTO-GIT-001  
**Dependencies**: ST-AUTO-001 (Path Analyzer), ST-AUTO-003 (GitReviewBot)

---

## Table of Contents

1. [How COMPLEX PRs Are Identified](#how-complex-prs-are-identified)
2. [Approval Workflow Steps](#approval-workflow-steps)
3. [Emergency Override Procedure](#emergency-override-procedure)
4. [Troubleshooting](#troubleshooting)
5. [API Reference](#api-reference)
6. [Audit Trail](#audit-trail)

---

## How COMPLEX PRs Are Identified

### Path Analyzer Integration

The Complex Path Gate integrates with the **Path Analyzer** (ST-AUTO-001) to classify PRs based on file paths:

```python
from scripts.pr_lifecycle.complex_path_gate import ComplexPathGate

gate = ComplexPathGate()
is_complex, risk_level, confidence = gate.is_complex_classification(files)
```

### COMPLEX Classification Criteria

A PR is classified as **COMPLEX** if it modifies any of the following:

| Category | File Patterns | Risk Level |
|----------|----------------|------------|
| **Infrastructure** | `infrastructure/terraform/*`, `docker-compose.yml`, `Dockerfile` | COMPLEX |
| **CI/CD** | `.woodpecker.yml`, `.github/workflows/*`, `pyproject.toml` | COMPLEX |
| **Execution** | `src/execution/*`, `src/governance/*` | COMPLEX |
| **Secrets** | `*.env*`, `*secret*`, `*credential*`, `*password*` | COMPLEX |
| **Core Config** | `AGENTS.md`, `config/bootstrap.py` | COMPLEX |
| **Database** | `*/migrations/*`, `infrastructure/terraform/*postgres*` | COMPLEX |

### Risk Levels

The Path Analyzer uses three risk levels:

- **SAFE**: Auto-approval eligible (docs, tests, non-critical files)
- **MEDIUM_RISK**: Requires GitReviewBot review
- **COMPLEX**: Requires human approval (this gate)

### Example Classifications

```python
# SAFE - Auto-approval eligible
["docs/README.md", "tests/test_utils.py"]
# Result: SAFE, confidence: 95%

# MEDIUM_RISK - GitReviewBot review
["src/utils/helpers.py", "src/models/base.py"]
# Result: MEDIUM_RISK, confidence: 75%

# COMPLEX - Human approval required
["infrastructure/terraform/main.tf", "src/execution/trade_executor.py"]
# Result: COMPLEX, confidence: 90%
```

---

## Approval Workflow Steps

### Step 1: PR Detection

When a new PR is opened or updated:

1. The PR files are analyzed by the Path Analyzer
2. If any file matches COMPLEX patterns, the PR is flagged
3. The PR is labeled with `complex-path` and `awaiting-human-approval`

### Step 2: GitReviewBot Pre-Review

Before human notification:

1. GitReviewBot (ST-AUTO-003) performs a pre-review
2. The bot analyzes code quality, compliance, and potential issues
3. Results are posted as a PR comment
4. PR is labeled with `gitreviewbot-pre-reviewed`

**Why**: Humans should not review code that fails basic quality checks.

### Step 3: Discord Notification

Once pre-review passes:

1. A notification is sent to Discord `#approvals` channel
2. The message includes:
   - PR number and title
   - Author and branch
   - Risk classification and confidence
   - List of changed files
   - GitReviewBot status
   - Link to PR

**Example Notification**:

```
🚨 COMPLEX PR Requires Human Approval

PR #123: Update Terraform infrastructure
Author: developer1
Branch: feature/infra-update

Risk Classification:
- Level: COMPLEX
- Confidence: 95%
- Files Changed: 3

Files Changed:
- infrastructure/terraform/main.tf
- infrastructure/terraform/network.tf
- infrastructure/terraform/outputs.tf

GitReviewBot Status: ✅ Pre-review complete

Action Required: Please review and approve/reject this PR.
@approvers

🔗 View PR: http://gitea:3000/chiseai/chiseai/pulls/123
```

### Step 4: Human Review

Human reviewers must:

1. Review the PR changes thoroughly
2. Verify GitReviewBot findings
3. Check for security implications
4. Approve or reject via Gitea review

### Step 5: Approval Recording

When a human approves:

1. The approval is recorded in the audit log
2. PR label changes to `human-approved`
3. The PR can now proceed to merge

**Approval States**:

| State | Description | Can Merge? |
|-------|-------------|------------|
| `PENDING` | Awaiting human review | ❌ No |
| `APPROVED` | Human has approved | ✅ Yes |
| `REJECTED` | Human has rejected | ❌ No |
| `EMERGENCY_OVERRIDE` | Emergency bypass used | ✅ Yes (with post-hoc review) |
| `EXPIRED` | Approval timed out | ❌ No |

### Step 6: Merge

Once approved:

1. The PR can be merged (manually or via auto-merge)
2. Approval expires after 48 hours (configurable)
3. Post-merge, the audit trail is preserved

---

## Emergency Override Procedure

### When to Use Emergency Override

Emergency override is for **critical fixes only**:

- Production outage requiring immediate fix
- Security vulnerability requiring immediate patching
- Data corruption requiring immediate correction
- System failure blocking all work

### Authorization

Only specific users are authorized for emergency override:

- Configured in `emergency_approvers` list
- Typically: senior engineers, tech leads, on-call engineers

### Procedure

1. **Assess the Emergency**
   ```
   Is this truly critical?
   - Production down? YES
   - Security breach? YES
   - Minor bug? NO - use normal workflow
   ```

2. **Apply Emergency Override**
   ```python
   from scripts.pr_lifecycle.human_approval_workflow import emergency_approve_pr
   
   result = await emergency_approve_pr(
       pr_number=123,
       approver="admin1",
       justification="Production outage - database connection pool exhausted",
   )
   ```

3. **Document the Justification**
   - Be specific about the emergency
   - Include incident ticket numbers
   - Explain why normal workflow couldn't be used

4. **Merge Immediately**
   - The PR can now be merged
   - CI checks still run

5. **Schedule Post-Hoc Review**
   - Within 24 hours, schedule a retrospective review
   - Document lessons learned
   - Update procedures if needed

### Example Justification

```
Production database connection pool exhausted causing 500 errors
across all API endpoints. Incident #INC-2024-001. Emergency fix
increases pool size and adds connection timeout handling. Normal
approval workflow would take 2+ hours, causing extended outage.
```

### Post-Hoc Review Template

```markdown
## Post-Hoc Review: PR #123

**Emergency Override By**: @admin1
**Date**: 2024-01-15
**Incident**: INC-2024-001

### What Happened
[Describe the emergency]

### Why Emergency Override Was Used
[Justification]

### Was It Justified?
[ ] Yes - true emergency
[ ] No - could have used normal workflow

### Lessons Learned
- 
- 

### Process Improvements
- 
-
```

---

## Troubleshooting

### Issue: PR Not Flagged as COMPLEX

**Symptoms**: PR modifies infrastructure but not labeled as COMPLEX

**Diagnosis**:
```python
from scripts.pr_lifecycle.complex_path_gate import ComplexPathGate

gate = ComplexPathGate()
result = await gate.check_pr_status(pr_number=123)
print(result.to_dict())
```

**Solutions**:
1. Check Path Analyzer configuration
2. Verify file patterns in `config.yaml`
3. Manually add `complex-path` label

### Issue: Discord Notification Not Sent

**Symptoms**: COMPLEX PR not appearing in #approvals channel

**Diagnosis**:
```bash
# Check Discord client configuration
python -c "from discord_alerts.config import DiscordConfig; print(DiscordConfig.from_env())"
```

**Solutions**:
1. Verify `DISCORD_BOT_TOKEN` environment variable
2. Check Discord channel ID configuration
3. Review bot permissions in Discord
4. Check logs for connection errors

### Issue: GitReviewBot Pre-Review Failing

**Symptoms**: PR stuck waiting for GitReviewBot

**Diagnosis**:
```bash
# Check GitReviewBot status
python scripts/trigger_gitreviewbot.py --pr 123
```

**Solutions**:
1. Check Gitea API connectivity
2. Verify `GITEA_TOKEN` environment variable
3. Review GitReviewBot logs
4. Manually add `gitreviewbot-pre-reviewed` label to bypass

### Issue: Approval Not Recognized

**Symptoms**: Human approved PR but still blocked

**Diagnosis**:
```python
from scripts.pr_lifecycle.complex_path_gate import ComplexPathGate

gate = ComplexPathGate()
status, record = await gate._check_human_approval(123)
print(f"Status: {status}, Record: {record}")
```

**Solutions**:
1. Ensure approval was submitted via Gitea review (not just comment)
2. Check that approver has write access
3. Manually record approval:
   ```python
   await gate.record_human_approval(
       pr_number=123,
       approver="reviewer1",
       reason="Approved via Gitea",
   )
   ```

### Issue: Approval Expired

**Symptoms**: Previously approved PR now blocked

**Diagnosis**:
```bash
# Check audit log
grep '"pr_number": 123' data/complex_path_audit.log | tail -5
```

**Solutions**:
1. Re-approve the PR
2. Extend timeout: update `approval_timeout_hours` configuration
3. Emergency override if truly urgent

### Issue: Emergency Override Unauthorized

**Symptoms**: "Not authorized for emergency override" error

**Diagnosis**:
```python
gate = ComplexPathGate()
print(f"Emergency approvers: {gate.emergency_approvers}")
```

**Solutions**:
1. Add user to `emergency_approvers` list
2. Use normal approval workflow
3. Contact an authorized approver

---

## Human Gate Module (ST-AUTO-004)

The `human_gate.py` module provides a focused implementation for managing COMPLEX PR human approval with Redis integration.

### Key Features

- **Redis State Storage**: All approval states stored in Redis with configurable TTL
- **Discord Notifications**: Rich embed notifications to #pr-reviews channel
- **Reminder Scheduling**: Automatic reminders every 4 hours until reviewed
- **Emergency Override**: Authorized emergency bypass with audit logging

### Redis Key Schema

| Key Pattern | Type | Description |
|-------------|------|-------------|
| `bmad:chiseai:pr:human_gate:{pr_number}:status` | STRING | Current approval status |
| `bmad:chiseai:pr:human_gate:{pr_number}:reviewer` | STRING | Reviewer username |
| `bmad:chiseai:pr:human_gate:{pr_number}:timestamp` | STRING | ISO timestamp of last action |
| `bmad:chiseai:pr:human_gate:{pr_number}:emergency_override` | STRING | Emergency justification |
| `bmad:chiseai:pr:human_gate:{pr_number}:reminder_count` | STRING | Number of reminders sent |
| `bmad:chiseai:pr:human_gate:{pr_number}:history` | LIST | JSON history of all actions |

### Usage Examples

```python
from scripts.pr_lifecycle.human_gate import HumanGate

# Initialize gate
gate = HumanGate(
    discord_webhook_url="https://discord.com/api/webhooks/...",
    emergency_approvers=["admin1", "admin2"],
    approval_timeout_hours=48,
    reminder_interval_hours=4,
)

# Check PR status
result = await gate.check_pr_status(pr_number=123, files=["src/critical.py"])
print(f"Can merge: {result.can_merge}")

# Request human approval
await gate.request_approval(
    pr_number=123,
    pr_title="Critical infrastructure update",
    pr_author="developer1",
    pr_url="https://gitea.example.com/pr/123",
    files=["infrastructure/terraform/main.tf"],
    gitreviewbot_summary="GitReviewBot analysis here...",
)

# Record approval
await gate.record_approval(
    pr_number=123,
    approver="senior-reviewer",
    reason="Infrastructure changes look good",
)

# Emergency override (for critical hotfixes)
await gate.emergency_override(
    pr_number=123,
    approver="admin1",
    justification="Production outage requires immediate fix",
)
```

### CLI Usage

```bash
# Check PR status
python scripts/pr_lifecycle/human_gate.py 123 --files file1.py file2.py

# Dry run mode (no actual Discord notifications)
python scripts/pr_lifecycle/human_gate.py 123 --dry-run
```

### Escalation Templates

Discord notification templates are stored in:
- `scripts/pr_lifecycle/escalation_templates/initial_escalation.md`
- `scripts/pr_lifecycle/escalation_templates/reminder.md`
- `scripts/pr_lifecycle/escalation_templates/approval_confirmation.md`
- `scripts/pr_lifecycle/escalation_templates/rejection_notice.md`

---

## API Reference

### HumanGate

```python
class HumanGate:
    def __init__(
        self,
        redis_client=None,
        discord_webhook_url: str | None = None,
        emergency_approvers: list[str] | None = None,
        approval_timeout_hours: int = 48,
        reminder_interval_hours: int = 4,
        dry_run: bool = False,
    )
    
    async def check_pr_status(
        self, pr_number: int, files: list[str] | None = None
    ) -> HumanGateResult
    
    async def request_approval(
        self,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        files: list[str],
        gitreviewbot_summary: str | None = None,
    ) -> bool
    
    async def record_approval(
        self,
        pr_number: int,
        approver: str,
        reason: str | None = None,
    ) -> ApprovalRecord
    
    async def record_rejection(
        self,
        pr_number: int,
        reviewer: str,
        reason: str,
    ) -> ApprovalRecord
    
    async def record_changes_requested(
        self,
        pr_number: int,
        reviewer: str,
        comments: str,
    ) -> ApprovalRecord
    
    async def emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> ApprovalRecord
    
    async def send_reminder(self, pr_number: int) -> bool
    
    async def clear_approval_state(self, pr_number: int) -> bool
```

### ComplexPathGate

```python
class ComplexPathGate:
    def __init__(
        self,
        gitea_client: GiteaClient | None = None,
        audit_log_path: str | None = None,
        emergency_approvers: list[str] | None = None,
        approval_timeout_hours: int = 48,
    )
    
    def is_complex_classification(
        self, files: list[str]
    ) -> tuple[bool, RiskLevel, float]
    
    async def check_pr_status(
        self, pr_number: int
    ) -> ComplexPathCheckResult
    
    async def record_human_approval(
        self,
        pr_number: int,
        approver: str,
        reason: str | None = None,
    ) -> ApprovalRecord
    
    async def record_human_rejection(
        self,
        pr_number: int,
        approver: str,
        reason: str,
    ) -> ApprovalRecord
    
    async def emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> ApprovalRecord
    
    def get_audit_trail(
        self, pr_number: int | None = None
    ) -> list[ApprovalRecord]
```

### HumanApprovalWorkflow

```python
class HumanApprovalWorkflow:
    def __init__(
        self,
        gate: ComplexPathGate | None = None,
        gitea_client: GiteaClient | None = None,
        gitreviewbot: GitReviewBot | None = None,
        discord_client: DiscordClient | None = None,
        config: WorkflowConfig | None = None,
    )
    
    async def process_complex_pr(
        self, pr_number: int
    ) -> WorkflowResult
    
    async def process_emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> WorkflowResult
    
    async def poll_for_approvals(
        self, pr_numbers: list[int] | None = None
    ) -> list[WorkflowResult]
```

### CLI Usage

```bash
# Check PR status
python scripts/pr_lifecycle/complex_path_gate.py 123

# Process COMPLEX PR through workflow
python scripts/pr_lifecycle/human_approval_workflow.py 123

# Emergency override
python scripts/pr_lifecycle/human_approval_workflow.py 123 \
    --emergency \
    --approver admin1 \
    --justification "Critical production fix"
```

---

## Audit Trail

### Audit Log Format

The audit log is stored in JSON Lines format:

```json
{"pr_number": 123, "status": "approved", "approver": "reviewer1", "timestamp": "2024-01-15T10:30:00Z", "reason": "Looks good"}
{"pr_number": 124, "status": "emergency_override", "approver": "admin1", "timestamp": "2024-01-15T11:00:00Z", "emergency_justification": "Production outage", "post_hoc_review_required": true}
```

### Location

Default: `data/complex_path_audit.log`

Configurable via `audit_log_path` parameter.

### Retention

- Audit logs are **append-only**
- No automatic deletion
- Archive old logs periodically

### Querying Audit Trail

```python
from scripts.pr_lifecycle.complex_path_gate import ComplexPathGate

gate = ComplexPathGate()

# Get all approvals
all_approvals = gate.get_audit_trail()

# Get approvals for specific PR
pr_approvals = gate.get_audit_trail(pr_number=123)

# Filter by date
recent = [r for r in all_approvals if r.timestamp > datetime(2024, 1, 1)]

# Count emergency overrides
emergencies = [r for r in all_approvals if r.status == ApprovalStatus.EMERGENCY_OVERRIDE]
print(f"Emergency overrides this month: {len(emergencies)}")
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITEA_URL` | Gitea API base URL | `http://localhost:3000` |
| `GITEA_TOKEN` | Gitea API token | Required |
| `GITEA_OWNER` | Repository owner | `chiseai` |
| `GITEA_REPO` | Repository name | `chiseai` |
| `DISCORD_BOT_TOKEN` | Discord bot token | Required for notifications |
| `DISCORD_GUILD_ID` | Discord guild ID | Required for notifications |

### Workflow Configuration

```python
from scripts.pr_lifecycle.human_approval_workflow import WorkflowConfig

config = WorkflowConfig(
    poll_interval_seconds=60,
    max_poll_attempts=100,
    approval_timeout_hours=48,
    emergency_approvers=["admin1", "admin2", "oncall"],
    reminder_interval_hours=12,
    max_reminders=3,
)
```

---

## Related Documentation

- [Path Analyzer Documentation](../autonomous_git/path_analyzer/README.md)
- [GitReviewBot Documentation](../autonomous_git/gitreviewbot/README.md)
- [PR Lifecycle README](../../scripts/pr_lifecycle/README.md)

---

## Support

For issues or questions:

1. Check this runbook
2. Review logs in `data/complex_path_audit.log`
3. Contact: #dev-ops channel on Discord
4. Create issue with label `pr-lifecycle`
