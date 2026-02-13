"""Tests for DSL validator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from src.backtesting.dsl.validator import (
    DSLValidator,
    ValidationResult,
    ValidationError,
    ValidationWarning,
)
from tests.test_backtesting.test_dsl.fixtures import (  # noqa: E402
    create_valid_config,
    create_invalid_leverage_config,
    create_invalid_position_percent_config,
    create_invalid_confluence_score_config,
    create_invalid_timeframe_config,
    create_no_stop_loss_config,
    create_missing_required_fields_config,
)


class TestDSLValidator:
    """Tests for DSLValidator."""

    def test_validate_valid_config(self):
        """Test validating a valid config."""
        validator = DSLValidator()
        config = create_valid_config()

        result = validator.validate(config)

        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        validator = DSLValidator()
        config = create_missing_required_fields_config()

        result = validator.validate(config)

        assert result.is_valid is False
        assert len(result.errors) > 0

        # Check for specific errors
        error_paths = [e.field_path for e in result.errors]
        assert "metadata.name" in error_paths
        assert "metadata.version" in error_paths
        assert "universe.symbols" in error_paths

    def test_field_level_error_details(self):
        """Test that field-level errors have complete details."""
        validator = DSLValidator()
        config = create_missing_required_fields_config()

        result = validator.validate(config)

        # Find the name error
        name_errors = [e for e in result.errors if e.field_path == "metadata.name"]
        assert len(name_errors) == 1

        error = name_errors[0]
        assert error.field_path == "metadata.name"
        assert "required" in error.message.lower()
        assert error.constraint == "required field"

    def test_validate_invalid_timeframe(self):
        """Test validation fails for invalid timeframe."""
        validator = DSLValidator()
        config = create_invalid_timeframe_config()

        result = validator.validate(config)

        assert result.is_valid is False

        # Check for timeframe error
        timeframe_errors = [e for e in result.errors if "timeframe" in e.field_path]
        assert len(timeframe_errors) > 0

    def test_validate_warnings_for_best_practices(self):
        """Test that validator produces warnings for best practices."""
        validator = DSLValidator()
        config = create_no_stop_loss_config()

        result = validator.validate(config)

        # Should have warning about stop-loss
        stop_loss_warnings = [w for w in result.warnings if "stop_loss" in w.field_path]
        assert len(stop_loss_warnings) > 0

    def test_get_errors_for_field(self):
        """Test getting errors for specific field."""
        validator = DSLValidator()
        config = create_missing_required_fields_config()

        result = validator.validate(config)

        name_errors = result.get_errors_for_field("metadata.name")
        assert len(name_errors) == 1
        assert name_errors[0].field_path == "metadata.name"

    def test_has_error_in_path(self):
        """Test checking for errors in path prefix."""
        validator = DSLValidator()
        config = create_missing_required_fields_config()

        result = validator.validate(config)

        assert result.has_error_in_path("metadata") is True
        assert result.has_error_in_path("metadata.name") is True
        assert result.has_error_in_path("signals") is False

    def test_validation_result_to_dict(self):
        """Test converting result to dictionary."""
        validator = DSLValidator()
        config = create_valid_config()

        result = validator.validate(config)
        data = result.to_dict()

        assert "is_valid" in data
        assert "errors" in data
        assert "warnings" in data
        assert "dsl_version" in data
        assert "error_count" in data
        assert "warning_count" in data


class TestValidationError:
    """Tests for ValidationError."""

    def test_error_creation(self):
        """Test creating validation error."""
        error = ValidationError(
            field_path="risk_rules.position_limits.max_leverage",
            message="Leverage exceeds limit",
            value=5.0,
            constraint="must be <= 3.0",
        )

        assert error.field_path == "risk_rules.position_limits.max_leverage"
        assert error.value == 5.0
        assert error.constraint == "must be <= 3.0"

    def test_error_to_dict(self):
        """Test converting error to dict."""
        error = ValidationError(
            field_path="test.path",
            message="Test error",
            value=123,
            constraint="test constraint",
        )

        data = error.to_dict()

        assert data["field_path"] == "test.path"
        assert data["message"] == "Test error"
        assert data["value"] == 123
        assert data["constraint"] == "test constraint"


class TestValidationWarning:
    """Tests for ValidationWarning."""

    def test_warning_creation(self):
        """Test creating validation warning."""
        warning = ValidationWarning(
            field_path="exits.stop_loss.enabled",
            message="Stop-loss is disabled",
            value=False,
            suggestion="Enable stop-loss for risk protection",
        )

        assert warning.field_path == "exits.stop_loss.enabled"
        assert warning.value is False
        assert "risk protection" in warning.suggestion

    def test_warning_to_dict(self):
        """Test converting warning to dict."""
        warning = ValidationWarning(
            field_path="test.path",
            message="Test warning",
            value="test",
            suggestion="Fix this",
        )

        data = warning.to_dict()

        assert data["field_path"] == "test.path"
        assert data["message"] == "Test warning"
        assert data["suggestion"] == "Fix this"


class TestCrossSectionValidation:
    """Tests for cross-section validation."""

    def test_sizing_exceeds_risk_limit_warning(self):
        """Test warning when sizing exceeds risk limits."""
        validator = DSLValidator()
        config = create_valid_config()

        # Set sizing max_position_percent higher than risk limit
        config["sizing"]["risk_percent"]["max_position_percent"] = 20.0
        config["risk_rules"]["position_limits"]["max_position_percent"] = 10.0

        result = validator.validate(config)

        # Should have warning about sizing exceeding risk limit
        sizing_warnings = [w for w in result.warnings if "sizing" in w.field_path]
        assert len(sizing_warnings) > 0


class TestEnumValidation:
    """Tests for enum value validation."""

    def test_invalid_category(self):
        """Test validation fails for invalid category."""
        validator = DSLValidator()
        config = create_valid_config()
        config["metadata"]["category"] = "invalid_category"

        result = validator.validate(config)

        assert result.is_valid is False
        category_errors = [e for e in result.errors if "category" in e.field_path]
        assert len(category_errors) > 0

    def test_invalid_status(self):
        """Test validation fails for invalid status."""
        validator = DSLValidator()
        config = create_valid_config()
        config["metadata"]["status"] = "invalid_status"

        result = validator.validate(config)

        assert result.is_valid is False
        status_errors = [e for e in result.errors if "status" in e.field_path]
        assert len(status_errors) > 0

    def test_invalid_indicator_type(self):
        """Test validation fails for invalid indicator type."""
        validator = DSLValidator()
        config = create_valid_config()
        config["signals"]["indicators"][0]["type"] = "invalid_indicator"

        result = validator.validate(config)

        assert result.is_valid is False
        indicator_errors = [e for e in result.errors if "indicator" in e.field_path]
        assert len(indicator_errors) > 0
