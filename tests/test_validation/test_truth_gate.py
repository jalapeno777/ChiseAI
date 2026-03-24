"""Tests for truth gate validation tool."""

from __future__ import annotations

import json
import subprocess

# Add parent directories to path
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from truth_gate_checks.merge_truth import (
    check_merge_truth,
    verify_commit_on_branch,
)
from truth_gate_checks.test_counts import (
    check_test_counts,
    find_story_test_count,
    infer_test_path_from_story,
    run_pytest_collect,
)
from truth_gate_checks.test_counts import (
    find_story_in_workflow as find_story_in_workflow_for_tests,
)
from truth_gate_checks.workflow_status import (
    check_workflow_status,
    find_story_in_workflow,
    verify_file_exists,
)


class TestFindStoryInWorkflow:
    """Tests for find_story_in_workflow function."""

    def test_find_story_in_in_progress(self):
        """Test finding story in in_progress list."""
        workflow_data = {
            "in_progress": [
                {"id": "STORY-001", "title": "Test Story"},
            ],
            "completed": [],
            "metadata": {"recent_changes": []},
        }
        result = find_story_in_workflow("STORY-001", workflow_data)
        assert result is not None
        assert result["id"] == "STORY-001"

    def test_find_story_in_completed(self):
        """Test finding story in completed list."""
        workflow_data = {
            "in_progress": [],
            "completed": [
                {"id": "STORY-002", "title": "Completed Story"},
            ],
            "metadata": {"recent_changes": []},
        }
        result = find_story_in_workflow("STORY-002", workflow_data)
        assert result is not None
        assert result["id"] == "STORY-002"

    def test_find_story_in_recent_changes(self):
        """Test finding story in recent_changes."""
        workflow_data = {
            "in_progress": [],
            "completed": [],
            "metadata": {
                "recent_changes": [
                    {"story_id": "STORY-003", "action": "completed"},
                ]
            },
        }
        result = find_story_in_workflow("STORY-003", workflow_data)
        assert result is not None
        assert result["story_id"] == "STORY-003"

    def test_find_story_not_found(self):
        """Test when story is not found."""
        workflow_data = {
            "in_progress": [],
            "completed": [],
            "metadata": {"recent_changes": []},
        }
        result = find_story_in_workflow("NONEXISTENT", workflow_data)
        assert result is None


class TestVerifyFileExists:
    """Tests for verify_file_exists function."""

    def test_file_exists_on_disk(self, tmp_path):
        """Test verifying file that exists on disk."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = verify_file_exists("test.py", tmp_path)
        assert result["passed"] is True
        assert "exists" in result["message"]

    @patch("subprocess.run")
    def test_file_tracked_in_git(self, mock_run, tmp_path):
        """Test verifying file tracked in git."""
        mock_run.return_value = Mock(returncode=0, stdout="test.py\n")

        result = verify_file_exists("test.py", tmp_path)
        assert result["passed"] is True
        assert "tracked" in result["message"]

    def test_file_not_found(self, tmp_path):
        """Test verifying file that doesn't exist."""
        result = verify_file_exists("nonexistent.py", tmp_path)
        assert result["passed"] is False
        assert "not found" in result["message"]


