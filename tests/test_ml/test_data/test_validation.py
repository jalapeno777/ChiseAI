"""Tests for validation module."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ml.data.validation import (
    ArraySizeValidationRule,
    CategoricalDistributionRule,
    CompositeRule,
    CrossFieldValidationRule,
    DataFreshnessRule,
    DataTypeValidationRule,
    DataValidator,
    DuplicateDetectionRule,
    EncodingValidationRule,
    EnumValueValidationRule,
    FileFormatValidationRule,
    ForeignKeyReferenceRule,
    MonotonicFieldRule,
    NonNegativeRule,
    NotEmptyStringRule,
    NullCheckRule,
    NumericPrecisionRule,
    RangeValidationRule,
    RowCountRule,
    SchemaCompletenessRule,
    StringLengthValidationRule,
    StringPatternRule,
    TimestampFormatRule,
    UniqueConstraintRule,
    ValidationResult,
    ValidationRule,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_creation(self) -> None:
        """Test creating a ValidationResult."""
        result = ValidationResult(
            rule_name="test_rule",
            passed=True,
            message="Validation passed",
            severity="info",
            details={"key": "value"},
        )

        assert result.rule_name == "test_rule"
        assert result.passed is True
        assert result.severity == "info"
        assert result.details["key"] == "value"

    def test_validation_result_to_dict(self) -> None:
        """Test serialization to dictionary."""
        result = ValidationResult(
            rule_name="test_rule",
            passed=False,
            message="Validation failed",
            severity="error",
        )

        result_dict = result.to_dict()
        assert result_dict["rule_name"] == "test_rule"
        assert result_dict["passed"] is False
        assert result_dict["severity"] == "error"


class TestSchemaCompletenessRule:
    """Tests for SchemaCompletenessRule."""

    def test_schema_completeness_pass(self) -> None:
        """Test schema completeness with all fields present."""
        rule = SchemaCompletenessRule(required_fields=["name", "age"])
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

        results = rule.validate(data)
        assert len(results) == 1
        assert results[0].passed is True

    def test_schema_completeness_fail(self) -> None:
        """Test schema completeness with missing fields."""
        rule = SchemaCompletenessRule(required_fields=["name", "age"])
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob"},  # Missing age
        ]

        results = rule.validate(data)
        assert len(results) == 1
        assert results[0].passed is False
        assert "Missing fields" in results[0].message


class TestDataTypeValidationRule:
    """Tests for DataTypeValidationRule."""

    def test_data_type_pass(self) -> None:
        """Test data type validation with correct types."""
        rule = DataTypeValidationRule(field_types={"age": int, "name": str})
        data = [{"age": 30, "name": "Alice"}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_data_type_fail(self) -> None:
        """Test data type validation with incorrect types."""
        rule = DataTypeValidationRule(field_types={"age": int})
        data = [{"age": "30"}]  # String instead of int

        results = rule.validate(data)
        assert results[0].passed is False


class TestNullCheckRule:
    """Tests for NullCheckRule."""

    def test_null_check_pass(self) -> None:
        """Test null check with no null values."""
        rule = NullCheckRule(fields=["name", "age"])
        data = [{"name": "Alice", "age": 30}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_null_check_fail(self) -> None:
        """Test null check with null values."""
        rule = NullCheckRule(fields=["name", "age"])
        data = [{"name": "Alice", "age": None}]

        results = rule.validate(data)
        assert results[0].passed is False


class TestRangeValidationRule:
    """Tests for RangeValidationRule."""

    def test_range_validation_pass(self) -> None:
        """Test range validation with values in range."""
        rule = RangeValidationRule(field_ranges={"age": {"min": 0, "max": 150}})
        data = [{"age": 30}, {"age": 50}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_range_validation_fail(self) -> None:
        """Test range validation with values out of range."""
        rule = RangeValidationRule(field_ranges={"age": {"min": 0, "max": 150}})
        data = [{"age": 200}]

        results = rule.validate(data)
        assert results[0].passed is False


class TestStringPatternRule:
    """Tests for StringPatternRule."""

    def test_string_pattern_pass(self) -> None:
        """Test string pattern with matching values."""
        rule = StringPatternRule(field_patterns={"email": r"^[\w.-]+@[\w.-]+\.\w+$"})
        data = [{"email": "test@example.com"}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_string_pattern_fail(self) -> None:
        """Test string pattern with non-matching values."""
        rule = StringPatternRule(field_patterns={"email": r"^[\w.-]+@[\w.-]+\.\w+$"})
        data = [{"email": "invalid-email"}]

        results = rule.validate(data)
        assert results[0].passed is False


class TestEnumValueValidationRule:
    """Tests for EnumValueValidationRule."""

    def test_enum_value_pass(self) -> None:
        """Test enum validation with valid values."""
        rule = EnumValueValidationRule(field_enums={"status": ["active", "inactive"]})
        data = [{"status": "active"}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_enum_value_fail(self) -> None:
        """Test enum validation with invalid values."""
        rule = EnumValueValidationRule(field_enums={"status": ["active", "inactive"]})
        data = [{"status": "unknown"}]

        results = rule.validate(data)
        assert results[0].passed is False


class TestUniqueConstraintRule:
    """Tests for UniqueConstraintRule."""

    def test_unique_constraint_pass(self) -> None:
        """Test unique constraint with unique values."""
        rule = UniqueConstraintRule(fields=["email"])
        data = [
            {"email": "alice@example.com"},
            {"email": "bob@example.com"},
        ]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_unique_constraint_fail(self) -> None:
        """Test unique constraint with duplicate values."""
        rule = UniqueConstraintRule(fields=["email"])
        data = [
            {"email": "alice@example.com"},
            {"email": "alice@example.com"},
        ]

        results = rule.validate(data)
        assert results[0].passed is False


class TestForeignKeyReferenceRule:
    """Tests for ForeignKeyReferenceRule."""

    def test_foreign_key_pass(self) -> None:
        """Test foreign key with valid references."""
        rule = ForeignKeyReferenceRule(
            field="department_id", reference_values=[1, 2, 3]
        )
        data = [{"department_id": 1}, {"department_id": 2}]

        results = rule.validate(data)
        assert results[0].passed is True

    def test_foreign_key_fail(self) -> None:
        """Test foreign key with invalid references."""
        rule = ForeignKeyReferenceRule(
            field="department_id", reference_values=[1, 2, 3]
        )
        data = [{"department_id": 99}]

        results = rule.validate(data)
        assert results[0].passed is False


class TestTimestampFormatRule:
    """Tests for TimestampFormatRule."""

    def test_timestamp_format_pass(self) -> None:
        """Test timestamp format with valid values."""
        rule = TimestampFormatRule(field="timestamp", fmt="iso")
        data = [{"timestamp": "2024-01-01T00:00:00"}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestNumericPrecisionRule:
    """Tests for NumericPrecisionRule."""

    def test_numeric_precision_pass(self) -> None:
        """Test numeric precision with valid values."""
        rule = NumericPrecisionRule(field="price", max_decimals=2)
        data = [{"price": 19.99}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestStringLengthValidationRule:
    """Tests for StringLengthValidationRule."""

    def test_string_length_pass(self) -> None:
        """Test string length with valid values."""
        rule = StringLengthValidationRule(field="name", min_length=1, max_length=100)
        data = [{"name": "Alice"}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestArraySizeValidationRule:
    """Tests for ArraySizeValidationRule."""

    def test_array_size_pass(self) -> None:
        """Test array size with valid values."""
        rule = ArraySizeValidationRule(field="tags", min_size=1, max_size=5)
        data = [{"tags": ["tag1", "tag2"]}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestCategoricalDistributionRule:
    """Tests for CategoricalDistributionRule."""

    def test_categorical_distribution_pass(self) -> None:
        """Test categorical distribution with healthy distribution."""
        rule = CategoricalDistributionRule(field="status", max_dominance=0.9)
        data = [{"status": "a"} for _ in range(50)] + [
            {"status": "b"} for _ in range(50)
        ]

        results = rule.validate(data)
        assert results[0].passed is True


class TestDataFreshnessRule:
    """Tests for DataFreshnessRule."""

    def test_data_freshness_pass(self) -> None:
        """Test data freshness with recent data."""
        rule = DataFreshnessRule(field="timestamp", max_age_hours=24)
        now = datetime.now().timestamp()
        data = [{"timestamp": now}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestFileFormatValidationRule:
    """Tests for FileFormatValidationRule."""

    def test_file_format_pass(self) -> None:
        """Test file format with valid extensions."""
        rule = FileFormatValidationRule(
            field="filename", allowed_extensions=[".csv", ".json"]
        )
        data = [{"filename": "data.csv"}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestEncodingValidationRule:
    """Tests for EncodingValidationRule."""

    def test_encoding_pass(self) -> None:
        """Test encoding with valid values."""
        rule = EncodingValidationRule(fields=["name"], encoding="utf-8")
        data = [{"name": "Alice"}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestDuplicateDetectionRule:
    """Tests for DuplicateDetectionRule."""

    def test_duplicate_detection_pass(self) -> None:
        """Test duplicate detection with no duplicates."""
        rule = DuplicateDetectionRule()
        data = [{"id": 1}, {"id": 2}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestCrossFieldValidationRule:
    """Tests for CrossFieldValidationRule."""

    def test_cross_field_pass(self) -> None:
        """Test cross-field validation with valid data."""
        rule = CrossFieldValidationRule(
            name="end_after_start",
            description="End time must be after start time",
            predicate=lambda r: r.get("end", 0) > r.get("start", 0),
        )
        data = [{"start": 10, "end": 20}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestNonNegativeRule:
    """Tests for NonNegativeRule."""

    def test_non_negative_pass(self) -> None:
        """Test non-negative with valid values."""
        rule = NonNegativeRule(fields=["price", "quantity"])
        data = [{"price": 10.0, "quantity": 5}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestNotEmptyStringRule:
    """Tests for NotEmptyStringRule."""

    def test_not_empty_pass(self) -> None:
        """Test not empty with non-empty strings."""
        rule = NotEmptyStringRule(fields=["name"])
        data = [{"name": "Alice"}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestMonotonicFieldRule:
    """Tests for MonotonicFieldRule."""

    def test_monotonic_pass(self) -> None:
        """Test monotonic field with increasing values."""
        rule = MonotonicFieldRule(field="timestamp", direction="increasing")
        data = [{"timestamp": 1}, {"timestamp": 2}, {"timestamp": 3}]

        results = rule.validate(data)
        assert results[0].passed is True


class TestRowCountRule:
    """Tests for RowCountRule."""

    def test_row_count_pass(self) -> None:
        """Test row count with valid count."""
        rule = RowCountRule(min_rows=5, max_rows=100)
        data = [{"id": i} for i in range(10)]

        results = rule.validate(data)
        assert results[0].passed is True


class TestDataValidator:
    """Tests for DataValidator class."""

    def test_validator_creation(self) -> None:
        """Test creating a DataValidator."""
        validator = DataValidator()
        assert len(validator.get_rules()) == 0

    def test_register_rule(self) -> None:
        """Test registering a validation rule."""
        validator = DataValidator()
        rule = SchemaCompletenessRule(required_fields=["id"])
        validator.register_rule(rule)

        assert len(validator.get_rules()) == 1

    def test_unregister_rule(self) -> None:
        """Test unregistering a validation rule."""
        validator = DataValidator()
        rule = SchemaCompletenessRule(required_fields=["id"])
        validator.register_rule(rule)

        result = validator.unregister_rule("schema_completeness")
        assert result is True
        assert len(validator.get_rules()) == 0

    def test_validate(self) -> None:
        """Test running validation."""
        validator = DataValidator()
        validator.register_rule(SchemaCompletenessRule(required_fields=["id"]))

        data = [{"id": 1}, {"id": 2}]
        results = validator.validate(data)

        assert len(results) > 0


class TestCompositeRule:
    """Tests for CompositeRule."""

    def test_composite_rule(self) -> None:
        """Test composite rule aggregates results."""
        rule1 = SchemaCompletenessRule(required_fields=["id"])
        rule2 = NullCheckRule(fields=["id"])

        composite = CompositeRule(
            name="composite",
            description="Combined rules",
            rules=[rule1, rule2],
        )

        data = [{"id": 1}, {"id": None}]
        results = composite.validate(data)

        assert len(results) == 2
