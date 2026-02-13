"""Tests for strategy submission API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
import tempfile
import yaml

from src.backtesting.dsl.submission import (
    StrategySubmission,
    SubmissionResult,
    submit_strategy,
    validate_strategy,
    check_strategy_safety,
)
from src.backtesting.dsl.validator import ValidationResult
from tests.test_backtesting.test_dsl.fixtures import (  # noqa: E402
    create_valid_config,
    create_invalid_leverage_config,
    create_missing_required_fields_config,
)


class TestStrategySubmission:
    """Tests for StrategySubmission class."""

    def test_submit_valid_strategy(self):
        """Test submitting a valid strategy."""
        submission = StrategySubmission()
        config = create_valid_config()

        result = submission.submit(config)

        assert isinstance(result, SubmissionResult)
        assert result.success is True
        assert result.is_valid is True
        assert result.strategy_id == "TestStrategy"
        assert result.version == "1.0.0"
        assert result.fingerprint is not None
        assert len(result.fingerprint) == 64

    def test_submit_invalid_strategy(self):
        """Test submitting an invalid strategy."""
        submission = StrategySubmission()
        config = create_missing_required_fields_config()

        result = submission.submit(config)

        assert result.success is False
        assert result.is_valid is False
        assert len(result.validation_result.errors) > 0

    def test_submit_unsafe_strategy(self):
        """Test submitting a strategy that violates safety constraints."""
        submission = StrategySubmission()
        config = create_invalid_leverage_config()

        result = submission.submit(config)

        assert result.success is False
        assert result.is_valid is False
        assert len(result.safety_errors) > 0

    def test_submission_stored(self):
        """Test that submissions are stored."""
        submission = StrategySubmission()
        config = create_valid_config()

        result = submission.submit(config)

        # Should be retrievable
        stored = submission.get_submission(result.submission_id)
        assert stored is not None
        assert stored.submission_id == result.submission_id

    def test_get_all_submissions(self):
        """Test getting all submissions."""
        submission = StrategySubmission()
        config = create_valid_config()

        submission.submit(config)
        submission.submit(config)

        all_submissions = submission.get_all_submissions()

        assert len(all_submissions) == 2

    def test_get_submissions_for_strategy(self):
        """Test getting submissions for specific strategy."""
        submission = StrategySubmission()

        config1 = create_valid_config()
        submission.submit(config1)

        config2 = create_valid_config()
        config2["metadata"]["name"] = "OtherStrategy"
        submission.submit(config2)

        test_strategy_submissions = submission.get_submissions_for_strategy(
            "TestStrategy"
        )

        assert len(test_strategy_submissions) == 1

    def test_get_validation_errors(self):
        """Test getting validation errors for UI display."""
        submission = StrategySubmission()
        config = create_missing_required_fields_config()

        errors = submission.get_validation_errors(config)

        assert len(errors) > 0
        # Check field-level details
        error_paths = [e.field_path for e in errors]
        assert "metadata.name" in error_paths

    def test_validate_only(self):
        """Test validate without submitting."""
        submission = StrategySubmission()
        config = create_valid_config()

        result = submission.validate_only(config)

        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    def test_check_safety_only(self):
        """Test safety check without submitting."""
        submission = StrategySubmission()
        config = create_invalid_leverage_config()

        errors = submission.check_safety_only(config)

        assert len(errors) > 0

    def test_submit_file_valid(self):
        """Test submitting from valid file."""
        submission = StrategySubmission()
        config = create_valid_config()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            result = submission.submit_file(temp_path)

            assert result.success is True
            assert result.is_valid is True
        finally:
            Path(temp_path).unlink()

    def test_submit_file_not_found(self):
        """Test submitting from non-existent file."""
        submission = StrategySubmission()

        result = submission.submit_file("/nonexistent/path.yaml")

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_submit_file_invalid_yaml(self):
        """Test submitting from invalid YAML file."""
        submission = StrategySubmission()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        try:
            result = submission.submit_file(temp_path)

            assert result.success is False
            assert "yaml" in result.error_message.lower()
        finally:
            Path(temp_path).unlink()


class TestSubmissionResult:
    """Tests for SubmissionResult dataclass."""

    def test_create_result(self):
        """Test creating submission result."""
        from datetime import datetime
        from src.backtesting.dsl.validator import ValidationResult as VR

        result = SubmissionResult(
            success=True,
            submission_id="test-id",
            strategy_id="TestStrategy",
            version="1.0.0",
            fingerprint="abc123",
            validation_result=VR(is_valid=True, errors=[], warnings=[]),
            safety_errors=[],
            submitted_at=datetime.utcnow(),
        )

        assert result.success is True
        assert result.submission_id == "test-id"
        assert result.is_valid is True

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        from datetime import datetime
        from src.backtesting.dsl.validator import ValidationResult as VR

        result = SubmissionResult(
            success=True,
            submission_id="test-id",
            strategy_id="TestStrategy",
            version="1.0.0",
            fingerprint="abc123",
            validation_result=VR(is_valid=True, errors=[], warnings=[]),
            safety_errors=[],
            submitted_at=datetime.utcnow(),
        )

        data = result.to_dict()

        assert "success" in data
        assert "submission_id" in data
        assert "strategy_id" in data
        assert "validation" in data
        assert "safety_passed" in data

    def test_get_field_errors(self):
        """Test getting errors for specific field."""
        from datetime import datetime
        from src.backtesting.dsl.validator import (
            ValidationResult as VR,
            ValidationError as VE,
        )

        result = SubmissionResult(
            success=False,
            submission_id="test-id",
            strategy_id="Test",
            version="1.0.0",
            fingerprint="",
            validation_result=VR(
                is_valid=False,
                errors=[
                    VE("metadata.name", "Required", "", "required"),
                    VE("metadata.version", "Required", "", "required"),
                ],
                warnings=[],
            ),
            safety_errors=[],
            submitted_at=datetime.utcnow(),
        )

        name_errors = result.get_field_errors("metadata.name")

        assert len(name_errors) == 1
        assert name_errors[0].field_path == "metadata.name"

    def test_has_warnings_property(self):
        """Test has_warnings property."""
        from datetime import datetime
        from src.backtesting.dsl.validator import (
            ValidationResult as VR,
            ValidationWarning as VW,
        )

        result = SubmissionResult(
            success=True,
            submission_id="test-id",
            strategy_id="Test",
            version="1.0.0",
            fingerprint="abc",
            validation_result=VR(
                is_valid=True,
                errors=[],
                warnings=[VW("test", "Warning", "value", "Suggestion")],
            ),
            safety_errors=[],
            submitted_at=datetime.utcnow(),
        )

        assert result.has_warnings is True


class TestUtilityFunctions:
    """Tests for submission utility functions."""

    def test_submit_strategy_function(self):
        """Test submit_strategy utility function."""
        config = create_valid_config()

        result = submit_strategy(config)

        assert isinstance(result, SubmissionResult)
        assert result.success is True

    def test_validate_strategy_function(self):
        """Test validate_strategy utility function."""
        config = create_valid_config()

        result = validate_strategy(config)

        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    def test_check_strategy_safety_function(self):
        """Test check_strategy_safety utility function."""
        config = create_invalid_leverage_config()

        errors = check_strategy_safety(config)

        assert len(errors) > 0
