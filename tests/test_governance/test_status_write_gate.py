#!/usr/bin/env python3
"""
Comprehensive tests for status_write_gate module.

This test suite covers:
- Git SHA verification
- YAML validation
- EP-AUTO-GIT entry validation
- Integration with merlin_authority
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Create a mock redis_state module for testing
mock_redis_state = MagicMock()
sys.modules["redis_state"] = mock_redis_state

from scripts.governance.status_write_gate import (
    ValidationError,
    ValidationResult,
    check_authority,
    check_ep_auto_git_entries,
    extract_shas_from_yaml,
    format_validation_report,
    validate_status_write,
    validate_status_yaml,
    validate_yaml_structure,
    verify_git_sha,
)


class TestValidationError(unittest.TestCase):
    """Test the ValidationError dataclass."""

    def test_error_creation(self) -> None:
        """Test creating a validation error."""
        error = ValidationError(
            field="metadata.version", message="Version is required", severity="error"
        )

        self.assertEqual(error.field, "metadata.version")
        self.assertEqual(error.message, "Version is required")
        self.assertEqual(error.severity, "error")

    def test_warning_creation(self) -> None:
        """Test creating a validation warning."""
        warning = ValidationError(
            field="epics[0].description",
            message="Description is short",
            severity="warning",
        )

        self.assertEqual(warning.severity, "warning")


class TestValidationResult(unittest.TestCase):
    """Test the ValidationResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a validation result."""
        result = ValidationResult(valid=True)

        self.assertTrue(result.valid)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)

    def test_add_error(self) -> None:
        """Test adding an error to the result."""
        result = ValidationResult(valid=True)
        result.add_error("field", "error message")

        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].field, "field")
        self.assertEqual(result.errors[0].message, "error message")

    def test_add_warning(self) -> None:
        """Test adding a warning to the result."""
        result = ValidationResult(valid=True)
        result.add_warning("field", "warning message")

        self.assertTrue(result.valid)  # Warnings don't invalidate
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].severity, "warning")


class TestVerifyGitSha(unittest.TestCase):
    """Test git SHA verification."""

    @patch("subprocess.run")
    def test_verify_valid_sha(self, mock_run) -> None:
        """Test verifying a valid SHA."""
        mock_run.return_value = MagicMock(returncode=0, stdout="commit\n", stderr="")

        result = verify_git_sha("19e9e62")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_verify_invalid_sha(self, mock_run) -> None:
        """Test verifying an invalid SHA."""
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: Not a valid object name"
        )

        result = verify_git_sha("0000000")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_verify_full_sha(self, mock_run) -> None:
        """Test verifying a full 40-character SHA."""
        mock_run.return_value = MagicMock(returncode=0, stdout="commit\n", stderr="")

        result = verify_git_sha("19e9e62f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d")
        self.assertTrue(result)

    def test_verify_empty_sha(self) -> None:
        """Test verifying empty SHA."""
        result = verify_git_sha("")
        self.assertFalse(result)

    def test_verify_none_sha(self) -> None:
        """Test verifying None SHA."""
        result = verify_git_sha(None)  # type: ignore
        self.assertFalse(result)

    def test_verify_invalid_format(self) -> None:
        """Test verifying SHA with invalid format."""
        # Too short
        result = verify_git_sha("abc")
        self.assertFalse(result)

        # Invalid characters
        result = verify_git_sha("ghijklm")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_verify_with_repo_path(self, mock_run) -> None:
        """Test verifying SHA with custom repo path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="commit\n", stderr="")

        result = verify_git_sha("19e9e62", "/path/to/repo")
        self.assertTrue(result)

        # Verify the command was called with -C flag
        call_args = mock_run.call_args[0][0]
        self.assertIn("-C", call_args)
        self.assertIn("/path/to/repo", call_args)

    @patch("subprocess.run")
    def test_verify_timeout(self, mock_run) -> None:
        """Test handling of timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=10)

        result = verify_git_sha("19e9e62")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_verify_file_not_found(self, mock_run) -> None:
        """Test handling when git is not found."""
        mock_run.side_effect = FileNotFoundError("git not found")

        result = verify_git_sha("19e9e62")
        self.assertFalse(result)


class TestExtractShasFromYaml(unittest.TestCase):
    """Test SHA extraction from YAML data."""

    def test_extract_from_dict(self) -> None:
        """Test extracting SHAs from a dictionary."""
        data = {"merge_commit_sha": "19e9e62", "other_field": "not-a-sha"}

        shas = extract_shas_from_yaml(data)

        self.assertEqual(len(shas), 1)
        self.assertEqual(shas[0], ("merge_commit_sha", "19e9e62"))

    def test_extract_from_nested_dict(self) -> None:
        """Test extracting SHAs from nested dictionaries."""
        data = {"metadata": {"recent_changes": [{"merge_commit_sha": "abc1234"}]}}

        shas = extract_shas_from_yaml(data)

        self.assertEqual(len(shas), 1)
        self.assertEqual(shas[0][1], "abc1234")

    def test_extract_from_list(self) -> None:
        """Test extracting SHAs from lists."""
        data = {"commits": [{"sha": "abc1234"}, {"sha": "def5678"}]}

        shas = extract_shas_from_yaml(data)

        self.assertEqual(len(shas), 2)
        self.assertEqual(shas[0][1], "abc1234")
        self.assertEqual(shas[1][1], "def5678")

    def test_extract_no_shas(self) -> None:
        """Test extracting when no SHAs are present."""
        data = {"field1": "value1", "field2": 123}

        shas = extract_shas_from_yaml(data)

        self.assertEqual(len(shas), 0)

    def test_extract_invalid_sha_format(self) -> None:
        """Test that invalid SHA formats are not extracted."""
        data = {
            "sha_field": "not-a-valid-sha",
            "short_sha": "abc",  # Too short
        }

        shas = extract_shas_from_yaml(data)

        self.assertEqual(len(shas), 0)


class TestValidateYamlStructure(unittest.TestCase):
    """Test YAML structure validation."""

    def test_valid_structure(self) -> None:
        """Test valid YAML structure."""
        data = {"metadata": {"version": "1.0", "recent_changes": []}, "epics": []}

        errors = validate_yaml_structure(data)

        self.assertEqual(len(errors), 0)

    def test_missing_metadata(self) -> None:
        """Test validation when metadata is missing."""
        data = {"epics": []}

        errors = validate_yaml_structure(data)

        self.assertEqual(len(errors), 1)
        self.assertIn("metadata", errors[0].message)

    def test_missing_epics(self) -> None:
        """Test validation when epics is missing."""
        data = {"metadata": {}}

        errors = validate_yaml_structure(data)

        self.assertEqual(len(errors), 1)
        self.assertIn("epics", errors[0].message)

    def test_non_dict_root(self) -> None:
        """Test validation when root is not a dictionary."""
        data = ["not", "a", "dict"]

        errors = validate_yaml_structure(data)

        self.assertEqual(len(errors), 1)
        self.assertIn("dictionary", errors[0].message)

    def test_invalid_epics_type(self) -> None:
        """Test validation when epics is not a list."""
        data = {"metadata": {}, "epics": "not-a-list"}

        errors = validate_yaml_structure(data)

        epic_errors = [e for e in errors if "epics" in e.field]
        self.assertEqual(len(epic_errors), 1)

    def test_epic_missing_id(self) -> None:
        """Test validation when epic is missing id field."""
        data = {"metadata": {}, "epics": [{"name": "Test Epic"}]}

        errors = validate_yaml_structure(data)

        epic_errors = [e for e in errors if "epics" in e.field]
        self.assertTrue(len(epic_errors) > 0)


class TestCheckEpAutoGitEntries(unittest.TestCase):
    """Test EP-AUTO-GIT entry validation."""

    def test_valid_ep_auto_git_epic(self) -> None:
        """Test valid EP-AUTO-GIT epic entry."""
        data = {
            "epics": [
                {
                    "id": "EP-AUTO-GIT-001",
                    "status": "completed",
                    "story_count": 8,
                    "story_points": 47,
                    "story_ids": ["ST-AUTO-001"],
                    "completion_date": "2026-02-26",
                }
            ]
        }

        errors = check_ep_auto_git_entries(data)

        self.assertEqual(len(errors), 0)

    def test_missing_required_fields(self) -> None:
        """Test validation when required fields are missing."""
        data = {
            "epics": [
                {
                    "id": "EP-AUTO-GIT-001",
                    # Missing status, story_count, story_points
                }
            ]
        }

        errors = check_ep_auto_git_entries(data)

        self.assertTrue(len(errors) >= 3)  # At least 3 required fields

    def test_invalid_story_ids_type(self) -> None:
        """Test validation when story_ids is not a list."""
        data = {
            "epics": [
                {
                    "id": "EP-AUTO-GIT-001",
                    "status": "completed",
                    "story_count": 8,
                    "story_points": 47,
                    "story_ids": "not-a-list",
                }
            ]
        }

        errors = check_ep_auto_git_entries(data)

        story_id_errors = [e for e in errors if "story_ids" in e.field]
        self.assertEqual(len(story_id_errors), 1)

    def test_completed_epic_missing_completion_date(self) -> None:
        """Test warning when completed epic lacks completion_date."""
        data = {
            "epics": [
                {
                    "id": "EP-AUTO-GIT-001",
                    "status": "completed",
                    "story_count": 8,
                    "story_points": 47,
                }
            ]
        }

        errors = check_ep_auto_git_entries(data)

        completion_errors = [e for e in errors if "completion_date" in e.field]
        self.assertEqual(len(completion_errors), 1)
        self.assertEqual(completion_errors[0].severity, "warning")

    def test_non_ep_auto_git_epic_ignored(self) -> None:
        """Test that non-EP-AUTO-GIT epics are ignored."""
        data = {
            "epics": [
                {
                    "id": "EP-OTHER-001",
                    # Missing fields that would be required for EP-AUTO-GIT
                }
            ]
        }

        errors = check_ep_auto_git_entries(data)

        # Should have no EP-AUTO-GIT specific errors
        self.assertEqual(len(errors), 0)

    def test_recent_changes_validation(self) -> None:
        """Test validation of recent_changes entries."""
        data = {
            "metadata": {
                "recent_changes": [
                    {
                        "epic_id": "EP-AUTO-GIT-001",
                        "timestamp": "2026-02-26T00:00:00Z",
                        # Missing actor (should be warning)
                    }
                ]
            },
            "epics": [],
        }

        errors = check_ep_auto_git_entries(data)

        actor_errors = [e for e in errors if "actor" in e.field]
        self.assertEqual(len(actor_errors), 1)
        self.assertEqual(actor_errors[0].severity, "warning")

    def test_recent_changes_missing_timestamp(self) -> None:
        """Test error when recent_changes entry lacks timestamp."""
        data = {
            "metadata": {
                "recent_changes": [
                    {
                        "epic_id": "EP-AUTO-GIT-001",
                        "actor": "jarvis",
                        # Missing timestamp (should be error)
                    }
                ]
            },
            "epics": [],
        }

        errors = check_ep_auto_git_entries(data)

        timestamp_errors = [e for e in errors if "timestamp" in e.field]
        self.assertEqual(len(timestamp_errors), 1)
        self.assertEqual(timestamp_errors[0].severity, "error")


class TestValidateStatusYaml(unittest.TestCase):
    """Test the validate_status_yaml function."""

    def setUp(self) -> None:
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.yaml_file = os.path.join(self.temp_dir, "test_status.yaml")

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_not_found(self) -> None:
        """Test validation when file doesn't exist."""
        result = validate_status_yaml("/nonexistent/file.yaml")

        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("not found", result.errors[0].message)

    def test_invalid_yaml_syntax(self) -> None:
        """Test validation of invalid YAML syntax."""
        with open(self.yaml_file, "w") as f:
            f.write("invalid: yaml: content: [")

        result = validate_status_yaml(self.yaml_file)

        self.assertFalse(result.valid)
        self.assertFalse(result.yaml_valid)

    def test_valid_yaml_no_sha_verification(self) -> None:
        """Test validation of valid YAML without SHA verification."""
        data = {"metadata": {"version": "1.0", "recent_changes": []}, "epics": []}

        with open(self.yaml_file, "w") as f:
            yaml.dump(data, f)

        result = validate_status_yaml(self.yaml_file, verify_shas=False)

        self.assertTrue(result.valid)
        self.assertTrue(result.yaml_valid)

    @patch("scripts.governance.status_write_gate.verify_git_sha")
    def test_sha_verification_success(self, mock_verify) -> None:
        """Test successful SHA verification."""
        mock_verify.return_value = True

        data = {
            "metadata": {"recent_changes": [{"merge_commit_sha": "19e9e62"}]},
            "epics": [],
        }

        with open(self.yaml_file, "w") as f:
            yaml.dump(data, f)

        result = validate_status_yaml(self.yaml_file, verify_shas=True)

        self.assertTrue(result.valid)
        self.assertIn("19e9e62", result.git_shas_verified)

    @patch("scripts.governance.status_write_gate.verify_git_sha")
    def test_sha_verification_failure(self, mock_verify) -> None:
        """Test failed SHA verification."""
        mock_verify.return_value = False

        data = {
            "metadata": {"recent_changes": [{"merge_commit_sha": "0000000"}]},
            "epics": [],
        }

        with open(self.yaml_file, "w") as f:
            yaml.dump(data, f)

        result = validate_status_yaml(self.yaml_file, verify_shas=True)

        self.assertFalse(result.valid)
        self.assertIn("0000000", result.git_shas_failed)


