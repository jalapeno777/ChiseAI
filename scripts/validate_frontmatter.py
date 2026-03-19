#!/usr/bin/env python3
"""Validate YAML frontmatter in OpenCode agent/command/skill markdown files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

DEFAULT_PATTERNS = [
    ".opencode/agent/*.md",
    ".opencode/agents/*.md",
    ".opencode/commands/*.md",
    ".opencode/command/*.md",
    ".opencode/skills/*/SKILL.md",
]


def extract_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """Return parsed frontmatter or an error string."""
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n")

    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]

    if not normalized.startswith("---\n"):
        return None, None

    end = normalized.find("\n---\n", 4)
    if end == -1:
        return None, "missing closing frontmatter delimiter"

    raw_frontmatter = normalized[4:end]
    try:
        parsed = yaml.safe_load(raw_frontmatter)
    except Exception as exc:  # pragma: no cover - exact parser errors vary
        return None, f"invalid YAML frontmatter: {exc}"

    if not isinstance(parsed, dict):
        return None, "frontmatter must be a YAML mapping/object"

    return parsed, None


def required_keys_for(path: Path) -> list[str]:
    """Return required frontmatter keys for a given markdown file."""
    path_str = str(path).replace("\\", "/")

    if path_str.startswith(".opencode/agent/") or path_str.startswith(
        ".opencode/agents/"
    ):
        return ["description"]
    if path_str.startswith(".opencode/skills/") and path.name == "SKILL.md":
        return ["name", "description"]
    if path_str.startswith(".opencode/command/") or path_str.startswith(
        ".opencode/commands/"
    ):
        return ["description"]

    return []


def validate_file(path: Path) -> list[str]:
    """Return all errors found for one file."""
    errors: list[str] = []
    parsed, parse_error = extract_frontmatter(path)

    if parse_error:
        errors.append(f"{path}: {parse_error}")
        return errors

    if parsed is None:
        # No frontmatter is currently allowed for non-frontmatter markdown files.
        return errors

    for key in required_keys_for(path):
        value = parsed.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: required frontmatter key '{key}' is missing/empty")

    return errors


def gather_files(patterns: list[str]) -> list[Path]:
    """Collect markdown files matching configured patterns."""
    files: list[Path] = []
    for pattern in patterns:
        files.extend(Path(".").glob(pattern))
    return sorted(set(files))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate OpenCode markdown frontmatter."
    )
    parser.add_argument(
        "--patterns",
        nargs="*",
        default=DEFAULT_PATTERNS,
        help="Glob patterns to scan.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    files = gather_files(args.patterns)

    for path in files:
        errors.extend(validate_file(path))

    if errors:
        print("\n".join(errors))
        return 1

    print(f"Frontmatter validation passed ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
