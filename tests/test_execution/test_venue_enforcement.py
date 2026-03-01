"""Unit tests for venue enforcement gate.

Tests for:
- VenueEnforcementError exception
- ValidationResult dataclass
- VenueEnforcementGate class
- require_bybit_demo=True enforcement
- require_bybit_demo=False lenient mode
"""

import pytest

from execution.safety.venue_enforcement import (
    VenueEnforcementError,
    VenueEnforcementGate,
    ValidationResult,
    create_default_gate,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result_creation(self):
        """Test creating a valid result."""
        result = ValidationResult(
            valid=True,
            test_mode_status="VALID_TEST_MODE",
            errors=[],
            warnings=[],
        )
        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_creation(self):
        """Test creating an invalid result."""
        result = ValidationResult(
            valid=False,
            test_mode_status="INVALID_TEST_MODE",
            errors=["Venue not allowed"],
            warnings=["Check configuration"],
        )
        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert len(result.errors) == 1
        assert len(result.warnings) == 1

    def test_invalid_test_mode_status_raises_error(self):
        """Test that invalid test_mode_status raises ValueError."""
        with pytest.raises(ValueError, match="test_mode_status must be one of"):
            ValidationResult(
                valid=True,
                test_mode_status="INVALID_STATUS",
                errors=[],
                warnings=[],
            )

    def test_default_factories(self):
        """Test default factory methods for lists."""
        result = ValidationResult(
            valid=True,
            test_mode_status="VALID_TEST_MODE",
        )
        assert result.errors == []
        assert result.warnings == []


class TestVenueEnforcementError:
    """Tests for VenueEnforcementError exception."""

    def test_error_creation(self):
        """Test creating an enforcement error."""
        error = VenueEnforcementError(
            message="Venue not allowed",
            venue="okx",
            test_mode_status="INVALID_TEST_MODE",
        )
        assert str(error) == "Venue not allowed"
        assert error.venue == "okx"
        assert error.test_mode_status == "INVALID_TEST_MODE"

    def test_error_with_defaults(self):
        """Test error with default values."""
        error = VenueEnforcementError(message="Validation failed")
        assert error.venue is None
        assert error.test_mode_status == "INVALID_TEST_MODE"


class TestVenueEnforcementGate:
    """Tests for VenueEnforcementGate class."""

    def test_gate_initialization(self):
        """Test gate initialization."""
        gate = VenueEnforcementGate(
            require_bybit_demo=True,
            allowed_venues=["bybit_demo", "okx"],
        )
        assert gate.require_bybit_demo is True
        assert gate.allowed_venues == {"bybit_demo", "okx"}

    def test_gate_initialization_defaults(self):
        """Test gate initialization with defaults."""
        gate = VenueEnforcementGate()
        assert gate.require_bybit_demo is False
        assert gate.allowed_venues is None

    # Tests for is_bybit_demo method

    def test_is_bybit_demo_with_venue_only(self):
        """Test is_bybit_demo with venue identifier only."""
        gate = VenueEnforcementGate()

        assert gate.is_bybit_demo("bybit_demo") is True
        assert gate.is_bybit_demo("BYBIT_DEMO") is True
        assert gate.is_bybit_demo("bybit") is False
        assert gate.is_bybit_demo("okx") is False

    def test_is_bybit_demo_with_demo_endpoint(self):
        """Test is_bybit_demo with demo endpoint."""
        gate = VenueEnforcementGate()

        assert gate.is_bybit_demo("bybit", "https://api-demo.bybit.com") is True
        assert gate.is_bybit_demo("bybit", "api-demo.bybit.com") is True
        assert gate.is_bybit_demo("bybit", "wss://stream-demo.bybit.com") is True

    def test_is_bybit_demo_with_prod_endpoint(self):
        """Test is_bybit_demo with production endpoint."""
        gate = VenueEnforcementGate()

        assert gate.is_bybit_demo("bybit", "https://api.bybit.com") is False
        assert gate.is_bybit_demo("bybit", "api.bybit.com") is False

    def test_is_bybit_demo_endpoint_takes_precedence(self):
        """Test that endpoint takes precedence over venue name."""
        gate = VenueEnforcementGate()

        # Even if venue is bybit_demo, prod endpoint makes it not demo
        assert gate.is_bybit_demo("bybit_demo", "https://api.bybit.com") is False

    # Tests for validate_execution_venue with require_bybit_demo=True

    def test_validate_bybit_demo_passes_when_required(self):
        """Test that bybit_demo passes when require_bybit_demo=True."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        result = gate.validate_execution_venue("bybit_demo")

        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"
        assert result.errors == []
        assert result.warnings == []

    def test_validate_bybit_demo_with_endpoint_passes_when_required(self):
        """Test that bybit_demo with demo endpoint passes when required."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        result = gate.validate_execution_venue(
            "bybit_demo",
            "https://api-demo.bybit.com",
        )

        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"

    def test_validate_non_bybit_blocked_when_required(self):
        """Test that non-bybit venues are blocked when require_bybit_demo=True."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        result = gate.validate_execution_venue("okx")

        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert len(result.errors) > 0
        assert "not Bybit demo mode" in result.errors[0]

    def test_validate_bybit_prod_blocked_when_required(self):
        """Test that Bybit production endpoint is blocked when required."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        result = gate.validate_execution_venue(
            "bybit",
            "https://api.bybit.com",
        )

        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert any("PRODUCTION endpoint" in err for err in result.errors)

    def test_validate_venue_not_in_allowed_list(self):
        """Test that venue not in allowed list is blocked."""
        gate = VenueEnforcementGate(
            require_bybit_demo=False,
            allowed_venues=["bybit_demo", "okx"],
        )

        result = gate.validate_execution_venue("binance")

        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert "not in allowed venues" in result.errors[0]

    # Tests for validate_execution_venue with require_bybit_demo=False

    def test_validate_bybit_demo_passes_when_not_required(self):
        """Test that bybit_demo passes when require_bybit_demo=False."""
        gate = VenueEnforcementGate(require_bybit_demo=False)

        result = gate.validate_execution_venue("bybit_demo")

        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"

    def test_validate_non_bybit_allowed_when_not_required(self):
        """Test that non-bybit venues are allowed when require_bybit_demo=False."""
        gate = VenueEnforcementGate(require_bybit_demo=False)

        result = gate.validate_execution_venue("okx")

        assert result.valid is True
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert result.errors == []
        assert len(result.warnings) > 0
        assert any("not Bybit" in w for w in result.warnings)

    def test_validate_bybit_prod_warns_when_not_required(self):
        """Test that Bybit production triggers warning when not required."""
        gate = VenueEnforcementGate(require_bybit_demo=False)

        result = gate.validate_execution_venue(
            "bybit",
            "https://api.bybit.com",
        )

        assert result.valid is True
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert len(result.warnings) > 0
        assert any("not in demo mode" in w for w in result.warnings)

    # Tests for validate_outcome method

    def test_validate_outcome_with_venue(self):
        """Test validating an outcome with venue attribute."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        # Mock outcome object
        class MockOutcome:
            venue = "bybit_demo"
            endpoint = "https://api-demo.bybit.com"

        result = gate.validate_outcome(MockOutcome())

        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"

    def test_validate_outcome_without_venue(self):
        """Test validating an outcome without venue attribute."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        # Mock outcome without venue
        class MockOutcome:
            pass

        result = gate.validate_outcome(MockOutcome())

        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert "does not have a 'venue' attribute" in result.errors[0]

    def test_validate_outcome_with_provenance(self):
        """Test validating an outcome with provenance."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        # Mock outcome with provenance
        class MockProvenance:
            endpoint = "https://api-demo.bybit.com"

        class MockOutcome:
            venue = "bybit"
            provenance = MockProvenance()

        result = gate.validate_outcome(MockOutcome())

        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"

    # Tests for enforce_venue method

    def test_enforce_venue_passes(self):
        """Test enforce_venue passes for valid venue."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        # Should not raise
        gate.enforce_venue("bybit_demo")

    def test_enforce_venue_raises_on_invalid(self):
        """Test enforce_venue raises exception for invalid venue."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        with pytest.raises(VenueEnforcementError) as exc_info:
            gate.enforce_venue("okx")

        assert exc_info.value.venue == "okx"
        assert exc_info.value.test_mode_status == "INVALID_TEST_MODE"

    # Tests for factory function

    def test_create_default_gate(self):
        """Test create_default_gate factory function."""
        gate = create_default_gate(require_bybit_demo=True)
        assert gate.require_bybit_demo is True

        gate = create_default_gate(require_bybit_demo=False)
        assert gate.require_bybit_demo is False


class TestVenueEnforcementIntegration:
    """Integration tests for venue enforcement."""

    def test_full_workflow_strict_mode(self):
        """Test full workflow in strict mode."""
        gate = VenueEnforcementGate(require_bybit_demo=True)

        # Valid Bybit demo should pass
        result1 = gate.validate_execution_venue(
            "bybit_demo",
            "https://api-demo.bybit.com",
        )
        assert result1.valid is True

        # Non-demo should fail
        result2 = gate.validate_execution_venue("okx")
        assert result2.valid is False

        # Bybit prod should fail
        result3 = gate.validate_execution_venue(
            "bybit",
            "https://api.bybit.com",
        )
        assert result3.valid is False

    def test_full_workflow_lenient_mode(self):
        """Test full workflow in lenient mode."""
        gate = VenueEnforcementGate(require_bybit_demo=False)

        # All venues should pass with warnings
        result1 = gate.validate_execution_venue("bybit_demo")
        assert result1.valid is True

        result2 = gate.validate_execution_venue("okx")
        assert result2.valid is True
        assert len(result2.warnings) > 0

        result3 = gate.validate_execution_venue(
            "bybit",
            "https://api.bybit.com",
        )
        assert result3.valid is True
        assert len(result3.warnings) > 0

    def test_allowed_venues_filter(self):
        """Test allowed venues filtering."""
        gate = VenueEnforcementGate(
            require_bybit_demo=False,
            allowed_venues=["bybit_demo", "okx"],
        )

        # Allowed venues should pass
        result1 = gate.validate_execution_venue("bybit_demo")
        assert result1.valid is True

        result2 = gate.validate_execution_venue("okx")
        assert result2.valid is True

        # Non-allowed venue should fail
        result3 = gate.validate_execution_venue("binance")
        assert result3.valid is False
        assert "not in allowed venues" in result3.errors[0]

    def test_combined_strict_mode_and_allowed_venues(self):
        """Test strict mode combined with allowed venues."""
        gate = VenueEnforcementGate(
            require_bybit_demo=True,
            allowed_venues=["bybit_demo"],
        )

        # bybit_demo should pass
        result1 = gate.validate_execution_venue("bybit_demo")
        assert result1.valid is True

        # okx should fail (not in allowed list, even though require check would fail first)
        result2 = gate.validate_execution_venue("okx")
        assert result2.valid is False
