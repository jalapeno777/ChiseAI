#!/usr/bin/env python3
"""
Metacognition Validator for Story Files

Validates that story markdown files contain required metacognition sections
and fields. Used by pre-commit hooks and CI to enforce metacognition compliance.

Usage:
    python3 metacog_validator.py --file story.md
    python3 metacog_validator.py --file story.md --fix
    python3 metacog_validator.py --file story.md --strict
    python3 metacog_validator.py --dir stories/

Exit codes:
    0 - Validation passed
    1 - Validation failed
    2 - Configuration or system error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Version
VERSION = "1.0.0"

# Required sections for metacognition compliance
REQUIRED_SECTIONS = [
    "## Metacognitive Predictions",
    "## Metacognitive Outcomes",
    "## Metacognitive Calibration",
]

# Required fields within each section
REQUIRED_PREDICTION_FIELDS = {
    "predicted_outcome",
    "predicted_risks",
    "confidence",
    "verification_plan",
    "expected_metrics",
}

REQUIRED_OUTCOME_FIELDS = {
    "actual_outcome",
    "actual_metrics",
    "wins",
    "misses",
    "new_prevention_rules",
}

REQUIRED_CALIBRATION_FIELDS = {
    "predicted_confidence",
    "observed_result",
    "calibration_delta",
    "confidence_adjustment_recommendation",
}

# Valid observed result values
VALID_OBSERVED_RESULTS = {"success", "partial", "failure"}

# Story ID pattern
STORY_ID_PATTERN = re.compile(
    r"^(ST|CH|FT|REWARD|REPO|SAFETY|BRANCH|PAPER|RECON|PROCESS)-[A-Z0-9-]*[0-9][A-Z0-9-]*$"
)


@dataclass
class ValidationResult:
    """Result of validating a single file."""

    file_path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixed: bool = False

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class MetacogValidator:
    """Validator for metacognition compliance in story files."""

    def __init__(self, strict: bool = False, fix: bool = False):
        self.strict = strict
        self.fix = fix

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a single story file."""
        result = ValidationResult(file_path=file_path)

        # Check file exists
        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        # Check file is markdown
        if file_path.suffix != ".md":
            result.add_warning(f"File is not markdown: {file_path}")

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            result.add_error(f"Failed to read file: {e}")
            return result

        # Parse frontmatter
        frontmatter = self._extract_frontmatter(content)
        body = self._extract_body(content)

        # Validate frontmatter
        self._validate_frontmatter(frontmatter, result)

        # Validate metacognition sections
        self._validate_sections(body, result)

        # Validate field semantics
        self._validate_semantics(body, result)

        # Attempt auto-fix if requested and has errors
        if self.fix and not result.is_valid:
            fixed = self._attempt_fix(file_path, content, result)
            if fixed:
                result.fixed = True
                result.errors.clear()
                result.add_warning("File was auto-fixed with template sections")

        return result

    def validate_directory(self, dir_path: Path) -> list[ValidationResult]:
        """Validate all story files in a directory."""
        results = []

        if not dir_path.exists():
            return [
                ValidationResult(
                    file_path=dir_path, errors=[f"Directory not found: {dir_path}"]
                )
            ]

        # Find all markdown files
        md_files = list(dir_path.rglob("*.md"))

        if not md_files:
            return [
                ValidationResult(
                    file_path=dir_path,
                    warnings=[f"No markdown files found in: {dir_path}"],
                )
            ]

        for md_file in md_files:
            # Skip certain files
            if self._should_skip_file(md_file):
                continue
            results.append(self.validate_file(md_file))

        return results

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = [
            "README",
            "TEMPLATE",
            "CHANGELOG",
            "CONTRIBUTING",
            "LICENSE",
            ".git",
            "node_modules",
            "__pycache__",
        ]

        name_upper = file_path.stem.upper()
        return any(pattern in name_upper for pattern in skip_patterns)

    def _extract_frontmatter(self, content: str) -> dict[str, Any]:
        """Extract YAML frontmatter from markdown content."""
        if not content.startswith("---\n"):
            return {}

        end = content.find("\n---\n", 4)
        if end == -1:
            return {}

        raw_yaml = content[4:end]
        try:
            data = yaml.safe_load(raw_yaml) or {}
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}

    def _extract_body(self, content: str) -> str:
        """Extract body content (without frontmatter)."""
        if not content.startswith("---\n"):
            return content

        end = content.find("\n---\n", 4)
        if end == -1:
            return content

        return content[end + 5 :]

    def _validate_frontmatter(
        self, frontmatter: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate frontmatter fields."""
        # Check for story_id
        story_id = frontmatter.get("story_id")
        if not story_id:
            result.add_error("Missing required frontmatter field: story_id")
        elif not STORY_ID_PATTERN.match(str(story_id)):
            msg = f"Invalid story_id format: {story_id}"
            if self.strict:
                result.add_error(msg)
            else:
                result.add_warning(msg)

        # Check for status
        status = frontmatter.get("status")
        if not status:
            result.add_warning("Missing frontmatter field: status")

        # Check for priority (for strict mode)
        priority = frontmatter.get("priority")
        if self.strict and not priority:
            result.add_error("Missing required frontmatter field: priority")

    def _validate_sections(self, body: str, result: ValidationResult) -> None:
        """Validate that required metacognition sections exist."""
        for section in REQUIRED_SECTIONS:
            if section not in body:
                msg = f"Missing required section: {section}"
                if self.strict:
                    result.add_error(msg)
                else:
                    result.add_warning(msg)
                continue

            # If section exists, validate its fields
            section_text = self._extract_section(body, section)
            if section_text:
                self._validate_section_fields(section, section_text, result)

    def _extract_section(self, body: str, heading: str) -> str | None:
        """Extract text content of a section."""
        pattern = rf"(?ms)^({re.escape(heading)}\n.*?)(?=^## |\Z)"
        match = re.search(pattern, body)
        if match:
            return match.group(1)
        return None

    def _validate_section_fields(
        self, section: str, section_text: str, result: ValidationResult
    ) -> None:
        """Validate fields within a section."""
        if "Metacognitive Predictions" in section:
            required_fields = REQUIRED_PREDICTION_FIELDS
        elif "Metacognitive Outcomes" in section:
            required_fields = REQUIRED_OUTCOME_FIELDS
        elif "Metacognitive Calibration" in section:
            required_fields = REQUIRED_CALIBRATION_FIELDS
        else:
            return

        for field in required_fields:
            if not self._has_field(section_text, field):
                msg = f"{section}: missing field '{field}'"
                if self.strict:
                    result.add_error(msg)
                else:
                    result.add_warning(msg)

    def _has_field(self, section_text: str, field: str) -> bool:
        """Check if a field exists in section text."""
        # Match various patterns:
        # - field:
        # - **field:**
        # - **field**:
        # - `field:`
        escaped_field = re.escape(field)
        pattern = rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*\s*)?{escaped_field}(?:\s*\*\*)?\s*:"
        return re.search(pattern, section_text) is not None

    def _extract_field_value(self, section_text: str, field: str) -> str | None:
        """Extract the value of a field from section text."""
        # Pattern to match field name possibly surrounded by ** markers, followed by :
        # Handles formats like: field: value, **field:** value, **field**: value
        escaped_field = re.escape(field)
        pattern = rf"^\s*(?:[-*]\s*)?\*?\*?\s*{escaped_field}\s*\*?\*?\s*:\s*(.*?)$"
        match = re.search(pattern, section_text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            # Clean up any remaining ** markers at start or end
            value = re.sub(r"^\*+\s*", "", value)
            value = re.sub(r"\s*\*+$", "", value)
            return value
        return None

    def _validate_semantics(self, body: str, result: ValidationResult) -> None:
        """Validate semantic correctness of field values."""
        # Extract sections
        pred_text = self._extract_section(body, "## Metacognitive Predictions")
        cal_text = self._extract_section(body, "## Metacognitive Calibration")

        # Validate confidence in predictions
        if pred_text:
            confidence = self._extract_field_value(pred_text, "confidence")
            if confidence is not None:
                try:
                    conf_val = float(confidence)
                    if not 0.0 <= conf_val <= 1.0:
                        result.add_error(
                            f"confidence must be between 0.0 and 1.0, got: {confidence}"
                        )
                except ValueError:
                    result.add_error(f"confidence must be a number, got: {confidence}")

        # Validate observed_result in calibration
        if cal_text:
            observed = self._extract_field_value(cal_text, "observed_result")
            if observed is not None:
                normalized = observed.strip().lower()
                # Normalize common variations
                if normalized.startswith(("success", "pass", "completed")):
                    normalized = "success"
                elif normalized.startswith(("partial", "partial_success")):
                    normalized = "partial"
                elif normalized.startswith(("failure", "fail", "failed", "incomplete")):
                    normalized = "failure"

                if normalized not in VALID_OBSERVED_RESULTS:
                    result.add_error(
                        f"observed_result must be one of {sorted(VALID_OBSERVED_RESULTS)}, "
                        f"got: {observed}"
                    )

        # Validate calibration_delta in calibration (strict mode)
        if cal_text and self.strict:
            delta = self._extract_field_value(cal_text, "calibration_delta")
            if delta is not None:
                try:
                    delta_val = float(delta)
                    if not -1.0 <= delta_val <= 1.0:
                        result.add_error(
                            f"calibration_delta should be between -1.0 and 1.0, got: {delta}"
                        )
                except ValueError:
                    result.add_error(
                        f"calibration_delta should be a number, got: {delta}"
                    )

    def _attempt_fix(
        self, file_path: Path, content: str, result: ValidationResult
    ) -> bool:
        """Attempt to auto-fix missing sections by adding templates."""
        try:
            # Read template
            template_path = Path(".opencode/templates/story-with-metacognition.md")
            if not template_path.exists():
                result.add_error("Cannot fix: template file not found")
                return False

            template_content = template_path.read_text(encoding="utf-8")

            # Extract metacognition sections from template
            fixed_content = content

            for section in REQUIRED_SECTIONS:
                if section not in content:
                    section_content = self._extract_section(template_content, section)
                    if section_content:
                        fixed_content = fixed_content + "\n\n" + section_content

            # Write fixed content
            file_path.write_text(fixed_content, encoding="utf-8")
            return True

        except Exception as e:
            result.add_error(f"Failed to auto-fix: {e}")
            return False


def print_results(results: list[ValidationResult], verbose: bool = False) -> None:
    """Print validation results."""
    total_files = len(results)
    valid_files = sum(1 for r in results if r.is_valid)
    fixed_files = sum(1 for r in results if r.fixed)

    print("\n" + "=" * 60)
    print("METACOGNITION VALIDATION RESULTS")
    print("=" * 60)

    for result in results:
        if result.is_valid and not result.warnings and not verbose:
            continue

        print(f"\n📄 {result.file_path}")

        if result.fixed:
            print("  🛠️  Auto-fixed with template sections")

        if result.errors:
            print("  ❌ ERRORS:")
            for error in result.errors:
                print(f"     • {error}")

        if result.warnings:
            print("  ⚠️  WARNINGS:")
            for warning in result.warnings:
                print(f"     • {warning}")

        if result.is_valid and not result.warnings:
            print("  ✅ Valid")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {valid_files}/{total_files} files valid")
    if fixed_files > 0:
        print(f"         {fixed_files} files auto-fixed")
    print("=" * 60 + "\n")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate metacognition compliance in story files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a single file
  %(prog)s --file story.md
  
  # Validate with strict mode (all fields required)
  %(prog)s --file story.md --strict
  
  # Auto-fix missing sections
  %(prog)s --file story.md --fix
  
  # Validate all files in a directory
  %(prog)s --dir stories/
  
  # Verbose output
  %(prog)s --file story.md --verbose
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--file", type=Path, help="Path to a story markdown file to validate"
    )
    group.add_argument(
        "--dir", type=Path, help="Path to a directory containing story files"
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: all fields required with non-empty values (for CI)",
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix missing sections by adding template sections",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="Verbose output including valid files"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for CI integration)",
    )

    args = parser.parse_args()

    # Create validator
    validator = MetacogValidator(strict=args.strict, fix=args.fix)

    # Validate file or directory
    if args.file:
        results = [validator.validate_file(args.file)]
    else:
        results = validator.validate_directory(args.dir)

    # Output results
    if args.json:
        import json

        output = []
        for r in results:
            output.append(
                {
                    "file": str(r.file_path),
                    "valid": r.is_valid,
                    "fixed": r.fixed,
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
            )
        print(json.dumps(output, indent=2))
    else:
        print_results(results, verbose=args.verbose)

    # Return exit code
    if any(not r.is_valid for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