class TestCheckWorkflowStatus:
    """Tests for check_workflow_status function."""

    def test_workflow_file_not_found(self, tmp_path):
        """Test when workflow file doesn't exist."""
        result = check_workflow_status(
            story_id="STORY-001",
            workflow_file="nonexistent.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is False
        assert "not found" in result["errors"][0]

    def test_story_not_found(self, tmp_path):
        """Test when story is not in workflow."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "in_progress": [],
                    "completed": [],
                }
            )
        )

        result = check_workflow_status(
            story_id="NONEXISTENT",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is False
        assert "not found" in result["errors"][0]

    def test_story_with_files_changed(self, tmp_path):
        """Test story with files_changed verification."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "STORY-001",
                            "files_changed": ["src/test.py"],
                            "test_results": {"total_tests": 10},
                        }
                    ],
                }
            )
        )

        # Create the actual file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("# test")

        result = check_workflow_status(
            story_id="STORY-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is True
        assert len(result["checks"]) == 1

    def test_story_with_missing_file(self, tmp_path):
        """Test story with missing file in files_changed."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "STORY-001",
                            "files_changed": ["src/missing.py"],
                        }
                    ],
                }
            )
        )

        result = check_workflow_status(
            story_id="STORY-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is False

    def test_all_stories_checked_when_no_story_id(self, tmp_path):
        """Test that all stories are checked when no story_id provided."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "in_progress": [{"id": "STORY-001", "files_changed": []}],
                    "completed": [{"id": "STORY-002", "files_changed": []}],
                }
            )
        )

        result = check_workflow_status(
            story_id=None,
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["total_checks"] == 2


class TestRunPytestCollect:
    """Tests for run_pytest_collect function."""

    @patch("subprocess.run")
    def test_successful_collection(self, mock_run):
        """Test successful pytest collection."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="collected 42 items\n",
            stderr="",
        )

        result = run_pytest_collect("tests/")
        assert result["success"] is True
        assert result["test_count"] == 42

    @patch("subprocess.run")
    def test_collection_with_no_items(self, mock_run):
        """Test pytest collection with no items."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="collected 0 items\n",
            stderr="",
        )

        result = run_pytest_collect("tests/")
        assert result["success"] is True
        assert result["test_count"] == 0

    @patch("subprocess.run")
    def test_collection_timeout(self, mock_run):
        """Test pytest collection timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=120)

        result = run_pytest_collect("tests/")
        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch("subprocess.run")
    def test_collection_error(self, mock_run):
        """Test pytest collection error."""
        mock_run.side_effect = Exception("Command failed")

        result = run_pytest_collect("tests/")
        assert result["success"] is False
        assert "Command failed" in result["error"]


class TestFindStoryTestCount:
    """Tests for find_story_test_count function."""

    def test_find_in_in_progress(self):
        """Test finding test count in in_progress."""
        workflow_data = {
            "in_progress": [
                {
                    "id": "STORY-001",
                    "test_results": {"total_tests": 25},
                }
            ],
        }
        result = find_story_test_count("STORY-001", workflow_data)
        assert result == 25

    def test_find_in_completed(self):
        """Test finding test count in completed."""
        workflow_data = {
            "completed": [
                {
                    "id": "STORY-002",
                    "test_results": {"total_tests": 50},
                }
            ],
        }
        result = find_story_test_count("STORY-002", workflow_data)
        assert result == 50

    def test_find_in_recent_changes(self):
        """Test finding test count in recent_changes."""
        workflow_data = {
            "metadata": {
                "recent_changes": [
                    {
                        "story_id": "STORY-003",
                        "test_results": {"total_tests": 75},
                    }
                ]
            },
        }
        result = find_story_test_count("STORY-003", workflow_data)
        assert result == 75

    def test_not_found(self):
        """Test when story not found."""
        workflow_data = {"in_progress": [], "completed": []}
        result = find_story_test_count("NONEXISTENT", workflow_data)
        assert result is None


class TestCheckTestCounts:
    """Tests for check_test_counts function."""

    @patch("truth_gate_checks.test_counts.run_pytest_collect")
    def test_matching_counts(self, mock_collect, tmp_path):
        """Test when recorded count matches actual count."""
        mock_collect.return_value = {
            "success": True,
            "test_count": 42,
        }

        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "STORY-001",
                            "test_results": {"total_tests": 42},
                        }
                    ],
                }
            )
        )

        result = check_test_counts(
            story_id="STORY-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is True
        assert result["checks"][0]["actual"] == 42

    @patch("truth_gate_checks.test_counts.run_pytest_collect")
    def test_mismatch_counts(self, mock_collect, tmp_path):
        """Test when recorded count doesn't match actual count."""
        mock_collect.return_value = {
            "success": True,
            "test_count": 40,
        }

        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "STORY-001",
                            "test_results": {"total_tests": 42},
                        }
                    ],
                }
            )
        )

        result = check_test_counts(
            story_id="STORY-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is False

    def test_no_story_id_no_path(self, tmp_path):
        """Test when neither story_id nor path provided."""
        result = check_test_counts(
            story_id=None,
            path=None,
            repo_root=tmp_path,
        )
        # Should still work, just collect all tests
        assert "checks" in result

    @patch("truth_gate_checks.test_counts.run_pytest_collect")
    def test_pytest_failure(self, mock_collect, tmp_path):
        """Test handling of pytest failure."""
        mock_collect.return_value = {
            "success": False,
            "error": "pytest not found",
        }

        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "STORY-001",
                            "test_results": {"total_tests": 42},
                        }
                    ],
                }
            )
        )

        result = check_test_counts(
            story_id="STORY-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )
        assert result["passed"] is False
        assert "pytest" in result["errors"][0]


class TestVerifyCommitOnBranch:
    """Tests for verify_commit_on_branch function."""

    @patch("subprocess.run")
    def test_commit_on_local_main(self, mock_run):
        """Test commit on local main branch."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="* main\n  feature/test\n",
        )

        result = verify_commit_on_branch("abc123", "main")
        assert result["passed"] is True
        assert "is on main" in result["message"]

    @patch("subprocess.run")
    def test_commit_on_origin_main(self, mock_run):
        """Test commit on origin/main branch."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="origin/main\norigin/feature\n",
        )

        result = verify_commit_on_branch("abc123", "main", remote=True)
        assert result["passed"] is True
        assert "is on main" in result["message"]

    @patch("subprocess.run")
    def test_commit_not_on_branch(self, mock_run):
        """Test commit not on target branch."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="feature/other\n",
        )

        result = verify_commit_on_branch("abc123", "main")
        assert result["passed"] is False
        assert "NOT on main" in result["message"]

    @patch("subprocess.run")
    def test_commit_not_found(self, mock_run):
        """Test commit not found in repository."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="error: no such commit",
        )

        result = verify_commit_on_branch("abc123", "main")
        assert result["passed"] is False
        assert "not found" in result["message"]


