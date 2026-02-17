---
# Post-Mortem Template for ChiseAI
# Copy this file when creating a new post-mortem and fill in all sections

incident_id: "PM-YYYY-MM-DD-NNN"
date: "YYYY-MM-DDTHH:MM:SSZ"
severity: P1  # P0=Critical, P1=High, P2=Medium, P3=Low
story_id: "ST-XXX-NNN"
batch: "Batch-N-description"
scope_globs: []
---

# Post-Mortem: [Brief Title]

## Summary

A brief, one-paragraph summary of what happened, the impact, and the resolution.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| YYYY-MM-DDTHH:MM:SSZ | Incident started / first symptom observed |
| YYYY-MM-DDTHH:MM:SSZ | Detection / alert triggered |
| YYYY-MM-DDTHH:MM:SSZ | Investigation began |
| YYYY-MM-DDTHH:MM:SSZ | Root cause identified |
| YYYY-MM-DDTHH:MM:SSZ | Resolution implemented |
| YYYY-MM-DDTHH:MM:SSZ | Service fully restored / incident closed |

## Root Cause

### Symptom
What was observed? What failed? What error messages appeared?

### Underlying Cause
Why did this happen? Use the "5 Whys" technique to dig deep:
1. Why did X happen? → Because Y
2. Why did Y happen? → Because Z
3. ...continue until you reach the root cause

### Missed Signals
What warning signs were present but not acted upon? What could have prevented this?

## Impact

### Affected Systems/Services
- List affected components
- List affected users/stories

### Quantified Impact
- Duration of outage/degradation
- Number of affected operations/users
- Data loss (if any)
- Development time lost

## Resolution

### Immediate Fix
What was done to restore service/fix the immediate problem?

### Verification
How was it confirmed that the fix worked?

## Prevention

### Immediate Actions
- [ ] Action item 1 (Owner: @username, Due: YYYY-MM-DD)
- [ ] Action item 2 (Owner: @username, Due: YYYY-MM-DD)

### Process/Tooling Improvements
- [ ] Skill/command update needed
- [ ] Automation/monitoring improvement
- [ ] Documentation update

### Prevention Rules
Specific rules or guidelines that, if followed, would prevent recurrence:

```
Rule: [Brief rule name]
When: [Context where rule applies]
Then: [What must be done]
```

## Follow-up Tasks

- [ ] Schedule post-mortem meeting (if not done)
- [ ] Share learnings with team
- [ ] Update relevant documentation
- [ ] Create tickets for prevention actions
- [ ] Review similar systems for same vulnerability

## Lessons Learned

### What Went Well
- 

### What Could Be Better
- 

### Key Insights
- 

---

## Blameless Culture Reminder

This post-mortem follows the ChiseAI blameless culture:

- Focus on system/process failures, not individual blame
- Ask "How did the process allow this?" not "Why did YOU do that?"
- Look for patterns across incidents
- Thank people for admitting mistakes and sharing learnings

**Remember:** The goal is learning and prevention, not blame.

---

## Metadata

| Field | Value |
|-------|-------|
| Incident ID | PM-YYYY-MM-DD-NNN |
| Created | YYYY-MM-DD |
| Severity | P0/P1/P2/P3 |
| Story | ST-XXX-NNN |
| Lead Investigator | @username |
| Reviewers | @username1, @username2 |
| Status | Draft / In Review / Complete |
