---
description: Repair and validate a YAML file or YAML frontmatter file
agent: yaml-config-editor
---

Repair the target file with the smallest possible diff.

Target: $ARGUMENTS

Rules:

- If the target is `.yaml` or `.yml`, run:
  1. `npx --prefix . prettier --write <target>`
  2. `yamllint <target>`
  3. if lint fails, fix and rerun until clean.
- If the target is markdown with frontmatter:
  1. preserve frontmatter boundaries
  2. run `python3 scripts/validate_frontmatter.py`
  3. if validation fails, fix and rerun until clean.
- Do not stop until the file is valid.
- Summarize exactly what changed.
