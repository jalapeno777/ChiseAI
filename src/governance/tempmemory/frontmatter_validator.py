"""
Frontmatter Validation Module for Tempmemory Governance.

Validates YAML frontmatter in markdown files according to the tempmemory schema.
"""

import re
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


class FrontmatterType(str, Enum):
    """Valid frontmatter types for tempmemory files."""

    DECISION = "decision"
    PATTERN = "pattern"
    SUMMARY = "summary"
    ANTI_PATTERN = "anti-pattern"


@dataclass
class ValidationError:
    """Represents a validation error."""

    field: str
    message: str
    severity: str = "error"  # "error" or "warning"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Result of frontmatter validation."""

    file_path: Path
    is_valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    frontmatter: Optional[dict] = None

    def add_error(self, field: str, message: str) -> None:
        """Add an error to the result."""
        self.errors.append(ValidationError(field, message, "error"))
        self.is_valid = False

    def add_warning(self, field: str, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(ValidationError(field, message, "warning"))

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def get_all_issues(self) -> List[ValidationError]:
        """Get all errors and warnings."""
        return self.errors + self.warnings

    def format_report(self) -> str:
        """Format a human-readable validation report."""
        lines = [f"Validation Report: {self.file_path}"]
        lines.append("=" * 60)

        if self.is_valid and not self.warnings:
            lines.append("✓ Valid frontmatter")
            return "\n".join(lines)

        if self.errors:
            lines.append("\nErrors:")
            for error in self.errors:
                lines.append(f"  ✗ {error}")

        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  ⚠ {warning}")

        return "\n".join(lines)


class ValidationRule:
    """Defines a single validation rule."""

    def __init__(
        self,
        field: str,
        required: bool = False,
        allowed_values: Optional[List[str]] = None,
        value_type: Optional[type] = None,
        validator: Optional[Any] = None,
        custom_message: Optional[str] = None,
    ):
        self.field = field
        self.required = required
        self.allowed_values = allowed_values
        self.value_type = value_type
        self.validator = validator
        self.custom_message = custom_message

    def validate(self, value: Any, result: ValidationResult) -> bool:
        """
        Validate a value against this rule.

        Returns True if valid, False otherwise.
        """
        # Check required
        if self.required and (value is None or value == ""):
            result.add_error(
                self.field, f"Required field '{self.field}' is missing or empty"
            )
            return False

        # Skip further validation if value is None/empty and not required
        if value is None or value == "":
            return True

        # Check type
        if self.value_type and not isinstance(value, self.value_type):
            result.add_error(
                self.field,
                f"Field '{self.field}' must be of type {self.value_type.__name__}, "
                f"got {type(value).__name__}",
            )
            return False

        # Check allowed values
        if self.allowed_values is not None:
            if isinstance(value, str) and value not in self.allowed_values:
                result.add_error(
                    self.field,
                    f"Field '{self.field}' must be one of: {', '.join(self.allowed_values)}, "
                    f"got '{value}'",
                )
                return False

        # Run custom validator
        if self.validator:
            is_valid, message = self.validator(value)
            if not is_valid:
                msg = (
                    self.custom_message
                    or message
                    or f"Validation failed for '{self.field}'"
                )
                result.add_error(self.field, msg)
                return False

        return True


class FrontmatterValidator:
    """Main validator for tempmemory frontmatter."""

    # Required fields that must be present
    REQUIRED_FIELDS = ["type", "story_id", "created"]

    # Valid types for tempmemory entries
    VALID_TYPES = ["decision", "pattern", "summary", "anti-pattern"]

    # Optional fields with their types
    OPTIONAL_FIELDS = {
        "tags": list,
        "author": str,
        "priority": str,
    }

    def __init__(self, strict: bool = False):
        """
        Initialize the validator.

        Args:
            strict: If True, warnings are treated as errors
        """
        self.strict = strict
        self.rules = self._build_rules()

    def _build_rules(self) -> List[ValidationRule]:
        """Build the validation rules."""
        rules = [
            # Required fields
            ValidationRule(
                field="type", required=True, allowed_values=self.VALID_TYPES
            ),
            ValidationRule(
                field="story_id",
                required=True,
                value_type=str,
                validator=self._validate_story_id,
            ),
            ValidationRule(
                field="created",
                required=True,
                validator=self._validate_iso_date,
            ),
            # Optional fields
            ValidationRule(field="tags", required=False, value_type=list),
            ValidationRule(field="author", required=False, value_type=str),
            ValidationRule(
                field="priority",
                required=False,
                value_type=str,
                allowed_values=["low", "medium", "high", "critical"],
            ),
        ]

        return rules

    def _validate_story_id(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate story_id format (e.g., ST-123, CH-456)."""
        if not isinstance(value, str):
            return False, "story_id must be a string"

        # Accept story IDs like ST-123, CH-456, FT-789, etc.
        pattern = r"^[A-Z]+-\d+$"
        if not re.match(pattern, value):
            return (
                False,
                f"story_id must match pattern 'PREFIX-NUMBER' (e.g., ST-123), got '{value}'",
            )

        return True, None

    def _validate_iso_date(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate ISO 8601 date format.

        Accepts both string dates and datetime objects (YAML parses dates as datetime).
        """
        # If it's already a datetime object, it's valid
        if isinstance(value, datetime):
            return True, None

        # If it's a date object, it's also valid
        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            # It's a date or datetime-like object
            return True, None

        if not isinstance(value, str):
            return (
                False,
                f"created date must be a string or datetime, got {type(value).__name__}",
            )

        # Try various ISO 8601 formats
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                datetime.strptime(value, fmt)
                return True, None
            except ValueError:
                continue

        return False, (
            f"created date must be in ISO 8601 format (e.g., '2024-01-15T10:30:00' or '2024-01-15'), "
            f"got '{value}'"
        )

    def extract_frontmatter(self, content: str) -> tuple[Optional[dict], Optional[str]]:
        """
        Extract YAML frontmatter from markdown content.

        Returns:
            Tuple of (frontmatter_dict, error_message)
        """
        # Match frontmatter between --- delimiters
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            return None, "No YAML frontmatter found (expected format: ---\nyaml\n---\n)"

        yaml_content = match.group(1)

        try:
            frontmatter = yaml.safe_load(yaml_content)
            if not isinstance(frontmatter, dict):
                return None, "Frontmatter must be a YAML dictionary (key: value pairs)"
            return frontmatter, None
        except yaml.YAMLError as e:
            return None, f"Invalid YAML syntax: {str(e)}"

    def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Validate a single file.

        Args:
            file_path: Path to the markdown file

        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(file_path=file_path)

        # Check file exists
        if not file_path.exists():
            result.add_error("file", f"File not found: {file_path}")
            return result

        # Check file is markdown
        if file_path.suffix.lower() != ".md":
            result.add_error(
                "file", f"File must be a markdown file (.md), got: {file_path.suffix}"
            )
            return result

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            result.add_error("file", f"Failed to read file: {str(e)}")
            return result

        # Extract frontmatter
        frontmatter, error = self.extract_frontmatter(content)
        if error:
            result.add_error("frontmatter", error)
            return result

        result.frontmatter = frontmatter

        # Validate against rules
        for rule in self.rules:
            value = frontmatter.get(rule.field)
            rule.validate(value, result)

        # Check for unknown fields
        known_fields = {rule.field for rule in self.rules}
        unknown_fields = set(frontmatter.keys()) - known_fields
        if unknown_fields:
            for field in unknown_fields:
                result.add_warning(
                    "frontmatter", f"Unknown field '{field}' will be ignored"
                )

        # In strict mode, warnings become errors
        if self.strict and result.warnings:
            for warning in result.warnings:
                result.add_error(warning.field, f"[STRICT] {warning.message}")
            result.warnings = []

        return result

    def validate_directory(
        self, directory: Path, pattern: str = "*.md", recursive: bool = True
    ) -> List[ValidationResult]:
        """
        Validate all markdown files in a directory.

        Args:
            directory: Directory to search
            pattern: Glob pattern for files
            recursive: Whether to search recursively

        Returns:
            List of ValidationResult for each file
        """
        results = []

        if not directory.exists():
            return [
                ValidationResult(
                    file_path=directory,
                    is_valid=False,
                    errors=[
                        ValidationError(
                            "directory", f"Directory not found: {directory}"
                        )
                    ],
                )
            ]

        glob_pattern = f"**/{pattern}" if recursive else pattern

        for file_path in directory.glob(glob_pattern):
            if file_path.is_file():
                result = self.validate_file(file_path)
                results.append(result)

        return results

    def can_auto_fix(self, result: ValidationResult) -> bool:
        """
        Check if the validation result can be auto-fixed.

        Currently supports:
        - Adding missing required fields with default values
        """
        # For now, we can't auto-fix much
        # Future: could add default values, fix common typos, etc.
        return False

    def auto_fix(self, file_path: Path) -> ValidationResult:
        """
        Attempt to auto-fix frontmatter issues.

        Returns the validation result after attempting fixes.
        """
        # TODO: Implement auto-fix logic
        # - Add missing required fields with placeholders
        # - Fix common type value typos
        # - Normalize date formats
        raise NotImplementedError("Auto-fix not yet implemented")
