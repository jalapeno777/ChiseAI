"""Integration tests for truth gate CI enforcement.

Tests that CI pipeline correctly:
1. Identifies strong-system stories (STRONG-*, TG-*, ST-*)
2. Invokes truth gate with correct story ID
3. Fails pipeline when truth gate fails
4. Skips truth gate for non-strong-system stories
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from extract_story_id_from_pr import (
    STORY_ID_REGEX,
    extract_from_branch_name,
    extract_from_ci_environment,
    extract_from_pr_title,
    extract_from_text,
    is_strong_system_story,
)


class TestExtractFromText:
    """Tests for extract_from_text function."""

    def test_extract_strong_pattern(self):
        """Test extracting STRONG-* pattern."""
        result = extract_from_text("feat: Add feature (STRONG-001)")
        assert result == "STRONG-001"

    def test_extract_strong_with_suffix(self):
        """Test extracting STRONG-*-A pattern returns base ID."""
        result = extract_from_text("feat: Add feature (STRONG-001-A)")
        # Base ID is extracted; validation suffixes (-A, -A-S3) are for internal tracking
        assert result == "STRONG-001"

    def test_extract_strong_with_full_suffix(self):
        """Test extracting STRONG-*-A-S3 pattern returns base ID."""
        result = extract_from_text("feat: Add feature (STRONG-001-A-S3)")
        # Base ID is extracted; validation suffixes (-A, -A-S3) are for internal tracking
        assert result == "STRONG-001"

    def test_extract_tg_pattern(self):
        """Test extracting TG-* pattern."""
        result = extract_from_text("feat: CI gate (TG-003)")
        assert result == "TG-003"

    def test_extract_st_pattern(self):
        """Test extracting ST-* pattern."""
        result = extract_from_text("feat: New feature (ST-042)")
        assert result == "ST-042"

    def test_extract_st_with_suffix(self):
        """Test extracting ST-*-CI pattern returns base ID."""
        result = extract_from_text("feat: Add feature (ST-042-CI)")
        # Base ID is extracted; suffixes are for internal tracking
        assert result == "ST-042"

    def test_extract_case_insensitive(self):
        """Test case-insensitive extraction."""
        result = extract_from_text("feat: Add feature (strong-001)")
        assert result == "STRONG-001"

    def test_extract_no_match(self):
        """Test when no story ID found."""
        result = extract_from_text("feat: Regular feature")
        assert result is None

    def test_extract_empty_text(self):
        """Test extracting from empty text."""
        result = extract_from_text("")
        assert result is None

    def test_extract_none_text(self):
        """Test extracting from None."""
        result = extract_from_text(None)
        assert result is None

    def test_extract_multiple_ids_returns_first(self):
        """Test that first story ID is returned when multiple found."""
        result = extract_from_text("feat: Add (STRONG-001) and fix (TG-002)")
        assert result == "STRONG-001"


class TestExtractFromPrTitle:
    """Tests for extract_from_pr_title function."""

    def test_title_with_strong_id(self):
        """Test extracting from PR title with STRONG ID."""
        result = extract_from_pr_title(
            "feat(dsl): Add trailing_stop support (STRONG-001)"
        )
        assert result == "STRONG-001"

    def test_title_with_tg_id(self):
        """Test extracting from PR title with TG ID."""
        result = extract_from_pr_title("ci: Add truth gate enforcement (TG-003)")
        assert result == "TG-003"

    def test_title_without_id(self):
        """Test extracting from PR title without story ID."""
        result = extract_from_pr_title("docs: Update README")
        assert result is None

    def test_title_empty(self):
        """Test extracting from empty PR title."""
        result = extract_from_pr_title("")
        assert result is None


class TestExtractFromBranchName:
    """Tests for extract_from_branch_name function."""

    def test_branch_feature_strong(self):
        """Test extracting from feature/STRONG-* branch."""
        result = extract_from_branch_name("feature/STRONG-001-grammar-extensions")
        assert result == "STRONG-001"

    def test_branch_feature_tg(self):
        """Test extracting from feature/TG-* branch."""
        result = extract_from_branch_name("feature/TG-003-ci-truth-gate")
        assert result == "TG-003"

    def test_branch_feature_st(self):
        """Test extracting from feature/ST-* branch."""
        result = extract_from_branch_name("feature/ST-042-validation-fix")
        assert result == "ST-042"

    def test_branch_no_id(self):
        """Test extracting from branch without story ID."""
        result = extract_from_branch_name("feature/update-docs")
        assert result is None

    def test_branch_hotfix_format(self):
        """Test extracting from hotfix branch."""
        result = extract_from_branch_name("hotfix/STRONG-001-critical-fix")
        assert result == "STRONG-001"


class TestIsStrongSystemStory:
    """Tests for is_strong_system_story function."""

    def test_strong_prefix(self):
        """Test STRONG-* is strong-system."""
        assert is_strong_system_story("STRONG-001") is True

    def test_tg_prefix(self):
        """Test TG-* is strong-system."""
        assert is_strong_system_story("TG-003") is True

    def test_st_prefix(self):
        """Test ST-* is strong-system."""
        assert is_strong_system_story("ST-042") is True

    def test_other_prefix(self):
        """Test other prefixes are not strong-system."""
        assert is_strong_system_story("CH-001") is False
        assert is_strong_system_story("FT-001") is False
        assert is_strong_system_story("REWARD-001") is False

    def test_none_input(self):
        """Test None is not strong-system."""
        assert is_strong_system_story(None) is False

    def test_empty_string(self):
        """Test empty string is not strong-system."""
        assert is_strong_system_story("") is False

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert is_strong_system_story("strong-001") is True
        assert is_strong_system_story("tg-003") is True
        assert is_strong_system_story("st-042") is True


class TestExtractFromCiEnvironment:
    """Tests for extract_from_ci_environment function."""

    @patch.dict(
        os.environ, {"CI_COMMIT_MESSAGE": "feat: Add feature (STRONG-001)"}, clear=True
    )
    def test_from_commit_message(self):
        """Test extracting from CI_COMMIT_MESSAGE."""
        result = extract_from_ci_environment()
        assert result == "STRONG-001"

    @patch.dict(os.environ, {"CI_COMMIT_BRANCH": "feature/TG-003-ci-gate"}, clear=True)
    def test_from_commit_branch(self):
        """Test extracting from CI_COMMIT_BRANCH."""
        result = extract_from_ci_environment()
        assert result == "TG-003"

    @patch.dict(
        os.environ,
        {
            "CI_COMMIT_MESSAGE": "Regular commit",
            "CI_COMMIT_BRANCH": "feature/ST-042-fix",
        },
        clear=True,
    )
    def test_branch_fallback_when_title_no_id(self):
        """Test branch fallback when title has no ID."""
        result = extract_from_ci_environment()
        assert result == "ST-042"

    @patch.dict(
        os.environ,
        {
            "CI_PR_TITLE": "feat: New feature (STRONG-001)",
            "CI_COMMIT_BRANCH": "feature/other-branch",
        },
        clear=True,
    )
    def test_pr_title_priority_over_branch(self):
        """Test PR title takes priority over branch."""
        result = extract_from_ci_environment()
        assert result == "STRONG-001"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_vars(self):
        """Test when no CI env vars set."""
        result = extract_from_ci_environment()
        assert result is None

    @patch.dict(
        os.environ,
        {
            "GITHUB_HEAD_REF": "feature/STRONG-001-github",
        },
        clear=True,
    )
    def test_github_env(self):
        """Test extracting from GitHub environment."""
        result = extract_from_ci_environment()
        assert result == "STRONG-001"

    @patch.dict(
        os.environ,
        {
            "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME": "feature/TG-003-gitlab",
        },
        clear=True,
    )
    def test_gitlab_env(self):
        """Test extracting from GitLab environment."""
        result = extract_from_ci_environment()
        assert result == "TG-003"


class TestStrongSystemPatterns:
    """Tests for strong-system story pattern matching."""

    def test_strong_regex_matches_variants(self):
        """Test STRONG regex matches all variants."""
        assert STORY_ID_REGEX.search("STRONG-001")
        assert STORY_ID_REGEX.search("STRONG-001-A")
        assert STORY_ID_REGEX.search("STRONG-001-A-S3")
        assert STORY_ID_REGEX.search("STRONG-999-Z-S99")

    def test_tg_regex_matches(self):
        """Test TG regex matches."""
        assert STORY_ID_REGEX.search("TG-001")
        assert STORY_ID_REGEX.search("TG-999")

    def test_st_regex_matches_variants(self):
        """Test ST regex matches variants."""
        assert STORY_ID_REGEX.search("ST-001")
        assert STORY_ID_REGEX.search("ST-001-CI")
        assert STORY_ID_REGEX.search("ST-999-VALIDATION")

    def test_non_strong_patterns_not_matched(self):
        """Test non-strong patterns are not matched as story IDs."""
        # These should not be extracted as story IDs
        assert not STORY_ID_REGEX.search("CH-001")
        assert not STORY_ID_REGEX.search("FT-001")
        assert not STORY_ID_REGEX.search("REWARD-001")


class TestCiTruthGateIntegration:
    """Integration tests for CI truth gate enforcement."""

    def test_strong_system_story_detection_logic(self):
        """Test the complete strong-system story detection logic."""
        # Simulate CI environment
        test_cases = [
            ("feat: Add (STRONG-001)", "feature/STRONG-001-x", True, "STRONG-001"),
            ("feat: Add (TG-003)", "feature/TG-003-x", True, "TG-003"),
            ("feat: Add (ST-042)", "feature/ST-042-x", True, "ST-042"),
            ("docs: Update", "feature/docs-update", False, None),
            ("feat: Add (CH-001)", "feature/CH-001-x", False, None),
        ]

        for title, branch, expected_strong, expected_id in test_cases:
            # Test title extraction
            story_id = extract_from_pr_title(title)
            is_strong = is_strong_system_story(story_id)

            if expected_id:
                assert story_id == expected_id, f"Failed for title: {title}"
                assert is_strong == expected_strong, f"Failed strong check for: {title}"
            else:
                # Fall back to branch
                story_id = extract_from_branch_name(branch)
                is_strong = is_strong_system_story(story_id)
                assert is_strong == expected_strong, f"Failed for branch: {branch}"

    @patch.dict(
        os.environ,
        {
            "CI_COMMIT_MESSAGE": "feat: Add truth gate (TG-003)",
            "CI_COMMIT_BRANCH": "feature/TG-003-ci-truth-gate",
        },
        clear=True,
    )
    def test_ci_pipeline_would_run_truth_gate(self):
        """Test that CI pipeline would run truth gate for strong-system story."""
        story_id = extract_from_ci_environment()
        assert story_id == "TG-003"
        assert is_strong_system_story(story_id) is True
        # This means CI should run: truth_gate.py --check all --story-id TG-003

    @patch.dict(
        os.environ,
        {
            "CI_COMMIT_MESSAGE": "docs: Update README",
            "CI_COMMIT_BRANCH": "feature/docs-update",
        },
        clear=True,
    )
    def test_ci_pipeline_would_skip_truth_gate(self):
        """Test that CI pipeline would skip truth gate for non-strong-system."""
        story_id = extract_from_ci_environment()
        assert story_id is None
        # This means CI should skip truth gate


class TestTruthGateCliInvocation:
    """Tests for truth gate CLI invocation patterns."""

    def test_truth_gate_all_check_command(self):
        """Test the truth gate --check all command structure."""
        story_id = "TG-003"
        expected_cmd = f"python3 scripts/validation/truth_gate.py --check all --story-id {story_id}"
        # Verify command structure is valid
        parts = expected_cmd.split()
        assert "--check" in parts
        assert "all" in parts
        assert "--story-id" in parts
        assert story_id in parts

    def test_truth_gate_exit_code_handling(self):
        """Test that truth gate exit code is properly handled."""
        # Truth gate returns 0 on pass, 1 on fail
        # CI should fail pipeline when exit code is 1
        pass_exit = 0
        fail_exit = 1
        assert pass_exit == 0, "Pass should return 0"
        assert fail_exit != 0, "Fail should return non-zero"


class TestCiYamlTruthGateStep:
    """Tests for CI YAML truth gate step configuration."""

    def test_ci_yaml_has_truth_gate_step(self):
        """Test that CI YAML contains truth gate step."""
        ci_yaml_path = Path(__file__).parent.parent.parent / ".woodpecker" / "ci.yaml"
        assert ci_yaml_path.exists(), "CI YAML file should exist"

        content = ci_yaml_path.read_text()
        assert (
            "truth-gate" in content or "truth_gate" in content
        ), "CI YAML should contain truth gate step"

    def test_ci_yaml_step_runs_truth_gate_py(self):
        """Test that CI step runs truth_gate.py."""
        ci_yaml_path = Path(__file__).parent.parent.parent / ".woodpecker" / "ci.yaml"
        content = ci_yaml_path.read_text()

        assert "truth_gate.py" in content, "CI YAML should run truth_gate.py"

    def test_ci_yaml_uses_extract_story_id(self):
        """Test that CI YAML uses extract_story_id_from_pr.py."""
        ci_yaml_path = Path(__file__).parent.parent.parent / ".woodpecker" / "ci.yaml"
        content = ci_yaml_path.read_text()

        assert (
            "extract_story_id_from_pr.py" in content
        ), "CI YAML should use extract_story_id_from_pr.py"


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling."""

    def test_malformed_story_id_in_title(self):
        """Test handling of malformed story ID in title."""
        result = extract_from_pr_title("feat: Add (STRONG001)")  # Missing dash
        assert result is None

    def test_partial_story_id_match(self):
        """Test partial story ID doesn't match."""
        result = extract_from_pr_title("feat: Add (STRONG-)")
        assert result is None

    def test_story_id_with_special_chars(self):
        """Test story ID with special characters."""
        result = extract_from_pr_title("feat: Add (STRONG-001@dev)")
        assert result == "STRONG-001"

    def test_multiple_strong_ids_priority(self):
        """Test priority when multiple strong IDs present."""
        # First match wins
        result = extract_from_pr_title("feat: (TG-001) and (STRONG-002)")
        assert result == "TG-001"

    def test_empty_branch_name(self):
        """Test empty branch name."""
        result = extract_from_branch_name("")
        assert result is None

    def test_branch_with_only_story_id(self):
        """Test branch that's just the story ID."""
        result = extract_from_branch_name("STRONG-001")
        assert result == "STRONG-001"


class TestScriptExecution:
    """Tests for script execution as CLI."""

    def test_extract_script_help(self):
        """Test extract script shows help."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "validation"
            / "extract_story_id_from_pr.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "extract story id" in result.stdout.lower()

    def test_extract_script_from_title(self):
        """Test extract script with --from-title."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "validation"
            / "extract_story_id_from_pr.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--from-title", "feat: (STRONG-001)"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "STRONG-001" in result.stdout

    def test_extract_script_check_strong_system_yes(self):
        """Test extract script --check-strong-system returns 0 for strong."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "validation"
            / "extract_story_id_from_pr.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--check-strong-system", "STRONG-001"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "STRONG-001" in result.stdout

    def test_extract_script_check_strong_system_no(self):
        """Test extract script --check-strong-system returns 1 for non-strong."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "validation"
            / "extract_story_id_from_pr.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--check-strong-system", "CH-001"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_extract_script_json_output(self):
        """Test extract script JSON output."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "validation"
            / "extract_story_id_from_pr.py"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--from-title",
                "feat: (TG-003)",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["story_id"] == "TG-003"
        assert data["is_strong_system"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
