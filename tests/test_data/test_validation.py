"""
Tests for data validation module.

ML-DATA-001-A: Data Validation Module
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.data.validation import (
    ValidationSeverity,
    ValidationStatus,
    ValidationIssue,
    ValidationResult,
    DataQualityReport,
    DataValidator,
    NullValidator,
    TypeValidator,
    RangeValidator,
    PatternValidator,
    LengthValidator,
    UniquenessValidator,
    DateTimeValidator,
    EnumValidator,
    SchemaValidator,
    CrossFieldValidator,
    StatisticalValidator,
    JSONValidator,
    EmailValidator,
    URLValidator,
    CoordinateValidator,
    CreditCardValidator,
    FilePathValidator,
    PhoneValidator,
    CurrencyValidator,
    UUIDValidator,
    IPAddressValidator,
    PercentageValidator,
    BusinessRuleValidator,
    ValidationOrchestrator,
    create_validation_orchestrator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    return {
        "name": "John Doe",
        "age": 30,
        "email": "john@example.com",
        "price": 100.50,
        "quantity": 5,
        "timestamp": "2024-01-15T10:30:00",
        "status": "active",
        "tags": ["tag1", "tag2"],
        "metadata": {"source": "api"},
    }


@pytest.fixture
def orchestrator():
    """Create a fresh validation orchestrator."""
    return create_validation_orchestrator()


# =============================================================================
# Test Data Classes
# =============================================================================


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_issue_creation(self):
        issue = ValidationIssue(
            validator_name="TestValidator",
            message="Test message",
            severity=ValidationSeverity.ERROR,
            field="test_field",
            value="invalid_value",
            expected="valid_value",
            suggestion="Fix it",
        )
        assert issue.validator_name == "TestValidator"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.field == "test_field"


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_result_creation(self):
        result = ValidationResult(
            validator_name="TestValidator",
            status=ValidationStatus.PASSED,
            issues=[],
            metadata={"count": 10},
        )
        assert result.validator_name == "TestValidator"
        assert result.passed is True
        assert result.has_errors is False

    def test_result_with_errors(self):
        result = ValidationResult(
            validator_name="TestValidator",
            status=ValidationStatus.FAILED,
            issues=[
                ValidationIssue("Test", "Error", ValidationSeverity.ERROR),
            ],
        )
        assert result.passed is False
        assert result.has_errors is True
        assert result.has_warnings is False

    def test_result_with_warnings(self):
        result = ValidationResult(
            validator_name="TestValidator",
            status=ValidationStatus.PASSED,
            issues=[
                ValidationIssue("Test", "Warning", ValidationSeverity.WARNING),
            ],
        )
        assert result.has_errors is False
        assert result.has_warnings is True


class TestDataQualityReport:
    """Test DataQualityReport dataclass."""

    def test_report_creation(self):
        report = DataQualityReport(
            total_records=100,
            valid_records=95,
            invalid_records=5,
        )
        assert report.total_records == 100
        assert report.valid_records == 95
        assert report.invalid_records == 5

    def test_error_count(self):
        report = DataQualityReport(
            total_records=100,
            valid_records=90,
            invalid_records=10,
            validation_results=[
                ValidationResult(
                    "V1",
                    ValidationStatus.FAILED,
                    [
                        ValidationIssue("V1", "Error1", ValidationSeverity.ERROR),
                        ValidationIssue("V1", "Warning1", ValidationSeverity.WARNING),
                    ],
                ),
                ValidationResult(
                    "V2",
                    ValidationStatus.FAILED,
                    [ValidationIssue("V2", "Error2", ValidationSeverity.ERROR)],
                ),
            ],
        )
        assert report.error_count == 2
        assert report.warning_count == 1


# =============================================================================
# Test Validator 1: NullValidator
# =============================================================================


class TestNullValidator:
    """Test NullValidator."""

    def test_no_nulls(self):
        validator = NullValidator(fields=["name", "age"])
        data = {"name": "John", "age": 30}
        result = validator.validate(data)
        assert result.passed is True

    def test_null_value(self):
        validator = NullValidator(fields=["name", "age"])
        data = {"name": "John", "age": None}
        result = validator.validate(data)
        assert result.passed is False
        assert result.issues[0].field == "age"

    def test_missing_field(self):
        validator = NullValidator(fields=["name", "age"])
        data = {"name": "John"}
        result = validator.validate(data)
        assert result.passed is False
        assert "missing" in result.issues[0].message.lower()

    def test_empty_string_not_allowed(self):
        validator = NullValidator(fields=["name"], allow_empty=False)
        data = {"name": ""}
        result = validator.validate(data)
        assert result.passed is False
        assert result.issues[0].severity == ValidationSeverity.WARNING


# =============================================================================
# Test Validator 2: TypeValidator
# =============================================================================


class TestTypeValidator:
    """Test TypeValidator."""

    def test_correct_types(self):
        validator = TypeValidator(type_map={"age": int, "name": str, "price": float})
        data = {"age": 30, "name": "John", "price": 100.50}
        result = validator.validate(data)
        assert result.passed is True

    def test_wrong_type(self):
        validator = TypeValidator(type_map={"age": int})
        data = {"age": "thirty"}
        result = validator.validate(data)
        assert result.passed is False
        assert result.issues[0].field == "age"
        assert "wrong type" in result.issues[0].message.lower()


# =============================================================================
# Test Validator 3: RangeValidator
# =============================================================================


class TestRangeValidator:
    """Test RangeValidator."""

    def test_value_in_range(self):
        validator = RangeValidator(ranges={"age": {"min": 0, "max": 120}})
        data = {"age": 30}
        result = validator.validate(data)
        assert result.passed is True

    def test_value_below_min(self):
        validator = RangeValidator(ranges={"age": {"min": 0, "max": 120}})
        data = {"age": -5}
        result = validator.validate(data)
        assert result.passed is False
        assert "below minimum" in result.issues[0].message.lower()

    def test_value_above_max(self):
        validator = RangeValidator(ranges={"age": {"min": 0, "max": 120}})
        data = {"age": 150}
        result = validator.validate(data)
        assert result.passed is False
        assert "exceeds maximum" in result.issues[0].message.lower()


# =============================================================================
# Test Validator 4: PatternValidator
# =============================================================================


class TestPatternValidator:
    """Test PatternValidator."""

    def test_matching_pattern(self):
        validator = PatternValidator(patterns={"code": r"^[A-Z]{3}\d{3}$"})
        data = {"code": "ABC123"}
        result = validator.validate(data)
        assert result.passed is True

    def test_non_matching_pattern(self):
        validator = PatternValidator(patterns={"code": r"^[A-Z]{3}\d{3}$"})
        data = {"code": "ABC12"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 5: LengthValidator
# =============================================================================


class TestLengthValidator:
    """Test LengthValidator."""

    def test_string_length_valid(self):
        validator = LengthValidator(length_specs={"name": {"min": 2, "max": 50}})
        data = {"name": "John"}
        result = validator.validate(data)
        assert result.passed is True

    def test_string_too_short(self):
        validator = LengthValidator(length_specs={"name": {"min": 5}})
        data = {"name": "John"}
        result = validator.validate(data)
        assert result.passed is False

    def test_list_length(self):
        validator = LengthValidator(length_specs={"tags": {"max": 3}})
        data = {"tags": ["a", "b", "c", "d"]}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 6: UniquenessValidator
# =============================================================================


class TestUniquenessValidator:
    """Test UniquenessValidator."""

    def test_unique_records(self):
        validator = UniquenessValidator(fields=["id"])
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = validator.validate(data)
        assert result.passed is True

    def test_duplicate_records(self):
        validator = UniquenessValidator(fields=["id"])
        data = [{"id": 1}, {"id": 2}, {"id": 1}]
        result = validator.validate(data)
        assert result.passed is False
        assert "duplicate" in result.issues[0].message.lower()


# =============================================================================
# Test Validator 7: DateTimeValidator
# =============================================================================


class TestDateTimeValidator:
    """Test DateTimeValidator."""

    def test_valid_datetime(self):
        validator = DateTimeValidator(fields=["timestamp"])
        data = {"timestamp": "2024-01-15T10:30:00"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_datetime_format(self):
        validator = DateTimeValidator(fields=["timestamp"])
        data = {"timestamp": "not-a-date"}
        result = validator.validate(data)
        assert result.passed is False

    def test_future_date_not_allowed(self):
        validator = DateTimeValidator(fields=["date"], allow_future=False)
        future_date = (datetime.now() + timedelta(days=1)).isoformat()
        data = {"date": future_date}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 8: EnumValidator
# =============================================================================


class TestEnumValidator:
    """Test EnumValidator."""

    def test_valid_enum_value(self):
        validator = EnumValidator(
            allowed_values={"status": ["active", "inactive", "pending"]}
        )
        data = {"status": "active"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_enum_value(self):
        validator = EnumValidator(allowed_values={"status": ["active", "inactive"]})
        data = {"status": "deleted"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 9: SchemaValidator
# =============================================================================


class TestSchemaValidator:
    """Test SchemaValidator."""

    def test_valid_schema(self):
        validator = SchemaValidator(
            required_fields=["name", "age"],
            optional_fields=["email"],
        )
        data = {"name": "John", "age": 30, "email": "john@example.com"}
        result = validator.validate(data)
        assert result.passed is True

    def test_missing_required_field(self):
        validator = SchemaValidator(required_fields=["name", "age"])
        data = {"name": "John"}
        result = validator.validate(data)
        assert result.passed is False

    def test_extra_field_warning(self):
        validator = SchemaValidator(
            required_fields=["name"],
            allow_extra=False,
        )
        data = {"name": "John", "extra_field": "value"}
        result = validator.validate(data)
        assert result.has_warnings is True  # Has warning for extra field
        assert result.issues[0].severity == ValidationSeverity.WARNING


# =============================================================================
# Test Validator 10: CrossFieldValidator
# =============================================================================


class TestCrossFieldValidator:
    """Test CrossFieldValidator."""

    def test_valid_cross_field(self):
        validator = CrossFieldValidator(
            validations=[
                {"field1": "start_date", "field2": "end_date", "operator": "<"}
            ]
        )
        data = {"start_date": 1, "end_date": 10}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_cross_field(self):
        validator = CrossFieldValidator(
            validations=[
                {"field1": "start_date", "field2": "end_date", "operator": "<"}
            ]
        )
        data = {"start_date": 10, "end_date": 1}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 11: StatisticalValidator
# =============================================================================


class TestStatisticalValidator:
    """Test StatisticalValidator."""

    def test_mean_in_range(self):
        validator = StatisticalValidator(field="value", checks={"mean_range": [0, 100]})
        data = [{"value": 50}, {"value": 60}, {"value": 40}]
        result = validator.validate(data)
        assert result.passed is True

    def test_outliers_detected(self):
        validator = StatisticalValidator(
            field="value", checks={"no_outliers": {"method": "iqr", "threshold": 1.5}}
        )
        data = [
            {"value": 50},
            {"value": 51},
            {"value": 49},
            {"value": 50},
            {"value": 200},  # Outlier
        ]
        result = validator.validate(data)
        assert result.has_warnings is True


# =============================================================================
# Test Validator 12: JSONValidator
# =============================================================================


class TestJSONValidator:
    """Test JSONValidator."""

    def test_valid_json_object(self):
        validator = JSONValidator(fields=["metadata"])
        data = {"metadata": {"key": "value"}}
        result = validator.validate(data)
        assert result.passed is True

    def test_valid_json_string(self):
        validator = JSONValidator(fields=["config"])
        data = {"config": '{"setting": true}'}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_json(self):
        validator = JSONValidator(fields=["config"])
        data = {"config": "not valid json{"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 13: EmailValidator
# =============================================================================


class TestEmailValidator:
    """Test EmailValidator."""

    def test_valid_email(self):
        validator = EmailValidator(fields=["email"])
        data = {"email": "user@example.com"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_email(self):
        validator = EmailValidator(fields=["email"])
        data = {"email": "not-an-email"}
        result = validator.validate(data)
        assert result.passed is False

    def test_multiple_emails(self):
        validator = EmailValidator(fields=["emails"], allow_multiple=True)
        data = {"emails": "user1@example.com,user2@example.com"}
        result = validator.validate(data)
        assert result.passed is True


# =============================================================================
# Test Validator 14: URLValidator
# =============================================================================


class TestURLValidator:
    """Test URLValidator."""

    def test_valid_http_url(self):
        validator = URLValidator(fields=["website"])
        data = {"website": "https://example.com"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_url(self):
        validator = URLValidator(fields=["website"])
        data = {"website": "not-a-url"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 15: CoordinateValidator
# =============================================================================


class TestCoordinateValidator:
    """Test CoordinateValidator."""

    def test_valid_coordinates(self):
        validator = CoordinateValidator(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 40.7128, "longitude": -74.0060}
        result = validator.validate(data)
        assert result.passed is True

    def test_latitude_out_of_range(self):
        validator = CoordinateValidator(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 95.0, "longitude": -74.0}
        result = validator.validate(data)
        assert result.passed is False

    def test_longitude_out_of_range(self):
        validator = CoordinateValidator(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 40.0, "longitude": -200.0}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 16: CreditCardValidator
# =============================================================================


class TestCreditCardValidator:
    """Test CreditCardValidator."""

    def test_valid_credit_card(self):
        # Using a valid Luhn number
        validator = CreditCardValidator(field="card_number")
        data = {"card_number": "4532015112830366"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_credit_card(self):
        validator = CreditCardValidator(field="card_number")
        data = {"card_number": "1234567890123456"}
        result = validator.validate(data)
        assert result.passed is False

    def test_non_numeric_characters_stripped(self):
        validator = CreditCardValidator(field="card_number")
        # Valid Luhn number with dashes - dashes should be stripped
        data = {"card_number": "4532-0151-1283-0366"}
        result = validator.validate(data)
        # After stripping dashes, this should pass Luhn check
        assert result.passed is True


# =============================================================================
# Test Validator 17: FilePathValidator
# =============================================================================


class TestFilePathValidator:
    """Test FilePathValidator."""

    def test_valid_path(self):
        validator = FilePathValidator(fields=["path"], must_exist=False)
        data = {"path": "/tmp/test.txt"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_extension(self):
        validator = FilePathValidator(
            fields=["path"], allowed_extensions=[".txt", ".csv"]
        )
        data = {"path": "/tmp/test.pdf"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 18: PhoneValidator
# =============================================================================


class TestPhoneValidator:
    """Test PhoneValidator."""

    def test_valid_phone(self):
        validator = PhoneValidator(fields=["phone"])
        data = {"phone": "+1-555-123-4567"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_characters(self):
        validator = PhoneValidator(fields=["phone"])
        data = {"phone": "555-abc-1234"}
        result = validator.validate(data)
        assert result.passed is False

    def test_too_short(self):
        validator = PhoneValidator(fields=["phone"])
        data = {"phone": "123"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 19: CurrencyValidator
# =============================================================================


class TestCurrencyValidator:
    """Test CurrencyValidator."""

    def test_valid_amount(self):
        validator = CurrencyValidator(field="amount", min_amount=0, max_amount=10000)
        data = {"amount": 100.50}
        result = validator.validate(data)
        assert result.passed is True

    def test_amount_below_min(self):
        validator = CurrencyValidator(field="amount", min_amount=0)
        data = {"amount": -10}
        result = validator.validate(data)
        assert result.passed is False

    def test_invalid_currency(self):
        validator = CurrencyValidator(
            field="amount", currency_field="currency", allowed_currencies=["USD", "EUR"]
        )
        data = {"amount": 100, "currency": "XYZ"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 20: UUIDValidator
# =============================================================================


class TestUUIDValidator:
    """Test UUIDValidator."""

    def test_valid_uuid(self):
        validator = UUIDValidator(fields=["id"])
        data = {"id": "550e8400-e29b-41d4-a716-446655440000"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_uuid(self):
        validator = UUIDValidator(fields=["id"])
        data = {"id": "not-a-uuid"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 21: IPAddressValidator
# =============================================================================


class TestIPAddressValidator:
    """Test IPAddressValidator."""

    def test_valid_ipv4(self):
        validator = IPAddressValidator(fields=["ip"])
        data = {"ip": "192.168.1.1"}
        result = validator.validate(data)
        assert result.passed is True

    def test_valid_ipv6(self):
        validator = IPAddressValidator(fields=["ip"], allow_v6=True)
        data = {"ip": "2001:0db8:85a3:0000:0000:8a2e:0370:7334"}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_ip(self):
        validator = IPAddressValidator(fields=["ip"])
        data = {"ip": "999.999.999.999"}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test Validator 22: PercentageValidator
# =============================================================================


class TestPercentageValidator:
    """Test PercentageValidator."""

    def test_valid_percentage(self):
        validator = PercentageValidator(fields=["rate"])
        data = {"rate": 50}
        result = validator.validate(data)
        assert result.passed is True

    def test_percentage_out_of_range(self):
        validator = PercentageValidator(fields=["rate"])
        data = {"rate": 150}
        result = validator.validate(data)
        assert result.passed is False

    def test_percentage_string(self):
        validator = PercentageValidator(fields=["rate"])
        data = {"rate": "75%"}
        result = validator.validate(data)
        assert result.passed is True


# =============================================================================
# Test Validator 23: BusinessRuleValidator
# =============================================================================


class TestBusinessRuleValidator:
    """Test BusinessRuleValidator."""

    def test_valid_business_rule(self):
        validator = BusinessRuleValidator(
            rules=[
                {
                    "name": "check_total",
                    "condition": lambda d: d["price"] * d["quantity"] == d["total"],
                    "message": "Total must equal price * quantity",
                    "severity": "error",
                }
            ]
        )
        data = {"price": 10, "quantity": 5, "total": 50}
        result = validator.validate(data)
        assert result.passed is True

    def test_invalid_business_rule(self):
        validator = BusinessRuleValidator(
            rules=[
                {
                    "name": "check_total",
                    "condition": lambda d: d["price"] * d["quantity"] == d["total"],
                    "message": "Total must equal price * quantity",
                    "severity": "error",
                }
            ]
        )
        data = {"price": 10, "quantity": 5, "total": 100}
        result = validator.validate(data)
        assert result.passed is False


# =============================================================================
# Test ValidationOrchestrator
# =============================================================================


class TestValidationOrchestrator:
    """Test ValidationOrchestrator."""

    def test_orchestrator_creation(self):
        orchestrator = create_validation_orchestrator()
        assert isinstance(orchestrator, ValidationOrchestrator)

    def test_register_validator(self, orchestrator):
        validator = NullValidator(fields=["name"])
        orchestrator.register(validator)
        assert len(orchestrator.validators) == 1

    def test_unregister_validator(self, orchestrator):
        validator = NullValidator(fields=["name"])
        orchestrator.register(validator)
        orchestrator.unregister("NullValidator")
        assert len(orchestrator.validators) == 0

    def test_validate_single_record(self, orchestrator):
        orchestrator.register(NullValidator(fields=["name"]))
        orchestrator.register(TypeValidator(type_map={"age": int}))

        data = {"name": "John", "age": 30}
        report = orchestrator.validate(data)

        assert report.total_records == 1
        assert report.valid_records == 1
        assert report.invalid_records == 0

    def test_validate_invalid_record(self, orchestrator):
        orchestrator.register(NullValidator(fields=["name"]))

        data = {"name": None}
        report = orchestrator.validate(data)

        assert report.valid_records == 0
        assert report.invalid_records == 1

    def test_validate_batch(self, orchestrator):
        orchestrator.register(NullValidator(fields=["name"]))

        records = [
            {"name": "John"},
            {"name": "Jane"},
            {"name": None},  # Invalid
        ]
        report = orchestrator.validate_batch(records)

        assert report.total_records == 3
        assert report.valid_records == 2
        assert report.invalid_records == 1

    def test_get_validator_stats(self, orchestrator):
        validator = NullValidator(fields=["name"])
        orchestrator.register(validator)

        orchestrator.validate({"name": "John"})

        stats = orchestrator.get_validator_stats()
        assert "NullValidator" in stats
        assert stats["NullValidator"]["execution_count"] == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the validation framework."""

    def test_comprehensive_validation(self):
        """Test comprehensive validation with multiple validators."""
        orchestrator = create_validation_orchestrator()

        # Add multiple validators
        orchestrator.register(NullValidator(fields=["id", "name", "email"]))
        orchestrator.register(
            TypeValidator(
                type_map={
                    "id": int,
                    "name": str,
                    "age": int,
                    "email": str,
                }
            )
        )
        orchestrator.register(RangeValidator(ranges={"age": {"min": 0, "max": 150}}))
        orchestrator.register(EmailValidator(fields=["email"]))
        orchestrator.register(
            LengthValidator(length_specs={"name": {"min": 1, "max": 100}})
        )

        # Valid data
        valid_data = {
            "id": 1,
            "name": "John Doe",
            "age": 30,
            "email": "john@example.com",
        }

        report = orchestrator.validate(valid_data)
        assert report.valid_records == 1
        assert report.error_count == 0

    def test_all_validator_types(self):
        """Verify all expected validator types are available."""
        expected_validators = [
            NullValidator,
            TypeValidator,
            RangeValidator,
            PatternValidator,
            LengthValidator,
            UniquenessValidator,
            DateTimeValidator,
            EnumValidator,
            SchemaValidator,
            CrossFieldValidator,
            StatisticalValidator,
            JSONValidator,
            EmailValidator,
            URLValidator,
            CoordinateValidator,
            CreditCardValidator,
            FilePathValidator,
            PhoneValidator,
            CurrencyValidator,
            UUIDValidator,
            IPAddressValidator,
            PercentageValidator,
            BusinessRuleValidator,
        ]

        for validator_class in expected_validators:
            # Just verify they can be instantiated
            if validator_class == NullValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == TypeValidator:
                validator = validator_class(type_map={"test": str})
            elif validator_class == RangeValidator:
                validator = validator_class(ranges={"test": {"min": 0}})
            elif validator_class == PatternValidator:
                validator = validator_class(patterns={"test": r".*"})
            elif validator_class == LengthValidator:
                validator = validator_class(length_specs={"test": {"max": 10}})
            elif validator_class == UniquenessValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == DateTimeValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == EnumValidator:
                validator = validator_class(allowed_values={"test": ["a", "b"]})
            elif validator_class == SchemaValidator:
                validator = validator_class(required_fields=["test"])
            elif validator_class == CrossFieldValidator:
                validator = validator_class(validations=[])
            elif validator_class == StatisticalValidator:
                validator = validator_class(field="test", checks={})
            elif validator_class == JSONValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == EmailValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == URLValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == CoordinateValidator:
                validator = validator_class(lat_field="lat", lon_field="lon")
            elif validator_class == CreditCardValidator:
                validator = validator_class(field="test")
            elif validator_class == FilePathValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == PhoneValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == CurrencyValidator:
                validator = validator_class(field="test")
            elif validator_class == UUIDValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == IPAddressValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == PercentageValidator:
                validator = validator_class(fields=["test"])
            elif validator_class == BusinessRuleValidator:
                validator = validator_class(rules=[])
            else:
                validator = validator_class()

            assert validator.name is not None
