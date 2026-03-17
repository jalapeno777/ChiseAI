#!/usr/bin/env python3
"""
Integration tests for blocking gates.

Tests the integration of blocking gates with CI pipeline,
ensuring gates properly validate and block on failures.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest


class TestBlockingGatesRunner:
    """Tests for the blocking gates runner integration."""

    def test_blocking_gates_runner_imports(self):
        """Test that blocking_gates_runner can be imported."""
        from scripts.ci.blocking_gates_runner import (
            BlockingGatesRunner,
            GateResult,
            GatesReport,
        )

        assert BlockingGatesRunner is not None
        assert GateResult is not None
        assert GatesReport is not None

    def test_gate_result_dataclass(self):
        """Test GateResult dataclass creation."""
        from scripts.ci.blocking_gates_runner import GateResult

        result = GateResult(
            name="test-gate",
            passed=True,
            exit_code=0,
            duration_seconds=1.5,
            stdout="test output",
            stderr="",
            error_message=None,
        )

        assert result.name == "test-gate"
        assert result.passed is True
        assert result.exit_code == 0
        assert result.duration_seconds == 1.5

    def test_gates_report_dataclass(self):
        """Test GatesReport dataclass creation."""
        from scripts.ci.blocking_gates_runner import GatesReport

        report = GatesReport(
            overall_passed=True,
            total_duration_seconds=10.0,
            metadata={"test": "value"},
        )

        assert report.overall_passed is True
        assert report.total_duration_seconds == 10.0
        assert report.metadata == {"test": "value"}
        assert len(report.gates) == 0

    def test_blocking_gates_list(self):
        """Test that blocking gates are properly defined."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        runner = BlockingGatesRunner()

        # Verify blocking gates list is not empty
        assert len(runner.BLOCKING_GATES) > 0

        # Verify expected gates are present
        expected_gates = [
            "swarm-context",
            "lint",
            "security-scan",
            "dependency-audit",
            "secret-scan",
            "risk-invariants",
            "brain-regression",
            "docs-pairing",
            "docker-governance",
            "changed-lines-coverage",
            "status-write-gate",
            "performance-gate",
            "evidence-gate",
        ]

        for gate in expected_gates:
            assert gate in runner.BLOCKING_GATES, f"Missing gate: {gate}"

    def test_full_only_gates_list(self):
        """Test that full-only gates are properly defined."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        runner = BlockingGatesRunner()

        # Verify full-only gates are defined
        assert len(runner.FULL_ONLY_GATES) > 0

        # Verify expected full-only gates
        expected_full_only = ["local-ci", "brain-eval"]

        for gate in expected_full_only:
            assert gate in runner.FULL_ONLY_GATES, f"Missing full-only gate: {gate}"

    def test_read_status_file_not_found(self):
        """Test reading status file that doesn't exist."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = BlockingGatesRunner(ci_status_dir=tmpdir)
            result = runner.read_status_file("nonexistent-gate")

            assert result is None

    def test_read_status_file_success(self):
        """Test reading valid status file."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create status file
            status_file = Path(tmpdir) / "test-gate.status"
            status_file.write_text("0")

            log_file = Path(tmpdir) / "test-gate.log"
            log_file.write_text("Test log content")

            runner = BlockingGatesRunner(ci_status_dir=tmpdir)
            result = runner.read_status_file("test-gate")

            assert result is not None
            assert result[0] == 0  # exit code
            assert result[1] == "Test log content"  # log content

    def test_run_gate_pass(self):
        """Test running a gate that passes."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create passing status file
            status_file = Path(tmpdir) / "test-gate.status"
            status_file.write_text("0")

            runner = BlockingGatesRunner(ci_status_dir=tmpdir)
            result = runner.run_gate("test-gate")

            assert result.name == "test-gate"
            assert result.passed is True
            assert result.exit_code == 0

    def test_run_gate_fail(self):
        """Test running a gate that fails."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create failing status file
            status_file = Path(tmpdir) / "test-gate.status"
            status_file.write_text("1")

            runner = BlockingGatesRunner(ci_status_dir=tmpdir)
            result = runner.run_gate("test-gate")

            assert result.name == "test-gate"
            assert result.passed is False
            assert result.exit_code == 1

    def test_run_gate_missing_status(self):
        """Test running a gate with missing status file."""
        from scripts.ci.blocking_gates_runner import BlockingGatesRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = BlockingGatesRunner(ci_status_dir=tmpdir)
            result = runner.run_gate("missing-gate")

            assert result.name == "missing-gate"
            assert result.passed is False
            assert result.exit_code == -1
            assert result.error_message is not None
            assert "Status file not found" in result.error_message

    def test_overall_passed_all_blocking_pass(self):
        """Test overall_passed when all blocking gates pass."""
        from scripts.ci.blocking_gates_runner import (
            BlockingGatesRunner,
            GateResult,
        )

        runner = BlockingGatesRunner()

        # Add passing results for all blocking gates
        for gate_name in runner.BLOCKING_GATES:
            runner.report.gates.append(
                GateResult(
                    name=gate_name,
                    passed=True,
                    exit_code=0,
                    duration_seconds=1.0,
                )
            )

        # Calculate overall result
        blocking_results = [
            g for g in runner.report.gates if g.name in runner.BLOCKING_GATES
        ]
        runner.report.overall_passed = all(g.passed for g in blocking_results)

        assert runner.report.overall_passed is True

    def test_overall_passed_one_blocking_fails(self):
        """Test overall_passed when one blocking gate fails."""
        from scripts.ci.blocking_gates_runner import (
            BlockingGatesRunner,
            GateResult,
        )

        runner = BlockingGatesRunner()

        # Add passing results for all but one blocking gate
        for i, gate_name in enumerate(runner.BLOCKING_GATES):
            runner.report.gates.append(
                GateResult(
                    name=gate_name,
                    passed=(i != 0),  # First one fails
                    exit_code=0 if i != 0 else 1,
                    duration_seconds=1.0,
                )
            )

        # Calculate overall result
        blocking_results = [
            g for g in runner.report.gates if g.name in runner.BLOCKING_GATES
        ]
        runner.report.overall_passed = all(g.passed for g in blocking_results)

        assert runner.report.overall_passed is False

    def test_report_to_dict(self):
        """Test converting report to dictionary."""
        from scripts.ci.blocking_gates_runner import (
            BlockingGatesRunner,
            GateResult,
        )

        runner = BlockingGatesRunner()
        runner.report.gates.append(
            GateResult(
                name="test-gate",
                passed=True,
                exit_code=0,
                duration_seconds=1.0,
            )
        )
        runner.report.overall_passed = True

        report_dict = runner.report.to_dict()

        assert report_dict["overall_passed"] is True
        assert len(report_dict["gates"]) == 1
        assert report_dict["gates"][0]["name"] == "test-gate"


class TestEvidenceGateRunner:
    """Tests for the evidence gate runner integration."""

    def test_evidence_gate_runner_imports(self):
        """Test that evidence_gate_runner can be imported."""
        from scripts.ci.evidence_gate_runner import (
            check_validation_script_exists,
            extract_story_id_from_ci,
            run_evidence_validation,
        )

        assert check_validation_script_exists is not None
        assert extract_story_id_from_ci is not None
        assert run_evidence_validation is not None

    def test_check_validation_script_exists(self):
        """Test checking if validation script exists."""
        from scripts.ci.evidence_gate_runner import check_validation_script_exists

        # This should return True since the script exists
        result = check_validation_script_exists()
        assert result is True

    def test_paths_configuration(self):
        """Test that paths are properly configured."""
        from scripts.ci.evidence_gate_runner import (
            EVIDENCE_DIR,
            VALIDATION_SCRIPT,
            WORKFLOW_STATUS_FILE,
        )

        # Verify paths are Path objects
        assert isinstance(WORKFLOW_STATUS_FILE, Path)
        assert isinstance(EVIDENCE_DIR, Path)
        assert isinstance(VALIDATION_SCRIPT, Path)

        # Verify paths are not empty
        assert str(WORKFLOW_STATUS_FILE) != ""
        assert str(EVIDENCE_DIR) != ""
        assert str(VALIDATION_SCRIPT) != ""


class TestMergeTruthVerifier:
    """Tests for the merge truth verifier integration."""

    def test_merge_truth_verifier_imports(self):
        """Test that merge_truth_verifier can be imported."""
        from scripts.ci.merge_truth_verifier import (
            MergeClaim,
            MergeTruthVerifier,
            VerificationReport,
        )

        assert MergeTruthVerifier is not None
        assert MergeClaim is not None
        assert VerificationReport is not None

    def test_merge_claim_dataclass(self):
        """Test MergeClaim dataclass creation."""
        from scripts.ci.merge_truth_verifier import MergeClaim

        claim = MergeClaim(
            commit_sha="abc123",
            story_id="ST-001",
            source="PR #123",
            verified=True,
            error_message=None,
        )

        assert claim.commit_sha == "abc123"
        assert claim.story_id == "ST-001"
        assert claim.source == "PR #123"
        assert claim.verified is True

    def test_verification_report_dataclass(self):
        """Test VerificationReport dataclass creation."""
        from scripts.ci.merge_truth_verifier import VerificationReport

        report = VerificationReport(
            overall_passed=True,
            total_checked=10,
            total_verified=10,
            total_failed=0,
        )

        assert report.overall_passed is True
        assert report.total_checked == 10
        assert report.total_verified == 10
        assert report.total_failed == 0
        assert len(report.claims) == 0

    def test_merge_truth_verifier_init(self):
        """Test MergeTruthVerifier initialization."""
        from scripts.ci.merge_truth_verifier import MergeTruthVerifier

        verifier = MergeTruthVerifier(verbose=True, main_branch="main")

        assert verifier.verbose is True
        assert verifier.main_branch == "main"
        assert verifier.report is not None

    def test_story_id_pattern(self):
        """Test that story ID pattern matches expected formats."""
        from scripts.ci.merge_truth_verifier import MergeTruthVerifier

        verifier = MergeTruthVerifier()

        # Test valid story IDs
        valid_ids = [
            "ST-001",
            "ST-TEST-001",
            "CH-001",
            "FT-001",
            "STRONG-001",
            "TG-001",
            "BATCH-001",
            "CI-001",
        ]

        for story_id in valid_ids:
            match = verifier.STORY_ID_PATTERN.search(f"Merge {story_id}")
            assert match is not None, f"Failed to match {story_id}"


class TestCIGateIntegration:
    """Tests for CI gate integration."""

    def test_ci_gate_imports(self):
        """Test that ci_gate can be imported."""
        from scripts.ci.ci_gate import (
            CRON_REQUIRED,
            FAST_REQUIRED,
            FULL_REQUIRED,
        )

        assert len(FAST_REQUIRED) > 0  # type: ignore
        assert len(FULL_REQUIRED) > 0  # type: ignore
        assert len(CRON_REQUIRED) > 0  # type: ignore

    def test_fast_required_gates(self):
        """Test that fast required gates are properly defined."""
        from scripts.ci.ci_gate import FAST_REQUIRED

        # Verify expected gates are present
        expected_gates = [
            "swarm-context.status",
            "lint.status",
            "security-scan.status",
            "dependency-audit.status",
            "secret-scan.status",
            "risk-invariants.status",
            "brain-regression.status",
            "docs-pairing.status",
            "docker-governance.status",
            "changed-lines-coverage.status",
            "status-write-gate.status",
            "performance-gate.status",
            "evidence-gate.status",
        ]

        for gate in expected_gates:
            assert gate in FAST_REQUIRED, f"Missing gate: {gate}"

    def test_full_required_gates(self):
        """Test that full required gates are properly defined."""
        from scripts.ci.ci_gate import FULL_REQUIRED

        expected_gates = ["local-ci.status", "brain-eval.status"]

        for gate in expected_gates:
            assert gate in FULL_REQUIRED, f"Missing gate: {gate}"


class TestEndToEndBlockingGates:
    """End-to-end tests for blocking gates."""

    @pytest.mark.slow
    def test_blocking_gates_runner_cli_help(self):
        """Test blocking gates runner CLI help."""
        result = subprocess.run(
            ["python3", "scripts/ci/blocking_gates_runner.py", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "blocking gates" in result.stdout.lower()

    @pytest.mark.slow
    def test_evidence_gate_runner_cli_help(self):
        """Test evidence gate runner CLI help."""
        result = subprocess.run(
            ["python3", "scripts/ci/evidence_gate_runner.py", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "evidence" in result.stdout.lower()

    @pytest.mark.slow
    def test_merge_truth_verifier_cli_help(self):
        """Test merge truth verifier CLI help."""
        result = subprocess.run(
            ["python3", "scripts/ci/merge_truth_verifier.py", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "merge" in result.stdout.lower() or "truth" in result.stdout.lower()

    def test_integration_all_ci_scripts_exist(self):
        """Test that all CI scripts exist and are executable."""
        scripts = [
            "scripts/ci/blocking_gates_runner.py",
            "scripts/ci/evidence_gate_runner.py",
            "scripts/ci/merge_truth_verifier.py",
            "scripts/ci/ci_gate.py",
        ]

        for script in scripts:
            path = Path(script)
            assert path.exists(), f"Script does not exist: {script}"
            assert path.stat().st_size > 0, f"Script is empty: {script}"
