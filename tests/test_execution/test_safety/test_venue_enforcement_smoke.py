"""Smoke tests for venue_enforcement module.

Basic tests to verify the VenueEnforcementGate functionality.
"""

import pytest
from unittest.mock import MagicMock, patch

from execution.safety.venue_enforcement import (
    ValidationResult,
    VenueEnforcementError,
    VenueEnforcementGate,
    create_default_gate,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_creation_valid(self):
        """Test that ValidationResult can be created for valid case."""
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

    def test_validation_result_creation_invalid(self):
        """Test that ValidationResult can be created for invalid case."""
        result = ValidationResult(
            valid=False,
            test_mode_status="INVALID_TEST_MODE",
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
        )
        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert result.errors == ["Error 1", "Error 2"]
        assert result.warnings == ["Warning 1"]

    def test_validation_result_invalid_status_raises(self):
        """Test that ValidationResult raises on invalid status."""
        with pytest.raises(ValueError) as exc_info:
            ValidationResult(
                valid=True,
                test_mode_status="INVALID_STATUS",
                errors=[],
                warnings=[],
            )
        assert "test_mode_status must be one of" in str(exc_info.value)


class TestVenueEnforcementError:
    """Tests for VenueEnforcementError exception."""

    def test_error_creation_basic(self):
        """Test basic error creation."""
        error = VenueEnforcementError("Test error message")
        assert str(error) == "Test error message"
        assert error.venue is None
        assert error.test_mode_status == "INVALID_TEST_MODE"

    def test_error_creation_with_venue(self):
        """Test error creation with venue."""
        error = VenueEnforcementError(
            message="Venue not allowed",
            venue="unauthorized_venue",
            test_mode_status="INVALID_TEST_MODE",
        )
        assert str(error) == "Venue not allowed"
        assert error.venue == "unauthorized_venue"
        assert error.test_mode_status == "INVALID_TEST_MODE"

    def test_error_is_exception(self):
        """Test that VenueEnforcementError is an Exception."""
        error = VenueEnforcementError("Test")
        assert isinstance(error, Exception)


class TestVenueEnforcementGateInitialization:
    """Tests for VenueEnforcementGate initialization."""

    def test_gate_creation_default(self):
        """Test gate creation with default parameters."""
        gate = VenueEnforcementGate()
        assert gate.require_bybit_demo is False
        assert gate.allowed_venues is None

    def test_gate_creation_with_require_demo(self):
        """Test gate creation with require_bybit_demo=True."""
        gate = VenueEnforcementGate(require_bybit_demo=True)
        assert gate.require_bybit_demo is True
        assert gate.allowed_venues is None

    def test_gate_creation_with_allowed_venues(self):
        """Test gate creation with allowed_venues list."""
        venues = ["bybit_demo", "bybit"]
        gate = VenueEnforcementGate(allowed_venues=venues)
        assert gate.require_bybit_demo is False
        assert gate.allowed_venues == {"bybit_demo", "bybit"}

    def test_gate_creation_with_both_params(self):
        """Test gate creation with both parameters."""
        venues = ["bybit_demo"]
        gate = VenueEnforcementGate(
            require_bybit_demo=True,
            allowed_venues=venues,
        )
        assert gate.require_bybit_demo is True
        assert gate.allowed_venues == {"bybit_demo"}

    def test_gate_has_demo_endpoints(self):
        """Test that gate has BYBIT_DEMO_ENDPOINTS defined."""
        gate = VenueEnforcementGate()
        assert hasattr(gate, "BYBIT_DEMO_ENDPOINTS")
        assert "https://api-demo.bybit.com" in gate.BYBIT_DEMO_ENDPOINTS
        assert "api-demo.bybit.com" in gate.BYBIT_DEMO_ENDPOINTS

    def test_gate_has_prod_endpoints(self):
        """Test that gate has BYBIT_PROD_ENDPOINTS defined."""
        gate = VenueEnforcementGate()
        assert hasattr(gate, "BYBIT_PROD_ENDPOINTS")
        assert "https://api.bybit.com" in gate.BYBIT_PROD_ENDPOINTS
        assert "api.bybit.com" in gate.BYBIT_PROD_ENDPOINTS


class TestVenueEnforcementGateIsBybitDemo:
    """Tests for is_bybit_demo method."""

    def test_is_bybit_demo_by_venue_name(self):
        """Test detection by venue name."""
        gate = VenueEnforcementGate()
        assert gate.is_bybit_demo("bybit_demo") is True
        assert gate.is_bybit_demo("bybit_demo", None) is True

    def test_is_bybit_demo_by_venue_name_case_insensitive(self):
        """Test that venue name detection is case insensitive."""
        gate = VenueEnforcementGate()
        assert gate.is_bybit_demo("BYBIT_DEMO") is True
        assert gate.is_bybit_demo("Bybit_Demo") is True

    def test_is_bybit_demo_by_endpoint(self):
        """Test detection by endpoint."""
        gate = VenueEnforcementGate()
        assert gate.is_bybit_demo("bybit", "https://api-demo.bybit.com") is True
        assert gate.is_bybit_demo("bybit", "api-demo.bybit.com") is True

    def test_is_bybit_demo_non_demo_venue(self):
        """Test that non-demo venues return False."""
        gate = VenueEnforcementGate()
        assert gate.is_bybit_demo("bybit") is False
        assert gate.is_bybit_demo("okx") is False
        assert gate.is_bybit_demo("binance") is False

    def test_is_bybit_demo_with_prod_endpoint(self):
        """Test that production endpoint returns False."""
        gate = VenueEnforcementGate()
        assert gate.is_bybit_demo("bybit", "https://api.bybit.com") is False


class TestVenueEnforcementGateValidateExecutionVenue:
    """Tests for validate_execution_venue method."""

    def test_validate_allowed_venue(self):
        """Test validation of allowed venue."""
        gate = VenueEnforcementGate(allowed_venues=["bybit_demo"])
        result = gate.validate_execution_venue("bybit_demo")
        assert result.valid is True

    def test_validate_disallowed_venue(self):
        """Test validation of disallowed venue."""
        gate = VenueEnforcementGate(allowed_venues=["bybit_demo"])
        result = gate.validate_execution_venue("unauthorized_venue")
        assert result.valid is False
        assert "not in allowed venues" in result.errors[0]

    def test_validate_with_require_bybit_demo_success(self):
        """Test validation with require_bybit_demo=True and demo venue."""
        gate = VenueEnforcementGate(require_bybit_demo=True)
        result = gate.validate_execution_venue("bybit_demo")
        assert result.valid is True
        assert result.test_mode_status == "VALID_TEST_MODE"

    def test_validate_with_require_bybit_demo_failure(self):
        """Test validation with require_bybit_demo=True and non-demo venue."""
        gate = VenueEnforcementGate(require_bybit_demo=True)
        result = gate.validate_execution_venue("bybit")
        assert result.valid is False
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert "not Bybit demo mode" in result.errors[0]

    def test_validate_with_prod_endpoint_in_strict_mode(self):
        """Test validation catches production endpoint in strict mode."""
        gate = VenueEnforcementGate(require_bybit_demo=True)
        result = gate.validate_execution_venue("bybit", "https://api.bybit.com")
        assert result.valid is False
        assert "PRODUCTION endpoint" in result.errors[1]

    def test_validate_lenient_mode_with_bybit_non_demo(self):
        """Test lenient mode allows bybit non-demo with warning."""
        gate = VenueEnforcementGate(require_bybit_demo=False)
        result = gate.validate_execution_venue("bybit")
        assert result.valid is True
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert len(result.warnings) > 0
        assert "Production execution detected" in result.warnings[0]

    def test_validate_lenient_mode_with_non_bybit(self):
        """Test lenient mode allows non-bybit venue with warning."""
        gate = VenueEnforcementGate(require_bybit_demo=False)
        result = gate.validate_execution_venue("okx")
        assert result.valid is True
        assert result.test_mode_status == "INVALID_TEST_MODE"
        assert len(result.warnings) > 0
        assert "not Bybit" in result.warnings[0]


class TestVenueEnforcementGateValidateOutcome:
    """Tests for validate_outcome method."""

    def test_validate_outcome_with_venue(self):
        """Test validation with outcome that has venue."""
        gate = VenueEnforcementGate()
        mock_outcome = MagicMock()
        mock_outcome.venue = "bybit_demo"
        mock_outcome.endpoint = None
        mock_outcome.provenance = None

        result = gate.validate_outcome(mock_outcome)
        assert result.valid is True

    def test_validate_outcome_without_venue(self):
        """Test validation with outcome missing venue."""
        gate = VenueEnforcementGate()
        mock_outcome = MagicMock()
        mock_outcome.venue = None

        result = gate.validate_outcome(mock_outcome)
        assert result.valid is False
        assert "does not have a 'venue' attribute" in result.errors[0]

    def test_validate_outcome_with_endpoint_from_provenance(self):
        """Test validation extracts endpoint from provenance."""
        gate = VenueEnforcementGate(require_bybit_demo=True)
        mock_outcome = MagicMock()
        mock_outcome.venue = "bybit_demo"
        mock_outcome.endpoint = None
        mock_provenance = MagicMock()
        mock_provenance.endpoint = "https://api-demo.bybit.com"
        mock_outcome.provenance = mock_provenance

        result = gate.validate_outcome(mock_outcome)
        assert result.valid is True


class TestVenueEnforcementGateEnforceVenue:
    """Tests for enforce_venue method."""

    def test_enforce_venue_passes(self):
        """Test that enforce_venue passes for valid venue."""
        gate = VenueEnforcementGate()
        # Should not raise
        gate.enforce_venue("bybit_demo")

    def test_enforce_venue_raises_on_invalid(self):
        """Test that enforce_venue raises for invalid venue."""
        gate = VenueEnforcementGate(
            require_bybit_demo=True,
            allowed_venues=["bybit_demo"],
        )
        with pytest.raises(VenueEnforcementError) as exc_info:
            gate.enforce_venue("unauthorized_venue")
        assert exc_info.value.venue == "unauthorized_venue"

    def test_enforce_venue_logs_warnings(self):
        """Test that enforce_venue logs warnings even when valid."""
        gate = VenueEnforcementGate(require_bybit_demo=False)
        with patch("execution.safety.venue_enforcement.logger") as mock_logger:
            gate.enforce_venue("okx")  # Non-Bybit venue
            mock_logger.warning.assert_called()


class TestCreateDefaultGate:
    """Tests for create_default_gate function."""

    def test_create_default_gate_returns_gate(self):
        """Test that create_default_gate returns a VenueEnforcementGate."""
        gate = create_default_gate()
        assert isinstance(gate, VenueEnforcementGate)

    def test_create_default_gate_default_params(self):
        """Test that create_default_gate uses default parameters."""
        gate = create_default_gate()
        assert gate.require_bybit_demo is False
        assert gate.allowed_venues is None

    def test_create_default_gate_with_require_demo(self):
        """Test that create_default_gate accepts require_bybit_demo parameter."""
        gate = create_default_gate(require_bybit_demo=True)
        assert gate.require_bybit_demo is True
