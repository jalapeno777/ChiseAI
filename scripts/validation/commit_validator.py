#!/usr/bin/env python3
"""Commit message validator for conventional commits and story ID presence.

Validates that commit messages follow the conventional commit format and
contain a recognized story ID token. Designed for use in pre-commit hooks
and CI pipelines.

Usage:
    python commit_validator.py "feat(api): Add new endpoint (ST-042)"
    python commit_validator.py --message-file .git/COMMIT_EDITMSG
    python commit_validator.py --json "fix: Resolve crash on startup (CH-007)"

Conventional Commit Format:
    type[(scope)][!]: description

    Types: feat, fix, docs, style, refactor, perf, test, build, ci,
           chore, revert

    Example:
        feat(api): Add user authentication endpoint (ST-042)
        fix(core)!: Resolve critical memory leak (SAFETY-003)

Story ID Tokens:
    ST-*, CH-*, FT-*, REWARD-*, REPO-*, SAFETY-*, BRANCH-*, PAPER-*,
    RECON-*, STRONG-*, TG-*
    All patterns must include at least one digit.

Exit Codes:
    0 - All validations pass
    1 - Validation failures found
    2 - Usage or runtime error

Story: SWARM-HARDEN-001-7.1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationError(Enum):
    """Categories of commit message validation errors."""

    EMPTY_MESSAGE = "EMPTY_MESSAGE"
    NO_CONVENTIONAL_PREFIX = "NO_CONVENTIONAL_PREFIX"
    INVALID_TYPE = "INVALID_TYPE"
    MISSING_BODY_AFTER_SCOPE = "MISSING_BODY_AFTER_SCOPE"
    NO_STORY_ID = "NO_STORY_ID"
    INVALID_STORY_ID = "INVALID_STORY_ID"


@dataclass
class ValidationIssue:
    """A single validation issue found in a commit message."""

    code: ValidationError
    message: str
    context: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert issue to dictionary."""
        result: dict[str, str] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.context:
            result["context"] = self.context
        return result


@dataclass
class ValidationResult:
    """Result of validating a commit message."""

    valid: bool
    message: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "valid": self.valid,
            "message": self.message,
            "issue_count": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
        }


# Recognized conventional commit types
CONVENTIONAL_TYPES = frozenset(
    {
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    }
)

# Regex for conventional commit first line:
#   type[(scope)][!]: description
# Allows optional scope in parens, optional breaking change !, and description text.
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<desc>.*)",
    re.IGNORECASE,
)

# Pattern to detect description that is only parenthesized content
_PARENS_ONLY_RE = re.compile(r"^\s*\([^)]*\)\s*$")

# Recognized story ID prefixes from AGENTS.md and extract_story_id_from_pr.py
STORY_ID_PREFIXES = (
    "ST-",
    "CH-",
    "FT-",
    "REWARD-",
    "REPO-",
    "SAFETY-",
    "BRANCH-",
    "PAPER-",
    "RECON-",
    "STRONG-",
    "TG-",
)

# Regex: match any recognized story ID (prefix + at least one digit + optional suffix)
_STORY_ID_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in STORY_ID_PREFIXES) + r")\d+",
    re.IGNORECASE,
)


