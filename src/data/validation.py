"""
Data Validation Module for ChiseAI ML Pipeline.

Provides comprehensive validators for ML data quality assurance.
Part of ML-DATA-001-A.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationStatus(Enum):
    """Status of a validation result."""

    PASSED = auto()
    FAILED = auto()
    SKIPPED = auto()


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""

    validator_name: str
    message: str
    severity: ValidationSeverity
    field: str | None = None
    value: Any = None
    expected: Any = None
    suggestion: str = ""


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    validator_name: str
    status: ValidationStatus
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.PASSED

    @property
    def has_errors(self) -> bool:
        return any(
            i.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]
            for i in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == ValidationSeverity.WARNING for i in self.issues)


@dataclass
class DataQualityReport:
    """Comprehensive data quality report."""

    total_records: int
    valid_records: int
    invalid_records: int
    validation_results: list[ValidationResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def error_count(self) -> int:
        return sum(
            len([i for i in r.issues if i.severity == ValidationSeverity.ERROR])
            for r in self.validation_results
        )

    @property
    def warning_count(self) -> int:
        return sum(
            len([i for i in r.issues if i.severity == ValidationSeverity.WARNING])
            for r in self.validation_results
        )


class DataValidator(ABC):
    """Abstract base class for all data validators."""

    def __init__(self, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}
        self._execution_count = 0
        self._last_execution_time: datetime | None = None

    @abstractmethod
    def validate(
        self, data: Any, context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """Validate data and return result."""
        pass

    def _create_result(
        self,
        status: ValidationStatus,
        issues: list[ValidationIssue] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Helper to create validation result."""
        self._execution_count += 1
        self._last_execution_time = datetime.now()
        return ValidationResult(
            validator_name=self.name,
            status=status,
            issues=issues or [],
            metadata=metadata or {},
        )

    def _create_issue(
        self,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        field: str | None = None,
        value: Any = None,
        expected: Any = None,
        suggestion: str = "",
    ) -> ValidationIssue:
        """Helper to create validation issue."""
        return ValidationIssue(
            validator_name=self.name,
            message=message,
            severity=severity,
            field=field,
            value=value,
            expected=expected,
            suggestion=suggestion,
        )


# =============================================================================
# VALIDATOR 1: NullValidator
# =============================================================================


class NullValidator(DataValidator):
    """Validates that fields are not null/None."""

    def __init__(self, fields: list[str] | None = None, allow_empty: bool = False):
        super().__init__(
            "NullValidator", {"fields": fields, "allow_empty": allow_empty}
        )
        self.fields = fields
        self.allow_empty = allow_empty

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        if not isinstance(data, dict):
            return self._create_result(
                ValidationStatus.FAILED,
                [
                    self._create_issue(
                        "Data must be a dictionary", ValidationSeverity.ERROR
                    )
                ],
            )

        fields_to_check = self.fields if self.fields else data.keys()

        for _field in fields_to_check:
            if _field not in data:
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is missing",
                        ValidationSeverity.ERROR,
                        field=_field,
                    )
                )
            elif data[_field] is None:
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is null",
                        ValidationSeverity.ERROR,
                        field=_field,
                    )
                )
            elif not self.allow_empty and data[_field] == "":
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is empty",
                        ValidationSeverity.WARNING,
                        field=_field,
                        value=data[_field],
                        suggestion="Consider allowing empty or provide default value",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 2: TypeValidator
# =============================================================================


class TypeValidator(DataValidator):
    """Validates that fields have correct types."""

    def __init__(self, type_map: dict[str, type], strict: bool = True):
        super().__init__("TypeValidator", {"type_map": type_map, "strict": strict})
        self.type_map = type_map
        self.strict = strict

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field_name, expected_type in self.type_map.items():
            if _field_name not in data:
                continue

            value = data[_field_name]
            if value is None:
                continue

            if not isinstance(value, expected_type):
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' has wrong type",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=type(value).__name__,
                        expected=expected_type.__name__,
                        suggestion=f"Expected {expected_type.__name__}, got {type(value).__name__}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 3: RangeValidator
# =============================================================================


