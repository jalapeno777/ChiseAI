---
name: yaml-editor
description: Safely edit YAML and YAML frontmatter with minimal diffs, formatting, and validation.
compatibility: opencode
---

## Rules

- Trigger: use this skill when editing any `.yaml`, `.yml`, or markdown frontmatter block.
- Special-case: when editing `docs/bmm-workflow-status.yaml`, run
  `python3 scripts/governance/status_guard.py validate --file docs/bmm-workflow-status.yaml`
  before and after edits.
- For `docs/bmm-workflow-status.yaml`, if two manual fix attempts fail, run mandatory repair:
  `python3 scripts/governance/status_guard.py repair --file docs/bmm-workflow-status.yaml --enforce-repair-after 2`
- Read the full file before editing.
- Make the smallest possible change.
- Preserve key order unless reordering is explicitly requested.
- Use 2 spaces for indentation.
- Never use tabs in YAML.
- After editing any `.yaml` or `.yml` file:
  1. run `npx --prefix . prettier --write <file>`
  2. run `yamllint <file>`
  3. if lint fails, fix and rerun both commands
- After editing markdown frontmatter:
  1. preserve the opening and closing `---`
  2. run `python3 scripts/validate_frontmatter.py`
  3. if validation fails, fix and rerun
- For YAML-heavy edits, route to `@yaml-config-editor`.
- Do not leave known YAML parse or lint errors behind.
