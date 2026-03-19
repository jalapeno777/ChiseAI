import sys
from pathlib import Path

import yaml

patterns = [
    ".opencode/agent/*.md",
    ".opencode/commands/*.md",
    ".opencode/skills/*/SKILL.md",
]

errors = []


def validate_file(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        errors.append(f"{path}: missing closing frontmatter delimiter")
        return
    frontmatter = text[4:end]
    try:
        yaml.safe_load(frontmatter)
    except Exception as e:
        errors.append(f"{path}: invalid YAML frontmatter: {e}")


for pattern in patterns:
    for path in Path(".").glob(pattern):
        validate_file(path)

if errors:
    print("\n".join(errors))
    sys.exit(1)

print("Frontmatter validation passed")
