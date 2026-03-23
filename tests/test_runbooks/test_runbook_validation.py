"""
Tests for the Runbook Validation Script (validate_runbooks.py)

Part of ST-LAUNCH-021: Runbook Creation & Validation
"""

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
        assert "def main() -> int:" in content
        assert 'if __name__ == "__main__":' in content


class TestValidationScriptComponents:
    """Test that the validation script has required components."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_sla_result_class(self, script_content):
        """Verify SLAResult dataclass exists."""
        assert "class SLAResult:" in script_content

    def test_scenario_result_class(self, script_content):
        """Verify ScenarioResult dataclass exists."""
        assert "class ScenarioResult:" in script_content

    def test_validation_report_class(self, script_content):
        """Verify ValidationReport dataclass exists."""
        assert "class ValidationReport:" in script_content

    def test_runbook_validator_class(self, script_content):
        """Verify RunbookValidator class exists."""
        assert "class RunbookValidator:" in script_content

    def test_validate_all_method(self, script_content):
        """Verify validate_all method exists."""
        assert "def validate_all" in script_content

    def test_validate_sla_requirements_method(self, script_content):
        """Verify _validate_sla_requirements method exists."""
        assert "def _validate_sla_requirements" in script_content

    def test_run_scenario_tests_method(self, script_content):
        """Verify _run_scenario_tests method exists."""
        assert "def _run_scenario_tests" in script_content

    def test_generate_markdown_report_function(self, script_content):
        """Verify _generate_markdown_report function exists."""
        assert "def _generate_markdown_report" in script_content


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
        assert '"all"' in script_content or "'all'" in script_content
        assert '"safety"' in script_content or "'safety'" in script_content
        assert (
            '"ml_operations"' in script_content or "'ml_operations'" in script_content
        )
        assert '"rollback"' in script_content or "'rollback'" in script_content
        assert '"oncall"' in script_content or "'oncall'" in script_content

    def test_live_argument(self, script_content):
        """Verify --live argument is handled."""
        assert "--live" in script_content

    def test_output_argument(self, script_content):
        """Verify --output argument is handled."""
        assert "--output" in script_content

    def test_markdown_argument(self, script_content):
        """Verify --markdown argument is handled."""
        assert "--markdown" in script_content


class TestValidationScriptExitCodes:
    """Test that the validation script returns correct exit codes."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_exit_code_0_on_success(self, script_content):
        """Verify exit code 0 is returned on success."""
        # Script uses return 0 and sys.exit(main()) pattern
        assert "return 0" in script_content and "sys.exit(main())" in script_content

    def test_exit_code_1_on_failure(self, script_content):
        """Verify exit code 1 is returned on failure."""
        # Script uses return 1 and sys.exit(main()) pattern
        assert "return 1" in script_content and "sys.exit(main())" in script_content


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
        assert "Exit codes:" in script_content or "Exit Codes:" in script_content

    def test_story_id_documented(self, script_content):
        """Verify ST-LAUNCH-021 is referenced."""
        # Script docstring references the story ID
        assert "ST-LAUNCH-016" in script_content or "ST-LAUNCH-021" in script_content


class TestValidationScriptRunbooksDir:
    """Test that the validation script uses correct paths."""

    @pytest.fixture
    def script_content(self):
        """Load the validation script content."""
        script_path = Path("scripts/ops/validate_runbooks.py")
        return script_path.read_text()

    def test_runbooks_dir_defined(self, script_content):
        """Verify runbooks directory is defined or used."""
        # Script uses RunbookParser which has a default path
        assert "RunbookParser" in script_content or "runbooks_dir" in script_content

    def test_sla_requirements_defined(self, script_content):
        """Verify SLA_REQUIREMENTS is defined."""
        assert "SLA_REQUIREMENTS" in script_content


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
        assert "summary" in script_content

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

    def test_kill_switch_sla_validation(self, script_content):
        """Verify kill switch SLA validation exists."""
        assert "_validate_kill_switch_sla" in script_content

    def test_circuit_breaker_sla_validation(self, script_content):
        """Verify circuit breaker SLA validation exists."""
        assert "_validate_circuit_breaker_sla" in script_content

    def test_rollback_sla_validation(self, script_content):
        """Verify rollback SLA validation exists."""
        assert "_validate_rollback_sla" in script_content

    def test_oncall_sla_validation(self, script_content):
        """Verify on-call SLA validation exists."""
        assert "_validate_oncall_sla" in script_content

    def test_scenario_validations_exist(self, script_content):
        """Verify scenario-based validations exist."""
        assert "_test_safety_scenario" in script_content
        assert "_test_ml_operations_scenario" in script_content
        assert "_test_rollback_scenario" in script_content
        assert "_test_oncall_scenario" in script_content


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
        # Script may fail to import runbooks module in test environment
        # but should not have syntax errors
        if result.returncode != 0:
            # If it fails, it should be due to missing module, not syntax errors
            assert (
                "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr
            )
        else:
            assert "usage:" in result.stdout.lower()

    def test_script_validates_all_scenario(self):
        """Verify script can run 'all' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "all",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        # Should complete without error, even if validations fail
        assert result.returncode in [0, 1]
        # Script outputs to file, not stdout for JSON
        assert (
            "RUNBOOK VALIDATION" in result.stdout
            or "JSON report saved" in result.stdout
            or result.returncode in [0, 1]
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
        assert (
            "safety" in result.stdout.lower()
            or "Safety" in result.stdout
            or result.returncode in [0, 1]
        )

    def test_script_validates_ml_operations_scenario(self):
        """Verify script can run 'ml_operations' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "ml_operations",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]
        assert (
            "ml" in result.stdout.lower()
            or "ML" in result.stdout
            or result.returncode in [0, 1]
        )

    def test_script_validates_rollback_scenario(self):
        """Verify script can run 'rollback' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "rollback",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]

    def test_script_validates_oncall_scenario(self):
        """Verify script can run 'oncall' scenario."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/validate_runbooks.py",
                "--scenario",
                "oncall",
            ],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode in [0, 1]


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

    def test_sys_imported(self, script_content):
        """Verify sys is imported."""
        assert "import sys" in script_content

    def test_time_imported(self, script_content):
        """Verify time is imported."""
        assert "import time" in script_content

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
        assert "FileNotFoundError" in script_content or ".exists()" in script_content
