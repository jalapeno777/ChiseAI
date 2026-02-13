"""Tests for DSL safety constraints."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from src.backtesting.dsl.safety import (
    SafetyChecker,
    check_safety,
    is_safe,
    SAFETY_CONSTRAINTS,
    SafetyConstraint,
)
from src.backtesting.dsl.validator import ValidationError
from tests.test_backtesting.test_dsl.fixtures import (  # noqa: E402
    create_valid_config,
    create_invalid_leverage_config,
    create_invalid_position_percent_config,
    create_invalid_confluence_score_config,
    create_invalid_timeframe_config,
)


class TestSafetyConstraints:
    """Tests for safety constraint definitions."""

    def test_max_leverage_constraint(self):
        """Test max leverage constraint definition."""
        constraint = SAFETY_CONSTRAINTS["max_leverage"]

        assert constraint.name == "max_leverage"
        assert constraint.max_value == 3.0
        assert constraint.min_value == 1.0
        assert constraint.required is True

    def test_max_position_percent_constraint(self):
        """Test max position percent constraint definition."""
        constraint = SAFETY_CONSTRAINTS["max_position_percent"]

        assert constraint.name == "max_position_percent"
        assert constraint.max_value == 100.0
        assert constraint.required is True

    def test_min_confluence_score_constraint(self):
        """Test min confluence score constraint definition."""
        constraint = SAFETY_CONSTRAINTS["min_confluence_score"]

        assert constraint.name == "min_confluence_score"
        assert constraint.min_value == 0.5
        assert constraint.max_value == 1.0
        assert constraint.required is True


class TestSafetyChecker:
    """Tests for SafetyChecker."""

    def test_valid_config_passes_safety(self):
        """Test that valid config passes safety checks."""
        checker = SafetyChecker()
        config = create_valid_config()

        errors = checker.check(config)

        assert len(errors) == 0

    def test_max_leverage_violation(self):
        """Test that leverage > 3.0 causes safety error."""
        checker = SafetyChecker()
        config = create_invalid_leverage_config()

        errors = checker.check(config)

        assert len(errors) > 0

        # Check for leverage error
        leverage_errors = [e for e in errors if "max_leverage" in e.field_path]
        assert len(leverage_errors) == 1

        error = leverage_errors[0]
        assert "SAFETY VIOLATION" in error.message
        assert error.value == 5.0
        assert "3.0" in error.constraint

    def test_max_position_percent_violation(self):
        """Test that position percent > 100% causes safety error."""
        checker = SafetyChecker()
        config = create_invalid_position_percent_config()

        errors = checker.check(config)

        assert len(errors) > 0

        # Check for position percent error
        position_errors = [e for e in errors if "max_position_percent" in e.field_path]
        assert len(position_errors) == 1

        error = position_errors[0]
        assert "SAFETY VIOLATION" in error.message
        assert error.value == 150.0

    def test_min_confluence_score_violation(self):
        """Test that confluence score < 0.5 causes safety error."""
        checker = SafetyChecker()
        config = create_invalid_confluence_score_config()

        errors = checker.check(config)

        assert len(errors) > 0

        # Check for confluence score error
        confluence_errors = [e for e in errors if "min_score" in e.field_path]
        assert len(confluence_errors) == 1

        error = confluence_errors[0]
        assert "SAFETY VIOLATION" in error.message
        assert error.value == 0.3

    def test_invalid_timeframe_violation(self):
        """Test that invalid timeframe causes safety error."""
        checker = SafetyChecker()
        config = create_invalid_timeframe_config()

        errors = checker.check(config)

        assert len(errors) > 0

        # Check for timeframe error
        timeframe_errors = [e for e in errors if "timeframe" in e.field_path]
        assert len(timeframe_errors) >= 1

    def test_get_constraint(self):
        """Test getting constraint by name."""
        checker = SafetyChecker()

        constraint = checker.get_constraint("max_leverage")
        assert constraint is not None
        assert constraint.name == "max_leverage"

        # Non-existent constraint
        assert checker.get_constraint("non_existent") is None

    def test_get_all_constraints(self):
        """Test getting all constraints."""
        checker = SafetyChecker()

        constraints = checker.get_all_constraints()

        assert "max_leverage" in constraints
        assert "max_position_percent" in constraints
        assert "min_confluence_score" in constraints


class TestSafetyUtilityFunctions:
    """Tests for safety utility functions."""

    def test_check_safety_function(self):
        """Test check_safety utility function."""
        config = create_valid_config()
        errors = check_safety(config)

        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_is_safe_function_true(self):
        """Test is_safe returns True for safe config."""
        config = create_valid_config()

        assert is_safe(config) is True

    def test_is_safe_function_false(self):
        """Test is_safe returns False for unsafe config."""
        config = create_invalid_leverage_config()

        assert is_safe(config) is False


class TestSafetyConstraintDataclass:
    """Tests for SafetyConstraint dataclass."""

    def test_create_constraint(self):
        """Test creating safety constraint."""
        constraint = SafetyConstraint(
            name="test_constraint",
            description="A test constraint",
            max_value=100.0,
            min_value=0.0,
            required=True,
        )

        assert constraint.name == "test_constraint"
        assert constraint.max_value == 100.0
        assert constraint.min_value == 0.0
        assert constraint.required is True

    def test_create_optional_constraint(self):
        """Test creating optional (non-required) constraint."""
        constraint = SafetyConstraint(
            name="optional_constraint",
            description="An optional constraint",
            required=False,
        )

        assert constraint.required is False
        assert constraint.max_value is None
        assert constraint.min_value is None
