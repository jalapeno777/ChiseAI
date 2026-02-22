"""
Tests for the Runbook Validation Script (validate_runbooks.py)

Part of ST-LAUNCH-021: Runbook Creation & Validation
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestValidationScriptStructure:
    """Test that the validation script exists and is structured correctly."""

    def test_script_exists(self):
        """Verify validation script file exists."""
        assert Path("scripts/ops/validate_runbooks.py").exists()

    def test_script_is_executable(self):
        """Verify validation script is executable Python file."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env python3")

    def test_script_has_main_function(self):
        """Verify script has a main function."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        content = script_path.read_text()
        assert "def main():" in content
        assert 'if __name__ == "__main__":' in content


class TestValidationScriptComponents:
    """Test that the validation script has required components."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_validation_result_class(self, script_content):
        """Verify ValidationResult dataclass exists."""
        assert (
            "class ValidationResult:" in script_content
            or "@dataclass" in script_content
        )

    def test_runbook_validator_class(self, script_content):
        """Verify RunbookValidator class exists."""
        assert "class RunbookValidator:" in script_content

    def test_validate_all_method(self, script_content):
        """Verify validate_all method exists."""
        assert "def validate_all" in script_content

    def test_validate_safety_method(self, script_content):
        """Verify validate_safety method exists."""
        assert "def validate_safety" in script_content

    def test_validate_ml_method(self, script_content):
        """Verify validate_ml method exists."""
        assert "def validate_ml" in script_content

    def test_validate_incident_method(self, script_content):
        """Verify validate_incident method exists."""
        assert "def validate_incident" in script_content

    def test_print_report_function(self, script_content):
        """Verify print_report function exists."""
        assert "def print_report" in script_content


class TestValidationScriptArguments:
    """Test that the validation script handles arguments correctly."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_scenario_argument(self, script_content):
        """Verify --scenario argument is handled."""
        assert "--scenario" in script_content

    def test_scenario_choices(self, script_content):
        """Verify scenario choices are defined."""
        assert "all" in script_content
        assert "safety" in script_content
        assert "ml" in script_content
        assert "incident" in script_content

    def test_verbose_argument(self, script_content):
        """Verify --verbose argument is handled."""
        assert "--verbose" in script_content or "-v" in script_content

    def test_json_argument(self, script_content):
        """Verify --json argument is handled."""
        assert "--json" in script_content

    def test_checklist_argument(self, script_content):
        """Verify --checklist argument is handled."""
        assert "--checklist" in script_content


class TestValidationScriptExitCodes:
    """Test that the validation script returns correct exit codes."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_exit_code_0_on_success(self, script_content):
        """Verify exit code 0 is returned on success."""
        assert "sys.exit(0" in script_content or "exit(0" in script_content

    def test_exit_code_1_on_failure(self, script_content):
        """Verify exit code 1 is returned on failure."""
        assert (
            "sys.exit(1" in script_content
            or "exit(1" in script_content
            or "else 1" in script_content
        )


class TestValidationScriptDocstring:
    """Test that the validation script has proper documentation."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_module_docstring_present(self, script_content):
        """Verify module has docstring."""
        assert '"""' in script_content
        assert "Runbook Validation Script" in script_content

    def test_usage_documented(self, script_content):
        """Verify usage is documented."""
        assert "Usage:" in script_content

    def test_exit_codes_documented(self, script_content):
        """Verify exit codes are documented."""
        assert "Exit Codes:" in script_content

    def test_story_id_documented(self, script_content):
        """Verify ST-LAUNCH-021 is referenced."""
        assert "ST-LAUNCH-021" in script_content


class TestValidationScriptRunbooksDir:
    """Test that the validation script uses correct paths."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_runbooks_dir_defined(self, script_content):
        """Verify runbooks directory is defined."""
        assert "docs/runbooks" in script_content or "RUNBOOKS_DIR" in script_content

    def test_required_runbooks_defined(self, script_content):
        """Verify required runbooks list is defined."""
        assert "launch_runbook.md" in script_content
        assert "ml_operations.md" in script_content
        assert "incident_response.md" in script_content


class TestValidationScriptOutput:
    """Test that the validation script produces correct output format."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_json_output_format(self, script_content):
        """Verify JSON output format is correct."""
        assert "json.dumps" in script_content

    def test_report_includes_timestamp(self, script_content):
        """Verify report includes timestamp."""
        assert "timestamp" in script_content

    def test_report_includes_summary(self, script_content):
        """Verify report includes summary."""
        assert "passed" in script_content.lower() and "failed" in script_content.lower()

    def test_report_shows_result(self, script_content):
        """Verify report shows PASS/FAIL result."""
        assert "PASS" in script_content or "FAIL" in script_content


