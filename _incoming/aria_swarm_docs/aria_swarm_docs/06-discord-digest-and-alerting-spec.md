# Discord Digest and Alerting Specification

## Goal
Notify Craig about meaningful memory, belief, lesson, and governance changes at the right urgency level.

## 1. Routing rules
### Daily digest
- send once daily at 8:00 PM America/Toronto
- include low and medium items by default
- may include high items that were already immediately alerted, if useful for summary

### Immediate alert
Send immediately for:
- any high-severity event
- any critical-severity event
- any approval request
- any attempted change touching soul items, core values, PRD objectives, or other approval-gated fields

## 2. Digest contents
Required sections:
1. summary line
2. new beliefs added
3. beliefs updated
4. lessons promoted
5. lessons deprecated
6. contradictions detected and resolutions
7. memories archived or consolidated
8. blocked items awaiting Craig approval
9. top 3 things Aria learned today

## 3. Alert payload fields
All digest items and immediate alerts should include:
- severity
- short title
- what changed
- why it changed
- evidence summary
- whether approval is needed
- link or reference to audit record if available
- timestamp in America/Toronto

## 4. Severity interpretation
### Low
Minor preference refinement or weak observation.

### Medium
Useful new belief, recurring pattern, lesson promotion/deprecation, tool preference change.

### High
Execution, planning, coordination, or memory-integrity impact.

### Critical
Identity, PRD, governance, safety conflict, or harmful autonomous behavior risk.

## 5. Delivery reliability
Required behavior:
- failed sends should retry
- failures should be logged
- repeated failures should raise a higher-severity operational event
- duplicate sends should be deduplicated by event id where possible

## 6. Daily digest generation flow
1. collect all digest-eligible events for the local day
2. group by event type
3. summarize repetitive items
4. sort by severity then time
5. render digest payload
6. send to Discord at scheduled time
7. write digest audit entry

## 7. Immediate alert flow
1. event created
2. severity and approval status computed
3. immediate routing rules evaluated
4. alert sent to Discord
5. send outcome logged
6. if failed, retry and escalate operationally if needed

## 8. Approval request wording guidance
Approval alerts should clearly say:
- what protected item Aria wants to change
- why the change is proposed
- what evidence supports it
- what happens if the change is not approved

## 9. Timezone rule
All scheduling must use `America/Toronto` timezone logic rather than hardcoded EDT offsets.