class TestCheckAuthority(unittest.TestCase):
    """Test the check_authority function."""

    @patch("scripts.governance.merlin_authority.check_ep_auto_git_authority")
    def test_check_authority_success(self, mock_check) -> None:
        """Test successful authority check."""
        mock_result = MagicMock()
        mock_result.authorized = True
        mock_result.reason = "Agent is merlin"
        mock_check.return_value = mock_result

        authorized, message = check_authority("merlin")

        self.assertTrue(authorized)
        self.assertEqual(message, "Agent is merlin")

    @patch("scripts.governance.merlin_authority.check_ep_auto_git_authority")
    def test_check_authority_failure(self, mock_check) -> None:
        """Test failed authority check."""
        mock_result = MagicMock()
        mock_result.authorized = False
        mock_result.reason = "Agent not authorized"
        mock_check.return_value = mock_result

        authorized, message = check_authority("worker-1")

        self.assertFalse(authorized)
        self.assertEqual(message, "Agent not authorized")

    @patch.dict(os.environ, {"AGENT_NAME": "merlin"})
    def test_check_authority_import_error_fallback_merlin(self) -> None:
        """Test fallback when merlin_authority import fails for merlin."""
        with patch.dict("sys.modules", {"scripts.governance.merlin_authority": None}):
            authorized, message = check_authority()

            self.assertTrue(authorized)
            self.assertIn("merlin", message)
            self.assertIn("fallback", message)

    @patch.dict(os.environ, {"AGENT_NAME": "worker-1"})
    def test_check_authority_import_error_fallback_non_merlin(self) -> None:
        """Test fallback when merlin_authority import fails for non-merlin."""
        with patch.dict("sys.modules", {"scripts.governance.merlin_authority": None}):
            authorized, message = check_authority()

            self.assertFalse(authorized)
            self.assertIn("worker-1", message)
            self.assertIn("fallback", message)

    @patch("scripts.governance.merlin_authority.check_ep_auto_git_authority")
    def test_check_authority_exception(self, mock_check) -> None:
        """Test handling of exceptions during authority check."""
        mock_check.side_effect = Exception("Unexpected error")

        authorized, message = check_authority("merlin")

        # Should fail-secure (deny access)
        self.assertFalse(authorized)
        self.assertIn("failed", message)


