# Swarm Lessons

Purpose: durable, actionable lessons that improve future execution quality.

## Usage Rules

- Aria/Jarvis must read relevant lessons at session start.
- Workers should emit `LESSON_CANDIDATE` packets; Jarvis is the single writer for final entries.
- Every lesson must be testable and traceable to evidence.
- Prefer concise rules over narrative retrospectives.

## Rule Template

```text
LESSON
- id: LESSON-<YYYYMMDD>-<slug>
- context:
- trigger:
- actionable_rule:
- applies_to:
  - aria|jarvis|quickdev|dev|senior-dev|merlin|critic
- expected_outcome:
- evidence_ref:
- added_utc:
- supersedes: <optional lesson id>
```

## Lessons

<!-- Append new LESSON blocks below this line. -->
