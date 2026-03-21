#!/usr/bin/env python3
"""Pre-commit hook to validate YAML frontmatter in tempmemory markdown files."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml

# Valid type values for tempmemory frontmatter
VALID_TYPES = {"decision", "pattern", "summary", "anti-pattern"}

# Valid priority values
VALID_PRIORITIES = {"low", "medium", "high", "p0", "p1", "p2", "critical"}


def extract_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """Extract and parse YAML frontmatter from a markdown file.

    Returns:
        Tuple of (parsed_frontmatter_dict, error_message).
        If no frontmatter, returns (None, None).
        If frontmatter exists but has issues, returns (None, error_message).
    """
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
    except Exception as exc:
        return None, f"invalid YAML frontmatter: {exc}"

    if not isinstance(parsed, dict):
        return None, "frontmatter must be a YAML mapping/object"

    return parsed, None


def validate_date(date_str: str) -> str | None:
    """Validate ISO 8601 datetime format.

    Returns:
        None if valid, error message if invalid.
    """
    try:
        # Try parsing as ISO 8601 datetime
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return None
    except ValueError:
        return "must be a valid ISO 8601 datetime string (e.g., 2024-01-15T10:30:00 or 2024-01-15T10:30:00Z)"


def validate_frontmatter(frontmatter: dict, file_path: Path) -> list[str]:
    """Validate frontmatter fields.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Required fields
    required_fields = ["type", "story_id", "created"]

    for field in required_fields:
        value = frontmatter.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{file_path}: required field '{field}' is missing or empty")

    # Validate type field
    if "type" in frontmatter:
        type_value = frontmatter["type"]
        if isinstance(type_value, str) and type_value not in VALID_TYPES:
            errors.append(
                f"{file_path}: 'type' must be one of {sorted(VALID_TYPES)}, got '{type_value}'"
            )

    # Validate story_id field
    if "story_id" in frontmatter:
        story_id = frontmatter["story_id"]
        if isinstance(story_id, str) and not story_id.strip():
            errors.append(f"{file_path}: 'story_id' must be a non-empty string")

    # Validate created field (date)
    if "created" in frontmatter:
        created = frontmatter["created"]
        if isinstance(created, str):
            date_error = validate_date(created)
            if date_error:
                errors.append(f"{file_path}: 'created' {date_error}")

    # Optional fields validation

    # tags must be a list of strings
    if "tags" in frontmatter:
        tags = frontmatter["tags"]
        if tags is not None:
            if not isinstance(tags, list):
                errors.append(f"{file_path}: 'tags' must be a list of strings")
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        errors.append(
                            f"{file_path}: 'tags'[{i}] must be a string, got {type(tag).__name__}"
                        )

    # author must be a string
    if "author" in frontmatter:
        author = frontmatter["author"]
        if author is not None and not isinstance(author, str):
            errors.append(
                f"{file_path}: 'author' must be a string, got {type(author).__name__}"
            )

    # priority must be a string
    if "priority" in frontmatter:
        priority = frontmatter["priority"]
        if priority is not None:
            if not isinstance(priority, str):
                errors.append(
                    f"{file_path}: 'priority' must be a string, got {type(priority).__name__}"
                )
            # Note: We don't strictly enforce valid priority values here,
            # just check it's a string. Could be enhanced to validate against VALID_PRIORITIES.

    return errors


def validate_file(path: Path) -> list[str]:
    """Validate a single tempmemory markdown file.

    Returns:
        List of error messages (empty if valid).
    """
    # Only process files in docs/tempmemories/
    path_str = str(path).replace("\\", "/")
    if not path_str.startswith("docs/tempmemories/"):
        return []

    # Only process .md files
    if not path.suffix == ".md":
        return []

    # Extract and validate frontmatter
    frontmatter, parse_error = extract_frontmatter(path)

    if parse_error:
        return [f"{path}: {parse_error}"]

    # If no frontmatter, skip (not all tempmemory files may have frontmatter)
    if frontmatter is None:
        return []

    return validate_frontmatter(frontmatter, path)


def main() -> int:
    """Main entry point for pre-commit hook.

    Returns:
        0 if all files valid, 1 if any validation fails.
    """
    # Get file paths from command-line arguments (staged files from git)
    if len(sys.argv) < 2:
        # No files provided, nothing to validate
        return 0

    all_errors: list[str] = []

    for file_path in sys.argv[1:]:
        path = Path(file_path)
        errors = validate_file(path)
        all_errors.extend(errors)

    if all_errors:
        print("\n".join(all_errors))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
