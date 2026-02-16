---
name: "chise-postmortem-create"
description: "ChiseAI: create a structured post-mortem document from an incident."
disable-model-invocation: false
---

Create a blameless post-mortem to learn from incidents.

## When To Use

- After P0 or P1 incidents (required)
- After significant process failures
- When patterns emerge from multiple small issues

## Prerequisites

1. Incident already logged via `chise-incident-log.md`
2. Issue has been resolved
3. Within 24-48 hours of resolution

## Execution

### Create from Existing Incident
```bash
python3 scripts/incident/create_postmortem.py \
    --story-id="ST-NS-016" \
    --output="docs/postmortems/2026-02-16-ST-NS-016.md"
```

### Interactive Creation
```bash
python3 scripts/incident/create_postmortem.py --interactive
```

## Post-Mortem Document Structure

```markdown
# Post-Mortem: [Title]

## Metadata
- **Incident**: ST-NS-016
- **Severity**: P1
- **Date**: 2026-02-16
- **Duration**: 2 hours
- **Owner**: [Name]

## Summary
One-paragraph overview of what happened.

## Timeline
| Time | Event |
|------|-------|
| 10:00 | CI started failing |
| 10:30 | Root cause identified |
| 11:00 | Issue resolved |

## Root Cause Analysis
### 5 Whys
1. Why did CI fail? → Merge conflict
2. Why was there a conflict? → Two workers edited same file
3. Why did they edit same file? → Overlapping SCOPE_GLOBS
4. Why were scopes overlapping? → Jarvis didn't check
5. Why didn't Jarvis check? → Not in delegation checklist

### Root Cause
Jarvis delegated parallel work without verifying scope disjointness.

## Impact
- PR #234 delayed 2 hours
- 2 developer hours lost
- Batch 4 integration delayed

## Resolution
Re-planned with sequential integration.

## Prevention Measures
- [ ] Update chiseai-worker-contracts skill
- [ ] Add ownership check to pre-edit checklist
- [ ] Consider automated overlap detection

## Lessons Learned
- Parallel work requires strict boundaries
- 5-minute check saves 2 hours

## Action Items
| Task | Owner | Due Date |
|------|-------|----------|
| Update skill | Jarvis | 2026-02-17 |
| Update checklist | SeniorDev | 2026-02-17 |
```

## Review Process

1. Draft post-mortem
2. Review with team (15 min meeting or async)
3. Update based on feedback
4. Store in docs/postmortems/
5. Share learnings (Discord/docs)

## Related
- `.opencode/skills/chiseai-incident-response/SKILL.md`
- `.opencode/command/chise-incident-log.md`
