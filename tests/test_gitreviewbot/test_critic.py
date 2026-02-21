"""Tests for Critic reviewer."""

import pytest
from datetime import datetime

from autonomous_git.gitreviewbot.models import (
    Violation,
    Severity,
    ReviewResult,
)
from autonomous_git.gitreviewbot.critic import CriticReviewer


@pytest.fixture
def critic():
    """Create a CriticReviewer for testing."""
    return CriticReviewer()


class TestCriticReviewer:
    """Test CriticReviewer."""

    async def test_review_valid_pr(self, critic):
        """Test reviewing valid PR."""
        diff = """diff --git a/src/test.py b/src/test.py
+def hello():
+    return "Hello"
"""

        result = await critic.review(
            pr_title="ST-123: Add hello",
            story_id="ST-123",
            diff=diff,
            files=["src/test.py"],
        )

        assert result.role == "Critic"
        assert result.confidence > 0

    async def test_review_missing_story_id(self, critic):
        """Test reviewing PR without story ID."""
        diff = """diff --git a/src/test.py b/src/test.py
+def hello():
+    return "Hello"
"""

        result = await critic.review(
            pr_title="Add hello function",  # No story ID
            story_id=None,
            diff=diff,
            files=["src/test.py"],
        )

        assert result.role == "Critic"
        # Should have violation for missing story ID
        assert any(v.rule == "missing_story_id" for v in result.violations)
        assert "Missing story ID" in result.blockers


class TestStaticChecks:
    """Test static compliance checks."""

    def test_check_story_id_present(self, critic):
        """Test story ID detection when present."""
        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test PR",
            story_id="ST-123",
            diff="",
            files=["test.py"],
        )

        assert len(violations) == 0
        assert len(blockers) == 0

    def test_check_story_id_missing(self, critic):
        """Test story ID detection when missing."""
        violations, blockers = critic._run_static_checks(
            pr_title="Test PR",
            story_id=None,
            diff="",
            files=["test.py"],
        )

        assert any(v.rule == "missing_story_id" for v in violations)
        assert "Missing story ID" in blockers

    def test_check_hardcoded_secret(self, critic):
        """Test detection of hardcoded secrets."""
        diff = """
+password = "secret123"
+api_key = "abc123"
"""

        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff=diff,
            files=["config.py"],
        )

        assert any(v.rule == "potential_secret" for v in violations)
        assert any("secret" in b.lower() for b in blockers)

    def test_check_debug_code(self, critic):
        """Test detection of debug code."""
        diff = """
+def func():
+    import pdb; pdb.set_trace()
+    return 42
"""

        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff=diff,
            files=["test.py"],
        )

        assert any(v.rule == "debug_code" for v in violations)

    def test_check_todo_without_ticket(self, critic):
        """Test detection of TODO without ticket."""
        diff = """
+def func():
+    # TODO: fix this later
+    pass
"""

        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff=diff,
            files=["test.py"],
        )

        assert any(v.rule == "todo_without_ticket" for v in violations)

    def test_check_todo_with_ticket(self, critic):
        """Test TODO with ticket is allowed."""
        diff = """
+def func():
+    # TODO(ST-456): fix this later
+    pass
"""

        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff=diff,
            files=["test.py"],
        )

        # Should not flag TODO with ticket
        assert not any(v.rule == "todo_without_ticket" for v in violations)

    def test_check_protected_file_woodpecker(self, critic):
        """Test detection of protected file modification (woodpecker)."""
        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff="",
            files=[".woodpecker.yml"],
        )

        assert any(v.rule == "protected_file_modified" for v in violations)

    def test_check_protected_file_terraform(self, critic):
        """Test detection of protected file modification (terraform)."""
        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff="",
            files=["infrastructure/terraform/main.tf"],
        )

        assert any(v.rule == "protected_file_modified" for v in violations)

    def test_check_protected_file_agents(self, critic):
        """Test detection of protected file modification (AGENTS.md)."""
        violations, blockers = critic._run_static_checks(
            pr_title="ST-123: Test",
            story_id="ST-123",
            diff="",
            files=["AGENTS.md"],
        )

        assert any(v.rule == "protected_file_modified" for v in violations)