class RangeValidator(DataValidator):
    """Validates that numeric fields are within specified ranges."""

    def __init__(self, ranges: dict[str, dict[str, float]]):
        """
        ranges: {"field": {"min": 0, "max": 100, "inclusive": True}}
        """
        super().__init__("RangeValidator", {"ranges": ranges})
        self.ranges = ranges

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field_name, range_spec in self.ranges.items():
            if _field_name not in data or data[_field_name] is None:
                continue

            value = data[_field_name]
            if not isinstance(value, (int, float)):
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' is not numeric",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=value,
                    )
                )
                continue

            min_val = range_spec.get("min")
            max_val = range_spec.get("max")
            inclusive = range_spec.get("inclusive", True)

            if min_val is not None:
                if inclusive and value < min_val:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field_name}' is below minimum",
                            ValidationSeverity.ERROR,
                            field=_field_name,
                            value=value,
                            expected=f"{min_val}",
                            suggestion=f"Value must be >= {min_val}",
                        )
                    )
                elif not inclusive and value <= min_val:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field_name}' is at or below minimum",
                            ValidationSeverity.ERROR,
                            field=_field_name,
                            value=value,
                            expected=f"> {min_val}",
                        )
                    )

            if max_val is not None:
                if inclusive and value > max_val:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field_name}' exceeds maximum",
                            ValidationSeverity.ERROR,
                            field=_field_name,
                            value=value,
                            expected=f"{max_val}",
                            suggestion=f"Value must be <= {max_val}",
                        )
                    )
                elif not inclusive and value >= max_val:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field_name}' is at or above maximum",
                            ValidationSeverity.ERROR,
                            field=_field_name,
                            value=value,
                            expected=f"< {max_val}",
                        )
                    )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 4: PatternValidator
# =============================================================================


class PatternValidator(DataValidator):
    """Validates string fields against regex patterns."""

    def __init__(self, patterns: dict[str, str]):
        """patterns: {"field": "regex_pattern"}"""
        super().__init__("PatternValidator", {"patterns": patterns})
        self.patterns = {k: re.compile(v) for k, v in patterns.items()}

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field_name, pattern in self.patterns.items():
            if _field_name not in data or data[_field_name] is None:
                continue

            value = str(data[_field_name])
            if not pattern.match(value):
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' does not match required pattern",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=value,
                        expected=pattern.pattern,
                        suggestion=f"Value must match pattern: {pattern.pattern}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 5: LengthValidator
# =============================================================================


class LengthValidator(DataValidator):
    """Validates length of string, list, or dict fields."""

    def __init__(self, length_specs: dict[str, dict[str, int]]):
        """length_specs: {"field": {"min": 1, "max": 100}}"""
        super().__init__("LengthValidator", {"length_specs": length_specs})
        self.length_specs = length_specs

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field_name, specs in self.length_specs.items():
            if _field_name not in data or data[_field_name] is None:
                continue

            value = data[_field_name]
            if hasattr(value, "__len__"):
                length = len(value)
            else:
                continue

            min_len = specs.get("min")
            max_len = specs.get("max")

            if min_len is not None and length < min_len:
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' is too short",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=length,
                        expected=f"{min_len}",
                        suggestion=f"Length must be >= {min_len}",
                    )
                )

            if max_len is not None and length > max_len:
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' is too long",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=length,
                        expected=f"{max_len}",
                        suggestion=f"Length must be <= {max_len}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 6: UniquenessValidator
# =============================================================================


class UniquenessValidator(DataValidator):
    """Validates uniqueness of values across records."""

    def __init__(self, fields: list[str], case_sensitive: bool = True):
        super().__init__(
            "UniquenessValidator", {"fields": fields, "case_sensitive": case_sensitive}
        )
        self.fields = fields
        self.case_sensitive = case_sensitive
        self._seen_values: set[tuple] = set()

    def validate(
        self, data: list[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []
        seen_in_batch: set[tuple] = set()

        if not isinstance(data, list):
            return self._create_result(
                ValidationStatus.FAILED,
                [
                    self._create_issue(
                        "Data must be a list of records", ValidationSeverity.ERROR
                    )
                ],
            )

        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                continue

            # Create key from specified fields
            key_parts = []
            for _field in self.fields:
                value = record.get(_field)
                if value is None:
                    key_parts.append(None)
                elif isinstance(value, str) and not self.case_sensitive:
                    key_parts.append(value.lower())
                else:
                    key_parts.append(value)

            key = tuple(key_parts)

            if key in self._seen_values or key in seen_in_batch:
                issues.append(
                    self._create_issue(
                        f"Duplicate record at index {idx}",
                        ValidationSeverity.ERROR,
                        field=",".join(self.fields),
                        value=key,
                        suggestion="Ensure combination of fields is unique",
                    )
                )
            else:
                seen_in_batch.add(key)

        # Update global seen values
        self._seen_values.update(seen_in_batch)

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(
            status, issues, {"unique_records": len(seen_in_batch)}
        )


# =============================================================================
# VALIDATOR 7: DateTimeValidator
# =============================================================================


class DateTimeValidator(DataValidator):
    """Validates datetime fields."""

    def __init__(
        self,
        fields: list[str],
        format_str: str | None = None,
        min_date: datetime | None = None,
        max_date: datetime | None = None,
        allow_future: bool = True,
        allow_past: bool = True,
    ):
        super().__init__(
            "DateTimeValidator",
            {
                "fields": fields,
                "format": format_str,
                "min_date": min_date,
                "max_date": max_date,
                "allow_future": allow_future,
                "allow_past": allow_past,
            },
        )
        self.fields = fields
        self.format_str = format_str
        self.min_date = min_date
        self.max_date = max_date
        self.allow_future = allow_future
        self.allow_past = allow_past

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []
        now = datetime.now()

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = data[_field]
            dt_value = None

            # Parse datetime
            if isinstance(value, datetime):
                dt_value = value
            elif isinstance(value, str):
                try:
                    if self.format_str:
                        dt_value = datetime.strptime(value, self.format_str)
                    else:
                        dt_value = datetime.fromisoformat(value)
                except ValueError:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' has invalid datetime format",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=value,
                            expected=self.format_str or "ISO format",
                            suggestion="Use ISO 8601 format or specify format",
                        )
                    )
                    continue

            if dt_value:
                # Check range
                if self.min_date and dt_value < self.min_date:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' is before minimum date",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=str(dt_value),
                            expected=f">= {self.min_date}",
                        )
                    )

                if self.max_date and dt_value > self.max_date:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' is after maximum date",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=str(dt_value),
                            expected=f"<= {self.max_date}",
                        )
                    )

                # Check future/past
                if not self.allow_future and dt_value > now:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' is in the future",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=str(dt_value),
                            suggestion="Future dates are not allowed",
                        )
                    )

                if not self.allow_past and dt_value < now:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' is in the past",
                            ValidationSeverity.WARNING,
                            field=_field,
                            value=str(dt_value),
                        )
                    )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 8: EnumValidator