class TestCheckMergeTruth:
    """Tests for check_merge_truth function."""

    @patch("truth_gate_checks.merge_truth.verify_commit_on_branch")
    def test_single_commit_on_both_branches(self, mock_verify):
        """Test single commit on both local and origin main."""
        mock_verify.side_effect = [
            {"passed": True, "message": "on main"},
            {"passed": True, "message": "on origin/main"},
        ]

        result = check_merge_truth(["abc123"])
        assert result["passed"] is True
        assert result["total_checks"] == 1

    @patch("truth_gate_checks.merge_truth.verify_commit_on_branch")
    def test_commit_not_on_local_main(self, mock_verify):
        """Test commit not on local main."""
        mock_verify.side_effect = [
            {"passed": False, "message": "NOT on main"},
            {"passed": True, "message": "on origin/main"},
        ]

        result = check_merge_truth(["abc123"])
        assert result["passed"] is False

    @patch("truth_gate_checks.merge_truth.verify_commit_on_branch")
    def test_commit_not_on_origin_main(self, mock_verify):
        """Test commit not on origin main."""
        mock_verify.side_effect = [
            {"passed": True, "message": "on main"},
            {"passed": False, "message": "NOT on origin/main"},
        ]

        result = check_merge_truth(["abc123"])
        assert result["passed"] is False

    def test_no_commits_provided(self):
        """Test when no commits provided."""
        result = check_merge_truth([])
        assert result["passed"] is False
        assert "No commits" in result["errors"][0]

    @patch("truth_gate_checks.merge_truth.verify_commit_on_branch")
    def test_multiple_commits(self, mock_verify):
        """Test multiple commits."""
        mock_verify.side_effect = [
            {"passed": True, "message": "on main"},
            {"passed": True, "message": "on origin/main"},
            {"passed": True, "message": "on main"},
            {"passed": True, "message": "on origin/main"},
        ]

        result = check_merge_truth(["abc123", "def456"])
        assert result["passed"] is True
        assert result["total_checks"] == 2


