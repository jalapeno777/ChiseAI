"""Test structured issue enforcement in iterlog validation.

This test suite verifies that the validate_iterloop_compliance.py script
correctly validates structured issues sections in iterlog files.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Path to the validator script (use absolute path for subprocess calls with different cwd)
VALIDATOR_SCRIPT = (
    Path(__file__).parent.parent / "scripts" / "validate_iterloop_compliance.py"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "iterlog"


class TestIterloopStructuredIssues:
    """Integration tests for structured issue validation in iterlogs."""

    def test_validation_passes_with_structured_issues(self, tmp_path: Path):
        """Valid iterlog with complete structured issues should pass."""
        # Create a temporary iterlog file with valid structured issues
        result = self._run_validator_on_fixture(tmp_path, "valid_with_issues.md")

        # Should pass (exit code 0)
        assert result.returncode == 0, (
            f"Expected validation to pass for valid_with_issues.md.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "✅ Iteration-loop compliance checks passed" in result.stdout

    def test_validation_passes_with_empty_issues(self, tmp_path: Path):
        """Valid iterlog with issues: [] sentinel should pass."""
        result = self._run_validator_on_fixture(tmp_path, "valid_empty_issues.md")

        # Should pass (exit code 0)
        assert result.returncode == 0, (
            f"Expected validation to pass for valid_empty_issues.md.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "✅ Iteration-loop compliance checks passed" in result.stdout

    def test_validation_fails_missing_structured_issues(self, tmp_path: Path):
        """Completed iterlog without structured issues section should fail."""
        result = self._run_validator_on_fixture(tmp_path, "invalid_missing_section.md")

        # Should fail (exit code 1) because completed status requires structured issues
        assert result.returncode == 1, (
            f"Expected validation to fail for invalid_missing_section.md.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "missing '## Structured Issues' section" in result.stderr

    def test_validation_fails_missing_required_field(self, tmp_path: Path):
        """Issue missing required field should fail validation."""
        result = self._run_validator_on_fixture(tmp_path, "invalid_missing_field.md")

        # Should fail (exit code 1) because issue is missing recurrence_hint field
        assert result.returncode == 1, (
            f"Expected validation to fail for invalid_missing_field.md.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "missing required fields" in result.stderr
        assert "recurrence_hint" in result.stderr

    def _run_validator_on_fixture(
        self, tmp_path: Path, fixture_name: str
    ) -> subprocess.CompletedProcess:
        """Run the validator against a specific fixture file in an isolated temp directory.

        We create an isolated tempmemories directory to avoid interference from
        existing iterlog files in the main docs/tempmemories directory.
        """
        fixture_path = FIXTURES_DIR / fixture_name

        # Create isolated tempmemories directory
        tempmemories_dir = tmp_path / "docs" / "tempmemories"
        tempmemories_dir.mkdir(parents=True)
        temp_iterlog_path = tempmemories_dir / f"iterlog-{fixture_name}"

        # Copy fixture to isolated tempmemories directory
        temp_iterlog_path.write_text(fixture_path.read_text())

        # Run the validator with the isolated directory
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_SCRIPT),
                "--require-structured-issues",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        return result


class TestIterloopIssueSchemaValidation:
    """Tests for individual issue schema validation."""

    def test_invalid_impact_area_fails(self, tmp_path: Path):
        """Issue with invalid impact_area should fail validation."""
        invalid_iterlog = """---
story_id: TEST-INVALID-IMPACT
story_title: Test Invalid Impact Area
phase: implementation
status: completed
started_at: "2026-03-01T00:00:00Z"
completed_at: "2026-03-01T23:59:59Z"
---

## Incidents
None

## Scope Ownership
Scope: tests/

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test failure"
    fix_applied: "fixed test"
    time_lost_minutes: 10
    recurrence_hint: "check tests before committing"
    impact_area: "invalid_area"
    resolved: true
"""
        result = self._run_validator_with_content(tmp_path, invalid_iterlog)

        assert result.returncode == 1
        assert "impact_area must be one of" in result.stderr

    def test_non_integer_time_lost_fails(self, tmp_path: Path):
        """Issue with non-integer time_lost_minutes should fail."""
        invalid_iterlog = """---
story_id: TEST-INVALID-TIME
story_title: Test Invalid Time Format
phase: implementation
status: completed
started_at: "2026-03-01T00:00:00Z"
completed_at: "2026-03-01T23:59:59Z"
---

## Incidents
None

## Scope Ownership
Scope: tests/

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test failure"
    fix_applied: "fixed test"
    time_lost_minutes: "thirty"
    recurrence_hint: "check tests before committing"
    impact_area: "efficiency"
    resolved: true
"""
        result = self._run_validator_with_content(tmp_path, invalid_iterlog)

        assert result.returncode == 1
        assert "time_lost_minutes must be an integer" in result.stderr

    def test_non_boolean_resolved_fails(self, tmp_path: Path):
        """Issue with non-boolean resolved field should fail."""
        invalid_iterlog = """---
story_id: TEST-INVALID-RESOLVED
story_title: Test Invalid Resolved Format
phase: implementation
status: completed
started_at: "2026-03-01T00:00:00Z"
completed_at: "2026-03-01T23:59:59Z"
---

## Incidents
None

## Scope Ownership
Scope: tests/

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test failure"
    fix_applied: "fixed test"
    time_lost_minutes: 10
    recurrence_hint: "check tests before committing"
    impact_area: "efficiency"
    resolved: "yes"
"""
        result = self._run_validator_with_content(tmp_path, invalid_iterlog)

        assert result.returncode == 1
        assert "resolved must be a boolean" in result.stderr

    def _run_validator_with_content(
        self, tmp_path: Path, content: str
    ) -> subprocess.CompletedProcess:
        """Run validator with custom iterlog content in an isolated temp directory."""
        # Create isolated tempmemories directory
        tempmemories_dir = tmp_path / "docs" / "tempmemories"
        tempmemories_dir.mkdir(parents=True)
        temp_iterlog_path = tempmemories_dir / "iterlog-test-temp.md"
        temp_iterlog_path.write_text(content)

        # Run the validator with the isolated directory
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_SCRIPT),
                "--require-structured-issues",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        return result


class TestIterlogValidatorCommandLine:
    """Tests for validator command-line interface."""

    def test_validator_help(self):
        """Validator should display help information."""
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT), "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--require-structured-issues" in result.stdout
        assert "--story-id" in result.stdout
        assert "--fail-on-warn" in result.stdout

    def test_validator_no_iterlogs_warning(self, tmp_path: Path):
        """Validator should warn when no iterlog files found."""
        # Create an isolated temp directory with no iterlog files
        tempmemories_dir = tmp_path / "docs" / "tempmemories"
        tempmemories_dir.mkdir(parents=True)

        result = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        # Should pass but with warning
        assert result.returncode == 0
        assert "No iterlog files found" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
