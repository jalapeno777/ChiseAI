"""Venue enforcement gate for test mode validation.

This module provides enforcement gates to ensure that:
1. Only approved venues are used for execution
2. Bybit demo mode is enforced when required
3. Non-demo execution is flagged/blocked based on configuration
4. Test mode status is tracked for audit trails

For ST-VENUE-003: Venue Enforcement Gate
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.outcome_capture.models import Outcome

logger = logging.getLogger(__name__)


class VenueEnforcementError(Exception):
    """Exception raised when venue enforcement fails.

    This exception is raised when:
    - A venue is not in the allowed list
    - Bybit demo mode is required but not used
    - Execution venue validation fails

    Attributes:
        message: Error message describing the enforcement failure
        venue: The venue that failed validation
        test_mode_status: The test mode status (VALID_TEST_MODE / INVALID_TEST_MODE)
    """

    def __init__(
        self,
        message: str,
        venue: str | None = None,
        test_mode_status: str = "INVALID_TEST_MODE",
    ) -> None:
        """Initialize the enforcement error.

        Args:
            message: Error message
            venue: The venue that failed validation
            test_mode_status: The test mode status
        """
        super().__init__(message)
        self.venue = venue
        self.test_mode_status = test_mode_status


@dataclass
class ValidationResult:
    """Result of venue validation.

    Attributes:
        valid: Whether the validation passed
        test_mode_status: Status of test mode (VALID_TEST_MODE / INVALID_TEST_MODE)
        errors: List of validation errors
        warnings: List of validation warnings
    """

    valid: bool
    test_mode_status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate test_mode_status is one of the allowed values."""
        allowed_statuses = {"VALID_TEST_MODE", "INVALID_TEST_MODE"}
        if self.test_mode_status not in allowed_statuses:
            raise ValueError(
                f"test_mode_status must be one of {allowed_statuses}, "
                f"got {self.test_mode_status}"
            )


