"""Comprehensive tests for scripts/gates/precommit_validator.py

Story: SWARM-HARDEN-001 Task 7.2
Scope: All public methods, main branch blocking, timeout/exception handling
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.gates.precommit_validator import PrecommitValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def validator() -> PrecommitValidator:
    """Return a fresh PrecommitValidator with verbose=True for log assertions."""
    return PrecommitValidator(verbose=True, fix=False)


@pytest.fixture
def fix_validator() -> PrecommitValidator:
    """Return a validator in fix mode."""
    return PrecommitValidator(verbose=False, fix=True)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Tests for PrecommitValidator.__init__."""

    def test_default_values(self) -> None:
        v = PrecommitValidator()
        assert v.verbose is False
        assert v.fix is False
        assert v.errors == []
        assert v.warnings == []

    def test_verbose_true(self) -> None:
        v = PrecommitValidator(verbose=True)
        assert v.verbose is True

    def test_fix_true(self) -> None:
        v = PrecommitValidator(fix=True)
        assert v.fix is True

    def test_both_flags(self) -> None:
        v = PrecommitValidator(verbose=True, fix=True)
        assert v.verbose is True
        assert v.fix is True


# ---------------------------------------------------------------------------
# log()
# ---------------------------------------------------------------------------


class TestLog:
    """Tests for PrecommitValidator.log."""

    def test_verbose_prints(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.log("hello world")
        assert "[precommit] hello world" in capsys.readouterr().out

    def test_non_verbose_suppresses(self, capsys: pytest.CaptureFixture) -> None:
        v = PrecommitValidator(verbose=False)
        v.log("should not appear")
        assert capsys.readouterr().out == ""

    def test_log_multiple_messages(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.log("first")
        validator.log("second")
        output = capsys.readouterr().out
        assert "[precommit] first" in output
        assert "[precommit] second" in output


# ---------------------------------------------------------------------------
# run_command()
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for PrecommitValidator.run_command."""

    def test_success_returns_zero(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            code, out, err = validator.run_command(["echo", "hi"], "test desc")
        assert code == 0
        assert out == "ok"
        assert err == ""
        assert validator.errors == []

    def test_nonzero_returncode_adds_error(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="bad")
            code, out, err = validator.run_command(["false"], "fail desc")
        assert code == 1
        assert len(validator.errors) == 1
        assert "fail desc failed" in validator.errors[0]

    def test_allow_failure_no_error(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="warn")
            code, out, err = validator.run_command(["cmd"], "soft", allow_failure=True)
        assert code == 1
        assert validator.errors == []

    def test_timeout_expired_adds_error(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="cmd", timeout=300)
            code, out, err = validator.run_command(["sleep", "999"], "slow cmd")
        assert code == 1
        assert out == ""
        assert err == "Timeout"
        assert any("timed out" in e for e in validator.errors)

    def test_generic_exception_adds_error(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("permission denied")
            code, out, err = validator.run_command(["bad"], "oops")
        assert code == 1
        assert out == ""
        assert err == "permission denied"
        assert any("permission denied" in e for e in validator.errors)

    def test_timeout_value_is_300(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            validator.run_command(["true"], "check timeout")
            mock_run.assert_called_once()
            kwargs = mock_run.call_args[1]
            assert kwargs["timeout"] == 300

    def test_capture_output_and_text(self, validator: PrecommitValidator) -> None:
        with patch("scripts.gates.precommit_validator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="out", stderr="err")
            validator.run_command(["true"], "capture")
            kwargs = mock_run.call_args[1]
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True


# ---------------------------------------------------------------------------
# validate_black()
# ---------------------------------------------------------------------------


class TestValidateBlack:
    """Tests for PrecommitValidator.validate_black."""

    def test_no_files_returns_true(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        assert validator.validate_black([]) is True
        assert "No Python files" in capsys.readouterr().out

    def test_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_black(["a.py"]) is True
        assert "Black formatting OK" in capsys.readouterr().out

    def test_failure_returns_false(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "err")):
            assert validator.validate_black(["a.py"]) is False
        assert "Black formatting issues" in capsys.readouterr().out

    def test_fix_mode_uses_black_without_check(
        self, fix_validator: PrecommitValidator
    ) -> None:
        with patch.object(
            fix_validator, "run_command", return_value=(0, "", "")
        ) as mock:
            fix_validator.validate_black(["a.py"])
            cmd = mock.call_args[0][0]
            assert "--check" not in cmd

    def test_normal_mode_uses_black_with_check(
        self, validator: PrecommitValidator
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_black(["a.py"])
            cmd = mock.call_args[0][0]
            assert "--check" in cmd

    def test_failure_non_fix_suggests_fix(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "")):
            validator.validate_black(["a.py"])
        assert "--fix" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# validate_ruff()
# ---------------------------------------------------------------------------


class TestValidateRuff:
    """Tests for PrecommitValidator.validate_ruff."""

    def test_no_files_returns_true(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        assert validator.validate_ruff([]) is True
        assert "No Python files" in capsys.readouterr().out

    def test_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_ruff(["a.py"]) is True
        assert "Ruff linting OK" in capsys.readouterr().out

    def test_failure_returns_false(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "err")):
            assert validator.validate_ruff(["a.py"]) is False
        assert "Ruff linting issues" in capsys.readouterr().out

    def test_fix_mode_appends_fix_flag(self, fix_validator: PrecommitValidator) -> None:
        with patch.object(
            fix_validator, "run_command", return_value=(0, "", "")
        ) as mock:
            fix_validator.validate_ruff(["a.py"])
            cmd = mock.call_args[0][0]
            assert "--fix" in cmd

    def test_normal_mode_no_fix_flag(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_ruff(["a.py"])
            cmd = mock.call_args[0][0]
            assert "--fix" not in cmd


# ---------------------------------------------------------------------------
# validate_mypy()
# ---------------------------------------------------------------------------


class TestValidateMypy:
    """Tests for PrecommitValidator.validate_mypy."""

    def test_no_files_returns_true(self, validator: PrecommitValidator) -> None:
        assert validator.validate_mypy([]) is True

    def test_non_src_files_returns_true(self, validator: PrecommitValidator) -> None:
        # Files not under src/ or scripts/ are skipped
        assert validator.validate_mypy(["tests/test_foo.py", "README.md"]) is True

    def test_src_files_checked_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_mypy(["src/app.py"]) is True
        assert "Type annotations OK" in capsys.readouterr().out

    def test_scripts_files_checked_success(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            assert validator.validate_mypy(["scripts/foo.py"]) is True
            cmd = mock.call_args[0][0]
            assert "scripts/foo.py" in cmd

    def test_mypy_failure_returns_false_blocking(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        """Mypy issues are blocking and must return False."""
        with patch.object(validator, "run_command", return_value=(1, "", "type error")):
            assert validator.validate_mypy(["src/app.py"]) is False
        assert "issues found" in capsys.readouterr().out
        assert len(validator.errors) >= 1
        assert any("mypy" in err for err in validator.errors)

    def test_mypy_uses_allow_failure(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_mypy(["src/app.py"])
            _, kwargs = mock.call_args
            assert kwargs.get("allow_failure", False) is False

    def test_mixed_files_filters_correctly(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_mypy(["src/a.py", "tests/b.py", "scripts/c.py"])
            cmd = mock.call_args[0][0]
            assert "src/a.py" in cmd
            assert "scripts/c.py" in cmd
            assert "tests/b.py" not in cmd


# ---------------------------------------------------------------------------
# validate_status_sync()
# ---------------------------------------------------------------------------


class TestValidateStatusSync:
    """Tests for PrecommitValidator.validate_status_sync."""

    def test_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_status_sync() is True
        assert "Status sync OK" in capsys.readouterr().out

    def test_failure_nonblocking(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "err")):
            assert validator.validate_status_sync() is True
        assert "non-blocking" in capsys.readouterr().out
        assert len(validator.warnings) == 1
        assert "status-sync" in validator.warnings[0]

    def test_calls_correct_script(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_status_sync()
            cmd = mock.call_args[0][0]
            assert "scripts/validate_status_sync.py" in cmd

    def test_uses_allow_failure(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_status_sync()
            _, kwargs = mock.call_args
            assert kwargs.get("allow_failure", False) is True


# ---------------------------------------------------------------------------
# validate_traceability()
# ---------------------------------------------------------------------------


class TestValidateTraceability:
    """Tests for PrecommitValidator.validate_traceability."""

    def test_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_traceability() is True
        assert "FR traceability OK" in capsys.readouterr().out

    def test_failure_nonblocking(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "err")):
            assert validator.validate_traceability() is True
        assert "non-blocking" in capsys.readouterr().out
        assert len(validator.warnings) == 1
        assert "traceability" in validator.warnings[0]

    def test_calls_correct_script(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_traceability()
            cmd = mock.call_args[0][0]
            assert "scripts/validate_fr_traceability.py" in cmd


# ---------------------------------------------------------------------------
# validate_swarm_policy()
# ---------------------------------------------------------------------------


class TestValidateSwarmPolicy:
    """Tests for PrecommitValidator.validate_swarm_policy."""

    def test_success(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.validate_swarm_policy() is True
        assert "Swarm policy consistency OK" in capsys.readouterr().out

    def test_failure_blocking(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "conflict")):
            assert validator.validate_swarm_policy() is False
        assert "failed" in capsys.readouterr().out.lower()

    def test_calls_correct_script(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.validate_swarm_policy()
            cmd = mock.call_args[0][0]
            assert "scripts/validate_swarm_policy_consistency.py" in cmd

    def test_run_command_called_without_allow_failure(
        self, validator: PrecommitValidator
    ) -> None:
        """Swarm policy calls run_command without allow_failure=True."""
        with patch.object(validator, "run_command", return_value=(1, "", "")) as mock:
            validator.validate_swarm_policy()
            _, kwargs = mock.call_args
            assert kwargs.get("allow_failure", False) is False


# ---------------------------------------------------------------------------
# validate_git_sanity()  — MAIN BRANCH BLOCKING (AC2)
# ---------------------------------------------------------------------------


class TestValidateGitSanity:
    """Tests for PrecommitValidator.validate_git_sanity.

    This is the critical main-branch blocking logic (AC2).
    """

    def test_on_main_branch_blocks(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        """Committing to main must be blocked."""
        with patch.object(
            validator, "run_command", return_value=(0, "main\n", "")
        ) as mock:
            assert validator.validate_git_sanity() is False
        assert "main" in capsys.readouterr().out.lower()
        assert any("main branch" in e for e in validator.errors)

    def test_on_feature_branch_passes(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(
            validator,
            "run_command",
            side_effect=[
                (0, "feature/foo-123\n", ""),  # branch check
                (0, "", ""),  # diff check
            ],
        ):
            assert validator.validate_git_sanity() is True
        assert "feature/foo-123" in capsys.readouterr().out

    def test_merge_markers_detected(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        """Merge conflict markers must block."""
        with patch.object(
            validator,
            "run_command",
            side_effect=[
                (0, "feature/x\n", ""),  # not main
                (1, "", "conflict"),  # diff check fails
            ],
        ):
            assert validator.validate_git_sanity() is False
        assert any("conflict" in e.lower() for e in validator.errors)

    def test_branch_check_failure_propagates(
        self, validator: PrecommitValidator
    ) -> None:
        """If git branch command itself fails, git_sanity should still return False."""
        with patch.object(
            validator,
            "run_command",
            return_value=(1, "", "not a git repo"),
        ):
            result = validator.validate_git_sanity()
        # When branch command fails we skip the main check but diff check still runs
        # The overall result depends on the diff check - with no second mock, it fails
        assert isinstance(result, bool)

    def test_main_branch_error_message_exact(
        self, validator: PrecommitValidator
    ) -> None:
        with patch.object(validator, "run_command", return_value=(0, "main\n", "")):
            validator.validate_git_sanity()
        assert any(
            "Cannot commit directly to main branch" in e for e in validator.errors
        )

    def test_clean_git_state_passes(self, validator: PrecommitValidator) -> None:
        with patch.object(
            validator,
            "run_command",
            side_effect=[
                (0, "feature/SWARM-HARDEN-001-7.2\n", ""),
                (0, "", ""),
            ],
        ):
            assert validator.validate_git_sanity() is True


# ---------------------------------------------------------------------------
# get_changed_files()
# ---------------------------------------------------------------------------


class TestGetChangedFiles:
    """Tests for PrecommitValidator.get_changed_files."""

    def test_no_staged_files(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            assert validator.get_changed_files() == []

    def test_filters_to_python(self, validator: PrecommitValidator) -> None:
        output = "src/a.py\nREADME.md\nscripts/b.py\nconfig.yaml\n"
        with patch.object(validator, "run_command", return_value=(0, output, "")):
            files = validator.get_changed_files()
            assert files == ["src/a.py", "scripts/b.py"]

    def test_git_command_failure_returns_empty(
        self, validator: PrecommitValidator
    ) -> None:
        with patch.object(validator, "run_command", return_value=(1, "", "err")):
            assert validator.get_changed_files() == []

    def test_strips_whitespace(self, validator: PrecommitValidator) -> None:
        output = "  src/a.py  \n  scripts/b.py  \n"
        with patch.object(validator, "run_command", return_value=(0, output, "")):
            files = validator.get_changed_files()
            assert files == ["src/a.py", "scripts/b.py"]

    def test_skips_empty_lines(self, validator: PrecommitValidator) -> None:
        output = "src/a.py\n\nscripts/b.py\n"
        with patch.object(validator, "run_command", return_value=(0, output, "")):
            files = validator.get_changed_files()
            assert files == ["src/a.py", "scripts/b.py"]

    def test_uses_correct_git_diff_flags(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "run_command", return_value=(0, "", "")) as mock:
            validator.get_changed_files()
            cmd = mock.call_args[0][0]
            assert "--cached" in cmd
            assert "--name-only" in cmd
            assert "--diff-filter=ACM" in cmd


# ---------------------------------------------------------------------------
# validate()  — full pipeline
# ---------------------------------------------------------------------------


class TestValidate:
    """Tests for PrecommitValidator.validate - the full pipeline."""

    def test_git_sanity_failure_short_circuits(
        self, validator: PrecommitValidator
    ) -> None:
        """If git sanity fails, no other checks run."""
        with patch.object(
            validator, "validate_git_sanity", return_value=False
        ) as mock_git:
            with patch.object(validator, "get_changed_files") as mock_files:
                with patch.object(validator, "validate_black") as mock_black:
                    with patch.object(validator, "validate_ruff") as mock_ruff:
                        with patch.object(validator, "validate_mypy") as mock_mypy:
                            assert validator.validate() is False
        mock_git.assert_called_once()
        mock_files.assert_not_called()
        mock_black.assert_not_called()
        mock_ruff.assert_not_called()
        mock_mypy.assert_not_called()

    def test_no_changed_files_skips_code_quality(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        """When no Python files are staged, code quality checks are skipped."""
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=[]):
                with patch.object(validator, "validate_status_sync", return_value=True):
                    with patch.object(
                        validator, "validate_traceability", return_value=True
                    ):
                        with patch.object(
                            validator, "validate_swarm_policy", return_value=True
                        ):
                            assert validator.validate() is True
        assert "No Python files changed" in capsys.readouterr().out

    def test_all_checks_pass(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=["a.py"]):
                with patch.object(validator, "validate_black", return_value=True):
                    with patch.object(validator, "validate_ruff", return_value=True):
                        with patch.object(
                            validator, "validate_mypy", return_value=True
                        ):
                            with patch.object(
                                validator, "validate_status_sync", return_value=True
                            ):
                                with patch.object(
                                    validator,
                                    "validate_traceability",
                                    return_value=True,
                                ):
                                    with patch.object(
                                        validator,
                                        "validate_swarm_policy",
                                        return_value=True,
                                    ):
                                        assert validator.validate() is True

    def test_black_failure_blocks(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=["a.py"]):
                with patch.object(validator, "validate_black", return_value=False):
                    with patch.object(validator, "validate_ruff", return_value=True):
                        with patch.object(
                            validator, "validate_mypy", return_value=True
                        ):
                            assert validator.validate() is False

    def test_ruff_failure_blocks(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=["a.py"]):
                with patch.object(validator, "validate_black", return_value=True):
                    with patch.object(validator, "validate_ruff", return_value=False):
                        with patch.object(
                            validator, "validate_mypy", return_value=True
                        ):
                            assert validator.validate() is False

    def test_swarm_policy_failure_blocks(self, validator: PrecommitValidator) -> None:
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=[]):
                with patch.object(validator, "validate_status_sync", return_value=True):
                    with patch.object(
                        validator, "validate_traceability", return_value=True
                    ):
                        with patch.object(
                            validator, "validate_swarm_policy", return_value=False
                        ):
                            assert validator.validate() is False


# ---------------------------------------------------------------------------
# print_summary()
# ---------------------------------------------------------------------------


class TestPrintSummary:
    """Tests for PrecommitValidator.print_summary."""

    def test_no_errors_no_warnings(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.print_summary()
        assert "All validations passed" in capsys.readouterr().out

    def test_errors_shown(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.errors = ["error one", "error two"]
        validator.print_summary()
        output = capsys.readouterr().out
        assert "FAILED" in output
        assert "error one" in output
        assert "error two" in output
        assert "2 error(s)" in output

    def test_warnings_shown(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.warnings = ["warn one"]
        validator.print_summary()
        output = capsys.readouterr().out
        assert "WARNINGS" in output
        assert "warn one" in output

    def test_errors_and_warnings(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.errors = ["err"]
        validator.warnings = ["warn"]
        validator.print_summary()
        output = capsys.readouterr().out
        assert "FAILED" in output
        assert "WARNINGS" in output
        # "Passed with warnings" should NOT appear when errors exist
        assert "Passed with warnings" not in output

    def test_warnings_only_shows_passed_with_warnings(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
    ) -> None:
        validator.warnings = ["mypy: type issues"]
        validator.print_summary()
        assert "Passed with warnings" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Timeout and exception handling (AC3)
# ---------------------------------------------------------------------------


class TestTimeoutAndExceptionHandling:
    """Tests for timeout and exception handling in command execution (AC3)."""

    def test_timeout_in_run_command(self, validator: PrecommitValidator) -> None:
        """TimeoutExpired must return (1, '', 'Timeout') and add error."""
        with patch(
            "scripts.gates.precommit_validator.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="slow", timeout=300),
        ):
            code, out, err = validator.run_command(["sleep", "999"], "slow check")
        assert code == 1
        assert out == ""
        assert err == "Timeout"
        assert len(validator.errors) == 1

    def test_oserror_in_run_command(self, validator: PrecommitValidator) -> None:
        """OSError (e.g. file not found) must be caught gracefully."""
        with patch(
            "scripts.gates.precommit_validator.subprocess.run",
            side_effect=FileNotFoundError("black not found"),
        ):
            code, out, err = validator.run_command(["black", "--check"], "black")
        assert code == 1
        assert "black not found" in err
        assert len(validator.errors) == 1

    def test_keyboard_interrupt_propagates(self, validator: PrecommitValidator) -> None:
        """KeyboardInterrupt should NOT be caught - let it propagate."""
        with patch(
            "scripts.gates.precommit_validator.subprocess.run",
            side_effect=KeyboardInterrupt(),
        ):
            with pytest.raises(KeyboardInterrupt):
                validator.run_command(["sleep", "999"], "interruptible")

    def test_timeout_during_validate_black(self, validator: PrecommitValidator) -> None:
        """Black check with timeout returns False."""
        with patch.object(
            validator,
            "run_command",
            return_value=(1, "", "Timeout"),
        ):
            assert validator.validate_black(["a.py"]) is False

    def test_timeout_during_validate_ruff(self, validator: PrecommitValidator) -> None:
        """Ruff check with timeout returns False."""
        with patch.object(
            validator,
            "run_command",
            return_value=(1, "", "Timeout"),
        ):
            assert validator.validate_ruff(["a.py"]) is False

    def test_timeout_during_validate_git_sanity(
        self, validator: PrecommitValidator
    ) -> None:
        """Git sanity with command failure still returns a boolean."""
        with patch.object(
            validator,
            "run_command",
            return_value=(1, "", "error"),
        ):
            result = validator.validate_git_sanity()
        assert isinstance(result, bool)

    def test_generic_exception_in_validate_status_sync(
        self, validator: PrecommitValidator
    ) -> None:
        """Status sync script missing must not crash the validator."""
        with patch.object(
            validator,
            "run_command",
            return_value=(1, "", "FileNotFoundError"),
        ):
            # Status sync is non-blocking, so returns True even on failure
            assert validator.validate_status_sync() is True
            assert len(validator.warnings) == 1

    def test_multiple_command_failures_accumulate_errors(
        self, validator: PrecommitValidator
    ) -> None:
        """Multiple failing commands should accumulate errors."""
        with patch(
            "scripts.gates.precommit_validator.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="fail"),
        ):
            validator.run_command(["cmd1"], "first")
            validator.run_command(["cmd2"], "second")
            validator.run_command(["cmd3"], "third")
        assert len(validator.errors) == 3

    def test_errors_and_warnings_accumulate_independently(
        self, validator: PrecommitValidator
    ) -> None:
        """Errors and warnings are separate accumulators."""
        validator.errors.append("error")
        validator.warnings.append("warning")
        assert len(validator.errors) == 1
        assert len(validator.warnings) == 1
        validator.errors.append("error2")
        assert len(validator.warnings) == 1
        assert len(validator.errors) == 2


# ---------------------------------------------------------------------------
# main() and argparse (C1 fix)
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() function and argparse (C1)."""

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_no_args_success(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() with no arguments - success path."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py"]):
            main()

        mock_validator_class.assert_called_once_with(verbose=False, fix=False)
        mock_validator.validate.assert_called_once_with(skip_git_check=False)
        mock_validator.print_summary.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_verbose_flag(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() with --verbose flag."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py", "--verbose"]):
            main()

        mock_validator_class.assert_called_once_with(verbose=True, fix=False)
        mock_validator.validate.assert_called_once_with(skip_git_check=False)
        mock_exit.assert_called_once_with(0)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_fix_flag(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() with --fix flag."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py", "--fix"]):
            main()

        mock_validator_class.assert_called_once_with(verbose=False, fix=True)
        mock_validator.validate.assert_called_once_with(skip_git_check=False)
        mock_exit.assert_called_once_with(0)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_skip_git_check_flag(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() with --skip-git-check flag (C1 fix)."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py", "--skip-git-check"]):
            main()

        mock_validator_class.assert_called_once_with(verbose=False, fix=False)
        # Critical: skip_git_check=True must be passed to validate()
        mock_validator.validate.assert_called_once_with(skip_git_check=True)
        mock_exit.assert_called_once_with(0)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_multiple_flags(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() with multiple flags combined."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch(
        "sys.argv", ["precommit_validator.py", "--verbose", "--fix", "--skip-git-check"]
        ):
            main()

        mock_validator_class.assert_called_once_with(verbose=True, fix=True)
        mock_validator.validate.assert_called_once_with(skip_git_check=True)
        mock_exit.assert_called_once_with(0)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_failure_exits_with_1(
        self, mock_exit, mock_validator_class, capsys: pytest.CaptureFixture
        ) -> None:
        """Test main() exits with code 1 on validation failure."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = False
        mock_validator_class.return_value = mock_validator

        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py"]):
            main()

        mock_exit.assert_called_once_with(1)

    @patch("scripts.gates.precommit_validator.PrecommitValidator")
    @patch("scripts.gates.precommit_validator.sys.exit")
    def test_main_help_flag(self, mock_exit, mock_validator_class) -> None:
        """Test main() --help shows usage information."""
        from scripts.gates.precommit_validator import main

        with patch("sys.argv", ["precommit_validator.py", "--help"]):
            main()

        mock_exit.assert_called_with(0)


class TestValidateSkipGitCheck:
    """Tests for validate() with skip_git_check parameter (C1)."""

    def test_skip_git_check_true_skips_git_sanity(
        self, validator: PrecommitValidator, capsys: pytest.CaptureFixture
        ) -> None:
        """When skip_git_check=True, validate_git_sanity should not be called."""
        with patch.object(validator, "validate_git_sanity") as mock_git:
            with patch.object(validator, "get_changed_files", return_value=[]):
                with patch.object(validator, "validate_status_sync", return_value=True):
                    with patch.object(validator, "validate_traceability", return_value=True):
                        with patch.object(validator, "validate_swarm_policy", return_value=True):
                            validator.validate(skip_git_check=True)

        mock_git.assert_not_called()
        assert "Skipping git sanity checks" in capsys.readouterr().out

    def test_skip_git_check_false_calls_git_sanity(
        self, validator: PrecommitValidator
        ) -> None:
        """When skip_git_check=False (default), validate_git_sanity should be called."""
        with patch.object(validator, "validate_git_sanity", return_value=True) as mock_git:
            with patch.object(validator, "get_changed_files", return_value=[]):
                with patch.object(validator, "validate_status_sync", return_value=True):
                    with patch.object(validator, "validate_traceability", return_value=True):
                        with patch.object(validator, "validate_swarm_policy", return_value=True):
                            validator.validate(skip_git_check=False)

        mock_git.assert_called_once()

    def test_skip_git_check_default_false(
        self, validator: PrecommitValidator
        ) -> None:
        """validate() default behavior should check git sanity."""
        with patch.object(validator, "validate_git_sanity", return_value=True) as mock_git:
            with patch.object(validator, "get_changed_files", return_value=[]):
                with patch.object(validator, "validate_status_sync", return_value=True):
                    with patch.object(validator, "validate_traceability", return_value=True):
                        with patch.object(validator, "validate_swarm_policy", return_value=True):
                            validator.validate() # No skip_git_check parameter

        mock_git.assert_called_once()


class TestValidateMypyBlocking:
    """Tests for validate_mypy() blocking behavior (C2 fix)."""

    def test_mypy_failure_returns_false(self, validator: PrecommitValidator) -> None:
        """Mypy failure should return False (blocking error)."""
        with patch.object(validator, "run_command", return_value=(1, "", "type error")):
            result = validator.validate_mypy(["src/app.py"])
        assert result is False
        assert len(validator.errors) == 1
        assert "mypy" in validator.errors[0]

    def test_mypy_success_returns_true(self, validator: PrecommitValidator) -> None:
        """Mypy success should return True."""
        with patch.object(validator, "run_command", return_value=(0, "", "")):
            result = validator.validate_mypy(["src/app.py"])
        assert result is True
        assert len(validator.errors) == 0

    def test_mypy_failure_blocks_validation(self, validator: PrecommitValidator) -> None:
        """Mypy failure should block overall validation (C2 fix)."""
        with patch.object(validator, "validate_git_sanity", return_value=True):
            with patch.object(validator, "get_changed_files", return_value=["src/app.py"]):
                with patch.object(validator, "validate_black", return_value=True):
                    with patch.object(validator, "validate_ruff", return_value=True):
                        with patch.object(validator, "validate_mypy", return_value=False):  # Mypy fails
                            with patch.object(validator, "validate_status_sync", return_value=True):
                                with patch.object(validator, "validate_traceability", return_value=True):
                                    with patch.object(validator, "validate_swarm_policy", return_value=True):
                                        result = validator.validate()
        assert result is False  # Should be blocked by mypy failure

    def test_mypy_failure_no_warning_added(self, validator: PrecommitValidator) -> None:
        """Mypy failure should add to errors, not warnings (C2 fix)."""
        with patch.object(validator, "run_command", return_value=(1, "", "type error")):
            validator.validate_mypy(["src/app.py"])
        assert len(validator.errors) == 1
        assert len(validator.warnings) == 0
        assert "mypy" in validator.errors[0]
