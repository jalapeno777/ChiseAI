# Initial Escalation Message Template

## Usage
This template is used for the initial Discord notification when a COMPLEX PR requires human approval.

## Variables
- `{{pr_number}}` - The PR number
- `{{pr_title}}` - PR title
- `{{pr_author}}` - PR author username
- `{{pr_url}}` - URL to the PR
- `{{pr_branch}}` - Branch name
- `{{files_count}}` - Number of files changed
- `{{files_list}}` - List of files (formatted)
- `{{risk_level}}` - Risk classification (COMPLEX)
- `{{confidence}}` - Classification confidence (percentage)
- `{{gitreviewbot_summary}}` - GitReviewBot pre-review summary

## Template

```markdown
🚨 **COMPLEX PR Requires Human Approval**

**PR #{{pr_number}}**: {{pr_title}}
**Author**: {{pr_author}}
**Branch**: `{{pr_branch}}`

---

**Risk Classification**:
- Level: 🔴 {{risk_level}}
- Confidence: {{confidence}}%
- Files Changed: {{files_count}}

**Files Changed**:
{{files_list}}

---

**GitReviewBot Pre-Review**:
{{gitreviewbot_summary}}

---

**Action Required**: Please review and approve/reject this PR.

**Review Options**:
- ✅ **Approve** - Merge allowed
- ❌ **Reject** - PR blocked, author notified
- 📝 **Request Changes** - PR needs updates

@here

🔗 [View PR]({{pr_url}})
```

## Example Output

```markdown
🚨 **COMPLEX PR Requires Human Approval**

**PR #123**: Update infrastructure/terraform for new VPC
**Author**: developer1
**Branch**: `feature/infra-vpc-update`

---

**Risk Classification**:
- Level: 🔴 COMPLEX
- Confidence: 95%
- Files Changed: 5

**Files Changed**:
- `infrastructure/terraform/main.tf`
- `infrastructure/terraform/network.tf`
- `infrastructure/terraform/variables.tf`
- `.woodpecker.yml`
- `src/execution/trade_executor.py`

---

**GitReviewBot Pre-Review**:
✅ **Decision**: COMMENT (confidence: 85%)

**Summary**:
This PR modifies critical infrastructure components. Key changes:
- VPC configuration updates
- CI pipeline modifications
- Execution engine changes

**Recommendations**:
- Review by infrastructure team required
- Test in staging environment first
- Verify rollback procedures

---

**Action Required**: Please review and approve/reject this PR.

**Review Options**:
- ✅ **Approve** - Merge allowed
- ❌ **Reject** - PR blocked, author notified
- 📝 **Request Changes** - PR needs updates

@here

🔗 [View PR](https://gitea.example.com/craig/ChiseAI/pulls/123)
```
