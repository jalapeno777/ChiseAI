"""Tests that session.py cmd_validate_evidence uses evidence validator in blocking mode.

Verifies three properties:
1. cmd_validate_evidence returns the validator exit code (0=pass, 1=fail).
2. --strict flag is properly forwarded to the validator subprocess.
3. Invalid evidence blocks (exit code 1); valid evidence passes (exit code 0).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.swarm.session import build_parser, cmd_validate_evidence

VALID_EVIDENCE = """\
Files changed:
  - scripts/swarm/evidence_validator.py
Commands run:
  - ls -la scripts/swarm/evidence_validator.py
  - pytest tests/test_swarm/test_evidence_validator.py
Verification:
  - All tests passed
"""

INVALID_EVIDENCE_NO_PROOF = """\
Files changed:
  - scripts/swarm/evidence_validator.py
Commands run:
  - echo 'did something'
Verification:
  - Looks good
"""

INVALID_EVIDENCE_MISSING_SECTIONS = """\
I did some work.
"""


class TestCmdValidateEvidenceReturnsExitCode:
    """Verify that cmd_validate_evidence propagates the validator exit code."""

    def test_valid_evidence_returns_zero(self):
        """Valid evidence file must produce exit code 0."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(VALID_EVIDENCE)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert exit_code == 0, "Valid evidence should return exit code 0"
        finally:
            temp_path.unlink()

    def test_invalid_evidence_returns_one(self):
        """Invalid evidence file must produce exit code 1 (blocking)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(INVALID_EVIDENCE_NO_PROOF)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert (
                exit_code == 1
            ), "Invalid evidence (missing file proof) should return exit code 1"
        finally:
            temp_path.unlink()

    def test_missing_evidence_file_returns_one(self):
        """Nonexistent evidence file must produce exit code 1."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "validate-evidence",
                "--evidence-file",
                "/nonexistent/evidence.md",
            ]
        )
        exit_code = cmd_validate_evidence(args)
        assert exit_code == 1, "Missing evidence file should return exit code 1"

    def test_invalid_evidence_missing_sections_returns_one(self):
        """Evidence missing required sections must produce exit code 1."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(INVALID_EVIDENCE_MISSING_SECTIONS)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert (
                exit_code == 1
            ), "Evidence missing all required sections should return exit code 1"
        finally:
            temp_path.unlink()


class TestStrictFlagHandling:
    """Verify --strict flag is properly forwarded to the validator subprocess."""

    def test_strict_flag_added_to_command(self):
        """When --strict is passed, the subprocess command must include --strict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(INVALID_EVIDENCE_NO_PROOF)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                    "--strict",
                ]
            )

            # Patch subprocess.run to inspect the command passed
            captured_cmd = []
            original_run = __import__("subprocess").run

            def spy_run(cmd, **kwargs):
                captured_cmd.append(cmd)
                return original_run(cmd, **kwargs)

            with patch("subprocess.run", side_effect=spy_run):
                cmd_validate_evidence(args)

            assert len(captured_cmd) == 1, "subprocess.run should be called once"
            assert (
                "--strict" in captured_cmd[0]
            ), "--strict flag must be forwarded to the validator subprocess"
        finally:
            temp_path.unlink()

    def test_no_strict_flag_omitted_from_command(self):
        """When --strict is NOT passed, the subprocess command must NOT include --strict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(VALID_EVIDENCE)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )

            captured_cmd = []
            original_run = __import__("subprocess").run

            def spy_run(cmd, **kwargs):
                captured_cmd.append(cmd)
                return original_run(cmd, **kwargs)

            with patch("subprocess.run", side_effect=spy_run):
                cmd_validate_evidence(args)

            assert len(captured_cmd) == 1, "subprocess.run should be called once"
            assert (
                "--strict" not in captured_cmd[0]
            ), "--strict flag must NOT be in command when not requested"
        finally:
            temp_path.unlink()

    def test_strict_and_non_strict_both_block_on_invalid(self):
        """Both --strict and no-strict block on invalid evidence.

        This verifies the blocking behavior: the validator defaults to strict=True,
        so invalid evidence always fails regardless of the --strict flag.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(INVALID_EVIDENCE_NO_PROOF)
            temp_path = Path(f.name)

        try:
            parser = build_parser()

            # Without --strict
            args_no_strict = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )
            exit_no_strict = cmd_validate_evidence(args_no_strict)

            # With --strict
            args_strict = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                    "--strict",
                ]
            )
            exit_strict = cmd_validate_evidence(args_strict)

            assert (
                exit_no_strict == 1
            ), "Invalid evidence must block (exit 1) even without --strict flag"
            assert (
                exit_strict == 1
            ), "Invalid evidence must block (exit 1) with --strict flag"
        finally:
            temp_path.unlink()


class TestBlockingBehaviorIntegration:
    """Integration tests demonstrating end-to-end blocking behavior."""

    def test_valid_evidence_with_completion_report_passes(self):
        """Complete evidence with worker completion report must pass."""
        full_evidence = VALID_EVIDENCE + """\
WORKER_COMPLETION_REPORT:
story_id: ST-123
branch: feature/ST-123-test
head_sha: abc123def
test_summary: 30 passed in 2.06s
status_sync_proof: Validated
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(full_evidence)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                    "--strict",
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert (
                exit_code == 0
            ), "Complete valid evidence with completion report should pass"
        finally:
            temp_path.unlink()

    def test_evidence_with_missing_file_proof_blocks(self):
        """Evidence without file existence proof commands must block."""
        evidence_no_proof = """\
Files changed:
  - scripts/swarm/session.py
Commands run:
  - python3 scripts/swarm/session.py verify
Verification:
  - session.verify: OK
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(evidence_no_proof)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert (
                exit_code == 1
            ), "Evidence without file existence proof must block (exit 1)"
        finally:
            temp_path.unlink()

    def test_evidence_with_partial_completion_report_blocks(self):
        """Evidence with incomplete worker completion report must block."""
        partial_report = VALID_EVIDENCE + """\
WORKER_COMPLETION_REPORT:
story_id: ST-456
branch: feature/ST-456-test
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(partial_report)
            temp_path = Path(f.name)

        try:
            parser = build_parser()
            args = parser.parse_args(
                [
                    "validate-evidence",
                    "--evidence-file",
                    str(temp_path),
                    "--strict",
                ]
            )
            exit_code = cmd_validate_evidence(args)
            assert (
                exit_code == 1
            ), "Evidence with incomplete completion report must block (exit 1)"
        finally:
            temp_path.unlink()
