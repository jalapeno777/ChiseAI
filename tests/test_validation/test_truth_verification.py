"""Comprehensive tests for per_task_truth_verification module.

Tests validate:
AC1: Validator checks all per-task evidence fields exist
AC2: Validator verifies test results include pass/fail counts
AC3: All tests pass with 100% pass rate
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure import path for the module under test
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from per_task_truth_verification import (
    DICT_FIELDS,
    LIST_FIELDS,
    REQUIRED_FIELDS,
    EvidenceValidationError,
    FieldValidation,
    PerTaskEvidenceValidator,
    PerTaskValidationResult,
    validate_per_task_evidence,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_evidence() -> dict[str, Any]:
    """Return a valid evidence dict with all required fields."""
    return {
        "commands_run": ["pytest tests/test_validation/test_truth_verification.py -v"],
        "tests_run_with_results": "42 passed, 0 failed",
        "logs_checked_with_findings": ["Checked Redis logs - no anomalies found"],
        "acceptance_criteria_mapping": {
            "AC1": "All required fields present and validated",
            "AC2": "Test results string contains pass/fail counts",
            "AC3": "All tests pass",
        },
        "residual_risks": ["None identified"],
    }


@pytest.fixture
def valid_evidence_dict_tests() -> dict[str, Any]:
    """Return valid evidence with dict-format test results."""
    return {
        "commands_run": ["pytest tests/ -v", "ruff check ."],
        "tests_run_with_results": {"passed": 42, "failed": 0, "skipped": 2},
        "logs_checked_with_findings": ["Application logs clean"],
        "acceptance_criteria_mapping": {"AC1": "Verified"},
        "residual_risks": [],
    }


@pytest.fixture
def valid_evidence_list_tests() -> dict[str, Any]:
    """Return valid evidence with list-format test results."""
    return {
        "commands_run": ["pytest"],
        "tests_run_with_results": [
            "test_foo.py::test_bar PASSED",
            "test_baz.py::test_qux PASSED",
        ],
        "logs_checked_with_findings": ["No issues"],
        "acceptance_criteria_mapping": {"AC1": "Done"},
        "residual_risks": ["Minor: needs re-test after refactor"],
    }


@pytest.fixture
def validator() -> PerTaskEvidenceValidator:
    """Return a default PerTaskEvidenceValidator."""
    return PerTaskEvidenceValidator()


# ── AC1: Validator checks all per-task evidence fields exist ─────────────────


class TestRequiredFieldsExist:
    """AC1: Validator checks all per-task evidence fields exist."""

    def test_all_fields_present_passes(self, validator, valid_evidence):
        """Valid evidence with all fields passes validation."""
        result = validator.validate(valid_evidence)
        assert result.valid
        assert result.fields_failed == 0
        assert result.fields_passed == len(REQUIRED_FIELDS)

    def test_missing_commands_run_fails(self, validator, valid_evidence):
        """Missing commands_run field causes failure."""
        del valid_evidence["commands_run"]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("commands_run" in e for e in result.errors)

    def test_missing_tests_run_with_results_fails(self, validator, valid_evidence):
        """Missing tests_run_with_results field causes failure."""
        del valid_evidence["tests_run_with_results"]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("tests_run_with_results" in e for e in result.errors)

    def test_missing_logs_checked_with_findings_fails(self, validator, valid_evidence):
        """Missing logs_checked_with_findings field causes failure."""
        del valid_evidence["logs_checked_with_findings"]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("logs_checked_with_findings" in e for e in result.errors)

    def test_missing_acceptance_criteria_mapping_fails(self, validator, valid_evidence):
        """Missing acceptance_criteria_mapping field causes failure."""
        del valid_evidence["acceptance_criteria_mapping"]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("acceptance_criteria_mapping" in e for e in result.errors)

    def test_missing_residual_risks_fails(self, validator, valid_evidence):
        """Missing residual_risks field causes failure."""
        del valid_evidence["residual_risks"]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("residual_risks" in e for e in result.errors)

    def test_empty_evidence_fails_all_fields(self, validator):
        """Empty dict fails all field checks."""
        result = validator.validate({})
        assert not result.valid
        assert result.fields_failed == len(REQUIRED_FIELDS)
        assert result.fields_passed == 0

    def test_extra_fields_do_not_cause_failure(self, validator, valid_evidence):
        """Extra fields beyond required do not cause failure."""
        valid_evidence["extra_field"] = "some value"
        valid_evidence["another_extra"] = 42
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_non_dict_evidence_fails(self, validator):
        """Non-dict evidence causes immediate failure."""
        result = validator.validate("not a dict")
        assert not result.valid
        assert any("dictionary" in e for e in result.errors)

    def test_none_evidence_fails(self, validator):
        """None evidence causes immediate failure."""
        result = validator.validate(None)
        assert not result.valid

    def test_list_evidence_fails(self, validator):
        """List evidence causes immediate failure."""
        result = validator.validate([1, 2, 3])
        assert not result.valid


class TestFieldTypeValidation:
    """Validate type constraints on evidence fields."""

    def test_commands_run_as_string_passes(self, validator, valid_evidence):
        """commands_run accepts string value."""
        valid_evidence["commands_run"] = "pytest tests/ -v"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_commands_run_as_list_passes(self, validator, valid_evidence):
        """commands_run accepts list value."""
        valid_evidence["commands_run"] = ["pytest tests/ -v", "ruff check ."]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_commands_run_as_int_fails(self, validator, valid_evidence):
        """commands_run rejects int value."""
        valid_evidence["commands_run"] = 42
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("commands_run" in e and "list or string" in e for e in result.errors)

    def test_tests_run_with_results_as_string_passes(self, validator, valid_evidence):
        """tests_run_with_results accepts string."""
        valid_evidence["tests_run_with_results"] = "30 passed, 0 failed"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_tests_run_with_results_as_dict_passes(self, validator, valid_evidence):
        """tests_run_with_results accepts dict."""
        valid_evidence["tests_run_with_results"] = {"passed": 30, "failed": 0}
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_tests_run_with_results_as_list_passes(self, validator, valid_evidence):
        """tests_run_with_results accepts list."""
        valid_evidence["tests_run_with_results"] = [
            "test_foo PASSED",
            "test_bar PASSED",
        ]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_acceptance_criteria_mapping_must_be_dict(self, validator, valid_evidence):
        """acceptance_criteria_mapping rejects non-dict."""
        valid_evidence["acceptance_criteria_mapping"] = "not a dict"
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any(
            "acceptance_criteria_mapping" in e and "dict" in e for e in result.errors
        )

    def test_acceptance_criteria_mapping_as_list_fails(self, validator, valid_evidence):
        """acceptance_criteria_mapping rejects list."""
        valid_evidence["acceptance_criteria_mapping"] = ["AC1", "AC2"]
        result = validator.validate(valid_evidence)
        assert not result.valid


class TestEmptyValueValidation:
    """Validate that empty values are properly rejected."""

    def test_none_value_fails(self, validator, valid_evidence):
        """None value for required field fails."""
        valid_evidence["commands_run"] = None
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("commands_run" in e and "empty" in e.lower() for e in result.errors)

    def test_empty_string_fails(self, validator, valid_evidence):
        """Empty string for required field fails."""
        valid_evidence["tests_run_with_results"] = ""
        result = validator.validate(valid_evidence)
        assert not result.valid

    def test_empty_list_fails(self, validator, valid_evidence):
        """Empty list for required field fails."""
        valid_evidence["commands_run"] = []
        result = validator.validate(valid_evidence)
        assert not result.valid

    def test_empty_dict_for_ac_mapping_fails(self, validator, valid_evidence):
        """Empty dict for acceptance_criteria_mapping fails."""
        valid_evidence["acceptance_criteria_mapping"] = {}
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("at least one entry" in e for e in result.errors)

    def test_whitespace_only_commands_fails(self, validator, valid_evidence):
        """Whitespace-only commands_run fails."""
        valid_evidence["commands_run"] = ["   ", "\t"]
        result = validator.validate(valid_evidence)
        assert not result.valid


# ── AC2: Validator verifies test results include pass/fail counts ────────────


class TestTestResultsPassFailCounts:
    """AC2: Validator verifies test results include pass/fail counts."""

    def test_string_with_pass_and_fail_counts_passes(self, validator, valid_evidence):
        """String '42 passed, 0 failed' passes validation."""
        valid_evidence["tests_run_with_results"] = "42 passed, 0 failed"
        result = validator.validate(valid_evidence)
        assert result.valid
        test_field = next(
            (
                f
                for f in result.field_results
                if f.field_name == "tests_run_with_results"
            ),
            None,
        )
        assert test_field is not None
        assert test_field.passed

    def test_string_with_pass_count_only_warns(self, validator, valid_evidence):
        """String with pass count but no fail count produces warning."""
        valid_evidence["tests_run_with_results"] = "42 passed"
        result = validator.validate(valid_evidence)
        # Warning is not an error, so overall valid
        assert result.valid
        assert any("fail count" in w for w in result.warnings)

    def test_string_with_no_pass_count_fails(self, validator, valid_evidence):
        """String without pass count fails validation."""
        valid_evidence["tests_run_with_results"] = "All tests look good"
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("pass count" in e for e in result.errors)

    def test_string_with_fail_count_only_warns(self, validator, valid_evidence):
        """String with fail count but no pass count fails."""
        valid_evidence["tests_run_with_results"] = "0 failed"
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("pass count" in e for e in result.errors)

    def test_pytest_output_format_passes(self, validator, valid_evidence):
        """Standard pytest output format passes."""
        valid_evidence["tests_run_with_results"] = (
            "30 passed, 2 failed, 1 skipped in 5.2s"
        )
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_pytest_verbose_output_passes(self, validator, valid_evidence):
        """Verbose pytest output passes."""
        valid_evidence["tests_run_with_results"] = "15 passed in 2.1s"
        result = validator.validate(valid_evidence)
        assert result.valid
        # Should warn about missing fail count
        assert any("fail count" in w for w in result.warnings)

    def test_dict_with_passed_key_passes(self, validator, valid_evidence):
        """Dict with 'passed' key passes."""
        valid_evidence["tests_run_with_results"] = {"passed": 30, "failed": 0}
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_dict_without_passed_key_fails(self, validator, valid_evidence):
        """Dict without 'passed' key fails."""
        valid_evidence["tests_run_with_results"] = {"total": 30, "success_rate": 1.0}
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("passed" in e for e in result.errors)

    def test_list_of_test_results_passes(self, validator, valid_evidence):
        """List of test result strings passes."""
        valid_evidence["tests_run_with_results"] = [
            "tests/test_foo.py::test_bar PASSED",
            "tests/test_baz.py::test_qux PASSED",
        ]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_empty_list_of_test_results_fails(self, validator, valid_evidence):
        """Empty list of test results fails."""
        valid_evidence["tests_run_with_results"] = []
        result = validator.validate(valid_evidence)
        assert not result.valid

    def test_case_insensitive_pass_fail(self, validator, valid_evidence):
        """Pass/fail detection is case-insensitive."""
        valid_evidence["tests_run_with_results"] = "30 PASSED, 0 FAILED"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_numeric_pass_count_variants(self, validator, valid_evidence):
        """Various numeric patterns for pass counts are detected."""
        valid_evidence["tests_run_with_results"] = "100 passed, 3 failed, 5 skipped"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_zero_passed_with_failures(self, validator, valid_evidence):
        """Zero passed with failures is still valid (has pass count)."""
        valid_evidence["tests_run_with_results"] = "0 passed, 5 failed"
        result = validator.validate(valid_evidence)
        assert result.valid


# ── AC3: Comprehensive edge case tests ───────────────────────────────────────


class TestCommandsRunValidation:
    """Validate commands_run field content."""

    def test_single_command_passes(self, validator, valid_evidence):
        """Single command string passes."""
        valid_evidence["commands_run"] = ["pytest tests/ -v"]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_multiple_commands_passes(self, validator, valid_evidence):
        """Multiple commands pass."""
        valid_evidence["commands_run"] = [
            "pytest tests/ -v",
            "ruff check .",
            "black --check .",
        ]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_string_command_passes(self, validator, valid_evidence):
        """Single string command passes."""
        valid_evidence["commands_run"] = "pytest tests/ -v"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_list_with_empty_strings_fails(self, validator, valid_evidence):
        """List with only empty strings fails."""
        valid_evidence["commands_run"] = ["", "   "]
        result = validator.validate(valid_evidence)
        assert not result.valid
        assert any("non-empty command" in e for e in result.errors)

    def test_list_with_non_string_entries_passes_if_non_empty(
        self, validator, valid_evidence
    ):
        """List with non-string entries is filtered; valid strings suffice."""
        valid_evidence["commands_run"] = [123, "pytest tests/"]
        result = validator.validate(valid_evidence)
        # 123 is not a string so it's filtered, but "pytest tests/" is valid
        assert result.valid


class TestAcceptanceCriteriaMappingValidation:
    """Validate acceptance_criteria_mapping field content."""

    def test_single_entry_passes(self, validator, valid_evidence):
        """Single AC entry passes."""
        valid_evidence["acceptance_criteria_mapping"] = {"AC1": "Verified"}
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_multiple_entries_passes(self, validator, valid_evidence):
        """Multiple AC entries pass."""
        valid_evidence["acceptance_criteria_mapping"] = {
            "AC1": "All fields present",
            "AC2": "Tests verified",
            "AC3": "100% pass rate",
        }
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_empty_dict_fails(self, validator, valid_evidence):
        """Empty dict fails."""
        valid_evidence["acceptance_criteria_mapping"] = {}
        result = validator.validate(valid_evidence)
        assert not result.valid

    def test_non_dict_fails(self, validator, valid_evidence):
        """Non-dict value fails."""
        valid_evidence["acceptance_criteria_mapping"] = "AC1: verified"
        result = validator.validate(valid_evidence)
        assert not result.valid


class TestLogsCheckedWithFindingsValidation:
    """Validate logs_checked_with_findings field."""

    def test_string_value_passes(self, validator, valid_evidence):
        """String value passes."""
        valid_evidence["logs_checked_with_findings"] = "Checked Redis, no anomalies"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_list_value_passes(self, validator, valid_evidence):
        """List value passes."""
        valid_evidence["logs_checked_with_findings"] = [
            "Redis: no anomalies",
            "Application: clean",
        ]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_int_value_fails(self, validator, valid_evidence):
        """Int value fails type check."""
        valid_evidence["logs_checked_with_findings"] = 42
        result = validator.validate(valid_evidence)
        assert not result.valid


class TestResidualRisksValidation:
    """Validate residual_risks field."""

    def test_list_with_risks_passes(self, validator, valid_evidence):
        """List with risk items passes."""
        valid_evidence["residual_risks"] = [
            "Minor: needs re-test after refactor",
            "Watch: dependency version may change",
        ]
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_string_value_passes(self, validator, valid_evidence):
        """String value passes."""
        valid_evidence["residual_risks"] = "None identified"
        result = validator.validate(valid_evidence)
        assert result.valid

    def test_empty_list_fails(self, validator, valid_evidence):
        """Empty list fails."""
        valid_evidence["residual_risks"] = []
        result = validator.validate(valid_evidence)
        assert not result.valid


class TestPerTaskValidationResult:
    """Test the PerTaskValidationResult data class."""

    def test_initial_state_is_valid(self):
        """Default result starts as valid with no errors."""
        result = PerTaskValidationResult()
        assert result.valid
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_makes_invalid(self):
        """Adding an error makes result invalid."""
        result = PerTaskValidationResult()
        result.add_field_result(
            FieldValidation(field_name="test", passed=False, message="Error")
        )
        assert not result.valid
        assert len(result.errors) == 1

    def test_add_warning_keeps_valid(self):
        """Adding a warning keeps result valid."""
        result = PerTaskValidationResult()
        result.add_field_result(
            FieldValidation(
                field_name="test", passed=False, message="Warning", severity="warning"
            )
        )
        # Warning severity does not invalidate the result
        assert result.valid
        assert len(result.warnings) == 1
        assert len(result.errors) == 0

    def test_add_passed_increments_counters(self):
        """Adding passed result increments counters."""
        result = PerTaskValidationResult()
        result.add_field_result(
            FieldValidation(field_name="f1", passed=True, message="OK")
        )
        assert result.total_fields_checked == 1
        assert result.fields_passed == 1
        assert result.fields_failed == 0

    def test_summary_includes_status(self):
        """Summary includes PASS/FAIL status."""
        result = PerTaskValidationResult()
        summary = result.summary()
        assert "PASS" in summary

    def test_summary_includes_fail(self):
        """Summary includes FAIL when invalid."""
        result = PerTaskValidationResult()
        result.add_field_result(
            FieldValidation(field_name="f1", passed=False, message="Bad field")
        )
        summary = result.summary()
        assert "FAIL" in summary
        assert "Bad field" in summary


class TestFieldValidation:
    """Test the FieldValidation data class."""

    def test_defaults(self):
        """Default values are set correctly."""
        fv = FieldValidation(field_name="test", passed=True, message="OK")
        assert fv.field_name == "test"
        assert fv.passed is True
        assert fv.message == "OK"
        assert fv.severity == "error"

    def test_custom_severity(self):
        """Custom severity is set correctly."""
        fv = FieldValidation(
            field_name="test", passed=False, message="Warn", severity="warning"
        )
        assert fv.severity == "warning"


class TestEvidenceValidationError:
    """Test the EvidenceValidationError exception."""

    def test_basic_message(self):
        """Exception has basic message."""
        err = EvidenceValidationError("test error")
        assert str(err) == "test error"
        assert err.field is None

    def test_with_field(self):
        """Exception can include field name."""
        err = EvidenceValidationError("missing field", field="commands_run")
        assert err.field == "commands_run"


class TestConvenienceFunction:
    """Test the validate_per_task_evidence convenience function."""

    def test_valid_evidence(self, valid_evidence):
        """Valid evidence passes via convenience function."""
        result = validate_per_task_evidence(valid_evidence)
        assert result.valid

    def test_invalid_evidence(self):
        """Invalid evidence fails via convenience function."""
        result = validate_per_task_evidence({})
        assert not result.valid

    def test_returns_per_task_result(self, valid_evidence):
        """Returns PerTaskValidationResult instance."""
        result = validate_per_task_evidence(valid_evidence)
        assert isinstance(result, PerTaskValidationResult)


class TestCustomRequiredFields:
    """Test validator with custom field configuration."""

    def test_custom_required_fields(self, valid_evidence):
        """Validator accepts custom required fields."""
        custom_validator = PerTaskEvidenceValidator(
            required_fields=["commands_run", "tests_run_with_results"],
        )
        # Only needs the 2 custom fields
        minimal_evidence = {
            "commands_run": ["pytest"],
            "tests_run_with_results": "10 passed, 0 failed",
        }
        result = custom_validator.validate(minimal_evidence)
        assert result.valid

    def test_custom_required_fields_missing(self, valid_evidence):
        """Custom validator fails when custom fields are missing."""
        custom_validator = PerTaskEvidenceValidator(
            required_fields=["custom_field"],
        )
        result = custom_validator.validate({})
        assert not result.valid
        assert any("custom_field" in e for e in result.errors)


class TestModuleConstants:
    """Test module-level constants are properly defined."""

    def test_required_fields_not_empty(self):
        """REQUIRED_FIELDS is not empty."""
        assert len(REQUIRED_FIELDS) == 5

    def test_required_fields_contains_all_expected(self):
        """REQUIRED_FIELDS contains all expected field names."""
        expected = {
            "commands_run",
            "tests_run_with_results",
            "logs_checked_with_findings",
            "acceptance_criteria_mapping",
            "residual_risks",
        }
        assert set(REQUIRED_FIELDS) == expected

    def test_list_fields_not_empty(self):
        """LIST_FIELDS is not empty."""
        assert len(LIST_FIELDS) > 0

    def test_dict_fields_not_empty(self):
        """DICT_FIELDS is not empty."""
        assert len(DICT_FIELDS) > 0

    def test_list_and_dict_fields_disjoint(self):
        """LIST_FIELDS and DICT_FIELDS are disjoint."""
        assert LIST_FIELDS.isdisjoint(DICT_FIELDS)


class TestIntegrationFullEvidence:
    """Integration tests with complete realistic evidence payloads."""

    def test_realistic_agent_report(self):
        """Full realistic agent completion report validates."""
        evidence = {
            "commands_run": [
                "pytest tests/test_validation/test_truth_verification.py -v",
                "ruff check scripts/validation/per_task_truth_verification.py",
            ],
            "tests_run_with_results": "42 passed, 0 failed, 2 skipped in 3.5s",
            "logs_checked_with_findings": [
                "Redis iterlog: SWARM-HARDEN-001 batch in progress",
                "Docker logs: chiseai-api healthy, no errors in last 24h",
            ],
            "acceptance_criteria_mapping": {
                "AC1": "All 5 required fields present and type-checked",
                "AC2": "Test results string parsed, pass/fail counts extracted",
                "AC3": "42/42 tests passing, 100% pass rate",
            },
            "residual_risks": [
                "Edge case: very long command strings not explicitly bounded",
                "Note: logs_checked field accepts any string/list, no schema enforcement",
            ],
        }
        result = validate_per_task_evidence(evidence)
        assert result.valid
        assert result.fields_passed == 5
        assert result.fields_failed == 0

    def test_minimal_passing_evidence(self):
        """Minimal but valid evidence passes."""
        evidence = {
            "commands_run": ["pytest"],
            "tests_run_with_results": "1 passed, 0 failed",
            "logs_checked_with_findings": "ok",
            "acceptance_criteria_mapping": {"AC1": "done"},
            "residual_risks": "none",
        }
        result = validate_per_task_evidence(evidence)
        assert result.valid

    def test_each_missing_field_identified(self):
        """Each missing field is individually identified."""
        evidence: dict[str, Any] = {}
        result = validate_per_task_evidence(evidence)
        assert not result.valid
        for field_name in REQUIRED_FIELDS:
            assert any(field_name in e for e in result.errors), (
                f"Missing error for field: {field_name}"
            )
