---
name: "chise-incident-log"
description: "ChiseAI: log a structured incident for tracking and post-mortem analysis."
disable-model-invocation: true
---

Log a structured incident to Redis and markdown fallback.

## Execution

### Interactive Mode
```bash
python3 scripts/incident/log_incident.py --interactive
```

### Command Line
```bash
python3 scripts/incident/log_incident.py \
    --story-id="ST-NS-016" \
    --severity="P1" \
    --symptom="Two workers had merge conflict on grammar.py" \
    --root-cause="Jarvis delegated overlapping scopes" \
    --prevention="Workers must check ownership before edits"
```

## Required Fields

- story_id: Affected story
- severity: P0/P1/P2/P3
- symptom: What went wrong
- root_cause: Why it happened
- prevention_rule: How to prevent

## Optional Fields

- scope_globs: Affected code areas
- timeline: JSON array of events
- impact: Description of effects
- resolution: How it was fixed
- follow_up_tasks: Action items

## Storage

Logs to:
1. Redis: bmad:chiseai:iterlog:story:[id]:incidents
2. Markdown: docs/tempmemories/iterlog-[id].md (fallback)

## Related
- `.opencode/skills/chiseai-incident-response/SKILL.md`
- `.opencode/command/chise-postmortem-create.md`
