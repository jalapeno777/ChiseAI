"""Tests for commit_validator.py.

Validates conventional commit format and story ID presence in commit messages.

Story: SWARM-HARDEN-001-7.1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from commit_validator import (
    CommitValidator,
    ValidationError,
    ValidationIssue,
    ValidationResult,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def validator() -> CommitValidator:
    """Create a default validator with story ID required."""
    return CommitValidator(require_story_id=True)


@pytest.fixture
def validator_no_story() -> CommitValidator:
    """Create a validator without story ID requirement."""
    return CommitValidator(require_story_id=False)


# ---------------------------------------------------------------------------
# ValidationError enum
# ---------------------------------------------------------------------------


class TestValidationError:
    """Tests for ValidationError enum values."""

    def test_enum_values(self) -> None:
        """Test all expected enum members exist."""
        expected = {
            "EMPTY_MESSAGE",
            "NO_CONVENTIONAL_PREFIX",
            "INVALID_TYPE",
            "MISSING_BODY_AFTER_SCOPE",
            "NO_STORY_ID",
            "INVALID_STORY_ID",
        }
        actual = {e.value for e in ValidationError}
        assert actual == expected


# ---------------------------------------------------------------------------
# ValidationIssue dataclass
# ---------------------------------------------------------------------------


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_creation(self) -> None:
        """Test basic issue creation."""
        issue = ValidationIssue(
            code=ValidationError.NO_STORY_ID,
            message="Missing story ID",
            context="feat: some change",
        )
        assert issue.code == ValidationError.NO_STORY_ID
        assert issue.message == "Missing story ID"
        assert issue.context == "feat: some change"

    def test_to_dict_with_context(self) -> None:
        """Test to_dict includes context when present."""
        issue = ValidationIssue(
            code=ValidationError.NO_STORY_ID,
            message="Missing story ID",
            context="feat: some change",
        )
        d = issue.to_dict()
        assert d["code"] == "NO_STORY_ID"
        assert d["message"] == "Missing story ID"
        assert d["context"] == "feat: some change"

    def test_to_dict_without_context(self) -> None:
        """Test to_dict omits context when empty."""
        issue = ValidationIssue(
            code=ValidationError.EMPTY_MESSAGE,
            message="Empty message",
        )
        d = issue.to_dict()
        assert "context" not in d


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Test a valid result."""
        result = ValidationResult(valid=True, message="feat: ok (ST-1)")
        assert result.valid is True
        assert len(result.issues) == 0

    def test_invalid_result(self) -> None:
        """Test an invalid result with issues."""
        issue = ValidationIssue(
            code=ValidationError.NO_CONVENTIONAL_PREFIX,
            message="Bad format",
        )
        result = ValidationResult(valid=False, message="bad message", issues=[issue])
        assert result.valid is False
        assert len(result.issues) == 1

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        issue = ValidationIssue(
            code=ValidationError.NO_STORY_ID,
            message="Missing ID",
            context="feat: change",
        )
        result = ValidationResult(valid=False, message="msg", issues=[issue])
        d = result.to_dict()
        assert d["valid"] is False
        assert d["issue_count"] == 1
        assert len(d["issues"]) == 1
        assert d["issues"][0]["code"] == "NO_STORY_ID"


# ---------------------------------------------------------------------------
# AC1: Conventional commit format validation
# ---------------------------------------------------------------------------


