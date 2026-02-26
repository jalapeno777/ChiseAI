# Rejection Notice Template

## Usage
This template is used for Discord notifications when a human rejects a COMPLEX PR.

## Variables
- `{{pr_number}}` - The PR number
- `{{pr_title}}` - PR title
- `{{reviewer}}` - Username of the rejecting reviewer
- `{{pr_url}}` - URL to the PR
- `{{reason}}` - Rejection reason (required)
- `{{timestamp}}` - Rejection timestamp
- `{{suggestions}}` - Optional suggestions for improvement

## Template

```markdown
❌ **PR Rejected**

**PR #{{pr_number}}**: {{pr_title}}
**Rejected By**: {{reviewer}}
**At**: {{timestamp}}

---

**Rejection Reason**:
{{reason}}

---

{{#if suggestions}}
**Suggestions for Improvement**:
{{suggestions}}
{{/if}}

---

This COMPLEX PR has been rejected and is blocked from merge.

**Next Steps**:
1. Address the feedback from the reviewer
2. Make necessary changes to the PR
3. Request re-review when ready

@{{pr_author}}

🔗 [View PR]({{pr_url}})
```

## Example Output

```markdown
❌ **PR Rejected**

**PR #123**: Update infrastructure/terraform for new VPC
**Rejected By**: senior-reviewer
**At**: 2026-02-25 14:30 UTC

---

**Rejection Reason**:
The VPC configuration has security concerns. The CIDR block overlaps with production, and the security group rules are too permissive.

---

**Suggestions for Improvement**:
- Use a non-overlapping CIDR block (10.1.0.0/16 instead of 10.0.0.0/16)
- Restrict security group ingress to specific IPs
- Add network ACLs for additional security layer
- Include terraform plan output in PR description

---

This COMPLEX PR has been rejected and is blocked from merge.

**Next Steps**:
1. Address the feedback from the reviewer
2. Make necessary changes to the PR
3. Request re-review when ready

@developer1

🔗 [View PR](https://gitea.example.com/craig/ChiseAI/pulls/123)
```

## Redis State Update

When rejection is recorded, the following Redis keys are updated:

- `bmad:chiseai:pr:human_gate:{pr_number}:status` = "rejected"
- `bmad:chiseai:pr:human_gate:{pr_number}:reviewer` = "{reviewer}"
- `bmad:chiseai:pr:human_gate:{pr_number}:timestamp` = "{timestamp}"

## Merge Eligibility

After rejection:
- ❌ PR is blocked from merge
- ❌ Automerge disabled
- 📝 Author must address feedback and request re-review
- 🔄 State resets to "pending" when new commits are pushed
