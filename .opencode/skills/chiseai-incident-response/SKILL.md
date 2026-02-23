---
name: chiseai-incident-response
description: Structured incident logging, response procedures, and post-mortem process for learning from failures.
metadata:
  version: "2.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-incident-response

## Goal

Turn failures into learning opportunities through structured incident logging and blameless post-mortems.

## When To Use

- Merge conflicts in parallel work
- CI regressions
- Unexpected system failures
- Process breakdowns
- Any "this shouldn't have happened" moment

## What is a Post-Mortem?

A structured review AFTER something goes wrong. NOT about blame - about learning.

Process:
1. Incident occurs
2. Fix the immediate problem
3. Schedule post-mortem (within 24-48 hours)
4. Document what happened and why
5. Identify prevention measures
6. Share learnings with team

## Incident Severity Levels

### P0 - Critical
- Blocks main branch
- Production outage
- Data loss risk
- Response: Immediate, post-mortem within 4 hours

### P1 - High
- Blocks story delivery
- Significant functionality broken
- Response: Same-day fix, post-mortem within 24 hours

### P2 - Medium
- Degraded experience
- Workaround available
- Response: Fix in current sprint, post-mortem optional

### P3 - Low
- Process improvement opportunity
- Minor inconvenience
- Response: Track for trends, no immediate post-mortem

## Incident Logging Template

```markdown
INCIDENT:
  story_id: ST-NS-016
  batch: Batch-4-integration
  scope_globs: ["src/neuro_symbolic/evolution/", "src/strategy/dsl/"]
  severity: P1
  
  timeline:
    - "2026-02-16T10:00:00Z": "CI started failing on PR #234"
    - "2026-02-16T10:30:00Z": "Root cause identified: overlapping ownership"
    - "2026-02-16T11:00:00Z": "Fixed by re-planning with sequential integration"
  
  symptom: |
    Two workers (senior-dev and dev) both modified strategy/dsl/grammar.py
    Merge conflict prevented PR #234 from passing CI
  
  root_cause: |
    Jarvis delegated parallel work without checking scope overlap.
    Both workers had SCOPE_GLOBS that included the same file.
  
  missed_signal: |
    Redis ownership check would have caught this BEFORE edits.
    The chise-check-ownership command was not run by workers.
  
  impact:
    - "PR #234 delayed 2 hours"
    - "2 developer hours lost to conflict resolution"
    - "Batch 4 integration delayed"
  
  resolution:
    "Re-planned with sequential integration. First worker completed,
    merged to main, then second worker rebased and completed."
  
  prevention_rule: |
    Workers MUST run chise-check-ownership before edits.
    Jarvis MUST verify SCOPE_GLOBS don't overlap for parallel work.
  
  follow_up_tasks:
    - "Update chiseai-worker-contracts skill to emphasize ownership check"
    - "Add ownership check to pre-edit checklist"
    - "Review: Should we add automated overlap detection?"
  
  lessons_learned:
    - "Parallel work requires strict scope boundaries"
    - "Assumptions about 'disjoint' scopes need verification"
    - "5-minute ownership check saves 2 hours of conflict resolution"
```

## Redis Storage

```python
# Log incident
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-NS-016:incidents",
    value=json.dumps(incident_data)
)

# Track post-mortem completion
redis_state_hset(
    name="bmad:chiseai:postmortems:2026-02",
    key="ST-NS-016",
    value='{"completed": "2026-02-16T15:00:00Z", "severity": "P1"}'
)
```

## Post-Mortem Meeting Structure (15-30 min)

### Participants
- Incident owner (who fixed it)
- Jarvis (orchestrator at time of incident)
- Any affected workers
- Optional: Observer for pattern recognition

### Agenda
1. **Timeline Review** (5 min) - What happened when?
2. **Root Cause** (5 min) - Why did it happen? (5 Whys technique)
3. **Impact Assessment** (3 min) - What was affected?
4. **Prevention Rules** (10 min) - How do we prevent recurrence?
5. **Action Items** (5 min) - Who does what by when?

### Output
- Incident log entry (filled out completely)
- Updated skill/command if process gap found
- Shared with team (can be async via Discord/docs)

## Blameless Culture Rules

✅ DO:
- Focus on system/process failures
- Ask "How did the process allow this?"
- Look for patterns across incidents
- Thank people for admitting mistakes

❌ DON'T:
- Name names or assign blame
- Ask "Why did YOU do that?"
- Hide incidents to avoid embarrassment
- Skip post-mortems for "small" issues

## Templates

### Template 1: Full Incident Report

