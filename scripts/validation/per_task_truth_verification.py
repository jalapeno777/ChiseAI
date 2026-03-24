#!/usr/bin/env python3
"""
Per-Task Truth Verification - Validates per-task evidence requirements.

This module validates that task completion evidence contains all required fields:
- commands_run: List of commands executed with their outcomes
- tests_run_with_results: Test execution results including pass/fail counts
- logs_checked_with_findings: Log inspection results with findings
- acceptance_criteria_mapping: Mapping of acceptance criteria to evidence
- residual_risks: Known residual risks and caveats

The validator enforces structured evidence that is machine-checkable,
preventing agents from submitting incomplete or vague completion reports.

Exit codes:
    0 - All required fields present and valid
    1 - Missing or invalid required fields

Usage:
    from scripts.validation.per_task_truth_verification import (
        PerTaskEvidenceValidator,
        EvidenceValidationError,
        validate_per_task_evidence,
    )

    validator = PerTaskEvidenceValidator()
    result = validator.validate(evidence_dict)
    if not result.valid:
        for error in result.errors:
            print(error)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── Required Evidence Fields ──────────────────────────────────────────────────

REQUIRED_FIELDS: list[str] = [
    "commands_run",
    "tests_run_with_results",
    "logs_checked_with_findings",
    "acceptance_criteria_mapping",
    "residual_risks",
]

# Fields that must be lists or strings
LIST_FIELDS: set[str] = {
    "commands_run",
    "logs_checked_with_findings",
    "residual_risks",
}

# Fields that accept list, string, or dict
FLEXIBLE_FIELDS: set[str] = {
    "tests_run_with_results",
}

# Fields that must be dicts
DICT_FIELDS: set[str] = {
    "acceptance_criteria_mapping",
}


# ── Exceptions ────────────────────────────────────────────────────────────────


class EvidenceValidationError(Exception):
    """Raised when evidence validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class FieldValidation:
    """Result of validating a single evidence field."""

    field_name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning


