# OpenCode Cache-Friendly Orchestrator Prompt Pattern

## Objective
Increase throughput while preserving safety and review quality by maximizing prompt-prefix reuse.

## Key rule
Keep the first part of orchestrator prompts stable across calls.

## Template
Use this exact block order:

1. `POLICY_PREFIX` (stable)
- role
- guardrails
- merge/CI/scope-lock rules
- escalation rules

2. `OUTPUT_SCHEMA` (stable)
- required fields
- evidence format
- acceptance criteria mapping format

3. `TASK_CONTEXT` (dynamic)
- story id, scope, changed files, blockers
- latest evidence and deltas only

4. `REQUEST` (dynamic)
- what decision/action is needed now

## Do
- Keep policy text deterministic and reused verbatim.
- Append dynamic data near the end.
- Reuse fixed JSON/YAML output schemas.
- Include only net-new evidence on follow-up turns.

## Do not
- Put timestamps/random IDs in the prefix.
- Re-send large static instructions every turn.
- Re-send full prior transcripts when a delta summary is enough.

## Guardrail parity requirement
Compression is allowed only if all canonical rules still apply from:
- `AGENTS.md`
- `.opencode/agent/Aria.md`
- `.opencode/agent/Jarvis.md`

## Fallback
If quality/regression risk increases, revert to full prompt mode for that workstream.
