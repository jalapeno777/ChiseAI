---
project: ChiseAI
scope: tooling
type: pattern
story_id: CH-AGENTS-002
tags: [opencode, bmad, commands, skills]
date: 2026-02-08
---

## Summary

ChiseAI uses BMAD Beta 7 workflows primarily through Opencode workflow commands under `.opencode/command/`.

We added repo-specific helper commands:

- `.opencode/command/chise-iterloop-start.md`
- `.opencode/command/chise-iterloop-close.md`
- `.opencode/command/chise-precommit-gates.md`
- `.opencode/command/chise-risk-audit.md`
- `.opencode/command/chise-dashboard-smoke.md`

We also added Claude-style skills under `.opencode/skills/` to guide when to use commands and enforce PRD quality, data-first discipline, and risk audits.

## Rationale

- Commands are the repeatable execution entry points.
- Skills are persistent guidance and routing rules for agents.

## Notes

Qdrant semantic store was not invoked via MCP in this runtime; this note should be promoted to Qdrant later.