class TestTruthGateCLI:
    """Tests for truth_gate CLI."""

    @patch("truth_gate.check_workflow_status")
    def test_cli_workflow_status_check(self, mock_check):
        """Test CLI with workflow-status check."""
        mock_check.return_value = {
            "check_type": "workflow-status",
            "passed": True,
            "checks": [],
            "total_checks": 1,
            "passed_checks": 1,
            "failed_checks": 0,
            "timestamp": "2026-01-01T00:00:00Z",
        }

        from truth_gate import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["--check", "workflow-status", "--story-id", "STORY-001"]
        )
        assert args.check == "workflow-status"
        assert args.story_id == "STORY-001"

    @patch("truth_gate.check_test_counts")
    def test_cli_test_counts_check(self, mock_check):
        """Test CLI with test-counts check."""
        mock_check.return_value = {
            "check_type": "test-counts",
            "passed": True,
            "checks": [],
            "timestamp": "2026-01-01T00:00:00Z",
        }

        from truth_gate import create_parser

        parser = create_parser()
        args = parser.parse_args(["--check", "test-counts", "--path", "tests/unit/"])
        assert args.check == "test-counts"
        assert args.path == "tests/unit/"

    @patch("truth_gate.check_merge_truth")
    def test_cli_merge_truth_check(self, mock_check):
        """Test CLI with merge-truth check."""
        mock_check.return_value = {
            "check_type": "merge-truth",
            "passed": True,
            "checks": [],
            "timestamp": "2026-01-01T00:00:00Z",
        }

        from truth_gate import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["--check", "merge-truth", "--commits", "abc123", "def456"]
        )
        assert args.check == "merge-truth"
        assert args.commits == ["abc123", "def456"]

    def test_cli_json_output(self):
        """Test CLI with JSON output format."""
        from truth_gate import create_parser

        parser = create_parser()
        args = parser.parse_args(["--check", "workflow-status", "--output", "json"])
        assert args.output == "json"

    def test_cli_default_output(self):
        """Test CLI default output format."""
        from truth_gate import create_parser

        parser = create_parser()
        args = parser.parse_args(["--check", "workflow-status"])
        assert args.output == "text"


class TestTruthGateFormatOutput:
    """Tests for format_output function."""

    def test_format_pass_result_text(self):
        """Test formatting pass result in text format."""
        from truth_gate import format_output

        result = {
            "check_type": "workflow-status",
            "passed": True,
            "timestamp": "2026-01-01T00:00:00Z",
            "checks": [{"name": "Test", "passed": True, "message": "OK"}],
            "total_checks": 1,
            "passed_checks": 1,
            "failed_checks": 0,
        }

        output = format_output(result, "text")
        assert "PASS" in output
        assert "Test: OK" in output

    def test_format_fail_result_text(self):
        """Test formatting fail result in text format."""
        from truth_gate import format_output

        result = {
            "check_type": "workflow-status",
            "passed": False,
            "timestamp": "2026-01-01T00:00:00Z",
            "checks": [{"name": "Test", "passed": False, "message": "Failed"}],
            "total_checks": 1,
            "passed_checks": 0,
            "failed_checks": 1,
        }

        output = format_output(result, "text")
        assert "FAIL" in output

    def test_format_json_output(self):
        """Test formatting result as JSON."""
        from truth_gate import format_output

        result = {
            "check_type": "workflow-status",
            "passed": True,
            "timestamp": "2026-01-01T00:00:00Z",
        }

        output = format_output(result, "json")
        parsed = json.loads(output)
        assert parsed["passed"] is True

    def test_format_with_errors(self):
        """Test formatting result with errors."""
        from truth_gate import format_output

        result = {
            "check_type": "workflow-status",
            "passed": False,
            "timestamp": "2026-01-01T00:00:00Z",
            "errors": ["Error 1", "Error 2"],
            "checks": [],
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
        }

        output = format_output(result, "text")
        assert "ERRORS:" in output
        assert "Error 1" in output
        assert "Error 2" in output


