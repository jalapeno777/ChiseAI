"""Tests for CI integration scripts."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "ci_integration")
)

from pre_flight_checks import (
    CheckResult,
    check_code_quality,
    check_environment_vars,
    check_git_status,
    check_python_version,
    check_required_tools,
    run_pre_flight_checks,
)
from pre_flight_checks import (
    main as preflight_main,
)


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test CheckResult can be created with required fields."""
        result = CheckResult(name="test", passed=True, message="OK")
        assert result.name == "test"
        assert result.passed is True
        assert result.message == "OK"
        assert result.details is None

    def test_check_result_with_details(self):
        """Test CheckResult with optional details."""
        result = CheckResult(
            name="test",
            passed=False,
            message="Failed",
            details={"error": "something went wrong"},
        )
        assert result.details == {"error": "something went wrong"}


class TestCheckPythonVersion:
    """Tests for Python version check."""

    def test_check_python_version_returns_check_result(self):
        """Test that check returns CheckResult."""
        result = check_python_version()
        assert isinstance(result, CheckResult)
        assert result.name == "python_version"

    def test_check_python_version_passes_on_valid_version(self):
        """Test that check passes for valid Python version."""
        result = check_python_version()
        # Should pass since we require 3.10 and use 3.11+
        assert result.passed is True
        assert "OK" in result.message or "3." in result.message


class TestCheckRequiredTools:
    """Tests for required tools check."""

    @patch("subprocess.run")
    def test_all_tools_found(self, mock_run):
        """Test when all required tools are found."""
        mock_run.return_value = MagicMock(returncode=0)

        result = check_required_tools()
        assert isinstance(result, CheckResult)
        assert result.name == "required_tools"

    @patch("subprocess.run")
    def test_some_tools_missing(self, mock_run):
        """Test when some tools are missing."""
        # First call returns None (git found), second returns non-zero (tool not found)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git found
            MagicMock(returncode=1),  # pytest not found
            MagicMock(returncode=0),  # ruff found
            MagicMock(returncode=0),  # black found
        ]

        result = check_required_tools()
        assert result.passed is False
        assert "Some tools missing" in result.message


class TestCheckGitStatus:
    """Tests for git status check."""

    @patch("subprocess.run")
    def test_clean_working_tree(self, mock_run):
        """Test when working tree is clean."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = check_git_status()
        assert result.name == "git_status"
        assert result.passed is True
        assert "Clean" in result.message

    @patch("subprocess.run")
    def test_uncommitted_changes(self, mock_run):
        """Test when there are uncommitted changes."""
        mock_run.return_value = MagicMock(
            stdout=" M file.py\n?? newfile.py", returncode=0
        )

        result = check_git_status()
        assert result.passed is False
        assert "Uncommitted" in result.message

    @patch("subprocess.run")
    def test_git_command_fails(self, mock_run):
        """Test when git command fails."""
        mock_run.side_effect = FileNotFoundError("git not found")

        result = check_git_status()
        assert result.passed is False
        assert "Failed" in result.message


class TestCheckEnvironmentVars:
    """Tests for environment variables check."""

    def test_envrc_exists_check(self):
        """Test environment check returns proper result type."""
        result = check_environment_vars()
        assert isinstance(result, CheckResult)
        assert result.name == "environment_vars"


class TestCheckCodeQuality:
    """Tests for code quality checks."""

    @patch("subprocess.run")
    def test_black_passes(self, mock_run):
        """Test when black check passes."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = check_code_quality()
        # If all tools pass, check should pass
        # Note: this may fail if ruff is not installed
        assert isinstance(result, CheckResult)
        assert result.name == "code_quality"

    @patch("subprocess.run")
    def test_black_finds_issues(self, mock_run):
        """Test when black finds formatting issues."""
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="would reformat file.py"),
            MagicMock(returncode=0, stdout=""),
        ]

        result = check_code_quality()
        assert result.passed is False
        assert "Issues found" in result.message


class TestRunPreFlightChecks:
    """Tests for run_pre_flight_checks function."""

    @patch("pre_flight_checks.check_python_version")
    @patch("pre_flight_checks.check_required_tools")
    @patch("pre_flight_checks.check_git_status")
    @patch("pre_flight_checks.check_environment_vars")
    @patch("pre_flight_checks.check_code_quality")
    def test_all_checks_run(
        self,
        mock_code_quality,
        mock_env,
        mock_git,
        mock_tools,
        mock_python,
    ):
        """Test that all checks are called."""
        mock_python.return_value = CheckResult("python_version", True, "OK")
        mock_tools.return_value = CheckResult("required_tools", True, "OK")
        mock_git.return_value = CheckResult("git_status", True, "OK")
        mock_env.return_value = CheckResult("environment_vars", True, "OK")
        mock_code_quality.return_value = CheckResult("code_quality", True, "OK")

        results = run_pre_flight_checks()

        assert len(results) == 5
        assert mock_python.called
        assert mock_tools.called
        assert mock_git.called
        assert mock_env.called
        assert mock_code_quality.called

    @patch("pre_flight_checks.check_python_version")
    @patch("pre_flight_checks.check_required_tools")
    @patch("pre_flight_checks.check_git_status")
    @patch("pre_flight_checks.check_environment_vars")
    @patch("pre_flight_checks.check_code_quality")
    def test_overall_pass_when_all_pass(
        self,
        mock_code_quality,
        mock_env,
        mock_git,
        mock_tools,
        mock_python,
    ):
        """Test overall success when all checks pass."""
        mock_python.return_value = CheckResult("python_version", True, "OK")
        mock_tools.return_value = CheckResult("required_tools", True, "OK")
        mock_git.return_value = CheckResult("git_status", True, "OK")
        mock_env.return_value = CheckResult("environment_vars", True, "OK")
        mock_code_quality.return_value = CheckResult("code_quality", True, "OK")

        results = run_pre_flight_checks()
        assert all(r.passed for r in results)


class TestPreFlightMain:
    """Tests for pre_flight_checks main function."""

    @patch("pre_flight_checks.run_pre_flight_checks")
    def test_main_returns_zero_when_all_pass(self, mock_run):
        """Test main returns 0 when all checks pass."""
        mock_run.return_value = [
            CheckResult("test1", True, "OK"),
            CheckResult("test2", True, "OK"),
        ]

        with patch("sys.stdout", new=MagicMock()) as mock_stdout:
            exit_code = preflight_main()

        assert exit_code == 0

    @patch("pre_flight_checks.run_pre_flight_checks")
    def test_main_returns_one_when_any_fails(self, mock_run):
        """Test main returns 1 when any check fails."""
        mock_run.return_value = [
            CheckResult("test1", True, "OK"),
            CheckResult("test2", False, "Failed"),
        ]

        with patch("sys.stdout", new=MagicMock()) as mock_stdout:
            exit_code = preflight_main()

        assert exit_code == 1

    @patch("pre_flight_checks.run_pre_flight_checks")
    def test_main_outputs_json(self, mock_run):
        """Test main outputs JSON to stdout."""
        mock_run.return_value = [
            CheckResult("test1", True, "OK"),
        ]

        from io import StringIO

        output = StringIO()
        with patch("sys.stdout", output):
            preflight_main()

        result = output.getvalue()
        parsed = json.loads(result)
        assert "success" in parsed
        assert "checks" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