```markdown
# Incident Report: [INCIDENT-ID]

## Classification
- **Severity**: P0 / P1 / P2 / P3
- **Story ID**: [ST-XXX]
- **Batch/Phase**: [if applicable]
- **Status**: Active / Resolved / Post-Mortem Scheduled / Closed

## Summary
[One or two sentences describing what happened]

## Timeline (UTC)
| Time | Event | Actor |
|------|-------|-------|
| [timestamp] | [what happened] | [who/what] |
| [timestamp] | [what happened] | [who/what] |

## Impact
- **Users Affected**: [number or "internal only"]
- **Duration**: [time from start to resolution]
- **Data Loss**: [yes/no, extent]
- **Revenue Impact**: [if applicable]

## Root Cause Analysis

### Immediate Cause
[What directly caused the incident]

### Contributing Factors
1. [Factor 1]
2. [Factor 2]

### 5 Whys
1. Why did [symptom] happen? → [Answer 1]
2. Why did [Answer 1] happen? → [Answer 2]
3. Why did [Answer 2] happen? → [Answer 3]
4. Why did [Answer 3] happen? → [Answer 4]
5. Why did [Answer 4] happen? → [Root Cause]

## Detection
- **How Detected**: [monitoring/user report/CI/other]
- **Time to Detect**: [duration]
- **Alerting Gaps**: [what alerts should have fired]

## Response
- **Initial Response Time**: [duration from detection]
- **Responders**: [who helped]
- **Resolution Time**: [total duration]

## Resolution
[Description of how the issue was fixed]

## Prevention Measures
| Measure | Owner | Due Date | Status |
|---------|-------|----------|--------|
| [measure 1] | [owner] | [date] | [status] |
| [measure 2] | [owner] | [date] | [status] |

## Lessons Learned
1. [Lesson 1]
2. [Lesson 2]

## Appendix
- Links to related PRs, logs, screenshots
- Slack/Discord conversation snippets (anonymized)
```

### Template 2: Quick Incident Log

```markdown
# Quick Incident Log

INCIDENT:
  id: [INC-XXX]
  story_id: [ST-XXX]
  severity: [P0-P3]
  detected: [timestamp]
  resolved: [timestamp]
  
  symptom: |
    [What was observed - be specific]
  
  root_cause: |
    [Why it happened - one or two sentences]
  
  resolution: |
    [How it was fixed]
  
  prevention: |
    [How to prevent in future]
  
  redis_key: bmad:chiseai:iterlog:story:[ST-XXX]:incidents
```

### Template 3: Post-Mortem Agenda

```markdown
# Post-Mortem Agenda

## Meeting Info
- **Incident**: [INC-XXX]
- **Date**: [scheduled date]
- **Duration**: 15-30 minutes
- **Participants**: [list]

## Pre-Meeting Prep (by incident owner)
- [ ] Timeline compiled
- [ ] Root cause documented
- [ ] Impact quantified
- [ ] Initial prevention ideas

## Agenda

### 1. Timeline Walkthrough (5 min)
- Incident owner presents timeline
- Clarifying questions only

### 2. Root Cause Deep Dive (5 min)
- Present 5 Whys analysis
- Discuss contributing factors

### 3. Impact Review (3 min)
- Quantify impact
- Identify any missed detection

### 4. Prevention Rules (10 min)
- Brainstorm prevention measures
- Prioritize by impact vs effort

### 5. Action Items (5 min)
- Assign owners
- Set due dates

## Outputs
- [ ] Updated incident report
- [ ] Prevention rules documented
- [ ] Action items assigned
- [ ] Knowledge shared (Discord/wiki)
```

### Template 4: Incident Trend Analysis

```markdown
# Incident Trend Analysis - [Month/Quarter]

## Summary
- **Total Incidents**: [N]
- **By Severity**: P0: [n], P1: [n], P2: [n], P3: [n]
- **Average Resolution Time**: [duration]
- **Post-Mortem Completion Rate**: [%]

## Top Categories
| Category | Count | Example |
|----------|-------|---------|
| [category] | [n] | [INC-XXX] |
| [category] | [n] | [INC-XXX] |

## Patterns Identified
1. **Pattern**: [description]
   - Incidents: [list]
   - Common factor: [factor]
   - Recommended action: [action]

2. **Pattern**: [description]
   - Incidents: [list]
   - Common factor: [factor]
   - Recommended action: [action]

## Prevention Effectiveness
| Measure | Incidents Before | Incidents After |
|---------|------------------|-----------------|
| [measure] | [n] | [n] |

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
```

## Examples

### Example 1: Merge Conflict Incident (P1)

**Context**: Two workers edited the same file in parallel

**Incident Log**:

