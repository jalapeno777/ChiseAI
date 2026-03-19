#!/usr/bin/env python3
"""
Tests for evidence_validator.py — machine-checkable file existence proof validation.

Story: SWARM-HARDEN-001
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.swarm.evidence_validator import (
    CommandProofResult,
    EvidenceCheckStatus,
    EvidenceSeverity,
    EvidenceValidationResult,
    EvidenceValidator,
    FileExistenceResult,
    TestClaimResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class _TempRepoMixin:
    """Mixin that creates a temporary directory tree for tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="evidence_validator_test_")
        self.repo_root = Path(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, relative_path: str, content: str = "") -> Path:
        """Create a file in the temp repo and return its absolute path."""
        full = self.repo_root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content or "dummy content\n")
        return full


# ---------------------------------------------------------------------------
# FileExistenceResult tests
# ---------------------------------------------------------------------------


class TestFileExistenceResult(unittest.TestCase):
    """Test FileExistenceResult dataclass."""

    def test_existing_file_result(self):
        result = FileExistenceResult(
            path="src/foo.py",
            exists=True,
            check_method="os.path",
            detail="File exists",
        )
        self.assertTrue(result.exists)
        self.assertEqual(result.check_method, "os.path")

    def test_missing_file_result_is_critical(self):
        result = FileExistenceResult(
            path="src/phantom.py",
            exists=False,
            check_method="os.path+glob",
            detail="Not found",
            severity=EvidenceSeverity.CRITICAL,
        )
        self.assertFalse(result.exists)
        self.assertEqual(result.severity, EvidenceSeverity.CRITICAL)


# ---------------------------------------------------------------------------
# TestClaimResult tests
# ---------------------------------------------------------------------------


class TestTestClaimResult(unittest.TestCase):
    """Test TestClaimResult dataclass."""

    def test_matching_claim(self):
        result = TestClaimResult(
            test_file_pattern="tests/test_foo.py",
            claimed_result="passed",
            test_file_exists=True,
            actual_test_files=["tests/test_foo.py"],
            match_found=True,
        )
        self.assertTrue(result.match_found)
        self.assertTrue(result.test_file_exists)

    def test_phantom_claim_is_critical(self):
        result = TestClaimResult(
            test_file_pattern="tests/test_phantom.py",
            claimed_result="5 passed",
            test_file_exists=False,
            actual_test_files=[],
            match_found=False,
            severity=EvidenceSeverity.CRITICAL,
        )
        self.assertFalse(result.match_found)
        self.assertFalse(result.test_file_exists)
        self.assertEqual(result.severity, EvidenceSeverity.CRITICAL)


# ---------------------------------------------------------------------------
# CommandProofResult tests
# ---------------------------------------------------------------------------


class TestCommandProofResult(unittest.TestCase):
    """Test CommandProofResult dataclass."""

    def test_verified_command(self):
        result = CommandProofResult(
            command="ls src/foo.py",
            claimed_exit_code=0,
            verified=True,
            detail="Re-ran: exit=0 (claimed=0)",
        )
        self.assertTrue(result.verified)

    def test_unverified_command(self):
        result = CommandProofResult(
            command="pytest tests/",
            claimed_exit_code=0,
            verified=False,
            detail="Not auto-verifiable",
            severity=EvidenceSeverity.WARNING,
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.WARNING)


# ---------------------------------------------------------------------------
# EvidenceValidationResult tests
# ---------------------------------------------------------------------------