@dataclass
class PerTaskValidationResult:
    """Aggregated result of per-task evidence validation."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_results: list[FieldValidation] = field(default_factory=list)
    total_fields_checked: int = 0
    fields_passed: int = 0
    fields_failed: int = 0

    def add_field_result(self, result: FieldValidation) -> None:
        """Add a field validation result."""
        self.field_results.append(result)
        self.total_fields_checked += 1
        if result.passed:
            self.fields_passed += 1
        else:
            self.fields_failed += 1
            if result.severity == "error":
                self.errors.append(result.message)
                self.valid = False
            else:
                self.warnings.append(result.message)

    def summary(self) -> str:
        """Return a human-readable summary."""
        status = "PASS" if self.valid else "FAIL"
        lines = [
            f"Per-Task Evidence Validation: {status}",
            f"  Fields checked: {self.total_fields_checked}",
            f"  Passed: {self.fields_passed}",
            f"  Failed: {self.fields_failed}",
        ]
        if self.errors:
            lines.append("  Errors:")
            for err in self.errors:
                lines.append(f"    - {err}")
        if self.warnings:
            lines.append("  Warnings:")
            for warn in self.warnings:
                lines.append(f"    - {warn}")
        return "\n".join(lines)


# ── Validators ────────────────────────────────────────────────────────────────


class PerTaskEvidenceValidator:
    """Validates per-task evidence completeness and correctness.

    This validator checks that task completion evidence includes all required
    fields with valid structure and content. It enforces machine-checkable
    evidence standards for agent task completion reports.

    Example:
        validator = PerTaskEvidenceValidator()
        result = validator.validate({
            "commands_run": ["pytest tests/ -v"],
            "tests_run_with_results": "30 passed, 0 failed",
            "logs_checked_with_findings": ["Checked Redis keys - no anomalies"],
            "acceptance_criteria_mapping": {"AC1": "Test passes"},
            "residual_risks": ["None identified"],
        })
        assert result.valid
    """

    def __init__(
        self,
        required_fields: list[str] | None = None,
        list_fields: set[str] | None = None,
        dict_fields: set[str] | None = None,
        flexible_fields: set[str] | None = None,
    ) -> None:
        """Initialize validator with configurable field requirements.

        Args:
            required_fields: List of required field names. Defaults to standard set.
            list_fields: Fields that must be lists. Defaults to standard set.
            dict_fields: Fields that must be dicts. Defaults to standard set.
            flexible_fields: Fields accepting list, string, or dict.
        """
        self.required_fields = required_fields or REQUIRED_FIELDS.copy()
        self.list_fields = list_fields or LIST_FIELDS.copy()
        self.dict_fields = dict_fields or DICT_FIELDS.copy()
        self.flexible_fields = flexible_fields or FLEXIBLE_FIELDS.copy()

    def validate(self, evidence: dict[str, Any]) -> PerTaskValidationResult:
        """Validate evidence dict against all required fields.

        Args:
            evidence: Dictionary containing task completion evidence.

        Returns:
            PerTaskValidationResult with validation details.
        """
        result = PerTaskValidationResult()

        if not isinstance(evidence, dict):
            result.add_field_result(
                FieldValidation(
                    field_name="_root",
                    passed=False,
                    message=f"Evidence must be a dictionary, got {type(evidence).__name__}",
                )
            )
            return result

        # Check all required fields exist
        for field_name in self.required_fields:
            self._validate_field(field_name, evidence, result)

        return result

    def _validate_field(
        self,
        field_name: str,
        evidence: dict[str, Any],
        result: PerTaskValidationResult,
    ) -> None:
        """Validate a single field presence, type, and content."""
        # Check presence
        if field_name not in evidence:
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=False,
                    message=f"Missing required field: {field_name}",
                )
            )
            return

        value = evidence[field_name]

        # Check not empty
        if value is None or value == "" or value == []:
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=False,
                    message=f"Field '{field_name}' is empty (None, empty string, or empty list)",
                )
            )
            return

        # Check type constraints for list fields
        if field_name in self.list_fields and not isinstance(value, (list, str)):
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=False,
                    message=f"Field '{field_name}' must be a list or string, got {type(value).__name__}",
                )
            )
            return

        # Check type constraints for dict fields
        if field_name in self.dict_fields and not isinstance(value, dict):
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=False,
                    message=f"Field '{field_name}' must be a dict, got {type(value).__name__}",
                )
            )
            return

        # Flexible fields accept list, string, or dict
        if field_name in self.flexible_fields and not isinstance(
            value, (list, str, dict)
        ):
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=False,
                    message=f"Field '{field_name}' must be a list, string, or dict, got {type(value).__name__}",
                )
            )
            return

        # Field-specific content validation
        if field_name == "tests_run_with_results":
            self._validate_tests_run(value, result)
        elif field_name == "commands_run":
            self._validate_commands_run(value, result)
        elif field_name == "acceptance_criteria_mapping":
            self._validate_ac_mapping(value, result)

        # If we got here without adding a failure, the field is valid
        if not any(
            fr.field_name == field_name and not fr.passed for fr in result.field_results
        ):
            result.add_field_result(
                FieldValidation(
                    field_name=field_name,
                    passed=True,
                    message=f"Field '{field_name}' is valid",
                )
            )

    def _validate_tests_run(self, value: Any, result: PerTaskValidationResult) -> None:
        """Validate tests_run_with_results includes pass/fail counts.

        Accepts string like "30 passed, 0 failed" or a dict with
        passed/failed keys or a list of test result strings.
        """
        if isinstance(value, str):
            # Check for pass/fail patterns in string
            has_pass_info = bool(re.search(r"\d+\s+pass", value, re.IGNORECASE))
            has_fail_info = bool(re.search(r"\d+\s+fail", value, re.IGNORECASE))

            if not has_pass_info:
                result.add_field_result(
                    FieldValidation(
                        field_name="tests_run_with_results",
                        passed=False,
                        message=(
                            "tests_run_with_results must include pass count "
                            f"(e.g., '30 passed, 0 failed'). Got: {value!r}"
                        ),
                    )
                )
                return

            if not has_fail_info:
                result.add_field_result(
                    FieldValidation(
                        field_name="tests_run_with_results",
                        passed=False,
                        severity="warning",
                        message=(
                            "tests_run_with_results should include fail count "
                            f"(e.g., '30 passed, 0 failed'). Got: {value!r}"
                        ),
                    )
                )
                return

        elif isinstance(value, dict):
            if "passed" not in value:
                result.add_field_result(
                    FieldValidation(
                        field_name="tests_run_with_results",
                        passed=False,
                        message="tests_run_with_results dict must include 'passed' key",
                    )
                )
                return

        elif isinstance(value, list):
            if not value:
                result.add_field_result(
                    FieldValidation(
                        field_name="tests_run_with_results",
                        passed=False,
                        message="tests_run_with_results list must not be empty",
                    )
                )
                return

    def _validate_commands_run(
        self, value: Any, result: PerTaskValidationResult
    ) -> None:
        """Validate commands_run has at least one non-empty entry."""
        if isinstance(value, list):
            non_empty = [c for c in value if c and isinstance(c, str) and c.strip()]
            if not non_empty:
                result.add_field_result(
                    FieldValidation(
                        field_name="commands_run",
                        passed=False,
                        message="commands_run must contain at least one non-empty command string",
                    )
                )
        elif isinstance(value, str):
            if not value.strip():
                result.add_field_result(
                    FieldValidation(
                        field_name="commands_run",
                        passed=False,
                        message="commands_run string must not be empty or whitespace",
                    )
                )

    def _validate_ac_mapping(self, value: Any, result: PerTaskValidationResult) -> None:
        """Validate acceptance_criteria_mapping has at least one entry."""
        if not isinstance(value, dict):
            return  # Type check already handled

        if not value:
            result.add_field_result(
                FieldValidation(
                    field_name="acceptance_criteria_mapping",
                    passed=False,
                    message="acceptance_criteria_mapping must have at least one entry",
                )
            )


# ── Convenience Function ──────────────────────────────────────────────────────


def validate_per_task_evidence(
    evidence: dict[str, Any],
) -> PerTaskValidationResult:
    """Validate per-task evidence against all required fields.

    This is the primary entry point for validating task completion evidence.
    It checks for presence, type, and content validity of all required fields.

    Args:
        evidence: Dictionary containing task completion evidence with keys:
            - commands_run: Commands executed (list of strings)
            - tests_run_with_results: Test results with pass/fail counts
            - logs_checked_with_findings: Log inspection findings
            - acceptance_criteria_mapping: AC-to-evidence mapping (dict)
            - residual_risks: Known residual risks

    Returns:
        PerTaskValidationResult with detailed validation findings.

    Example:
        result = validate_per_task_evidence({
            "commands_run": ["pytest tests/ -v"],
            "tests_run_with_results": "42 passed, 0 failed",
            "logs_checked_with_findings": ["No anomalies found"],
            "acceptance_criteria_mapping": {"AC1": "All tests pass"},
            "residual_risks": ["None"],
        })
        print(result.summary())
    """
    validator = PerTaskEvidenceValidator()
    return validator.validate(evidence)
