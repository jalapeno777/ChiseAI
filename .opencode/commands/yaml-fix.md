---
description: Repair and validate a YAML file or YAML frontmatter file
agent: build
---

Repair the target file with the smallest possible diff.

Target: $ARGUMENTS

Rules:
- If the target is `.yaml` or `.yml`, run formatter then yamllint after editing.
- If the target is markdown with frontmatter, preserve frontmatter boundaries and validate frontmatter after editing.
- Do not stop until the file is valid.
- Summarize exactly what changed.