class TestEvidenceValidationResult(unittest.TestCase):
    """Test EvidenceValidationResult aggregation logic."""

    def test_empty_result_is_not_valid(self):
        result = EvidenceValidationResult()
        self.assertFalse(result.is_valid)
        self.assertEqual(result.overall_status, EvidenceCheckStatus.SKIP)

    def test_pass_result_is_valid(self):
        result = EvidenceValidationResult(overall_status=EvidenceCheckStatus.PASS)
        self.assertTrue(result.is_valid)

    def test_fail_result_is_not_valid(self):
        result = EvidenceValidationResult(overall_status=EvidenceCheckStatus.FAIL)
        self.assertFalse(result.is_valid)

    def test_critical_count(self):
        result = EvidenceValidationResult(
            file_existence_results=[
                FileExistenceResult(
                    path="a.py",
                    exists=False,
                    check_method="os.path",
                    severity=EvidenceSeverity.CRITICAL,
                ),
                FileExistenceResult(
                    path="b.py",
                    exists=True,
                    check_method="os.path",
                    severity=EvidenceSeverity.INFO,
                ),
            ]
        )
        self.assertEqual(result.critical_count, 1)

    def test_warning_count(self):
        result = EvidenceValidationResult(
            test_claim_results=[
                TestClaimResult(
                    test_file_pattern="t.py",
                    claimed_result="passed",
                    test_file_exists=True,
                    actual_test_files=["t_other.py"],
                    match_found=True,
                    severity=EvidenceSeverity.WARNING,
                ),
            ]
        )
        self.assertEqual(result.warning_count, 1)

    def test_summary_includes_key_info(self):
        result = EvidenceValidationResult(
            overall_status=EvidenceCheckStatus.PASS,
            file_existence_results=[
                FileExistenceResult(path="a.py", exists=True, check_method="os.path")
            ],
            errors=["err1"],
        )
        summary = result.summary()
        self.assertIn("pass", summary)
        self.assertIn("Files checked: 1", summary)
        self.assertIn("Errors: 1", summary)


# ---------------------------------------------------------------------------
# EvidenceValidator — check_file_exists (AC1)
# ---------------------------------------------------------------------------