# =============================================================================


class EnumValidator(DataValidator):
    """Validates that fields have values from a predefined set."""

    def __init__(
        self, allowed_values: dict[str, list[Any]], case_sensitive: bool = True
    ):
        super().__init__(
            "EnumValidator",
            {"allowed_values": allowed_values, "case_sensitive": case_sensitive},
        )
        self.allowed_values = allowed_values
        self.case_sensitive = case_sensitive

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field_name, allowed in self.allowed_values.items():
            if _field_name not in data or data[_field_name] is None:
                continue

            value = data[_field_name]

            if not self.case_sensitive and isinstance(value, str):
                valid = value.lower() in [str(v).lower() for v in allowed]
            else:
                valid = value in allowed

            if not valid:
                issues.append(
                    self._create_issue(
                        f"Field '{_field_name}' has invalid value",
                        ValidationSeverity.ERROR,
                        field=_field_name,
                        value=value,
                        expected=allowed,
                        suggestion=f"Value must be one of: {allowed}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 9: SchemaValidator
# =============================================================================


class SchemaValidator(DataValidator):
    """Validates data against a predefined schema."""

    def __init__(
        self,
        required_fields: list[str],
        optional_fields: list[str] | None = None,
        allow_extra: bool = False,
    ):
        super().__init__(
            "SchemaValidator",
            {
                "required_fields": required_fields,
                "optional_fields": optional_fields,
                "allow_extra": allow_extra,
            },
        )
        self.required_fields = required_fields
        self.optional_fields = optional_fields or []
        self.allow_extra = allow_extra

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        if not isinstance(data, dict):
            return self._create_result(
                ValidationStatus.FAILED,
                [
                    self._create_issue(
                        "Data must be a dictionary", ValidationSeverity.ERROR
                    )
                ],
            )

        # Check required fields
        for _field in self.required_fields:
            if _field not in data:
                issues.append(
                    self._create_issue(
                        f"Required field '{_field}' is missing",
                        ValidationSeverity.ERROR,
                        field=_field,
                    )
                )

        # Check for extra fields
        if not self.allow_extra:
            allowed_fields = set(self.required_fields + self.optional_fields)
            extra_fields = set(data.keys()) - allowed_fields
            for field in extra_fields:
                issues.append(
                    self._create_issue(
                        f"Unexpected field '{field}'",
                        ValidationSeverity.WARNING,
                        field=field,
                        suggestion="Remove field or add to schema",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 10: CrossFieldValidator
# =============================================================================


class CrossFieldValidator(DataValidator):
    """Validates relationships between multiple fields."""

    def __init__(self, validations: list[dict[str, Any]]):
        """
        validations: [
            {"field1": "start_date", "field2": "end_date", "operator": "<="}
        ]
        """
        super().__init__("CrossFieldValidator", {"validations": validations})
        self.validations = validations

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for validation in self.validations:
            field1 = validation.get("field1")
            field2 = validation.get("field2")
            operator = validation.get("operator", "==")

            if field1 not in data or field2 not in data:
                continue

            value1 = data[field1]
            value2 = data[field2]

            if value1 is None or value2 is None:
                continue

            valid = False
            try:
                if operator == "==":
                    valid = value1 == value2
                elif operator == "!=":
                    valid = value1 != value2
                elif operator == ">":
                    valid = value1 > value2
                elif operator == ">=":
                    valid = value1 >= value2
                elif operator == "<":
                    valid = value1 < value2
                elif operator == "<=":
                    valid = value1 <= value2
                elif operator == "in":
                    valid = value1 in value2
                elif operator == "not_in":
                    valid = value1 not in value2
            except TypeError:
                issues.append(
                    self._create_issue(
                        f"Cannot compare '{field1}' and '{field2}': type mismatch",
                        ValidationSeverity.ERROR,
                        field=f"{field1},{field2}",
                    )
                )
                continue

            if not valid:
                issues.append(
                    self._create_issue(
                        f"Cross-field validation failed: {field1} {operator} {field2}",
                        ValidationSeverity.ERROR,
                        field=f"{field1},{field2}",
                        value=f"{value1} {operator} {value2}",
                        expected=f"{field1} {operator} {field2} should be true",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 11: StatisticalValidator
# =============================================================================


class StatisticalValidator(DataValidator):
    """Validates statistical properties of numeric data."""

    def __init__(self, field: str, checks: dict[str, Any]):
        """
        checks: {
            "mean_range": [min, max],
            "std_max": max_std,
            "no_outliers": {"method": "iqr", "threshold": 1.5}
        }
        """
        super().__init__("StatisticalValidator", {"field": field, "checks": checks})
        self.field = field
        self.checks = checks

    def validate(
        self, data: list[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        if not isinstance(data, list):
            return self._create_result(
                ValidationStatus.FAILED,
                [self._create_issue("Data must be a list", ValidationSeverity.ERROR)],
            )

        values = [
            record.get(self.field)
            for record in data
            if record.get(self.field) is not None
        ]
        values = [v for v in values if isinstance(v, (int, float))]

        if len(values) < 2:
            return self._create_result(
                ValidationStatus.PASSED, [], {"sample_size": len(values)}
            )

        # Calculate statistics
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance**0.5

        # Check mean range
        if "mean_range" in self.checks:
            min_mean, max_mean = self.checks["mean_range"]
            if mean < min_mean or mean > max_mean:
                issues.append(
                    self._create_issue(
                        f"Mean of '{self.field}' ({mean:.4f}) outside acceptable range",
                        ValidationSeverity.ERROR,
                        field=self.field,
                        value=mean,
                        expected=f"[{min_mean}, {max_mean}]",
                    )
                )

        # Check std max
        if "std_max" in self.checks:
            max_std = self.checks["std_max"]
            if std > max_std:
                issues.append(
                    self._create_issue(
                        f"Standard deviation of '{self.field}' ({std:.4f}) exceeds maximum",
                        ValidationSeverity.WARNING,
                        field=self.field,
                        value=std,
                        expected=f"<= {max_std}",
                    )
                )

        # Check for outliers
        if "no_outliers" in self.checks:
            outlier_config = self.checks["no_outliers"]
            method = outlier_config.get("method", "iqr")
            threshold = outlier_config.get("threshold", 1.5)

            if method == "iqr":
                sorted_values = sorted(values)
                q1 = sorted_values[len(sorted_values) // 4]
                q3 = sorted_values[3 * len(sorted_values) // 4]
                iqr = q3 - q1
                lower_bound = q1 - threshold * iqr
                upper_bound = q3 + threshold * iqr

                outliers = [v for v in values if v < lower_bound or v > upper_bound]
                if outliers:
                    issues.append(
                        self._create_issue(
                            f"Found {len(outliers)} outliers in '{self.field}'",
                            ValidationSeverity.WARNING,
                            field=self.field,
                            value=f"{len(outliers)} outliers",
                            suggestion=f"Consider investigating values outside [{lower_bound:.2f}, {upper_bound:.2f}]",
                        )
                    )

        status = (
            ValidationStatus.FAILED
            if any(i.severity == ValidationSeverity.ERROR for i in issues)
            else ValidationStatus.PASSED
        )
        metadata = {
            "sample_size": len(values),
            "mean": mean,
            "std": std,
            "min": min(values),
            "max": max(values),
        }

        return self._create_result(status, issues, metadata)


# =============================================================================
# VALIDATOR 12: JSONValidator
# =============================================================================


class JSONValidator(DataValidator):
    """Validates that fields contain valid JSON."""

    def __init__(self, fields: list[str], schema: dict[str, Any] | None = None):
        super().__init__("JSONValidator", {"fields": fields, "schema": schema})
        self.fields = fields
        self.schema = schema

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        import json

        issues = []

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = data[_field]

            # If it's already a dict, it's valid JSON object
            if isinstance(value, dict):
                continue

            # Try to parse as JSON string
            if isinstance(value, str):
                try:
                    json.loads(value)
                except json.JSONDecodeError:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' contains invalid JSON",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=value,
                            expected="Valid JSON object or string",
                            suggestion="Provide valid JSON format",
                        )
                    )
            else:
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is not JSON-serializable",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=type(value).__name__,
                        expected="dict or JSON string",
                        suggestion="Provide a JSON object or valid JSON string",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 15: CoordinateValidator
# =============================================================================


class CoordinateValidator(DataValidator):
    """Validates geographic coordinates."""

    def __init__(self, lat_field: str, lon_field: str):
        super().__init__(
            "CoordinateValidator", {"lat_field": lat_field, "lon_field": lon_field}
        )
        self.lat_field = lat_field
        self.lon_field = lon_field

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        lat = data.get(self.lat_field)
        lon = data.get(self.lon_field)

        if lat is not None:
            if not isinstance(lat, (int, float)):
                issues.append(
                    self._create_issue(
                        f"Latitude field '{self.lat_field}' is not numeric",
                        ValidationSeverity.ERROR,
                        field=self.lat_field,
                        value=lat,
                    )
                )
            elif not -90 <= lat <= 90:
                issues.append(
                    self._create_issue(
                        f"Latitude field '{self.lat_field}' out of range",
                        ValidationSeverity.ERROR,
                        field=self.lat_field,
                        value=lat,
                        expected="-90 to 90",
                        suggestion="Latitude must be between -90 and 90 degrees",
                    )
                )

        if lon is not None:
            if not isinstance(lon, (int, float)):
                issues.append(
                    self._create_issue(
                        f"Longitude field '{self.lon_field}' is not numeric",
                        ValidationSeverity.ERROR,
                        field=self.lon_field,
                        value=lon,
                    )
                )
            elif not -180 <= lon <= 180:
                issues.append(
                    self._create_issue(
                        f"Longitude field '{self.lon_field}' out of range",
                        ValidationSeverity.ERROR,
                        field=self.lon_field,
                        value=lon,
                        expected="-180 to 180",
                        suggestion="Longitude must be between -180 and 180 degrees",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 16: CreditCardValidator
# =============================================================================


class CreditCardValidator(DataValidator):
    """Validates credit card numbers using Luhn algorithm."""

    def __init__(self, field: str, allowed_types: list[str] | None = None):
        super().__init__(
            "CreditCardValidator", {"field": field, "allowed_types": allowed_types}
        )
        self.field = field
        self.allowed_types = allowed_types

    def _luhn_check(self, card_number: str) -> bool:
        """Validate using Luhn algorithm."""
        digits = [int(d) for d in card_number if d.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False

        # Luhn algorithm
        odd_sum = sum(digits[-1::-2])
        even_sum = sum(sum(divmod(d * 2, 10)) for d in digits[-2::-2])
        return (odd_sum + even_sum) % 10 == 0

    def _detect_card_type(self, card_number: str) -> str:
        """Detect card type from number."""
        patterns = {
            "visa": r"^4[0-9]{12}(?:[0-9]{3})?$",
            "mastercard": r"^5[1-5][0-9]{14}$",
            "amex": r"^3[47][0-9]{13}$",
            "discover": r"^6(?:011|5[0-9]{2})[0-9]{12}$",
        }

        for card_type, pattern in patterns.items():
            if re.match(pattern, card_number):
                return card_type
        return "unknown"

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        if self.field not in data or data[self.field] is None:
            return self._create_result(ValidationStatus.PASSED)

        value = str(data[self.field]).replace(" ", "").replace("-", "")

        if not value.isdigit():
            issues.append(
                self._create_issue(
                    f"Credit card number in '{self.field}' contains non-numeric characters",
                    ValidationSeverity.ERROR,
                    field=self.field,
                    suggestion="Remove spaces and dashes",
                )
            )
        elif not self._luhn_check(value):
            issues.append(
                self._create_issue(
                    f"Credit card number in '{self.field}' is invalid (failed Luhn check)",
                    ValidationSeverity.ERROR,
                    field=self.field,
                    suggestion="Check for typos in card number",
                )
            )
        elif self.allowed_types:
            card_type = self._detect_card_type(value)
            if card_type not in self.allowed_types:
                issues.append(
                    self._create_issue(
                        f"Card type '{card_type}' not allowed",
                        ValidationSeverity.ERROR,
                        field=self.field,
                        value=card_type,
                        expected=f"One of: {', '.join(self.allowed_types)}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 17: FilePathValidator
# =============================================================================


class FilePathValidator(DataValidator):
    """Validates file paths."""

    def __init__(
        self,
        fields: list[str],
        must_exist: bool = False,
        allowed_extensions: list[str] | None = None,
        max_length: int = 4096,
    ):
        super().__init__(
            "FilePathValidator",
            {
                "fields": fields,
                "must_exist": must_exist,
                "allowed_extensions": allowed_extensions,
                "max_length": max_length,
            },
        )
        self.fields = fields
        self.must_exist = must_exist
        self.allowed_extensions = allowed_extensions
        self.max_length = max_length

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        import os

        issues = []

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = str(data[_field])

            # Check length
            if len(value) > self.max_length:
                issues.append(
                    self._create_issue(
                        f"File path in '{field}' is too long",
                        ValidationSeverity.ERROR,
                        field=field,
                        value=len(value),
                        expected=f"<= {self.max_length}",
                    )
                )

            # Check extension
            if self.allowed_extensions:
                ext = os.path.splitext(value)[1].lower()
                if ext not in self.allowed_extensions:
                    issues.append(
                        self._create_issue(
                            f"File path in '{field}' has invalid extension",
                            ValidationSeverity.ERROR,
                            field=field,
                            value=ext,
                            expected=f"One of: {', '.join(self.allowed_extensions)}",
                        )
                    )

            # Check existence
            if self.must_exist and not os.path.exists(value):
                issues.append(
                    self._create_issue(
                        f"File path in '{field}' does not exist",
                        ValidationSeverity.ERROR,
                        field=field,
                        value=value,
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 18: PhoneValidator
# =============================================================================


class PhoneValidator(DataValidator):
    """Validates phone numbers."""

    def __init__(
        self,
        fields: list[str],
        country_code: str | None = None,
        formats: list[str] | None = None,
    ):
        super().__init__(
            "PhoneValidator",
            {"fields": fields, "country_code": country_code, "formats": formats},
        )
        self.fields = fields
        self.country_code = country_code
        self.formats = formats

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        # Simple phone number pattern (digits, spaces, dashes, parentheses, +)
        phone_pattern = re.compile(r"^[\d\s\-\(\)\+]+$")

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = str(data[_field]).strip()

            # Check basic characters
            if not phone_pattern.match(value):
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' contains invalid characters for phone number",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        suggestion="Phone should only contain digits, spaces, dashes, parentheses, and +",
                    )
                )
                continue

            # Extract digits only
            digits = "".join(c for c in value if c.isdigit())

            # Check length (10-15 digits)
            if len(digits) < 10 or len(digits) > 15:
                issues.append(
                    self._create_issue(
                        f"Phone number in '{_field}' has invalid length",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=f"{len(digits)} digits",
                        expected="10-15 digits",
                        suggestion="Check for missing or extra digits",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 19: CurrencyValidator
# =============================================================================


class CurrencyValidator(DataValidator):
    """Validates currency amounts."""

    def __init__(
        self,
        field: str,
        currency_field: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        allowed_currencies: list[str] | None = None,
    ):
        super().__init__(
            "CurrencyValidator",
            {
                "field": field,
                "currency_field": currency_field,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "allowed_currencies": allowed_currencies,
            },
        )
        self.field = field
        self.currency_field = currency_field
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.allowed_currencies = allowed_currencies

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        if self.field not in data or data[self.field] is None:
            return self._create_result(ValidationStatus.PASSED)

        amount = data[self.field]

        # Validate amount is numeric
        if not isinstance(amount, (int, float)):
            issues.append(
                self._create_issue(
                    f"Amount field '{self.field}' is not numeric",
                    ValidationSeverity.ERROR,
                    field=self.field,
                    value=amount,
                )
            )
            return self._create_result(ValidationStatus.FAILED, issues)

        # Check range
        if self.min_amount is not None and amount < self.min_amount:
            issues.append(
                self._create_issue(
                    f"Amount in '{self.field}' is below minimum",
                    ValidationSeverity.ERROR,
                    field=self.field,
                    value=amount,
                    expected=f">= {self.min_amount}",
                )
            )

        if self.max_amount is not None and amount > self.max_amount:
            issues.append(
                self._create_issue(
                    f"Amount in '{self.field}' exceeds maximum",
                    ValidationSeverity.ERROR,
                    field=self.field,
                    value=amount,
                    expected=f"<= {self.max_amount}",
                )
            )

        # Check currency
        if self.currency_field and self.allowed_currencies:
            currency = data.get(self.currency_field)
            if currency and currency not in self.allowed_currencies:
                issues.append(
                    self._create_issue(
                        f"Currency '{currency}' is not allowed",
                        ValidationSeverity.ERROR,
                        field=self.currency_field,
                        value=currency,
                        expected=f"One of: {', '.join(self.allowed_currencies)}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 20: UUIDValidator
# =============================================================================


class UUIDValidator(DataValidator):
    """Validates UUID format."""

    UUID_PATTERN = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def __init__(self, fields: list[str], version: int | None = None):
        super().__init__("UUIDValidator", {"fields": fields, "version": version})
        self.fields = fields
        self.version = version

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = str(data[_field]).lower().strip()

            if not self.UUID_PATTERN.match(value):
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is not a valid UUID",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        expected="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        suggestion="UUID should be in standard format with 36 characters",
                    )
                )
            elif self.version:
                # Check UUID version (13th character)
                version_char = value[14]
                expected_version = str(self.version)
                if version_char != expected_version:
                    issues.append(
                        self._create_issue(
                            f"UUID in '{_field}' has wrong version",
                            ValidationSeverity.WARNING,
                            field=_field,
                            value=f"version {version_char}",
                            expected=f"version {expected_version}",
                        )
                    )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 21: IPAddressValidator
# =============================================================================


class IPAddressValidator(DataValidator):
    """Validates IP addresses (IPv4 and IPv6)."""

    def __init__(self, fields: list[str], allow_v4: bool = True, allow_v6: bool = True):
        super().__init__(
            "IPAddressValidator",
            {"fields": fields, "allow_v4": allow_v4, "allow_v6": allow_v6},
        )
        self.fields = fields
        self.allow_v4 = allow_v4
        self.allow_v6 = allow_v6

    def _is_valid_ipv4(self, ip: str) -> bool:
        """Validate IPv4 address."""
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            try:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
        return True

    def _is_valid_ipv6(self, ip: str) -> bool:
        """Simple IPv6 validation."""
        if "::" in ip:
            # Handle :: abbreviation
            parts = ip.split(":")
            if len(parts) > 8:
                return False
        else:
            parts = ip.split(":")
            if len(parts) != 8:
                return False

        for part in parts:
            if part and len(part) > 4:
                return False
            try:
                if part:
                    int(part, 16)
            except ValueError:
                return False
        return True

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = str(data[_field]).strip()

            is_v4 = self._is_valid_ipv4(value)
            is_v6 = self._is_valid_ipv6(value)

            if not is_v4 and not is_v6:
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is not a valid IP address",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        expected="Valid IPv4 or IPv6 address",
                    )
                )
            elif is_v4 and not self.allow_v4:
                issues.append(
                    self._create_issue(
                        f"IPv4 addresses not allowed in '{_field}'",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        expected="IPv6 address",
                    )
                )
            elif is_v6 and not self.allow_v6:
                issues.append(
                    self._create_issue(
                        f"IPv6 addresses not allowed in '{_field}'",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        expected="IPv4 address",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 22: PercentageValidator
# =============================================================================


class PercentageValidator(DataValidator):
    """Validates percentage values."""

    def __init__(
        self,
        fields: list[str],
        allow_decimal: bool = True,
        min_val: float = 0.0,
        max_val: float = 100.0,
    ):
        super().__init__(
            "PercentageValidator",
            {
                "fields": fields,
                "allow_decimal": allow_decimal,
                "min_val": min_val,
                "max_val": max_val,
            },
        )
        self.fields = fields
        self.allow_decimal = allow_decimal
        self.min_val = min_val
        self.max_val = max_val

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for _field in self.fields:
            if _field not in data or data[_field] is None:
                continue

            value = data[_field]

            # Handle percentage strings (e.g., "50%")
            if isinstance(value, str):
                value = value.replace("%", "").strip()
                try:
                    value = float(value)
                except ValueError:
                    issues.append(
                        self._create_issue(
                            f"Field '{_field}' is not a valid percentage",
                            ValidationSeverity.ERROR,
                            field=_field,
                            value=data[_field],
                        )
                    )
                    continue

            if not isinstance(value, (int, float)):
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' is not numeric",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                    )
                )
                continue

            if not self.allow_decimal and value != int(value):
                issues.append(
                    self._create_issue(
                        f"Field '{_field}' must be whole number",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                    )
                )

            if value < self.min_val or value > self.max_val:
                issues.append(
                    self._create_issue(
                        f"Percentage in '{_field}' out of range",
                        ValidationSeverity.ERROR,
                        field=_field,
                        value=value,
                        expected=f"{self.min_val} to {self.max_val}",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 22: EmailValidator
# =============================================================================


class EmailValidator(DataValidator):
    """Validates email addresses."""

    # RFC 5322 simplified email regex
    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def __init__(self, fields: list[str], allow_multiple: bool = False):
        """
        fields: list of field names to validate as emails
        allow_multiple: if True, comma-separated emails are valid
        """
        super().__init__(
            "EmailValidator",
            {"fields": fields, "allow_multiple": allow_multiple},
        )
        self.fields = fields
        self.allow_multiple = allow_multiple

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for fld in self.fields:
            if fld not in data or data[fld] is None:
                continue

            value = str(data[fld])

            if self.allow_multiple:
                emails = [e.strip() for e in value.split(",")]
            else:
                emails = [value]

            for email in emails:
                if not self.EMAIL_REGEX.match(email):
                    issues.append(
                        self._create_issue(
                            f"Field '{field}' is not a valid email address",
                            ValidationSeverity.ERROR,
                            field=field,
                            value=email,
                            expected="valid email format (e.g., user@example.com)",
                        )
                    )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 23: URLValidator
# =============================================================================


class URLValidator(DataValidator):
    """Validates URL strings."""

    # Simplified URL regex
    URL_REGEX = re.compile(
        r"^https?://"
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
        r"localhost|"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(?::\d+)?"
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    def __init__(self, fields: list[str]):
        """fields: list of field names to validate as URLs"""
        super().__init__("URLValidator", {"fields": fields})
        self.fields = fields

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for fld in self.fields:
            if fld not in data or data[fld] is None:
                continue

            value = str(data[fld])
            if not self.URL_REGEX.match(value):
                issues.append(
                    self._create_issue(
                        f"Field '{fld}' is not a valid URL",
                        ValidationSeverity.ERROR,
                        field=field,
                        value=value,
                        expected="valid URL format (e.g., https://example.com)",
                    )
                )

        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED
        return self._create_result(status, issues)


# =============================================================================
# VALIDATOR 24: BusinessRuleValidator
# =============================================================================


class BusinessRuleValidator(DataValidator):
    """Validates data against custom business rules."""

    def __init__(self, rules: list[dict[str, Any]]):
        """
        rules: [
            {
                "name": "check_total",
                "condition": lambda d: d["price"] * d["quantity"] == d["total"],
                "message": "Total must equal price * quantity",
                "severity": "error"
            }
        ]
        """
        super().__init__("BusinessRuleValidator", {"rules": rules})
        self.rules = rules

    def validate(
        self, data: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ValidationResult:
        issues = []

        for rule in self.rules:
            condition = rule.get("condition")
            if condition is None:
                continue

            try:
                if callable(condition):
                    result = condition(data)
                else:
                    # Handle string expressions
                    result = eval(condition, {"__builtins__": {}}, data)

                if not result:
                    severity_str = rule.get("severity", "error")
                    severity = ValidationSeverity(severity_str)

                    issues.append(
                        self._create_issue(
                            rule.get(
                                "message",
                                f"Business rule '{rule.get('name', 'unknown')}' failed",
                            ),
                            severity,
                            suggestion=rule.get("suggestion", ""),
                        )
                    )
            except Exception as e:
                issues.append(
                    self._create_issue(
                        f"Error evaluating rule '{rule.get('name', 'unknown')}': {str(e)}",
                        ValidationSeverity.ERROR,
                    )
                )

        status = (
            ValidationStatus.FAILED
            if any(
                i.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]
                for i in issues
            )
            else ValidationStatus.PASSED
        )

        return self._create_result(status, issues)


# =============================================================================
# Validation Orchestrator
# =============================================================================


class ValidationOrchestrator:
    """Orchestrates multiple validators for comprehensive data validation."""

    def __init__(self, stop_on_error: bool = False, stop_on_critical: bool = True):
        self.validators: list[DataValidator] = []
        self.stop_on_error = stop_on_error
        self.stop_on_critical = stop_on_critical
        self._validation_history: list[ValidationResult] = []

    def register(self, validator: DataValidator) -> None:
        """Register a validator."""
        self.validators.append(validator)

    def unregister(self, validator_name: str) -> None:
        """Unregister a validator by name."""
        self.validators = [v for v in self.validators if v.name != validator_name]

    def validate(
        self, data: Any, context: dict[str, Any] | None = None
    ) -> DataQualityReport:
        """Run all validators and return comprehensive report."""
        results = []
        valid_records = 0
        invalid_records = 0

        for validator in self.validators:
            try:
                result = validator.validate(data, context)
                results.append(result)
                self._validation_history.append(result)

                # Check if we should stop
                if self.stop_on_critical:
                    if any(
                        i.severity == ValidationSeverity.CRITICAL for i in result.issues
                    ):
                        break

                if self.stop_on_error and result.has_errors:
                    break

            except Exception as e:
                error_result = ValidationResult(
                    validator_name=validator.name,
                    status=ValidationStatus.FAILED,
                    issues=[
                        ValidationIssue(
                            validator_name=validator.name,
                            message=f"Validation error: {str(e)}",
                            severity=ValidationSeverity.ERROR,
                        )
                    ],
                )
                results.append(error_result)

        # Determine record validity
        has_critical_error = any(
            any(i.severity == ValidationSeverity.CRITICAL for i in r.issues)
            for r in results
        )
        has_error = any(r.has_errors for r in results)

        if has_critical_error or has_error:
            invalid_records = 1
        else:
            valid_records = 1

        return DataQualityReport(
            total_records=1,
            valid_records=valid_records,
            invalid_records=invalid_records,
            validation_results=results,
        )

    def validate_batch(
        self, records: list[Any], context: dict[str, Any] | None = None
    ) -> DataQualityReport:
        """Validate a batch of records."""
        all_results = []
        valid_count = 0
        invalid_count = 0

        for record in records:
            report = self.validate(record, context)
            all_results.extend(report.validation_results)
            valid_count += report.valid_records
            invalid_count += report.invalid_records

        return DataQualityReport(
            total_records=len(records),
            valid_records=valid_count,
            invalid_records=invalid_count,
            validation_results=all_results,
        )

    def get_validator_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all validators."""
        return {
            validator.name: {
                "execution_count": validator._execution_count,
                "last_execution": validator._last_execution_time,
            }
            for validator in self.validators
        }

    def clear_history(self) -> None:
        """Clear validation history."""
        self._validation_history.clear()


# Convenience factory function
def create_validation_orchestrator() -> ValidationOrchestrator:
    """Create a new validation orchestrator."""
    return ValidationOrchestrator()