class CommitValidator:
    """Validates commit messages for conventional commit format and story IDs."""

    def __init__(
        self,
        require_story_id: bool = True,
        allowed_types: frozenset[str] | None = None,
    ) -> None:
        """Initialize the validator.

        Args:
            require_story_id: Whether a story ID is mandatory.
            allowed_types: Set of allowed conventional commit types.
                           Defaults to CONVENTIONAL_TYPES if None.
        """
        self.require_story_id = require_story_id
        self.allowed_types = allowed_types or CONVENTIONAL_TYPES

    def validate(self, message: str) -> ValidationResult:
        """Validate a commit message against all rules.

        Args:
            message: The commit message to validate.

        Returns:
            ValidationResult with valid flag and any issues found.
        """
        issues: list[ValidationIssue] = []

        if not message or not message.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationError.EMPTY_MESSAGE,
                    message="Commit message is empty.",
                )
            )
            return ValidationResult(valid=False, message=message, issues=issues)

        # Use only the first line for format checks (conventional commits spec)
        first_line = message.strip().split("\n", 1)[0].strip()

        # Check conventional commit format
        match = _CONVENTIONAL_RE.match(first_line)
        if not match:
            issues.append(
                ValidationIssue(
                    code=ValidationError.NO_CONVENTIONAL_PREFIX,
                    message=(
                        "Commit message must follow conventional commit format: "
                        "<type>[(scope)][!]: <description>"
                    ),
                    context=f"First line: {first_line!r}",
                )
            )
            # Still check for story ID even if format is wrong
            if self.require_story_id:
                self._check_story_id(first_line, issues)
            return ValidationResult(valid=False, message=message, issues=issues)

        # Check the type is recognized
        commit_type = match.group("type").lower()
        if commit_type not in self.allowed_types:
            issues.append(
                ValidationIssue(
                    code=ValidationError.INVALID_TYPE,
                    message=(
                        f"Invalid conventional commit type: {commit_type!r}. "
                        f"Allowed: {sorted(self.allowed_types)}"
                    ),
                    context=f"First line: {first_line!r}",
                )
            )

        # Check description is non-empty and meaningful after the prefix
        description = match.group("desc") or ""
        desc_stripped = description.strip()
        # Remove parenthesized groups to detect description that is only a story ID ref
        without_parens = re.sub(r"\([^)]*\)", "", desc_stripped).strip()
        if not desc_stripped or not without_parens:
            issues.append(
                ValidationIssue(
                    code=ValidationError.MISSING_BODY_AFTER_SCOPE,
                    message="Commit message has no description after conventional prefix.",
                    context=f"First line: {first_line!r}",
                )
            )

        # Check for story ID
        if self.require_story_id:
            self._check_story_id(first_line, issues)

        valid = len(issues) == 0
        return ValidationResult(valid=valid, message=message, issues=issues)

    def _check_story_id(self, text: str, issues: list[ValidationIssue]) -> None:
        """Check text for a recognized story ID and append issues if missing.

        Args:
            text: Text to search for story ID.
            issues: List to append any found issues to.
        """
        story_id_match = _STORY_ID_RE.search(text)
        if not story_id_match:
            issues.append(
                ValidationIssue(
                    code=ValidationError.NO_STORY_ID,
                    message=(
                        "Commit message must contain a recognized story ID token. "
                        f"Recognized prefixes: {', '.join(sorted(set(STORY_ID_PREFIXES)))}"
                    ),
                    context=f"Text searched: {text!r}",
                )
            )

    def extract_story_id(self, message: str) -> str | None:
        """Extract story ID from a commit message.

        Args:
            message: The commit message to search.

        Returns:
            The story ID string if found, None otherwise.
        """
        if not message:
            return None
        match = _STORY_ID_RE.search(message)
        if match:
            return match.group(0).upper()
        return None

    def extract_type(self, message: str) -> str | None:
        """Extract the conventional commit type from a message.

        Args:
            message: The commit message to parse.

        Returns:
            The commit type (lowercase) if valid, None otherwise.
        """
        if not message:
            return None
        first_line = message.strip().split("\n", 1)[0].strip()
        match = _CONVENTIONAL_RE.match(first_line)
        if match:
            return match.group("type").lower()
        return None

    def extract_scope(self, message: str) -> str | None:
        """Extract the conventional commit scope from a message.

        Args:
            message: The commit message to parse.

        Returns:
            The scope string if present, None otherwise.
        """
        if not message:
            return None
        first_line = message.strip().split("\n", 1)[0].strip()
        match = _CONVENTIONAL_RE.match(first_line)
        if match:
            scope = match.group("scope")
            return scope if scope else None
        return None

    def is_breaking(self, message: str) -> bool:
        """Check if a commit message signals a breaking change.

        Args:
            message: The commit message to check.

        Returns:
            True if the commit has a breaking change indicator (!), False otherwise.
        """
        if not message:
            return False
        first_line = message.strip().split("\n", 1)[0].strip()
        match = _CONVENTIONAL_RE.match(first_line)
        return bool(match and match.group("breaking"))


def _read_message_from_file(path: str) -> str:
    """Read commit message from a file, stripping trailing whitespace/blank lines.

    Args:
        path: Path to the file containing the commit message.

    Returns:
        The commit message string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Strip trailing whitespace and blank lines (git appends a trailing newline)
    return content.rstrip()


def main() -> int:
    """CLI entry point for commit message validation.

    Returns:
        Exit code: 0 for valid, 1 for validation failures, 2 for errors.
    """
    parser = argparse.ArgumentParser(
        description="Validate commit message format and story ID presence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "feat(api): Add user auth endpoint (ST-042)"
  %(prog)s --message-file .git/COMMIT_EDITMSG
  %(prog)s --json --no-story-id "chore: Update dependencies"
        """,
    )

    parser.add_argument(
        "message",
        nargs="?",
        help="Commit message to validate (positional argument).",
    )

    parser.add_argument(
        "--message-file",
        type=str,
        metavar="FILE",
        help="Read commit message from a file (e.g., .git/COMMIT_EDITMSG).",
    )

    parser.add_argument(
        "--no-story-id",
        action="store_true",
        help="Do not require a story ID in the commit message.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )

    args = parser.parse_args()

    # Determine message source
    message: str | None = None
    if args.message_file:
        try:
            message = _read_message_from_file(args.message_file)
        except FileNotFoundError:
            print(
                f"Error: message file not found: {args.message_file}",
                file=sys.stderr,
            )
            return 2
    elif args.message:
        message = args.message

    if message is None:
        parser.error("Provide a commit message or --message-file FILE.")

    validator = CommitValidator(require_story_id=not args.no_story_id)
    result = validator.validate(message)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.valid:
            print("OK: commit message is valid.")
        else:
            print("FAIL: commit message validation errors:")
            for issue in result.issues:
                print(f"  - [{issue.code.value}] {issue.message}")
                if issue.context:
                    print(f"    {issue.context}")

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
