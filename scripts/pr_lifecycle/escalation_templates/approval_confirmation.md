# Approval Confirmation Template

## Usage
This template is used for Discord notifications when a human approves a COMPLEX PR.

## Variables
- `{{pr_number}}` - The PR number
- `{{pr_title}}` - PR title
- `{{approver}}` - Username of the approving reviewer
- `{{pr_url}}` - URL to the PR
- `{{reason}}` - Optional approval reason
- `{{timestamp}}` - Approval timestamp

## Template

```markdown
✅ **PR Approved**

**PR #{{pr_number}}**: {{pr_title}}
**Approved By**: {{approver}}
**At**: {{timestamp}}

---

{{#if reason}}
**Approval Reason**:
{{reason}}
{{/if}}

---

This COMPLEX PR has been approved and is now eligible for merge.

🔗 [View PR]({{pr_url}})
```

## Example Output

```markdown
✅ **PR Approved**

**PR #123**: Update infrastructure/terraform for new VPC
**Approved By**: senior-reviewer
**At**: 2026-02-25 14:30 UTC

---

**Approval Reason**:
Infrastructure changes look good. Tested in staging environment successfully. VPC configuration is correct and follows best practices.

---

This COMPLEX PR has been approved and is now eligible for merge.

🔗 [View PR](https://gitea.example.com/craig/ChiseAI/pulls/123)
```

## Redis State Update

When approval is recorded, the following Redis keys are updated:

- `bmad:chiseai:pr:human_gate:{pr_number}:status` = "approved"
- `bmad:chiseai:pr:human_gate:{pr_number}:reviewer` = "{approver}"
- `bmad:chiseai:pr:human_gate:{pr_number}:timestamp` = "{timestamp}"

## Merge Eligibility

After approval:
- ✅ PR is eligible for merge
- ✅ Automerge can proceed (if enabled)
- ✅ No further human approval required (unless new commits are pushed)