class VenueEnforcementGate:
    """Enforcement gate for venue validation.

    This gate validates execution venues to ensure:
    - Only approved venues are used
    - Bybit demo mode is enforced when required
    - Test mode status is properly tracked

    Attributes:
        require_bybit_demo: Whether to require Bybit demo mode
        allowed_venues: List of allowed venue identifiers (None = all allowed)
    """

    # Known Bybit demo endpoints
    BYBIT_DEMO_ENDPOINTS = {
        "https://api-demo.bybit.com",
        "api-demo.bybit.com",
        "wss://stream-demo.bybit.com",
        "stream-demo.bybit.com",
    }

    # Known Bybit production endpoints (for detection)
    BYBIT_PROD_ENDPOINTS = {
        "https://api.bybit.com",
        "api.bybit.com",
        "wss://stream.bybit.com",
        "stream.bybit.com",
    }

    def __init__(
        self,
        require_bybit_demo: bool = False,
        allowed_venues: list[str] | None = None,
    ) -> None:
        """Initialize the venue enforcement gate.

        Args:
            require_bybit_demo: If True, only bybit_demo venue is allowed
            allowed_venues: List of allowed venue identifiers. If None, all venues
                           are allowed (subject to require_bybit_demo)
        """
        self.require_bybit_demo = require_bybit_demo
        self.allowed_venues = set(allowed_venues) if allowed_venues else None

        logger.info(
            f"VenueEnforcementGate initialized - "
            f"require_bybit_demo={require_bybit_demo}, "
            f"allowed_venues={allowed_venues}"
        )

    def is_bybit_demo(self, venue: str, endpoint: str | None = None) -> bool:
        """Check if a venue is Bybit demo mode.

        Args:
            venue: Venue identifier (e.g., "bybit_demo", "bybit", "okx")
            endpoint: Optional endpoint URL for additional validation

        Returns:
            True if the venue is Bybit demo mode
        """
        # Check venue identifier
        if venue.lower() == "bybit_demo":
            # If endpoint is provided, validate it's actually a demo endpoint
            if endpoint:
                endpoint_normalized = endpoint.rstrip("/")
                return endpoint_normalized in self.BYBIT_DEMO_ENDPOINTS
            return True

        # Check if endpoint is a Bybit demo endpoint
        if endpoint:
            endpoint_normalized = endpoint.rstrip("/")
            if endpoint_normalized in self.BYBIT_DEMO_ENDPOINTS:
                logger.info(
                    f"Venue {venue} identified as Bybit demo via endpoint {endpoint}"
                )
                return True

        return False

    def validate_execution_venue(
        self,
        venue: str,
        endpoint: str | None = None,
    ) -> ValidationResult:
        """Validate an execution venue.

        Args:
            venue: Venue identifier (e.g., "bybit_demo", "bybit", "okx")
            endpoint: Optional endpoint URL for additional validation

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check if venue is in allowed list
        if self.allowed_venues is not None and venue not in self.allowed_venues:
            error_msg = (
                f"Venue '{venue}' is not in allowed venues: {self.allowed_venues}"
            )
            errors.append(error_msg)
            logger.error(f"VENUE ENFORCEMENT: {error_msg}")
            return ValidationResult(
                valid=False,
                test_mode_status="INVALID_TEST_MODE",
                errors=errors,
                warnings=warnings,
            )

        # Check Bybit demo requirement
        is_demo = self.is_bybit_demo(venue, endpoint)

        if self.require_bybit_demo:
            # Strict mode: Only Bybit demo is allowed
            if not is_demo:
                error_msg = (
                    f"Venue '{venue}' is not Bybit demo mode. "
                    f"require_bybit_demo=True enforces Bybit demo only."
                )
                errors.append(error_msg)

                # Additional context about endpoint
                if endpoint:
                    if endpoint.rstrip("/") in self.BYBIT_PROD_ENDPOINTS:
                        error_detail = (
                            f"Endpoint {endpoint} is a Bybit PRODUCTION endpoint. "
                            f"Demo endpoints required."
                        )
                        errors.append(error_detail)
                        logger.error(f"VENUE ENFORCEMENT: {error_detail}")

                logger.error(f"VENUE ENFORCEMENT: {error_msg}")

                return ValidationResult(
                    valid=False,
                    test_mode_status="INVALID_TEST_MODE",
                    errors=errors,
                    warnings=warnings,
                )

            # Bybit demo is valid
            logger.info(
                f"VENUE ENFORCEMENT: Venue '{venue}' validated as Bybit demo mode"
            )
            return ValidationResult(
                valid=True,
                test_mode_status="VALID_TEST_MODE",
                errors=errors,
                warnings=warnings,
            )

        else:
            # Lenient mode: Non-Bybit venues allowed but flagged
            if venue.lower().startswith("bybit") and not is_demo:
                warning_msg = (
                    f"Venue '{venue}' is Bybit but not in demo mode. "
                    f"Production execution detected."
                )
                warnings.append(warning_msg)
                logger.warning(f"VENUE ENFORCEMENT: {warning_msg}")

            elif not venue.lower().startswith("bybit"):
                warning_msg = (
                    f"Venue '{venue}' is not Bybit. Cross-venue execution detected."
                )
                warnings.append(warning_msg)
                logger.warning(f"VENUE ENFORCEMENT: {warning_msg}")

            # Still valid in lenient mode
            test_mode_status = "VALID_TEST_MODE" if is_demo else "INVALID_TEST_MODE"
            logger.info(
                f"VENUE ENFORCEMENT: Venue '{venue}' allowed (lenient mode). "
                f"test_mode_status={test_mode_status}"
            )

            return ValidationResult(
                valid=True,
                test_mode_status=test_mode_status,
                errors=errors,
                warnings=warnings,
            )

    def validate_outcome(self, outcome: Outcome) -> ValidationResult:
        """Validate an execution outcome.

        This method extracts venue information from an outcome and validates it.

        Args:
            outcome: The execution outcome to validate

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        # Extract venue from outcome
        venue = getattr(outcome, "venue", None)
        if venue is None:
            error_msg = "Outcome does not have a 'venue' attribute"
            logger.error(f"VENUE ENFORCEMENT: {error_msg}")
            return ValidationResult(
                valid=False,
                test_mode_status="INVALID_TEST_MODE",
                errors=[error_msg],
                warnings=[],
            )

        # Extract endpoint if available
        endpoint = getattr(outcome, "endpoint", None)
        if endpoint is None:
            # Try to get from provenance if available
            provenance = getattr(outcome, "provenance", None)
            if provenance:
                endpoint = getattr(provenance, "endpoint", None)

        # Validate the venue
        return self.validate_execution_venue(venue, endpoint)

    def enforce_venue(
        self,
        venue: str,
        endpoint: str | None = None,
    ) -> None:
        """Enforce venue validation and raise exception on failure.

        This is a convenience method that validates the venue and raises
        VenueEnforcementError if validation fails.

        Args:
            venue: Venue identifier
            endpoint: Optional endpoint URL

        Raises:
            VenueEnforcementError: If venue validation fails
        """
        result = self.validate_execution_venue(venue, endpoint)

        if not result.valid:
            raise VenueEnforcementError(
                message="; ".join(result.errors),
                venue=venue,
                test_mode_status=result.test_mode_status,
            )

        # Log warnings even if valid
        for warning in result.warnings:
            logger.warning(f"VENUE ENFORCEMENT WARNING: {warning}")


def create_default_gate(require_bybit_demo: bool = False) -> VenueEnforcementGate:
    """Create a default venue enforcement gate.

    Args:
        require_bybit_demo: Whether to require Bybit demo mode

    Returns:
        Configured VenueEnforcementGate instance
    """
    return VenueEnforcementGate(require_bybit_demo=require_bybit_demo)
