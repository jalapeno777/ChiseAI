"""Tests for brain evaluation CI script.

Tests the detection of brain changes, evaluation script behavior,
and output format verification.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Import the module under test using importlib (similar to other CI tests)
MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "run_brain_evaluation.py"
)
SPEC = importlib.util.spec_from_file_location("run_brain_evaluation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_brain_evaluation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_brain_evaluation
SPEC.loader.exec_module(run_brain_evaluation)


class TestDetectChangedFiles:
    """Tests for detect_changed_files function."""

    def test_detect_changed_files_success(self, tmp_path: Path) -> None:
        """Test successful detection of changed files."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="src/brain/batch_evaluator.py\nbrains/v1/config.yaml\n",
                returncode=0,
            )

            result = run_brain_evaluation.detect_changed_files("HEAD~1", "HEAD")

            assert result == ["src/brain/batch_evaluator.py", "brains/v1/config.yaml"]
            mock_run.assert_called_once_with(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_detect_changed_files_failure(self) -> None:
        """Test handling of git command failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            result = run_brain_evaluation.detect_changed_files()

            assert result == []

    def test_detect_changed_files_empty(self) -> None:
        """Test handling of no changed files."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            result = run_brain_evaluation.detect_changed_files()

            assert result == []


class TestIsBrainRelatedChange:
    """Tests for is_brain_related_change function."""

    def test_src_brain_path(self) -> None:
        """Test detection of src/brain/ changes."""
        assert run_brain_evaluation.is_brain_related_change(
            "src/brain/batch_evaluator.py"
        )
        assert run_brain_evaluation.is_brain_related_change("src/brain/__init__.py")
        assert run_brain_evaluation.is_brain_related_change(
            "src/brain/deep/nested/file.py"
        )

    def test_brains_path(self) -> None:
        """Test detection of brains/ changes."""
        assert run_brain_evaluation.is_brain_related_change("brains/v1/config.yaml")
        assert run_brain_evaluation.is_brain_related_change("brains/README.md")
        assert run_brain_evaluation.is_brain_related_change("brains/brain_v2.py")

    def test_non_brain_path(self) -> None:
        """Test rejection of non-brain paths."""
        assert not run_brain_evaluation.is_brain_related_change("src/api/main.py")
        assert not run_brain_evaluation.is_brain_related_change("tests/test_brain.py")
        assert not run_brain_evaluation.is_brain_related_change("docs/README.md")
        assert not run_brain_evaluation.is_brain_related_change(".woodpecker.yml")


class TestDetectChangedBrainVersions:
    """Tests for detect_changed_brain_versions function."""

    def test_no_brain_files(self) -> None:
        """Test with no brain-related files."""
        changed_files = ["src/api/main.py", "tests/test_api.py"]
        result = run_brain_evaluation.detect_changed_brain_versions(changed_files)
        assert result == []

    def test_with_brain_files(self) -> None:
        """Test detection of versions from brain files."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="abc1234\n", returncode=0)

            changed_files = ["src/brain/batch_evaluator.py", "src/api/main.py"]
            result = run_brain_evaluation.detect_changed_brain_versions(changed_files)

            assert result == ["brain-abc1234"]

    def test_with_brains_directory(self) -> None:
        """Test detection of versions from brains/ directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="def5678\n", returncode=0)

            changed_files = ["brains/v1/config.yaml"]
            result = run_brain_evaluation.detect_changed_brain_versions(changed_files)

            assert result == ["brain-def5678"]

    def test_git_failure_fallback(self) -> None:
        """Test fallback to timestamp when git fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            changed_files = ["src/brain/test.py"]
            result = run_brain_evaluation.detect_changed_brain_versions(changed_files)

            # Should return a timestamp-based version
            assert len(result) == 1
            assert result[0].startswith("brain-")
            # Should contain date format (YYYYMMDD-HHMMSS)
            assert len(result[0]) == len("brain-YYYYMMDD-HHMMSS")


class TestGenerateCiOutput:
    """Tests for generate_ci_output function."""

    def test_successful_summary(self) -> None:
        """Test output generation for successful evaluation."""
        summary = {
            "versions_evaluated": 2,
            "successful": 2,
            "failed": 0,
            "results_file": "_bmad-output/brain-eval/results.json",
            "versions": ["brain-v1", "brain-v2"],
            "details": [
                {
                    "brain_version": "brain-v1",
                    "status": "completed",
                    "f1_score": 0.85,
                    "win_rate": 0.72,
                    "sharpe_ratio": 1.5,
                },
                {
                    "brain_version": "brain-v2",
                    "status": "completed",
                    "f1_score": 0.88,
                    "win_rate": 0.75,
                    "sharpe_ratio": 1.7,
                },
            ],
        }

        output = run_brain_evaluation.generate_ci_output(summary)

        assert "Brain Evaluation Results" in output
        assert "Versions evaluated: 2" in output
        assert "Successful: 2" in output
        assert "Failed: 0" in output
        assert "brain-v1: completed" in output
        assert "brain-v2: completed" in output
        assert "F1: 0.8500" in output

    def test_failed_summary(self) -> None:
        """Test output generation with failures."""
        summary = {
            "versions_evaluated": 2,
            "successful": 1,
            "failed": 1,
            "results_file": "_bmad-output/brain-eval/results.json",
            "versions": ["brain-v1", "brain-v2"],
            "details": [
                {
                    "brain_version": "brain-v1",
                    "status": "completed",
                    "f1_score": 0.85,
                    "win_rate": 0.72,
                    "sharpe_ratio": 1.5,
                },
                {
                    "brain_version": "brain-v2",
                    "status": "failed",
                    "error_message": "Evaluation timeout",
                },
            ],
        }

        output = run_brain_evaluation.generate_ci_output(summary)

        assert "Successful: 1" in output
        assert "Failed: 1" in output
        assert "brain-v2: failed" in output
        assert "Error: Evaluation timeout" in output

    def test_error_summary(self) -> None:
        """Test output generation with error."""
        summary = {
            "versions_evaluated": 1,
            "successful": 0,
            "failed": 1,
            "error": "Batch evaluation failed: Connection error",
            "versions": ["brain-v1"],
        }

        output = run_brain_evaluation.generate_ci_output(summary)

        assert "ERROR: Batch evaluation failed: Connection error" in output


class TestRunBatchEvaluation:
    """Tests for run_batch_evaluation function."""

    def test_successful_evaluation(self, tmp_path: Path) -> None:
        """Test successful batch evaluation."""
        versions = ["brain-v1", "brain-v2"]
        output_dir = tmp_path / "brain-eval"

        with patch("asyncio.run") as mock_run:
            # Create mock results
            mock_result1 = Mock()
            mock_result1.is_successful.return_value = True
            mock_result1.to_dict.return_value = {
                "brain_version": "brain-v1",
                "status": "completed",
            }

            mock_result2 = Mock()
            mock_result2.is_successful.return_value = True
            mock_result2.to_dict.return_value = {
                "brain_version": "brain-v2",
                "status": "completed",
            }

            mock_run.return_value = [mock_result1, mock_result2]

            summary = run_brain_evaluation.run_batch_evaluation(
                versions=versions,
                output_dir=output_dir,
                timeout=300.0,
            )

            assert summary["versions_evaluated"] == 2
            assert summary["successful"] == 2
            assert summary["failed"] == 0
            assert (output_dir / "results.json").exists()
            assert (output_dir / "summary.json").exists()

    def test_evaluation_failure(self, tmp_path: Path) -> None:
        """Test handling of evaluation failure."""
        versions = ["brain-v1"]
        output_dir = tmp_path / "brain-eval"

        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Connection error")

            summary = run_brain_evaluation.run_batch_evaluation(
                versions=versions,
                output_dir=output_dir,
            )

            assert summary["versions_evaluated"] == 1
            assert summary["successful"] == 0
            assert summary["failed"] == 1
            assert "error" in summary


class TestMain:
    """Tests for main function."""

    def test_no_brain_changes_no_force(self) -> None:
        """Test that evaluation is skipped when no brain changes."""
        with patch.object(
            run_brain_evaluation,
            "detect_changed_files",
            return_value=["src/api/main.py"],
        ), patch("sys.argv", ["run_brain_evaluation.py"]):
            result = run_brain_evaluation.main()
            assert result == 0

    def test_explicit_versions(self, tmp_path: Path) -> None:
        """Test running with explicit version list."""
        with patch.object(
            run_brain_evaluation,
            "run_batch_evaluation",
            return_value={
                "versions_evaluated": 1,
                "successful": 1,
                "failed": 0,
                "results_file": str(tmp_path / "results.json"),
                "versions": ["brain-v1"],
                "details": [],
            },
        ), patch(
            "sys.argv", ["run_brain_evaluation.py", "--versions", "brain-v1"]
        ):
            result = run_brain_evaluation.main()
            assert result == 0

    def test_force_flag(self) -> None:
        """Test that --force runs evaluation even without brain changes."""
        with patch.object(
            run_brain_evaluation,
            "detect_changed_files",
            return_value=["src/api/main.py"],
        ), patch.object(
            run_brain_evaluation,
            "run_batch_evaluation",
            return_value={
                "versions_evaluated": 1,
                "successful": 1,
                "failed": 0,
                "results_file": "results.json",
                "versions": ["brain-abc1234"],
                "details": [],
            },
        ), patch("sys.argv", ["run_brain_evaluation.py", "--force"]):
            result = run_brain_evaluation.main()
            assert result == 0


class TestOutputFormat:
    """Tests for output format verification."""

    def test_summary_json_structure(self, tmp_path: Path) -> None:
        """Verify summary.json has expected structure."""
        versions = ["brain-test"]
        output_dir = tmp_path / "brain-eval"

        with patch("asyncio.run") as mock_run:
            mock_result = Mock()
            mock_result.is_successful.return_value = True
            mock_result.to_dict.return_value = {
                "brain_version": "brain-test",
                "status": "completed",
                "accuracy": 0.8,
                "precision": 0.75,
                "recall": 0.85,
                "f1_score": 0.8,
                "win_rate": 0.7,
                "sharpe_ratio": 1.2,
                "max_drawdown": 0.15,
                "duration_seconds": 10.5,
                "error_message": None,
                "timestamp": "2026-02-14T18:30:00",
            }

            mock_run.return_value = [mock_result]

            run_brain_evaluation.run_batch_evaluation(
                versions=versions,
                output_dir=output_dir,
            )

            # Verify summary.json structure
            with open(output_dir / "summary.json") as f:
                summary = json.load(f)

            assert "versions_evaluated" in summary
            assert "successful" in summary
            assert "failed" in summary
            assert "results_file" in summary
            assert "versions" in summary
            assert "details" in summary
            assert isinstance(summary["details"], list)

    def test_results_json_structure(self, tmp_path: Path) -> None:
        """Verify results.json has expected structure."""

        versions = ["brain-test"]
        output_dir = tmp_path / "brain-eval"

        with patch("asyncio.run") as mock_run:
            mock_result = Mock()
            mock_result.is_successful.return_value = True
            mock_result.to_dict.return_value = {
                "brain_version": "brain-test",
                "status": "completed",
                "accuracy": 0.8,
                "precision": 0.75,
                "recall": 0.85,
                "f1_score": 0.8,
                "win_rate": 0.7,
                "sharpe_ratio": 1.2,
                "max_drawdown": 0.15,
                "duration_seconds": 10.5,
                "error_message": None,
                "timestamp": "2026-02-14T18:30:00",
            }

            mock_run.return_value = [mock_result]

            run_brain_evaluation.run_batch_evaluation(
                versions=versions,
                output_dir=output_dir,
            )

            # Verify results.json structure (saved by EvaluationPersistence)
            with open(output_dir / "results.json") as f:
                results = json.load(f)

            assert "saved_at" in results
            assert "count" in results
            assert "results" in results
            assert isinstance(results["results"], list)
            assert len(results["results"]) == 1

            # Verify result structure
            result = results["results"][0]
            assert "brain_version" in result
            assert "status" in result
            assert "timestamp" in result
