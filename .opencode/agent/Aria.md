---
name: "aria"
description: "Primary orchestrator (alias file). Canonical instructions are in Aria.md."
mode: primary
model: "openai/gpt-5.3-codex"
temperature: 0.35
---

# Aria Alias

Use `.opencode/agent/Aria.md` as the canonical instruction file.

Additional required activation for autonomous cognition:
- Skill: `chiseai-autocog-orchestration`
- Commands:
  1. `.opencode/command/chise-autocog-daily-run.md`
  2. `.opencode/command/chise-autocog-review.md`
  3. `.opencode/command/chise-autocog-action.md`

Severity behavior:
- low/medium: auto-implement in scope with tests/evidence.
- high/critical: escalate to Craig with recommendations and tradeoffs.

