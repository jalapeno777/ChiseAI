#!/usr/bin/env python3
"""
Evidence Schema Validator.

Validates evidence data dictionaries against the required evidence schema.
Ensures all required fields exist with correct types, including nested structures.

Required top-level fields:
    - story_id: str
    - branch: str
    - head_sha: str
    - test_summary: dict (nested structure)
    - status_sync_proof: str or dict
    - blockers: list

Nested test_summary fields:
    - total: int
    - passed: int
    - failed: int
    - skipped: int (optional)
    - pass_rate: float (optional, 0.0-100.0)

Usage (programmatic):
    from scripts.validation.evidence_schema_validator import EvidenceSchemaValidator

    validator = EvidenceSchemaValidator()
    result = validator.validate(evidence_data)
    if not result.is_valid:
        for error in result.errors:
            print(error)

Usage (CLI):
    python3 scripts/validation/evidence_schema_validator.py --file docs/evidence/ST-001-evidence.json
    python3 scripts/validation/evidence_schema_validator.py --stdin < evidence.json

Exit Codes:
    0 - Validation passed
    1 - Validation failed
    2 - I/O or configuration errors
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL_FIELDS: dict[str, type | tuple[type, ...]] = {
    "story_id": str,
    "branch": str,
    "head_sha": str,
    "test_summary": dict,
    "status_sync_proof": (str, dict),
    "blockers": list,
}

# SHA pattern (full 40-char hex or abbreviated >= 7)
_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)

TEST_SUMMARY_REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "total": int,
    "passed": int,
    "failed": int,
}

TEST_SUMMARY_OPTIONAL_FIELDS: dict[str, type | tuple[type, ...]] = {
    "skipped": int,
    "pass_rate": float,
}


# ---------------------------------------------------------------------------
# Validation Result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Container for evidence schema validation results."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record a validation error."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Record a validation warning (does not invalidate)."""
        self.warnings.append(message)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        """Serialise result to a plain dict."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class EvidenceSchemaValidator:
    """Validates evidence data against the required schema."""

    def __init__(self, strict_head_sha: bool = False) -> None:
        """
        Args:
            strict_head_sha: If True, require a full 40-char SHA.
        """
        self.strict_head_sha = strict_head_sha

    # -- type helpers -------------------------------------------------------

    @staticmethod
    def _check_type(value: Any, expected: type | tuple[type, ...]) -> bool:
        """Return True if *value* matches *expected* type(s).

        Note: ``bool`` is explicitly rejected for ``int`` checks because
        ``isinstance(True, int)`` is ``True`` in Python, but booleans are
        not valid integer values in evidence data.
        """
        # Reject booleans masquerading as ints
        if isinstance(value, bool):
            if expected is int or (isinstance(expected, tuple) and int in expected):
                return False
            # If the expected type IS bool, let it through
            if expected is bool or (isinstance(expected, tuple) and bool in expected):
                return True
            return False

        if isinstance(expected, tuple):
            return isinstance(value, expected)
        return isinstance(value, expected)

    @staticmethod
    def _type_name(expected: type | tuple[type, ...]) -> str:
        """Human-readable type name for error messages."""
        if isinstance(expected, tuple):
            return " or ".join(t.__name__ for t in expected)
        return expected.__name__

    # -- top-level ----------------------------------------------------------

    def _validate_top_level(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Check all required top-level fields exist with correct types."""
        for field_name, expected_type in REQUIRED_TOP_LEVEL_FIELDS.items():
            if field_name not in data:
                result.add_error(f"Missing required field: {field_name}")
                continue

            value = data[field_name]
            if not self._check_type(value, expected_type):
                result.add_error(
                    f"Field '{field_name}' must be {self._type_name(expected_type)}, "
                    f"got {type(value).__name__}"
                )

    def _validate_head_sha_format(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate head_sha looks like a git commit SHA."""
        sha = data.get("head_sha")
        if not isinstance(sha, str):
            return  # type error already recorded

        min_len = 40 if self.strict_head_sha else 7
        if len(sha) < min_len:
            result.add_error(
                f"Field 'head_sha' is too short ({len(sha)} chars, minimum {min_len})"
            )

        if not _SHA_PATTERN.match(sha):
            result.add_error(f"Field 'head_sha' is not a valid hex SHA: '{sha}'")

    def _validate_story_id_format(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate story_id follows a recognizable pattern."""
        story_id = data.get("story_id")
        if not isinstance(story_id, str):
            return  # type error already recorded

        # Common patterns: ST-XXX, CH-XXX, FT-XXX, REPO-XXX, SAFETY-XXX, etc.
        # Must contain at least one digit
        if not re.search(r"\d", story_id):
            result.add_warning(
                f"Field 'story_id' '{story_id}' does not contain a digit"
            )

    # -- nested test_summary ------------------------------------------------

    def _validate_test_summary(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate the nested test_summary structure."""
        test_summary = data.get("test_summary")
        if not isinstance(test_summary, dict):
            return  # type error already recorded in top-level check

        # Required sub-fields
        for field_name, expected_type in TEST_SUMMARY_REQUIRED_FIELDS.items():
            dotted = f"test_summary.{field_name}"
            if field_name not in test_summary:
                result.add_error(f"Missing required field: {dotted}")
                continue

            value = test_summary[field_name]
            if not self._check_type(value, expected_type):
                result.add_error(
                    f"Field '{dotted}' must be "
                    f"{self._type_name(expected_type)}, "
                    f"got {type(value).__name__}"
                )

        # Optional sub-fields (error on type mismatch)
        for field_name, expected_type in TEST_SUMMARY_OPTIONAL_FIELDS.items():
            dotted = f"test_summary.{field_name}"
            if field_name in test_summary:
                value = test_summary[field_name]
                if not self._check_type(value, expected_type):
                    result.add_error(
                        f"Field '{dotted}' must be "
                        f"{self._type_name(expected_type)}, "
                        f"got {type(value).__name__}"
                    )

        # Semantic checks (only if all required fields exist and are ints)
        total = test_summary.get("total")
        passed = test_summary.get("passed")
        failed = test_summary.get("failed")
        skipped = test_summary.get("skipped", 0)

        if (
            isinstance(total, int)
            and isinstance(passed, int)
            and isinstance(failed, int)
        ):
            if total < 0:
                result.add_error("Field 'test_summary.total' must be >= 0")
            if passed < 0:
                result.add_error("Field 'test_summary.passed' must be >= 0")
            if failed < 0:
                result.add_error("Field 'test_summary.failed' must be >= 0")

            if passed + failed > total:
                result.add_error(
                    f"test_summary: passed ({passed}) + failed ({failed}) "
                    f"exceeds total ({total})"
                )

        # pass_rate consistency check
        pass_rate = test_summary.get("pass_rate")
        if isinstance(pass_rate, float) and isinstance(total, int) and total > 0:
            expected_rate = (
                round((passed / total) * 100, 2) if isinstance(passed, int) else None
            )
            if expected_rate is not None and abs(pass_rate - expected_rate) > 0.5:
                result.add_warning(
                    f"test_summary.pass_rate ({pass_rate}) does not match "
                    f"computed rate ({expected_rate}% from {passed}/{total})"
                )

    # -- blockers -----------------------------------------------------------

    def _validate_blockers(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate blockers list structure."""
        blockers = data.get("blockers")
        if not isinstance(blockers, list):
            return  # type error already recorded

        for idx, item in enumerate(blockers):
            if not isinstance(item, str):
                result.add_error(
                    f"blockers[{idx}] must be str, got {type(item).__name__}"
                )
            elif not item.strip():
                result.add_warning(f"blockers[{idx}] is an empty string")

    # -- status_sync_proof --------------------------------------------------

    def _validate_status_sync_proof(
        self, data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate status_sync_proof has meaningful content."""
        proof = data.get("status_sync_proof")
        if isinstance(proof, str) and not proof.strip():
            result.add_warning("Field 'status_sync_proof' is an empty string")
        elif isinstance(proof, dict):
            if not proof:
                result.add_warning("Field 'status_sync_proof' is an empty dict")

    # -- public API ---------------------------------------------------------

    def validate(self, data: Any) -> ValidationResult:
        """
        Validate *data* against the evidence schema.

        Args:
            data: A dict-like object containing evidence data.

        Returns:
            ValidationResult with errors/warnings populated.
        """
        result = ValidationResult()

        # Must be a dict at the top level
        if not isinstance(data, dict):
            result.add_error(f"Evidence must be a dict, got {type(data).__name__}")
            return result

        self._validate_top_level(data, result)
        self._validate_head_sha_format(data, result)
        self._validate_story_id_format(data, result)
        self._validate_test_summary(data, result)
        self._validate_blockers(data, result)
        self._validate_status_sync_proof(data, result)

        return result

    def validate_file(self, file_path: Path | str) -> ValidationResult:
        """
        Load a JSON evidence file and validate it.

        Args:
            file_path: Path to the JSON evidence file.

        Returns:
            ValidationResult with errors/warnings populated.
        """
        path = Path(file_path)

        if not path.exists():
            result = ValidationResult()
            result.add_error(f"File does not exist: {path}")
            return result

        try:
            with open(path) as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            result = ValidationResult()
            result.add_error(f"Invalid JSON in {path}: {exc}")
            return result
        except OSError as exc:
            result = ValidationResult()
            result.add_error(f"Cannot read {path}: {exc}")
            return result

        return self.validate(data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point for evidence schema validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate evidence files against the required schema.",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="Path to a JSON evidence file to validate.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read evidence JSON from stdin.",
    )
    parser.add_argument(
        "--strict-sha",
        action="store_true",
        help="Require a full 40-char commit SHA.",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results as JSON.",
    )

    args = parser.parse_args()

    if not args.file and not args.stdin:
        parser.error("Must specify --file or --stdin")

    validator = EvidenceSchemaValidator(strict_head_sha=args.strict_sha)

    if args.stdin:
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON from stdin: {exc}", file=sys.stderr)
            return 2
        result = validator.validate(data)
    else:
        result = validator.validate_file(args.file)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.is_valid:
            print("PASS: Evidence schema validation passed.")
            if result.warnings:
                for w in result.warnings:
                    print(f"  WARNING: {w}")
        else:
            print("FAIL: Evidence schema validation failed.")
            for e in result.errors:
                print(f"  ERROR: {e}")
            for w in result.warnings:
                print(f"  WARNING: {w}")

    return 0 if result.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