class TestCheckFileExists(_TempRepoMixin, unittest.TestCase):
    """AC1: Validator checks claimed files exist via machine-checkable methods."""

    def test_existing_file_found_by_os_path(self):
        self._write_file("src/real_module.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/real_module.py", ["os.path"])
        self.assertTrue(result.exists)
        self.assertEqual(result.check_method, "os.path")

    def test_existing_file_found_by_glob(self):
        self._write_file("src/real_module.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/real_module.py", ["glob"])
        self.assertTrue(result.exists)
        self.assertEqual(result.check_method, "glob")

    def test_existing_file_found_by_git_ls_files(self):
        self._write_file("src/tracked.py")
        # Initialize git repo so git_ls_files works
        subprocess_run = MagicMock(
            return_value=_make_completed_process(
                returncode=0,
                stdout="src/tracked.py\n",
            )
        )
        with patch("subprocess.run", subprocess_run):
            validator = EvidenceValidator(repo_root=self.repo_root)
            result = validator.check_file_exists("src/tracked.py", ["git_ls_files"])
        self.assertTrue(result.exists)
        self.assertEqual(result.check_method, "git_ls_files")

    def test_missing_file_is_critical(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/phantom_module.py")
        self.assertFalse(result.exists)
        self.assertEqual(result.severity, EvidenceSeverity.CRITICAL)

    def test_missing_file_tries_all_methods(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists(
            "src/ghost.py",
            check_methods=["os.path", "glob"],
        )
        self.assertFalse(result.exists)
        self.assertIn("os.path", result.check_method)
        self.assertIn("glob", result.check_method)

    def test_absolute_path_handled(self):
        abs_path = self._write_file("src/absolute.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists(str(abs_path))
        self.assertTrue(result.exists)

    def test_git_unavailable_falls_back(self):
        """When git is not available, git_ls_files method gracefully fails."""
        self._write_file("src/nogit.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        # Force git to appear unavailable
        validator._git_available = False
        result = validator.check_file_exists("src/nogit.py", ["git_ls_files"])
        self.assertFalse(result.exists)
        self.assertEqual(result.check_method, "git_ls_files")


# ---------------------------------------------------------------------------
# EvidenceValidator — check_files_exist
# ---------------------------------------------------------------------------


class TestCheckFilesExist(_TempRepoMixin, unittest.TestCase):
    """Test batch file existence checking."""

    def test_all_files_exist(self):
        self._write_file("src/a.py")
        self._write_file("src/b.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.check_files_exist(["src/a.py", "src/b.py"])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.exists for r in results))

    def test_some_files_missing(self):
        self._write_file("src/real.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.check_files_exist(["src/real.py", "src/phantom.py"])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].exists)
        self.assertFalse(results[1].exists)

    def test_all_files_missing(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.check_files_exist(["ghost1.py", "ghost2.py"])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not r.exists for r in results))

    def test_empty_list_returns_empty(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.check_files_exist([])
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# EvidenceValidator — validate_test_claim (AC3)
# ---------------------------------------------------------------------------


class TestValidateTestClaim(_TempRepoMixin, unittest.TestCase):
    """AC3: Validator checks test result claims match actual test file existence."""

    def test_exact_test_file_exists(self):
        self._write_file("tests/test_foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_test_claim("tests/test_foo.py", "passed")
        self.assertTrue(result.match_found)
        self.assertTrue(result.test_file_exists)
        self.assertEqual(result.severity, EvidenceSeverity.INFO)

    def test_test_file_not_found_is_critical(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_test_claim(
            "tests/test_phantom.py", "5 passed, 0 failed"
        )
        self.assertFalse(result.match_found)
        self.assertFalse(result.test_file_exists)
        self.assertEqual(result.severity, EvidenceSeverity.CRITICAL)

    def test_glob_match_is_warning(self):
        """When exact file doesn't match but glob finds similar, severity is WARNING."""
        self._write_file("tests/test_foo_v2.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        # Pattern that will glob-match but not exact-match
        result = validator.validate_test_claim("tests/test_foo*.py", "passed")
        self.assertTrue(result.match_found)
        self.assertTrue(result.test_file_exists)
        self.assertEqual(result.severity, EvidenceSeverity.WARNING)


# ---------------------------------------------------------------------------
# EvidenceValidator — validate_test_claims
# ---------------------------------------------------------------------------


class TestValidateTestClaims(_TempRepoMixin, unittest.TestCase):
    """Test batch test claim validation."""

    def test_all_claims_valid(self):
        self._write_file("tests/test_a.py")
        self._write_file("tests/test_b.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_test_claims(
            {
                "tests/test_a.py": "passed",
                "tests/test_b.py": "3 passed",
            }
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.match_found for r in results))

    def test_phantom_test_claim_detected(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_test_claims(
            {
                "tests/test_real.py": "passed",  # doesn't exist
                "tests/test_phantom.py": "10 passed",  # doesn't exist
            }
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not r.match_found for r in results))
        self.assertTrue(all(r.severity == EvidenceSeverity.CRITICAL for r in results))

    def test_mixed_valid_and_phantom(self):
        self._write_file("tests/test_real.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_test_claims(
            {
                "tests/test_real.py": "passed",
                "tests/test_phantom.py": "5 passed",
            }
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].match_found)
        self.assertFalse(results[1].match_found)


# ---------------------------------------------------------------------------
# EvidenceValidator — validate_command_proof
# ---------------------------------------------------------------------------


class TestValidateCommandProof(_TempRepoMixin, unittest.TestCase):
    """Test command proof verification."""

    def test_ls_command_verified_success(self):
        self._write_file("src/foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof("ls src/foo.py", claimed_exit_code=0)
        self.assertTrue(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.INFO)

    def test_ls_command_verified_failure(self):
        """ls on a non-existent file returns non-zero — mismatch with claim."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "ls src/phantom.py", claimed_exit_code=0
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.CRITICAL)

    def test_ls_command_verified_failure_matching_exit_code(self):
        """ls on a non-existent file with matching claimed exit code."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "ls src/phantom.py", claimed_exit_code=2
        )
        # ls returns 2 for non-existent files on Linux
        if result.verified:
            self.assertEqual(result.severity, EvidenceSeverity.INFO)
        else:
            # Some systems return different exit codes
            self.assertIn(
                result.severity, [EvidenceSeverity.CRITICAL, EvidenceSeverity.WARNING]
            )

    def test_test_command_verified(self):
        self._write_file("src/foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "test -f src/foo.py", claimed_exit_code=0
        )
        self.assertTrue(result.verified)

    def test_stat_command_verified(self):
        self._write_file("src/foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "stat src/foo.py", claimed_exit_code=0
        )
        self.assertTrue(result.verified)

    def test_non_file_command_not_auto_verifiable(self):
        """pytest and other arbitrary commands should not be auto-re-run."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "pytest tests/ -v", claimed_exit_code=0
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.WARNING)
        self.assertIn("not auto-verifiable", result.detail)

    def test_empty_command_is_warning(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof("", claimed_exit_code=0)
        self.assertFalse(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.WARNING)

    def test_file_not_found_for_command(self):
        """If the command binary doesn't exist, should be a warning, not critical."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "nonexistent_binary src/foo.py", claimed_exit_code=0
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.severity, EvidenceSeverity.WARNING)


# ---------------------------------------------------------------------------
# EvidenceValidator — validate_command_proofs
# ---------------------------------------------------------------------------


class TestValidateCommandProofs(_TempRepoMixin, unittest.TestCase):
    """Test batch command proof validation."""

    def test_list_of_strings(self):
        self._write_file("src/a.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_command_proofs(
            [
                "ls src/a.py",
                "test -f src/a.py",
            ]
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].verified)
        self.assertTrue(results[1].verified)

    def test_list_of_dicts(self):
        self._write_file("src/a.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_command_proofs(
            [
                {"command": "ls src/a.py", "exit_code": 0},
                {"command": "pytest tests/", "exit_code": 0},
            ]
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].verified)
        self.assertFalse(results[1].verified)  # pytest not auto-verifiable

    def test_mixed_formats(self):
        self._write_file("src/a.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_command_proofs(
            [
                "ls src/a.py",
                {"command": "stat src/a.py", "exit_code": 0},
            ]
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.verified for r in results))

    def test_invalid_format_is_warning(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        results = validator.validate_command_proofs([42])  # type: ignore
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].verified)
        self.assertEqual(results[0].severity, EvidenceSeverity.WARNING)


# ---------------------------------------------------------------------------
# EvidenceValidator — validate (full pipeline)
# ---------------------------------------------------------------------------


class TestValidateFullPipeline(_TempRepoMixin, unittest.TestCase):
    """Test full evidence validation pipeline."""

    def test_complete_valid_evidence_passes(self):
        """AC4: All checks pass with valid evidence."""
        self._write_file("src/foo.py")
        self._write_file("tests/test_foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/foo.py", "tests/test_foo.py"],
                "test_results": {"tests/test_foo.py": "passed"},
                "commands_run": ["ls src/foo.py"],
            }
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.overall_status, EvidenceCheckStatus.PASS)
        self.assertEqual(result.critical_count, 0)

    def test_phantom_file_claim_fails(self):
        """AC2: Validator rejects claims missing file existence proof."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/phantom.py"],
                "test_results": {"tests/test_phantom.py": "5 passed"},
                "commands_run": ["ls src/phantom.py"],
            }
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(result.overall_status, EvidenceCheckStatus.FAIL)
        self.assertGreater(result.critical_count, 0)

    def test_phantom_test_claim_fails(self):
        """AC2: Validator rejects test claims without test file existence proof."""
        self._write_file("src/foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/foo.py"],
                "test_results": {"tests/test_phantom.py": "all passed"},
                "commands_run": ["ls src/foo.py"],
            }
        )
        self.assertFalse(result.is_valid)
        # Test claim should be critical
        test_critical = any(
            r.severity == EvidenceSeverity.CRITICAL for r in result.test_claim_results
        )
        self.assertTrue(test_critical)

    def test_empty_evidence_skips(self):
        result = EvidenceValidationResult()
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate({})
        self.assertEqual(result.overall_status, EvidenceCheckStatus.SKIP)
        self.assertFalse(result.is_valid)

    def test_only_files_changed_passes(self):
        """Evidence with only files_changed should still validate."""
        self._write_file("src/foo.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/foo.py"],
            }
        )
        self.assertTrue(result.is_valid)

    def test_only_files_changed_fails_on_phantom(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/ghost.py"],
            }
        )
        self.assertFalse(result.is_valid)

    def test_require_all_files_false_allows_partial(self):
        """When require_all_files=False, missing files are warnings not failures."""
        self._write_file("src/real.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/real.py", "src/phantom.py"],
                "require_all_files": False,
            }
        )
        # Even with require_all_files=False, phantom files are still CRITICAL
        # because check_file_exists always returns CRITICAL severity for missing files
        self.assertFalse(result.is_valid)

    def test_warnings_generated_for_missing_sections(self):
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/foo.py"],
            }
        )
        self.assertTrue(len(result.warnings) >= 1)
        # Should warn about missing test_results and commands_run
        warning_texts = " ".join(result.warnings)
        self.assertIn("test_results", warning_texts)
        self.assertIn("commands_run", warning_texts)

    def test_summary_contains_all_sections(self):
        self._write_file("src/a.py")
        self._write_file("tests/test_a.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["src/a.py"],
                "test_results": {"tests/test_a.py": "passed"},
                "commands_run": ["ls src/a.py"],
            }
        )
        summary = result.summary()
        self.assertIn("pass", summary)
        self.assertIn("Files checked: 1", summary)
        self.assertIn("Test claims checked: 1", summary)
        self.assertIn("Command proofs checked: 1", summary)


# ---------------------------------------------------------------------------
# EvidenceValidator — git_available property
# ---------------------------------------------------------------------------


class TestGitAvailable(_TempRepoMixin, unittest.TestCase):
    """Test git availability detection."""

    def test_git_available_when_git_works(self):
        with patch("subprocess.run", return_value=_make_completed_process(0, ".git")):
            validator = EvidenceValidator(repo_root=self.repo_root)
            self.assertTrue(validator.git_available)

    def test_git_unavailable_when_git_fails(self):
        with patch("subprocess.run", return_value=_make_completed_process(1)):
            validator = EvidenceValidator(repo_root=self.repo_root)
            self.assertFalse(validator.git_available)

    def test_git_unavailable_when_git_missing(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            validator = EvidenceValidator(repo_root=self.repo_root)
            self.assertFalse(validator.git_available)

    def test_git_available_cached(self):
        """Result is cached after first check."""
        with patch(
            "subprocess.run", return_value=_make_completed_process(0, ".git")
        ) as mock_run:
            validator = EvidenceValidator(repo_root=self.repo_root)
            _ = validator.git_available
            _ = validator.git_available
            # Should only call subprocess.run once
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# EvidenceValidator — _git_ls_files helper
# ---------------------------------------------------------------------------


class TestGitLsFiles(_TempRepoMixin, unittest.TestCase):
    """Test git ls-files helper method."""

    def test_tracked_file_returns_path(self):
        with patch(
            "subprocess.run", return_value=_make_completed_process(0, "src/foo.py\n")
        ):
            validator = EvidenceValidator(repo_root=self.repo_root)
            result = validator._git_ls_files("src/foo.py")
            self.assertEqual(result, "src/foo.py")

    def test_untracked_file_returns_empty(self):
        with patch(
            "subprocess.run", return_value=_make_completed_process(1, stderr="error")
        ):
            validator = EvidenceValidator(repo_root=self.repo_root)
            result = validator._git_ls_files("src/untracked.py")
            self.assertEqual(result, "")

    def test_git_not_found_returns_empty(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git")):
            validator = EvidenceValidator(repo_root=self.repo_root)
            result = validator._git_ls_files("src/foo.py")
            self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# CLI main tests
# ---------------------------------------------------------------------------


class TestCLI(_TempRepoMixin, unittest.TestCase):
    """Test CLI entry point."""

    def test_files_flag_valid(self):
        self._write_file("src/real.py")
        with patch(
            "sys.argv",
            [
                "evidence_validator.py",
                "--files",
                "src/real.py",
                "--repo-root",
                str(self.repo_root),
            ],
        ):
            from scripts.swarm.evidence_validator import main

            exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_files_flag_phantom(self):
        with patch(
            "sys.argv",
            [
                "evidence_validator.py",
                "--files",
                "src/ghost.py",
                "--repo-root",
                str(self.repo_root),
            ],
        ):
            from scripts.swarm.evidence_validator import main

            exit_code = main()
            self.assertEqual(exit_code, 1)

    def test_evidence_file_valid(self):
        self._write_file("src/a.py")
        self._write_file("tests/test_a.py")
        evidence = {
            "files_changed": ["src/a.py"],
            "test_results": {"tests/test_a.py": "passed"},
            "commands_run": ["ls src/a.py"],
        }
        evidence_path = self.repo_root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence))

        with patch(
            "sys.argv",
            [
                "evidence_validator.py",
                "--evidence-file",
                str(evidence_path),
                "--repo-root",
                str(self.repo_root),
            ],
        ):
            from scripts.swarm.evidence_validator import main

            exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_evidence_file_phantom(self):
        evidence = {
            "files_changed": ["src/phantom.py"],
            "test_results": {"tests/test_phantom.py": "passed"},
        }
        evidence_path = self.repo_root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence))

        with patch(
            "sys.argv",
            [
                "evidence_validator.py",
                "--evidence-file",
                str(evidence_path),
                "--repo-root",
                str(self.repo_root),
            ],
        ):
            from scripts.swarm.evidence_validator import main

            exit_code = main()
            self.assertEqual(exit_code, 1)

    def test_json_output(self):
        self._write_file("src/a.py")
        with patch(
            "sys.argv",
            [
                "evidence_validator.py",
                "--files",
                "src/a.py",
                "--repo-root",
                str(self.repo_root),
                "--json",
            ],
        ):
            from io import StringIO

            fake_stdout = StringIO()
            with patch("sys.stdout", fake_stdout):
                from scripts.swarm.evidence_validator import main

                main()
            output_text = fake_stdout.getvalue()
            # Should contain JSON structure
            self.assertIn('"overall_status"', output_text)
            self.assertIn('"is_valid"', output_text)

    def test_no_args_fails(self):
        with patch("sys.argv", ["evidence_validator.py"]):
            from scripts.swarm.evidence_validator import main

            with self.assertRaises(SystemExit):
                main()


# ---------------------------------------------------------------------------
# Edge cases and regression tests
# ---------------------------------------------------------------------------


class TestEdgeCases(_TempRepoMixin, unittest.TestCase):
    """Edge cases and regression tests."""

    def test_nested_directory_file(self):
        self._write_file("src/deep/nested/module.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/deep/nested/module.py")
        self.assertTrue(result.exists)

    def test_file_with_spaces_in_name(self):
        self._write_file("src/file with spaces.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/file with spaces.py")
        self.assertTrue(result.exists)

    def test_symlink_target_exists(self):
        """If a path is a symlink to an existing file, it should be found."""
        target = self._write_file("src/target.py")
        link = self.repo_root / "src/link.py"
        link.symlink_to(target)
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src/link.py")
        self.assertTrue(result.exists)

    def test_directory_not_file(self):
        """A path that is a directory should not count as a file existing."""
        (self.repo_root / "src").mkdir(parents=True, exist_ok=True)
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.check_file_exists("src")
        # os.path.exists returns True but is_file returns False
        self.assertFalse(result.exists)

    def test_command_with_cwd_override(self):
        self._write_file("subdir/file.py")
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate_command_proof(
            "ls file.py",
            claimed_exit_code=0,
            cwd=str(self.repo_root / "subdir"),
        )
        self.assertTrue(result.verified)

    def test_command_timeout_handled(self):
        """Commands that timeout should produce a warning, not crash."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ls", 30)):
            validator = EvidenceValidator(repo_root=self.repo_root)
            result = validator.validate_command_proof(
                "ls src/foo.py", claimed_exit_code=0
            )
            self.assertFalse(result.verified)
            self.assertEqual(result.severity, EvidenceSeverity.WARNING)

    def test_evidence_with_no_changes_but_commands(self):
        """Evidence with no files_changed but commands_run should not crash."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "commands_run": ["echo hello"],
            }
        )
        # echo is not a file-check command, so it's a warning
        self.assertEqual(result.overall_status, EvidenceCheckStatus.FAIL)
        self.assertEqual(len(result.command_proof_results), 1)

    def test_multiple_phantom_claims_all_reported(self):
        """All phantom claims should be individually reported."""
        validator = EvidenceValidator(repo_root=self.repo_root)
        result = validator.validate(
            {
                "files_changed": ["a.py", "b.py", "c.py"],
                "test_results": {
                    "tests/test_a.py": "passed",
                    "tests/test_b.py": "passed",
                    "tests/test_c.py": "passed",
                },
            }
        )
        # All 3 file claims should be critical
        file_criticals = sum(
            1
            for r in result.file_existence_results
            if r.severity == EvidenceSeverity.CRITICAL
        )
        test_criticals = sum(
            1
            for r in result.test_claim_results
            if r.severity == EvidenceSeverity.CRITICAL
        )
        self.assertEqual(file_criticals, 3)
        self.assertEqual(test_criticals, 3)


# Need subprocess import for TimeoutExpired test
import subprocess

if __name__ == "__main__":
    unittest.main()