class TestValidateStatusWrite(unittest.TestCase):
    """Test the validate_status_write function."""

    def setUp(self) -> None:
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.yaml_file = os.path.join(self.temp_dir, "test_status.yaml")

        # Create a valid YAML file
        data = {"metadata": {"version": "1.0", "recent_changes": []}, "epics": []}
        with open(self.yaml_file, "w") as f:
            yaml.dump(data, f)

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("scripts.governance.status_write_gate.check_authority")
    def test_full_validation_with_authority(self, mock_check) -> None:
        """Test full validation with authority check."""
        mock_check.return_value = (True, "Authorized")

        result = validate_status_write(
            yaml_file=self.yaml_file, agent="merlin", verify_shas=False
        )

        self.assertTrue(result.valid)
        self.assertTrue(result.authority_valid)
        self.assertTrue(result.yaml_valid)

    @patch("scripts.governance.status_write_gate.check_authority")
    def test_validation_fails_without_authority(self, mock_check) -> None:
        """Test validation fails when authority check fails."""
        mock_check.return_value = (False, "Not authorized")

        result = validate_status_write(
            yaml_file=self.yaml_file, agent="worker-1", verify_shas=False
        )

        self.assertFalse(result.valid)
        self.assertFalse(result.authority_valid)

    def test_validation_without_authority_check(self) -> None:
        """Test validation when authority check is disabled."""
        result = validate_status_write(
            yaml_file=self.yaml_file, require_authority=False, verify_shas=False
        )

        self.assertTrue(result.valid)
        self.assertTrue(result.authority_valid)  # Should be True when not required