```markdown
INCIDENT:
  id: INC-2026-002
  story_id: ST-DSL-042
  batch: Batch-3-dsl
  severity: P1
  detected: 2026-02-23T10:00:00Z
  resolved: 2026-02-23T12:30:00Z
  
  symptom: |
    CI failed on PR #234 with merge conflict in src/strategy/dsl/grammar.py
    Both senior-dev-A and senior-dev-B modified lines 45-52
  
  root_cause: |
    Jarvis delegated parallel work with overlapping SCOPE_GLOBS
    Both workers had "src/strategy/dsl/" in scope
  
  missed_signal: |
    chise-check-ownership would have shown the file was being edited
    Neither worker ran ownership check before editing
  
  impact:
    - "PR #234 delayed 2.5 hours"
    - "Required manual conflict resolution"
    - "Batch 3 integration delayed by half day"
  
  resolution: |
    1. senior-dev-A's work merged first (was more complete)
    2. senior-dev-B rebased and resolved conflicts
    3. Re-ran CI validation
  
  prevention: |
    1. Workers MUST run chise-check-ownership before any edits
    2. Jarvis MUST verify SCOPE_GLOBS overlap before parallel delegation
    3. Add file-level ownership tracking (not just directory)
  
  lessons_learned:
    - "Directory-level scope is too coarse for parallel work"
    - "Ownership check takes 30 seconds, saves hours of conflict resolution"
    - "Consider pre-edit hooks that check ownership automatically"
```

**Post-Mortem Outcome**:
- Updated chiseai-worker-contracts to require ownership check
- Added ownership check to precommit-gates
- File-level ownership tracking added to roadmap

### Example 2: CI Regression Incident (P2)

**Context**: Tests started failing after dependency update

**Incident Log**:

```markdown
INCIDENT:
  id: INC-2026-003
  story_id: N/A (infrastructure)
  severity: P2
  detected: 2026-02-23T14:00:00Z
  resolved: 2026-02-23T15:30:00Z
  
  symptom: |
    All PRs failing CI with numpy-related test errors
    Error: "module 'numpy' has no attribute 'float'"
  
  root_cause: |
    numpy 2.0 removed np.float alias (was deprecated)
    CI environment auto-updated to numpy 2.0
    Code still used np.float
  
  missed_signal: |
    No pinning of numpy version in requirements.txt
    No deprecation warning tests
  
  resolution: |
    1. Pinned numpy<2.0 in requirements.txt
    2. Updated code to use float instead of np.float
    3. Added test for numpy version compatibility
  
  prevention: |
    1. Pin all dependency versions
    2. Add deprecation warning tests
    3. Consider dependabot for controlled updates
  
  lessons_learned:
    - "Always pin dependency versions"
    - "Deprecation warnings are signals, not noise"
    - "Test environment should match production"
```

### Example 3: Production Configuration Incident (P0)

**Context**: Wrong configuration deployed to production

**Incident Log**:

```markdown
INCIDENT:
  id: INC-2026-001
  story_id: ST-DEPLOY-005
  severity: P0
  detected: 2026-02-22T09:15:00Z
  resolved: 2026-02-22T09:45:00Z
  
  symptom: |
    Trading engine started using testnet credentials in production
    Detected by monitoring alert: "API endpoint mismatch"
  
  root_cause: |
    Configuration file not properly templated during deployment
    ENV variable substitution failed silently
    Default value was testnet instead of mainnet
  
  timeline:
    - "09:00": "Deployment completed"
    - "09:05": "Trading engine started with wrong config"
    - "09:15": "Monitoring alert fired"
    - "09:20": "On-call identified issue"
    - "09:30": "Hotfix deployed"
    - "09:45": "Verified correct operation"
  
  impact:
    - "No actual trades executed (caught early)"
    - "30 minutes of potential trading time lost"
    - "Team incident response activated"
  
  resolution: |
    1. Immediate: Hotfix with correct configuration
    2. Verification: Confirmed mainnet endpoints active
    3. Follow-up: Added configuration validation step
  
  prevention: |
    1. Configuration validation in CI (fail if ENV missing)
    2. Remove testnet defaults from production configs
    3. Add startup check for API endpoint sanity
    4. Pre-deployment configuration diff review
  
  lessons_learned:
    - "Silent failures in config substitution are dangerous"
    - "Default values should be safe (fail closed)"
    - "Monitoring caught this quickly - good investment"
```

## When Not To Use

- Expected errors (handled by normal error handling)
- External service outages (track separately)
- Planned maintenance events
- Minor warnings that don't impact delivery

## Exit Conditions

- Incident logged with all required fields.
- Severity assigned appropriately.
- Resolution documented.
- Prevention rules identified.
- Follow-up tasks assigned.

## Troubleshooting/Safety

- **Incomplete incident log**: Do not close incident until all fields filled.
- **Severity mismatch**: Escalate to Jarvis for severity review.
- **No prevention rule**: Incident not fully understood; continue analysis.
- **Recurring pattern**: Flag for process improvement; update skills.

## Related Skills

- `chiseai-parallel-safety` - Prevents incidents via ownership
- `chiseai-worker-contracts` - Defines incident template in contracts
- `chiseai-memory-ops` - Redis storage for incidents

## Related Commands

- `.opencode/command/chise-incident-log.md`
- `.opencode/command/chise-postmortem-create.md`
- `.opencode/command/chise-append-incident.md`
