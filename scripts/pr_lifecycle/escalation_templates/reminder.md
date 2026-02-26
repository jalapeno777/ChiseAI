# Reminder Message Template

## Usage
This template is used for reminder notifications sent every 4 hours until a COMPLEX PR is reviewed.

## Variables
- `{{pr_number}}` - The PR number
- `{{pr_title}}` - PR title
- `{{pr_author}}` - PR author username
- `{{pr_url}}` - URL to the PR
- `{{reminder_count}}` - Which reminder this is (1, 2, 3, etc.)
- `{{hours_pending}}` - How many hours the PR has been pending
- `{{files_count}}` - Number of files changed
- `{{risk_level}}` - Risk classification

## Template

```markdown
⏰ **Reminder #{{reminder_count}}: PR Awaiting Human Approval**

**PR #{{pr_number}}**: {{pr_title}}
**Author**: {{pr_author}}
**Pending For**: {{hours_pending}} hours

---

**Risk Level**: 🔴 {{risk_level}}
**Files**: {{files_count}} files changed

---

This COMPLEX PR has been waiting for human review for **{{hours_pending}} hours**.

**Action Required**: Please review and provide feedback.

@here

🔗 [View PR]({{pr_url}})
```

## Example Output

```markdown
⏰ **Reminder #2: PR Awaiting Human Approval**

**PR #123**: Update infrastructure/terraform for new VPC
**Author**: developer1
**Pending For**: 8 hours

---

**Risk Level**: 🔴 COMPLEX
**Files**: 5 files changed

---

This COMPLEX PR has been waiting for human review for **8 hours**.

**Action Required**: Please review and provide feedback.

@here

🔗 [View PR](https://gitea.example.com/craig/ChiseAI/pulls/123)
```

## Reminder Schedule

- **Reminder 1**: 4 hours after initial escalation
- **Reminder 2**: 8 hours after initial escalation
- **Reminder 3**: 12 hours after initial escalation
- **Subsequent reminders**: Every 4 hours until reviewed or timeout

## Timeout

After 48 hours without approval, the approval request expires and the PR is blocked from merge until re-approved.