class TestFormatValidationReport(unittest.TestCase):
    """Test the format_validation_report function."""

    def test_valid_result(self) -> None:
        """Test formatting a valid result."""
        result = ValidationResult(valid=True)
        result.yaml_valid = True
        result.authority_valid = True

        report = format_validation_report(result)

        self.assertIn("PASSED", report)
        self.assertIn("VALID", report)

    def test_invalid_result(self) -> None:
        """Test formatting an invalid result."""
        result = ValidationResult(valid=False)
        result.yaml_valid = False
        result.authority_valid = False
        result.add_error("field", "error message")

        report = format_validation_report(result)

        self.assertIn("FAILED", report)
        self.assertIn("error message", report)

    def test_verbose_output(self) -> None:
        """Test verbose report formatting."""
        result = ValidationResult(valid=True)
        result.yaml_valid = True
        result.authority_valid = True
        result.git_shas_verified = ["abc1234", "def5678"]
        result.add_warning("field", "warning message")

        report = format_validation_report(result, verbose=True)

        self.assertIn("abc1234", report)
        self.assertIn("def5678", report)
        self.assertIn("warning message", report)

    def test_sha_failure_reporting(self) -> None:
        """Test reporting of SHA verification failures."""
        result = ValidationResult(valid=False)
        result.git_shas_failed = ["0000000"]
        result.add_error("sha", "SHA not found")

        report = format_validation_report(result)

        self.assertIn("0000000", report)
        self.assertIn("failed", report.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
