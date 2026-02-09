---
name: "chise-append-incident"
description: "ChiseAI: append an incident entry (Redis list + tempmemories fallback)"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Preconditions
   - You MUST have a `story_id`.
   - You MUST have a filled `INCIDENT_TEMPLATE` (from `jarvis`).

2. Append incident
   - Run:
     - `python3 scripts/iterlog_ops.py append-incident --story-id=<story_id> --text "<paste incident text>"`
   - Note: the helper will append to markdown fallback even when Redis works.

3. Evidence
   - Record the command output under Evidence (iterlog and/or worker report).

