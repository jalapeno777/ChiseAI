---
project: ChiseAI
scope: tooling
type: decision
story_id: CH-AGENTS-001
tags: [opencode, agents, orchestration, bmad]
date: 2026-02-08
---

## Summary

Opencode agents were defined under `.opencode/agent/*.md` for ChiseAI. Jarvis is the BMAD orchestrator replacement and Aria delegates to Jarvis.

## Decisions

- `jarvis` is planning and assessment only (model `zai-coding-plan/glm-4.7-thinking`, temp `0.2`).
- Execution agents:
  - `dev` (model `kimi-for-coding/k2p5`, temp `0.2`)
  - `senior-dev` (model `kimi-for-coding/k2p5`, temp `0.15`)
  - `quickdev` (model `minimax/MiniMax-M2.5`, temp `0.35`)
- Research and review agents:
  - `research` (repo-docs and forensics, no edits)
  - `web-research` (online search and citations, no edits)
  - `critic` (adversarial review, no edits)

## Notes

This memory should be promoted into Qdrant `ChiseAI` collection when a Qdrant store tool is available in the current agent runtime.

