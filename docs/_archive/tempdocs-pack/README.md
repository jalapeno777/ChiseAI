# OpenCode pack — Agentic Trading R&D (V1)

## What’s included
- `docs/architecture_diagram_outline.md` — Mermaid-based diagram outline
- `docs/agentic_neurosymbolic_trading_rd_v1_spec.md` — V1 system spec (copied in)
- `.opencode/skills/*/SKILL.md` — skills for gates, paper canary, brain CI/CD, DSL, metrics, promotion packets
- `.opencode/commands/*.md` — handy slash commands

## Install
Copy the `.opencode/` folder into your project root:
- `.opencode/skills/...`
- `.opencode/commands/...`

Then open OpenCode in that repo. Skills should appear in the `skill` tool list, and commands as `/rd-iteration`, etc.

## Notes
- If skills don’t show up, confirm the folder path and YAML frontmatter are correct.
- If you use strict permissions, ensure `permission.skill` allows these skill names.
