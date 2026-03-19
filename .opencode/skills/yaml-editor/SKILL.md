---
name: yaml-editor
description: Safely edit YAML and YAML frontmatter with minimal diffs, formatting, and validation.
compatibility: opencode
---

## Rules
- Read the full file before editing.
- Make the smallest possible change.
- Preserve key order unless reordering is explicitly requested.
- Use 2 spaces for indentation.
- Never use tabs in YAML.
- After editing any `.yaml` or `.yml` file:
  1. run the formatter
  2. run yamllint
  3. fix any issues before finishing
- After editing markdown frontmatter:
  1. preserve the opening and closing `---`
  2. validate the frontmatter with the frontmatter validator script if available
- Do not leave known YAML parse or lint errors behind.
