# Post-Mortems Directory

This directory contains post-mortem reports for incidents within the ChiseAI project.

## Purpose

Post-mortems are structured reviews conducted AFTER something goes wrong. They are:

- **Blameless** - Focus on system/process failures, not individual blame
- **Learning-focused** - Identify root causes and prevention measures
- **Action-oriented** - Produce concrete follow-up tasks to prevent recurrence

## When to Create a Post-Mortem

| Severity | Trigger | Timeline |
|----------|---------|----------|
| **P0 - Critical** | Production outage, data loss risk, main branch blocked | Within 4 hours |
| **P1 - High** | Significant functionality broken, story delivery blocked | Within 24 hours |
| **P2 - Medium** | Degraded experience, workaround available | Optional, within sprint |
| **P3 - Low** | Process improvement opportunity | Track for trends |

## Directory Structure

```
docs/postmortems/
├── template.md          # Copy this to create new post-mortems
├── README.md            # This file
├── .gitkeep            # Ensures directory is tracked by git
└── PM-YYYY-MM-DD-NNN.md # Individual post-mortem reports
```

## Creating a New Post-Mortem

1. Copy `template.md` to a new file: `PM-YYYY-MM-DD-NNN.md`
   - Use format: `PM-YYYY-MM-DD-NNN` where NNN is a sequential number
   - Example: `PM-2026-02-17-001.md`

2. Fill in all sections of the template

3. Update the YAML frontmatter with incident details

4. Submit for review via PR

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

## Blameless Culture Rules

### DO:
- Focus on system/process failures
- Ask "How did the process allow this?"
- Look for patterns across incidents
- Thank people for admitting mistakes

### DON'T:
- Name names or assign blame
- Ask "Why did YOU do that?"
- Hide incidents to avoid embarrassment
- Skip post-mortems for "small" issues

## Related Resources

- **Skill**: `chiseai-incident-response` - Structured incident logging procedures
- **Command**: `chise-incident-log` - Log an incident
- **Command**: `chise-postmortem-create` - Create a post-mortem
- **Command**: `chise-append-incident` - Append to an existing incident log

## Incident Severity Levels

### P0 - Critical
- Blocks main branch
- Production outage
- Data loss risk
- **Response:** Immediate, post-mortem within 4 hours

### P1 - High
- Blocks story delivery
- Significant functionality broken
- **Response:** Same-day fix, post-mortem within 24 hours

### P2 - Medium
- Degraded experience
- Workaround available
- **Response:** Fix in current sprint, post-mortem optional

### P3 - Low
- Process improvement opportunity
- Minor inconvenience
- **Response:** Track for trends, no immediate post-mortem

---

*Last updated: 2026-02-17*
