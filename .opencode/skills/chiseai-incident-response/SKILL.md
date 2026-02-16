---
name: chiseai-incident-response
description: Structured incident logging, response procedures, and post-mortem process for learning from failures.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
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

## Related Commands
- `.opencode/command/chise-incident-log.md`
- `.opencode/command/chise-postmortem-create.md`
- `.opencode/command/chise-append-incident.md`
