"""Data Validation Rules Engine for ML Training Data.

Provides a comprehensive set of validation rules for ensuring training data
quality, including schema enforcement, type checking, range validation,
pattern matching, and custom business rules.

Architecture:
    ValidationRule (ABC)
        -> 20+ concrete rule implementations
    DataValidator
        -> registers rules
        -> runs rules against datasets (list-of-dicts or pandas DataFrames)
        -> aggregates results
    RuleRegistry
        -> singleton of named rules for quick lookup
    CompositeRule
        -> groups multiple rules under one name
"""

from __future__ import annotations

import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    import pandas as pd

    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Severity levels for validation results."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of executing a single validation rule.

    Attributes:
        rule_name: Name of the rule that produced this result.
        passed: Whether the validation passed.
        message: Human-readable description of the result.
        severity: Severity level (error, warning, info).
        details: Optional dictionary with extra context (row indices, values, etc.).
    """

    rule_name: str
    passed: bool
    message: str
    severity: str = "error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# ValidationRule (ABC)
# ---------------------------------------------------------------------------


class ValidationRule(ABC):
    """Abstract base class for all validation rules.

    Subclasses must implement ``validate`` which receives data and returns
    a list of ``ValidationResult`` instances.

    Attributes:
        name: Human-readable rule name.
        description: What the rule checks.
        severity: Default severity when the rule fails.
    """

    name: str = "base_rule"
    description: str = "Base validation rule"
    severity: str = "error"

    @abstractmethod
    def validate(self, data: Any) -> list[ValidationResult]:
        """Run validation against *data*.

        Args:
            data: The data to validate. Concrete rules should document
                  what shape of data they expect (list-of-dicts, DataFrame,
                  single dict, scalar, etc.).

        Returns:
            List of ``ValidationResult`` objects.
        """
        ...


# ---------------------------------------------------------------------------
# Helper: coerce to list-of-dicts
# ---------------------------------------------------------------------------


def _to_records(data: Any) -> list[dict[str, Any]]:
    """Normalise *data* into a list of row-dicts.

    Accepts:
        - list[dict]
        - pandas DataFrame
        - single dict (wrapped in a list)
    """
    if _HAS_PANDAS and isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise TypeError(f"Unsupported data type: {type(data).__name__}")


# ===================================================================
# Concrete Validation Rules (20+)
# ===================================================================


# 1. Schema Completeness
class SchemaCompletenessRule(ValidationRule):
    """Check that required fields are present in every record."""

    def __init__(
        self,
        required_fields: Sequence[str],
        severity: str = "error",
    ) -> None:
        self.required_fields: list[str] = list(required_fields)
        self.severity = severity
        self.name = "schema_completeness"
        self.description = f"Ensure required fields are present: {self.required_fields}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        missing_rows: list[int] = []
        missing_fields_by_row: dict[int, list[str]] = {}

        for idx, record in enumerate(records):
            missing = [f for f in self.required_fields if f not in record]
            if missing:
                missing_rows.append(idx)
                missing_fields_by_row[idx] = missing

        passed = len(missing_rows) == 0
        message = (
            "All required fields present."
            if passed
            else f"Missing fields in {len(missing_rows)} row(s): {missing_fields_by_row}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={
                    "missing_rows": missing_rows,
                    "missing_fields": missing_fields_by_row,
                },
            )
        ]


# 2. Data Type Validation
class DataTypeValidationRule(ValidationRule):
    """Validate that field values match expected types."""

    def __init__(
        self,
        field_types: dict[str, type | tuple[type, ...]],
        severity: str = "error",
        allow_none: bool = False,
    ) -> None:
        self.field_types = field_types
        self.severity = severity
        self.allow_none = allow_none
        self.name = "data_type_validation"
        self.description = f"Validate field types: {field_types}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        type_errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for field_name, expected_type in self.field_types.items():
                if field_name not in record:
                    continue
                value = record[field_name]
                if self.allow_none and value is None:
                    continue
                if not isinstance(value, expected_type):
                    type_errors.append(
                        {
                            "row": idx,
                            "field": field_name,
                            "expected": str(expected_type),
                            "actual": type(value).__name__,
                            "actual_value": repr(value)[:100],
                        }
                    )

        passed = len(type_errors) == 0
        message = (
            "All fields have correct types."
            if passed
            else f"Type mismatches in {len(type_errors)} field(s): {type_errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"type_errors": type_errors},
            )
        ]


# 3. Null / NaN Check
class NullCheckRule(ValidationRule):
    """Detect null / NaN values in specified fields."""

    def __init__(
        self,
        fields: Sequence[str],
        severity: str = "error",
        allow_none: bool = False,
    ) -> None:
        self.fields = list(fields)
        self.severity = severity
        self.allow_none = allow_none
        self.name = "null_check"
        self.description = f"Check for null/NaN values in: {self.fields}"

    @staticmethod
    def _is_null(value: Any) -> bool:
        if value is None:
            return True
        return bool(isinstance(value, float) and math.isnan(value))

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        null_findings: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for f in self.fields:
                if f in record and self._is_null(record[f]):
                    null_findings.append({"row": idx, "field": f})

        passed = len(null_findings) == 0
        message = (
            "No null/NaN values found."
            if passed
            else f"Null/NaN found in {len(null_findings)} cell(s): {null_findings}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"null_findings": null_findings},
            )
        ]


# 4. Range Validation
class RangeValidationRule(ValidationRule):
    """Validate numeric fields fall within [min, max]."""

    def __init__(
        self,
        field_ranges: dict[str, dict[str, float]],
        severity: str = "error",
    ) -> None:
        self.field_ranges = field_ranges
        self.severity = severity
        self.name = "range_validation"
        self.description = f"Validate numeric ranges: {field_ranges}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        out_of_range: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for field_name, bounds in self.field_ranges.items():
                if field_name not in record or record[field_name] is None:
                    continue
                value = record[field_name]
                min_val = bounds.get("min", float("-inf"))
                max_val = bounds.get("max", float("inf"))
                if not (min_val <= value <= max_val):
                    out_of_range.append(
                        {
                            "row": idx,
                            "field": field_name,
                            "value": value,
                            "min": min_val,
                            "max": max_val,
                        }
                    )

        passed = len(out_of_range) == 0
        message = (
            "All values within range."
            if passed
            else f"Out-of-range values in {len(out_of_range)} cell(s): {out_of_range}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"out_of_range": out_of_range},
            )
        ]


# 5. String Pattern (regex)
class StringPatternRule(ValidationRule):
    """Validate string fields match a regex pattern."""

    def __init__(
        self,
        field_patterns: dict[str, str],
        severity: str = "error",
    ) -> None:
        self.field_patterns = field_patterns
        self.severity = severity
        self.name = "string_pattern"
        self.description = f"Validate string patterns: {field_patterns}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        mismatches: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for field_name, pattern in self.field_patterns.items():
                if field_name not in record or record[field_name] is None:
                    continue
                value = str(record[field_name])
                if not re.match(pattern, value):
                    mismatches.append(
                        {
                            "row": idx,
                            "field": field_name,
                            "value": repr(value)[:100],
                            "pattern": pattern,
                        }
                    )

        passed = len(mismatches) == 0
        message = (
            "All strings match patterns."
            if passed
            else f"Pattern mismatches in {len(mismatches)} cell(s): {mismatches}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"mismatches": mismatches},
            )
        ]


# 6. Enum Value Validation
class EnumValueValidationRule(ValidationRule):
    """Validate field values belong to an allowed set."""

    def __init__(
        self,
        field_enums: dict[str, Sequence[Any]],
        severity: str = "error",
        allow_none: bool = False,
    ) -> None:
        self.field_enums = {k: set(v) for k, v in field_enums.items()}
        self.severity = severity
        self.allow_none = allow_none
        self.name = "enum_value_validation"
        self.description = f"Validate enum values: {field_enums}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        invalid: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for field_name, allowed in self.field_enums.items():
                if field_name not in record:
                    continue
                value = record[field_name]
                if self.allow_none and value is None:
                    continue
                if value not in allowed:
                    invalid.append(
                        {
                            "row": idx,
                            "field": field_name,
                            "value": repr(value)[:100],
                            "allowed": sorted(str(a) for a in allowed),
                        }
                    )

        passed = len(invalid) == 0
        message = (
            "All enum values valid."
            if passed
            else f"Invalid enum values in {len(invalid)} cell(s): {invalid}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"invalid": invalid},
            )
        ]


# 7. Unique Constraint
class UniqueConstraintRule(ValidationRule):
    """Ensure values in specified fields are unique across records."""

    def __init__(
        self,
        fields: Sequence[str],
        severity: str = "error",
    ) -> None:
        self.fields = list(fields)
        self.severity = severity
        self.name = "unique_constraint"
        self.description = f"Ensure unique constraint on: {self.fields}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        seen: dict[tuple, list[int]] = {}
        duplicates: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            key = tuple(record.get(f) for f in self.fields)
            if key in seen:
                duplicates.append(
                    {
                        "row": idx,
                        "field": self.fields,
                        "duplicate_key": key,
                        "first_seen": seen[key],
                    }
                )
            else:
                seen[key] = [idx]

        passed = len(duplicates) == 0
        message = (
            "All values unique."
            if passed
            else f"Duplicate values found in {len(duplicates)} row(s): {duplicates}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"duplicates": duplicates},
            )
        ]


# 8. Foreign Key Reference
class ForeignKeyReferenceRule(ValidationRule):
    """Validate that field values exist in a reference set (FK check)."""

    def __init__(
        self,
        field: str,
        reference_values: Sequence[Any],
        severity: str = "error",
    ) -> None:
        self.field = field
        self.reference_set: set = set(reference_values)
        self.severity = severity
        self.name = "foreign_key_reference"
        self.description = f"Validate {field} references exist in reference set"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        missing_refs: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is not None and value not in self.reference_set:
                missing_refs.append(
                    {"row": idx, "field": self.field, "value": repr(value)[:100]}
                )

        passed = len(missing_refs) == 0
        message = (
            "All foreign key references valid."
            if passed
            else f"Broken references in {len(missing_refs)} row(s): {missing_refs}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"missing_refs": missing_refs},
            )
        ]


# 9. Timestamp Format
class TimestampFormatRule(ValidationRule):
    """Validate timestamp fields match expected format."""

    SUPPORTED_FORMATS = {
        "iso": "%Y-%m-%dT%H:%M:%S",
        "iso_tz": "%Y-%m-%dT%H:%M:%S%z",
        "date": "%Y-%m-%d",
        "datetime": "%Y-%m-%d %H:%M:%S",
        "unix": "unix",
    }

    def __init__(
        self,
        field: str,
        fmt: str = "iso",
        severity: str = "error",
    ) -> None:
        self.field = field
        self.fmt = fmt
        self.severity = severity
        self.name = "timestamp_format"
        self.description = f"Validate timestamp format '{fmt}' on field: {field}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        errors: list[dict[str, Any]] = []
        fmt_str = self.SUPPORTED_FORMATS.get(self.fmt, self.fmt)

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            try:
                if fmt_str == "unix":
                    float(value)
                elif isinstance(value, datetime):
                    pass  # already a datetime
                else:
                    datetime.strptime(str(value), fmt_str)
            except (ValueError, TypeError, OSError):
                errors.append(
                    {
                        "row": idx,
                        "field": self.field,
                        "value": repr(value)[:100],
                        "format": self.fmt,
                    }
                )

        passed = len(errors) == 0
        message = (
            "All timestamps valid."
            if passed
            else f"Invalid timestamps in {len(errors)} row(s): {errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"errors": errors},
            )
        ]


# 10. Numeric Precision
class NumericPrecisionRule(ValidationRule):
    """Validate numeric values have at most N decimal places."""

    def __init__(
        self,
        field: str,
        max_decimals: int,
        severity: str = "error",
    ) -> None:
        self.field = field
        self.max_decimals = max_decimals
        self.severity = severity
        self.name = "numeric_precision"
        self.description = f"Validate {field} has at most {max_decimals} decimal places"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        precision_errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            try:
                decimal_places = (
                    len(str(value).rstrip("0").split(".")[-1])
                    if "." in str(value)
                    else 0
                )
                if decimal_places > self.max_decimals:
                    precision_errors.append(
                        {
                            "row": idx,
                            "field": self.field,
                            "value": value,
                            "decimal_places": decimal_places,
                            "max_allowed": self.max_decimals,
                        }
                    )
            except (ValueError, IndexError):
                precision_errors.append(
                    {
                        "row": idx,
                        "field": self.field,
                        "value": repr(value)[:100],
                        "error": "not a number",
                    }
                )

        passed = len(precision_errors) == 0
        message = (
            "All numeric precision within limits."
            if passed
            else f"Precision errors in {len(precision_errors)} cell(s): {precision_errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"precision_errors": precision_errors},
            )
        ]


# 11. String Length Validation
class StringLengthValidationRule(ValidationRule):
    """Validate string field length constraints."""

    def __init__(
        self,
        field: str,
        min_length: int = 0,
        max_length: int | None = None,
        severity: str = "error",
    ) -> None:
        self.field = field
        self.min_length = min_length
        self.max_length = max_length
        self.severity = severity
        self.name = "string_length"
        self.description = (
            f"Validate {field} length: min={min_length}, max={max_length}"
        )

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        length_errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            length = len(str(value))
            if length < self.min_length or (
                self.max_length is not None and length > self.max_length
            ):
                length_errors.append(
                    {
                        "row": idx,
                        "field": self.field,
                        "length": length,
                        "min": self.min_length,
                        "max": self.max_length,
                    }
                )

        passed = len(length_errors) == 0
        message = (
            "All string lengths valid."
            if passed
            else f"Length errors in {len(length_errors)} cell(s): {length_errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"length_errors": length_errors},
            )
        ]


# 12. Array/List Size Validation
class ArraySizeValidationRule(ValidationRule):
    """Validate that array/list fields have expected size constraints."""

    def __init__(
        self,
        field: str,
        min_size: int = 0,
        max_size: int | None = None,
        severity: str = "error",
    ) -> None:
        self.field = field
        self.min_size = min_size
        self.max_size = max_size
        self.severity = severity
        self.name = "array_size_validation"
        self.description = (
            f"Validate {field} array size: min={min_size}, max={max_size}"
        )

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        size_errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            if not isinstance(value, (list, tuple)):
                size_errors.append(
                    {"row": idx, "field": self.field, "error": "not a list/tuple"}
                )
                continue
            size = len(value)
            if size < self.min_size or (
                self.max_size is not None and size > self.max_size
            ):
                size_errors.append(
                    {
                        "row": idx,
                        "field": self.field,
                        "size": size,
                        "min": self.min_size,
                        "max": self.max_size,
                    }
                )

        passed = len(size_errors) == 0
        message = (
            "All array sizes valid."
            if passed
            else f"Size errors in {len(size_errors)} cell(s): {size_errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"size_errors": size_errors},
            )
        ]


# 13. JSON Schema Validation
class JSONSchemaValidationRule(ValidationRule):
    """Validate that a field contains valid JSON matching a schema subset."""

    def __init__(
        self,
        field: str,
        schema: dict[str, Any] | None = None,
        severity: str = "error",
    ) -> None:
        self.field = field
        self.schema = schema or {}
        self.severity = severity
        self.name = "json_schema_validation"
        self.description = f"Validate JSON structure in field: {field}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            # Try to parse as JSON if it's a string
            parsed = value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    errors.append(
                        {
                            "row": idx,
                            "field": self.field,
                            "error": "invalid JSON",
                            "value": repr(value)[:100],
                        }
                    )
                    continue

            # Check required keys in parsed object
            if isinstance(parsed, dict):
                for key in self.schema.get("required", []):
                    if key not in parsed:
                        errors.append(
                            {
                                "row": idx,
                                "field": self.field,
                                "error": f"missing required key '{key}'",
                            }
                        )

                # Check types of fields
                properties = self.schema.get("properties", {})
                for key, type_constraint in properties.items():
                    if key in parsed:
                        expected_type = type_constraint.get("type")
                        actual = parsed[key]
                        if expected_type == "string" and not isinstance(actual, str):
                            errors.append(
                                {
                                    "row": idx,
                                    "field": self.field,
                                    "key": key,
                                    "error": f"expected string, got {type(actual).__name__}",
                                }
                            )
                        elif expected_type == "number" and not isinstance(
                            actual, (int, float)
                        ):
                            errors.append(
                                {
                                    "row": idx,
                                    "field": self.field,
                                    "key": key,
                                    "error": f"expected number, got {type(actual).__name__}",
                                }
                            )
                        elif expected_type == "boolean" and not isinstance(
                            actual, bool
                        ):
                            errors.append(
                                {
                                    "row": idx,
                                    "field": self.field,
                                    "key": key,
                                    "error": f"expected boolean, got {type(actual).__name__}",
                                }
                            )

        passed = len(errors) == 0
        message = (
            "All JSON structures valid."
            if passed
            else f"JSON validation errors in {len(errors)} cell(s): {errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"errors": errors},
            )
        ]


# 14. Categorical Value Distribution
class CategoricalDistributionRule(ValidationRule):
    """Check that categorical field values have a reasonable distribution.

    Flags when a single category dominates beyond the allowed threshold,
    or when the number of unique categories exceeds a limit.
    """

    def __init__(
        self,
        field: str,
        max_dominance: float = 0.95,
        max_unique: int | None = None,
        severity: str = "warning",
    ) -> None:
        self.field = field
        self.max_dominance = max_dominance
        self.max_unique = max_unique
        self.severity = severity
        self.name = "categorical_distribution"
        self.description = f"Check {field} distribution: max_dominance={max_dominance}, max_unique={max_unique}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        issues: list[str] = []

        values = [r.get(self.field) for r in records if r.get(self.field) is not None]
        if not values:
            return [
                ValidationResult(
                    rule_name=self.name,
                    passed=True,
                    message="No values to check distribution.",
                    severity="info",
                )
            ]

        total = len(values)
        from collections import Counter

        counts = Counter(values)
        most_common_val, most_common_count = counts.most_common(1)[0]
        dominance = most_common_count / total

        if dominance > self.max_dominance:
            issues.append(
                f"Value {repr(most_common_val)} dominates at {dominance:.1%} (threshold {self.max_dominance:.1%})"
            )

        if self.max_unique is not None and len(counts) > self.max_unique:
            issues.append(
                f"Too many unique values: {len(counts)} (max {self.max_unique})"
            )

        passed = len(issues) == 0
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message="; ".join(issues) if issues else "Distribution looks healthy.",
                severity=self.severity,
                details={
                    "unique_count": len(counts),
                    "dominance": dominance,
                    "distribution": {str(k): v for k, v in counts.most_common(10)},
                },
            )
        ]


# 15. Data Freshness
class DataFreshnessRule(ValidationRule):
    """Check that data timestamps are within a freshness window."""

    def __init__(
        self,
        field: str,
        max_age_hours: float,
        severity: str = "warning",
    ) -> None:
        self.field = field
        self.max_age_hours = max_age_hours
        self.severity = severity
        self.name = "data_freshness"
        self.description = f"Ensure {field} is within {max_age_hours}h of now"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        now = datetime.now(UTC)
        stale: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            try:
                if isinstance(value, datetime):
                    ts = value
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                elif isinstance(value, (int, float)):
                    ts = datetime.fromtimestamp(value, tz=UTC)
                else:
                    ts = datetime.fromisoformat(str(value))

                age_hours = (now - ts).total_seconds() / 3600
                if age_hours > self.max_age_hours:
                    stale.append(
                        {
                            "row": idx,
                            "field": self.field,
                            "age_hours": round(age_hours, 2),
                        }
                    )
            except (ValueError, TypeError, OSError):
                stale.append(
                    {"row": idx, "field": self.field, "error": "cannot parse timestamp"}
                )

        passed = len(stale) == 0
        message = (
            "All data within freshness window."
            if passed
            else f"Stale data in {len(stale)} row(s): {stale}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"stale": stale},
            )
        ]


# 16. File Format Validation
class FileFormatValidationRule(ValidationRule):
    """Validate that a string field contains a value ending with an allowed extension."""

    def __init__(
        self,
        field: str,
        allowed_extensions: Sequence[str],
        severity: str = "error",
    ) -> None:
        self.field = field
        self.allowed_extensions = [
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in allowed_extensions
        ]
        self.severity = severity
        self.name = "file_format_validation"
        self.description = (
            f"Validate file format for {field}: {self.allowed_extensions}"
        )

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            value_str = str(value).lower()
            if not any(value_str.endswith(ext) for ext in self.allowed_extensions):
                errors.append(
                    {"row": idx, "field": self.field, "value": repr(value)[:100]}
                )

        passed = len(errors) == 0
        message = (
            "All file formats valid."
            if passed
            else f"Invalid file formats in {len(errors)} row(s): {errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"errors": errors},
            )
        ]


# 17. Encoding Validation
class EncodingValidationRule(ValidationRule):
    """Validate that string fields can be encoded/decoded with a specific encoding."""

    def __init__(
        self,
        fields: Sequence[str],
        encoding: str = "utf-8",
        severity: str = "error",
    ) -> None:
        self.fields = list(fields)
        self.encoding = encoding
        self.severity = severity
        self.name = "encoding_validation"
        self.description = f"Validate {encoding} encoding for fields: {self.fields}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        errors: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for f in self.fields:
                value = record.get(f)
                if value is None:
                    continue
                try:
                    str(value).encode(self.encoding)
                except (UnicodeEncodeError, UnicodeDecodeError):
                    errors.append({"row": idx, "field": f, "value": repr(value)[:50]})

        passed = len(errors) == 0
        message = (
            "All values encode correctly."
            if passed
            else f"Encoding errors in {len(errors)} cell(s): {errors}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"errors": errors},
            )
        ]


# 18. Duplicate Detection
class DuplicateDetectionRule(ValidationRule):
    """Detect exact duplicate rows across all fields."""

    def __init__(
        self,
        fields: Sequence[str] | None = None,
        severity: str = "warning",
    ) -> None:
        self.fields = list(fields) if fields else None
        self.severity = severity
        self.name = "duplicate_detection"
        self.description = (
            f"Detect duplicate rows across: {self.fields or 'all fields'}"
        )

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        seen: dict[tuple, int] = {}
        duplicates: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            if self.fields:
                key = tuple(record.get(f) for f in self.fields)
            else:
                key = tuple(sorted(record.items()))
            if key in seen:
                duplicates.append({"row": idx, "duplicate_of": seen[key]})
            else:
                seen[key] = idx

        passed = len(duplicates) == 0
        message = (
            "No duplicate rows found."
            if passed
            else f"Found {len(duplicates)} duplicate row(s): {duplicates}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"duplicates": duplicates, "duplicate_count": len(duplicates)},
            )
        ]


# 19. Cross-Field Validation
class CrossFieldValidationRule(ValidationRule):
    """Validate relationships between two or more fields using a custom predicate."""

    def __init__(
        self,
        name: str,
        description: str,
        predicate: Callable[[dict[str, Any]], bool],
        severity: str = "error",
    ) -> None:
        self.name = name
        self.description = description
        self.predicate = predicate
        self.severity = severity

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        failures: list[int] = []

        for idx, record in enumerate(records):
            try:
                if not self.predicate(record):
                    failures.append(idx)
            except Exception:
                failures.append(idx)

        passed = len(failures) == 0
        message = (
            "Cross-field validation passed."
            if passed
            else f"Cross-field validation failed in {len(failures)} row(s): {failures}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"failure_rows": failures},
            )
        ]


# 20. Custom Business Rule
class CustomBusinessRule(ValidationRule):
    """User-defined validation rule backed by an arbitrary callable."""

    def __init__(
        self,
        name: str,
        description: str,
        check_fn: Callable[[Any], list[ValidationResult]],
    ) -> None:
        self.name = name
        self.description = description
        self.check_fn = check_fn
        self.severity = "error"

    def validate(self, data: Any) -> list[ValidationResult]:
        try:
            return self.check_fn(data)
        except Exception as exc:
            return [
                ValidationResult(
                    rule_name=self.name,
                    passed=False,
                    message=f"Custom rule raised exception: {exc}",
                    severity="error",
                    details={"exception": str(exc)},
                )
            ]


# 21. Non-Negative Rule (bonus)
class NonNegativeRule(ValidationRule):
    """Ensure numeric fields are non-negative (>= 0)."""

    def __init__(
        self,
        fields: Sequence[str],
        severity: str = "error",
    ) -> None:
        self.fields = list(fields)
        self.severity = severity
        self.name = "non_negative"
        self.description = f"Ensure {self.fields} are non-negative"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        negatives: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for f in self.fields:
                value = record.get(f)
                if value is not None and isinstance(value, (int, float)) and value < 0:
                    negatives.append({"row": idx, "field": f, "value": value})

        passed = len(negatives) == 0
        message = (
            "All values non-negative."
            if passed
            else f"Negative values in {len(negatives)} cell(s): {negatives}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"negatives": negatives},
            )
        ]


# 22. NotEmpty String Rule (bonus)
class NotEmptyStringRule(ValidationRule):
    """Ensure string fields are not empty or whitespace-only."""

    def __init__(
        self,
        fields: Sequence[str],
        severity: str = "error",
    ) -> None:
        self.fields = list(fields)
        self.severity = severity
        self.name = "not_empty_string"
        self.description = f"Ensure {self.fields} are not empty strings"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        empty: list[dict[str, Any]] = []

        for idx, record in enumerate(records):
            for f in self.fields:
                value = record.get(f)
                if isinstance(value, str) and value.strip() == "":
                    empty.append({"row": idx, "field": f})

        passed = len(empty) == 0
        message = (
            "No empty strings found."
            if passed
            else f"Empty strings in {len(empty)} cell(s): {empty}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"empty": empty},
            )
        ]


# 23. Monotonic Field Rule (bonus)
class MonotonicFieldRule(ValidationRule):
    """Check that a numeric field is monotonic (increasing or decreasing) across records."""

    def __init__(
        self,
        field: str,
        direction: str = "increasing",
        severity: str = "error",
    ) -> None:
        self.field = field
        self.direction = direction
        self.severity = severity
        self.name = "monotonic_field"
        self.description = f"Ensure {field} is {direction}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        violations: list[dict[str, Any]] = []

        prev = None
        for idx, record in enumerate(records):
            value = record.get(self.field)
            if value is None:
                continue
            if prev is not None:
                if (
                    self.direction == "increasing"
                    and value < prev
                    or self.direction == "decreasing"
                    and value > prev
                ):
                    violations.append({"row": idx, "value": value, "prev": prev})
            prev = value

        passed = len(violations) == 0
        message = (
            f"Field is {self.direction}."
            if passed
            else f"Monotonicity violated in {len(violations)} row(s): {violations}"
        )
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={"violations": violations},
            )
        ]


# 24. Row Count Rule (bonus)
class RowCountRule(ValidationRule):
    """Validate that dataset has at least/ at most N rows."""

    def __init__(
        self,
        min_rows: int = 0,
        max_rows: int | None = None,
        severity: str = "error",
    ) -> None:
        self.min_rows = min_rows
        self.max_rows = max_rows
        self.severity = severity
        self.name = "row_count"
        self.description = f"Row count between {min_rows} and {max_rows}"

    def validate(self, data: Any) -> list[ValidationResult]:
        records = _to_records(data)
        count = len(records)
        issues: list[str] = []

        if count < self.min_rows:
            issues.append(f"Row count {count} below minimum {self.min_rows}")
        if self.max_rows is not None and count > self.max_rows:
            issues.append(f"Row count {count} above maximum {self.max_rows}")

        passed = len(issues) == 0
        message = f"Row count {count} is valid." if passed else "; ".join(issues)
        return [
            ValidationResult(
                rule_name=self.name,
                passed=passed,
                message=message,
                severity=self.severity,
                details={
                    "row_count": count,
                    "min": self.min_rows,
                    "max": self.max_rows,
                },
            )
        ]


# ===================================================================
# Composite Rule
# ===================================================================


class CompositeRule(ValidationRule):
    """Group multiple rules under a single name and aggregate results."""

    def __init__(
        self,
        name: str,
        description: str,
        rules: Sequence[ValidationRule],
        severity: str = "error",
    ) -> None:
        self.name = name
        self.description = description
        self.rules = list(rules)
        self.severity = severity

    def validate(self, data: Any) -> list[ValidationResult]:
        all_results: list[ValidationResult] = []
        for rule in self.rules:
            try:
                all_results.extend(rule.validate(data))
            except Exception as exc:
                all_results.append(
                    ValidationResult(
                        rule_name=rule.name,
                        passed=False,
                        message=f"Rule execution failed: {exc}",
                        severity="error",
                        details={"exception": str(exc)},
                    )
                )
        return all_results


# ===================================================================
# DataValidator (main orchestrator)
# ===================================================================


class DataValidator:
    """Central orchestrator for running validation rules against datasets.

    Usage::

        validator = DataValidator()
        validator.register_rule(SchemaCompletenessRule(["name", "age"]))
        validator.register_rule(RangeValidationRule({"age": {"min": 0, "max": 150}}))

        results = validator.validate(data)
        for r in results:
            print(f"{r.rule_name}: {'PASS' if r.passed else 'FAIL'} - {r.message}")
    """

    def __init__(self) -> None:
        self._rules: list[ValidationRule] = []

    def register_rule(self, rule: ValidationRule) -> None:
        """Register a validation rule.

        Args:
            rule: Instance of a ``ValidationRule`` subclass.
        """
        self._rules.append(rule)

    def unregister_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if found and removed."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def get_rules(self) -> list[ValidationRule]:
        """Return a copy of registered rules."""
        return list(self._rules)

    def validate(self, data: Any) -> list[ValidationResult]:
        """Run all registered rules against *data*.

        Args:
            data: Data to validate (list-of-dicts, DataFrame, or single dict).

        Returns:
            Flat list of ``ValidationResult`` from all rules.
        """
        all_results: list[ValidationResult] = []
        for rule in self._rules:
            try:
                all_results.extend(rule.validate(data))
            except Exception as exc:
                all_results.append(
                    ValidationResult(
                        rule_name=rule.name,
                        passed=False,
                        message=f"Rule execution error: {exc}",
                        severity="error",
                        details={"exception": str(exc)},
                    )
                )
        return all_results

    def validate_schema(self, data: dict[str, Any], schema: dict[str, Any]) -> bool:
        """Validate a single record against a schema dict.

        The schema dict maps field names to expected types::

            validator.validate_schema(
                {"name": "Alice", "age": 30},
                {"name": str, "age": int}
            )

        Args:
            data: Record dict to validate.
            schema: Mapping of field name -> expected type.

        Returns:
            True if all present fields match the schema types.
        """
        for field_name, expected_type in schema.items():
            if field_name in data and data[field_name] is not None:
                if not isinstance(data[field_name], expected_type):
                    return False
        return True

    def get_rule_summary(self) -> dict[str, Any]:
        """Return a summary of registered rules.

        Returns:
            Dict with rule names, descriptions, and count.
        """
        return {
            "total_rules": len(self._rules),
            "rules": [
                {
                    "name": r.name,
                    "description": r.description,
                    "severity": r.severity,
                }
                for r in self._rules
            ],
        }


# ===================================================================
# RuleRegistry (singleton lookup)
# ===================================================================


class RuleRegistry:
    """Named registry of rule factories for easy lookup and reuse.

    Usage::

        registry = RuleRegistry()
        registry.register("required_fields", lambda: SchemaCompletenessRule(["id", "name"]))
        rule = registry.create("required_fields")
    """

    _global: RuleRegistry | None = None

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ValidationRule]] = {}

    @classmethod
    def global_registry(cls) -> RuleRegistry:
        """Return the global singleton registry."""
        if cls._global is None:
            cls._global = cls()
        return cls._global

    def register(self, name: str, factory: Callable[[], ValidationRule]) -> None:
        """Register a rule factory under *name*."""
        self._factories[name] = factory

    def create(self, name: str) -> ValidationRule:
        """Instantiate a rule by registered name."""
        if name not in self._factories:
            raise KeyError(
                f"Rule '{name}' not found in registry. Available: {list(self._factories.keys())}"
            )
        return self._factories[name]()

    def list_rules(self) -> list[str]:
        """Return list of registered rule names."""
        return list(self._factories.keys())

    def unregister(self, name: str) -> bool:
        """Remove a rule factory by name."""
        if name in self._factories:
            del self._factories[name]
            return True
        return False