class TestTruthGateIntegration:
    """Integration tests for truth gate."""

    def test_end_to_end_workflow_check(self, tmp_path):
        """Test end-to-end workflow status check."""
        # Setup workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "completed": [
                        {
                            "id": "TEST-001",
                            "files_changed": ["src/main.py"],
                            "test_results": {"total_tests": 5},
                        }
                    ],
                }
            )
        )

        # Create actual file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")

        result = check_workflow_status("TEST-001", "workflow.yaml", tmp_path)
        assert result["passed"] is True
        assert result["total_checks"] == 1

    @patch("subprocess.run")
    def test_end_to_end_merge_truth(self, mock_run):
        """Test end-to-end merge truth check."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="* main\n",
        )

        result = check_merge_truth(["abc123"])
        assert result["passed"] is True
        assert result["total_checks"] == 1


class TestInferTestPathFromStory:
    """Tests for infer_test_path_from_story function - TG-002 regression tests."""

    def test_infer_from_files_changed_single_test_dir(self):
        """Test inferring path from files_changed with single test directory."""
        story = {
            "id": "STRONG-001-A",
            "files_changed": [
                "src/strong_system/neural_beliefs/belief.py",
                "tests/test_strong_system/test_neural_beliefs/test_belief.py",
                "tests/test_strong_system/test_neural_beliefs/test_revision.py",
            ],
        }
        result = infer_test_path_from_story(story, "STRONG-001-A")
        # Path is returned without trailing slash (os.path.commonprefix behavior)
        assert result == "tests/test_strong_system/test_neural_beliefs"

    def test_infer_from_files_changed_multiple_test_dirs(self):
        """Test inferring path from files_changed with multiple test directories."""
        story = {
            "id": "MIXED-001",
            "files_changed": [
                "src/module_a/file.py",
                "tests/test_module_a/test_file.py",
                "tests/test_module_b/test_file.py",
            ],
        }
        result = infer_test_path_from_story(story, "MIXED-001")
        # Should fall back to tests/ when multiple directories
        assert result == "tests/"

    def test_infer_from_files_changed_no_tests(self):
        """Test inferring path when no test files in files_changed."""
        story = {
            "id": "NO-TESTS-001",
            "files_changed": [
                "src/module/file.py",
                "docs/readme.md",
            ],
        }
        result = infer_test_path_from_story(story, "NO-TESTS-001")
        assert result is None

    def test_infer_from_story_id_strong_001(self):
        """Test inferring path from STRONG-001 story ID pattern."""
        story = {"id": "STRONG-001-A", "files_changed": []}
        result = infer_test_path_from_story(story, "STRONG-001-A")
        assert result == "tests/test_strong_system/test_neural_beliefs/"

    def test_infer_from_story_id_strong_002(self):
        """Test inferring path from STRONG-002 story ID pattern."""
        story = {"id": "STRONG-002-A", "files_changed": []}
        result = infer_test_path_from_story(story, "STRONG-002-A")
        assert result == "tests/test_strong_system/test_belief_embeddings/"

    def test_infer_from_story_id_strong_003(self):
        """Test inferring path from STRONG-003 story ID pattern."""
        story = {"id": "STRONG-003-A", "files_changed": []}
        result = infer_test_path_from_story(story, "STRONG-003-A")
        assert result == "tests/test_strong_system/test_hypothesis_generator/"

    def test_infer_from_story_id_strong_004(self):
        """Test inferring path from STRONG-004 story ID pattern."""
        story = {"id": "STRONG-004-A", "files_changed": []}
        result = infer_test_path_from_story(story, "STRONG-004-A")
        assert result == "tests/test_strong_system/test_symbolic_rules/"

    def test_infer_from_story_id_generic_strong(self):
        """Test inferring path from generic STRONG story ID."""
        story = {"id": "STRONG-999-A", "files_changed": []}
        result = infer_test_path_from_story(story, "STRONG-999-A")
        assert result == "tests/test_strong_system/"

    def test_infer_no_story_no_id(self):
        """Test inferring path with no story data and no story_id."""
        result = infer_test_path_from_story(None, None)
        assert result is None

    def test_infer_empty_story(self):
        """Test inferring path with empty story data."""
        story = {}
        result = infer_test_path_from_story(story, "UNKNOWN-001")
        assert result is None


class TestFindStoryInWorkflowForTests:
    """Tests for find_story_in_workflow function in test_counts module."""

    def test_find_in_stories_list(self):
        """Test finding story in stories list (new format)."""
        workflow_data = {
            "stories": [
                {"id": "STORY-001", "test_results": {"total_tests": 10}},
                {"id": "STORY-002", "test_results": {"total_tests": 20}},
            ],
        }
        result = find_story_in_workflow_for_tests("STORY-001", workflow_data)
        assert result is not None
        assert result["id"] == "STORY-001"
        assert result["test_results"]["total_tests"] == 10

    def test_find_in_in_progress_legacy(self):
        """Test finding story in in_progress list (legacy format)."""
        workflow_data = {
            "in_progress": [
                {"id": "STORY-001", "test_results": {"total_tests": 10}},
            ],
            "stories": [],
        }
        result = find_story_in_workflow_for_tests("STORY-001", workflow_data)
        assert result is not None
        assert result["id"] == "STORY-001"

    def test_find_in_completed_legacy(self):
        """Test finding story in completed list (legacy format)."""
        workflow_data = {
            "completed": [
                {"id": "STORY-001", "test_results": {"total_tests": 10}},
            ],
            "stories": [],
        }
        result = find_story_in_workflow_for_tests("STORY-001", workflow_data)
        assert result is not None
        assert result["id"] == "STORY-001"

    def test_find_not_found(self):
        """Test when story is not found."""
        workflow_data = {
            "stories": [],
            "in_progress": [],
            "completed": [],
        }
        result = find_story_in_workflow_for_tests("NONEXISTENT", workflow_data)
        assert result is None


class TestStorySpecificPathInference:
    """Integration tests for story-specific test path inference - TG-002."""

    @patch("truth_gate_checks.test_counts.run_pytest_collect")
    def test_story_specific_path_used(self, mock_collect, tmp_path):
        """Test that story-specific path is inferred and used."""
        mock_collect.return_value = {
            "success": True,
            "test_count": 59,
        }

        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "stories": [
                        {
                            "id": "STRONG-001-A-S3",
                            "test_results": {"total_tests": 59},
                            "files_changed": [
                                "src/strong_system/computational_graph/optimizer.py",
                                "tests/test_strong_system/test_computational_graph/test_optimizer.py",
                            ],
                        }
                    ],
                }
            )
        )

        result = check_test_counts(
            story_id="STRONG-001-A-S3",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )

        # Should pass with matching counts
        assert result["passed"] is True
        # Verify the correct path was passed to pytest
        mock_collect.assert_called_once()
        call_args = mock_collect.call_args
        # First positional arg should be the inferred path
        assert "test_strong_system" in call_args[0][0]

    @patch("truth_gate_checks.test_counts.run_pytest_collect")
    def test_fallback_to_tests_when_no_specific_path(self, mock_collect, tmp_path):
        """Test fallback to tests/ when no specific path can be inferred."""
        mock_collect.return_value = {
            "success": True,
            "test_count": 42,
        }

        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(
            yaml.dump(
                {
                    "stories": [
                        {
                            "id": "UNKNOWN-001",
                            "test_results": {"total_tests": 42},
                            "files_changed": [
                                "src/module/file.py",
                            ],
                        }
                    ],
                }
            )
        )

        result = check_test_counts(
            story_id="UNKNOWN-001",
            workflow_file="workflow.yaml",
            repo_root=tmp_path,
        )

        # Should pass with matching counts
        assert result["passed"] is True
        # Verify fallback to tests/ was used
        mock_collect.assert_called_once()
        call_args = mock_collect.call_args
        assert call_args[0][0] == "tests/"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