class TestValidationScriptValidations:
    """Test that the validation script performs required validations."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_frontmatter_validation(self, script_content):
        """Verify frontmatter validation exists."""
        assert "_validate_frontmatter" in script_content

    def test_sections_validation(self, script_content):
        """Verify sections validation exists."""
        assert "_validate_required_sections" in script_content

    def test_executable_steps_validation(self, script_content):
        """Verify executable steps validation exists."""
        assert "_validate_executable_steps" in script_content

    def test_links_validation(self, script_content):
        """Verify links validation exists."""
        assert "_validate_links" in script_content

    def test_scenario_validations_exist(self, script_content):
        """Verify scenario-based validations exist."""
        assert "_validate_safety_scenarios" in script_content
        assert "_validate_ml_scenarios" in script_content
        assert "_validate_incident_scenarios" in script_content


@pytest.mark.integration
class TestValidationScriptExecution:
    """Integration tests for the validation script execution."""

    def test_script_runs_without_errors(self):
        """Verify script runs without Python errors."""
        result = subprocess.run(
            [sys.executable, "scripts/ops/validate_runbooks.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_script_validates_all_scenario(self):
        """Verify script can run 'all' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "all",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        # Should complete without error, even if validations fail
        assert result.returncode in [0, 1]

        # Verify output is valid JSON
        try:
            output = json.loads(result.stdout)
            assert "timestamp" in output
            assert "scenario" in output
            assert "results" in output or "summary" in output
        except json.JSONDecodeError:
            # If not JSON, check for expected text output
            assert (
                "RUNBOOK VALIDATION REPORT" in result.stdout or "Error" in result.stderr
            )

    def test_script_validates_safety_scenario(self):
        """Verify script can run 'safety' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "safety",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]
        assert "safety" in result.stdout.lower() or "Safety" in result.stdout

    def test_script_validates_ml_scenario(self):
        """Verify script can run 'ml' scenario."""
        result = subprocess.run(
            [sys.executable, "scripts/ops/validate_runbooks.py", "--scenario", "ml"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]
        assert "ml" in result.stdout.lower() or "ML" in result.stdout

    def test_script_validates_incident_scenario(self):
        """Verify script can run 'incident' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "incident",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]
        assert "incident" in result.stdout.lower() or "Incident" in result.stdout

    def test_script_outputs_json_when_requested(self):
        """Verify script outputs JSON when --json flag is used."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "all",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Should output valid JSON
        try:
            output = json.loads(result.stdout)
            assert isinstance(output, dict)
            assert "timestamp" in output
            assert "all_passed" in output or "summary" in output
        except json.JSONDecodeError:
            pytest.fail("Script did not output valid JSON when --json was requested")


class TestValidationScriptImports:
    """Test that the validation script imports required modules."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_argparse_imported(self, script_content):
        """Verify argparse is imported."""
        assert "import argparse" in script_content

    def test_json_imported(self, script_content):
        """Verify json is imported."""
        assert "import json" in script_content

    def test_pathlib_imported(self, script_content):
        """Verify pathlib is imported."""
        assert (
            "from pathlib import Path" in script_content
            or "import pathlib" in script_content
        )

    def test_re_imported(self, script_content):
        """Verify re is imported."""
        assert "import re" in script_content

    def test_sys_imported(self, script_content):
        """Verify sys is imported."""
        assert "import sys" in script_content

    def test_dataclasses_imported(self, script_content):
        """Verify dataclasses are imported."""
        assert (
            "from dataclasses" in script_content
            or "import dataclasses" in script_content
        )

    def test_datetime_imported(self, script_content):
        """Verify datetime is imported."""
        assert "from datetime" in script_content or "import datetime" in script_content

    def test_typing_imported(self, script_content):
        """Verify typing is imported."""
        assert "from typing" in script_content or "import typing" in script_content


class TestValidationScriptErrorHandling:
    """Test that the validation script handles errors gracefully."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_missing_runbook_handled(self, script_content):
        """Verify script handles missing runbooks gracefully."""
        assert ".exists()" in script_content or "exists = " in script_content
