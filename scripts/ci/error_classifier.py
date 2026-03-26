#!/usr/bin/env python3
"""CI Error Classifier - Categorizes CI failures and suggests fixes.

Classifies errors into categories:
- SYNTAX: Python syntax errors, indentation issues
- IMPORT: Module import failures
- TEST: Test failures (pytest, unittest)
- LINT: Code style/lint issues (black, ruff, flake8)
- TYPE: Type checking errors (mypy)
- CONFIG: Configuration/misconfiguration issues
- DEPENDENCY: Missing/incorrect dependencies
- UNKNOWN: Unclassified errors

Each category includes suggested fix actions.
"""

from __future__ import annotations

import contextlib
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ErrorCategory(Enum):
    """Categories of CI errors."""

    SYNTAX = "syntax"
    IMPORT = "import"
    TEST = "test"
    LINT = "lint"
    TYPE = "type"
    CONFIG = "config"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """A classified error with category and fix suggestions."""

    category: ErrorCategory
    message: str
    file_path: str | None = None
    line_number: int | None = None
    column_number: int | None = None
    raw_error: str = ""
    fix_suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.0


# Regex patterns for error classification
_PATTERNS: list[tuple[ErrorCategory, float, re.Pattern]] = [
    # Syntax errors
    (
        ErrorCategory.SYNTAX,
        0.95,
        re.compile(
            r"""
            (?P<message>
                (?:SyntaxError|IndentationError|TabError|E999)
                (?::\s*(?P<syntax_msg>.*))?
            )
            (?:\s+on\s+line\s+(?P<line>\d+))?
            (?:\s+of\s+(?P<file>[^\s]+))?
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Import errors
    (
        ErrorCategory.IMPORT,
        0.95,
        re.compile(
            r"""
            (?P<message>
                (?:ModuleNotFoundError|ImportError|ModuleImportError)
                (?:\s*:)?
                \s*
                (?:No\s+module\s+named\s+['"]?(?P<module>[\w.]+))
                |
                (?:cannot\s+import\s+name\s+['"]?(?P<import_name>[\w.]+))
                |
                (?:No\s+module\s+named\s+['"]?(?P<module2>[\w.]+))
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Test failures (pytest)
    (
        ErrorCategory.TEST,
        0.90,
        re.compile(
            r"""
            (?P<message>
                (?:FAILED|PASSED|ERROR)
                (?::\s*(?P<test_name>[^\s]+))?
                |
                (?:(?P<assertion>AssertionError|E AssertionError|pytest\.raises)
                    (?:\s*:?\s*(?P<assert_msg>.*))?)
                |
                (?:(?P<test_error>Failed|Error)\s+in\s+(?P<test_file>[^\s]+))
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Lint errors
    (
        ErrorCategory.LINT,
        0.90,
        re.compile(
            r"""
            (?P<message>
                (?:E\d{3,4}|W\d{3,4})   # Ruff error codes
                |
                (?:E501.*line.*too.*long)  # Black line length
                |
                (?:F401.*import.*unused)
                |
                (?:F841.*local.*variable.*assigned)
                |
                (?:flake8|pylint|black|ruff)
                (?:\s+(?:error|warning))?
                (?:\s*:?\s*(?P<lint_msg>.*))?
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Type errors
    (
        ErrorCategory.TYPE,
        0.95,
        re.compile(
            r"""
            (?P<message>
                (?:mypy|type\s+error)
                (?:\s*:)?
                \s*
                (?:(?P<type_msg>.*))
                |
                (?:error\[type-assertion\])
                |
                (?:error\[misc\])
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Configuration errors
    (
        ErrorCategory.CONFIG,
        0.85,
        re.compile(
            r"""
            (?P<message>
                (?:ConfigError|ConfigurationError|ValidationError)
                |
                (?:invalid\s+configuration)
                |
                (?:missing\s+required\s+config)
                |
                (?:could\s+not\s+find\s+config)
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
    # Dependency errors
    (
        ErrorCategory.DEPENDENCY,
        0.90,
        re.compile(
            r"""
            (?P<message>
                (?:pip\.errors\.|DependencyError)
                |
                (?:requirements\.txt)
                |
                (?:package.*not.*found)
                |
                (?:version.*mismatch)
                |
                (?:incompatible.*version)
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        ),
    ),
]


# Fix suggestions by category
_FIX_SUGGESTIONS: dict[ErrorCategory, list[str]] = {
    ErrorCategory.SYNTAX: [
        "Check for consistent indentation (spaces, not tabs)",
        "Verify all parentheses, brackets, and braces are closed",
        "Run: python -m py_compile <file.py> to identify exact location",
        "Check for missing colons after function/class definitions",
    ],
    ErrorCategory.IMPORT: [
        "Run: pip install <module-name> to install missing dependency",
        "Check for typos in import statement",
        "Verify module is in requirements.txt or pyproject.toml",
        'Try: python -c "import <module>" to test import',
    ],
    ErrorCategory.TEST: [
        "Review test output for assertion details",
        "Run: pytest -v --tb=short to see failure details",
        "Check if test assumptions match implementation",
        "Verify test fixtures are properly set up",
    ],
    ErrorCategory.LINT: [
        "Run: black <file.py> to auto-fix formatting",
        "Run: ruff check --fix <file.py> to auto-fix issues",
        "Review lint output for specific issue locations",
        "Check .ruff.toml or pyproject.toml for rule configuration",
    ],
    ErrorCategory.TYPE: [
        "Run: mypy <file.py> for detailed type error output",
        "Add type annotations or TypeVar where needed",
        "Check for correct import from typing module",
        "Use # type: ignore if type checker is overly strict",
    ],
    ErrorCategory.CONFIG: [
        "Check configuration file syntax (YAML/TOML/JSON)",
        "Verify all required configuration keys are present",
        "Review configuration file against documentation",
        "Check for environment variable settings",
    ],
    ErrorCategory.DEPENDENCY: [
        "Run: pip install -r requirements.txt",
        "Check for version conflicts: pip check",
        "Verify package versions are compatible",
        "Try: pip install --upgrade <package>",
    ],
    ErrorCategory.UNKNOWN: [
        "Review full error traceback for context",
        "Search error message for keywords",
        "Try running the command manually with full output",
        "Check recent changes to related files",
    ],
}


def classify_error(error_text: str) -> ClassifiedError:
    """Classify a single error message.

    Args:
        error_text: Raw error text from CI output

    Returns:
        ClassifiedError with category, message, and fix suggestions
    """
    best_match: tuple[ErrorCategory, float, re.Match] | None = None

    for category, confidence, pattern in _PATTERNS:
        match = pattern.search(error_text)
        if match and (best_match is None or confidence > best_match[1]):
            best_match = (category, confidence, match)

    if best_match is None:
        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            message=error_text.strip(),
            raw_error=error_text,
            fix_suggestions=_FIX_SUGGESTIONS[ErrorCategory.UNKNOWN],
            confidence=0.5,
        )

    category, confidence, match = best_match

    # Extract file path if present
    file_path: str | None = None
    line_number: int | None = None
    column_number: int | None = None

    if match.groupdict().get("file"):
        file_path = match.group("file")
    if match.groupdict().get("file2"):
        file_path = match.group("file2")
    if match.groupdict().get("line"):
        with contextlib.suppress(ValueError, TypeError):
            line_number = int(match.group("line"))

    # Build message from match
    message_parts = []
    for key in ["message", "module", "module2", "lint_msg", "type_msg", "assert_msg"]:
        if match.groupdict().get(key):
            message_parts.append(match.group(key))

    message = " ".join(message_parts) if message_parts else error_text.strip()

    return ClassifiedError(
        category=category,
        message=message,
        file_path=file_path,
        line_number=line_number,
        column_number=column_number,
        raw_error=error_text,
        fix_suggestions=_FIX_SUGGESTIONS.get(
            category, _FIX_SUGGESTIONS[ErrorCategory.UNKNOWN]
        ),
        confidence=confidence,
    )


def classify_ci_output(output: str) -> list[ClassifiedError]:
    """Classify multiple errors from CI output.

    Args:
        output: Full CI output text containing multiple errors

    Returns:
        List of ClassifiedError objects
    """
    errors: list[ClassifiedError] = []

    # Split output into error chunks (separate error blocks)
    error_blocks = re.split(
        r"\n(?=ERROR|FAILED|Traceback|===|\Z)", output, flags=re.IGNORECASE
    )

    for block in error_blocks:
        block = block.strip()
        if not block:
            continue

        # Skip success indicators
        if re.search(r"^(PASSED|OK|success|All checks passed)", block, re.IGNORECASE):
            continue

        classified = classify_error(block)
        if classified.category != ErrorCategory.UNKNOWN or len(block) > 50:
            errors.append(classified)

    return errors


def format_classification_report(errors: list[ClassifiedError]) -> str:
    """Format a human-readable classification report.

    Args:
        errors: List of classified errors

    Returns:
        Formatted report string
    """
    if not errors:
        return "No errors to classify."

    lines = ["=" * 60, "CI ERROR CLASSIFICATION REPORT", "=" * 60, ""]

    # Group by category
    by_category: dict[ErrorCategory, list[ClassifiedError]] = {}
    for error in errors:
        by_category.setdefault(error.category, []).append(error)

    for category in sorted(by_category.keys(), key=lambda c: c.value):
        cat_errors = by_category[category]
        lines.append(f"## {category.value.upper()} ({len(cat_errors)} errors)")
        lines.append("-" * 40)

        for error in cat_errors:
            lines.append(f"  Message: {error.message[:80]}")
            if error.file_path:
                lines.append(
                    f"  Location: {error.file_path}:{error.line_number or '?'}"
                )
            lines.append(f"  Confidence: {error.confidence:.0%}")
            lines.append("  Fix suggestions:")
            for suggestion in error.fix_suggestions[:2]:
                lines.append(f"    - {suggestion}")
            lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    """Main entry point for CLI usage."""
    if len(sys.argv) > 1:
        # Read from file
        file_path = Path(sys.argv[1])
        if file_path.exists():
            output = file_path.read_text()
        else:
            output = sys.argv[1]
    else:
        # Read from stdin
        output = sys.stdin.read()

    errors = classify_ci_output(output)
    print(format_classification_report(errors))

    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