class TestComplianceScore:
    """Test compliance score calculation."""

    def test_perfect_compliance(self, critic):
        """Test score with no violations."""
        score = critic._calculate_compliance_score([])

        assert score == 100.0

    def test_error_violation(self, critic):
        """Test score with error violation."""
        violations = [
            Violation(rule="test", severity=Severity.ERROR, message="Error"),
        ]

        score = critic._calculate_compliance_score(violations)

        assert score == 85.0  # 100 - 15

    def test_warning_violation(self, critic):
        """Test score with warning violation."""
        violations = [
            Violation(rule="test", severity=Severity.WARNING, message="Warning"),
        ]

        score = critic._calculate_compliance_score(violations)

        assert score == 95.0  # 100 - 5

    def test_info_violation(self, critic):
        """Test score with info violation."""
        violations = [
            Violation(rule="test", severity=Severity.INFO, message="Info"),
        ]

        score = critic._calculate_compliance_score(violations)

        assert score == 99.0  # 100 - 1

    def test_multiple_violations(self, critic):
        """Test score with multiple violations."""
        violations = [
            Violation(rule="e1", severity=Severity.ERROR, message="Error 1"),
            Violation(rule="e2", severity=Severity.ERROR, message="Error 2"),
            Violation(rule="w1", severity=Severity.WARNING, message="Warning"),
        ]

        score = critic._calculate_compliance_score(violations)

        assert score == 65.0  # 100 - 15 - 15 - 5

    def test_score_clamped_to_zero(self, critic):
        """Test score is clamped to minimum of 0."""
        violations = [
            Violation(rule=f"e{i}", severity=Severity.ERROR, message="Error")
            for i in range(10)
        ]

        score = critic._calculate_compliance_score(violations)

        assert score == 0.0


class TestGenerateSummary:
    """Test summary generation."""

    def test_summary_no_violations(self, critic):
        """Test summary with no violations."""
        summary = critic._generate_summary([], 100.0)

        assert "passed" in summary.lower()
        assert "100.0%" in summary

    def test_summary_with_errors(self, critic):
        """Test summary with errors."""
        violations = [
            Violation(rule="e1", severity=Severity.ERROR, message="Error 1"),
            Violation(rule="e2", severity=Severity.ERROR, message="Error 2"),
        ]

        summary = critic._generate_summary(violations, 70.0)

        assert "2 error(s)" in summary
        assert "70.0%" in summary

    def test_summary_with_warnings(self, critic):
        """Test summary with warnings."""
        violations = [
            Violation(rule="w1", severity=Severity.WARNING, message="Warning 1"),
        ]

        summary = critic._generate_summary(violations, 95.0)

        assert "1 warning(s)" in summary
        assert "95.0%" in summary

    def test_summary_with_errors_and_warnings(self, critic):
        """Test summary with both errors and warnings."""
        violations = [
            Violation(rule="e1", severity=Severity.ERROR, message="Error"),
            Violation(rule="w1", severity=Severity.WARNING, message="Warning"),
        ]

        summary = critic._generate_summary(violations, 80.0)

        assert "1 error(s)" in summary
        assert "1 warning(s)" in summary


class TestParseLLMResponse:
    """Test LLM response parsing."""

    def test_parse_valid_response(self, critic):
        """Test parsing valid LLM response."""
        response = """
        {
            "violations": [
                {
                    "rule": "missing_docs",
                    "severity": "warning",
                    "message": "Documentation missing",
                    "file": "README.md"
                }
            ],
            "compliance_score": 85,
            "blockers": []
        }
        """

        violations = critic._parse_llm_response(response)

        assert len(violations) == 1
        assert violations[0].rule == "missing_docs"

    def test_parse_empty_response(self, critic):
        """Test parsing empty response."""
        violations = critic._parse_llm_response("")

        assert len(violations) == 0

    def test_parse_invalid_json(self, critic):
        """Test parsing invalid JSON."""
        violations = critic._parse_llm_response("not json")

        assert len(violations) == 0