class TestConventionalCommitFormat:
    """Tests for conventional commit format validation (AC1)."""

    def test_feat_type(self, validator) -> None:
        """Test feat: type is accepted."""
        result = validator.validate("feat: Add new endpoint (ST-001)")
        assert result.valid

    def test_fix_type(self, validator) -> None:
        """Test fix: type is accepted."""
        result = validator.validate("fix: Resolve crash on startup (ST-002)")
        assert result.valid

    def test_docs_type(self, validator) -> None:
        """Test docs: type is accepted."""
        result = validator.validate("docs: Update README (ST-003)")
        assert result.valid

    def test_style_type(self, validator) -> None:
        """Test style: type is accepted."""
        result = validator.validate("style: Format code (ST-004)")
        assert result.valid

    def test_refactor_type(self, validator) -> None:
        """Test refactor: type is accepted."""
        result = validator.validate("refactor: Simplify auth flow (ST-005)")
        assert result.valid

    def test_perf_type(self, validator) -> None:
        """Test perf: type is accepted."""
        result = validator.validate("perf: Optimize query (ST-006)")
        assert result.valid

    def test_test_type(self, validator) -> None:
        """Test test: type is accepted."""
        result = validator.validate("test: Add unit tests (ST-007)")
        assert result.valid

    def test_build_type(self, validator) -> None:
        """Test build: type is accepted."""
        result = validator.validate("build: Update Dockerfile (ST-008)")
        assert result.valid

    def test_ci_type(self, validator) -> None:
        """Test ci: type is accepted."""
        result = validator.validate("ci: Fix pipeline (ST-009)")
        assert result.valid

    def test_chore_type(self, validator) -> None:
        """Test chore: type is accepted."""
        result = validator.validate("chore: Update deps (ST-010)")
        assert result.valid

    def test_revert_type(self, validator) -> None:
        """Test revert: type is accepted."""
        result = validator.validate("revert: Undo bad commit (ST-011)")
        assert result.valid

    def test_type_with_scope(self, validator) -> None:
        """Test type(scope): format."""
        result = validator.validate("feat(api): Add endpoint (ST-012)")
        assert result.valid

    def test_type_with_scope_and_breaking(self, validator) -> None:
        """Test type(scope)!: breaking change format."""
        result = validator.validate("feat(api)!: Remove old endpoint (ST-013)")
        assert result.valid

    def test_type_with_breaking_no_scope(self, validator) -> None:
        """Test type!: breaking change without scope."""
        result = validator.validate("fix!: Critical hotfix (ST-014)")
        assert result.valid

    def test_invalid_type_rejected(self, validator) -> None:
        """Test that an unrecognized type is rejected."""
        result = validator.validate("wip: In progress (ST-015)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.INVALID_TYPE in codes

    def test_no_prefix_rejected(self, validator) -> None:
        """Test that a message with no conventional prefix is rejected."""
        result = validator.validate("Some random message (ST-016)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_CONVENTIONAL_PREFIX in codes

    def test_empty_description_rejected(self, validator) -> None:
        """Test that type: with no description is rejected."""
        result = validator.validate("feat: (ST-017)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.MISSING_BODY_AFTER_SCOPE in codes

    def test_empty_message_rejected(self, validator) -> None:
        """Test that empty message is rejected."""
        result = validator.validate("")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.EMPTY_MESSAGE in codes

    def test_whitespace_only_message_rejected(self, validator) -> None:
        """Test that whitespace-only message is rejected."""
        result = validator.validate("   \n\t  ")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.EMPTY_MESSAGE in codes

    def test_multiline_message_validates_first_line(self, validator) -> None:
        """Test that only the first line is validated for format."""
        msg = "feat: Add feature (ST-018)\n\nDetailed body here."
        result = validator.validate(msg)
        assert result.valid

    def test_case_insensitive_type(self, validator) -> None:
        """Test that type matching is case-insensitive."""
        result = validator.validate("FEAT: Uppercase type (ST-019)")
        assert result.valid

    def test_scope_with_dots_and_dashes(self, validator) -> None:
        """Test scopes with various characters."""
        result = validator.validate("feat(auth-v2): Add OAuth (ST-020)")
        assert result.valid


# ---------------------------------------------------------------------------
# AC2: Story ID presence validation
# ---------------------------------------------------------------------------


class TestStoryIdPresence:
    """Tests for story ID presence validation (AC2)."""

    def test_st_prefix(self, validator) -> None:
        """Test ST- prefix is accepted."""
        result = validator.validate("feat: Add feature (ST-001)")
        assert result.valid

    def test_ch_prefix(self, validator) -> None:
        """Test CH- prefix is accepted."""
        result = validator.validate("fix: Fix bug (CH-001)")
        assert result.valid

    def test_ft_prefix(self, validator) -> None:
        """Test FT- prefix is accepted."""
        result = validator.validate("feat: New feature (FT-001)")
        assert result.valid

    def test_reward_prefix(self, validator) -> None:
        """Test REWARD- prefix is accepted."""
        result = validator.validate("feat: Add reward (REWARD-001)")
        assert result.valid

    def test_repo_prefix(self, validator) -> None:
        """Test REPO- prefix is accepted."""
        result = validator.validate("chore: Cleanup (REPO-001)")
        assert result.valid

    def test_safety_prefix(self, validator) -> None:
        """Test SAFETY- prefix is accepted."""
        result = validator.validate("fix: Safety fix (SAFETY-001)")
        assert result.valid

    def test_branch_prefix(self, validator) -> None:
        """Test BRANCH- prefix is accepted."""
        result = validator.validate("ci: Fix branch (BRANCH-001)")
        assert result.valid

    def test_paper_prefix(self, validator) -> None:
        """Test PAPER- prefix is accepted."""
        result = validator.validate("docs: Paper results (PAPER-001)")
        assert result.valid

    def test_recon_prefix(self, validator) -> None:
        """Test RECON- prefix is accepted."""
        result = validator.validate("refactor: Reconcile (RECON-001)")
        assert result.valid

    def test_strong_prefix(self, validator) -> None:
        """Test STRONG- prefix is accepted."""
        result = validator.validate("feat: Strong story (STRONG-001)")
        assert result.valid

    def test_tg_prefix(self, validator) -> None:
        """Test TG- prefix is accepted."""
        result = validator.validate("feat: Task group (TG-001)")
        assert result.valid

    def test_missing_story_id_rejected(self, validator) -> None:
        """Test that missing story ID is rejected."""
        result = validator.validate("feat: Add new endpoint")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_STORY_ID in codes

    def test_story_id_without_digit_rejected(self, validator) -> None:
        """Test that story ID without a digit is rejected."""
        result = validator.validate("feat: Add feature (ST-ABC)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_STORY_ID in codes

    def test_story_id_case_insensitive(self, validator) -> None:
        """Test that story ID matching is case-insensitive."""
        result = validator.validate("feat: Add feature (st-042)")
        assert result.valid

    def test_story_id_in_description_not_parens(self, validator) -> None:
        """Test story ID in description body (not in parens)."""
        result = validator.validate("feat: implement ST-042 feature")
        assert result.valid

    def test_story_id_with_suffix(self, validator) -> None:
        """Test story ID with validation suffix."""
        result = validator.validate("feat: Add feature (STRONG-001-A-S3)")
        assert result.valid

    def test_no_story_id_flag_skips_check(self, validator_no_story) -> None:
        """Test --no-story-id flag skips story ID check."""
        result = validator_no_story.validate("feat: Add new endpoint")
        assert result.valid

    def test_multiple_story_ids(self, validator) -> None:
        """Test message with multiple story IDs."""
        result = validator.validate("feat: Cross-ref ST-042 and CH-007 together")
        assert result.valid

    def test_story_id_missing_with_bad_format(self, validator) -> None:
        """Test both format error and story ID error reported."""
        result = validator.validate("bad commit message")
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_CONVENTIONAL_PREFIX in codes
        assert ValidationError.NO_STORY_ID in codes


# ---------------------------------------------------------------------------
# AC3: Integration / 100% pass rate
# ---------------------------------------------------------------------------


class TestIntegrationValidMessages:
    """Integration tests ensuring valid messages pass cleanly (AC3)."""

    @pytest.mark.parametrize(
        "msg",
        [
            "feat: Add user authentication (ST-042)",
            "fix(core): Resolve memory leak (SAFETY-003)",
            "docs: Update API docs (CH-007)",
            "refactor(api): Simplify middleware (FT-012)",
            "test: Add integration tests (REPO-001)",
            "ci: Fix pipeline gate (BRANCH-002)",
            "perf: Optimize database queries (PAPER-001)",
            "build: Update base image (RECON-005)",
            "chore: Bump version (REWARD-003)",
            "revert: Undo breaking change (STRONG-010)",
            "style: Format with black (TG-001)",
            "feat(dashboard)!: Breaking API change (ST-099)",
            "fix(auth-v2): Resolve OAuth timeout (CH-042)",
        ],
    )
    def test_valid_messages_pass(self, msg: str, validator) -> None:
        """Test that well-formed messages pass all validations."""
        result = validator.validate(msg)
        assert (
            result.valid
        ), f"Expected valid, got issues: {[i.code.value for i in result.issues]} for message: {msg}"


class TestIntegrationInvalidMessages:
    """Integration tests ensuring invalid messages are properly caught."""

    @pytest.mark.parametrize(
        "msg,expected_codes",
        [
            ("", [ValidationError.EMPTY_MESSAGE]),
            (
                "random text without format",
                [ValidationError.NO_CONVENTIONAL_PREFIX, ValidationError.NO_STORY_ID],
            ),
            (
                "wip: doing things",
                [ValidationError.INVALID_TYPE, ValidationError.NO_STORY_ID],
            ),
            (
                "feat:",
                [ValidationError.MISSING_BODY_AFTER_SCOPE, ValidationError.NO_STORY_ID],
            ),
            ("feat: No story here", [ValidationError.NO_STORY_ID]),
            ("ST-042: Random prefix", [ValidationError.NO_CONVENTIONAL_PREFIX]),
        ],
    )
    def test_invalid_messages_fail(
        self, msg: str, expected_codes: list, validator
    ) -> None:
        """Test that malformed messages produce expected errors."""
        result = validator.validate(msg)
        assert not result.valid
        actual_codes = {i.code for i in result.issues}
        for code in expected_codes:
            assert code in actual_codes, (
                f"Expected {code.value} in issues for message: {msg!r}, "
                f"got: {[i.code.value for i in result.issues]}"
            )


# ---------------------------------------------------------------------------
# Extract methods
# ---------------------------------------------------------------------------


class TestExtractMethods:
    """Tests for the extract_* helper methods."""

    def test_extract_story_id(self, validator) -> None:
        """Test story ID extraction."""
        assert validator.extract_story_id("feat: Add feature (ST-042)") == "ST-042"
        assert validator.extract_story_id("fix: Fix bug CH-007") == "CH-007"
        assert validator.extract_story_id("No story here") is None
        assert validator.extract_story_id("") is None

    def test_extract_type(self, validator) -> None:
        """Test type extraction."""
        assert validator.extract_type("feat: Add feature (ST-042)") == "feat"
        assert validator.extract_type("fix(core): Fix bug (ST-001)") == "fix"
        assert validator.extract_type("bad message") is None
        assert validator.extract_type("") is None

    def test_extract_scope(self, validator) -> None:
        """Test scope extraction."""
        assert validator.extract_scope("feat(api): Add endpoint (ST-001)") == "api"
        assert validator.extract_scope("fix: No scope (ST-001)") is None
        assert validator.extract_scope("bad message") is None
        assert validator.extract_scope("") is None

    def test_is_breaking(self, validator) -> None:
        """Test breaking change detection."""
        assert validator.is_breaking("feat!: Breaking change (ST-001)") is True
        assert validator.is_breaking("feat(api)!: Breaking (ST-001)") is True
        assert validator.is_breaking("feat: Normal change (ST-001)") is False
        assert validator.is_breaking("bad message") is False
        assert validator.is_breaking("") is False


# ---------------------------------------------------------------------------
# Custom allowed types
# ---------------------------------------------------------------------------


class TestCustomAllowedTypes:
    """Tests for custom allowed_types configuration."""

    def test_restricted_types(self) -> None:
        """Test validator with only feat and fix allowed."""
        v = CommitValidator(
            require_story_id=True,
            allowed_types=frozenset({"feat", "fix"}),
        )
        # feat should pass
        result = v.validate("feat: New feature (ST-001)")
        assert result.valid
        # docs should fail
        result = v.validate("docs: Update readme (ST-002)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.INVALID_TYPE in codes


# ---------------------------------------------------------------------------
# Main / CLI
# ---------------------------------------------------------------------------


class TestMainFunction:
    """Tests for the CLI main() entry point."""

    def test_main_valid_message(self) -> None:
        """Test main with a valid commit message."""
        with patch("sys.argv", ["commit_validator.py", "feat: Add feature (ST-001)"]):
            assert main() == 0

    def test_main_invalid_message(self) -> None:
        """Test main with an invalid commit message."""
        with patch("sys.argv", ["commit_validator.py", "bad message"]):
            assert main() == 1

    def test_main_empty_message(self) -> None:
        """Test main with no arguments (should error)."""
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["commit_validator.py"]):
                main()

    def test_main_no_story_id_flag(self) -> None:
        """Test main with --no-story-id flag."""
        with patch(
            "sys.argv", ["commit_validator.py", "--no-story-id", "feat: Add feature"]
        ):
            assert main() == 0

    def test_main_json_output_valid(self) -> None:
        """Test main with --json flag and valid message."""
        with patch(
            "sys.argv", ["commit_validator.py", "--json", "feat: Add feature (ST-001)"]
        ):
            assert main() == 0

    def test_main_json_output_invalid(self) -> None:
        """Test main with --json flag and invalid message."""
        with patch("sys.argv", ["commit_validator.py", "--json", "bad message"]):
            assert main() == 1

    def test_main_message_file(self, tmp_path: Path) -> None:
        """Test main with --message-file flag."""
        msg_file = tmp_path / "commit_msg.txt"
        msg_file.write_text("feat: Add feature (ST-001)\n")
        with patch(
            "sys.argv", ["commit_validator.py", "--message-file", str(msg_file)]
        ):
            assert main() == 0

    def test_main_message_file_not_found(self) -> None:
        """Test main with nonexistent message file."""
        with patch(
            "sys.argv", ["commit_validator.py", "--message-file", "/nonexistent/file"]
        ):
            assert main() == 2

    def test_main_json_output_is_valid_json(self) -> None:
        """Test that --json produces valid JSON output."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with patch("sys.argv", ["commit_validator.py", "--json", "feat: Add (ST-001)"]):
            with redirect_stdout(buf):
                main()
        output = buf.getvalue()
        parsed = json.loads(output)
        assert parsed["valid"] is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_none_message(self, validator) -> None:
        """Test None as message input."""
        result = validator.validate("")  # Empty string simulates None-like
        assert not result.valid

    def test_very_long_message(self, validator) -> None:
        """Test very long commit message."""
        long_desc = "x" * 500
        result = validator.validate(f"feat: {long_desc} (ST-001)")
        assert result.valid

    def test_unicode_message(self, validator) -> None:
        """Test unicode in commit message."""
        result = validator.validate("feat: Add 日本語 support (ST-001)")
        assert result.valid

    def test_story_id_at_end_no_parens(self, validator) -> None:
        """Test story ID at end of description without parentheses."""
        result = validator.validate("feat: implement feature for ST-042")
        assert result.valid

    def test_story_id_in_middle(self, validator) -> None:
        """Test story ID in the middle of description."""
        result = validator.validate("feat: ST-042 is now implemented")
        assert result.valid

    def test_lookalike_rejected(self, validator) -> None:
        """Test that lookalike but unrecognized prefix is rejected."""
        result = validator.validate("feat: Implement XY-123 feature")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_STORY_ID in codes

    def test_story_id_with_many_digits(self, validator) -> None:
        """Test story ID with many digits."""
        result = validator.validate("feat: Very large ID (ST-999999)")
        assert result.valid

    def test_multiline_with_story_id_in_body(self, validator) -> None:
        """Test story ID only in body, not first line."""
        msg = "feat: Add feature\n\nRefs ST-042 for details."
        result = validator.validate(msg)
        # Story ID search is on first line only per the implementation
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.NO_STORY_ID in codes

    def test_message_with_trailing_newline(self, validator) -> None:
        """Test message with trailing newline (common from git)."""
        result = validator.validate("feat: Add feature (ST-001)\n")
        assert result.valid

    def test_message_with_multiple_newlines(self, validator) -> None:
        """Test message with multiple trailing newlines."""
        result = validator.validate("feat: Add feature (ST-001)\n\n\n")
        assert result.valid

    def test_only_prefix_and_story_no_desc(self, validator) -> None:
        """Test prefix with story ID but no description."""
        result = validator.validate("feat: (ST-001)")
        assert not result.valid
        codes = [i.code for i in result.issues]
        assert ValidationError.MISSING_BODY_AFTER_SCOPE in codes
