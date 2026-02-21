"""Strategy Submission API - Validate and register strategy submissions.

This module provides the main API for submitting strategies with validation,
safety checks, and registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from src.backtesting.dsl.validator import (
    DSLValidator,
    ValidationResult,
    ValidationError,
    ValidationWarning,
)
from src.backtesting.dsl.safety import SafetyChecker
from src.backtesting.dsl.fingerprint import compute_dsl_fingerprint


@dataclass(frozen=True)
class SubmissionResult:
    """Result of a strategy submission.

    Attributes:
        success: Whether submission was successful
        submission_id: Unique submission identifier
        strategy_id: Strategy identifier (from metadata)
        version: Strategy version
        fingerprint: DSL configuration fingerprint
        validation_result: Full validation results
        safety_errors: Safety constraint violations
        submitted_at: Submission timestamp
        error_message: Error message if failed
    """

    success: bool
    submission_id: str
    strategy_id: str
    version: str
    fingerprint: str
    validation_result: ValidationResult
    safety_errors: list[ValidationError]
    submitted_at: datetime
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "submission_id": self.submission_id,
            "strategy_id": self.strategy_id,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "validation": self.validation_result.to_dict(),
            "safety_errors": [e.to_dict() for e in self.safety_errors],
            "safety_passed": len(self.safety_errors) == 0,
            "submitted_at": self.submitted_at.isoformat(),
            "error_message": self.error_message,
        }

    def get_field_errors(self, field_path: str) -> list[ValidationError]:
        """Get errors for a specific field."""
        return self.validation_result.get_errors_for_field(field_path)

    @property
    def is_valid(self) -> bool:
        """Check if submission is valid (passed validation and safety)."""
        return (
            self.success
            and self.validation_result.is_valid
            and len(self.safety_errors) == 0
        )

    @property
    def has_warnings(self) -> bool:
        """Check if submission has warnings."""
        return len(self.validation_result.warnings) > 0


class StrategySubmission:
    """Strategy submission handler.

    Validates and registers strategy submissions with full field-level
    error reporting and safety constraint enforcement.
    """

    def __init__(self) -> None:
        """Initialize submission handler."""
        self.validator = DSLValidator()
        self.safety_checker = SafetyChecker()
        self._submissions: dict[str, SubmissionResult] = {}

    def submit(self, config: dict[str, Any]) -> SubmissionResult:
        """Validate and register a strategy submission.

        Args:
            config: DSL configuration dictionary

        Returns:
            SubmissionResult with validation results
        """
        submitted_at = datetime.utcnow()
        submission_id = str(uuid4())

        # Extract metadata
        metadata = config.get("metadata", {})
        strategy_id = metadata.get("name", "unknown")
        version = metadata.get("version", "unknown")

        try:
            # Step 1: Validate DSL schema
            validation_result = self.validator.validate(config)

            # Step 2: Check safety constraints
            safety_errors = self.safety_checker.check(config)

            # Step 3: Compute fingerprint
            fingerprint = compute_dsl_fingerprint(config)

            # Step 4: Determine success
            success = validation_result.is_valid and len(safety_errors) == 0

            result = SubmissionResult(
                success=success,
                submission_id=submission_id,
                strategy_id=strategy_id,
                version=version,
                fingerprint=fingerprint,
                validation_result=validation_result,
                safety_errors=safety_errors,
                submitted_at=submitted_at,
                error_message=None if success else "Validation or safety check failed",
            )

            # Store submission
            self._submissions[submission_id] = result

            return result

        except Exception as e:
            # Handle unexpected errors
            return SubmissionResult(
                success=False,
                submission_id=submission_id,
                strategy_id=strategy_id,
                version=version,
                fingerprint="",
                validation_result=ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field_path="",
                            message=f"Submission error: {str(e)}",
                            value="",
                            constraint="no exceptions",
                        )
                    ],
                    warnings=[],
                ),
                safety_errors=[],
                submitted_at=submitted_at,
                error_message=str(e),
            )

    def submit_file(self, path: Path | str) -> SubmissionResult:
        """Submit a strategy from a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            SubmissionResult
        """
        path = Path(path)

        if not path.exists():
            return SubmissionResult(
                success=False,
                submission_id=str(uuid4()),
                strategy_id="",
                version="",
                fingerprint="",
                validation_result=ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field_path="",
                            message=f"File not found: {path}",
                            value=str(path),
                            constraint="file must exist",
                        )
                    ],
                    warnings=[],
                ),
                safety_errors=[],
                submitted_at=datetime.utcnow(),
                error_message=f"File not found: {path}",
            )

        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
            return self.submit(config)
        except yaml.YAMLError as e:
            return SubmissionResult(
                success=False,
                submission_id=str(uuid4()),
                strategy_id="",
                version="",
                fingerprint="",
                validation_result=ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field_path="",
                            message=f"Invalid YAML: {e}",
                            value="",
                            constraint="valid YAML syntax",
                        )
                    ],
                    warnings=[],
                ),
                safety_errors=[],
                submitted_at=datetime.utcnow(),
                error_message=f"Invalid YAML: {e}",
            )

    def get_validation_errors(self, config: dict[str, Any]) -> list[ValidationError]:
        """Get field-level validation errors for UI display.

        Args:
            config: DSL configuration

        Returns:
            List of validation errors
        """
        result = self.validator.validate(config)
        return result.errors

    def get_validation_warnings(
        self, config: dict[str, Any]
    ) -> list[ValidationWarning]:
        """Get validation warnings for UI display.

        Args:
            config: DSL configuration

        Returns:
            List of validation warnings
        """
        result = self.validator.validate(config)
        return result.warnings

    def validate_only(self, config: dict[str, Any]) -> ValidationResult:
        """Validate without submitting.

        Args:
            config: DSL configuration

        Returns:
            ValidationResult
        """
        return self.validator.validate(config)

    def check_safety_only(self, config: dict[str, Any]) -> list[ValidationError]:
        """Check safety constraints without submitting.

        Args:
            config: DSL configuration

        Returns:
            List of safety violations
        """
        return self.safety_checker.check(config)

    def get_submission(self, submission_id: str) -> SubmissionResult | None:
        """Get a submission by ID.

        Args:
            submission_id: Submission identifier

        Returns:
            SubmissionResult or None if not found
        """
        return self._submissions.get(submission_id)

    def get_all_submissions(self) -> list[SubmissionResult]:
        """Get all submissions.

        Returns:
            List of all submissions
        """
        return list(self._submissions.values())

    def get_submissions_for_strategy(self, strategy_id: str) -> list[SubmissionResult]:
        """Get all submissions for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of submissions for the strategy
        """
        return [s for s in self._submissions.values() if s.strategy_id == strategy_id]


# Global submission handler
_default_submission = StrategySubmission()


def submit_strategy(config: dict[str, Any]) -> SubmissionResult:
    """Submit a strategy using default handler.

    Args:
        config: DSL configuration

    Returns:
        SubmissionResult
    """
    return _default_submission.submit(config)


def submit_strategy_file(path: Path | str) -> SubmissionResult:
    """Submit a strategy from file using default handler.

    Args:
        path: Path to YAML file

    Returns:
        SubmissionResult
    """
    return _default_submission.submit_file(path)


def validate_strategy(config: dict[str, Any]) -> ValidationResult:
    """Validate a strategy without submitting.

    Args:
        config: DSL configuration

    Returns:
        ValidationResult
    """
    return _default_submission.validate_only(config)


def check_strategy_safety(config: dict[str, Any]) -> list[ValidationError]:
    """Check strategy safety constraints.

    Args:
        config: DSL configuration

    Returns:
        List of safety violations
    """
    return _default_submission.check_safety_only(config)
